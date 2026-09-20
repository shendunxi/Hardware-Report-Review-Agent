from __future__ import annotations

import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest
import xlrd
import xlwt
from xlutils.copy import copy as copy_workbook

from hw_review.domain import TemplateStatus
from hw_review.persistence import repositories
from hw_review.services.templates import (
    A11TemplateValidator,
    TemplateService,
    TemplateServiceError,
)


BACKEND_ROOT = Path(__file__).resolve().parents[2]
PACKAGED_A11 = BACKEND_ROOT / "resources" / "a11" / "hardware-test-process-checklist-a11.xls"


def _database_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _migrate(database_url: str) -> None:
    environment = os.environ.copy()
    environment["HW_REVIEW_DATABASE_URL"] = database_url
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.fixture
def service(tmp_path: Path):
    database_url = _database_url(tmp_path / "templates.db")
    _migrate(database_url)
    bundle = repositories(database_url)
    instance = TemplateService(
        bundle,
        template_root=tmp_path / "managed-templates",
        baseline_path=PACKAGED_A11,
    )
    try:
        yield instance
    finally:
        bundle.close()


def _versioned_copy(destination: Path, version: str) -> Path:
    source = xlrd.open_workbook(PACKAGED_A11, formatting_info=True)
    writable = copy_workbook(source)
    sheet_index = source.sheet_names().index("硬件测试过程检查表")
    writable.get_sheet(sheet_index).write(1, 0, version)
    writable.save(str(destination))
    return destination


def _missing_sheet_workbook(destination: Path) -> Path:
    workbook = xlwt.Workbook()
    workbook.add_sheet("错误工作表").write(0, 0, "A12")
    workbook.save(str(destination))
    return destination


def test_ensure_baseline_is_idempotent_and_never_modifies_packaged_a11(service) -> None:
    before = sha256(PACKAGED_A11.read_bytes()).hexdigest()

    first = service.ensure_baseline()
    second = service.ensure_baseline()

    assert first == second
    assert first.status is TemplateStatus.PUBLISHED
    assert first.version == "A11"
    assert first.source_rows == 22
    assert first.effective_rules == 21
    assert len(service.detail(first.id)["rules"]) == 22
    assert sha256(PACKAGED_A11.read_bytes()).hexdigest() == before


def test_upload_valid_a12_creates_managed_draft_without_modifying_upload(
    service, tmp_path: Path
) -> None:
    source = _versioned_copy(tmp_path / "A12.xls", "A12")
    before = (sha256(source.read_bytes()).hexdigest(), source.stat().st_size, source.stat().st_mtime_ns)

    draft = service.upload(
        source,
        original_name="硬件测试过程检查单-A12.xls",
        name="硬件测试过程检查单",
        version="A12",
        actor="模板管理员",
    )

    assert draft.status is TemplateStatus.DRAFT
    assert draft.source_path != source
    assert draft.source_path.read_bytes() == source.read_bytes()
    assert draft.source_rows == 22
    assert draft.effective_rules == 21
    assert not [item for item in draft.validation_findings if item.severity == "ERROR"]
    assert (sha256(source.read_bytes()).hexdigest(), source.stat().st_size, source.stat().st_mtime_ns) == before


def test_a111_and_missing_sheet_are_persisted_as_publish_blockers(
    service, tmp_path: Path
) -> None:
    a111 = service.upload(
        _versioned_copy(tmp_path / "A111.xls", "A111"),
        original_name="A111.xls",
        name="硬件测试过程检查单",
        version="A111",
        actor="模板管理员",
    )
    broken = service.upload(
        _missing_sheet_workbook(tmp_path / "broken.xls"),
        original_name="broken.xls",
        name="缺失工作表模板",
        version="A12",
        actor="模板管理员",
    )

    assert {item.code for item in a111.validation_findings if item.severity == "ERROR"} == {"INVALID_A111_VERSION"}
    assert "CHECKLIST_SHEET_MISSING" in {item.code for item in broken.validation_findings if item.severity == "ERROR"}
    with pytest.raises(TemplateServiceError) as error:
        service.publish(a111.id, actor="模板管理员")
    assert error.value.code == "TEMPLATE_PUBLISH_BLOCKED"


def test_draft_rule_changes_refresh_counts_and_published_version_is_immutable(
    service, tmp_path: Path
) -> None:
    draft = service.upload(
        _versioned_copy(tmp_path / "A12.xls", "A12"),
        original_name="A12.xls",
        name="硬件测试过程检查单",
        version="A12",
        actor="模板管理员",
    )
    updated = service.update_rule(
        draft.id,
        "TR-01",
        {
            "summary": "JIRA 项目与链接检查",
            "enabled": False,
            "main_judgment": "DISABLED",
        },
        actor="模板管理员",
    )
    assert updated.summary == "JIRA 项目与链接检查"
    assert service.detail(draft.id)["template"].effective_rules == 20

    added = service.add_rule(
        draft.id,
        {
            "rule_id": "CUSTOM-01",
            "summary": "新增人工检查项",
            "verifiable_requirement": "由审核人员核对新增要求",
            "required_materials": "新增要求证明材料",
            "main_judgment": "MANUAL",
            "confirmed_boundary": "未配置自动判定条件时进入待人工确认",
            "enabled": True,
        },
        actor="模板管理员",
    )
    assert added.source_row is None
    assert service.detail(draft.id)["template"].effective_rules == 21
    service.delete_rule(draft.id, "CUSTOM-01", actor="模板管理员")

    published = service.publish(draft.id, actor="模板管理员")
    assert published.status is TemplateStatus.PUBLISHED
    with pytest.raises(TemplateServiceError) as error:
        service.update_rule(
            published.id,
            "TR-01",
            {"summary": "不得修改"},
            actor="模板管理员",
        )
    assert error.value.code == "TEMPLATE_IMMUTABLE"

    retired = service.retire(published.id, actor="模板管理员")
    assert retired.status is TemplateStatus.RETIRED
    assert len(service.detail(retired.id)["rules"]) == 22


def test_validator_reports_version_mismatch_without_rewriting_workbook(
    tmp_path: Path,
) -> None:
    source = _versioned_copy(tmp_path / "mismatch.xls", "A12")
    before = sha256(source.read_bytes()).hexdigest()

    result = A11TemplateValidator().validate(source, expected_version="A13")

    assert "TEMPLATE_VERSION_MISMATCH" in {item.code for item in result.findings}
    assert sha256(source.read_bytes()).hexdigest() == before
