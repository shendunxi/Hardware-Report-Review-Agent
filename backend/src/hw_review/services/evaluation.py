"""Parser-to-rule orchestration for one fully staged local task."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from hw_review.domain import ReviewInput, ReviewSource, ReviewStatus, RuleResult
from hw_review.rules import A11Engine, NormalizedDocumentQuery
from hw_review.services.parsing import ParserRegistry
from hw_review.services.template_binding import enabled_rules_for_task, is_frozen_a11_implementation


class EvaluationError(Exception):
    """Stable application-stage error; callers persist the exposed facts."""

    def __init__(self, stage: str, code: str, message: str) -> None:
        self.stage, self.code = stage, code
        super().__init__(message)


class EvaluationService:
    """Build one immutable ReviewInput from persisted staged copies only."""

    def __init__(self, registry: ParserRegistry, engine: A11Engine | None = None) -> None:
        self._registry = registry
        self._engine = engine or A11Engine()

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
        except Exception as error:
            raise EvaluationError("EVALUATING", "EVALUATION_FAILURE", str(error)) from error
        expected_ids = {rule.rule_id for rule in enabled_rules_for_task(task)}
        actual_ids = [result.rule_id for result in results]
        if len(results) != len(expected_ids) or len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != expected_ids:
            raise EvaluationError("EVALUATING", "INVALID_RESULT_SET", "模板审核结果与任务冻结的启用规则集合不一致")
        return results
