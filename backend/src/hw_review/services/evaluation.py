"""Parser-to-rule orchestration for one fully staged local task."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from hw_review.domain import ReviewInput, ReviewSource, ReviewStatus, RuleResult
from hw_review.rules import A11Engine, NormalizedDocumentQuery
from hw_review.services.parsing import ParserRegistry
from hw_review.services.semantic_judge import JUDGEABLE_JUDGEMENTS, build_judge_request
from hw_review.services.template_binding import enabled_rules_for_task, is_frozen_a11_implementation


# The engine's rollup emits this code for every deterministic NON_COMPLIANT
# (missing required material or a failed objective check).
HARD_FAILURE_BASIS_CODE = "ROLLUP_HARD_FAILURE"

# A determinate engine verdict and the model disagree: escalated to a human
# rather than decided in either direction.
DISAGREEMENT_BASIS_CODE = "LLM_DISAGREES_WITH_ENGINE"

# A model that lists every line it read can hand back hundreds of locators for a
# single rule, which bloats the result row for no auditing benefit. The retained
# count is bounded and the omission is stated in the basis text, mirroring how
# the checklist export already bounds its evidence section.
MAX_EVIDENCE_LOCATORS = 50


def _merge_locators(
    engine_locators: tuple, model_locators: tuple
) -> tuple:
    """Engine evidence first, then the model's, de-duplicated by address."""

    merged: list = []
    seen: set[tuple[str, str]] = set()
    for locator in (*engine_locators, *model_locators):
        key = (str(locator.source_file_id), locator.structural_address)
        if key in seen:
            continue
        seen.add(key)
        merged.append(locator)
    return tuple(merged)


def _merge_strings(left: tuple[str, ...], right: tuple[str, ...]) -> tuple[str, ...]:
    merged: list[str] = []
    for value in (*left, *right):
        if value and value not in merged:
            merged.append(value)
    return tuple(merged)


class EvaluationError(Exception):
    """Stable application-stage error; callers persist the exposed facts."""

    def __init__(self, stage: str, code: str, message: str) -> None:
        self.stage, self.code = stage, code
        super().__init__(message)


class EvaluationService:
    """Build one immutable ReviewInput from persisted staged copies only."""

    def __init__(
        self,
        registry: ParserRegistry,
        engine: A11Engine | None = None,
        judge=None,
        llm_scope: str = "all",
    ) -> None:
        self._registry = registry
        self._engine = engine or A11Engine()
        self._judge = judge
        self._llm_scope = llm_scope

    def evaluate(self, task, sources) -> tuple[RuleResult, ...]:
        review_sources = []
        for source in sources:
            try:
                review_sources.append(
                    ReviewSource(source_file=source, document=self._registry.for_format(source.detected_format).parse(source))
                )
            except Exception as error:
                code = getattr(error, "code", "PARSER_FAILURE")
                raise EvaluationError(
                    "PARSING", code, f"{source.original_name}: {error}"
                ) from error
        try:
            source_tuple = tuple(review_sources)
            review_input = ReviewInput(
                task_id=task.id, active_revision_no=task.active_revision_no, sources=source_tuple,
                evaluated_at=datetime.now(timezone.utc), query=NormalizedDocumentQuery(source_tuple),
            )
            baseline_results = {
                result.rule_id: result for result in self._engine.evaluate(review_input)
            }
            frozen_rules = enabled_rules_for_task(task)
            results = tuple(
                baseline_results[rule.rule_id].model_copy(
                    update={"baseline_version": task.template_version}
                )
                if is_frozen_a11_implementation(rule) and rule.rule_id in baseline_results
                else RuleResult(
                    id=uuid5(
                        NAMESPACE_URL,
                        f"{task.id}:{task.active_revision_no}:{rule.rule_id}",
                    ),
                    task_id=task.id,
                    rule_id=rule.rule_id,
                    initial_status=ReviewStatus.NEEDS_REVIEW,
                    basis_code="TEMPLATE_RULE_REQUIRES_MANUAL_REVIEW",
                    basis_text=f"模板校验要求尚无确定的自动判定实现：{rule.verifiable_requirement}",
                    evidence_locators=(),
                    missing_materials=(),
                    unresolved_semantics=(
                        f"请依据模板要求人工复核；所需材料：{rule.required_materials}",
                    ),
                    engine_version="template-manual-fallback-1",
                    baseline_version=task.template_version,
                    active_revision_no=task.active_revision_no,
                    created_at=review_input.evaluated_at,
                )
                for rule in frozen_rules
            )
            results = self._apply_llm_judgement(
                frozen_rules, results, review_input.sources
            )
        except Exception as error:
            raise EvaluationError("EVALUATING", "EVALUATION_FAILURE", str(error)) from error
        expected_ids = {rule.rule_id for rule in enabled_rules_for_task(task)}
        actual_ids = [result.rule_id for result in results]
        if len(results) != len(expected_ids) or len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != expected_ids:
            raise EvaluationError("EVALUATING", "INVALID_RESULT_SET", "模板审核结果与任务冻结的启用规则集合不一致")
        return results

    def _apply_llm_judgement(
        self,
        rules: tuple,
        results: tuple[RuleResult, ...],
        sources: tuple[ReviewSource, ...],
    ) -> tuple[RuleResult, ...]:
        """Route check items through the authorized judge.

        ``scope="all"`` sends every enabled check item. ``scope="semantic_only"``
        keeps the judge as a fallback for rules the deterministic engine left
        undecided.

        The model decides only what the engine left undecided. It may never move
        a determinate engine verdict, in either direction:

        * engine ``NEEDS_REVIEW`` -> the model's verdict is the answer.
        * engine determinate + model concurs -> keep the engine's basis code and
          detail codes (for an objective rule that is the audit backbone and must
          not be replaced by prose) and merge the model's traceable evidence in.
        * engine ``NON_COMPLIANT`` + model more lenient -> keep
          ``NON_COMPLIANT``. A missing required material is a deterministic hard
          failure (PRD: 缺少必需外部证据时系统初判不符合), and clearing it would
          skip review entirely, because only ``NEEDS_REVIEW`` items are forced
          through manual handling.
        * engine determinate + model disagrees otherwise -> ``NEEDS_REVIEW``.
          A phantom ``NON_COMPLIANT`` would also never be forced through review,
          so the disagreement is escalated to a human instead of being resolved
          by either side.

        In both dissent cases the engine's verdict and the model's verdict are
        both recorded in ``unresolved_semantics``, so the disagreement is visible
        rather than silently discarded.
        """

        if self._judge is None:
            return results
        by_id = {rule.rule_id: rule for rule in rules}
        if self._llm_scope == "all":
            targets = tuple(by_id[result.rule_id] for result in results)
        else:
            targets = tuple(
                by_id[result.rule_id]
                for result in results
                if result.initial_status is ReviewStatus.NEEDS_REVIEW
                and by_id[result.rule_id].main_judgment in JUDGEABLE_JUDGEMENTS
            )
        if not targets:
            return results
        try:
            outcome = self._judge.judge(build_judge_request(targets, sources))
        except Exception:  # noqa: BLE001 - a judge fault must not fail the task
            return results
        judged = {item.rule_id: item for item in outcome.judgements}
        updated: list[RuleResult] = []
        for result in results:
            judgement = judged.get(result.rule_id)
            if judgement is None:
                updated.append(result)
                continue
            if result.initial_status is ReviewStatus.NEEDS_REVIEW:
                # The engine abstained; the model's verdict is the answer.
                updated.append(
                    result.model_copy(
                        update={
                            "initial_status": judgement.initial_status,
                            "basis_code": judgement.basis_code,
                            "basis_text": self._bounded_basis_text(
                                judgement.basis_text, judgement.evidence_locators
                            ),
                            "evidence_locators": self._bounded_locators(
                                judgement.evidence_locators
                            ),
                            "missing_materials": judgement.missing_materials,
                            "unresolved_semantics": judgement.unresolved_semantics,
                            "engine_version": self._judge.engine_version,
                        }
                    )
                )
                continue
            if judgement.initial_status is result.initial_status:
                # Concurring. Keep the engine's precise basis code and detail
                # codes: for an objective rule that is the audit backbone, and it
                # must not be replaced by prose. The model still contributes its
                # own traceable evidence.
                updated.append(
                    result.model_copy(
                        update={
                            "evidence_locators": self._bounded_locators(
                                _merge_locators(
                                    result.evidence_locators,
                                    judgement.evidence_locators,
                                )
                            ),
                            "missing_materials": _merge_strings(
                                result.missing_materials, judgement.missing_materials
                            ),
                            "engine_version": (
                                f"{result.engine_version}+{self._judge.engine_version}"
                            ),
                        }
                    )
                )
                continue
            dissent = (
                f"确定性校验判定 {result.initial_status.value}"
                f"（{result.basis_text}），大模型判定 "
                f"{judgement.initial_status.value}（{judgement.basis_text}）。"
            )
            if (
                result.initial_status is ReviewStatus.NON_COMPLIANT
                or result.basis_code == HARD_FAILURE_BASIS_CODE
            ):
                updated.append(
                    result.model_copy(
                        update={
                            "unresolved_semantics": result.unresolved_semantics
                            + (dissent + "系统保留不符合，等待人工改判。",)
                        }
                    )
                )
                continue
            # Any other disagreement is escalated instead of being resolved by
            # either side: a phantom NON_COMPLIANT would skip review too.
            updated.append(
                result.model_copy(
                    update={
                        "initial_status": ReviewStatus.NEEDS_REVIEW,
                        "basis_code": DISAGREEMENT_BASIS_CODE,
                        "basis_text": (
                            dissent + "确定性校验与大模型存在分歧，需人工确认。"
                        ),
                        "evidence_locators": self._bounded_locators(
                            _merge_locators(
                                result.evidence_locators, judgement.evidence_locators
                            )
                        ),
                        "missing_materials": _merge_strings(
                            result.missing_materials, judgement.missing_materials
                        ),
                        "unresolved_semantics": result.unresolved_semantics
                        + (dissent + "请人工确认该检查项的最终结论。",),
                        "engine_version": (
                            f"{result.engine_version}+{self._judge.engine_version}"
                        ),
                    }
                )
            )
        return tuple(updated)

    @staticmethod
    def _bounded_locators(locators: tuple) -> tuple:
        if len(locators) <= MAX_EVIDENCE_LOCATORS:
            return locators
        return locators[:MAX_EVIDENCE_LOCATORS]

    @staticmethod
    def _bounded_basis_text(text: str, locators: tuple) -> str:
        if len(locators) <= MAX_EVIDENCE_LOCATORS:
            return text
        omitted = len(locators) - MAX_EVIDENCE_LOCATORS
        return (
            f"{text}（证据位置共 {len(locators)} 处，"
            f"按上限收录前 {MAX_EVIDENCE_LOCATORS} 处，其余 {omitted} 处省略）"
        )
