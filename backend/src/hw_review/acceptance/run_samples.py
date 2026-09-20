"""Run the frozen 17-file, read-only A11 acceptance matrix."""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import psutil

from hw_review.config import get_settings
from hw_review.domain import FileRole, ReviewInput, ReviewSource, SourceFileCreate
from hw_review.parsers import DocParser, PdfParser, XlsParser
from hw_review.rules import A11Engine, NormalizedDocumentQuery
from hw_review.services.cleanup import WorkspaceCleaner
from hw_review.services.staging import FileStager, fingerprint


MAX_GATE_SECONDS = 20 * 60

# The frozen sample tree lives outside the repository, so the manifest stores
# only repository-safe relative paths and the root is supplied by the caller.
SAMPLE_ROOT_ENV = "HW_REVIEW_SAMPLE_ROOT"

# This runner parses reports and evaluates rules. It cannot exercise the task
# lifecycle or drive a real browser, so G6/G8 are only as trustworthy as the
# evidence handed to it. Earlier revisions scraped prose out of historical task
# reports, which made both gates report GO no matter what the current code did.
# They now consume structured, dated evidence and abstain ("NOT_RUN") whenever it
# is missing, unreadable, stale or from an unsupported schema.
GATE_EVIDENCE_ENV = "HW_REVIEW_GATE_EVIDENCE"
GATE_EVIDENCE_RELATIVE_PATH = Path("docs") / "evidence" / "gate-evidence" / "gates.json"
GATE_EVIDENCE_SCHEMA_VERSION = "1.0"
GATE_EVIDENCE_MAX_AGE_DAYS = 30
# A floor so that a token suite cannot satisfy the lifecycle gate.
MIN_LIFECYCLE_SUITE_PASSED = 100
REQUIRED_UI_VIEWPORTS = ("1440x900", "1280x720", "760x900")
GATE_STATUS_GO = "GO"
GATE_STATUS_NO_GO = "NO-GO"
GATE_STATUS_NOT_RUN = "NOT_RUN"


class SamplePathError(ValueError):
    """Manifest path defect; it must not be reported as a parsing failure."""


class PeakRssSampler:
    """Sample this process and its descendants while one operation runs."""

    def __init__(self, interval_seconds: float = 0.05) -> None:
        self._process = psutil.Process()
        self._interval = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.peak_bytes = 0

    def _sample(self) -> None:
        total = 0
        for process in [self._process, *self._process.children(recursive=True)]:
            try:
                total += process.memory_info().rss
            except (psutil.Error, OSError):
                continue
        self.peak_bytes = max(self.peak_bytes, total)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            self._sample()

    def __enter__(self) -> "PeakRssSampler":
        self._sample()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_args) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        self._sample()

    @property
    def peak_mib(self) -> float:
        return round(self.peak_bytes / 1024 / 1024, 3)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fingerprint_payload(path: Path) -> dict:
    item = fingerprint(path)
    return {
        "sha256": item.sha256,
        "size_bytes": item.size_bytes,
        "mtime_ns": item.mtime_ns,
    }


def _stable_error(error: BaseException, fallback: str) -> tuple[str, str]:
    code = str(getattr(error, "code", fallback))
    message = str(error).strip() or type(error).__name__
    return code[:100], message[:1000]


def _document_counts(document) -> dict:
    blocks = [block for container in document.containers for block in container.blocks]
    return {
        "container_count": document.container_count,
        "text_block_count": sum(block.kind == "text" for block in blocks),
        "table_block_count": sum(block.kind == "table" for block in blocks),
        "image_block_count": sum(block.kind == "image" for block in blocks),
        "attachment_block_count": sum(block.kind == "attachment" for block in blocks),
        "cell_count": sum(len(block.cells) for block in blocks if block.kind == "table"),
    }


def _portable_parts(relative_path: str) -> tuple[str, ...]:
    """Normalize the manifest separator so one manifest works on every platform."""

    return tuple(part for part in relative_path.replace("\\", "/").split("/") if part)


def resolve_sample_path(sample_root: Path, relative_path: object) -> Path:
    """Resolve one manifest entry, refusing anything outside the sample root.

    Dropping the committed absolute paths makes ``relative_path`` the only input,
    so it must not be able to reach outside the root the caller supplied.
    """

    if not isinstance(relative_path, str) or not relative_path.strip():
        raise SamplePathError(
            f"manifest relative_path must be a non-empty string, got {relative_path!r}"
        )
    normalized = relative_path.replace("\\", "/")
    parts = _portable_parts(relative_path)
    if not parts:
        raise SamplePathError(f"manifest relative_path is empty: {relative_path!r}")
    if normalized.startswith("/") or ":" in parts[0]:
        raise SamplePathError(
            f"manifest relative_path must be relative, not absolute: {relative_path}"
        )
    if any(part == ".." for part in parts):
        raise SamplePathError(
            f"manifest relative_path must not traverse upwards: {relative_path}"
        )
    root = Path(sample_root).resolve()
    candidate = (root / Path(*parts)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise SamplePathError(
            f"manifest relative_path escapes the sample root: {relative_path}"
        ) from error
    return candidate


def _load_manifest(path: Path, sample_root: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    samples = payload.get("samples")
    if not isinstance(samples, list) or len(samples) != 17:
        raise ValueError("manifest must contain exactly 17 samples")
    ids = [item.get("id") for item in samples]
    if len(ids) != len(set(ids)):
        raise ValueError("sample IDs must be unique")
    groups = {item.get("group_id") for item in samples}
    if len(groups) != 15:
        raise ValueError("manifest must contain exactly 15 business groups")
    # Fail fast on a malformed manifest rather than emit suspect evidence.
    for item in samples:
        resolve_sample_path(sample_root, item.get("relative_path"))
    return payload


def _parse_samples(
    manifest: dict,
    output_dir: Path,
    *,
    sample_root: Path,
    word_policy: str | None = None,
) -> tuple[list[dict], dict[str, tuple]]:
    work_root = output_dir / "_work"
    stager = FileStager(work_root)
    cleaner = WorkspaceCleaner(work_root)
    parsers = {
        "XLS": XlsParser(),
        "PDF": PdfParser(),
        # The acceptance run must honour the same converter trust policy as the
        # service, otherwise a WPS-only host can never produce DOC evidence.
        "DOC": DocParser(
            timeout_seconds=MAX_GATE_SECONDS,
            word_policy=word_policy or get_settings().word_automation_policy,
        ),
    }
    records: list[dict] = []
    parsed: dict[str, tuple] = {}

    for sample in manifest["samples"]:
        # Record only the portable manifest path: the resolved absolute path is an
        # implementation detail and must not reach committed evidence.
        relative_path = sample.get("relative_path")
        path_error: SamplePathError | None = None
        try:
            source_path = resolve_sample_path(sample_root, relative_path)
        except SamplePathError as error:
            source_path = Path(sample_root)
            path_error = error
        record = {
            "id": sample["id"],
            "group_id": sample["group_id"],
            "role": sample["role"],
            "path": str(relative_path),
            "format": sample["expected_extension"].lstrip(".").upper(),
            "bytes": None,
            "before": None,
            "after": None,
            "source_unchanged": False,
            "parse_status": "FAILED",
            "parser_version": None,
            "counts": {
                "container_count": 0,
                "text_block_count": 0,
                "table_block_count": 0,
                "image_block_count": 0,
                "attachment_block_count": 0,
                "cell_count": 0,
            },
            "parse_warnings": [],
            "parse_seconds": 0.0,
            "rule_seconds": 0.0,
            "peak_rss_mib": 0.0,
            "error_stage": None,
            "error_code": None,
            "error_message": None,
        }
        task_id = uuid5(NAMESPACE_URL, f"a11-acceptance:{sample['id']}")
        try:
            if path_error is not None:
                raise path_error
            if not source_path.is_file():
                raise FileNotFoundError(str(relative_path))
            if source_path.suffix.lower() != sample["expected_extension"]:
                raise ValueError("source extension does not match the frozen manifest")
            record["before"] = _fingerprint_payload(source_path)
            record["bytes"] = record["before"]["size_bytes"]
            staged = stager.stage(
                source_path,
                task_id,
                SourceFileCreate(role=FileRole.PRIMARY_REPORT, original_name=source_path.name),
            )
            parser = parsers.get(staged.detected_format)
            if parser is None:
                raise RuntimeError(f"no acceptance parser for {staged.detected_format}")
            started = time.perf_counter()
            sampler = PeakRssSampler()
            try:
                with sampler:
                    document = parser.parse(staged)
            finally:
                record["parse_seconds"] = round(time.perf_counter() - started, 6)
                record["peak_rss_mib"] = sampler.peak_mib
            record["parse_status"] = "SUCCESS"
            record["parser_version"] = document.parser_version
            record["counts"] = _document_counts(document)
            record["parse_warnings"] = [item.model_dump(mode="json") for item in document.parse_warnings]
            parsed[sample["id"]] = (staged, document)
        except FileNotFoundError as error:
            record["error_stage"] = "SOURCE"
            record["error_code"], record["error_message"] = _stable_error(error, "SOURCE_NOT_FOUND")
        except SamplePathError as error:
            record["error_stage"] = "SOURCE"
            record["error_code"], record["error_message"] = "INVALID_SAMPLE_PATH", str(error)[:1000]
        except Exception as error:
            record["error_stage"] = "PARSING"
            record["error_code"], record["error_message"] = _stable_error(error, "PARSER_FAILURE")
        finally:
            try:
                cleaner.clean_task(task_id)
            except Exception as cleanup_error:
                record["parse_warnings"].append(
                    {
                        "code": "ACCEPTANCE_CLEANUP_FAILURE",
                        "message": str(cleanup_error)[:1000],
                        "structural_address": None,
                    }
                )
        records.append(record)

    # Independent post-run source fingerprint pass. No parser runs after this point.
    by_id = {item["id"]: item for item in records}
    for sample in manifest["samples"]:
        record = by_id[sample["id"]]
        try:
            source_path = resolve_sample_path(sample_root, sample.get("relative_path"))
        except SamplePathError:
            source_path = None
        if source_path is not None and source_path.is_file():
            record["after"] = _fingerprint_payload(source_path)
        record["source_unchanged"] = record["before"] is not None and record["before"] == record["after"]

    try:
        work_root.rmdir()
    except OSError:
        pass
    return records, parsed


def _evaluate_groups(manifest: dict, file_records: list[dict], parsed: dict[str, tuple]) -> list[dict]:
    engine = A11Engine()
    file_by_id = {item["id"]: item for item in file_records}
    groups: list[dict] = []
    for group_id in sorted({item["group_id"] for item in manifest["samples"]}):
        candidates = [item for item in manifest["samples"] if item["group_id"] == group_id]
        candidates.sort(key=lambda item: item["role"] != "TASK_PRIMARY")
        selected = next((item for item in candidates if item["id"] in parsed), None)
        primary = next(item for item in candidates if item["role"] == "TASK_PRIMARY")
        group = {
            "group_id": group_id,
            "primary_sample_id": primary["id"],
            "selected_sample_id": selected["id"] if selected else None,
            "fallback_used": bool(selected and selected["role"] == "COMPATIBILITY_ALTERNATE"),
            "rule_status": "FAILED",
            "rule_seconds": 0.0,
            "peak_rss_mib": 0.0,
            "error_code": None,
            "error_message": None,
            "rule_results": [],
        }
        if selected is None:
            group["error_code"] = "NO_PARSEABLE_GROUP_SOURCE"
            group["error_message"] = "neither the task primary nor a compatibility alternate parsed successfully"
            groups.append(group)
            continue
        staged, document = parsed[selected["id"]]
        try:
            source = ReviewSource(source_file=staged, document=document)
            source_tuple = (source,)
            review_input = ReviewInput(
                task_id=staged.task_id,
                active_revision_no=0,
                sources=source_tuple,
                evaluated_at=datetime.now(timezone.utc),
                query=NormalizedDocumentQuery(source_tuple),
            )
            started = time.perf_counter()
            with PeakRssSampler() as sampler:
                results = engine.evaluate(review_input)
            elapsed = round(time.perf_counter() - started, 6)
            group["rule_seconds"] = elapsed
            group["peak_rss_mib"] = sampler.peak_mib
            group["rule_status"] = "SUCCESS"
            group["rule_results"] = [
                {
                    "rule_id": item.rule_id,
                    "status": item.initial_status.value,
                    "basis_code": item.basis_code,
                    "basis_text": item.basis_text,
                    "evidence_locator_count": len(item.evidence_locators),
                    "missing_materials": list(item.missing_materials),
                    "unresolved_semantics": list(item.unresolved_semantics),
                }
                for item in results
            ]
            file_by_id[selected["id"]]["rule_seconds"] = elapsed
            file_by_id[selected["id"]]["peak_rss_mib"] = max(
                file_by_id[selected["id"]]["peak_rss_mib"], sampler.peak_mib
            )
        except Exception as error:
            group["error_code"], group["error_message"] = _stable_error(error, "RULE_FAILURE")
        groups.append(group)
    return groups


def _gate(gate_id: str, title: str, passed: bool, evidence: str) -> dict:
    return {
        "id": gate_id,
        "title": title,
        "status": GATE_STATUS_GO if passed else GATE_STATUS_NO_GO,
        "evidence": evidence,
    }


def _abstained_gate(gate_id: str, title: str, evidence: str) -> dict:
    """A gate this run cannot decide must abstain rather than claim a verdict."""
    return {
        "id": gate_id,
        "title": title,
        "status": GATE_STATUS_NOT_RUN,
        "evidence": evidence,
    }


def _parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        stamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def _load_gate_evidence(repository_root: Path) -> tuple[dict | None, str]:
    """Load supplementary lifecycle/UI evidence. Never echo an absolute path."""
    override = os.environ.get(GATE_EVIDENCE_ENV)
    path = (
        Path(override.strip())
        if override and override.strip()
        else repository_root / GATE_EVIDENCE_RELATIVE_PATH
    )
    if not path.is_file():
        return None, "supplementary gate evidence missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, "supplementary gate evidence unreadable"
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != GATE_EVIDENCE_SCHEMA_VERSION
    ):
        return None, "supplementary gate evidence has an unsupported schema"
    return payload, "supplementary gate evidence accepted"


def _evidence_is_fresh(recorded_at: object, reference: datetime) -> bool:
    stamp = _parse_utc(recorded_at)
    if stamp is None:
        return False
    age = reference - stamp
    # Tolerate a day of future skew; anything older than the window is stale.
    return timedelta(days=-1) <= age <= timedelta(days=GATE_EVIDENCE_MAX_AGE_DAYS)


def _lifecycle_gate(evidence: dict | None, note: str, reference: datetime) -> dict:
    """G6: the task state machine, attested by a dated backend-suite result."""
    if evidence is None:
        return _abstained_gate("G6", "Lifecycle", note)
    section = evidence.get("lifecycle")
    if not isinstance(section, dict):
        return _abstained_gate("G6", "Lifecycle", f"lifecycle section absent; {note}")
    passed = section.get("passed")
    failed = section.get("failed")
    skipped = section.get("skipped")
    recorded_at = section.get("recorded_at")
    decided = (
        isinstance(passed, int)
        and not isinstance(passed, bool)
        and passed >= MIN_LIFECYCLE_SUITE_PASSED
        and failed == 0
        and _evidence_is_fresh(recorded_at, reference)
    )
    return _gate(
        "G6",
        "Lifecycle",
        decided,
        f"backend suite passed={passed} failed={failed} skipped={skipped} "
        f"recorded_at={recorded_at}; {note}",
    )


def _ui_gate(evidence: dict | None, note: str, reference: datetime) -> dict:
    """G8: a real browser flow, attested explicitly rather than inferred."""
    if evidence is None:
        return _abstained_gate("G8", "UI", note)
    section = evidence.get("ui")
    if not isinstance(section, dict):
        return _abstained_gate("G8", "UI", f"ui section absent; {note}")
    viewports = section.get("viewports")
    observed = (
        {item for item in viewports if isinstance(item, str)}
        if isinstance(viewports, list)
        else set()
    )
    missing = sorted(set(REQUIRED_UI_VIEWPORTS) - observed)
    decided = (
        section.get("browser_verified") is True
        and not missing
        and _evidence_is_fresh(section.get("recorded_at"), reference)
    )
    return _gate(
        "G8",
        "UI",
        decided,
        f"browser_verified={section.get('browser_verified')} "
        f"recorded_at={section.get('recorded_at')} "
        f"missing viewports={missing or 'none'}; {note}",
    )


def _build_gates(
    files: list[dict],
    groups: list[dict],
    repository_root: Path,
    completed_at: str | None = None,
) -> list[dict]:
    reference = _parse_utc(completed_at) or datetime.now(timezone.utc)
    source_ok = len(files) == 17 and all(item["source_unchanged"] for item in files)
    readable = len(files) == 17 and all(item["parse_status"] == "SUCCESS" for item in files)
    structural = readable and all(
        item["counts"]["container_count"] > 0
        and sum(item["counts"][key] for key in ("text_block_count", "table_block_count", "image_block_count", "attachment_block_count")) > 0
        for item in files
    )
    rules_ok = len(groups) == 15 and all(
        group["rule_status"] == "SUCCESS"
        and len(group["rule_results"]) == 21
        and len({item["rule_id"] for item in group["rule_results"]}) == 21
        and all(item["rule_id"] != "TR-05" for item in group["rule_results"])
        for group in groups
    )
    traceability = rules_ok and all(
        (item["status"] != "NON_COMPLIANT" or item["evidence_locator_count"] > 0 or item["missing_materials"])
        and (item["status"] != "NEEDS_REVIEW" or item["unresolved_semantics"])
        for group in groups
        for item in group["rule_results"]
    )
    performance = all(
        item["parse_seconds"] + item["rule_seconds"] <= MAX_GATE_SECONDS for item in files
    )
    evidence, note = _load_gate_evidence(repository_root)
    return [
        _gate("G1", "Source protection", source_ok, f"{sum(item['source_unchanged'] for item in files)}/17 unchanged fingerprints"),
        _gate("G2", "Readability", readable, f"{sum(item['parse_status'] == 'SUCCESS' for item in files)}/17 parsed successfully"),
        _gate("G3", "Structural completeness", structural, "all 17 normalized documents contain inventoried structure" if structural else "one or more inputs lack a successful normalized structure"),
        _gate("G4", "Rule completeness", rules_ok, f"{sum(len(group['rule_results']) == 21 for group in groups)}/15 groups have 21 active results"),
        _gate("G5", "Traceability", traceability, "every hard failure has evidence/missing material and every pending item has an unresolved reason" if traceability else "traceability invariant failed"),
        _lifecycle_gate(evidence, note, reference),
        _gate("G7", "Performance", performance, f"all measured file parse + selected rule durations are <= {MAX_GATE_SECONDS} seconds"),
        _ui_gate(evidence, note, reference),
    ]


def _markdown(result: dict) -> str:
    lines = [
        "# A11 frozen-sample results",
        "",
        f"Run: `{result['run_id']}`  ",
        f"Overall release decision: **{result['overall_release_decision']}**  ",
        f"Files: {len(result['files'])}; business groups: {len(result['report_groups'])}  ",
        f"Word automation policy: `{result['word_automation_policy']}`",
        "",
        "## File matrix",
        "",
        "| ID | Group | Role | Format | Parse | Containers | Text | Tables | Images | Seconds | Peak RSS MiB | Unchanged | Error |",
        "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for item in result["files"]:
        counts = item["counts"]
        error = "" if item["error_code"] is None else f"{item['error_stage']}/{item['error_code']}"
        lines.append(
            f"| {item['id']} | {item['group_id']} | {item['role']} | {item['format']} | {item['parse_status']} | "
            f"{counts['container_count']} | {counts['text_block_count']} | {counts['table_block_count']} | "
            f"{counts['image_block_count']} | {item['parse_seconds']:.3f} | {item['peak_rss_mib']:.3f} | "
            f"{'YES' if item['source_unchanged'] else 'NO'} | {error} |"
        )
    lines.extend(["", "## Business groups", "", "| Group | Primary | Selected | Fallback | Rule status | Results | Seconds |", "|---|---|---|---|---|---:|---:|"])
    for group in result["report_groups"]:
        lines.append(
            f"| {group['group_id']} | {group['primary_sample_id']} | {group['selected_sample_id'] or '—'} | "
            f"{'YES' if group['fallback_used'] else 'NO'} | {group['rule_status']} | {len(group['rule_results'])} | {group['rule_seconds']:.3f} |"
        )
    lines.extend(["", "## Gates", "", "| Gate | Decision | Evidence |", "|---|---|---|"])
    for gate in result["gates"]:
        lines.append(f"| {gate['id']} {gate['title']} | {gate['status']} | {gate['evidence']} |")
    lines.extend([
        "",
        "## Boundaries",
        "",
        "- Historical A10/A11 values were not used as an accuracy gold standard.",
        "- Real LLM, OCR, DOCX/XLSX real-sample compatibility, production database, authentication and formal XLS writeback remain unverified.",
        "- A compatibility alternate may supply business-rule evidence for a paired DOC/PDF group, but it never converts a failed DOC parser input into a G2 pass.",
    ])
    return "\n".join(lines) + "\n"


def _release_gates_markdown(result: dict) -> str:
    lines = [
        "# A11 local vertical-slice release gates",
        "",
        f"Overall: **{result['overall_release_decision']}**",
        "",
        "| Gate | Decision | Evidence |",
        "|---|---|---|",
    ]
    for gate in result["gates"]:
        lines.append(f"| {gate['id']} {gate['title']} | **{gate['status']}** | {gate['evidence']} |")
    lines.extend([
        "",
        "Machine-readable evidence: [sample-results.json](sample-results.json)  ",
        "Human-readable matrix: [sample-results.md](sample-results.md)  ",
        "Supplementary lifecycle/UI evidence: [gates.json](../gate-evidence/gates.json)  ",
        "Run record: [verification.md](verification.md)",
        "",
        "## Unverified or deferred",
        "",
        "G1-G5 and G7 are computed from this run. G6 and G8 are read from "
        "`docs/evidence/gate-evidence/gates.json` and report NOT_RUN when that "
        "evidence is absent, stale or incomplete -- they are never inferred from prose.",
        "",
        "Real LLM calls, OCR, DOCX/XLSX real-sample compatibility, production database selection, authentication/authorization and formal A11 XLS writeback are not release-proven. Genuine Microsoft Word remains required for the acceptance-grade DOC gate; a Word-compatible host such as WPS is a development channel only, and the policy that produced this run is recorded in `sample-results.json`.",
    ])
    return "\n".join(lines) + "\n"


def run(
    manifest_path: Path,
    output_dir: Path,
    *,
    sample_root: Path,
    word_policy: str | None = None,
) -> dict:
    repository_root = Path(__file__).resolve().parents[4]
    manifest = _load_manifest(manifest_path, sample_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = _utc_now()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    policy = word_policy or get_settings().word_automation_policy
    files, parsed = _parse_samples(
        manifest, output_dir, sample_root=sample_root, word_policy=policy
    )
    groups = _evaluate_groups(manifest, files, parsed)
    completed_at = _utc_now()
    gates = _build_gates(files, groups, repository_root, completed_at)
    result = {
        "schema_version": "1.1",
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": completed_at,
        # Record caller-supplied values verbatim: committed evidence must not
        # carry machine-specific absolute paths.
        "manifest": str(manifest_path),
        "sample_root": str(sample_root),
        # A Word-compatible converter is not acceptance-grade, so the evidence
        # must state which policy produced these DOC results.
        "word_automation_policy": policy,
        "files": files,
        "report_groups": groups,
        "gates": gates,
        "overall_release_decision": (
            GATE_STATUS_GO
            if all(item["status"] == GATE_STATUS_GO for item in gates)
            else GATE_STATUS_NO_GO
        ),
    }
    (output_dir / "sample-results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "sample-results.md").write_text(_markdown(result), encoding="utf-8")
    (output_dir / "release-gates.md").write_text(_release_gates_markdown(result), encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--sample-root",
        type=Path,
        default=None,
        help=f"root of the frozen sample tree (defaults to {SAMPLE_ROOT_ENV})",
    )
    args = parser.parse_args(argv)
    root = args.sample_root
    if root is None:
        root = os.environ.get(SAMPLE_ROOT_ENV)
    if root is None or not str(root).strip():
        parser.error(
            f"--sample-root is required, or set {SAMPLE_ROOT_ENV} to the sample tree root"
        )
    result = run(args.manifest, args.output, sample_root=Path(root))
    print(
        json.dumps(
            {
                "run_id": result["run_id"],
                "decision": result["overall_release_decision"],
                "word_automation_policy": result["word_automation_policy"],
                "gates": result["gates"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if result["overall_release_decision"] == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
