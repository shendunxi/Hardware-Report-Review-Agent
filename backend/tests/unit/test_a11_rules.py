from datetime import datetime, timezone
from typing import get_type_hints
from pathlib import Path
from urllib.parse import quote
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from hw_review.domain.enums import EvidenceKind, FileRole, ReviewStatus
from hw_review.domain.hashing import normalized_text_hash, ordered_identity_hash
from hw_review.domain.models import (
    ContentBlock,
    DocumentContainer,
    EvidenceLocator,
    ReportDocument,
    ReviewInput,
    ReviewSource,
    StagedFile,
    TableCell,
)
from hw_review.domain.ports import DocumentQuery
from hw_review.rules.a11_engine import A11Engine, NormalizedDocumentQuery


class FactQuery:
    def __init__(self, *, labels=(), texts=(), kinds=()):
        self._labels = dict(labels)
        self._texts = dict(texts)
        self._kinds = set(kinds)

    def find_text(self, patterns: tuple[str, ...]) -> tuple[EvidenceLocator, ...]:
        found = []
        for pattern in patterns:
            found.extend(self._texts.get(pattern, ()))
        return tuple(dict.fromkeys(found))

    def find_nonempty_labels(self, labels: tuple[str, ...]) -> dict[str, EvidenceLocator]:
        return {label: self._labels[label] for label in labels if label in self._labels}

    def has_evidence_kind(self, kind: EvidenceKind) -> bool:
        return kind in self._kinds


def _locator(text: str = "evidence", *, source_file_id: UUID | None = None, address: str = "page:0/block:0") -> EvidenceLocator:
    return EvidenceLocator(
        source_file_id=source_file_id or uuid4(),
        container="page:0",
        structural_address=address,
        quoted_text=text,
        content_hash=normalized_text_hash(text),
    )


def _empty_document(source_file_id: UUID) -> ReportDocument:
    return ReportDocument(
        id=uuid4(), source_file_id=source_file_id, format="PDF", parser_version="test-1",
        container_count=0, text_digest=ordered_identity_hash(()), containers=(),
    )


def _review_input(query) -> ReviewInput:
    task_id = uuid4()
    source = StagedFile(
        id=uuid4(), task_id=task_id, role=FileRole.PRIMARY_REPORT,
        original_name="report.pdf", detected_format="PDF", path=Path("report.pdf"),
        size_bytes=0, sha256="0" * 64, source_mtime_ns=0,
    )
    return ReviewInput(
        task_id=task_id,
        active_revision_no=1,
        sources=(ReviewSource(source_file=source, document=_empty_document(source.id)),),
        evaluated_at=datetime(2026, 9, 15, 1, 2, 3, tzinfo=timezone.utc),
        query=query,
    )


def _status(rule_id: str, query: FactQuery) -> ReviewStatus:
    return A11Engine().evaluate_rule(_review_input(query), rule_id).initial_status


def test_rule_results_use_chinese_user_facing_basis_text_and_keep_stable_codes() -> None:
    hard_failure = A11Engine().evaluate_rule(_review_input(FactQuery()), "TR-04")
    pending = A11Engine().evaluate_rule(_review_input(FactQuery()), "TR-08")

    assert hard_failure.basis_text == (
        "缺少必需材料，或某项客观校验未通过。"
        "判定明细代码：FIELD_典型工作功耗_MISSING、FIELD_待机功耗_MISSING、"
        "EVIDENCE_POWER_RECORD_MISSING。"
    )
    assert pending.basis_text == (
        "未发现确定性不符合项，但仍有语义判断事项待确认。"
        "判定明细代码：HOMEPAGE_FIELD_LIST_ABSENT。"
    )
    assert pending.unresolved_semantics == (
        "未提供已发布的首页必填字段清单；系统不会自行推断字段名。",
    )
    assert hard_failure.engine_version == "a11-engine-2"


def test_review_input_rejects_missing_primary_and_mismatched_document_identity() -> None:
    task_id = uuid4()
    supporting = StagedFile(
        id=uuid4(), task_id=task_id, role=FileRole.SUPPORTING_EVIDENCE,
        evidence_kinds=(EvidenceKind.OTHER,), original_name="evidence.pdf",
        detected_format="PDF", path=Path("evidence.pdf"), size_bytes=0,
        sha256="0" * 64, source_mtime_ns=0,
    )
    with pytest.raises(ValidationError, match="primary"):
        ReviewInput(
            task_id=task_id, active_revision_no=1,
            sources=(ReviewSource(source_file=supporting, document=_empty_document(supporting.id)),),
            evaluated_at=datetime.now(timezone.utc), query=FactQuery(),
        )
    with pytest.raises(ValidationError, match="source_file_id"):
        ReviewSource(source_file=supporting, document=_empty_document(uuid4()))


def test_review_input_exposes_the_exact_document_query_boundary() -> None:
    assert get_type_hints(ReviewInput)["query"] is DocumentQuery


def test_normalized_query_is_literal_case_insensitive_ordered_and_deduplicated() -> None:
    task_id = uuid4()
    source = StagedFile(
        id=uuid4(), task_id=task_id, role=FileRole.PRIMARY_REPORT,
        original_name="JIRA_RECORD.pdf", detected_format="PDF", path=Path("report.pdf"),
        size_bytes=0, sha256="0" * 64, source_mtime_ns=0,
    )
    first = ContentBlock(id=uuid4(), kind="text", order=0, structural_address="page:0/block:0", text="Alpha [x]", content_hash=normalized_text_hash("Alpha [x]"))
    second = ContentBlock(id=uuid4(), kind="text", order=1, structural_address="page:0/block:1", text="alpha beta", content_hash=normalized_text_hash("alpha beta"))
    container = DocumentContainer(id=uuid4(), kind="page", name_or_number=1, order=0, blocks=(first, second))
    document = ReportDocument(
        id=uuid4(), source_file_id=source.id, format="PDF", parser_version="test-1",
        container_count=1,
        text_digest=ordered_identity_hash((
            f"0\0{first.order}\0{first.structural_address}\0{first.content_hash}",
            f"0\0{second.order}\0{second.structural_address}\0{second.content_hash}",
        )), containers=(container,),
    )
    query = NormalizedDocumentQuery((ReviewSource(source_file=source, document=document),))

    assert [item.structural_address for item in query.find_text(("ALPHA", "[x]", ".*"))] == ["page:0/block:0", "page:0/block:1"]
    assert all(item.source_file_id == source.id for item in query.find_text(("alpha",)))
    assert query.has_evidence_kind(EvidenceKind.JIRA_RECORD) is False


def test_normalized_query_requires_traceable_nonempty_adjacent_label_value() -> None:
    task_id = uuid4()
    source = StagedFile(
        id=uuid4(), task_id=task_id, role=FileRole.PRIMARY_REPORT,
        original_name="report.xls", detected_format="XLS", path=Path("report.xls"),
        size_bytes=0, sha256="0" * 64, source_mtime_ns=0,
    )
    sheet_name = "首页"
    sheet_prefix = f"sheet:0:{quote(sheet_name, safe='')}"
    values = ((0, 0, "版本"), (0, 1, "A11"), (1, 0, "空字段"), (1, 1, ""), (2, 0, "孤立标签"), (2, 2, "not-adjacent"))
    cells = tuple(
        TableCell(row=row, column=column, address=f"{chr(65 + column)}{row + 1}", structural_address=f"{sheet_prefix}/cell:{chr(65 + column)}{row + 1}", raw_value=value, display_value=value, content_hash=normalized_text_hash(value))
        for row, column, value in values
    )
    block = ContentBlock(id=uuid4(), kind="table", order=0, structural_address=f"{sheet_prefix}/range:A1:C3", content_hash=ordered_identity_hash(f"{cell.structural_address}\0{cell.content_hash}" for cell in cells), cells=cells)
    container = DocumentContainer(id=uuid4(), kind="sheet", name_or_number=sheet_name, order=0, blocks=(block,))
    document = ReportDocument(id=uuid4(), source_file_id=source.id, format="XLS", parser_version="test-1", container_count=1, text_digest=ordered_identity_hash((f"{container.order}\0{block.order}\0{block.structural_address}\0{block.content_hash}",)), containers=(container,))
    query = NormalizedDocumentQuery((ReviewSource(source_file=source, document=document),))

    found = query.find_nonempty_labels(("版本", "空字段", "孤立标签", "未知"))

    assert tuple(found) == ("版本",)
    assert found["版本"].quoted_text == "A11"
    assert found["版本"].structural_address.endswith("/cell:B1")


def test_normalized_query_routes_evidence_only_from_explicit_support_metadata() -> None:
    task_id = uuid4()
    primary = StagedFile(id=uuid4(), task_id=task_id, role=FileRole.PRIMARY_REPORT, original_name="JIRA_RECORD.pdf", detected_format="PDF", path=Path("primary.pdf"), size_bytes=0, sha256="0" * 64, source_mtime_ns=0)
    support = StagedFile(id=uuid4(), task_id=task_id, role=FileRole.SUPPORTING_EVIDENCE, evidence_kinds=(EvidenceKind.PAPER_RECORD,), original_name="anything.pdf", detected_format="PDF", path=Path("support.pdf"), size_bytes=0, sha256="1" * 64, source_mtime_ns=0)
    query = NormalizedDocumentQuery((ReviewSource(source_file=primary, document=_empty_document(primary.id)), ReviewSource(source_file=support, document=_empty_document(support.id))))

    assert query.has_evidence_kind(EvidenceKind.JIRA_RECORD) is False
    assert query.has_evidence_kind(EvidenceKind.PAPER_RECORD) is True


@pytest.mark.parametrize(
    ("rule_id", "query", "expected", "diagnostic_field"),
    [
        ("TR-01", FactQuery(), ReviewStatus.NON_COMPLIANT, "missing_materials"),
        ("TR-02", FactQuery(), ReviewStatus.NON_COMPLIANT, "missing_materials"),
        ("TR-03", FactQuery(texts=(("软件相关FAIL：无", (_locator("软件相关FAIL：无"),)),)), ReviewStatus.NOT_APPLICABLE, "evidence_locators"),
        ("TR-04", FactQuery(), ReviewStatus.NON_COMPLIANT, "missing_materials"),
        ("TR-06", FactQuery(texts=(("内部能力限制：无", (_locator("内部能力限制：无"),)),)), ReviewStatus.NOT_APPLICABLE, "evidence_locators"),
        ("TR-07", FactQuery(), ReviewStatus.NON_COMPLIANT, "missing_materials"),
        ("TR-08", FactQuery(), ReviewStatus.NEEDS_REVIEW, "unresolved_semantics"),
        ("TR-09", FactQuery(), ReviewStatus.NEEDS_REVIEW, "unresolved_semantics"),
        ("TR-10", FactQuery(), ReviewStatus.NON_COMPLIANT, "missing_materials"),
        ("TR-11", FactQuery(), ReviewStatus.NON_COMPLIANT, "missing_materials"),
        ("TR-12", FactQuery(), ReviewStatus.NON_COMPLIANT, "missing_materials"),
        ("TR-13", FactQuery(), ReviewStatus.NON_COMPLIANT, "missing_materials"),
        ("TR-14", FactQuery(texts=(("EMC适用性：不适用", (_locator("EMC适用性：不适用"),)),)), ReviewStatus.NOT_APPLICABLE, "evidence_locators"),
        ("TR-15", FactQuery(), ReviewStatus.NON_COMPLIANT, "missing_materials"),
        ("TR-16", FactQuery(), ReviewStatus.NEEDS_REVIEW, "unresolved_semantics"),
        ("TR-17", FactQuery(), ReviewStatus.NON_COMPLIANT, "missing_materials"),
        ("TR-18", FactQuery(), ReviewStatus.NON_COMPLIANT, "missing_materials"),
        ("TR-19", FactQuery(texts=(("CA卡工装温升测试：不适用", (_locator("CA卡工装温升测试：不适用"),)),)), ReviewStatus.NOT_APPLICABLE, "evidence_locators"),
        ("TR-20", FactQuery(labels=(("阶段", _locator("DS")),)), ReviewStatus.NOT_APPLICABLE, "evidence_locators"),
        ("TR-21", FactQuery(labels=(("WIFI适用性", _locator("否")),)), ReviewStatus.NOT_APPLICABLE, "evidence_locators"),
        ("TR-22", FactQuery(texts=(("温升部件喷漆检查：不适用", (_locator("温升部件喷漆检查：不适用"),)),)), ReviewStatus.NOT_APPLICABLE, "evidence_locators"),
    ],
)
def test_rule_missing_material_or_explicit_na_branches(rule_id, query, expected, diagnostic_field) -> None:
    result = A11Engine().evaluate_rule(_review_input(query), rule_id)
    assert result.initial_status is expected
    assert getattr(result, diagnostic_field)


def test_objective_rule_only_success_branches() -> None:
    evidence = _locator()
    cases = {
        "TR-04": FactQuery(labels=(("典型工作功耗", evidence), ("待机功耗", evidence)), kinds=(EvidenceKind.POWER_RECORD,)),
        "TR-19": FactQuery(labels=(("CA卡工装温升测试适用性", _locator("适用")), ("温升测试结果", evidence)), kinds=(EvidenceKind.TEMPERATURE_RECORD,)),
        "TR-20": FactQuery(labels=(("阶段", _locator("PP")), ("开关机自动化测试结果", evidence)), kinds=(EvidenceKind.AUTOMATION_RECORD,)),
        "TR-21": FactQuery(labels=(("WIFI适用性", _locator("是")), ("WIFI小结论", evidence), ("WIFI页面顶端结论", evidence))),
    }
    assert {rule_id: _status(rule_id, query) for rule_id, query in cases.items()} == {rule_id: ReviewStatus.COMPLIANT for rule_id in cases}


@pytest.mark.parametrize(
    ("rule_id", "label", "value"),
    [
        ("TR-03", "软件相关FAIL", "无"),
        ("TR-06", "内部能力限制", "无"),
        ("TR-14", "EMC适用性", "不适用"),
        ("TR-19", "CA卡工装温升测试适用性", "不适用"),
        ("TR-22", "温升部件喷漆适用性", "不适用"),
    ],
)
def test_allowed_not_applicable_branches_accept_traceable_label_values(rule_id, label, value) -> None:
    result = A11Engine().evaluate_rule(
        _review_input(FactQuery(labels=((label, _locator(value)),))), rule_id
    )
    assert result.initial_status is ReviewStatus.NOT_APPLICABLE
    assert result.evidence_locators


def test_tr03_without_fail_list_or_explicit_no_fail_proof_is_noncompliant() -> None:
    result = A11Engine().evaluate_rule(_review_input(FactQuery()), "TR-03")
    assert result.initial_status is ReviewStatus.NON_COMPLIANT
    assert result.missing_materials == ("软件FAIL清单或明确无FAIL依据",)


def test_pp_stage_text_is_not_misclassified_as_non_pp() -> None:
    query = FactQuery(
        labels=(("阶段", _locator("PP阶段")), ("开关机自动化测试结果", _locator("通过"))),
        kinds=(EvidenceKind.AUTOMATION_RECORD,),
    )
    assert _status("TR-20", query) is ReviewStatus.COMPLIANT


@pytest.mark.parametrize("stage_text", ["非PP", "非 PP", "non-pp", "not pp"])
def test_explicit_non_pp_stage_outranks_positive_pp_token(stage_text: str) -> None:
    result = A11Engine().evaluate_rule(
        _review_input(FactQuery(labels=(("阶段", _locator(stage_text)),))), "TR-20"
    )
    assert result.initial_status is ReviewStatus.NOT_APPLICABLE
    assert result.evidence_locators[0].quoted_text == stage_text


def test_embedded_traceable_coating_records_do_not_require_other_tag() -> None:
    evidence = _locator()
    query = FactQuery(
        labels=(("温升部件喷漆适用性", _locator("适用")),),
        texts=(("CPU散热器喷漆状态", (evidence,)), ("tuner屏蔽框喷漆状态", (evidence,))),
        kinds=(EvidenceKind.TEMPERATURE_RECORD, EvidenceKind.PUBLISHED_CRITERIA),
    )
    result = A11Engine().evaluate_rule(_review_input(query), "TR-22")
    assert result.initial_status is ReviewStatus.NEEDS_REVIEW
    assert not result.missing_materials


def test_component_name_alone_is_not_coating_state_evidence() -> None:
    evidence = _locator()
    query = FactQuery(
        labels=(("温升部件喷漆适用性", _locator("适用")),),
        texts=(("CPU散热器", (evidence,)), ("tuner屏蔽框", (evidence,))),
        kinds=(EvidenceKind.TEMPERATURE_RECORD, EvidenceKind.PUBLISHED_CRITERIA),
    )
    result = A11Engine().evaluate_rule(_review_input(query), "TR-22")
    assert result.initial_status is ReviewStatus.NON_COMPLIANT
    assert result.missing_materials == (
        "CPU散热器喷漆状态照片/记录",
        "tuner屏蔽框喷漆状态照片/记录",
    )


def test_explicit_no_unexecuted_items_does_not_require_a_reason() -> None:
    query = FactQuery(
        labels=(("未执行项", _locator("无")),),
        texts=(("未执行项", (_locator("未执行项"),)),),
        kinds=(EvidenceKind.REQUIREMENT_OR_CASE_MAPPING,),
    )
    result = A11Engine().evaluate_rule(_review_input(query), "TR-10")
    assert result.initial_status is ReviewStatus.NEEDS_REVIEW
    assert "未执行原因" not in result.missing_materials


def test_tr10_checks_only_fields_declared_by_traceable_required_data_list() -> None:
    declared = _locator("电压、纹波")
    voltage = _locator("12.0V")
    missing_query = FactQuery(
        labels=(("必填数据清单", declared), ("电压", voltage)),
        kinds=(EvidenceKind.REQUIREMENT_OR_CASE_MAPPING,),
    )
    complete_query = FactQuery(
        labels=(
            ("必填数据清单", declared),
            ("电压", voltage),
            ("纹波", _locator("20mV")),
        ),
        kinds=(EvidenceKind.REQUIREMENT_OR_CASE_MAPPING,),
    )

    missing = A11Engine().evaluate_rule(_review_input(missing_query), "TR-10")
    complete = A11Engine().evaluate_rule(_review_input(complete_query), "TR-10")

    assert missing.initial_status is ReviewStatus.NON_COMPLIANT
    assert missing.missing_materials == ("必填数据：纹波",)
    assert declared in missing.evidence_locators
    assert complete.initial_status is ReviewStatus.NEEDS_REVIEW
    assert not complete.missing_materials


def test_tr10_without_readable_declared_list_stays_semantic_pending() -> None:
    result = A11Engine().evaluate_rule(
        _review_input(FactQuery(kinds=(EvidenceKind.REQUIREMENT_OR_CASE_MAPPING,))),
        "TR-10",
    )
    assert result.initial_status is ReviewStatus.NEEDS_REVIEW
    assert result.unresolved_semantics


def test_tr11_checks_only_fields_declared_by_traceable_numeric_list() -> None:
    declared = _locator("电压、纹波")
    invalid_value = _locator("twelve volts")
    invalid_query = FactQuery(
        labels=(
            ("数值字段清单", declared),
            ("电压", invalid_value),
            ("纹波", _locator(".25 mV")),
        ),
        kinds=(EvidenceKind.PAPER_RECORD,),
    )
    missing_query = FactQuery(
        labels=(("数值字段清单", declared), ("电压", _locator("12V"))),
        kinds=(EvidenceKind.PAPER_RECORD,),
    )
    valid_query = FactQuery(
        labels=(
            ("数值字段清单", declared),
            ("电压", _locator("12V")),
            ("纹波", _locator(".25 mV")),
        ),
        kinds=(EvidenceKind.PAPER_RECORD,),
    )

    invalid = A11Engine().evaluate_rule(_review_input(invalid_query), "TR-11")
    missing = A11Engine().evaluate_rule(_review_input(missing_query), "TR-11")
    valid = A11Engine().evaluate_rule(_review_input(valid_query), "TR-11")

    assert invalid.initial_status is ReviewStatus.NON_COMPLIANT
    assert invalid_value in invalid.evidence_locators
    assert "NUMERIC_FORMAT_INVALID" in invalid.basis_text
    assert not invalid.missing_materials
    assert missing.initial_status is ReviewStatus.NON_COMPLIANT
    assert missing.missing_materials == ("数值字段：纹波",)
    assert declared in missing.evidence_locators
    assert valid.initial_status is ReviewStatus.NEEDS_REVIEW
    assert valid.unresolved_semantics


def test_tr11_without_readable_numeric_list_stays_semantic_pending() -> None:
    result = A11Engine().evaluate_rule(
        _review_input(FactQuery(kinds=(EvidenceKind.PAPER_RECORD,))), "TR-11"
    )
    assert result.initial_status is ReviewStatus.NEEDS_REVIEW
    assert result.unresolved_semantics


def test_semantic_rules_remain_pending_when_hard_requirements_are_present() -> None:
    evidence = _locator()
    cases = {
        "TR-01": FactQuery(labels=(("JIRA链接", evidence),), kinds=(EvidenceKind.JIRA_RECORD, EvidenceKind.PUBLISHED_CRITERIA)),
        "TR-02": FactQuery(kinds=(EvidenceKind.PREVIOUS_STAGE_REPORT,)),
        "TR-03": FactQuery(labels=(("处理说明", evidence),), texts=(("软件相关FAIL", (evidence,)),), kinds=(EvidenceKind.JIRA_RECORD,)),
        "TR-06": FactQuery(labels=(("测试需求", evidence), ("能力限制", evidence), ("委外安排", evidence))),
        "TR-07": FactQuery(labels=(("报告版本", evidence), ("项目", evidence), ("阶段", evidence)), kinds=(EvidenceKind.PUBLISHED_CRITERIA,)),
        "TR-08": FactQuery(kinds=(EvidenceKind.PUBLISHED_CRITERIA,)),
        "TR-09": FactQuery(labels=(("机型", evidence), ("区域", evidence)), kinds=(EvidenceKind.REQUIREMENT_OR_CASE_MAPPING,)),
        "TR-10": FactQuery(kinds=(EvidenceKind.REQUIREMENT_OR_CASE_MAPPING,)),
        "TR-11": FactQuery(kinds=(EvidenceKind.PAPER_RECORD,)),
        "TR-12": FactQuery(labels=(("报告数据", evidence), ("小结", evidence), ("结论", evidence))),
        "TR-13": FactQuery(labels=tuple((label, evidence) for label in ("原始记录", "日志", "问题清单", "小结", "结论"))),
        "TR-14": FactQuery(labels=(("EMC适用性", _locator("适用")), ("EMC合格余量", _locator("3.5dB"))), kinds=(EvidenceKind.EMC_REPORT, EvidenceKind.JIRA_RECORD)),
        "TR-15": FactQuery(labels=(("当前阶段", evidence),), kinds=(EvidenceKind.PREVIOUS_STAGE_REPORT,)),
        "TR-16": FactQuery(kinds=(EvidenceKind.PUBLISHED_CRITERIA,)),
        "TR-17": FactQuery(labels=tuple((label, evidence) for label in ("问题清单", "测试对象", "测试条件", "观察现象", "实际结果"))),
        "TR-18": FactQuery(labels=(("结论", evidence), ("问题清单", evidence))),
        "TR-22": FactQuery(labels=(("温升部件喷漆适用性", _locator("适用")),), texts=(("CPU散热器喷漆状态", (evidence,)), ("tuner屏蔽框喷漆状态", (evidence,))), kinds=(EvidenceKind.TEMPERATURE_RECORD, EvidenceKind.OTHER, EvidenceKind.PUBLISHED_CRITERIA)),
    }
    actual = {rule_id: A11Engine().evaluate_rule(_review_input(query), rule_id) for rule_id, query in cases.items()}
    assert {rule_id: result.initial_status for rule_id, result in actual.items()} == {rule_id: ReviewStatus.NEEDS_REVIEW for rule_id in cases}
    assert all(result.unresolved_semantics for result in actual.values())


def test_homepage_declared_required_fields_are_checked_without_inventing_names() -> None:
    list_evidence = _locator("项目、报告日期")
    value_evidence = _locator("Project X")
    missing = FactQuery(
        labels=(("首页必填字段清单", list_evidence), ("项目", value_evidence)),
        kinds=(EvidenceKind.PUBLISHED_CRITERIA,),
    )
    complete = FactQuery(
        labels=(
            ("首页必填字段清单", list_evidence),
            ("项目", value_evidence),
            ("报告日期", _locator("2026-09-15")),
        ),
        kinds=(EvidenceKind.PUBLISHED_CRITERIA,),
    )

    missing_result = A11Engine().evaluate_rule(_review_input(missing), "TR-08")
    complete_result = A11Engine().evaluate_rule(_review_input(complete), "TR-08")

    assert missing_result.initial_status is ReviewStatus.NON_COMPLIANT
    assert missing_result.missing_materials == ("首页必填字段：报告日期",)
    assert list_evidence in missing_result.evidence_locators
    assert complete_result.initial_status is ReviewStatus.NEEDS_REVIEW
    assert complete_result.unresolved_semantics


@pytest.mark.parametrize(
    ("rule_id", "query", "expected_missing"),
    [
        ("TR-01", FactQuery(kinds=(EvidenceKind.JIRA_RECORD,)), "JIRA链接"),
        ("TR-03", FactQuery(texts=(("软件相关FAIL", (_locator("软件相关FAIL"),)),)), "软件FAIL的JIRA/处理记录"),
        ("TR-04", FactQuery(labels=(("典型工作功耗", _locator("5W")),), kinds=(EvidenceKind.POWER_RECORD,)), "待机功耗"),
        ("TR-06", FactQuery(labels=(("测试需求", _locator()), ("能力限制", _locator()))), "委外安排"),
        ("TR-07", FactQuery(labels=(("报告版本", _locator()), ("项目", _locator())), kinds=(EvidenceKind.PUBLISHED_CRITERIA,)), "阶段"),
        ("TR-09", FactQuery(labels=(("机型", _locator()),), kinds=(EvidenceKind.REQUIREMENT_OR_CASE_MAPPING,)), "区域"),
        ("TR-10", FactQuery(texts=(("未执行项", (_locator("未执行项"),)),), kinds=(EvidenceKind.REQUIREMENT_OR_CASE_MAPPING,)), "未执行原因"),
        ("TR-12", FactQuery(labels=(("报告数据", _locator()), ("小结", _locator()))), "结论"),
        ("TR-13", FactQuery(labels=tuple((label, _locator()) for label in ("原始记录", "日志", "问题清单", "小结"))), "结论"),
        ("TR-14", FactQuery(labels=(("EMC适用性", _locator("适用")), ("EMC合格余量", _locator("3dB"))), kinds=(EvidenceKind.EMC_REPORT,)), "EMC异常JIRA记录"),
        ("TR-15", FactQuery(labels=(("当前阶段", _locator()),)), "以前阶段报告"),
        ("TR-17", FactQuery(labels=tuple((label, _locator()) for label in ("问题清单", "测试对象", "测试条件", "观察现象"))), "实际结果"),
        ("TR-18", FactQuery(labels=(("结论", _locator()),)), "问题清单"),
        ("TR-19", FactQuery(labels=(("CA卡工装温升测试适用性", _locator("适用")),), kinds=(EvidenceKind.TEMPERATURE_RECORD,)), "温升测试结果"),
        ("TR-20", FactQuery(labels=(("阶段", _locator("PP")),), kinds=(EvidenceKind.AUTOMATION_RECORD,)), "开关机自动化测试结果"),
        ("TR-21", FactQuery(labels=(("WIFI适用性", _locator("是")), ("WIFI小结论", _locator()))), "WIFI页面顶端结论"),
        ("TR-22", FactQuery(labels=(("温升部件喷漆适用性", _locator("适用")),), texts=(("CPU散热器喷漆状态", (_locator("CPU散热器喷漆状态"),)),), kinds=(EvidenceKind.TEMPERATURE_RECORD,)), "tuner屏蔽框喷漆状态照片/记录"),
    ],
)
def test_each_defined_objective_absence_is_a_traceable_hard_failure(rule_id, query, expected_missing) -> None:
    result = A11Engine().evaluate_rule(_review_input(query), rule_id)
    assert result.initial_status is ReviewStatus.NON_COMPLIANT
    assert expected_missing in result.missing_materials


def test_emc_margin_below_three_db_is_objective_failure_with_locator() -> None:
    margin = _locator("2.9dB")
    query = FactQuery(
        labels=(("EMC适用性", _locator("适用")), ("EMC合格余量", margin)),
        kinds=(EvidenceKind.EMC_REPORT, EvidenceKind.JIRA_RECORD),
    )
    result = A11Engine().evaluate_rule(_review_input(query), "TR-14")
    assert result.initial_status is ReviewStatus.NON_COMPLIANT
    assert margin in result.evidence_locators
    assert not result.missing_materials


@pytest.mark.parametrize("rule_id", ["TR-13", "TR-16", "TR-17", "TR-18"])
def test_ai_only_rules_never_return_rule_only_compliant(rule_id: str) -> None:
    evidence = _locator()
    query = FactQuery(
        labels=tuple((label, evidence) for label in ("原始记录", "日志", "问题清单", "小结", "结论", "测试对象", "测试条件", "观察现象", "实际结果")),
        kinds=(EvidenceKind.PUBLISHED_CRITERIA,),
    )
    assert _status(rule_id, query) is not ReviewStatus.COMPLIANT


def test_hard_failure_outranks_pending_semantics_and_keeps_both_diagnostics() -> None:
    evidence = _locator("2.5dB")
    query = FactQuery(labels=(("EMC适用性", _locator("适用")), ("EMC合格余量", evidence)), kinds=(EvidenceKind.EMC_REPORT,))
    result = A11Engine().evaluate_rule(_review_input(query), "TR-14")
    assert result.initial_status is ReviewStatus.NON_COMPLIANT
    assert result.evidence_locators
    assert result.missing_materials
    assert result.unresolved_semantics


def test_engine_returns_exactly_21_deterministic_ordered_results() -> None:
    review_input = _review_input(FactQuery())
    engine = A11Engine()
    first = engine.evaluate(review_input)
    second = engine.evaluate(review_input)

    assert [result.rule_id for result in first] == [f"TR-{number:02d}" for number in range(1, 23) if number != 5]
    assert len(first) == 21
    assert first == second
    assert all(result.task_id == review_input.task_id for result in first)
    assert all(result.active_revision_no == review_input.active_revision_no for result in first)
    assert all(result.created_at == review_input.evaluated_at for result in first)
    assert {result.baseline_version for result in first} == {"A11"}
    assert all(result.evidence_locators or result.missing_materials for result in first if result.initial_status is ReviewStatus.NON_COMPLIANT)
    assert all(result.unresolved_semantics for result in first if result.initial_status is ReviewStatus.NEEDS_REVIEW)
