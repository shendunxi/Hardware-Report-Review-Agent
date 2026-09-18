"""Behavior tests for the immutable A11 checklist export copy."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
import xlrd
import xlwt

from hw_review.rules import A11Registry
from hw_review.domain import TemplateRule
from hw_review.services.a11_export import A11ChecklistWriter, ChecklistExportError


SHEET_NAME = "硬件测试过程检查表"


def _write_template(path: Path, *, version: str = "A11") -> None:
    workbook = xlwt.Workbook()
    workbook.add_sheet("修订记录")
    sheet = workbook.add_sheet(SHEET_NAME, cell_overwrite_ok=True)
    sheet.write(1, 0, version)
    marker_style = xlwt.easyxf("font: bold on, colour red; pattern: pattern solid, fore_colour yellow")
    for rule in A11Registry.source_rows():
        row = rule.source_row - 1
        sheet.write(row, 1, rule.source_sequence)
        for column in range(3, 7):
            sheet.write(row, column, "", marker_style)
    disabled_row = A11Registry.get("TR-05").source_row - 1
    sheet.write(disabled_row, 3, "原始内容", marker_style)
    sheet.write(disabled_row, 6, "TR-05不执行", marker_style)
    workbook.save(str(path))


def _snapshot() -> str:
    task_id = str(uuid4())
    results = []
    result_ids: dict[str, str] = {}
    for rule in A11Registry.executed_rules():
        result_id = str(uuid4())
        result_ids[rule.id] = result_id
        status = {
            "TR-01": "COMPLIANT",
            "TR-02": "NON_COMPLIANT",
            "TR-03": "NOT_APPLICABLE",
        }.get(rule.id, "COMPLIANT")
        results.append(
            {
                "id": result_id,
                "task_id": task_id,
                "rule_id": rule.id,
                "initial_status": status,
                "basis_code": f"{rule.id}_BASIS",
                "basis_text": f"{rule.id}的系统判定依据",
                "evidence_locators": [
                    {
                        "source_file_id": str(uuid4()),
                        "container": "sheet:测试报告",
                        "structural_address": f"sheet:0/cell:A{rule.source_row}",
                        "bbox": None,
                        "quoted_text": f"{rule.id}证据摘要",
                        "content_hash": "a" * 64,
                    }
                ],
                "missing_materials": ["上阶段回归记录"] if rule.id == "TR-02" else [],
                "unresolved_semantics": [],
                "engine_version": "test-engine",
                "baseline_version": "A11",
                "active_revision_no": 0,
                "created_at": "2026-09-17T00:00:00Z",
            }
        )
    return json.dumps(
        {
            "task_id": task_id,
            "revision_no": 1,
            "results": results,
            "decisions": [
                {
                    "id": str(uuid4()),
                    "rule_result_id": result_ids["TR-01"],
                    "final_status": "NON_COMPLIANT",
                    "reason": "人工确认链接与项目不一致",
                    "supplemental_evidence": [],
                    "actor": "reviewer",
                    "decided_at": "2026-09-17T00:01:00Z",
                }
            ],
        },
        ensure_ascii=False,
    )


def test_render_writes_final_status_and_traceable_basis_without_changing_template(
    tmp_path: Path,
) -> None:
    template = tmp_path / "a11.xls"
    _write_template(template)
    before_hash = hashlib.sha256(template.read_bytes()).hexdigest()
    source_book = xlrd.open_workbook(template, formatting_info=True)
    source_sheet = source_book.sheet_by_name(SHEET_NAME)
    source_xf = source_book.xf_list[
        source_sheet.cell_xf_index(A11Registry.get("TR-01").source_row - 1, 3)
    ]

    exported = A11ChecklistWriter(template).render(_snapshot())

    assert hashlib.sha256(template.read_bytes()).hexdigest() == before_hash
    book = xlrd.open_workbook(file_contents=exported, formatting_info=True)
    sheet = book.sheet_by_name(SHEET_NAME)
    tr01 = A11Registry.get("TR-01").source_row - 1
    tr02 = A11Registry.get("TR-02").source_row - 1
    tr03 = A11Registry.get("TR-03").source_row - 1
    tr05 = A11Registry.get("TR-05").source_row - 1
    assert sheet.row_values(tr01, 3, 6) == ["", "╳", ""]
    assert sheet.row_values(tr02, 3, 6) == ["", "╳", ""]
    assert sheet.row_values(tr03, 3, 6) == ["", "", "⊙"]
    assert sheet.cell_value(tr05, 3) == "原始内容"
    assert sheet.cell_value(tr05, 6) == "TR-05不执行"
    exported_xf = book.xf_list[sheet.cell_xf_index(tr01, 3)]
    source_font = source_book.font_list[source_xf.font_index]
    exported_font = book.font_list[exported_xf.font_index]
    assert (
        exported_font.bold,
        exported_font.colour_index,
        exported_xf.background.fill_pattern,
        exported_xf.background.pattern_colour_index,
    ) == (
        source_font.bold,
        source_font.colour_index,
        source_xf.background.fill_pattern,
        source_xf.background.pattern_colour_index,
    )
    tr01_note = sheet.cell_value(tr01, 6)
    assert "系统判定依据：TR-01的系统判定依据" in tr01_note
    assert "可追溯证据：" in tr01_note
    assert "sheet:0/cell:A10" in tr01_note
    assert "人工修改原因：人工确认链接与项目不一致" in tr01_note
    assert "缺失材料：上阶段回归记录" in sheet.cell_value(tr02, 6)


def test_render_rejects_a_non_a11_template(tmp_path: Path) -> None:
    template = tmp_path / "wrong-version.xls"
    _write_template(template, version="A10")

    with pytest.raises(ChecklistExportError) as caught:
        A11ChecklistWriter(template).render(_snapshot())

    assert caught.value.code == "TEMPLATE_VERSION_MISMATCH"


def test_render_rejects_an_unresolved_final_status(tmp_path: Path) -> None:
    template = tmp_path / "a11.xls"
    _write_template(template)
    payload = json.loads(_snapshot())
    payload["results"][0]["initial_status"] = "NEEDS_REVIEW"
    payload["decisions"] = []

    with pytest.raises(ChecklistExportError) as caught:
        A11ChecklistWriter(template).render(json.dumps(payload, ensure_ascii=False))

    assert caught.value.code == "EXPORT_SNAPSHOT_INVALID"


def test_render_summarizes_large_evidence_sets_without_losing_traceability(
    tmp_path: Path,
) -> None:
    template = tmp_path / "a11.xls"
    _write_template(template)
    payload = json.loads(_snapshot())
    payload["results"][0]["evidence_locators"] = [
        {
            "source_file_id": "source-report",
            "container": "sheet:测试数据",
            "structural_address": f"sheet:0/cell:A{index + 1}",
            "bbox": None,
            "quoted_text": "可追溯证据摘要" * 80,
            "content_hash": "a" * 64,
        }
        for index in range(500)
    ]

    exported = A11ChecklistWriter(template).render(
        json.dumps(payload, ensure_ascii=False)
    )

    workbook = xlrd.open_workbook(file_contents=exported)
    note = workbook.sheet_by_name(SHEET_NAME).cell_value(
        A11Registry.get("TR-01").source_row - 1, 6
    )
    assert len(note) <= 32767
    assert "source-report | sheet:测试数据 | sheet:0/cell:A1" in note
    assert "其余" in note and "条证据见系统审核记录" in note


def test_render_localizes_legacy_english_review_text(tmp_path: Path) -> None:
    template = tmp_path / "a11.xls"
    _write_template(template)
    payload = json.loads(_snapshot())
    payload["results"][0]["basis_text"] = (
        "A required material is missing or an objective check has failed. "
        "Atomic bases: FIELD_PROJECT_MISSING."
    )
    payload["results"][0]["unresolved_semantics"] = [
        "Published report naming/version criteria were not supplied; no criterion is invented."
    ]

    exported = A11ChecklistWriter(template).render(
        json.dumps(payload, ensure_ascii=False)
    )

    workbook = xlrd.open_workbook(file_contents=exported)
    note = workbook.sheet_by_name(SHEET_NAME).cell_value(
        A11Registry.get("TR-01").source_row - 1, 6
    )
    assert "A required material" not in note
    assert "Published report naming" not in note
    assert "缺少必需材料，或某项客观校验未通过。" in note
    assert "判定明细代码：FIELD_PROJECT_MISSING。" in note
    assert "系统不会自行推断标准" in note


def test_render_uses_frozen_template_version_rules_and_appends_logical_rule(
    tmp_path: Path,
) -> None:
    template = tmp_path / "a12.xls"
    _write_template(template, version="A12")
    template_id = uuid4()
    timestamp = datetime(2026, 9, 17, tzinfo=timezone.utc)
    baseline = A11Registry.get("TR-01")
    rules = (
        TemplateRule(
            id=uuid5(NAMESPACE_URL, f"{template_id}:TR-01"), template_id=template_id,
            rule_id="TR-01", source_row=baseline.source_row, source_sequence=baseline.source_sequence,
            summary=baseline.summary, verifiable_requirement=baseline.verifiable_requirement,
            required_materials=baseline.required_materials, main_judgment=baseline.main_judgment,
            confirmed_boundary=baseline.confirmed_boundary, enabled=True,
            created_at=timestamp, updated_at=timestamp,
        ),
        TemplateRule(
            id=uuid4(), template_id=template_id, rule_id="CUSTOM-01", source_row=None,
            source_sequence=23, summary="新增人工校验", verifiable_requirement="核对补充说明",
            required_materials="补充说明", main_judgment="MANUAL",
            confirmed_boundary="无自动实现时人工确认", enabled=True,
            created_at=timestamp, updated_at=timestamp,
        ),
    )
    payload = json.loads(_snapshot())
    payload["results"] = [payload["results"][0], {
        **payload["results"][0], "id": str(uuid4()), "rule_id": "CUSTOM-01",
        "initial_status": "COMPLIANT", "basis_text": "人工已核对补充说明",
    }]
    payload["decisions"] = []
    before_hash = hashlib.sha256(template.read_bytes()).hexdigest()

    exported = A11ChecklistWriter(template).render(
        json.dumps(payload, ensure_ascii=False),
        template_path=template,
        template_version="A12",
        rules=rules,
        expected_sha256=before_hash,
    )

    assert hashlib.sha256(template.read_bytes()).hexdigest() == before_hash
    sheet = xlrd.open_workbook(file_contents=exported).sheet_by_name(SHEET_NAME)
    assert sheet.cell_value(baseline.source_row - 1, 3) == "√"
    appended = sheet.nrows - 1
    assert sheet.cell_value(appended, 1) == 23
    assert sheet.cell_value(appended, 2) == "新增人工校验"
    assert sheet.cell_value(appended, 3) == "√"
