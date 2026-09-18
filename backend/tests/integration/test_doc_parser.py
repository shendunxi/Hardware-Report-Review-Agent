"""Integration coverage for isolated Word conversion and DOC normalization."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pymupdf
import pytest

from hw_review.domain.enums import FileRole
from hw_review.domain.models import StagedFile
from hw_review.parsers.doc import DocParseError, DocParser
from hw_review.parsers.pdf import PdfParser
from hw_review.parsers.word_worker import (
    ChildConversionFailure,
    ConversionArtifacts,
    WordWorker,
    registered_word_server,
    run_child_conversion,
)
from hw_review.domain.models import SourceFileCreate
from hw_review.services.cleanup import WorkspaceCleaner
from hw_review.services.staging import FileStager, fingerprint


S06 = Path(
    r"D:\Document\AI创新应用大赛\硬件测试报告审核智能体\硬件测试报告及检查表"
    r"\TCY30\PP\TCY30 (903442) PP 可靠性测试报告_20260609.doc"
)
S14 = Path(
    r"D:\Document\AI创新应用大赛\硬件测试报告审核智能体\硬件测试报告及检查表"
    r"\TFY03\PP\TFY03 (903047) PP 可靠性测试报告_20240920.doc"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _png_bytes() -> bytes:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 3, 3), False)
    pixmap.clear_with(0x336699)
    return pixmap.tobytes("png")


def _task_staged(tmp_path: Path, *, detected_format: str = "DOC") -> StagedFile:
    task_id = uuid4()
    input_dir = tmp_path / str(task_id) / "input"
    input_dir.mkdir(parents=True)
    path = input_dir / f"{uuid4()}.{detected_format.lower()}"
    path.write_bytes(bytes.fromhex("D0CF11E0A1B11AE1") + b"fake-doc")
    return StagedFile(
        id=uuid4(),
        task_id=task_id,
        role=FileRole.PRIMARY_REPORT,
        original_name=f"source.{detected_format.lower()}",
        detected_format=detected_format,
        path=path,
        size_bytes=path.stat().st_size,
        sha256=_sha(path),
        source_mtime_ns=path.stat().st_mtime_ns,
    )


def _write_artifacts(output_dir: Path, staged: StagedFile) -> ConversionArtifacts:
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf = output_dir / "visual.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "visual text")
    document.save(pdf)
    document.close()
    html = output_dir / "filtered.html"
    html.write_text("<html><body>filtered</body></html>", encoding="utf-8")
    structure = output_dir / "structure.json"
    structure.write_text(
        json.dumps(
            {
                "paragraphs": [
                    {"index": 1, "page": 1, "text": "Heading"},
                    {"index": 2, "page": 1, "text": "Body"},
                ],
                "tables": [
                    {
                        "index": 1,
                        "page": 1,
                        "cells": [
                            {"row": 1, "column": 1, "text": "A"},
                            {"row": 1, "column": 2, "text": "B"},
                        ],
                    }
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return ConversionArtifacts(
        attempt_id=UUID(output_dir.name),
        source_path=staged.path.resolve(),
        source_sha256=staged.sha256,
        source_size_bytes=staged.size_bytes,
        pdf_path=pdf.resolve(),
        pdf_size_bytes=pdf.stat().st_size,
        pdf_sha256=_sha(pdf),
        html_path=html.resolve(),
        html_size_bytes=html.stat().st_size,
        html_sha256=_sha(html),
        structured_json_path=structure.resolve(),
        structured_json_size_bytes=structure.stat().st_size,
        structured_json_sha256=_sha(structure),
        word_version="16.0-test",
        duration_seconds=0.25,
        peak_memory_bytes=123456,
        diagnostics=("fake-worker",),
    )


def _future_artifact_payload(
    artifacts: ConversionArtifacts, attempt_id, **updates
) -> dict:
    payload = artifacts.model_dump(mode="json")
    payload.update(
        {
            "attempt_id": str(attempt_id),
            "pdf_size_bytes": artifacts.pdf_path.stat().st_size,
            "html_size_bytes": artifacts.html_path.stat().st_size,
            "structured_json_size_bytes": artifacts.structured_json_path.stat().st_size,
        }
    )
    payload.update(updates)
    return payload


class _FakeWorker:
    def __init__(self, artifacts_factory=_write_artifacts, error: Exception | None = None):
        self.artifacts_factory = artifacts_factory
        self.error = error
        self.calls = []
        self._artifacts = None
        self.attempt_id = uuid4()

    def convert(self, input_path: Path, output_dir: Path, timeout_seconds: int):
        self.calls.append((input_path, output_dir, timeout_seconds))
        if self.error:
            raise self.error
        staged = self.staged
        if self._artifacts is None:
            self._artifacts = self.artifacts_factory(
                output_dir / str(self.attempt_id), staged
            )
        return self._artifacts


def test_doc_parser_normalizes_structure_and_keeps_conversion_provenance(tmp_path: Path) -> None:
    staged = _task_staged(tmp_path)
    worker = _FakeWorker()
    worker.staged = staged
    parser = DocParser(worker=worker, timeout_seconds=37)

    first = parser.parse(staged)
    second = parser.parse(staged)

    assert worker.calls[0][0] == staged.path
    assert worker.calls[0][2] == 37
    assert first.source_file_id == staged.id
    assert first.format == "DOC"
    assert first.conversion_provenance is not None
    assert first.conversion_provenance.source_sha256 == staged.sha256
    assert first.conversion_provenance.pdf_sha256 == _sha(worker._artifacts.pdf_path)
    blocks = first.containers[0].blocks
    assert [block.structural_address for block in blocks[:3]] == [
        "page:1/paragraph:1",
        "page:1/paragraph:2",
        "page:1/table:1",
    ]
    assert [cell.structural_address for cell in blocks[2].cells] == [
        "page:1/table:1/cell:A1",
        "page:1/table:1/cell:B1",
    ]
    assert first.id == second.id
    assert first.text_digest == second.text_digest


def test_doc_pdf_reused_image_is_inventoried_once_per_visual_occurrence(
    tmp_path: Path,
) -> None:
    staged = _task_staged(tmp_path)

    def artifacts(output_dir: Path, source: StagedFile) -> ConversionArtifacts:
        value = _write_artifacts(output_dir, source)
        value.pdf_path.unlink()
        converted = pymupdf.open()
        page = converted.new_page()
        xref = page.insert_image(
            pymupdf.Rect(10, 10, 30, 30), stream=_png_bytes()
        )
        page.insert_image(pymupdf.Rect(50, 50, 80, 80), xref=xref)
        converted.save(value.pdf_path)
        converted.close()
        return value.model_copy(
            update={
                "pdf_size_bytes": value.pdf_path.stat().st_size,
                "pdf_sha256": _sha(value.pdf_path),
            }
        )

    worker = _FakeWorker(artifacts_factory=artifacts)
    worker.staged = staged
    parser = DocParser(worker=worker)

    first = parser.parse(staged)
    second = parser.parse(staged)
    images = [
        block for block in first.containers[0].blocks if block.kind == "image"
    ]

    assert len(images) == 2
    assert [block.structural_address for block in images] == [
        "page:1/image:1",
        "page:1/image:2",
    ]
    assert [block.bbox for block in images] == [
        (10.0, 10.0, 30.0, 30.0),
        (50.0, 50.0, 80.0, 80.0),
    ]
    assert images[0].content_hash == images[1].content_hash
    assert first.containers == second.containers


@pytest.mark.parametrize("detected_format", ["DOC", "DOCX"])
def test_doc_parser_contract_accepts_doc_and_docx(tmp_path: Path, detected_format: str) -> None:
    staged = _task_staged(tmp_path, detected_format=detected_format)
    worker = _FakeWorker()
    worker.staged = staged

    parsed = DocParser(worker=worker, format=detected_format).parse(staged)

    assert parsed.format == detected_format


def test_doc_parser_maps_worker_timeout_and_cleans_incomplete_outputs(tmp_path: Path) -> None:
    staged = _task_staged(tmp_path)
    worker = _FakeWorker(error=TimeoutError("worker exceeded deadline"))
    worker.staged = staged

    with pytest.raises(DocParseError) as error:
        DocParser(worker=worker).parse(staged)

    assert error.value.code == "DOC_CONVERSION_TIMEOUT"
    assert not (staged.path.parents[1] / "conversion" / str(staged.id)).exists()


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        ("wrong-format", "WRONG_FORMAT"),
        ("changed", "STAGED_FILE_CHANGED"),
        ("missing", "DOC_ARTIFACT_INVALID"),
        ("hash", "DOC_ARTIFACT_INVALID"),
        ("traversal", "DOC_ARTIFACT_INVALID"),
    ],
)
def test_doc_parser_rejects_invalid_source_or_artifacts(
    tmp_path: Path, mutate: str, expected: str
) -> None:
    staged = _task_staged(tmp_path)
    if mutate == "wrong-format":
        staged = staged.model_copy(update={"detected_format": "PDF"})
    elif mutate == "changed":
        staged.path.write_bytes(staged.path.read_bytes() + b"changed")

    def artifacts(output_dir: Path, source: StagedFile) -> ConversionArtifacts:
        value = _write_artifacts(output_dir, source)
        if mutate == "missing":
            value.structured_json_path.unlink()
        elif mutate == "hash":
            value.pdf_path.write_bytes(value.pdf_path.read_bytes() + b"tamper")
        elif mutate == "traversal":
            outside = tmp_path / "outside.pdf"
            outside.write_bytes(value.pdf_path.read_bytes())
            value = value.model_copy(update={"pdf_path": outside.resolve(), "pdf_sha256": _sha(outside)})
        return value

    worker = _FakeWorker(artifacts_factory=artifacts)
    worker.staged = staged
    with pytest.raises(DocParseError) as error:
        DocParser(worker=worker).parse(staged)
    assert error.value.code == expected


class _Collection:
    def __init__(self, values):
        self.values = values
        self.Count = len(values)

    def __iter__(self):
        return iter(self.values)

    def __call__(self, index):
        return self.values[index - 1]


class _FakeDocument:
    def __init__(self, calls: list):
        self.calls = calls
        paragraph_range = SimpleNamespace(Text="Paragraph\r", Information=lambda _code: 1)
        self.Paragraphs = _Collection([SimpleNamespace(Range=paragraph_range)])
        self.Tables = _Collection([])

    def ExportAsFixedFormat(self, **kwargs):
        self.calls.append(("export", kwargs))
        document = pymupdf.open()
        page = document.new_page()
        page.insert_text((72, 72), "Paragraph")
        document.save(kwargs["OutputFileName"])
        document.close()

    def SaveAs2(self, **kwargs):
        self.calls.append(("save-as", kwargs))
        Path(kwargs["FileName"]).write_text("<html></html>", encoding="utf-8")

    def Close(self, **kwargs):
        self.calls.append(("close", kwargs))


class _FakeApplication:
    def __init__(self, calls: list, fail_open: bool = False):
        object.__setattr__(self, "calls", calls)
        object.__setattr__(self, "fail_open", fail_open)
        object.__setattr__(self, "Version", "16.0-fake")
        object.__setattr__(self, "Documents", self)

    def __setattr__(self, name, value):
        if name not in {"calls", "fail_open", "Version", "Documents"}:
            self.calls.append(("set", name, value))
        object.__setattr__(self, name, value)

    def Open(self, path, **kwargs):
        self.calls.append(("open", path, kwargs))
        if self.fail_open:
            raise RuntimeError("injected open failure")
        return _FakeDocument(self.calls)

    def Quit(self, **kwargs):
        self.calls.append(("quit", kwargs))


class _FakeComRuntime:
    def __init__(self, fail_open: bool = False):
        self.calls: list = []
        self.application = _FakeApplication(self.calls, fail_open=fail_open)

    def initialize(self):
        self.calls.append(("com-init",))

    def dispatch_word(self):
        self.calls.append(("dispatch",))
        return self.application

    def uninitialize(self):
        self.calls.append(("com-uninit",))


@pytest.mark.parametrize("fail_open", [False, True])
def test_child_com_boundary_is_read_only_macro_disabled_and_always_quits(
    tmp_path: Path, fail_open: bool
) -> None:
    staged = _task_staged(tmp_path)
    source = staged.path
    output = staged.path.parents[1] / "conversion" / str(staged.id) / str(uuid4())
    output.mkdir(parents=True)
    runtime = _FakeComRuntime(fail_open=fail_open)

    if fail_open:
        with pytest.raises(ChildConversionFailure, match="injected open failure"):
            run_child_conversion(source, output, runtime=runtime)
    else:
        artifacts = run_child_conversion(source, output, runtime=runtime)
        assert artifacts.word_version == "16.0-fake"

    assert ("set", "Visible", False) in runtime.calls
    assert ("set", "DisplayAlerts", 0) in runtime.calls
    assert ("set", "AutomationSecurity", 3) in runtime.calls
    open_call = next(call for call in runtime.calls if call[0] == "open")
    assert open_call[2]["ReadOnly"] is True
    assert open_call[2]["AddToRecentFiles"] is False
    assert open_call[2]["UpdateLinks"] == 0
    if not fail_open:
        assert ("close", {"SaveChanges": 0}) in runtime.calls
    assert ("quit", {"SaveChanges": 0}) in runtime.calls
    assert runtime.calls[-1] == ("com-uninit",)


def test_child_restores_word_link_option_when_open_keyword_is_unavailable(
    tmp_path: Path,
) -> None:
    staged = _task_staged(tmp_path)
    source = staged.path
    output = staged.path.parents[1] / "conversion" / str(staged.id) / str(uuid4())
    output.mkdir(parents=True)
    runtime = _FakeComRuntime()
    application = runtime.application
    application.Options = SimpleNamespace(UpdateLinksAtOpen=True)
    real_open = application.Open
    attempts = []

    def open_with_old_type_library(path, **kwargs):
        attempts.append(dict(kwargs))
        if "UpdateLinks" in kwargs:
            raise TypeError("Open() got an unexpected keyword argument 'UpdateLinks'")
        assert application.Options.UpdateLinksAtOpen is False
        return real_open(path, **kwargs)

    application.Open = open_with_old_type_library

    run_child_conversion(source, output, runtime=runtime)

    assert len(attempts) == 2
    assert attempts[0]["UpdateLinks"] == 0
    assert "UpdateLinks" not in attempts[1]
    assert application.Options.UpdateLinksAtOpen is True


def test_child_failure_envelope_preserves_primary_and_all_cleanup_diagnostics(
    tmp_path: Path,
) -> None:
    staged = _task_staged(tmp_path)
    source = staged.path
    output = staged.path.parents[1] / "conversion" / str(staged.id) / str(uuid4())
    output.mkdir(parents=True)
    runtime = _FakeComRuntime()
    application = runtime.application

    class FailingOptions:
        def __init__(self):
            self.value = True
            self.disabled_once = False

        @property
        def UpdateLinksAtOpen(self):
            return self.value

        @UpdateLinksAtOpen.setter
        def UpdateLinksAtOpen(self, value):
            if value is False:
                self.disabled_once = True
                self.value = value
                return
            if self.disabled_once:
                raise RuntimeError("injected option restore failure")
            self.value = value

    application.Options = FailingOptions()
    document = _FakeDocument(runtime.calls)

    def open_with_fallback(path, **kwargs):
        runtime.calls.append(("open", path, kwargs))
        if "UpdateLinks" in kwargs:
            raise TypeError("Open() got an unexpected keyword argument 'UpdateLinks'")
        return document

    def fail_export(**_kwargs):
        raise RuntimeError("injected primary export failure")

    def fail_close(**_kwargs):
        raise RuntimeError("injected close failure")

    def fail_quit(**_kwargs):
        raise RuntimeError("injected quit failure")

    def fail_uninitialize():
        runtime.calls.append(("com-uninit",))
        raise RuntimeError("injected uninitialize failure")

    application.Open = open_with_fallback
    document.ExportAsFixedFormat = fail_export
    document.Close = fail_close
    application.Quit = fail_quit
    runtime.uninitialize = fail_uninitialize

    with pytest.raises(ChildConversionFailure) as error:
        run_child_conversion(source, output, runtime=runtime)

    envelope = error.value.to_envelope(diagnostic_limit=512)
    assert envelope["code"] == "DOC_CONVERSION_FAILED"
    assert envelope["message"] == "RuntimeError: injected primary export failure"
    combined = "\n".join(envelope["diagnostics"])
    assert "close failure" in combined
    assert "option restore failure" in combined
    assert "quit failure" in combined
    assert "uninitialize failure" in combined
    assert len(combined) <= 512


class _FakeProcess:
    def __init__(
        self,
        *,
        stdout: str,
        returncode: int = 0,
        timeout: bool = False,
        remain_hung_after_kill: bool = False,
    ):
        self.stdout_value = stdout
        self.stderr_value = "diagnostic-" * 1000
        self.returncode = returncode
        self.timeout = timeout
        self.pid = 4242
        self.communicate_calls = 0
        self.communicate_timeouts = []
        self.remain_hung_after_kill = remain_hung_after_kill
        self.kill_calls = 0

    def communicate(self, timeout=None):
        self.communicate_calls += 1
        self.communicate_timeouts.append(timeout)
        if self.timeout and self.communicate_calls == 1:
            raise subprocess.TimeoutExpired(["python"], timeout)
        if self.remain_hung_after_kill:
            raise subprocess.TimeoutExpired(["python"], timeout)
        return self.stdout_value, self.stderr_value

    def kill(self):
        self.kill_calls += 1


def test_parent_worker_uses_argument_list_validates_output_and_bounds_diagnostics(
    tmp_path: Path,
) -> None:
    staged = _task_staged(tmp_path)
    output = staged.path.parents[1] / "conversion" / str(staged.id)
    attempt_id = uuid4()
    generated = {}
    calls = []

    def factory(command, **kwargs):
        calls.append((command, kwargs))
        attempt = Path(command[command.index("--output-dir") + 1])
        artifacts = _write_artifacts(attempt, staged)
        generated["artifacts"] = artifacts
        return _FakeProcess(
            stdout=json.dumps(
                {"ok": True, "artifacts": artifacts.model_dump(mode="json")}
            )
        )

    accepted = WordWorker(
        process_factory=factory,
        diagnostic_limit=128,
        attempt_id_factory=lambda: attempt_id,
    ).convert(staged.path, output, 30)

    command, kwargs = calls[0]
    assert isinstance(command, list)
    assert kwargs["shell"] is False
    assert accepted.pdf_sha256 == generated["artifacts"].pdf_sha256
    assert len("\n".join(accepted.diagnostics)) <= 128


@pytest.mark.parametrize("case", ["malformed", "nonzero"])
def test_parent_worker_maps_malformed_or_nonzero_output_to_stable_failure(
    tmp_path: Path, case: str
) -> None:
    staged = _task_staged(tmp_path)
    output = staged.path.parents[1] / "conversion" / str(staged.id)
    attempt_id = uuid4()

    def factory(command, **_kwargs):
        attempt = Path(command[command.index("--output-dir") + 1])
        (attempt / "partial.tmp").write_text("partial")
        return _FakeProcess(
            stdout="not-json", returncode=1 if case == "nonzero" else 0
        )

    with pytest.raises(DocParseError) as error:
        WordWorker(
            process_factory=factory, attempt_id_factory=lambda: attempt_id
        ).convert(staged.path, output, 30)
    assert error.value.code == "DOC_CONVERSION_FAILED"
    assert not (output / str(attempt_id)).exists()


def test_parent_preserves_structured_child_failure_before_bounded_stderr(
    tmp_path: Path,
) -> None:
    staged = _task_staged(tmp_path)
    output = staged.path.parents[1] / "conversion" / str(staged.id)
    attempt_id = uuid4()
    primary = "PRIMARY-CONVERSION-SENTINEL"
    cleanup = [
        "Document.Close failed: CLEANUP-CLOSE-SENTINEL",
        "CoUninitialize failed: CLEANUP-COM-SENTINEL",
    ]
    process = _FakeProcess(
        stdout=json.dumps(
            {
                "ok": False,
                "code": "DOC_CONVERSION_FAILED",
                "message": primary,
                "diagnostics": cleanup,
            }
        ),
        returncode=1,
    )
    process.stderr_value = "x" * 4096 + "STDERR-TAIL-SENTINEL"

    def factory(command, **_kwargs):
        attempt = Path(command[command.index("--output-dir") + 1])
        (attempt / "partial.tmp").write_text("partial")
        return process

    with pytest.raises(DocParseError) as error:
        WordWorker(
            process_factory=factory,
            diagnostic_limit=160,
            attempt_id_factory=lambda: attempt_id,
        ).convert(staged.path, output, 30)

    message = str(error.value)
    assert error.value.code == "DOC_CONVERSION_FAILED"
    assert primary in message
    assert all(item in message for item in cleanup)
    assert "STDERR-TAIL-SENTINEL" in message
    assert "x" * 161 not in message
    assert not (output / str(attempt_id)).exists()


def test_parent_maps_malformed_structured_failure_envelope_stably(
    tmp_path: Path,
) -> None:
    staged = _task_staged(tmp_path)
    output = staged.path.parents[1] / "conversion" / str(staged.id)
    attempt_id = uuid4()
    process = _FakeProcess(
        stdout=json.dumps(
            {
                "ok": False,
                "code": 17,
                "message": ["not", "a", "string"],
                "diagnostics": "not-a-list",
            }
        ),
        returncode=1,
    )

    with pytest.raises(DocParseError) as error:
        WordWorker(
            process_factory=lambda *_args, **_kwargs: process,
            attempt_id_factory=lambda: attempt_id,
        ).convert(staged.path, output, 30)

    assert error.value.code == "DOC_CONVERSION_FAILED"
    assert str(error.value) == "Word worker returned invalid failure envelope"
    assert not (output / str(attempt_id)).exists()


@pytest.mark.parametrize("case", ["missing", "hash", "traversal"])
def test_parent_worker_rejects_invalid_artifacts_with_artifact_code(
    tmp_path: Path, case: str
) -> None:
    staged = _task_staged(tmp_path)
    output = staged.path.parents[1] / "conversion" / str(staged.id)
    attempt_id = uuid4()

    def factory(command, **_kwargs):
        attempt = Path(command[command.index("--output-dir") + 1])
        artifacts = _write_artifacts(attempt, staged)
        if case == "missing":
            artifacts.html_path.unlink()
        elif case == "hash":
            artifacts.pdf_path.write_bytes(artifacts.pdf_path.read_bytes() + b"tamper")
        else:
            outside = tmp_path / "outside.pdf"
            outside.write_bytes(artifacts.pdf_path.read_bytes())
            artifacts = artifacts.model_copy(
                update={"pdf_path": outside.resolve(), "pdf_sha256": _sha(outside)}
            )
        return _FakeProcess(
            stdout=json.dumps(
                {"ok": True, "artifacts": artifacts.model_dump(mode="json")}
            )
        )

    with pytest.raises(DocParseError) as error:
        WordWorker(
            process_factory=factory,
            attempt_id_factory=lambda: attempt_id,
        ).convert(
            staged.path, output, 30
        )

    assert error.value.code == "DOC_ARTIFACT_INVALID"
    assert not (output / str(attempt_id)).exists()


def test_parent_worker_timeout_kills_owned_tree_reaps_and_cleans(tmp_path: Path) -> None:
    staged = _task_staged(tmp_path)
    output = staged.path.parents[1] / "conversion" / str(staged.id)
    attempt_id = uuid4()
    process = _FakeProcess(stdout="", timeout=True)
    killed = []

    def factory(command, **_kwargs):
        attempt = Path(command[command.index("--output-dir") + 1])
        (attempt / "partial.tmp").write_text("partial")
        return process

    with pytest.raises(DocParseError) as error:
        WordWorker(
            process_factory=factory,
            process_tree_terminator=lambda pid: killed.append(pid),
            attempt_id_factory=lambda: attempt_id,
        ).convert(staged.path, output, 1)

    assert error.value.code == "DOC_CONVERSION_TIMEOUT"
    assert killed == [4242]
    assert process.communicate_calls == 2
    assert process.communicate_timeouts == [1, 5]
    assert not (output / str(attempt_id)).exists()


def test_parent_maps_process_start_oserror_and_cleans_attempt(tmp_path: Path) -> None:
    staged = _task_staged(tmp_path)
    output = staged.path.parents[1] / "conversion" / str(staged.id)
    attempt_id = uuid4()

    def cannot_start(*_args, **_kwargs):
        raise OSError("injected process start failure")

    with pytest.raises(DocParseError) as error:
        WordWorker(
            process_factory=cannot_start,
            attempt_id_factory=lambda: attempt_id,
        ).convert(staged.path, output, 30)

    assert error.value.code == "DOC_CONVERSION_FAILED"
    assert "start" in str(error.value).casefold()
    assert not (output / str(attempt_id)).exists()


def test_parent_uses_fresh_attempt_and_cannot_accept_stale_valid_outputs(
    tmp_path: Path,
) -> None:
    staged = _task_staged(tmp_path)
    base = staged.path.parents[1] / "conversion" / str(staged.id)
    stale_id = uuid4()
    stale = _write_artifacts(base / str(stale_id), staged)
    fresh_id = uuid4()
    launched = []

    def factory(command, **kwargs):
        launched.append((command, kwargs))
        attempt = Path(command[command.index("--output-dir") + 1])
        artifacts = _write_artifacts(attempt, staged)
        return _FakeProcess(
            stdout=json.dumps(
                {"ok": True, "artifacts": _future_artifact_payload(artifacts, fresh_id)}
            )
        )

    accepted = WordWorker(
        process_factory=factory,
        attempt_id_factory=lambda: fresh_id,
    ).convert(staged.path, base, 30)

    assert accepted.attempt_id == fresh_id
    assert accepted.pdf_path.parent == base / str(fresh_id)
    assert accepted.pdf_path != stale.pdf_path
    assert launched


def test_parent_refuses_reusing_existing_attempt_directory(tmp_path: Path) -> None:
    staged = _task_staged(tmp_path)
    base = staged.path.parents[1] / "conversion" / str(staged.id)
    attempt_id = uuid4()
    attempt = base / str(attempt_id)
    attempt.mkdir(parents=True)
    (attempt / "stale.txt").write_text("stale")
    launched = []

    with pytest.raises(DocParseError) as error:
        WordWorker(
            process_factory=lambda *args, **kwargs: launched.append((args, kwargs)),
            attempt_id_factory=lambda: attempt_id,
        ).convert(staged.path, base, 30)

    assert error.value.code == "DOC_ARTIFACT_INVALID"
    assert launched == []
    assert (attempt / "stale.txt").read_text() == "stale"


def test_parent_rejects_directory_symlink_component_before_process_start(
    tmp_path: Path,
) -> None:
    staged = _task_staged(tmp_path)
    task_dir = staged.path.parents[1]
    real_conversion = task_dir / "real-conversion"
    real_conversion.mkdir()
    link = task_dir / "conversion"
    try:
        link.symlink_to(real_conversion, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlink unavailable: {error}")
    base = link / str(staged.id)
    launched = []

    with pytest.raises(DocParseError) as error:
        WordWorker(
            process_factory=lambda *args, **kwargs: launched.append((args, kwargs))
        ).convert(staged.path, base, 30)

    assert error.value.code == "DOC_ARTIFACT_INVALID"
    assert launched == []


def test_child_rejects_symlink_attempt_before_com_initialization(tmp_path: Path) -> None:
    staged = _task_staged(tmp_path)
    base = staged.path.parents[1] / "conversion" / str(staged.id)
    base.mkdir(parents=True)
    real_attempt = staged.path.parents[1] / "real-attempt"
    real_attempt.mkdir()
    attempt = base / str(uuid4())
    try:
        attempt.symlink_to(real_attempt, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlink unavailable: {error}")
    runtime = _FakeComRuntime()

    with pytest.raises(DocParseError) as error:
        run_child_conversion(staged.path, attempt, runtime=runtime)

    assert error.value.code == "DOC_ARTIFACT_INVALID"
    assert runtime.calls == []


@pytest.mark.skipif(os.name != "nt", reason="Windows junction test")
def test_parent_rejects_windows_junction_component_when_available(tmp_path: Path) -> None:
    staged = _task_staged(tmp_path)
    task_dir = staged.path.parents[1]
    target = task_dir / "junction-target"
    target.mkdir()
    junction = task_dir / "conversion"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(target)],
        capture_output=True,
        text=True,
        shell=False,
    )
    if result.returncode != 0:
        pytest.skip(f"junction creation unavailable: {result.stderr or result.stdout}")
    try:
        with pytest.raises(DocParseError) as error:
            WordWorker(process_factory=lambda *_a, **_k: None).convert(
                staged.path, junction / str(staged.id), 30
            )
        assert error.value.code == "DOC_ARTIFACT_INVALID"
    finally:
        junction.rmdir()


@pytest.mark.parametrize(
    ("mutation", "field"),
    [
        ("empty", "html_size_bytes"),
        ("size-mismatch", "pdf_size_bytes"),
    ],
)
def test_parent_rejects_empty_or_size_mismatched_artifact(
    tmp_path: Path, mutation: str, field: str
) -> None:
    staged = _task_staged(tmp_path)
    base = staged.path.parents[1] / "conversion" / str(staged.id)
    attempt_id = uuid4()

    def factory(command, **_kwargs):
        attempt = Path(command[command.index("--output-dir") + 1])
        artifacts = _write_artifacts(attempt, staged)
        if mutation == "empty":
            artifacts.html_path.write_bytes(b"")
            updates = {
                "html_size_bytes": 0,
                "html_sha256": hashlib.sha256(b"").hexdigest(),
            }
        else:
            updates = {field: artifacts.pdf_path.stat().st_size + 1}
        payload = _future_artifact_payload(artifacts, attempt_id, **updates)
        return _FakeProcess(stdout=json.dumps({"ok": True, "artifacts": payload}))

    with pytest.raises(DocParseError) as error:
        WordWorker(
            process_factory=factory,
            attempt_id_factory=lambda: attempt_id,
        ).convert(staged.path, base, 30)

    assert error.value.code == "DOC_ARTIFACT_INVALID"
    assert not (base / str(attempt_id)).exists()


def test_timeout_preserves_primary_when_terminator_and_final_reap_fail(
    tmp_path: Path,
) -> None:
    staged = _task_staged(tmp_path)
    output = staged.path.parents[1] / "conversion" / str(staged.id)
    attempt_id = uuid4()
    process = _FakeProcess(
        stdout="",
        timeout=True,
        remain_hung_after_kill=True,
    )

    def failed_terminator(_pid):
        raise RuntimeError("injected terminator failure")

    with pytest.raises(DocParseError) as error:
        WordWorker(
            process_factory=lambda *a, **k: process,
            process_tree_terminator=failed_terminator,
            diagnostic_limit=160,
            attempt_id_factory=lambda: attempt_id,
        ).convert(staged.path, output, 1)

    assert error.value.code == "DOC_CONVERSION_TIMEOUT"
    assert "terminator failure" in str(error.value)
    assert "reap" in str(error.value).casefold()
    assert len(str(error.value)) <= 160
    assert process.kill_calls == 1
    assert process.communicate_timeouts == [1, 5]
    assert not (output / str(attempt_id)).exists()


def test_timeout_uses_fallback_kill_and_bounded_final_reap_after_terminator(
    tmp_path: Path,
) -> None:
    staged = _task_staged(tmp_path)
    output = staged.path.parents[1] / "conversion" / str(staged.id)
    attempt_id = uuid4()
    process = _FakeProcess(
        stdout="",
        timeout=True,
        remain_hung_after_kill=True,
    )
    terminated = []

    with pytest.raises(DocParseError) as error:
        WordWorker(
            process_factory=lambda *a, **k: process,
            process_tree_terminator=lambda pid: terminated.append(pid),
            attempt_id_factory=lambda: attempt_id,
        ).convert(staged.path, output, 1)

    assert error.value.code == "DOC_CONVERSION_TIMEOUT"
    assert terminated == [process.pid]
    assert process.kill_calls == 1
    assert process.communicate_timeouts == [1, 5, 5]
    assert "final reap timed out" in str(error.value)
    assert not (output / str(attempt_id)).exists()


def test_default_parent_worker_refuses_non_microsoft_word_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged = _task_staged(tmp_path)
    output = staged.path.parents[1] / "conversion" / str(staged.id)
    worker = WordWorker()
    launched = []
    worker._process_factory = lambda *args, **kwargs: launched.append((args, kwargs))
    monkeypatch.setattr(
        "hw_review.parsers.word_worker.registered_word_server",
        lambda: r"C:\Program Files (x86)\Kingsoft\WPS Office\office6\wps.exe /Automation",
    )

    with pytest.raises(DocParseError) as error:
        worker.convert(staged.path, output, 30)

    assert error.value.code == "DOC_CONVERSION_FAILED"
    assert "Microsoft Word" in str(error.value)
    assert launched == []


@pytest.mark.parametrize("failure_point", ["parser", "worker", "fingerprint", "assertion"])
def test_task5_acceptance_cleanup_cannot_be_bypassed(
    tmp_path: Path, failure_point: str
) -> None:
    source = tmp_path / "source.pdf"
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "synthetic")
    pdf.save(source)
    pdf.close()
    work_root = tmp_path / "work"
    task_id = uuid4()
    immutable_source = fingerprint(source)
    fingerprint_calls = 0

    def checked_fingerprint(path: Path):
        nonlocal fingerprint_calls
        fingerprint_calls += 1
        if failure_point == "fingerprint" and fingerprint_calls == 2:
            raise RuntimeError("injected fingerprint failure")
        return fingerprint(path)

    class FailingParser:
        def parse(self, staged):
            if failure_point == "worker":
                partial = staged.path.parents[1] / "conversion" / "partial"
                partial.mkdir(parents=True)
                (partial / "incomplete.tmp").write_text("partial")
                raise RuntimeError("injected worker failure")
            raise RuntimeError("injected parser failure")

    parser = FailingParser() if failure_point in {"parser", "worker"} else PdfParser()
    before = None
    try:
        with pytest.raises((RuntimeError, AssertionError)):
            try:
                before = checked_fingerprint(source)
                staged = FileStager(work_root).stage(
                    source,
                    task_id,
                    SourceFileCreate(role=FileRole.PRIMARY_REPORT, original_name=source.name),
                )
                document = parser.parse(staged)
                checked_fingerprint(source)
                if failure_point == "assertion":
                    raise AssertionError("injected acceptance assertion")
                raise AssertionError("unreachable")
            finally:
                WorkspaceCleaner(work_root).clean_task(task_id)
    finally:
        assert before == immutable_source
        assert fingerprint(source) == immutable_source
        assert not (work_root / str(task_id)).exists()


@pytest.mark.parametrize(("sample_id", "source"), [("S-06", S06), ("S-14", S14)])
def test_real_doc_is_staged_read_only_measured_and_cleaned(sample_id: str, source: Path) -> None:
    if not source.is_file():
        pytest.skip(f"frozen {sample_id} is unavailable")
    repository_root = Path(__file__).resolve().parents[3]
    work_root = repository_root / ".task-work" / f"task-5-{sample_id.lower()}"
    work_root.mkdir(parents=True, exist_ok=True)
    task_id = uuid4()
    before = fingerprint(source)
    server = registered_word_server()
    if not server or "winword.exe" not in server.casefold():
        after = fingerprint(source)
        assert after == before
        print(
            "REAL_DOC_NO_GO",
            {
                "sample_id": sample_id,
                "source_before": before,
                "source_after": after,
                "registered_word_server": server,
                "reason": "Microsoft Word COM server is unavailable",
            },
        )
        if work_root.exists() and not any(work_root.iterdir()):
            work_root.rmdir()
        pytest.skip("NO-GO: Word.Application is not registered to Microsoft WINWORD.EXE")
    try:
        staged = FileStager(work_root).stage(
            source,
            task_id,
            SourceFileCreate(role=FileRole.PRIMARY_REPORT, original_name=source.name),
        )
        assert staged.path != source
        started = time.perf_counter()
        document = DocParser(timeout_seconds=20 * 60).parse(staged)
        duration = time.perf_counter() - started
        after = fingerprint(source)
        assert after == before
        assert duration < 20 * 60
        assert document.container_count >= 1
        text_count = sum(block.kind == "text" for page in document.containers for block in page.blocks)
        table_count = sum(block.kind == "table" for page in document.containers for block in page.blocks)
        image_count = sum(block.kind == "image" for page in document.containers for block in page.blocks)
        assert text_count or any(warning.code == "IMAGE_ONLY_PAGE" for warning in document.parse_warnings)
        assert document.conversion_provenance is not None
        print(
            "REAL_DOC_METRICS",
            {
                "sample_id": sample_id,
                "source_before": before,
                "source_after": after,
                "bytes": staged.size_bytes,
                "page_count": document.container_count,
                "text_count": text_count,
                "table_count": table_count,
                "image_count": image_count,
                "duration_seconds": duration,
                "peak_memory_bytes": document.conversion_provenance.peak_memory_bytes,
                "word_version": document.conversion_provenance.word_version,
            },
        )
    finally:
        assert fingerprint(source) == before
        WorkspaceCleaner(work_root).clean_task(task_id)
        assert not (work_root / str(task_id)).exists()
        if work_root.exists() and not any(work_root.iterdir()):
            work_root.rmdir()
