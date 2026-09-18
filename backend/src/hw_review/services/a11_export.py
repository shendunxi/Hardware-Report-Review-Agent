"""Generate a filled legacy-XLS copy from one completed A11 revision snapshot."""

from __future__ import annotations

import io
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import xlrd
from xlutils.filter import XLRDReader, XLWTWriter, process

from hw_review.rules import A11Registry
from hw_review.domain import TaskState, TemplateRule
from hw_review.persistence import RepositoryNotFoundError
from hw_review.services.lifecycle import LifecycleError
from hw_review.services.template_binding import enabled_rules_for_task


CHECKLIST_SHEET = "硬件测试过程检查表"
FINAL_MARKS = {
    "COMPLIANT": ("√", "", ""),
    "NON_COMPLIANT": ("", "╳", ""),
    "NOT_APPLICABLE": ("", "", "⊙"),
}

_LEGACY_REVIEW_TEXT_TRANSLATIONS = (
    ("All checks in this source row are explicitly proven not applicable.", "本检查表来源行中的所有校验项均已有明确证据证明不适用。"),
    ("A required material is missing or an objective check has failed.", "缺少必需材料，或某项客观校验未通过。"),
    ("No hard failure was found, but a semantic obligation remains unresolved.", "未发现确定性不符合项，但仍有语义判断事项待确认。"),
    ("Every applicable deterministic obligation is positively evidenced.", "所有适用的客观校验项均已有明确证据证明符合。"),
    (" Atomic bases: ", "判定明细代码："),
    ("JIRA link legality cannot be proven by literal rule matching.", "仅通过文字规则匹配无法证明 JIRA 链接有效性。"),
    ("Issue, status, and regression correspondence requires semantic review.", "问题、状态与回归记录的对应关系需要语义审核。"),
    ("Review closure and manager notification correspondence require semantic review.", "问题闭环与经理通知的对应关系需要语义审核。"),
    ("Adequacy of the limitation reason and outsourcing arrangement requires semantic review.", "能力限制原因及委外安排是否充分需要语义审核。"),
    ("Published report naming/version criteria were not supplied; no criterion is invented.", "未提供已发布的报告命名/版本标准；系统不会自行推断标准。"),
    ("Comparison with the supplied naming/version criterion requires semantic review.", "与已提供的命名/版本标准进行比对需要语义审核。"),
    ("The published homepage required-field list was not supplied; field names are not invented.", "未提供已发布的首页必填字段清单；系统不会自行推断字段名。"),
    ("Published criteria are present, but a traceable homepage required-field list cannot be read.", "已提供发布标准，但无法读取可追溯的首页必填字段清单。"),
    ("The homepage required-field list contains no traceable field names.", "首页必填字段清单中没有可追溯的字段名。"),
    ("Homepage-to-body consistency requires semantic review.", "首页与正文的一致性需要语义审核。"),
    ("The model/region/standard/use-case mapping was not supplied; no mapping is invented.", "未提供机型/区域/标准/使用场景映射；系统不会自行推断映射关系。"),
    ("Mandatory-case coverage against the supplied mapping requires semantic review.", "根据已提供映射核对应测用例覆盖情况需要语义审核。"),
    ("Completeness against the supplied required-item checklist requires semantic review.", "根据已提供的应测项清单核对完整性需要语义审核。"),
    ("Cross-record numeric equality requires semantic review.", "不同记录之间的数值一致性需要语义审核。"),
    ("Data, summary, and conclusion consistency requires semantic review.", "数据、小结和结论的一致性需要语义审核。"),
    ("No-omission and no-summary-loss judgment requires LLM or manual review.", "是否存在遗漏或小结信息丢失需要大语言模型或人工审核。"),
    ("EMC anomaly and JIRA correspondence requires semantic review.", "EMC 异常与 JIRA 记录的对应关系需要语义审核。"),
    ("Unexplained conclusion conflicts across stages require semantic review.", "跨阶段存在的未解释结论冲突需要语义审核。"),
    ("Published ordering criteria were not supplied; no severity or ordering rule is invented.", "未提供已发布的排序标准；系统不会自行推断问题分级或排序规则。"),
    ("Emphasis and ordering against the supplied criteria require LLM or manual review.", "依据已提供标准核对强调内容和排序需要大语言模型或人工审核。"),
    ("Adequacy of the four fixed problem elements requires LLM or manual review.", "四个固定问题要素是否描述充分需要大语言模型或人工审核。"),
    ("Whether each conclusion expresses one independently actionable issue requires LLM or manual review.", "每条结论是否仅描述一个可独立处理的问题，需要大语言模型或人工审核。"),
    ("The published coating expectation was not supplied; no expected state is invented.", "未提供已发布的喷漆状态要求；系统不会自行推断预期状态。"),
    ("Comparison with the supplied coating expectation requires semantic review.", "与已提供的喷漆状态要求进行比对需要语义审核。"),
)


def _localize_legacy_review_text(value: object) -> str:
    text = str(value or "")
    for source, translation in _LEGACY_REVIEW_TEXT_TRANSLATIONS:
        text = text.replace(source, translation)
    marker = "判定明细代码："
    if marker in text:
        summary, codes = text.split(marker, 1)
        text = f"{summary}{marker}{codes.replace(', ', '、').removesuffix('.')}。"
    return text


class ChecklistExportError(Exception):
    """Stable export failure that can be mapped at the application boundary."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ChecklistArtifact:
    """One immutable HTTP-ready legacy-XLS export."""

    filename: str
    content: bytes


class A11ChecklistExportService:
    """Load the latest immutable completion snapshot and render its checklist."""

    def __init__(self, bundle, writer: "A11ChecklistWriter") -> None:
        self._bundle = bundle
        self._writer = writer

    def export(self, task_id: UUID) -> ChecklistArtifact:
        try:
            task = self._bundle.tasks.get(task_id)
            revisions = self._bundle.revisions.list_for_task(task_id)
        except RepositoryNotFoundError as error:
            raise LifecycleError("TASK_NOT_FOUND", "task was not found") from error
        if task.state is not TaskState.COMPLETED:
            raise LifecycleError(
                "INVALID_TASK_STATE",
                "checklist export requires a completed task",
                {"state": task.state.value},
            )
        if not revisions:
            raise LifecycleError(
                "EXPORT_REVISION_NOT_FOUND", "completed task has no review revision"
            )
        revision = max(revisions, key=lambda item: item.revision_no)
        try:
            rules = enabled_rules_for_task(task)
            content = self._writer.render(
                revision.result_snapshot,
                template_path=task.template_source_path,
                template_version=task.template_version,
                rules=rules,
                expected_sha256=task.template_source_sha256,
            )
        except ChecklistExportError as error:
            raise LifecycleError(error.code, str(error)) from error
        stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", Path(task.display_name).stem)
        stem = stem.strip(" ._") or "hardware-test-report"
        return ChecklistArtifact(
            filename=f"{stem}_{task.template_version}_R{revision.revision_no}.xls",
            content=content,
        )


class A11ChecklistWriter:
    """Copy an A11 template and fill only enabled rule rows in columns D:G."""

    def __init__(self, template_path: Path) -> None:
        self._template_path = Path(template_path)

    def render(
        self,
        snapshot: str,
        *,
        template_path: Path | None = None,
        template_version: str = "A11",
        rules: tuple[TemplateRule, ...] | None = None,
        expected_sha256: str | None = None,
    ) -> bytes:
        payload = self._parse_snapshot(snapshot)
        selected_path = Path(template_path) if template_path is not None else self._template_path
        selected_rules = tuple(rule for rule in (rules or ()) if rule.enabled)
        if rules is None:
            selected_rules = tuple(
                TemplateRule(
                    id=UUID(int=index + 1),
                    template_id=UUID(int=0),
                    rule_id=rule.id,
                    source_row=rule.source_row,
                    source_sequence=rule.source_sequence,
                    summary=rule.summary,
                    verifiable_requirement=rule.verifiable_requirement,
                    required_materials=rule.required_materials,
                    main_judgment=rule.main_judgment,
                    confirmed_boundary=rule.confirmed_boundary,
                    enabled=rule.enabled,
                    created_at="1970-01-01T00:00:00Z",
                    updated_at="1970-01-01T00:00:00Z",
                )
                for index, rule in enumerate(A11Registry.executed_rules())
            )
        source_book, source_sheet = self._open_template(selected_path, expected_sha256)
        self._validate_template(source_sheet, template_version, selected_rules)
        rows = self._resolve_rows(payload, {rule.rule_id for rule in selected_rules})

        writer = XLWTWriter()
        process(XLRDReader(source_book, selected_path.name), writer)
        destination = writer.output[0][1]
        sheet_index = source_book.sheet_names().index(CHECKLIST_SHEET)
        destination_sheet = destination.get_sheet(sheet_index)
        append_row = source_sheet.nrows
        for rule in selected_rules:
            final_status, note = rows[rule.rule_id]
            if rule.source_row is None:
                row_index = append_row
                append_row += 1
                destination_sheet.write(row_index, 1, rule.source_sequence)
                destination_sheet.write(row_index, 2, rule.summary)
                for offset, value in enumerate(FINAL_MARKS[final_status], start=3):
                    destination_sheet.write(row_index, offset, value)
                destination_sheet.write(row_index, 6, note)
                continue
            row_index = rule.source_row - 1
            for offset, value in enumerate(FINAL_MARKS[final_status], start=3):
                style = writer.style_list[source_sheet.cell_xf_index(row_index, offset)]
                destination_sheet.write(row_index, offset, value, style)
            note_style = writer.style_list[source_sheet.cell_xf_index(row_index, 6)]
            destination_sheet.write(row_index, 6, note, note_style)

        output = io.BytesIO()
        destination.save(output)
        return output.getvalue()

    def _open_template(self, template_path: Path, expected_sha256: str | None):
        if not template_path.is_file():
            raise ChecklistExportError(
                "TEMPLATE_NOT_FOUND", "任务绑定的审核模板不存在"
            )
        if expected_sha256 is not None:
            actual_hash = hashlib.sha256(template_path.read_bytes()).hexdigest()
            if actual_hash != expected_sha256.lower():
                raise ChecklistExportError("TEMPLATE_CHANGED", "任务绑定的审核模板内容已改变")
        try:
            book = xlrd.open_workbook(
                template_path, formatting_info=True, on_demand=False
            )
        except (OSError, xlrd.XLRDError) as error:
            raise ChecklistExportError(
                "TEMPLATE_INVALID", "A11审核模板无法读取"
            ) from error
        if book.sheet_names().count(CHECKLIST_SHEET) != 1:
            raise ChecklistExportError(
                "TEMPLATE_STRUCTURE_MISMATCH",
                "A11审核模板必须且只能包含一个硬件测试过程检查表",
            )
        return book, book.sheet_by_name(CHECKLIST_SHEET)

    @staticmethod
    def _validate_template(sheet, template_version: str, rules: tuple[TemplateRule, ...]) -> None:
        if sheet.nrows < 2 or str(sheet.cell_value(1, 0)).strip() != template_version:
            raise ChecklistExportError(
                "TEMPLATE_VERSION_MISMATCH", f"审核模板版本必须为{template_version}"
            )
        if sheet.ncols < 7:
            raise ChecklistExportError(
                "TEMPLATE_STRUCTURE_MISMATCH", "A11审核模板缺少D至G列"
            )
        for rule in rules:
            if rule.source_row is None:
                continue
            row_index = rule.source_row - 1
            if row_index >= sheet.nrows:
                raise ChecklistExportError(
                    "TEMPLATE_STRUCTURE_MISMATCH",
                    f"审核模板缺少源行{rule.source_row}",
                )
            value = sheet.cell_value(row_index, 1)
            try:
                sequence = int(float(value))
            except (TypeError, ValueError) as error:
                raise ChecklistExportError(
                    "TEMPLATE_STRUCTURE_MISMATCH",
                    f"审核模板第{rule.source_row}行序号无效",
                ) from error
            if sequence != rule.source_sequence:
                raise ChecklistExportError(
                    "TEMPLATE_STRUCTURE_MISMATCH",
                    f"审核模板第{rule.source_row}行序号与冻结规则不一致",
                )

    @staticmethod
    def _parse_snapshot(snapshot: str) -> dict[str, Any]:
        try:
            payload = json.loads(snapshot)
        except (TypeError, json.JSONDecodeError) as error:
            raise ChecklistExportError(
                "EXPORT_SNAPSHOT_INVALID", "审核修订快照不是有效JSON"
            ) from error
        if not isinstance(payload, dict):
            raise ChecklistExportError(
                "EXPORT_SNAPSHOT_INVALID", "审核修订快照结构无效"
            )
        return payload

    @classmethod
    def _resolve_rows(
        cls,
        payload: dict[str, Any],
        expected_ids: set[str] | None = None,
    ) -> dict[str, tuple[str, str]]:
        results = payload.get("results")
        decisions = payload.get("decisions")
        if not isinstance(results, list) or not isinstance(decisions, list):
            raise ChecklistExportError(
                "EXPORT_SNAPSHOT_INVALID", "审核修订快照缺少结果或人工判定"
            )
        expected_ids = expected_ids or {rule.id for rule in A11Registry.executed_rules()}
        result_by_rule = {
            item.get("rule_id"): item for item in results if isinstance(item, dict)
        }
        if set(result_by_rule) != expected_ids or len(result_by_rule) != len(results):
            raise ChecklistExportError(
                "EXPORT_SNAPSHOT_INVALID", "审核修订快照必须与任务冻结的启用规则集合一致"
            )
        decision_by_result: dict[str, dict[str, Any]] = {}
        for decision in decisions:
            if not isinstance(decision, dict):
                raise ChecklistExportError(
                    "EXPORT_SNAPSHOT_INVALID", "人工判定结构无效"
                )
            result_id = decision.get("rule_result_id")
            if not isinstance(result_id, str) or result_id in decision_by_result:
                raise ChecklistExportError(
                    "EXPORT_SNAPSHOT_INVALID", "人工判定未唯一关联规则结果"
                )
            decision_by_result[result_id] = decision

        rows: dict[str, tuple[str, str]] = {}
        known_result_ids = {item.get("id") for item in result_by_rule.values()}
        if not set(decision_by_result).issubset(known_result_ids):
            raise ChecklistExportError(
                "EXPORT_SNAPSHOT_INVALID", "人工判定引用了非当前修订结果"
            )
        for rule_id, result in result_by_rule.items():
            decision = decision_by_result.get(result.get("id"))
            final_status = (
                decision.get("final_status") if decision else result.get("initial_status")
            )
            if final_status not in FINAL_MARKS:
                raise ChecklistExportError(
                    "EXPORT_SNAPSHOT_INVALID",
                    f"{rule_id}没有可导出的最终状态",
                )
            if decision and not str(decision.get("reason") or "").strip():
                raise ChecklistExportError(
                    "EXPORT_SNAPSHOT_INVALID", f"{rule_id}的人工修改原因为空"
                )
            rows[rule_id] = (final_status, cls._build_note(result, decision))
        return rows

    @staticmethod
    def _build_note(result: dict[str, Any], decision: dict[str, Any] | None) -> str:
        sections = []
        basis = _localize_legacy_review_text(result.get("basis_text")).strip()
        if basis:
            sections.append(f"系统判定依据：{basis}")
        evidence_items = []
        evidence_keys: set[tuple[str, str, str, str]] = set()
        for locator in result.get("evidence_locators") or []:
            if not isinstance(locator, dict):
                continue
            quote = str(locator.get("quoted_text") or "").strip()
            if len(quote) > 160:
                quote = f"{quote[:159]}…"
            key = (
                str(locator.get("source_file_id") or "").strip(),
                str(locator.get("container") or "").strip(),
                str(locator.get("structural_address") or "").strip(),
                quote,
            )
            if key in evidence_keys:
                continue
            evidence_keys.add(key)
            values = key
            text = " | ".join(str(value).strip() for value in values if value)
            if text:
                evidence_items.append(text)
        if evidence_items:
            visible_items = evidence_items[:50]
            evidence_text = " 、".join(visible_items)
            hidden_count = len(evidence_items) - len(visible_items)
            if hidden_count:
                evidence_text += f"；其余{hidden_count}条证据见系统审核记录"
            sections.append(f"可追溯证据：{evidence_text}")
        missing = [str(item).strip() for item in result.get("missing_materials") or [] if str(item).strip()]
        if missing:
            sections.append(f"缺失材料：{'、'.join(missing)}")
        unresolved = [
            _localize_legacy_review_text(item).strip()
            for item in result.get("unresolved_semantics") or []
            if str(item).strip()
        ]
        if unresolved:
            sections.append(f"系统未决事项：{'、'.join(unresolved)}")
        if decision:
            sections.append(f"人工修改原因：{str(decision['reason']).strip()}")
        note = "；".join(sections)
        if len(note) > 32767:
            raise ChecklistExportError(
                "EXPORT_CELL_TOO_LONG", "导出说明超过XLS单元格长度限制"
            )
        return note
