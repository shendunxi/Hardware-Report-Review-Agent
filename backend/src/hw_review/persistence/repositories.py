"""Transactional SQLite implementations of the domain repository ports."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from sqlalchemy import Engine, and_, delete, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel
from pydantic_core import to_jsonable_python

from hw_review.domain import (
    EvidenceLocator,
    ManualDecision,
    ReviewRevision,
    ReviewTask,
    RuleResult,
    StageFailure,
    StagedFile,
    TemplateAuditEvent,
    TemplateRule,
    TemplateStatus,
    TemplateValidationFinding,
    TemplateVersion,
)
from hw_review.domain.timestamps import as_stored_text, from_stored_text
from hw_review.rules import A11Registry

from .database import create_database_engine
from .tables import (
    manual_decisions,
    review_revisions,
    rule_results,
    source_files,
    stage_failures,
    tasks,
    template_audit_events,
    template_rules,
    template_versions,
)


class RepositoryError(Exception):
    """Base class for stable persistence boundary failures."""


class RepositoryNotFoundError(RepositoryError):
    """Raised when a requested durable object does not exist."""


class RepositoryConflictError(RepositoryError):
    """Raised when a uniqueness or relation constraint rejects a write."""


class InvalidEvaluationResultSetError(RepositoryConflictError):
    """Raised before mutation when the frozen active A11 result identity set is wrong."""

    code = "INVALID_RESULT_SET"


class CompletedRevisionError(RepositoryConflictError):
    """Raised on any attempt to mutate a completed revision snapshot."""


def _enabled_task_rule_ids(task: ReviewTask) -> set[str]:
    try:
        payload = json.loads(task.template_rules_snapshot)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("task template rule snapshot is invalid") from error
    if not payload:
        if task.template_version != "A11":
            raise ValueError("non-A11 task has no template rule snapshot")
        return {definition.id for definition in A11Registry.executed_rules()}
    if not isinstance(payload, list):
        raise ValueError("task template rule snapshot must be a list")
    ids = [item.get("rule_id") for item in payload if isinstance(item, dict) and item.get("enabled") is True]
    if len(ids) != len(set(ids)) or any(not isinstance(item, str) or not item for item in ids):
        raise ValueError("task template rule snapshot has invalid enabled rule ids")
    return set(ids)


def _json_text(value: Any) -> str:
    return json.dumps(
        to_jsonable_python(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _task_values(task: ReviewTask) -> dict[str, Any]:
    return {
        "id": str(task.id),
        "state": task.state.value,
        "active_revision_no": task.active_revision_no,
        "display_name": task.display_name,
        "template_version": task.template_version,
        "template_id": str(task.template_id) if task.template_id is not None else None,
        "template_name": task.template_name,
        "template_source_path": str(task.template_source_path) if task.template_source_path is not None else None,
        "template_source_sha256": task.template_source_sha256,
        "template_rules_snapshot": task.template_rules_snapshot,
        "created_at": as_stored_text(task.created_at),
        "updated_at": as_stored_text(task.updated_at),
    }


def _task_from_row(row) -> ReviewTask:
    return ReviewTask(
        id=row.id,
        state=row.state,
        active_revision_no=row.active_revision_no,
        display_name=row.display_name,
        template_version=row.template_version,
        template_id=getattr(row, "template_id", None),
        template_name=getattr(row, "template_name", None) or "硬件测试过程检查单",
        template_source_path=getattr(row, "template_source_path", None),
        template_source_sha256=getattr(row, "template_source_sha256", None),
        template_rules_snapshot=getattr(row, "template_rules_snapshot", None) or "[]",
        created_at=from_stored_text(row.created_at),
        updated_at=from_stored_text(row.updated_at),
    )


def _result_values(result: RuleResult) -> dict[str, Any]:
    diagnostics = {
        "missing_materials": list(result.missing_materials),
        "unresolved_semantics": list(result.unresolved_semantics),
    }
    return {
        "id": str(result.id),
        "task_id": str(result.task_id),
        "rule_id": result.rule_id,
        "initial_status": result.initial_status.value,
        "basis_code": result.basis_code,
        "basis_text": result.basis_text,
        "evidence_json": _json_text(result.evidence_locators),
        "diagnostics_json": _json_text(diagnostics),
        "engine_version": result.engine_version,
        "active_revision_no": result.active_revision_no,
        "created_at": as_stored_text(result.created_at),
    }


def _result_from_row(row) -> RuleResult:
    diagnostics = json.loads(row.diagnostics_json)
    return RuleResult(
        id=row.id,
        task_id=row.task_id,
        rule_id=row.rule_id,
        initial_status=row.initial_status,
        basis_code=row.basis_code,
        basis_text=row.basis_text,
        evidence_locators=tuple(
            EvidenceLocator.model_validate(item) for item in json.loads(row.evidence_json)
        ),
        missing_materials=tuple(diagnostics["missing_materials"]),
        unresolved_semantics=tuple(diagnostics["unresolved_semantics"]),
        engine_version=row.engine_version,
        active_revision_no=row.active_revision_no,
        created_at=from_stored_text(row.created_at),
    )


def _decision_values(
    task_id: UUID,
    active_revision_no: int,
    decision: ManualDecision,
    *,
    revision_id: UUID | None = None,
) -> dict[str, Any]:
    return {
        "id": str(decision.id),
        "task_id": str(task_id),
        "rule_result_id": str(decision.rule_result_id),
        "revision_id": str(revision_id) if revision_id is not None else None,
        "active_revision_no": active_revision_no,
        "final_status": decision.final_status.value,
        "reason": decision.reason,
        "supplemental_evidence_json": _json_text(decision.supplemental_evidence),
        "actor": decision.actor,
        "decided_at": as_stored_text(decision.decided_at),
    }


def _decision_from_row(row) -> ManualDecision:
    return ManualDecision(
        id=row.id,
        rule_result_id=row.rule_result_id,
        final_status=row.final_status,
        reason=row.reason,
        supplemental_evidence=tuple(
            EvidenceLocator.model_validate(item)
            for item in json.loads(row.supplemental_evidence_json)
        ),
        actor=row.actor,
        decided_at=from_stored_text(row.decided_at),
    )


def _source_values(source: StagedFile) -> dict[str, Any]:
    return {
        "id": str(source.id), "task_id": str(source.task_id), "role": source.role.value,
        "evidence_kinds_json": _json_text(list(source.evidence_kinds)),
        "original_name": source.original_name, "detected_format": source.detected_format,
        "path": str(source.path), "size_bytes": source.size_bytes, "sha256": source.sha256,
        "source_mtime_ns": source.source_mtime_ns,
    }


def _source_from_row(row) -> StagedFile:
    return StagedFile(
        id=row.id, task_id=row.task_id, role=row.role,
        evidence_kinds=tuple(json.loads(row.evidence_kinds_json)),
        original_name=row.original_name, detected_format=row.detected_format,
        path=row.path, size_bytes=row.size_bytes, sha256=row.sha256,
        source_mtime_ns=row.source_mtime_ns,
    )


def _failure_from_row(row) -> StageFailure:
    return StageFailure(id=row.id, task_id=row.task_id, stage=row.stage, code=row.code,
                        message=row.message, occurred_at=from_stored_text(row.occurred_at))


def _template_values(template: TemplateVersion) -> dict[str, Any]:
    return {
        "id": str(template.id),
        "name": template.name,
        "version": template.version,
        "status": template.status.value,
        "source_filename": template.source_filename,
        "source_path": str(template.source_path),
        "source_sha256": template.source_sha256,
        "source_size_bytes": template.source_size_bytes,
        "source_mtime_ns": template.source_mtime_ns,
        "source_rows": template.source_rows,
        "effective_rules": template.effective_rules,
        "validation_json": _json_text(template.validation_findings),
        "created_by": template.created_by,
        "created_at": as_stored_text(template.created_at),
        "updated_at": as_stored_text(template.updated_at),
        "published_at": as_stored_text(template.published_at) if template.published_at else None,
    }


def _template_from_row(row) -> TemplateVersion:
    return TemplateVersion(
        id=row.id,
        name=row.name,
        version=row.version,
        status=row.status,
        source_filename=row.source_filename,
        source_path=row.source_path,
        source_sha256=row.source_sha256,
        source_size_bytes=row.source_size_bytes,
        source_mtime_ns=row.source_mtime_ns,
        source_rows=row.source_rows,
        effective_rules=row.effective_rules,
        validation_findings=tuple(
            TemplateValidationFinding.model_validate(item)
            for item in json.loads(row.validation_json)
        ),
        created_by=row.created_by,
        created_at=from_stored_text(row.created_at),
        updated_at=from_stored_text(row.updated_at),
        published_at=from_stored_text(row.published_at) if row.published_at else None,
    )


def _template_rule_values(rule: TemplateRule) -> dict[str, Any]:
    return {
        "id": str(rule.id),
        "template_id": str(rule.template_id),
        "rule_id": rule.rule_id,
        "source_row": rule.source_row,
        "source_sequence": rule.source_sequence,
        "summary": rule.summary,
        "verifiable_requirement": rule.verifiable_requirement,
        "required_materials": rule.required_materials,
        "main_judgment": rule.main_judgment,
        "confirmed_boundary": rule.confirmed_boundary,
        "enabled": 1 if rule.enabled else 0,
        "created_at": as_stored_text(rule.created_at),
        "updated_at": as_stored_text(rule.updated_at),
    }


def _template_rule_from_row(row) -> TemplateRule:
    return TemplateRule(
        id=row.id,
        template_id=row.template_id,
        rule_id=row.rule_id,
        source_row=row.source_row,
        source_sequence=row.source_sequence,
        summary=row.summary,
        verifiable_requirement=row.verifiable_requirement,
        required_materials=row.required_materials,
        main_judgment=row.main_judgment,
        confirmed_boundary=row.confirmed_boundary,
        enabled=bool(row.enabled),
        created_at=from_stored_text(row.created_at),
        updated_at=from_stored_text(row.updated_at),
    )


def _template_audit_values(event: TemplateAuditEvent) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "template_id": str(event.template_id),
        "template_version": event.template_version,
        "action": event.action.value,
        "rule_id": event.rule_id,
        "actor": event.actor,
        "occurred_at": as_stored_text(event.occurred_at),
        "before_json": _json_text(event.before) if event.before is not None else None,
        "after_json": _json_text(event.after) if event.after is not None else None,
    }


def _template_audit_from_row(row) -> TemplateAuditEvent:
    return TemplateAuditEvent(
        id=row.id,
        template_id=row.template_id,
        template_version=row.template_version,
        action=row.action,
        rule_id=row.rule_id,
        actor=row.actor,
        occurred_at=from_stored_text(row.occurred_at),
        before=json.loads(row.before_json) if row.before_json is not None else None,
        after=json.loads(row.after_json) if row.after_json is not None else None,
    )


def _insert_template_audit(connection, event: TemplateAuditEvent) -> None:
    connection.execute(insert(template_audit_events), _template_audit_values(event))


def _save_active_decision(
    connection,
    task_id: UUID,
    active_revision_no: int,
    decision: ManualDecision,
) -> None:
    result_row = connection.execute(
        select(rule_results.c.id).where(
            rule_results.c.id == str(decision.rule_result_id),
            rule_results.c.task_id == str(task_id),
            rule_results.c.active_revision_no == active_revision_no,
        )
    ).one_or_none()
    if result_row is None:
        raise RepositoryConflictError(
            "decision must reference a result in the task active revision"
        )

    existing = connection.execute(
        select(manual_decisions.c.id, manual_decisions.c.revision_id).where(
            manual_decisions.c.task_id == str(task_id),
            manual_decisions.c.rule_result_id == str(decision.rule_result_id),
            manual_decisions.c.active_revision_no == active_revision_no,
        )
    ).one_or_none()
    values = _decision_values(task_id, active_revision_no, decision)
    if existing is None:
        connection.execute(insert(manual_decisions), values)
        return
    if existing.revision_id is not None:
        raise CompletedRevisionError(
            f"decision is frozen by completed revision: {decision.rule_result_id}"
        )
    connection.execute(
        update(manual_decisions)
        .where(manual_decisions.c.id == existing.id)
        .values(**values)
    )


class SqliteTaskRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create(self, task: ReviewTask) -> ReviewTask:
        try:
            with self._engine.begin() as connection:
                connection.execute(insert(tasks), _task_values(task))
        except IntegrityError as error:
            raise RepositoryConflictError(f"task already exists: {task.id}") from error
        return task

    def get(self, task_id: UUID) -> ReviewTask:
        with self._engine.connect() as connection:
            row = connection.execute(
                select(tasks).where(tasks.c.id == str(task_id))
            ).one_or_none()
        if row is None:
            raise RepositoryNotFoundError(f"task not found: {task_id}")
        return _task_from_row(row)

    def update(self, task: ReviewTask) -> ReviewTask:
        values = _task_values(task)
        values.pop("id")
        with self._engine.begin() as connection:
            result = connection.execute(
                update(tasks).where(tasks.c.id == str(task.id)).values(**values)
            )
        if result.rowcount != 1:
            raise RepositoryNotFoundError(f"task not found: {task.id}")
        return task

    def list_recent(self) -> tuple[ReviewTask, ...]:
        with self._engine.connect() as connection:
            rows = connection.execute(select(tasks).order_by(tasks.c.created_at.desc(), tasks.c.id)).all()
        return tuple(_task_from_row(row) for row in rows)

    def claim_execution(
        self, task_id: UUID, *, now: datetime, lease_seconds: int
    ) -> ReviewTask | None:
        """Atomically claim a task that is either new or lease-expired.

        ``CREATED`` covers the first claim. A state in
        ``(FILES_STAGED, PARSING, PARSED, EVALUATING)`` covers an execution that
        was interrupted mid-flight: once ``updated_at`` is older than the lease
        the owning process is presumed dead, so the task becomes reclaimable
        instead of being stuck forever. Claimability is decided inside this
        single guarded UPDATE, so concurrent claimants cannot both win.
        """
        if lease_seconds <= 0:
            raise ValueError("execution lease must be positive")
        stale_before = as_stored_text(now - timedelta(seconds=lease_seconds))
        with self._engine.begin() as connection:
            claimed = connection.execute(
                update(tasks)
                .where(
                    tasks.c.id == str(task_id),
                    or_(
                        tasks.c.state == "CREATED",
                        and_(
                            tasks.c.state.in_(
                                ("FILES_STAGED", "PARSING", "PARSED", "EVALUATING")
                            ),
                            tasks.c.updated_at <= stale_before,
                        ),
                    ),
                )
                .values(state="FILES_STAGED", execution_claim=str(uuid4()), updated_at=as_stored_text(now))
            )
            if claimed.rowcount != 1:
                return None
            row = connection.execute(select(tasks).where(tasks.c.id == str(task_id))).one()
        return _task_from_row(row)


class SqliteSourceFileRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create(self, source: StagedFile) -> StagedFile:
        try:
            with self._engine.begin() as connection:
                connection.execute(insert(source_files), _source_values(source))
        except IntegrityError as error:
            raise RepositoryConflictError("source file already exists") from error
        return source

    def create_all(self, sources: tuple[StagedFile, ...]) -> tuple[StagedFile, ...]:
        """Record a task's whole source set in one transaction.

        A task is only meaningful together with every file it was created from, so
        the set is inserted atomically: a partial success would leave the task
        pointing at a silent subset of the uploads it was asked to review.
        """

        if not sources:
            return ()
        try:
            with self._engine.begin() as connection:
                connection.execute(
                    insert(source_files),
                    [_source_values(source) for source in sources],
                )
        except IntegrityError as error:
            raise RepositoryConflictError(
                "staged source set violates a database constraint"
            ) from error
        return tuple(sources)

    def list_for_task(self, task_id: UUID) -> tuple[StagedFile, ...]:
        with self._engine.connect() as connection:
            rows = connection.execute(select(source_files).where(source_files.c.task_id == str(task_id)).order_by(source_files.c.id)).all()
        return tuple(_source_from_row(row) for row in rows)


class SqliteStageFailureRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create(self, failure: StageFailure) -> StageFailure:
        with self._engine.begin() as connection:
            connection.execute(insert(stage_failures), {
                "id": str(failure.id), "task_id": str(failure.task_id), "stage": failure.stage,
                "code": failure.code, "message": failure.message,
                "occurred_at": as_stored_text(failure.occurred_at),
            })
        return failure

    def list_for_task(self, task_id: UUID) -> tuple[StageFailure, ...]:
        with self._engine.connect() as connection:
            rows = connection.execute(select(stage_failures).where(stage_failures.c.task_id == str(task_id)).order_by(stage_failures.c.occurred_at, stage_failures.c.id)).all()
        return tuple(_failure_from_row(row) for row in rows)


class SqliteTemplateRepository:
    """Transactional template versions with immutable published rule snapshots."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create(
        self,
        template: TemplateVersion,
        rules: tuple[TemplateRule, ...],
        audit_event: TemplateAuditEvent | None = None,
    ) -> TemplateVersion:
        if any(rule.template_id != template.id for rule in rules):
            raise RepositoryConflictError("every rule must belong to the template")
        try:
            with self._engine.begin() as connection:
                connection.execute(insert(template_versions), _template_values(template))
                if rules:
                    connection.execute(
                        insert(template_rules),
                        [_template_rule_values(rule) for rule in rules],
                    )
                if audit_event is not None:
                    _insert_template_audit(connection, audit_event)
        except IntegrityError as error:
            raise RepositoryConflictError(
                f"template version already exists or has invalid rules: {template.name} {template.version}"
            ) from error
        return template

    def get(self, template_id: UUID) -> TemplateVersion:
        with self._engine.connect() as connection:
            row = connection.execute(
                select(template_versions).where(template_versions.c.id == str(template_id))
            ).one_or_none()
        if row is None:
            raise RepositoryNotFoundError(f"template not found: {template_id}")
        return _template_from_row(row)

    def find_by_name_version(self, name: str, version: str) -> TemplateVersion | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                select(template_versions).where(
                    template_versions.c.name == name,
                    template_versions.c.version == version,
                )
            ).one_or_none()
        return _template_from_row(row) if row is not None else None

    def list_versions(self) -> tuple[TemplateVersion, ...]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(template_versions).order_by(
                    template_versions.c.created_at.desc(), template_versions.c.id
                )
            ).all()
        return tuple(_template_from_row(row) for row in rows)

    def list_rules(self, template_id: UUID) -> tuple[TemplateRule, ...]:
        self.get(template_id)
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(template_rules)
                .where(template_rules.c.template_id == str(template_id))
                .order_by(template_rules.c.source_sequence, template_rules.c.rule_id)
            ).all()
        return tuple(_template_rule_from_row(row) for row in rows)

    def update_version(
        self,
        template: TemplateVersion,
        audit_event: TemplateAuditEvent | None = None,
    ) -> TemplateVersion:
        current = self.get(template.id)
        if current.status is TemplateStatus.RETIRED:
            raise RepositoryConflictError("retired template is immutable")
        if current.status is TemplateStatus.PUBLISHED:
            immutable_current = current.model_dump(exclude={"status", "updated_at"})
            immutable_next = template.model_dump(exclude={"status", "updated_at"})
            if template.status is not TemplateStatus.RETIRED or immutable_current != immutable_next:
                raise RepositoryConflictError("published template is immutable")
        values = _template_values(template)
        values.pop("id")
        try:
            with self._engine.begin() as connection:
                connection.execute(
                    update(template_versions)
                    .where(template_versions.c.id == str(template.id))
                    .values(**values)
                )
                if audit_event is not None:
                    _insert_template_audit(connection, audit_event)
        except IntegrityError as error:
            raise RepositoryConflictError("template update violates a database constraint") from error
        return template

    def _require_draft(self, connection, template_id: UUID) -> None:
        status = connection.scalar(
            select(template_versions.c.status).where(
                template_versions.c.id == str(template_id)
            )
        )
        if status is None:
            raise RepositoryNotFoundError(f"template not found: {template_id}")
        if status != TemplateStatus.DRAFT.value:
            raise RepositoryConflictError("published or retired template rules are immutable")

    def update_rule(
        self,
        rule: TemplateRule,
        audit_event: TemplateAuditEvent | None = None,
    ) -> TemplateRule:
        values = _template_rule_values(rule)
        values.pop("id")
        try:
            with self._engine.begin() as connection:
                self._require_draft(connection, rule.template_id)
                result = connection.execute(
                    update(template_rules)
                    .where(
                        template_rules.c.id == str(rule.id),
                        template_rules.c.template_id == str(rule.template_id),
                    )
                    .values(**values)
                )
                if result.rowcount != 1:
                    raise RepositoryNotFoundError(f"template rule not found: {rule.rule_id}")
                if audit_event is not None:
                    _insert_template_audit(connection, audit_event)
        except IntegrityError as error:
            raise RepositoryConflictError("template rule update violates a database constraint") from error
        return rule

    def add_rule(
        self,
        rule: TemplateRule,
        audit_event: TemplateAuditEvent | None = None,
    ) -> TemplateRule:
        try:
            with self._engine.begin() as connection:
                self._require_draft(connection, rule.template_id)
                connection.execute(insert(template_rules), _template_rule_values(rule))
                if audit_event is not None:
                    _insert_template_audit(connection, audit_event)
        except IntegrityError as error:
            raise RepositoryConflictError("template rule already exists or conflicts") from error
        return rule

    def delete_rule(
        self,
        template_id: UUID,
        rule_id: str,
        audit_event: TemplateAuditEvent | None = None,
    ) -> None:
        with self._engine.begin() as connection:
            self._require_draft(connection, template_id)
            result = connection.execute(
                delete(template_rules).where(
                    template_rules.c.template_id == str(template_id),
                    template_rules.c.rule_id == rule_id,
                )
            )
            if result.rowcount != 1:
                raise RepositoryNotFoundError(f"template rule not found: {rule_id}")
            if audit_event is not None:
                _insert_template_audit(connection, audit_event)


class SqliteTemplateAuditRepository:
    """Append-only access to durable template mutation events."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create(self, event: TemplateAuditEvent) -> TemplateAuditEvent:
        try:
            with self._engine.begin() as connection:
                _insert_template_audit(connection, event)
        except IntegrityError as error:
            raise RepositoryConflictError("template audit event violates a database constraint") from error
        return event

    def list_for_template(self, template_id: UUID) -> tuple[TemplateAuditEvent, ...]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(template_audit_events)
                .where(template_audit_events.c.template_id == str(template_id))
                .order_by(
                    template_audit_events.c.occurred_at.desc(),
                    template_audit_events.c.id.desc(),
                )
            ).all()
        return tuple(_template_audit_from_row(row) for row in rows)

class SqliteResultRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def replace_all(self, task_id: UUID, results: tuple[RuleResult, ...]) -> None:
        if any(result.task_id != task_id for result in results):
            raise RepositoryConflictError("all results must belong to the requested task")
        revision_numbers = {result.active_revision_no for result in results}
        if len(revision_numbers) > 1:
            raise RepositoryConflictError("all results must share one active revision")
        try:
            with self._engine.begin() as connection:
                task_row = connection.execute(
                    select(tasks.c.active_revision_no).where(tasks.c.id == str(task_id))
                ).one_or_none()
                if task_row is None:
                    raise RepositoryNotFoundError(f"task not found: {task_id}")
                if results:
                    revision_no = next(iter(revision_numbers))
                    if revision_no != task_row.active_revision_no:
                        raise RepositoryConflictError(
                            "result revision does not match the task active revision"
                        )
                    connection.execute(
                        delete(rule_results).where(
                            rule_results.c.task_id == str(task_id),
                            rule_results.c.active_revision_no == revision_no,
                        )
                    )
                    connection.execute(
                        insert(rule_results),
                        [_result_values(result) for result in results],
                    )
                else:
                    connection.execute(
                        delete(rule_results).where(
                            rule_results.c.task_id == str(task_id),
                            rule_results.c.active_revision_no == task_row.active_revision_no,
                        )
                    )
        except IntegrityError as error:
            raise RepositoryConflictError("result replacement violates a database constraint") from error

    def list_for_task(self, task_id: UUID) -> tuple[RuleResult, ...]:
        with self._engine.connect() as connection:
            task_row = connection.execute(
                select(tasks.c.active_revision_no).where(tasks.c.id == str(task_id))
            ).one_or_none()
            if task_row is None:
                raise RepositoryNotFoundError(f"task not found: {task_id}")
            rows = connection.execute(
                select(rule_results)
                .where(
                    rule_results.c.task_id == str(task_id),
                    rule_results.c.active_revision_no == task_row.active_revision_no,
                )
                .order_by(rule_results.c.rule_id, rule_results.c.id)
            ).all()
        return tuple(_result_from_row(row) for row in rows)


class SqliteDecisionRepository:
    """Mutable active decisions that become immutable when a revision completes."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def save_or_replace(
        self, task_id: UUID, decision: ManualDecision
    ) -> ManualDecision:
        try:
            with self._engine.begin() as connection:
                task_row = connection.execute(
                    select(tasks.c.active_revision_no).where(tasks.c.id == str(task_id))
                ).one_or_none()
                if task_row is None:
                    raise RepositoryNotFoundError(f"task not found: {task_id}")
                _save_active_decision(
                    connection, task_id, task_row.active_revision_no, decision
                )
        except IntegrityError as error:
            raise RepositoryConflictError(
                "decision replacement violates a database constraint"
            ) from error
        return decision

    def list_for_task(self, task_id: UUID) -> tuple[ManualDecision, ...]:
        with self._engine.connect() as connection:
            task_row = connection.execute(
                select(tasks.c.active_revision_no).where(tasks.c.id == str(task_id))
            ).one_or_none()
            if task_row is None:
                raise RepositoryNotFoundError(f"task not found: {task_id}")
            rows = connection.execute(
                select(manual_decisions)
                .join(
                    rule_results,
                    manual_decisions.c.rule_result_id == rule_results.c.id,
                )
                .where(
                    manual_decisions.c.task_id == str(task_id),
                    manual_decisions.c.active_revision_no
                    == task_row.active_revision_no,
                )
                .order_by(rule_results.c.rule_id, manual_decisions.c.id)
            ).all()
        return tuple(_decision_from_row(row) for row in rows)


class SqliteRevisionRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def complete(
        self, task_id: UUID, decisions: tuple[ManualDecision, ...]
    ) -> ReviewRevision:
        result_identities = [decision.rule_result_id for decision in decisions]
        if len(result_identities) != len(set(result_identities)):
            raise RepositoryConflictError(
                "completion contains more than one decision for a rule result"
            )
        completed_at = datetime.now(timezone.utc)
        revision_id = uuid4()
        try:
            with self._engine.begin() as connection:
                task_row = connection.execute(
                    select(tasks.c.active_revision_no).where(tasks.c.id == str(task_id))
                ).one_or_none()
                if task_row is None:
                    raise RepositoryNotFoundError(f"task not found: {task_id}")
                result_rows = connection.execute(
                    select(rule_results)
                    .where(
                        rule_results.c.task_id == str(task_id),
                        rule_results.c.active_revision_no == task_row.active_revision_no,
                    )
                    .order_by(rule_results.c.rule_id, rule_results.c.id)
                ).all()
                known_ids = {UUID(row.id) for row in result_rows}
                if any(decision.rule_result_id not in known_ids for decision in decisions):
                    raise RepositoryConflictError(
                        "all decisions must reference current task results"
                    )
                for decision in decisions:
                    _save_active_decision(
                        connection,
                        task_id,
                        task_row.active_revision_no,
                        decision,
                    )
                decision_rows = connection.execute(
                    select(manual_decisions)
                    .join(
                        rule_results,
                        manual_decisions.c.rule_result_id == rule_results.c.id,
                    )
                    .where(
                        manual_decisions.c.task_id == str(task_id),
                        manual_decisions.c.active_revision_no
                        == task_row.active_revision_no,
                    )
                    .order_by(rule_results.c.rule_id, manual_decisions.c.id)
                ).all()
                if any(row.revision_id is not None for row in decision_rows):
                    raise CompletedRevisionError(
                        "active-revision decisions are already frozen"
                    )
                next_revision_no = (
                    connection.scalar(
                        select(func.max(review_revisions.c.revision_no)).where(
                            review_revisions.c.task_id == str(task_id)
                        )
                    )
                    or 0
                ) + 1
                authoritative_decisions = tuple(
                    _decision_from_row(row) for row in decision_rows
                )
                snapshot = _json_text(
                    {
                        "decisions": [
                            item.model_dump(mode="json")
                            for item in authoritative_decisions
                        ],
                        "results": [
                            _result_from_row(row).model_dump(mode="json") for row in result_rows
                        ],
                        "task_id": str(task_id),
                        "revision_no": next_revision_no,
                    }
                )
                revision = ReviewRevision(
                    id=revision_id,
                    task_id=task_id,
                    revision_no=next_revision_no,
                    completed_at=completed_at,
                    result_snapshot=snapshot,
                )
                connection.execute(
                    insert(review_revisions),
                    {
                        "id": str(revision.id),
                        "task_id": str(revision.task_id),
                        "revision_no": revision.revision_no,
                        "completed_at": as_stored_text(revision.completed_at),
                        "result_snapshot": revision.result_snapshot,
                    },
                )
                if decision_rows:
                    connection.execute(
                        update(manual_decisions)
                        .where(
                            manual_decisions.c.task_id == str(task_id),
                            manual_decisions.c.active_revision_no
                            == task_row.active_revision_no,
                            manual_decisions.c.revision_id.is_(None),
                        )
                        .values(revision_id=str(revision.id))
                    )
        except IntegrityError as error:
            raise RepositoryConflictError("revision violates a database constraint") from error
        return revision

    def get(self, revision_id: UUID) -> ReviewRevision:
        with self._engine.connect() as connection:
            row = connection.execute(
                select(review_revisions).where(review_revisions.c.id == str(revision_id))
            ).one_or_none()
        if row is None:
            raise RepositoryNotFoundError(f"revision not found: {revision_id}")
        return ReviewRevision(
            id=row.id,
            task_id=row.task_id,
            revision_no=row.revision_no,
            completed_at=from_stored_text(row.completed_at),
            result_snapshot=row.result_snapshot,
        )

    def list_for_task(self, task_id: UUID) -> tuple[ReviewRevision, ...]:
        with self._engine.connect() as connection:
            rows = connection.execute(select(review_revisions).where(review_revisions.c.task_id == str(task_id)).order_by(review_revisions.c.revision_no)).all()
        return tuple(ReviewRevision(id=row.id, task_id=row.task_id, revision_no=row.revision_no,
                                    completed_at=from_stored_text(row.completed_at), result_snapshot=row.result_snapshot)
                     for row in rows)

    def update_snapshot(
        self,
        revision_id: UUID,
        snapshot: BaseModel | Mapping[str, object],
    ) -> ReviewRevision:
        self.get(revision_id)
        raise CompletedRevisionError(f"completed revision is immutable: {revision_id}")


@dataclass(slots=True)
class RepositoryBundle:
    """Repositories sharing one engine and one explicit lifecycle."""

    engine: Engine
    tasks: SqliteTaskRepository
    results: SqliteResultRepository
    decisions: SqliteDecisionRepository
    revisions: SqliteRevisionRepository
    sources: SqliteSourceFileRepository
    failures: SqliteStageFailureRepository
    templates: SqliteTemplateRepository
    template_audits: SqliteTemplateAuditRepository

    @staticmethod
    def _require_complete_a11_results(task: ReviewTask, results: tuple[RuleResult, ...]) -> None:
        try:
            expected = _enabled_task_rule_ids(task)
        except ValueError as error:
            raise InvalidEvaluationResultSetError("task template rule snapshot is invalid") from error
        actual = [result.rule_id for result in results]
        if (
            len(results) != len(expected)
            or len(actual) != len(set(actual))
            or set(actual) != expected
            or any(result.task_id != task.id or result.active_revision_no != task.active_revision_no for result in results)
        ):
            raise InvalidEvaluationResultSetError("evaluation must exactly match the task template's enabled rule set")

    def commit_evaluation(self, task: ReviewTask, results: tuple[RuleResult, ...]) -> None:
        """Replace a complete active result set and transition state atomically."""
        self._require_complete_a11_results(task, results)
        try:
            with self.engine.begin() as connection:
                connection.execute(delete(rule_results).where(rule_results.c.task_id == str(task.id), rule_results.c.active_revision_no == task.active_revision_no))
                connection.execute(insert(rule_results), [_result_values(result) for result in results])
                values = _task_values(task); values.pop("id")
                connection.execute(update(tasks).where(tasks.c.id == str(task.id)).values(**values, execution_claim=None))
        except IntegrityError as error:
            raise RepositoryConflictError("evaluation result replacement violates a database constraint") from error

    def commit_failure(self, task: ReviewTask, failure: StageFailure) -> None:
        """Persist FAILED and its diagnosis together, dropping partial active results."""
        with self.engine.begin() as connection:
            connection.execute(delete(rule_results).where(rule_results.c.task_id == str(task.id), rule_results.c.active_revision_no == task.active_revision_no))
            connection.execute(insert(stage_failures), {"id": str(failure.id), "task_id": str(failure.task_id), "stage": failure.stage, "code": failure.code, "message": failure.message, "occurred_at": as_stored_text(failure.occurred_at)})
            values = _task_values(task); values.pop("id")
            connection.execute(update(tasks).where(tasks.c.id == str(task.id)).values(**values, execution_claim=None))

    def complete_task(self, task: ReviewTask, decisions: tuple[ManualDecision, ...], completed_at: datetime) -> ReviewRevision:
        """Freeze decisions/results/snapshot and COMPLETED state as one transaction."""
        revision_id = uuid4()
        with self.engine.begin() as connection:
            rows = connection.execute(select(rule_results).where(rule_results.c.task_id == str(task.id), rule_results.c.active_revision_no == task.active_revision_no).order_by(rule_results.c.rule_id)).all()
            for decision in decisions:
                _save_active_decision(connection, task.id, task.active_revision_no, decision)
            decision_rows = connection.execute(select(manual_decisions).where(manual_decisions.c.task_id == str(task.id), manual_decisions.c.active_revision_no == task.active_revision_no).order_by(manual_decisions.c.rule_result_id)).all()
            revision_no = (connection.scalar(select(func.max(review_revisions.c.revision_no)).where(review_revisions.c.task_id == str(task.id))) or 0) + 1
            snapshot = _json_text({
                "task_id": str(task.id),
                "revision_no": revision_no,
                "template_id": str(task.template_id) if task.template_id else None,
                "template_name": task.template_name,
                "template_version": task.template_version,
                "template_source_sha256": task.template_source_sha256,
                "template_rules": json.loads(task.template_rules_snapshot),
                "results": [_result_from_row(row).model_dump(mode="json") for row in rows],
                "decisions": [_decision_from_row(row).model_dump(mode="json") for row in decision_rows],
            })
            revision = ReviewRevision(id=revision_id, task_id=task.id, revision_no=revision_no, completed_at=completed_at, result_snapshot=snapshot)
            connection.execute(insert(review_revisions), {"id": str(revision.id), "task_id": str(revision.task_id), "revision_no": revision.revision_no, "completed_at": as_stored_text(revision.completed_at), "result_snapshot": revision.result_snapshot})
            connection.execute(update(manual_decisions).where(manual_decisions.c.task_id == str(task.id), manual_decisions.c.active_revision_no == task.active_revision_no).values(revision_id=str(revision.id)))
            values = _task_values(task); values.pop("id")
            connection.execute(update(tasks).where(tasks.c.id == str(task.id)).values(**values))
        return revision

    def reopen_task(self, task: ReviewTask, occurred_at: datetime) -> None:
        """Copy frozen system results to a new active revision without touching snapshots."""
        old_revision = task.active_revision_no - 1
        with self.engine.begin() as connection:
            rows = connection.execute(select(rule_results).where(rule_results.c.task_id == str(task.id), rule_results.c.active_revision_no == old_revision).order_by(rule_results.c.rule_id)).all()
            copies = []
            for row in rows:
                original = _result_from_row(row)
                copies.append(_result_values(original.model_copy(update={"id": uuid5(NAMESPACE_URL, f"{task.id}:{task.active_revision_no}:{original.rule_id}"), "active_revision_no": task.active_revision_no, "created_at": occurred_at})))
            if copies:
                connection.execute(insert(rule_results), copies)
            values = _task_values(task); values.pop("id")
            connection.execute(update(tasks).where(tasks.c.id == str(task.id)).values(**values))

    def close(self) -> None:
        self.engine.dispose()


def repositories(database_url: str) -> RepositoryBundle:
    """Construct repositories without creating or migrating the schema."""

    engine = create_database_engine(database_url)
    return RepositoryBundle(
        engine=engine,
        tasks=SqliteTaskRepository(engine),
        results=SqliteResultRepository(engine),
        decisions=SqliteDecisionRepository(engine),
        revisions=SqliteRevisionRepository(engine),
        sources=SqliteSourceFileRepository(engine),
        failures=SqliteStageFailureRepository(engine),
        templates=SqliteTemplateRepository(engine),
        template_audits=SqliteTemplateAuditRepository(engine),
    )
