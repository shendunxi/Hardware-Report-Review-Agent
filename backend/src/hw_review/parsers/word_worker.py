"""Short-lived Microsoft Word conversion worker and parent process client.

CLI contract::

    python -m hw_review.parsers.word_worker --input PATH --output-dir PATH

Exactly one JSON object is written to stdout. Success uses
``{"ok": true, "artifacts": {...}}``; failure uses
``{"ok": false, "code": "DOC_CONVERSION_FAILED", "message": "..."}``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Literal
from uuid import UUID, uuid4

import psutil
from pydantic import Field, ValidationError

from hw_review.domain.models import DomainModel
from hw_review.parsers.base import ParserError


class DocConversionError(ParserError):
    """Stable parent-side conversion failure."""


class ChildConversionFailure(Exception):
    """Child-side failure that preserves the primary error and cleanup evidence."""

    code = "DOC_CONVERSION_FAILED"

    def __init__(self, primary_error: BaseException, diagnostics: list[str]) -> None:
        self.primary_error = primary_error
        self.primary_message = f"{type(primary_error).__name__}: {primary_error}"
        self.diagnostics = tuple(str(item) for item in diagnostics)
        super().__init__(self.primary_message)

    def to_envelope(self, *, diagnostic_limit: int = 2048) -> dict:
        remaining = max(0, diagnostic_limit)
        bounded: list[str] = []
        for diagnostic in self.diagnostics:
            separator_cost = 1 if bounded else 0
            available = remaining - separator_cost
            if available <= 0:
                break
            bounded.append(diagnostic[:available])
            remaining -= separator_cost + len(bounded[-1])
        return {
            "ok": False,
            "code": self.code,
            "message": self.primary_message[:2048],
            "diagnostics": bounded,
        }


class ChildFailureEnvelope(DomainModel):
    """Strict wire contract for a failed child conversion."""

    ok: Literal[False]
    code: Literal["DOC_CONVERSION_FAILED"]
    message: str = Field(min_length=1, max_length=2048)
    diagnostics: tuple[str, ...] = Field(default=(), max_length=64)


class ConversionArtifacts(DomainModel):
    """Immutable, hash-bound artifacts returned by one child conversion."""

    attempt_id: UUID
    source_path: Path
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_size_bytes: int = Field(ge=0)
    pdf_path: Path
    pdf_size_bytes: int = Field(gt=0)
    pdf_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    html_path: Path
    html_size_bytes: int = Field(gt=0)
    html_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    structured_json_path: Path
    structured_json_size_bytes: int = Field(gt=0)
    structured_json_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    word_version: str = Field(min_length=1)
    duration_seconds: float = Field(ge=0)
    peak_memory_bytes: int = Field(ge=0)
    diagnostics: tuple[str, ...] = ()


def registered_word_server() -> str | None:
    """Return the registered Word COM executable without starting an Office app."""

    if os.name != "nt":
        return None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Word.Application\CLSID") as key:
            clsid = str(winreg.QueryValue(key, None))
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CLASSES_ROOT,
                    rf"CLSID\{clsid}\LocalServer32",
                    0,
                    winreg.KEY_READ | view,
                ) as key:
                    return str(winreg.QueryValue(key, None)).strip()
            except OSError:
                continue
        return None
    except (OSError, ValueError):
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _raw_absolute(path: Path) -> Path:
    """Make a path absolute without resolving links or reparse points."""

    return Path(os.path.abspath(os.fspath(path)))


def _is_reparse_point(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if is_junction is not None and is_junction():
            return True
        attributes = getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0)
        return bool(attributes & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
    except OSError:
        return False


def _reject_reparse_components(path: Path) -> Path:
    """Inspect every existing raw component before any path resolution."""

    raw = _raw_absolute(path)
    current = Path(raw.anchor)
    for component in raw.parts[1:]:
        current /= component
        if current.exists() or current.is_symlink():
            if _is_reparse_point(current):
                raise DocConversionError(
                    "DOC_ARTIFACT_INVALID",
                    f"conversion path contains a reparse point: {current}",
                )
    return raw


def _validated_child_attempt(input_path: Path, output_dir: Path) -> tuple[Path, Path]:
    raw_target = _reject_reparse_components(output_dir)
    source = Path(input_path).resolve(strict=True)
    try:
        target = raw_target.resolve(strict=True)
    except OSError as error:
        raise DocConversionError(
            "DOC_ARTIFACT_INVALID", "conversion attempt directory is unavailable"
        ) from error
    task_dir = source.parent.parent.resolve()
    if (
        not target.is_dir()
        or target.parent.parent.name != "conversion"
        or target.parents[2] != task_dir
    ):
        raise DocConversionError(
            "DOC_ARTIFACT_INVALID", "child conversion attempt is outside the task directory"
        )
    try:
        UUID(target.name)
    except ValueError as error:
        raise DocConversionError(
            "DOC_ARTIFACT_INVALID", "child conversion attempt must have a UUID name"
        ) from error
    if any(target.iterdir()):
        raise DocConversionError(
            "DOC_ARTIFACT_INVALID", "child conversion attempt must be empty"
        )
    return source, target


class _RealComRuntime:
    def __init__(self):
        import pythoncom
        import win32com.client

        self._pythoncom = pythoncom
        self._client = win32com.client

    def initialize(self):
        self._pythoncom.CoInitialize()

    def dispatch_word(self):
        return self._client.DispatchEx("Word.Application")

    def uninitialize(self):
        self._pythoncom.CoUninitialize()


def _clean_word_text(value: object) -> str:
    return str(value or "").replace("\r", "\n").replace("\x07", "").strip()


def _page_number(range_object) -> int:
    try:
        return max(1, int(range_object.Information(3)))
    except Exception:
        return 1


def _extract_structure(document) -> dict:
    paragraphs = []
    for index in range(1, int(document.Paragraphs.Count) + 1):
        paragraph = document.Paragraphs(index)
        text = _clean_word_text(paragraph.Range.Text)
        if text:
            paragraphs.append({"index": index, "page": _page_number(paragraph.Range), "text": text})
    tables = []
    for table_index in range(1, int(document.Tables.Count) + 1):
        table = document.Tables(table_index)
        cells = []
        for cell_index in range(1, int(table.Range.Cells.Count) + 1):
            cell = table.Range.Cells(cell_index)
            text = _clean_word_text(cell.Range.Text)
            if text:
                cells.append(
                    {
                        "row": int(cell.RowIndex),
                        "column": int(cell.ColumnIndex),
                        "text": text,
                    }
                )
        tables.append(
            {
                "index": table_index,
                "page": _page_number(table.Range),
                "cells": cells,
            }
        )
    return {"paragraphs": paragraphs, "tables": tables}


def _peak_memory_bytes() -> int:
    info = psutil.Process(os.getpid()).memory_info()
    return int(getattr(info, "peak_wset", info.rss))


def run_child_conversion(input_path: Path, output_dir: Path, *, runtime=None) -> ConversionArtifacts:
    """Run Word automation in the current child process only."""

    started = time.perf_counter()
    source, target = _validated_child_attempt(input_path, output_dir)
    pdf_path = target / "visual.pdf"
    html_path = target / "filtered.html"
    structure_path = target / "structure.json"
    diagnostics: list[str] = []
    com_runtime = runtime or _RealComRuntime()
    application = None
    document = None
    word_version = "unknown"
    prior_update_links_at_open = None
    changed_update_links_option = False
    primary_error: BaseException | None = None
    initialized = False
    try:
        com_runtime.initialize()
        initialized = True
        application = com_runtime.dispatch_word()
        word_version = str(application.Version)
        application.Visible = False
        application.DisplayAlerts = 0
        application.AutomationSecurity = 3
        try:
            open_arguments = {
                "ConfirmConversions": False,
                "ReadOnly": True,
                "AddToRecentFiles": False,
                "Revert": False,
                "UpdateLinks": 0,
                "NoEncodingDialog": True,
                "OpenAndRepair": False,
            }
            try:
                document = application.Documents.Open(str(source), **open_arguments)
            except TypeError as error:
                if "UpdateLinks" not in str(error):
                    raise
                # Some Word type libraries do not expose UpdateLinks on
                # Documents.Open. The equivalent application-level guard is
                # applied before retrying without that unsupported keyword.
                prior_update_links_at_open = application.Options.UpdateLinksAtOpen
                application.Options.UpdateLinksAtOpen = False
                changed_update_links_option = True
                open_arguments.pop("UpdateLinks")
                document = application.Documents.Open(str(source), **open_arguments)
            structure = _extract_structure(document)
            document.ExportAsFixedFormat(
                OutputFileName=str(pdf_path),
                ExportFormat=17,
                OpenAfterExport=False,
            )
            document.SaveAs2(
                FileName=str(html_path),
                FileFormat=10,
                AddToRecentFiles=False,
            )
            structure_path.write_text(
                json.dumps(structure, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
        except BaseException as error:
            primary_error = error
        finally:
            if document is not None:
                try:
                    document.Close(SaveChanges=0)
                except Exception as error:
                    diagnostics.append(f"Document.Close failed: {type(error).__name__}: {error}")
                    if primary_error is None:
                        primary_error = error
    except BaseException as error:
        if primary_error is None:
            primary_error = error
    finally:
        if application is not None and changed_update_links_option:
            try:
                application.Options.UpdateLinksAtOpen = prior_update_links_at_open
            except Exception as error:
                diagnostics.append(
                    f"Options.UpdateLinksAtOpen restore failed: {type(error).__name__}: {error}"
                )
                if primary_error is None:
                    primary_error = error
        try:
            if application is not None:
                application.Quit(SaveChanges=0)
        except Exception as error:
            diagnostics.append(f"Application.Quit failed: {type(error).__name__}: {error}")
            if primary_error is None:
                primary_error = error
        if initialized:
            try:
                com_runtime.uninitialize()
            except BaseException as error:
                diagnostics.append(
                    f"CoUninitialize failed: {type(error).__name__}: {error}"
                )
                if primary_error is None:
                    primary_error = error
    if primary_error is not None:
        raise ChildConversionFailure(primary_error, diagnostics) from primary_error
    return ConversionArtifacts(
        attempt_id=UUID(target.name),
        source_path=source,
        source_sha256=_sha256(source),
        source_size_bytes=source.stat().st_size,
        pdf_path=pdf_path.resolve(),
        pdf_size_bytes=pdf_path.stat().st_size,
        pdf_sha256=_sha256(pdf_path),
        html_path=html_path.resolve(),
        html_size_bytes=html_path.stat().st_size,
        html_sha256=_sha256(html_path),
        structured_json_path=structure_path.resolve(),
        structured_json_size_bytes=structure_path.stat().st_size,
        structured_json_sha256=_sha256(structure_path),
        word_version=word_version,
        duration_seconds=time.perf_counter() - started,
        peak_memory_bytes=_peak_memory_bytes(),
        diagnostics=tuple(diagnostics),
    )


def _terminate_owned_tree(pid: int) -> None:
    """Terminate only descendants of the worker PID, then the worker itself."""

    try:
        parent = psutil.Process(pid)
    except psutil.Error:
        return
    processes = parent.children(recursive=True)
    for process in reversed(processes):
        try:
            process.terminate()
        except psutil.Error:
            pass
    _, alive = psutil.wait_procs(processes, timeout=3)
    for process in alive:
        try:
            process.kill()
        except psutil.Error:
            pass
    try:
        parent.terminate()
        parent.wait(timeout=3)
    except psutil.TimeoutExpired:
        parent.kill()
        parent.wait(timeout=3)
    except psutil.Error:
        pass


class WordWorker:
    """Launch, bound, validate, and reap one short-lived Word conversion child."""

    def __init__(
        self,
        *,
        python_executable: Path | str | None = None,
        process_factory: Callable = subprocess.Popen,
        process_tree_terminator: Callable[[int], None] = _terminate_owned_tree,
        diagnostic_limit: int = 4096,
        attempt_id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._python = str(python_executable or sys.executable)
        self._process_factory = process_factory
        self._require_microsoft_word = process_factory is subprocess.Popen
        self._terminate = process_tree_terminator
        self._diagnostic_limit = diagnostic_limit
        self._attempt_id_factory = attempt_id_factory

    def _bounded(self, value: str) -> str:
        return value[: self._diagnostic_limit]

    def _cleanup_with_diagnostic(self, target: Path, diagnostics: list[str]) -> None:
        try:
            self._clean_target(target)
        except Exception as error:
            diagnostics.append(
                f"output cleanup failed: {type(error).__name__}: {error}"
            )

    def _structured_failure_message(
        self,
        envelope: ChildFailureEnvelope,
        stderr: str,
        parent_diagnostics: list[str],
    ) -> str:
        remaining = self._diagnostic_limit
        cleanup_diagnostics: list[str] = []
        for diagnostic in (*envelope.diagnostics, *parent_diagnostics):
            if remaining <= 0:
                break
            bounded = diagnostic[:remaining]
            if bounded:
                cleanup_diagnostics.append(bounded)
                remaining -= len(bounded)
        stderr_context = stderr[-remaining:] if stderr and remaining > 0 else ""
        parts = [envelope.message]
        if cleanup_diagnostics:
            parts.append("cleanup diagnostics: " + " | ".join(cleanup_diagnostics))
        if stderr_context:
            parts.append("stderr: " + stderr_context)
        return "; ".join(parts)

    def convert(self, input_path: Path, output_dir: Path, timeout_seconds: int) -> ConversionArtifacts:
        source = Path(input_path).resolve(strict=True)
        raw_output_base = _reject_reparse_components(output_dir)
        output_base = raw_output_base.resolve(strict=False)
        self._validate_target(source, output_base)
        if self._require_microsoft_word:
            server = registered_word_server()
            if not server or "winword.exe" not in server.casefold():
                raise DocConversionError(
                    "DOC_CONVERSION_FAILED",
                    "Microsoft Word COM server is unavailable; "
                    f"registered Word.Application server: {server or 'none'}",
                )
        output_base.mkdir(parents=True, exist_ok=True)
        _reject_reparse_components(raw_output_base)
        if raw_output_base.resolve(strict=True) != output_base:
            raise DocConversionError(
                "DOC_ARTIFACT_INVALID", "conversion base changed during validation"
            )
        attempt_id = self._attempt_id_factory()
        if not isinstance(attempt_id, UUID):
            raise DocConversionError(
                "DOC_ARTIFACT_INVALID", "conversion attempt ID must be a UUID"
            )
        raw_target = raw_output_base / str(attempt_id)
        target = output_base / str(attempt_id)
        if target.exists() or target.is_symlink():
            raise DocConversionError(
                "DOC_ARTIFACT_INVALID", "conversion attempt directory already exists"
            )
        try:
            raw_target.mkdir(exist_ok=False)
        except OSError as error:
            raise DocConversionError(
                "DOC_ARTIFACT_INVALID", "conversion attempt directory cannot be created"
            ) from error
        _reject_reparse_components(raw_target)
        if raw_target.resolve(strict=True) != target:
            self._clean_target(raw_target)
            raise DocConversionError(
                "DOC_ARTIFACT_INVALID", "conversion attempt changed during validation"
            )
        before_hash = _sha256(source)
        before_size = source.stat().st_size
        command = [
            self._python,
            "-m",
            "hw_review.parsers.word_worker",
            "--input",
            str(source),
            "--output-dir",
            str(target),
        ]
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        environment = os.environ.copy()
        source_root = str(Path(__file__).resolve().parents[2])
        prior_python_path = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = (
            os.pathsep.join((source_root, prior_python_path))
            if prior_python_path
            else source_root
        )
        try:
            process = self._process_factory(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
                creationflags=creationflags,
                env=environment,
            )
        except OSError as error:
            diagnostics = [f"process start failed: {type(error).__name__}: {error}"]
            self._cleanup_with_diagnostic(target, diagnostics)
            raise DocConversionError(
                "DOC_CONVERSION_FAILED", self._bounded("; ".join(diagnostics))
            ) from error
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as error:
            diagnostics = ["Word conversion worker exceeded its deadline"]
            fallback_kill_required = False
            try:
                self._terminate(process.pid)
            except Exception as terminate_error:
                fallback_kill_required = True
                diagnostics.append(
                    "owned-tree terminator failed: "
                    f"{type(terminate_error).__name__}: {terminate_error}"
                )
            if fallback_kill_required:
                try:
                    process.kill()
                    diagnostics.append("fallback process.kill issued")
                except Exception as kill_error:
                    diagnostics.append(
                        f"fallback process.kill failed: {type(kill_error).__name__}: {kill_error}"
                    )
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                diagnostics.append("reap timed out after 5 seconds")
                if not fallback_kill_required:
                    try:
                        process.kill()
                        diagnostics.append("fallback process.kill issued after reap timeout")
                    except Exception as kill_error:
                        diagnostics.append(
                            "fallback process.kill failed after reap timeout: "
                            f"{type(kill_error).__name__}: {kill_error}"
                        )
                    else:
                        try:
                            process.communicate(timeout=5)
                        except subprocess.TimeoutExpired:
                            diagnostics.append("final reap timed out after 5 seconds")
                        except Exception as final_reap_error:
                            diagnostics.append(
                                "final reap failed: "
                                f"{type(final_reap_error).__name__}: {final_reap_error}"
                            )
            except Exception as reap_error:
                diagnostics.append(
                    f"final reap failed: {type(reap_error).__name__}: {reap_error}"
                )
            finally:
                self._cleanup_with_diagnostic(target, diagnostics)
            raise DocConversionError(
                "DOC_CONVERSION_TIMEOUT", self._bounded("; ".join(diagnostics))
            ) from error
        if process.returncode != 0:
            try:
                envelope = ChildFailureEnvelope.model_validate(json.loads(stdout))
            except (TypeError, ValueError, ValidationError) as error:
                cleanup_diagnostics: list[str] = []
                self._cleanup_with_diagnostic(target, cleanup_diagnostics)
                message = "Word worker returned invalid failure envelope"
                if cleanup_diagnostics:
                    message += "; " + self._bounded("; ".join(cleanup_diagnostics))
                raise DocConversionError("DOC_CONVERSION_FAILED", message) from error
            cleanup_diagnostics = []
            self._cleanup_with_diagnostic(target, cleanup_diagnostics)
            raise DocConversionError(
                envelope.code,
                self._structured_failure_message(
                    envelope, stderr or "", cleanup_diagnostics
                ),
            )
        try:
            envelope = json.loads(stdout)
            if envelope.get("ok") is not True:
                raise ValueError("worker did not report success")
        except (KeyError, TypeError, ValueError) as error:
            diagnostics = ["Word worker returned invalid output"]
            self._cleanup_with_diagnostic(target, diagnostics)
            raise DocConversionError("DOC_CONVERSION_FAILED", "Word worker returned invalid output") from error
        try:
            artifacts = ConversionArtifacts.model_validate(envelope["artifacts"])
        except (KeyError, TypeError, ValidationError) as error:
            diagnostics = ["Word worker artifact manifest is invalid"]
            self._cleanup_with_diagnostic(target, diagnostics)
            raise DocConversionError(
                "DOC_ARTIFACT_INVALID", "Word worker artifact manifest is invalid"
            ) from error
        try:
            diagnostics = (stderr or "")[-self._diagnostic_limit :]
            artifacts = artifacts.model_copy(update={"diagnostics": (diagnostics,) if diagnostics else ()})
            self._validate_artifacts(
                artifacts,
                source,
                target,
                attempt_id,
                before_hash,
                before_size,
            )
            return artifacts
        except DocConversionError:
            diagnostics = []
            self._cleanup_with_diagnostic(target, diagnostics)
            raise
        except (TypeError, ValueError, OSError) as error:
            diagnostics = ["Word worker artifact validation failed"]
            self._cleanup_with_diagnostic(target, diagnostics)
            raise DocConversionError("DOC_ARTIFACT_INVALID", "Word worker artifact validation failed") from error

    @staticmethod
    def _validate_target(source: Path, target: Path) -> None:
        if target.is_symlink():
            raise DocConversionError("DOC_ARTIFACT_INVALID", "conversion directory cannot be a symlink")
        task_dir = source.parent.parent.resolve()
        if source.parent.name != "input" or target.parent.parent.resolve() != task_dir:
            raise DocConversionError("DOC_ARTIFACT_INVALID", "conversion output must remain inside the task directory")

    @staticmethod
    def _validate_artifacts(
        artifacts, source, target, attempt_id, source_hash, source_size
    ) -> None:
        if artifacts.attempt_id != attempt_id:
            raise ValueError("conversion attempt identity mismatch")
        if artifacts.source_path.resolve() != source or artifacts.source_sha256 != source_hash or artifacts.source_size_bytes != source_size:
            raise ValueError("source identity mismatch")
        if _sha256(source) != source_hash or source.stat().st_size != source_size:
            raise ValueError("source changed during conversion")
        for path, expected_size, expected_hash in (
            (artifacts.pdf_path, artifacts.pdf_size_bytes, artifacts.pdf_sha256),
            (artifacts.html_path, artifacts.html_size_bytes, artifacts.html_sha256),
            (
                artifacts.structured_json_path,
                artifacts.structured_json_size_bytes,
                artifacts.structured_json_sha256,
            ),
        ):
            raw_candidate = _reject_reparse_components(path)
            candidate = raw_candidate.resolve(strict=True)
            if candidate.parent != target or not candidate.is_file():
                raise ValueError("artifact path escaped conversion directory")
            if candidate.stat().st_size != expected_size:
                raise ValueError("artifact size mismatch")
            if _sha256(candidate) != expected_hash:
                raise ValueError("artifact hash mismatch")

    @staticmethod
    def _clean_target(target: Path) -> None:
        if target.exists() and not _is_reparse_point(target):
            shutil.rmtree(target)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    arguments = parser.parse_args(argv)
    try:
        artifacts = run_child_conversion(Path(arguments.input), Path(arguments.output_dir))
        print(json.dumps({"ok": True, "artifacts": artifacts.model_dump(mode="json")}, ensure_ascii=False))
        return 0
    except ChildConversionFailure as error:
        print(json.dumps(error.to_envelope(), ensure_ascii=False))
        return 1
    except BaseException as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "code": "DOC_CONVERSION_FAILED",
                    "message": f"{type(error).__name__}: {error}"[:2048],
                },
                ensure_ascii=False,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(_main())
