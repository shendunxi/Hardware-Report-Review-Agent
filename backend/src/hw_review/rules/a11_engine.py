"""Deterministic evidence query, A11 atomic checks, and row roll-up."""

from __future__ import annotations

import re
from collections.abc import Iterable
from uuid import NAMESPACE_URL, uuid5

from hw_review.domain.enums import EvidenceKind, FileRole, ReviewStatus
from hw_review.domain.models import (
    AtomicResult,
    EvidenceLocator,
    ReviewInput,
    ReviewSource,
    RuleResult,
)
from hw_review.domain.ports import DocumentQuery

from .a11_registry import A11Registry


ENGINE_VERSION = "a11-engine-2"


def _locator_identity(locator: EvidenceLocator) -> tuple[object, ...]:
    return (
        locator.source_file_id,
        locator.container,
        locator.structural_address,
        locator.bbox,
        locator.quoted_text,
        locator.content_hash,
    )


def _unique(items: Iterable[object]) -> tuple:
    result = []
    seen = set()
    for item in items:
        key = _locator_identity(item) if isinstance(item, EvidenceLocator) else item
        if key not in seen:
            seen.add(key)
            result.append(item)
    return tuple(result)


def rollup(atoms: tuple[AtomicResult, ...]) -> AtomicResult:
    """Aggregate atoms without discarding diagnostics from lower-priority atoms."""

    if not atoms:
        raise ValueError("rollup requires at least one atom")

    statuses = tuple(atom.status for atom in atoms)
    if all(status is ReviewStatus.NOT_APPLICABLE for status in statuses):
        status = ReviewStatus.NOT_APPLICABLE
        code = "ROLLUP_ALL_NOT_APPLICABLE"
        text = "本检查表来源行中的所有校验项均已有明确证据证明不适用。"
    elif any(status is ReviewStatus.NON_COMPLIANT for status in statuses):
        status = ReviewStatus.NON_COMPLIANT
        code = "ROLLUP_HARD_FAILURE"
        text = "缺少必需材料，或某项客观校验未通过。"
    elif any(status is ReviewStatus.NEEDS_REVIEW for status in statuses):
        status = ReviewStatus.NEEDS_REVIEW
        code = "ROLLUP_UNRESOLVED_SEMANTICS"
        text = "未发现确定性不符合项，但仍有语义判断事项待确认。"
    else:
        status = ReviewStatus.COMPLIANT
        code = "ROLLUP_ALL_APPLICABLE_COMPLIANT"
        text = "所有适用的客观校验项均已有明确证据证明符合。"

    selected_codes = _unique(
        atom.basis_code
        for atom in atoms
        if atom.status is status
        or (
            status is ReviewStatus.COMPLIANT
            and atom.status is ReviewStatus.NOT_APPLICABLE
        )
    )
    if selected_codes:
        text = f"{text}判定明细代码：{'、'.join(selected_codes)}。"

    return AtomicResult(
        status=status,
        basis_code=code,
        basis_text=text,
        evidence=_unique(locator for atom in atoms for locator in atom.evidence),
        missing_materials=_unique(
            material for atom in atoms for material in atom.missing_materials
        ),
        unresolved_semantics=_unique(
            reason for atom in atoms for reason in atom.unresolved_semantics
        ),
    )


class NormalizedDocumentQuery:
    """Conservative literal query over ordered normalized documents."""

    def __init__(self, sources: tuple[ReviewSource, ...]):
        self._sources = sources

    @staticmethod
    def _container_name(source_container) -> str:
        if source_container.kind == "sheet":
            return (
                f"sheet:{source_container.order}:"
                f"{source_container.name_or_number}"
            )
        return f"page:{source_container.order}"

    @staticmethod
    def _locator(source_file_id, container, structural_address, text, content_hash, bbox=None):
        return EvidenceLocator(
            source_file_id=source_file_id,
            container=container,
            structural_address=structural_address,
            bbox=bbox,
            quoted_text=text if text != "" else None,
            content_hash=content_hash,
        )

    def _text_items(self):
        for source in self._sources:
            for container in source.document.containers:
                container_name = self._container_name(container)
                for block in container.blocks:
                    if block.kind == "table":
                        for cell in block.cells:
                            yield (
                                source.source_file.id,
                                container_name,
                                cell.structural_address,
                                cell.display_value,
                                cell.content_hash,
                                None,
                            )
                    elif block.text is not None:
                        yield (
                            source.source_file.id,
                            container_name,
                            block.structural_address,
                            block.text,
                            block.content_hash,
                            block.bbox,
                        )

    def find_text(self, patterns: tuple[str, ...]) -> tuple[EvidenceLocator, ...]:
        folded = tuple(pattern.casefold() for pattern in patterns if pattern)
        found = []
        for item in self._text_items():
            text = item[3]
            if any(pattern in text.casefold() for pattern in folded):
                found.append(self._locator(*item))
        return _unique(found)

    def find_nonempty_labels(
        self, labels: tuple[str, ...]
    ) -> dict[str, EvidenceLocator]:
        wanted = {label.casefold(): label for label in labels}
        found: dict[str, EvidenceLocator] = {}
        for source in self._sources:
            for container in source.document.containers:
                container_name = self._container_name(container)
                for block in container.blocks:
                    if block.kind == "table":
                        by_coordinate = {
                            (cell.row, cell.column): cell for cell in block.cells
                        }
                        for cell in block.cells:
                            label = wanted.get(cell.display_value.strip().casefold())
                            if label is None or label in found:
                                continue
                            value = by_coordinate.get((cell.row, cell.column + 1))
                            if value is not None and value.display_value.strip():
                                found[label] = self._locator(
                                    source.source_file.id,
                                    container_name,
                                    value.structural_address,
                                    value.display_value,
                                    value.content_hash,
                                )
                    elif block.text:
                        for raw_line in block.text.splitlines():
                            for folded_label, label in wanted.items():
                                if label in found:
                                    continue
                                for separator in (":", "："):
                                    prefix = f"{label}{separator}"
                                    if raw_line.casefold().startswith(prefix.casefold()):
                                        value = raw_line[len(prefix) :].strip()
                                        if value:
                                            found[label] = self._locator(
                                                source.source_file.id,
                                                container_name,
                                                block.structural_address,
                                                value,
                                                block.content_hash,
                                                block.bbox,
                                            )
        return found

    def has_evidence_kind(self, kind: EvidenceKind) -> bool:
        return any(
            source.source_file.role is FileRole.SUPPORTING_EVIDENCE
            and kind in source.source_file.evidence_kinds
            for source in self._sources
        )


def _atom(
    status: ReviewStatus,
    code: str,
    text: str,
    *,
    evidence: Iterable[EvidenceLocator] = (),
    missing: Iterable[str] = (),
    unresolved: Iterable[str] = (),
) -> AtomicResult:
    return AtomicResult(
        status=status,
        basis_code=code,
        basis_text=text,
        evidence=tuple(evidence),
        missing_materials=tuple(missing),
        unresolved_semantics=tuple(unresolved),
    )


def _pass(code: str, text: str, evidence=()) -> AtomicResult:
    return _atom(ReviewStatus.COMPLIANT, code, text, evidence=evidence)


def _missing(code: str, material: str, evidence=()) -> AtomicResult:
    return _atom(
        ReviewStatus.NON_COMPLIANT,
        code,
        f"缺少必需材料：{material}。",
        evidence=evidence,
        missing=(material,),
    )


def _pending(code: str, reason: str, evidence=()) -> AtomicResult:
    return _atom(
        ReviewStatus.NEEDS_REVIEW,
        code,
        reason,
        evidence=evidence,
        unresolved=(reason,),
    )


def _na(code: str, text: str, evidence) -> AtomicResult:
    return _atom(ReviewStatus.NOT_APPLICABLE, code, text, evidence=evidence)


def _labels(query: DocumentQuery, labels: tuple[str, ...]) -> tuple[dict[str, EvidenceLocator], list[AtomicResult]]:
    found = query.find_nonempty_labels(labels)
    atoms = []
    for label in labels:
        if label in found:
            atoms.append(_pass(f"FIELD_{label}_PRESENT", f"字段“{label}”已填写。", (found[label],)))
        else:
            label_occurrences = query.find_text((label,))
            atoms.append(_missing(f"FIELD_{label}_MISSING", label, label_occurrences))
    return found, atoms


def _kind(query: DocumentQuery, kind: EvidenceKind, material: str) -> AtomicResult:
    if query.has_evidence_kind(kind):
        return _pass(f"EVIDENCE_{kind.value}_PRESENT", f"已明确标注并提供材料：{material}。")
    return _missing(f"EVIDENCE_{kind.value}_MISSING", material)


def _explicit_text(query: DocumentQuery, phrase: str) -> tuple[EvidenceLocator, ...]:
    return query.find_text((phrase,))


def _explicit_non_applicable_label(
    query: DocumentQuery, label: str
) -> tuple[EvidenceLocator, ...]:
    locator = query.find_nonempty_labels((label,)).get(label)
    if locator is None:
        return ()
    value = (locator.quoted_text or "").strip().casefold()
    if value in {"无", "否", "不适用", "no", "not applicable"}:
        return (locator,)
    return ()


def _declared_field_names(locator: EvidenceLocator) -> tuple[str, ...]:
    return _unique(
        value.strip()
        for value in re.split(r"[、,，;；\n]+", locator.quoted_text or "")
        if value.strip()
    )


class A11Engine:
    """Evaluate the 21 enabled A11 rows without LLM or inferred policy."""

    def evaluate(self, review_input: ReviewInput) -> tuple[RuleResult, ...]:
        return tuple(
            self.evaluate_rule(review_input, definition.id)
            for definition in A11Registry.executed_rules()
        )

    def evaluate_rule(self, review_input: ReviewInput, rule_id: str) -> RuleResult:
        definition = A11Registry.get(rule_id)
        if not definition.enabled:
            raise ValueError(f"disabled A11 rule cannot be evaluated: {rule_id}")
        handler = getattr(self, f"_rule_{rule_id[3:]}")
        aggregate = rollup(tuple(handler(review_input.query)))
        result_id = uuid5(
            NAMESPACE_URL,
            f"{review_input.task_id}:{review_input.active_revision_no}:"
            f"{rule_id}:{ENGINE_VERSION}:{definition.baseline_version}",
        )
        return RuleResult(
            id=result_id,
            task_id=review_input.task_id,
            rule_id=rule_id,
            initial_status=aggregate.status,
            basis_code=aggregate.basis_code,
            basis_text=aggregate.basis_text,
            evidence_locators=aggregate.evidence,
            missing_materials=aggregate.missing_materials,
            unresolved_semantics=aggregate.unresolved_semantics,
            engine_version=ENGINE_VERSION,
            baseline_version=definition.baseline_version,
            active_revision_no=review_input.active_revision_no,
            created_at=review_input.evaluated_at,
        )

    def _rule_01(self, query):
        yield _kind(query, EvidenceKind.JIRA_RECORD, "JIRA页面截图/导出件")
        _, atoms = _labels(query, ("JIRA链接",))
        yield from atoms
        yield _pending("JIRA_LINK_LEGALITY_UNRESOLVED", "仅通过文字规则匹配无法证明 JIRA 链接有效性。")

    def _rule_02(self, query):
        yield _kind(query, EvidenceKind.PREVIOUS_STAGE_REPORT, "上阶段问题清单、状态、回归记录")
        yield _pending("PREVIOUS_STAGE_CORRESPONDENCE_UNRESOLVED", "问题、状态与回归记录的对应关系需要语义审核。")

    def _rule_03(self, query):
        no_fail = _explicit_text(query, "软件相关FAIL：无") or _explicit_non_applicable_label(query, "软件相关FAIL")
        if no_fail:
            yield _na("SOFTWARE_FAIL_NOT_APPLICABLE", "明确证据表明不存在软件相关 FAIL。", no_fail)
            return
        fail = _explicit_text(query, "软件相关FAIL")
        if not fail:
            yield _missing(
                "SOFTWARE_FAIL_BASIS_MISSING",
                "软件FAIL清单或明确无FAIL依据",
            )
            return
        yield _pass("SOFTWARE_FAIL_PRESENT", "已明确说明软件相关 FAIL 的适用情况。", fail)
        yield _kind(query, EvidenceKind.JIRA_RECORD, "软件FAIL的JIRA/处理记录")
        _, atoms = _labels(query, ("处理说明",))
        yield from atoms
        yield _pending("SOFTWARE_FAIL_CLOSURE_UNRESOLVED", "问题闭环与经理通知的对应关系需要语义审核。")

    def _rule_04(self, query):
        _, atoms = _labels(query, ("典型工作功耗", "待机功耗"))
        yield from atoms
        yield _kind(query, EvidenceKind.POWER_RECORD, "共享功耗记录导出件/截图")

    def _rule_06(self, query):
        no_limit = _explicit_text(query, "内部能力限制：无") or _explicit_non_applicable_label(query, "内部能力限制")
        if no_limit:
            yield _na("NO_INTERNAL_LIMITATION", "明确证据表明不存在内部能力限制。", no_limit)
            return
        _, atoms = _labels(query, ("测试需求", "能力限制", "委外安排"))
        yield from atoms
        yield _pending("OUTSOURCING_ADEQUACY_UNRESOLVED", "能力限制原因及委外安排是否充分需要语义审核。")

    def _rule_07(self, query):
        _, atoms = _labels(query, ("报告版本", "项目", "阶段"))
        yield from atoms
        if not query.has_evidence_kind(EvidenceKind.PUBLISHED_CRITERIA):
            yield _pending("NAMING_CRITERION_ABSENT", "未提供已发布的报告命名/版本标准；系统不会自行推断标准。")
        else:
            yield _pending("NAMING_COMPARISON_UNRESOLVED", "与已提供的命名/版本标准进行比对需要语义审核。")

    def _rule_08(self, query):
        if not query.has_evidence_kind(EvidenceKind.PUBLISHED_CRITERIA):
            yield _pending("HOMEPAGE_FIELD_LIST_ABSENT", "未提供已发布的首页必填字段清单；系统不会自行推断字段名。")
            return
        list_lookup = query.find_nonempty_labels(("首页必填字段清单",))
        list_evidence = list_lookup.get("首页必填字段清单")
        if list_evidence is None:
            yield _pending("HOMEPAGE_FIELD_LIST_UNREADABLE", "已提供发布标准，但无法读取可追溯的首页必填字段清单。")
            return
        field_names = _declared_field_names(list_evidence)
        if not field_names:
            yield _pending("HOMEPAGE_FIELD_LIST_UNREADABLE", "首页必填字段清单中没有可追溯的字段名。", (list_evidence,))
            return
        filled = query.find_nonempty_labels(field_names)
        for field_name in field_names:
            if field_name in filled:
                yield _pass(f"HOMEPAGE_FIELD_{field_name}_PRESENT", f"已声明的首页字段“{field_name}”已填写。", (filled[field_name],))
            else:
                yield _missing(f"HOMEPAGE_FIELD_{field_name}_MISSING", f"首页必填字段：{field_name}", (list_evidence,))
        yield _pending("HOMEPAGE_BODY_CONSISTENCY_UNRESOLVED", "首页与正文的一致性需要语义审核。")

    def _rule_09(self, query):
        if not query.has_evidence_kind(EvidenceKind.REQUIREMENT_OR_CASE_MAPPING):
            yield _pending("CASE_MAPPING_ABSENT", "未提供机型/区域/标准/使用场景映射；系统不会自行推断映射关系。")
            return
        _, atoms = _labels(query, ("机型", "区域"))
        yield from atoms
        yield _pending("MANDATORY_CASE_MAPPING_UNRESOLVED", "根据已提供映射核对应测用例覆盖情况需要语义审核。")

    def _rule_10(self, query):
        yield _kind(query, EvidenceKind.REQUIREMENT_OR_CASE_MAPPING, "应测项清单/用例")
        declared_lookup = query.find_nonempty_labels(("必填数据清单",))
        declared_evidence = declared_lookup.get("必填数据清单")
        if declared_evidence is not None:
            declared_fields = _declared_field_names(declared_evidence)
            filled = query.find_nonempty_labels(declared_fields)
            for field_name in declared_fields:
                if field_name in filled:
                    yield _pass(
                        f"REQUIRED_DATA_{field_name}_PRESENT",
                        f"已声明的必填数据字段“{field_name}”已填写。",
                        (filled[field_name],),
                    )
                else:
                    yield _missing(
                        f"REQUIRED_DATA_{field_name}_MISSING",
                        f"必填数据：{field_name}",
                        (declared_evidence,),
                    )
        unexecuted = _explicit_text(query, "未执行项")
        explicitly_none = _explicit_non_applicable_label(query, "未执行项")
        if unexecuted and not explicitly_none:
            reasons = query.find_nonempty_labels(("未执行原因",))
            if "未执行原因" not in reasons:
                yield _missing("UNEXECUTED_REASON_MISSING", "未执行原因", unexecuted)
        yield _pending("TEST_COMPLETENESS_UNRESOLVED", "根据已提供的应测项清单核对完整性需要语义审核。")

    def _rule_11(self, query):
        yield _kind(query, EvidenceKind.PAPER_RECORD, "纸质记录扫描件/照片")
        declared_lookup = query.find_nonempty_labels(("数值字段清单",))
        declared_evidence = declared_lookup.get("数值字段清单")
        if declared_evidence is not None:
            declared_fields = _declared_field_names(declared_evidence)
            values = query.find_nonempty_labels(declared_fields)
            for field_name in declared_fields:
                value = values.get(field_name)
                if value is None:
                    yield _missing(
                        f"NUMERIC_FIELD_{field_name}_MISSING",
                        f"数值字段：{field_name}",
                        (declared_evidence,),
                    )
                elif re.search(
                    r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", value.quoted_text or ""
                ) is None:
                    yield _atom(
                        ReviewStatus.NON_COMPLIANT,
                        "NUMERIC_FORMAT_INVALID",
                        f"已声明的数值字段“{field_name}”不包含可解析的十进制数值。",
                        evidence=(value,),
                    )
                else:
                    yield _pass(
                        f"NUMERIC_FIELD_{field_name}_PARSEABLE",
                        f"已声明的数值字段“{field_name}”包含可解析的十进制数值。",
                        (value,),
                    )
        yield _pending("PAPER_RECORD_EQUALITY_UNRESOLVED", "不同记录之间的数值一致性需要语义审核。")

    def _rule_12(self, query):
        _, atoms = _labels(query, ("报告数据", "小结", "结论"))
        yield from atoms
        yield _pending("SUMMARY_CONCLUSION_CONSISTENCY_UNRESOLVED", "数据、小结和结论的一致性需要语义审核。")

    def _rule_13(self, query):
        _, atoms = _labels(query, ("原始记录", "日志", "问题清单", "小结", "结论"))
        yield from atoms
        yield _pending("NO_OMISSION_UNRESOLVED", "是否存在遗漏或小结信息丢失需要大语言模型或人工审核。")

    def _rule_14(self, query):
        not_applicable = _explicit_text(query, "EMC适用性：不适用") or _explicit_non_applicable_label(query, "EMC适用性")
        if not_applicable:
            yield _na("EMC_NOT_APPLICABLE", "明确证据表明 EMC 不适用。", not_applicable)
            return
        found, atoms = _labels(query, ("EMC适用性", "EMC合格余量"))
        yield from atoms
        yield _kind(query, EvidenceKind.EMC_REPORT, "EMC报告")
        yield _kind(query, EvidenceKind.JIRA_RECORD, "EMC异常JIRA记录")
        margin = found.get("EMC合格余量")
        if margin is not None:
            match = re.search(r"[-+]?\d+(?:\.\d+)?", margin.quoted_text or "")
            if match is None:
                yield _missing("EMC_MARGIN_FORMAT_INVALID", "可解析的EMC合格余量", (margin,))
            elif float(match.group()) < 3:
                yield _atom(ReviewStatus.NON_COMPLIANT, "EMC_MARGIN_BELOW_3DB", "已有证据中的 EMC 余量低于 3 dB。", evidence=(margin,))
            else:
                yield _pass("EMC_MARGIN_AT_LEAST_3DB", "已有证据中的 EMC 余量不低于 3 dB。", (margin,))
        yield _pending("EMC_ANOMALY_CORRESPONDENCE_UNRESOLVED", "EMC 异常与 JIRA 记录的对应关系需要语义审核。")

    def _rule_15(self, query):
        _, atoms = _labels(query, ("当前阶段",))
        yield from atoms
        yield _kind(query, EvidenceKind.PREVIOUS_STAGE_REPORT, "以前阶段报告")
        yield _pending("STAGE_CONFLICT_UNRESOLVED", "跨阶段存在的未解释结论冲突需要语义审核。")

    def _rule_16(self, query):
        if not query.has_evidence_kind(EvidenceKind.PUBLISHED_CRITERIA):
            reason = "未提供已发布的排序标准；系统不会自行推断问题分级或排序规则。"
        else:
            reason = "依据已提供标准核对强调内容和排序需要大语言模型或人工审核。"
        yield _pending("CONCLUSION_ORDER_UNRESOLVED", reason)

    def _rule_17(self, query):
        _, atoms = _labels(query, ("问题清单", "测试对象", "测试条件", "观察现象", "实际结果"))
        yield from atoms
        yield _pending("PROBLEM_DESCRIPTION_ADEQUACY_UNRESOLVED", "四个固定问题要素是否描述充分需要大语言模型或人工审核。")

    def _rule_18(self, query):
        _, atoms = _labels(query, ("结论", "问题清单"))
        yield from atoms
        yield _pending("SINGLE_ACTIONABLE_ISSUE_UNRESOLVED", "每条结论是否仅描述一个可独立处理的问题，需要大语言模型或人工审核。")

    def _rule_19(self, query):
        not_applicable = _explicit_text(query, "CA卡工装温升测试：不适用") or _explicit_non_applicable_label(query, "CA卡工装温升测试适用性")
        if not_applicable:
            yield _na("CA_TEMPERATURE_NOT_APPLICABLE", "明确证据表明 CA 卡工装温升测试不适用。", not_applicable)
            return
        _, atoms = _labels(query, ("CA卡工装温升测试适用性", "温升测试结果"))
        yield from atoms
        yield _kind(query, EvidenceKind.TEMPERATURE_RECORD, "CA卡工装温升记录")

    def _rule_20(self, query):
        found = query.find_nonempty_labels(("阶段",))
        stage = found.get("阶段")
        if stage is None:
            yield _missing("STAGE_MISSING", "阶段信息", query.find_text(("阶段",)))
            return
        stage_text = (stage.quoted_text or "").strip().casefold()
        if re.search(
            r"(?:非\s*pp(?![a-z0-9])|(?:non[\s-]*|not\s+)pp(?![a-z0-9]))",
            stage_text,
        ) is not None:
            yield _na("NON_PP_STAGE", "明确阶段证据表明当前不是 PP 阶段。", (stage,))
            return
        if re.search(r"(^|[^a-z0-9])pp([^a-z0-9]|$)", stage_text) is None:
            yield _na("NON_PP_STAGE", "明确阶段证据表明当前不是 PP 阶段。", (stage,))
            return
        yield _pass("PP_STAGE", "明确阶段证据表明当前是 PP 阶段。", (stage,))
        yield _kind(query, EvidenceKind.AUTOMATION_RECORD, "开关机自动化测试记录")
        _, atoms = _labels(query, ("开关机自动化测试结果",))
        yield from atoms

    def _rule_21(self, query):
        found = query.find_nonempty_labels(("WIFI适用性",))
        scope = found.get("WIFI适用性")
        if scope is None:
            yield _missing("WIFI_SCOPE_MISSING", "WIFI适用性", query.find_text(("WIFI适用性",)))
            return
        if (scope.quoted_text or "").strip().casefold() in {"否", "不适用", "non-wifi", "no"}:
            yield _na("NON_WIFI_SCOPE", "明确适用范围证据表明该报告不是 WIFI 报告。", (scope,))
            return
        yield _pass("WIFI_SCOPE", "明确适用范围证据表明该报告是 WIFI 报告。", (scope,))
        _, atoms = _labels(query, ("WIFI小结论", "WIFI页面顶端结论"))
        yield from atoms

    def _rule_22(self, query):
        not_applicable = _explicit_text(query, "温升部件喷漆检查：不适用") or _explicit_non_applicable_label(query, "温升部件喷漆适用性")
        if not_applicable:
            yield _na("COATING_NOT_APPLICABLE", "明确证据表明温升部件喷漆检查不适用。", not_applicable)
            return
        _, atoms = _labels(query, ("温升部件喷漆适用性",))
        yield from atoms
        yield _kind(query, EvidenceKind.TEMPERATURE_RECORD, "温升报告")
        for component in ("CPU散热器", "tuner屏蔽框"):
            evidence = query.find_text((f"{component}喷漆状态",))
            if evidence:
                yield _pass(f"COATING_{component}_EVIDENCE", f"可追溯证据包含部件“{component}”。", evidence)
            else:
                yield _missing(f"COATING_{component}_EVIDENCE_MISSING", f"{component}喷漆状态照片/记录")
        if not query.has_evidence_kind(EvidenceKind.PUBLISHED_CRITERIA):
            yield _pending("COATING_EXPECTATION_ABSENT", "未提供已发布的喷漆状态要求；系统不会自行推断预期状态。")
        else:
            yield _pending("COATING_COMPARISON_UNRESOLVED", "与已提供的喷漆状态要求进行比对需要语义审核。")
