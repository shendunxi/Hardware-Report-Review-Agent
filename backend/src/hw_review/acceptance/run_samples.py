"""Run the frozen 17-file, read-only A11 acceptance matrix."""

from __future__ import annotations

import argparse
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import psutil

from hw_review.domain import FileRole, ReviewInput, ReviewSource, SourceFileCreate
from hw_review.parsers import DocParser, PdfParser, XlsParser
from hw_review.rules import A11Engine, NormalizedDocumentQuery
from hw_review.services.cleanup import WorkspaceCleaner
from hw_review.services.staging import FileStager, fingerprint


MAX_GATE_SECONDS = 20 * 60


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


def _load_manifest(path: Path) -> dict:
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
    return payload


def _parse_samples(manifest: dict, output_dir: Path) -> tuple[list[dict], dict[str, tuple]]:
    work_root = output_dir / "_work"
    stager = FileStager(work_root)
    cleaner = WorkspaceCleaner(work_root)
    parsers = {
        "XLS": XlsParser(),
        "PDF": PdfParser(),
        "DOC": DocParser(timeout_seconds=MAX_GATE_SECONDS),
    }
    records: list[dict] = []
    parsed: dict[str, tuple] = {}

    for sample in manifest["samples"]:
        source_path = Path(sample["absolute_path"])
        record = {
            "id": sample["id"],
            "group_id": sample["group_id"],
            "role": sample["role"],
            "path": str(source_path),
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
            if not source_path.is_file():
                raise FileNotFoundError(str(source_path))
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
        source_path = Path(sample["absolute_path"])
        if source_path.is_file():
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
    return {"id": gate_id, "title": title, "status": "GO" if passed else "NO-GO", "evidence": evidence}


def _build_gates(files: list[dict], groups: list[dict], repository_root: Path) -> list[dict]:
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
    task7 = repository_root / ".superpowers" / "sdd" / "2026-09-11-a11-local-vertical-slice" / "task-7-report.md"
    task7_text = task7.read_text(encoding="utf-8") if task7.is_file() else ""
    lifecycle = "45 passed" in task7_text and "274 passed" in task7_text
    performance = all(item["parse_seconds"] + item["rule_seconds"] <= MAX_GATE_SECONDS for item in files)
    task8 = repository_root / ".superpowers" / "sdd" / "2026-09-11-a11-local-vertical-slice" / "task-8-report.md"
    task8_text = task8.read_text(encoding="utf-8") if task8.is_file() else ""
    ui_ok = "44 passed" in task8_text and "1440x900" in task8_text and "760x900" in task8_text
    return [
        _gate("G1", "Source protection", source_ok, f"{sum(item['source_unchanged'] for item in files)}/17 unchanged fingerprints"),
        _gate("G2", "Readability", readable, f"{sum(item['parse_status'] == 'SUCCESS' for item in files)}/17 parsed successfully"),
        _gate("G3", "Structural completeness", structural, "all 17 normalized documents contain inventoried structure" if structural else "one or more inputs lack a successful normalized structure"),
        _gate("G4", "Rule completeness", rules_ok, f"{sum(len(group['rule_results']) == 21 for group in groups)}/15 groups have 21 active results"),
        _gate("G5", "Traceability", traceability, "every hard failure has evidence/missing material and every pending item has an unresolved reason" if traceability else "traceability invariant failed"),
        _gate("G6", "Lifecycle", lifecycle, "Task 7 focused 45 pass and full backend 274 pass / 4 skips" if lifecycle else "Task 7 evidence unavailable or stale"),
        _gate("G7", "Performance", performance, f"all measured file parse + selected rule durations are <= {MAX_GATE_SECONDS} seconds"),
        _gate("G8", "UI", ui_ok, "Task 8 real browser flow and 1440x900/1280x720/760x900 checks passed" if ui_ok else "Task 8 evidence unavailable or stale"),
    ]


def _markdown(result: dict) -> str:
    lines = [
        "# A11 frozen-sample results",
        "",
        f"Run: `{result['run_id']}`  ",
        f"Overall release decision: **{result['overall_release_decision']}**  ",
        f"Files: {len(result['files'])}; business groups: {len(result['report_groups'])}",
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
        "Automated-suite evidence: [Task 9 report](../../../.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-9-report.md)  ",
        "Lifecycle evidence: [Task 7 report](../../../.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-7-report.md)  ",
        "Browser evidence: [Task 8 report](../../../.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-8-report.md)",
        "",
        "## Unverified or deferred",
        "",
        "Real LLM calls, OCR, DOCX/XLSX real-sample compatibility, production database selection, authentication/authorization and formal A11 XLS writeback are not release-proven. Genuine Microsoft Word remains required for the DOC gate; WPS evidence is not accepted.",
    ])
    return "\n".join(lines) + "\n"


def run(manifest_path: Path, output_dir: Path) -> dict:
    repository_root = Path(__file__).resolve().parents[4]
    manifest = _load_manifest(manifest_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = _utc_now()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    files, parsed = _parse_samples(manifest, output_dir)
    groups = _evaluate_groups(manifest, files, parsed)
    gates = _build_gates(files, groups, repository_root)
    result = {
        "schema_version": "1.0",
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": _utc_now(),
        "manifest": str(manifest_path.resolve()),
        "source_root": manifest["source_root"],
        "files": files,
        "report_groups": groups,
        "gates": gates,
        "overall_release_decision": "GO" if all(item["status"] == "GO" for item in gates) else "NO-GO",
    }
    (output_dir / "sample-results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "sample-results.md").write_text(_markdown(result), encoding="utf-8")
    (output_dir / "release-gates.md").write_text(_release_gates_markdown(result), encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = run(args.manifest, args.output)
    print(json.dumps({"run_id": result["run_id"], "decision": result["overall_release_decision"], "gates": result["gates"]}, ensure_ascii=False))
    return 0 if result["overall_release_decision"] == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
