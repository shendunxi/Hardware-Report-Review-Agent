"""Integration coverage for the read-only legacy XLS adapter."""

from __future__ import annotations

import hashlib
import io
import os
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
import xlrd
import xlwt

from hw_review.acceptance.run_samples import SAMPLE_ROOT_ENV
from hw_review.domain.enums import FileRole
from hw_review.domain.models import SourceFileCreate, StagedFile
from hw_review.parsers.xls import XlsParseError, XlsParser
from hw_review.services.cleanup import WorkspaceCleaner
from hw_review.services.staging import FileStager, fingerprint


# The frozen tree lives outside the repository and moves between machines, so
# the root is supplied exactly the way the acceptance runner supplies it.
SAMPLE_ROOT = Path(
    os.environ.get(SAMPLE_ROOT_ENV, r"D:\Document\AI创新应用大赛\硬件测试报告及检查表")
)
S01 = SAMPLE_ROOT / (
    r"HPYR2D\DS\HYR2D DS Project Hardware Test Report（DVB-C for Overseas）V1.23-0327.xls"
)


def _write_fixture(path: Path) -> None:
    workbook = xlwt.Workbook()
    first = workbook.add_sheet("Sheet 1 中文")
    first.write_merge(1, 1, 1, 2, "结论")
    first.write(2, 0, 12.5)
    first.write(3, 0, True)
    date_style = xlwt.easyxf(num_format_str="YYYY-MM-DD")
    first.write(4, 0, datetime(2026, 9, 11), date_style)
    first.write(5, 0, xlwt.Formula("A3*2"))
    workbook.add_sheet("Empty")
    workbook.save(str(path))


def _staged_for(path: Path, *, detected_format: str = "XLS") -> StagedFile:
    payload = path.read_bytes()
    return StagedFile(
        id=uuid4(),
        task_id=uuid4(),
        role=FileRole.PRIMARY_REPORT,
        original_name=path.name,
        detected_format=detected_format,
        path=path,
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        source_mtime_ns=path.stat().st_mtime_ns,
    )


def _exercise_staged_parse(
    source: Path,
    work_root: Path,
    task_id,
    parser,
    validate_document,
    *,
    fingerprint_fn=fingerprint,
):
    """Acceptance harness; its cleanup behavior is covered by failure injection."""

    before = None
    try:
        before = fingerprint_fn(source)
        started = time.perf_counter()
        staged = FileStager(work_root).stage(
            source,
            task_id,
            SourceFileCreate(
                role=FileRole.PRIMARY_REPORT,
                original_name=source.name,
            ),
        )
        assert staged.path != source
        assert staged.path.is_relative_to(work_root.resolve())
        document = parser.parse(staged)
        validate_document(document)
        after = fingerprint_fn(source)
        assert after == before
        return document, time.perf_counter() - started, before, after
    finally:
        try:
            if before is not None:
                assert fingerprint_fn(source) == before
        finally:
            WorkspaceCleaner(work_root).clean_task(task_id)
            assert not (work_root / str(task_id)).exists()


def test_xls_preserves_sheet_cell_merge_types_and_digest(tmp_path: Path) -> None:
    path = tmp_path / "fixture.xls"
    _write_fixture(path)
    staged = _staged_for(path)
    parser = XlsParser()

    first = parser.parse(staged)
    second = parser.parse(staged)

    assert [(item.name_or_number, item.order) for item in first.containers] == [
        ("Sheet 1 中文", 0),
        ("Empty", 1),
    ]
    conclusion = first.find_cell("Sheet 1 中文", "B2")
    assert conclusion.raw_value == "结论"
    assert conclusion.display_value == "结论"
    assert conclusion.structural_address == "sheet:0:Sheet%201%20%E4%B8%AD%E6%96%87/cell:B2"
    assert conclusion.merged_range == "B2:C2"
    assert len(conclusion.content_hash) == 64
    assert conclusion.content_hash == second.find_cell("Sheet 1 中文", "B2").content_hash
    assert first.text_digest == second.text_digest
    assert first.container_count == 2
    assert first.containers[1].blocks == ()

    assert first.find_cell("Sheet 1 中文", "A3").raw_value == 12.5
    assert first.find_cell("Sheet 1 中文", "A4").raw_value is True
    assert first.find_cell("Sheet 1 中文", "A5").display_value.startswith("2026-09-11")
    formula_cell = first.find_cell("Sheet 1 中文", "A6")
    assert formula_cell.formula_if_available is None
    assert any(warning.code == "FORMULA_METADATA_UNAVAILABLE" for warning in first.parse_warnings)


def test_xls_preserves_trailing_space_in_sheet_name_and_locator(tmp_path: Path) -> None:
    """Catch regressions where global string trimming invalidates real sheet locators."""
    path = tmp_path / "trailing-space-sheet.xls"
    workbook = xlwt.Workbook()
    sheet = workbook.add_sheet("DCDC ")
    sheet.write(0, 0, "value")
    workbook.save(str(path))

    document = XlsParser().parse(_staged_for(path))

    assert document.containers[0].name_or_number == "DCDC "
    assert document.containers[0].blocks[0].structural_address == "sheet:0:DCDC%20/range:A1:A1"
    assert document.containers[0].blocks[0].cells[0].structural_address == "sheet:0:DCDC%20/cell:A1"


def test_empty_cells_do_not_create_invented_text(tmp_path: Path) -> None:
    path = tmp_path / "empty.xls"
    workbook = xlwt.Workbook()
    sheet = workbook.add_sheet("Sparse")
    sheet.write(9, 9, "only")
    workbook.save(str(path))

    document = XlsParser().parse(_staged_for(path))
    table = document.containers[0].blocks[0]

    assert [(cell.address, cell.display_value) for cell in table.cells] == [("J10", "only")]


def test_xlrd_error_cells_keep_the_stable_display_code() -> None:
    raw, display = XlsParser._cell_values(
        xlrd.sheet.Cell(xlrd.XL_CELL_ERROR, 0x07), datemode=0
    )

    assert raw == 0x07
    assert display == "#DIV/0!"


def test_out_of_range_date_uses_raw_display_and_cell_warning(tmp_path: Path) -> None:
    path = tmp_path / "out-of-range-date.xls"
    workbook = xlwt.Workbook()
    sheet = workbook.add_sheet("Dates")
    date_style = xlwt.easyxf(num_format_str="YYYY-MM-DD")
    sheet.write(0, 0, 4_000_000, date_style)
    workbook.save(str(path))

    document = XlsParser().parse(_staged_for(path))
    cell = document.find_cell("Dates", "A1")

    assert cell.raw_value == 4_000_000
    assert cell.display_value == "4000000.0"
    assert any(
        warning.code == "DATE_VALUE_OUT_OF_RANGE"
        and warning.structural_address == "sheet:0:Dates/cell:A1"
        for warning in document.parse_warnings
    )


def test_encrypted_workbook_returns_stable_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "encrypted.xls"
    _write_fixture(path)
    staged = _staged_for(path)

    def _encrypted(**_kwargs):
        raise xlrd.biffh.XLRDError("Workbook is encrypted")

    monkeypatch.setattr("hw_review.parsers.xls.xlrd.open_workbook", _encrypted)

    with pytest.raises(XlsParseError) as error:
        XlsParser().parse(staged)
    assert error.value.code == "UNSUPPORTED_OR_ENCRYPTED"


@pytest.mark.parametrize(
    ("setup", "code"),
    [
        ("wrong_format", "WRONG_FORMAT"),
        ("changed_size", "STAGED_FILE_CHANGED"),
        ("changed_hash", "STAGED_FILE_CHANGED"),
        ("corrupt", "CORRUPT_WORKBOOK"),
    ],
)
def test_parser_failures_have_stable_codes(tmp_path: Path, setup: str, code: str) -> None:
    path = tmp_path / "case.xls"
    _write_fixture(path)
    staged = _staged_for(path, detected_format="PDF" if setup == "wrong_format" else "XLS")
    if setup == "changed_size":
        path.write_bytes(path.read_bytes() + b"changed")
    elif setup == "changed_hash":
        payload = bytearray(path.read_bytes())
        payload[-1] ^= 1
        path.write_bytes(payload)
        assert path.stat().st_size == staged.size_bytes
    elif setup == "corrupt":
        path.write_bytes(b"not an xls")
        staged = _staged_for(path)

    with pytest.raises(XlsParseError) as error:
        XlsParser().parse(staged)
    assert error.value.code == code


def test_ole_object_inventory_is_opaque_and_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "object.xls"
    _write_fixture(path)
    staged = _staged_for(path)
    calls: list[str] = []

    class _Stream:
        def __init__(self) -> None:
            self._sent = False

        def read(self, size: int = -1) -> bytes:
            calls.append("read")
            if self._sent:
                return b""
            self._sent = True
            return b"opaque-object"

        def close(self) -> None:
            calls.append("stream-close")

    class _Ole:
        def __init__(self, _path: str) -> None:
            calls.append("inspect")

        def listdir(self, *, streams: bool, storages: bool):
            assert streams is True and storages is False
            return [
                ["Workbook"],
                ["ObjectPool", "0001", "CONTENTS"],
                ["Custom", "Mystery"],
            ]

        def openstream(self, _entry):
            calls.append("openstream")
            return _Stream()

        def close(self) -> None:
            calls.append("ole-close")

    monkeypatch.setattr("hw_review.parsers.xls.olefile.OleFileIO", _Ole)

    first = XlsParser().parse(staged)
    second = XlsParser().parse(staged)
    objects_first = [
        block
        for container in first.containers
        for block in container.blocks
        if block.kind in {"image", "attachment"}
    ]
    objects_second = [
        block
        for container in second.containers
        for block in container.blocks
        if block.kind in {"image", "attachment"}
    ]

    assert len(objects_first) == 2
    by_address = {block.structural_address: block for block in objects_first}
    assert by_address["workbook/object:ObjectPool%2F0001%2FCONTENTS"].kind == "attachment"
    assert by_address["workbook/object:Custom%2FMystery"].kind == "attachment"
    assert [block.content_hash for block in objects_first] == [
        block.content_hash for block in objects_second
    ]
    assert "inspect" in calls and "openstream" in calls
    assert not any(call.startswith("execute") for call in calls)


@pytest.mark.parametrize("failure_point", ["stage", "parse", "fingerprint", "assertion"])
def test_acceptance_cleanup_survives_injected_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    source = tmp_path / "source.xls"
    _write_fixture(source)
    work_root = tmp_path / "work"
    task_id = uuid4()
    before = fingerprint(source)
    parser = XlsParser()
    validate_document = lambda _document: None
    fingerprint_fn = fingerprint

    if failure_point == "stage":
        real_stage = FileStager.stage

        def _stage_then_fail(self, *args, **kwargs):
            real_stage(self, *args, **kwargs)
            raise RuntimeError("injected stage failure")

        monkeypatch.setattr(FileStager, "stage", _stage_then_fail)
    elif failure_point == "parse":
        class _FailingParser:
            def parse(self, _staged):
                raise RuntimeError("injected parser failure")

        parser = _FailingParser()
    elif failure_point == "fingerprint":
        calls = 0

        def _failing_fingerprint(path: Path):
            nonlocal calls
            calls += 1
            if calls >= 2:
                raise RuntimeError("injected fingerprint failure")
            return fingerprint(path)

        fingerprint_fn = _failing_fingerprint
    else:
        def _fail_assertion(_document):
            raise AssertionError("injected acceptance assertion")

        validate_document = _fail_assertion

    with pytest.raises((RuntimeError, AssertionError)):
        _exercise_staged_parse(
            source,
            work_root,
            task_id,
            parser,
            validate_document,
            fingerprint_fn=fingerprint_fn,
        )

    assert fingerprint(source) == before
    assert not (work_root / str(task_id)).exists()


@pytest.mark.skipif(not S01.is_file(), reason="frozen S-01 is unavailable")
def test_real_s01_is_read_only_staged_parsed_and_cleaned() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    work_root = repository_root / ".task-work" / "task-4-s01"
    work_root.mkdir(parents=True, exist_ok=True)
    task_id = uuid4()
    metrics: dict[str, int] = {}

    def _validate(document) -> None:
        nonempty_cells = sum(
            len(block.cells)
            for container in document.containers
            for block in container.blocks
            if block.kind == "table"
        )
        embedded_objects = sum(
            block.kind in {"image", "attachment"}
            for container in document.containers
            for block in container.blocks
        )
        assert document.container_count >= 1
        assert nonempty_cells >= 1
        metrics.update(
            sheet_count=document.container_count,
            nonempty_cell_count=nonempty_cells,
            embedded_object_count=embedded_objects,
        )

    _document, duration_seconds, before, after = _exercise_staged_parse(
        S01,
        work_root,
        task_id,
        XlsParser(),
        _validate,
    )
    assert duration_seconds < 20 * 60
    print(
        "S01_METRICS",
        {
            **metrics,
            "duration_seconds": duration_seconds,
            "source_fingerprint_before": before,
            "source_fingerprint_after": after,
        },
    )
