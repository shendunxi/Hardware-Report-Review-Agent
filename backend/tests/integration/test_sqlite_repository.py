from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import event, func, inspect, select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from hw_review.domain import (
    EvidenceLocator,
    FileRole,
    FinalStatus,
    ManualDecision,
    ReviewRevision,
    ReviewStatus,
    ReviewTask,
    RuleResult,
    StageFailure,
    StagedFile,
    TaskState,
    TemplateRule,
    TemplateStatus,
    TemplateValidationFinding,
    TemplateVersion,
)
from hw_review.persistence import (
    CompletedRevisionError,
    RepositoryConflictError,
    repositories,
)
from hw_review.config import get_settings
from hw_review.persistence.tables import metadata, review_revisions, rule_results
from hw_review.persistence.tables import manual_decisions


BACKEND_ROOT = Path(__file__).resolve().parents[2]
TASK_ID = UUID("10000000-0000-0000-0000-000000000001")


def _database_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _migrate(database_url: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["HW_REVIEW_DATABASE_URL"] = database_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    database_url = _database_url(tmp_path / "review.db")
    completed = _migrate(database_url)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    # The Alembic environment already reads HW_REVIEW_DATABASE_URL; the runtime
    # must resolve the same variable or migrations and serving could diverge.
    monkeypatch.setenv("HW_REVIEW_DATABASE_URL", database_url)
    assert get_settings().database_url == database_url
    return database_url


def _task(*, state: TaskState = TaskState.READY_FOR_REVIEW) -> ReviewTask:
    return ReviewTask(
        id=TASK_ID,
        state=state,
        active_revision_no=0,
        display_name="TCY30 PP hardware report",
        template_version="A11",
        created_at=datetime(2026, 9, 11, 1, 2, 3, 456789, tzinfo=timezone.utc),
        updated_at=datetime(2026, 9, 11, 2, 3, 4, 567890, tzinfo=timezone.utc),
    )


def _results(*, count: int = 21, revision_no: int = 0) -> tuple[RuleResult, ...]:
    items = []
    for index in range(1, count + 1):
        rule_id = f"TR-{index:02d}"
        items.append(
            RuleResult(
                id=UUID(f"{2 + revision_no}0000000-0000-0000-0000-{index:012d}"),
                task_id=TASK_ID,
                rule_id=rule_id,
                initial_status=(
                    ReviewStatus.NON_COMPLIANT
                    if index == 2
                    else ReviewStatus.NEEDS_REVIEW
                    if index == 16
                    else ReviewStatus.COMPLIANT
                ),
                basis_code=f"BASIS_{index:02d}",
                basis_text=f"Evidence result {index}",
                evidence_locators=(
                    EvidenceLocator(
                        source_file_id=UUID(
                            f"30000000-0000-0000-0000-{index:012d}"
                        ),
                        container="Sheet 1",
                        structural_address=f"sheet:0:Sheet%201/cell:A{index}",
                        quoted_text=f"value {index}",
                        content_hash=f"{index:064x}",
                    ),
                ),
                missing_materials=(f"material-{index}",) if index == 2 else (),
                unresolved_semantics=(f"semantic-{index}",) if index == 16 else (),
                engine_version="a11-rules-1",
                active_revision_no=revision_no,
                created_at=datetime(2026, 9, 11, 3, index, tzinfo=timezone.utc),
            )
        )
    return tuple(items)


def _enabled_results(*, revision_no: int = 0) -> tuple[RuleResult, ...]:
    ids = [f"TR-{index:02d}" for index in range(1, 23) if index != 5]
    return tuple(
        result.model_copy(update={"rule_id": rule_id, "active_revision_no": revision_no})
        for result, rule_id in zip(_results(revision_no=revision_no), ids, strict=True)
    )


def _decisions(results: tuple[RuleResult, ...], marker: str) -> tuple[ManualDecision, ...]:
    return tuple(
        ManualDecision(
            id=uuid4(),
            rule_result_id=result.id,
            final_status=(
                FinalStatus.NON_COMPLIANT
                if result.initial_status is ReviewStatus.NON_COMPLIANT
                else FinalStatus.COMPLIANT
            ),
            reason=f"Human review {marker} for {result.rule_id}",
            supplemental_evidence=(
                {
                    "source_file_id": str(result.evidence_locators[0].source_file_id),
                    "container": "manual note",
                    "structural_address": f"revision:{marker}/{result.rule_id}",
                    "content_hash": f"{len(marker):064x}",
                },
            ),
            actor="local-reviewer",
            decided_at=datetime(2026, 9, 11, 4, 5, 6, tzinfo=timezone.utc),
        )
        for result in results
    )


def test_repository_construction_does_not_create_schema(tmp_path: Path) -> None:
    bundle = repositories(_database_url(tmp_path / "not-migrated.db"))
    try:
        assert inspect(bundle.engine).get_table_names() == []
        with pytest.raises(OperationalError):
            bundle.tasks.get(TASK_ID)
    finally:
        bundle.close()


def test_migration_creates_exact_application_tables_and_alembic_version(
    tmp_path: Path,
) -> None:
    database_url = _database_url(tmp_path / "migration.db")
    completed = _migrate(database_url)
    assert completed.returncode == 0, completed.stdout + completed.stderr

    bundle = repositories(database_url)
    try:
        assert set(inspect(bundle.engine).get_table_names()) == {
            "alembic_version",
            "tasks",
            "source_files",
            "parse_artifacts",
            "rule_results",
            "manual_decisions",
            "review_revisions",
            "stage_failures",
            "template_versions",
            "template_rules",
            "template_audit_events",
        }
        with bundle.engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0004"
    finally:
        bundle.close()


def test_foreign_keys_are_enabled_for_every_connection_and_enforced(db_url: str) -> None:
    bundle = repositories(db_url)
    try:
        with bundle.engine.connect() as first, bundle.engine.connect() as second:
            assert first.scalar(text("PRAGMA foreign_keys")) == 1
            assert second.scalar(text("PRAGMA foreign_keys")) == 1
        with pytest.raises(IntegrityError):
            with bundle.engine.begin() as connection:
                connection.execute(
                    rule_results.insert(),
                    {
                        "id": str(uuid4()),
                        "task_id": str(uuid4()),
                        "rule_id": "TR-01",
                        "initial_status": "COMPLIANT",
                        "basis_code": "PASS",
                        "basis_text": "proven",
                        "evidence_json": "[]",
                        "diagnostics_json": "{}",
                        "engine_version": "a11-rules-1",
                        "active_revision_no": 0,
                        "created_at": "2026-09-11T00:00:00+00:00",
                    },
                )
    finally:
        bundle.close()


def test_task_and_twenty_one_results_survive_repository_restart(db_url: str) -> None:
    task = _task()
    expected_results = _results()
    first = repositories(db_url)
    first.tasks.create(task)
    first.results.replace_all(TASK_ID, tuple(reversed(expected_results)))
    first.close()

    second = repositories(db_url)
    try:
        assert second.tasks.get(TASK_ID) == task
        actual_results = second.results.list_for_task(TASK_ID)
        assert actual_results == expected_results
        assert [result.rule_id for result in actual_results] == [
            f"TR-{index:02d}" for index in range(1, 22)
        ]
        assert actual_results[1].missing_materials == ("material-2",)
        assert actual_results[15].unresolved_semantics == ("semantic-16",)
        assert actual_results[0].evidence_locators[0].quoted_text == "value 1"
    finally:
        second.close()


def test_task_update_survives_repository_restart(db_url: str) -> None:
    first = repositories(db_url)
    task = first.tasks.create(_task(state=TaskState.CREATED))
    updated = task.model_copy(
        update={
            "state": TaskState.FILES_STAGED,
            "active_revision_no": 1,
            "updated_at": datetime(2026, 9, 11, 5, 6, 7, tzinfo=timezone.utc),
        }
    )
    assert first.tasks.update(updated) == updated
    first.close()

    second = repositories(db_url)
    try:
        assert second.tasks.get(TASK_ID) == updated
    finally:
        second.close()


def test_active_decision_survives_restart_can_be_replaced_then_is_frozen(
    db_url: str,
) -> None:
    first = repositories(db_url)
    task = first.tasks.create(_task())
    result = _results(count=1)[0]
    first.results.replace_all(task.id, (result,))
    initial = _decisions((result,), "initial")[0]
    assert first.decisions.save_or_replace(task.id, initial) == initial
    first.close()

    second = repositories(db_url)
    replacement = initial.model_copy(
        update={"id": uuid4(), "reason": "Human review replacement for TR-01"}
    )
    try:
        assert second.decisions.list_for_task(task.id) == (initial,)
        assert second.decisions.save_or_replace(task.id, replacement) == replacement
        assert second.decisions.list_for_task(task.id) == (replacement,)

        revision = second.revisions.complete(task.id, (replacement,))
        assert revision.revision_no == 1
        assert second.decisions.list_for_task(task.id) == (replacement,)
        snapshot = json.loads(revision.result_snapshot)
        assert len(snapshot["decisions"]) == 1
        assert snapshot["decisions"][0]["reason"] == replacement.reason

        attempted_edit = replacement.model_copy(
            update={"id": uuid4(), "reason": "Must not replace frozen decision"}
        )
        with pytest.raises(CompletedRevisionError):
            second.decisions.save_or_replace(task.id, attempted_edit)
        assert second.decisions.list_for_task(task.id) == (replacement,)
    finally:
        second.close()


def test_decision_repository_is_available_through_domain_port(db_url: str) -> None:
    from hw_review.domain import DecisionRepository

    bundle = repositories(db_url)
    try:
        assert isinstance(bundle.decisions, DecisionRepository)
    finally:
        bundle.close()


@pytest.mark.parametrize("invalid_revision_no", [0, 2])
def test_replace_all_rejects_stale_and_future_revisions_without_data_loss(
    db_url: str, invalid_revision_no: int
) -> None:
    bundle = repositories(db_url)
    try:
        task = bundle.tasks.create(_task())
        active_task = task.model_copy(update={"active_revision_no": 1})
        bundle.tasks.update(active_task)
        valid = _results(revision_no=1)
        bundle.results.replace_all(task.id, valid)

        with pytest.raises(RepositoryConflictError):
            bundle.results.replace_all(
                task.id,
                _results(count=1, revision_no=invalid_revision_no),
            )

        assert bundle.results.list_for_task(task.id) == valid
    finally:
        bundle.close()


def test_duplicate_completion_decisions_roll_back_revision_and_association(
    db_url: str,
) -> None:
    bundle = repositories(db_url)
    try:
        task = bundle.tasks.create(_task())
        result = _results(count=1)[0]
        bundle.results.replace_all(task.id, (result,))
        saved = _decisions((result,), "saved")[0]
        bundle.decisions.save_or_replace(task.id, saved)
        duplicate = saved.model_copy(
            update={"id": uuid4(), "reason": "Conflicting decision for same result"}
        )

        with pytest.raises(RepositoryConflictError):
            bundle.revisions.complete(task.id, (saved, duplicate))

        with bundle.engine.connect() as connection:
            assert connection.scalar(select(func.count()).select_from(review_revisions)) == 0
            stored = connection.execute(select(manual_decisions)).one()
            assert stored.revision_id is None
            assert stored.reason == saved.reason
        assert bundle.decisions.list_for_task(task.id) == (saved,)
    finally:
        bundle.close()


def test_database_enforces_active_and_completed_decision_identities(
    db_url: str,
) -> None:
    bundle = repositories(db_url)
    try:
        task = bundle.tasks.create(_task())
        result = _results(count=1)[0]
        bundle.results.replace_all(task.id, (result,))
        decision = _decisions((result,), "database-constraint")[0]
        bundle.decisions.save_or_replace(task.id, decision)
        duplicate_values = {
            "id": str(uuid4()),
            "task_id": str(task.id),
            "rule_result_id": str(result.id),
            "revision_id": None,
            "active_revision_no": 0,
            "final_status": decision.final_status.value,
            "reason": "direct duplicate",
            "supplemental_evidence_json": "[]",
            "actor": "constraint-probe",
            "decided_at": decision.decided_at.isoformat(),
        }
        with pytest.raises(IntegrityError):
            with bundle.engine.begin() as connection:
                connection.execute(manual_decisions.insert(), duplicate_values)

        revision = bundle.revisions.complete(task.id, ())
        duplicate_values.update(
            {
                "id": str(uuid4()),
                "revision_id": str(revision.id),
                "active_revision_no": 99,
            }
        )
        with pytest.raises(IntegrityError):
            with bundle.engine.begin() as connection:
                connection.execute(manual_decisions.insert(), duplicate_values)
    finally:
        bundle.close()


def test_failed_replace_all_keeps_previous_complete_set(db_url: str) -> None:
    bundle = repositories(db_url)
    try:
        bundle.tasks.create(_task())
        previous = _results()
        bundle.results.replace_all(TASK_ID, previous)
        duplicate = previous[0].model_copy(update={"id": uuid4()})

        with pytest.raises(RepositoryConflictError):
            bundle.results.replace_all(TASK_ID, (previous[0], duplicate))

        assert bundle.results.list_for_task(TASK_ID) == previous
    finally:
        bundle.close()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda values: values[:-1],
        lambda values: values[:-1] + (values[0].model_copy(update={"id": uuid4()}),),
        lambda values: values[:-1] + (values[-1].model_copy(update={"rule_id": "TR-05"}),),
        lambda values: values[:-1] + (values[-1].model_copy(update={"rule_id": "TR-99"}),),
    ],
    ids=["missing", "duplicate", "disabled", "unknown"],
)
def test_commit_evaluation_requires_exact_enabled_a11_result_set(db_url: str, mutate) -> None:
    bundle = repositories(db_url)
    try:
        task = bundle.tasks.create(_task(state=TaskState.EVALUATING))
        expected = _enabled_results()
        with pytest.raises(RepositoryConflictError):
            bundle.commit_evaluation(
                task.model_copy(update={"state": TaskState.READY_FOR_REVIEW}),
                mutate(expected),
            )
        assert bundle.results.list_for_task(task.id) == ()
        assert bundle.tasks.get(task.id).state is TaskState.EVALUATING
    finally:
        bundle.close()


def _raise_on_next_statement(engine, prefix: str):
    fired = False

    def fail_once(_connection, _cursor, statement, _parameters, _context, _many):
        nonlocal fired
        if not fired and statement.lstrip().upper().startswith(prefix):
            fired = True
            raise RuntimeError(f"injected transaction failure at {prefix}")

    event.listen(engine, "before_cursor_execute", fail_once)
    return fail_once


def test_commit_evaluation_rolls_back_results_and_state_on_mid_transaction_failure(db_url: str) -> None:
    bundle = repositories(db_url)
    try:
        task = bundle.tasks.create(_task(state=TaskState.EVALUATING))
        previous = _enabled_results()
        bundle.results.replace_all(task.id, previous)
        hook = _raise_on_next_statement(bundle.engine, "INSERT INTO RULE_RESULTS")
        with pytest.raises(RuntimeError, match="INSERT INTO RULE_RESULTS"):
            bundle.commit_evaluation(task.model_copy(update={"state": TaskState.READY_FOR_REVIEW}), _enabled_results())
        event.remove(bundle.engine, "before_cursor_execute", hook)
        assert bundle.results.list_for_task(task.id) == previous
        assert bundle.tasks.get(task.id).state is TaskState.EVALUATING
    finally:
        bundle.close()


def test_commit_failure_rolls_back_results_failure_and_state_on_mid_transaction_failure(db_url: str) -> None:
    bundle = repositories(db_url)
    try:
        task = bundle.tasks.create(_task(state=TaskState.EVALUATING))
        previous = _enabled_results()
        bundle.results.replace_all(task.id, previous)
        failure = StageFailure(id=uuid4(), task_id=task.id, stage="PARSING", code="INJECTED", message="injected", occurred_at=datetime.now(timezone.utc))
        hook = _raise_on_next_statement(bundle.engine, "INSERT INTO STAGE_FAILURES")
        with pytest.raises(RuntimeError, match="INSERT INTO STAGE_FAILURES"):
            bundle.commit_failure(task.model_copy(update={"state": TaskState.FAILED}), failure)
        event.remove(bundle.engine, "before_cursor_execute", hook)
        assert bundle.results.list_for_task(task.id) == previous
        assert bundle.failures.list_for_task(task.id) == ()
        assert bundle.tasks.get(task.id).state is TaskState.EVALUATING
    finally:
        bundle.close()


def test_complete_task_rolls_back_revision_and_state_on_mid_transaction_failure(db_url: str) -> None:
    bundle = repositories(db_url)
    try:
        task = bundle.tasks.create(_task())
        bundle.results.replace_all(task.id, _enabled_results())
        completed = task.model_copy(update={"state": TaskState.COMPLETED})
        hook = _raise_on_next_statement(bundle.engine, "INSERT INTO REVIEW_REVISIONS")
        with pytest.raises(RuntimeError, match="INSERT INTO REVIEW_REVISIONS"):
            bundle.complete_task(completed, (), datetime.now(timezone.utc))
        event.remove(bundle.engine, "before_cursor_execute", hook)
        assert bundle.revisions.list_for_task(task.id) == ()
        assert bundle.tasks.get(task.id).state is TaskState.READY_FOR_REVIEW
    finally:
        bundle.close()


def test_reopen_task_rolls_back_copied_results_and_state_on_mid_transaction_failure(db_url: str) -> None:
    bundle = repositories(db_url)
    try:
        task = bundle.tasks.create(_task(state=TaskState.COMPLETED))
        previous = _enabled_results()
        bundle.results.replace_all(task.id, previous)
        reopened = task.model_copy(update={"state": TaskState.READY_FOR_REVIEW, "active_revision_no": 1})
        hook = _raise_on_next_statement(bundle.engine, "INSERT INTO RULE_RESULTS")
        with pytest.raises(RuntimeError, match="INSERT INTO RULE_RESULTS"):
            bundle.reopen_task(reopened, datetime.now(timezone.utc))
        event.remove(bundle.engine, "before_cursor_execute", hook)
        assert bundle.tasks.get(task.id).active_revision_no == 0
        assert bundle.results.list_for_task(task.id) == previous
    finally:
        bundle.close()


def test_all_task_facts_survive_repository_restart(db_url: str, tmp_path: Path) -> None:
    first = repositories(db_url)
    try:
        task = first.tasks.create(_task())
        source = StagedFile(
            id=uuid4(), task_id=task.id, role=FileRole.PRIMARY_REPORT,
            original_name="restart.xls", detected_format="XLS", path=tmp_path / "staged.xls",
            size_bytes=1, sha256="0" * 64, source_mtime_ns=1,
        )
        first.sources.create(source)
        results = _enabled_results()
        first.results.replace_all(task.id, results)
        decision = _decisions((results[0],), "restart")[0]
        first.decisions.save_or_replace(task.id, decision)
        failure = StageFailure(id=uuid4(), task_id=task.id, stage="CLEANUP", code="CLEANUP_FAILURE", message="retained", occurred_at=datetime.now(timezone.utc))
        first.failures.create(failure)
        revision = first.complete_task(task.model_copy(update={"state": TaskState.COMPLETED}), (decision,), datetime.now(timezone.utc))
    finally:
        first.close()

    second = repositories(db_url)
    try:
        assert second.tasks.get(task.id).state is TaskState.COMPLETED
        assert second.sources.list_for_task(task.id) == (source,)
        assert second.results.list_for_task(task.id) == results
        assert second.decisions.list_for_task(task.id) == (decision,)
        assert second.failures.list_for_task(task.id) == (failure,)
        assert second.revisions.list_for_task(task.id) == (revision,)
    finally:
        second.close()


def test_database_rejects_duplicate_task_rule_revision_identity(db_url: str) -> None:
    bundle = repositories(db_url)
    try:
        bundle.tasks.create(_task())
        result = _results(count=1)[0]
        bundle.results.replace_all(TASK_ID, (result,))
        duplicate = result.model_copy(update={"id": uuid4()})
        with pytest.raises(IntegrityError):
            with bundle.engine.begin() as connection:
                connection.execute(
                    rule_results.insert(),
                    {
                        "id": str(duplicate.id),
                        "task_id": str(duplicate.task_id),
                        "rule_id": duplicate.rule_id,
                        "initial_status": duplicate.initial_status.value,
                        "basis_code": duplicate.basis_code,
                        "basis_text": duplicate.basis_text,
                        "evidence_json": "[]",
                        "diagnostics_json": "{}",
                        "engine_version": duplicate.engine_version,
                        "active_revision_no": duplicate.active_revision_no,
                        "created_at": duplicate.created_at.isoformat(),
                    },
                )
    finally:
        bundle.close()


def test_two_revisions_are_unique_frozen_and_survive_restart(db_url: str) -> None:
    bundle = repositories(db_url)
    task = bundle.tasks.create(_task())
    current_results = _results()
    bundle.results.replace_all(task.id, current_results)

    first_revision = bundle.revisions.complete(task.id, _decisions(current_results, "one"))
    reopened_task = task.model_copy(update={"active_revision_no": 1})
    bundle.tasks.update(reopened_task)
    reopened_results = _results(revision_no=1)
    bundle.results.replace_all(task.id, reopened_results)
    second_revision = bundle.revisions.complete(
        task.id, _decisions(reopened_results, "two")
    )
    assert isinstance(first_revision, ReviewRevision)
    assert (first_revision.revision_no, second_revision.revision_no) == (1, 2)
    original_snapshot = first_revision.result_snapshot
    assert original_snapshot == json.dumps(
        json.loads(original_snapshot), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )

    with pytest.raises(CompletedRevisionError):
        bundle.revisions.update_snapshot(first_revision.id, {"tampered": True})
    assert bundle.revisions.get(first_revision.id).result_snapshot == original_snapshot

    with pytest.raises(IntegrityError):
        with bundle.engine.begin() as connection:
            connection.execute(
                review_revisions.insert(),
                {
                    "id": str(uuid4()),
                    "task_id": str(task.id),
                    "revision_no": 1,
                    "completed_at": "2026-09-11T00:00:00+00:00",
                    "result_snapshot": "{}",
                },
            )
    bundle.close()

    reopened = repositories(db_url)
    try:
        assert reopened.revisions.get(first_revision.id) == first_revision
        assert reopened.revisions.get(second_revision.id) == second_revision
    finally:
        reopened.close()


def test_snapshot_and_structured_columns_are_text_without_json_queries(db_url: str) -> None:
    bundle = repositories(db_url)
    try:
        columns = {
            table_name: {
                column["name"]: type(column["type"]).__name__.upper()
                for column in inspect(bundle.engine).get_columns(table_name)
            }
            for table_name in ("rule_results", "manual_decisions", "review_revisions")
        }
        assert columns["rule_results"]["evidence_json"] == "TEXT"
        assert columns["rule_results"]["diagnostics_json"] == "TEXT"
        assert columns["manual_decisions"]["supplemental_evidence_json"] == "TEXT"
        assert columns["review_revisions"]["result_snapshot"] == "TEXT"
    finally:
        bundle.close()


def test_utc_timestamps_round_trip_as_aware_utc(db_url: str) -> None:
    bundle = repositories(db_url)
    try:
        task = bundle.tasks.create(_task())
        result = _results(count=1)[0]
        bundle.results.replace_all(task.id, (result,))
        loaded_task = bundle.tasks.get(task.id)
        loaded_result = bundle.results.list_for_task(task.id)[0]
        assert loaded_task.created_at.tzinfo is timezone.utc
        assert loaded_task.updated_at.tzinfo is timezone.utc
        assert loaded_result.created_at.tzinfo is timezone.utc
    finally:
        bundle.close()


def test_persisted_models_reject_assignment_and_invalid_model_copy() -> None:
    task = _task()
    result = _results(count=1)[0]
    decision = _decisions((result,), "one")[0]

    for model, field, value in (
        (task, "active_revision_no", -1),
        (result, "rule_id", "  "),
        (decision, "reason", "  "),
    ):
        with pytest.raises(ValidationError):
            setattr(model, field, value)
        with pytest.raises(ValidationError):
            model.model_copy(update={field: value})


def test_metadata_contains_only_application_tables() -> None:
    assert set(metadata.tables) == {
        "tasks",
        "source_files",
        "parse_artifacts",
        "rule_results",
        "manual_decisions",
        "review_revisions",
        "stage_failures",
        "template_versions",
        "template_rules",
        "template_audit_events",
    }


def _template_version(
    *,
    template_id: UUID | None = None,
    version: str = "A12",
    status: TemplateStatus = TemplateStatus.DRAFT,
) -> TemplateVersion:
    created_at = datetime(2026, 9, 17, 8, 0, tzinfo=timezone.utc)
    return TemplateVersion(
        id=template_id or uuid4(),
        name="硬件测试过程检查单",
        version=version,
        status=status,
        source_filename=f"checklist-{version}.xls",
        source_path=Path(f"templates/{version}/source.xls"),
        source_sha256="a" * 64,
        source_size_bytes=4096,
        source_mtime_ns=123456,
        source_rows=22,
        effective_rules=1,
        validation_findings=(
            TemplateValidationFinding(
                code="SEMANTIC_CRITERIA_MISSING",
                severity="WARNING",
                message="缺少语义判定标准，审核时将进入待人工确认。",
                structural_address="硬件测试过程检查表!B27",
            ),
        ),
        created_by="模板管理员",
        created_at=created_at,
        updated_at=created_at,
        published_at=None,
    )


def _template_rule(template_id: UUID, *, rule_id: str = "TR-01") -> TemplateRule:
    timestamp = datetime(2026, 9, 17, 8, 1, tzinfo=timezone.utc)
    return TemplateRule(
        id=uuid4(),
        template_id=template_id,
        rule_id=rule_id,
        source_row=10,
        source_sequence=1,
        summary="JIRA项目及链接",
        verifiable_requirement="JIRA项目已建立；报告包含对应链接",
        required_materials="JIRA页面截图/导出件、报告",
        main_judgment="RULE",
        confirmed_boundary="未提供JIRA证据则不符合",
        enabled=True,
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_template_version_rules_and_findings_survive_repository_restart(
    db_url: str,
) -> None:
    template = _template_version()
    rule = _template_rule(template.id)
    first = repositories(db_url)
    try:
        first.templates.create(template, (rule,))
    finally:
        first.close()

    second = repositories(db_url)
    try:
        assert second.templates.get(template.id) == template
        assert second.templates.list_rules(template.id) == (rule,)
        assert second.templates.list_versions() == (template,)
    finally:
        second.close()


def test_template_repository_rejects_duplicate_name_and_version(db_url: str) -> None:
    template = _template_version()
    bundle = repositories(db_url)
    try:
        bundle.templates.create(template, (_template_rule(template.id),))
        duplicate = _template_version(version=template.version)
        with pytest.raises(RepositoryConflictError):
            bundle.templates.create(duplicate, (_template_rule(duplicate.id),))
        assert bundle.templates.list_versions() == (template,)
    finally:
        bundle.close()


def test_published_template_rules_are_immutable_but_draft_rules_can_change(
    db_url: str,
) -> None:
    template = _template_version()
    rule = _template_rule(template.id)
    bundle = repositories(db_url)
    try:
        bundle.templates.create(template, (rule,))
        changed = rule.model_copy(
            update={
                "summary": "草稿中的新名称",
                "updated_at": datetime(2026, 9, 17, 9, 0, tzinfo=timezone.utc),
            }
        )
        assert bundle.templates.update_rule(changed) == changed
        published = template.model_copy(
            update={
                "status": TemplateStatus.PUBLISHED,
                "updated_at": datetime(2026, 9, 17, 9, 1, tzinfo=timezone.utc),
                "published_at": datetime(2026, 9, 17, 9, 1, tzinfo=timezone.utc),
            }
        )
        bundle.templates.update_version(published)
        with pytest.raises(RepositoryConflictError, match="immutable"):
            bundle.templates.update_rule(
                changed.model_copy(
                    update={
                        "summary": "不得写入",
                        "updated_at": datetime(2026, 9, 17, 9, 2, tzinfo=timezone.utc),
                    }
                )
            )
        assert bundle.templates.list_rules(template.id) == (changed,)
    finally:
        bundle.close()
