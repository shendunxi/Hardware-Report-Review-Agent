"""Immutable task-template snapshot helpers shared by lifecycle, evaluation and export."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import ValidationError

from hw_review.domain import ReviewTask, TemplateRule
from hw_review.rules import A11Registry


def serialize_rules(rules: tuple[TemplateRule, ...]) -> str:
    return json.dumps(
        [rule.model_dump(mode="json") for rule in rules],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def rules_for_task(task: ReviewTask) -> tuple[TemplateRule, ...]:
    """Return the frozen rules, falling back only for pre-0003 A11 tasks."""

    try:
        payload = json.loads(task.template_rules_snapshot)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("task template rule snapshot is not valid JSON") from error
    if payload:
        if not isinstance(payload, list):
            raise ValueError("task template rule snapshot must be a list")
        try:
            return tuple(TemplateRule.model_validate(item) for item in payload)
        except ValidationError as error:
            raise ValueError("task template rule snapshot contains an invalid rule") from error
    if task.template_version != "A11":
        raise ValueError("non-A11 task has no frozen template rule snapshot")
    timestamp = datetime(1970, 1, 1, tzinfo=timezone.utc)
    template_id = task.template_id or uuid5(NAMESPACE_URL, "hardware-review-template:A11")
    return tuple(
        TemplateRule(
            id=uuid5(NAMESPACE_URL, f"{template_id}:{definition.id}"),
            template_id=template_id,
            rule_id=definition.id,
            source_row=definition.source_row,
            source_sequence=definition.source_sequence,
            summary=definition.summary,
            verifiable_requirement=definition.verifiable_requirement,
            required_materials=definition.required_materials,
            main_judgment=definition.main_judgment,
            confirmed_boundary=definition.confirmed_boundary,
            enabled=definition.enabled,
            created_at=timestamp,
            updated_at=timestamp,
        )
        for definition in A11Registry.source_rows()
    )


def enabled_rules_for_task(task: ReviewTask) -> tuple[TemplateRule, ...]:
    return tuple(rule for rule in rules_for_task(task) if rule.enabled)


def enabled_rule_ids(task: ReviewTask) -> set[str]:
    return {rule.rule_id for rule in enabled_rules_for_task(task)}


def is_frozen_a11_implementation(rule: TemplateRule) -> bool:
    try:
        definition = A11Registry.get(rule.rule_id)
    except KeyError:
        return False
    return all(
        (
            rule.source_row == definition.source_row,
            rule.source_sequence == definition.source_sequence,
            rule.summary == definition.summary,
            rule.verifiable_requirement == definition.verifiable_requirement,
            rule.required_materials == definition.required_materials,
            rule.main_judgment == definition.main_judgment,
            rule.confirmed_boundary == definition.confirmed_boundary,
        )
    )
