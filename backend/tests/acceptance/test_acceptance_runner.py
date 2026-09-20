"""Focused behavior checks for the frozen-sample runner."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import xlwt

from hw_review.acceptance.run_samples import (
    SAMPLE_ROOT_ENV,
    SamplePathError,
    _parse_samples,
    main,
    resolve_sample_path,
)
from hw_review.parsers.base import ParserError


def test_failed_parse_still_records_elapsed_time_and_memory(
    tmp_path: Path, monkeypatch
) -> None:
    """A failed gate must retain measurements rather than report zero work."""
    source = tmp_path / "source.xls"
    workbook = xlwt.Workbook()
    workbook.add_sheet("Sheet1").write(0, 0, "value")
    workbook.save(str(source))

    def fail_after_work(_self, _staged):
        time.sleep(0.01)
        raise ParserError("EXPECTED_FAILURE", "intentional parser failure")

    monkeypatch.setattr("hw_review.acceptance.run_samples.XlsParser.parse", fail_after_work)
    manifest = {
        "samples": [
            {
                "id": "S-TEST",
                "group_id": "R-TEST",
                "role": "TASK_PRIMARY",
                "relative_path": "source.xls",
                "expected_extension": ".xls",
            }
        ]
    }

    records, parsed = _parse_samples(manifest, tmp_path / "output", sample_root=tmp_path)

    assert parsed == {}
    assert records[0]["parse_status"] == "FAILED"
    assert records[0]["error_code"] == "EXPECTED_FAILURE"
    assert records[0]["parse_seconds"] >= 0.01
    assert records[0]["peak_rss_mib"] > 0

    # With no absolute path left in the manifest, the relative path is the only
    # input, so it must not be able to leave the supplied sample root.
    expected = tmp_path / "nested" / "source.xls"
    assert resolve_sample_path(tmp_path, "nested\\source.xls") == expected
    assert resolve_sample_path(tmp_path, "nested/source.xls") == expected
    for rejected in (
        "C:\\Windows\\win.ini",
        "/etc/passwd",
        "../outside.xls",
        "nested/../../outside.xls",
        "",
    ):
        with pytest.raises(SamplePathError):
            resolve_sample_path(tmp_path, rejected)

    escaped = {
        "samples": [
            {
                "id": "S-BAD",
                "group_id": "R-TEST",
                "role": "TASK_PRIMARY",
                "relative_path": "../outside.xls",
                "expected_extension": ".xls",
            }
        ]
    }
    escaped_records, escaped_parsed = _parse_samples(
        escaped, tmp_path / "escaped-output", sample_root=tmp_path / "root"
    )
    assert escaped_parsed == {}
    assert escaped_records[0]["error_stage"] == "SOURCE"
    assert escaped_records[0]["error_code"] == "INVALID_SAMPLE_PATH"

    # A run with no sample root must fail loudly instead of emitting a
    # machine-dependent result.
    monkeypatch.delenv(SAMPLE_ROOT_ENV, raising=False)
    with pytest.raises(SystemExit) as missing_root:
        main(
            [
                "--manifest",
                str(Path(__file__).with_name("sample_manifest.json")),
                "--output",
                str(tmp_path / "cli-output"),
            ]
        )
    assert missing_root.value.code == 2
