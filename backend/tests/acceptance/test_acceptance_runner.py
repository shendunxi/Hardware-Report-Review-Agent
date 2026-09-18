"""Focused behavior checks for the frozen-sample runner."""

from __future__ import annotations

import time
from pathlib import Path

import xlwt

from hw_review.acceptance.run_samples import _parse_samples
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
                "absolute_path": str(source),
                "expected_extension": ".xls",
            }
        ]
    }

    records, parsed = _parse_samples(manifest, tmp_path / "output")

    assert parsed == {}
    assert records[0]["parse_status"] == "FAILED"
    assert records[0]["error_code"] == "EXPECTED_FAILURE"
    assert records[0]["parse_seconds"] >= 0.01
    assert records[0]["peak_rss_mib"] > 0

