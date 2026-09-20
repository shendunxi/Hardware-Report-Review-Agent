"""Application lifecycle rules independent from HTTP and SQLite SQL."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from hw_review.domain import FinalStatus, ManualDecision, ReviewStatus, ReviewTask, StageFailure, TaskState
from hw_review.persistence import InvalidEvaluationResultSetError, RepositoryConflictError, RepositoryNotFoundError
from hw_review.services.cleanup import WorkspaceCleaner
from hw_review.services.evaluation import EvaluationError, EvaluationService
from hw_review.services.staging import FileStager, StageError
from hw_review.services.template_binding import enabled_rule_ids, serialize_rules


class LifecycleError(Exception):
    """Stable business failure exposed by the API error mapper."""

    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        self.code, self.details = code, details or {}
        super().__init__(message)


_NEXT = {
    TaskState.CREATED: TaskState.FILES_STAGED,
    TaskState.FILES_STAGED: TaskState.PARSING,
    TaskState.PARSING: TaskState.PARSED,
    TaskState.PARSED: TaskState.EVALUATING,
    TaskState.EVALUATING: TaskState.READY_FOR_REVIEW,
}


class LifecycleService:
    """Owns task creation, ordered execution, manual review, completion and reopen."""

    def __init__(
        self,
        bundle,
        stager: FileStager,
        evaluator: EvaluationService,
        cleaner: WorkspaceCleaner,
        execution_lease_seconds: int = 1800,
    ) -> None:
        if execution_lease_seconds <= 0:
            raise ValueError("execution lease must be positive")
        self._bundle, self._stager, self._evaluator, self._cleaner = bundle, stager, evaluator, cleaner
        self._execution_lease_seconds = execution_lease_seconds

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def create(
        self,
        display_name: str,
        files: tuple[tuple[Path, object], ...],
        *,
        task_id: UUID | None = None,
        template=None,
        template_rules: tuple = (),
    ) -> tuple[ReviewTask, tuple]:
        now, task_id = self._now(), task_id or uuid4()
        binding = (
            {
                "template_id": template.id,
                "template_name": template.name,
                "template_version": template.version,
                "template_source_path": template.source_path,
                "template_source_sha256": template.source_sha256,
                "template_rules_snapshot": serialize_rules(tuple(template_rules)),
            }
            if template is not None
            else {"template_version": "A11"}
        )
        task = ReviewTask(id=task_id, state=TaskState.CREATED, active_revision_no=0, display_name=display_name,
                          created_at=now, updated_at=now, **binding)
        self._bundle.tasks.create(task)
        staged = []
        try:
            for ingress, metadata in files:
                source = self._stager.stage(ingress, task_id, metadata)
                self._bundle.sources.create(source)
                staged.append(source)
        except StageError as error:
            self._fail(task, "STAGING", error.code, str(error))
            raise LifecycleError("INVALID_UPLOAD", "upload could not be safely staged", {"stage_code": error.code}) from error
        return task, tuple(staged)

    def _transition(self, task: ReviewTask, state: TaskState) -> ReviewTask:
        if _NEXT.get(task.state) is not state:
            raise LifecycleError("INVALID_TASK_STATE", "invalid task state transition", {"state": task.state.value})
        current = task.model_copy(update={"state": state, "updated_at": self._now()})
        self._bundle.tasks.update(current)
        return current

    def request_execution(self, task_id: UUID) -> tuple[ReviewTask, bool]:
        task = self.get(task_id)
        if task.state in {TaskState.READY_FOR_REVIEW, TaskState.COMPLETED}:
            return task, False
        if task.state is TaskState.FAILED:
            raise LifecycleError("INVALID_TASK_STATE", "failed tasks require a new upload", {"state": task.state.value})
        claimed = self._bundle.tasks.claim_execution(
            task_id, now=self._now(), lease_seconds=self._execution_lease_seconds
        )
        return (claimed or self.get(task_id)), claimed is not None

    _INTERRUPTED_STATES = frozenset(
        {
            TaskState.FILES_STAGED,
            TaskState.PARSING,
            TaskState.PARSED,
            TaskState.EVALUATING,
        }
    )

    def execution_status(
        self, task: ReviewTask, now: datetime | None = None
    ) -> dict | None:
        """Report whether an interrupted execution may be reclaimed. Read-only.

        This is the single implementation of the lease arithmetic: the API payload
        and ``inspect_interrupted`` both read it, so no client has to re-derive the
        rule for itself.
        """

        if task.state not in self._INTERRUPTED_STATES:
            return None
        moment = now or self._now()
        remaining = max(
            0.0,
            self._execution_lease_seconds - (moment - task.updated_at).total_seconds(),
        )
        return {
            "reclaimable": remaining <= 0,
            "seconds_until_reclaimable": int(remaining),
        }

    def inspect_interrupted(self, now: datetime | None = None) -> list[dict]:
        """Report executions that were interrupted. Performs no writes.

        Startup must not silently rewrite task state, because in a multi-worker
        deployment a peer may still own the task. The abandoned claim is only
        surfaced here, and becomes reclaimable on its own once the lease expires.
        """

        moment = now or self._now()
        interrupted: list[dict] = []
        for task in self._bundle.tasks.list_recent():
            status = self.execution_status(task, moment)
            if status is None:
                continue
            interrupted.append(
                {
                    "task_id": task.id,
                    "state": task.state.value,
                    "seconds_since_progress": round(
                        (moment - task.updated_at).total_seconds(), 3
                    ),
                    "seconds_until_reclaimable": status["seconds_until_reclaimable"],
                }
            )
        return interrupted

    def execute(self, task_id: UUID) -> ReviewTask:
        task, claimed = self.request_execution(task_id)
        if not claimed:
            return task
        return self.execute_claimed(task_id)

    def execute_claimed(self, task_id: UUID) -> ReviewTask:
        task = self.get(task_id)
        if task.state is not TaskState.FILES_STAGED:
            return task
        try:
            task = self._transition(task, TaskState.PARSING)
            task = self._transition(task, TaskState.PARSED)
            task = self._transition(task, TaskState.EVALUATING)
            results = self._evaluator.evaluate(task, self._bundle.sources.list_for_task(task.id))
            ready = task.model_copy(update={"state": TaskState.READY_FOR_REVIEW, "updated_at": self._now()})
            try:
                self._bundle.commit_evaluation(ready, results)
            except InvalidEvaluationResultSetError as error:
                self._fail(task, "EVALUATING", error.code, str(error))
                raise LifecycleError("STAGE_FAILURE", "task execution failed", {"stage": "EVALUATING", "code": error.code}) from error
            except RepositoryConflictError as error:
                self._fail(task, "EVALUATING", "RESULT_COMMIT_CONFLICT", str(error))
                raise LifecycleError("STAGE_FAILURE", "task execution failed", {"stage": "EVALUATING", "code": "RESULT_COMMIT_CONFLICT"}) from error
            return ready
        except EvaluationError as error:
            self._fail(task, error.stage, error.code, str(error))
            raise LifecycleError("STAGE_FAILURE", "task execution failed", {"stage": error.stage, "code": error.code}) from error

    def _cleanup_or_record(self, task_id: UUID, operation: str) -> None:
        try:
            self._cleaner.clean_task(task_id)
        except Exception as error:
            self._bundle.failures.create(StageFailure(id=uuid4(), task_id=task_id, stage="CLEANUP", code="CLEANUP_FAILURE", message=f"{operation} cleanup failed: {error}", occurred_at=self._now()))

    def _fail(self, task: ReviewTask, stage: str, code: str, message: str) -> None:
        failed = task.model_copy(update={"state": TaskState.FAILED, "updated_at": self._now()})
        failure = StageFailure(id=uuid4(), task_id=task.id, stage=stage, code=code, message=message, occurred_at=self._now())
        self._bundle.commit_failure(failed, failure)
        self._cleanup_or_record(task.id, "failure")

    def get(self, task_id: UUID) -> ReviewTask:
        try:
            return self._bundle.tasks.get(task_id)
        except RepositoryNotFoundError as error:
            raise LifecycleError("TASK_NOT_FOUND", "task was not found") from error

    def detail(self, task_id: UUID) -> dict:
        task = self.get(task_id)
        results = self._bundle.results.list_for_task(task_id)
        decisions = self._bundle.decisions.list_for_task(task_id)
        return {"task": task, "source_files": self._bundle.sources.list_for_task(task_id), "stage_failures": self._bundle.failures.list_for_task(task_id), "rule_results": results, "manual_decisions": decisions, "revisions": self._bundle.revisions.list_for_task(task_id)}

    def save_decision(
        self,
        task_id: UUID,
        rule_id: str,
        final_status: str,
        reason: str,
        actor: str,
        supplemental_evidence=(),
    ) -> ManualDecision:
        task = self.get(task_id)
        if task.state is not TaskState.READY_FOR_REVIEW:
            raise LifecycleError("INVALID_TASK_STATE", "manual decisions require a ready task", {"state": task.state.value})
        try:
            active_rule_ids = enabled_rule_ids(task)
        except ValueError as error:
            raise LifecycleError("INVALID_RULE", "任务绑定的规则快照无效。") from error
        if rule_id not in active_rule_ids:
            raise LifecycleError("INVALID_RULE", "rule is not active in the task template")
        if not reason or not reason.strip():
            raise LifecycleError("INVALID_REASON", "manual decision reason is required")
        trusted_actor = actor.strip()
        if not trusted_actor:
            raise LifecycleError("AUTHENTICATION_REQUIRED", "manual decision actor is required")
        try:
            status = FinalStatus(final_status)
        except ValueError as error:
            raise LifecycleError("INVALID_STATUS", "manual final status is invalid") from error
        result = next((item for item in self._bundle.results.list_for_task(task_id) if item.rule_id == rule_id), None)
        if result is None:
            raise LifecycleError("INVALID_RULE", "rule result is not available")
        decision = ManualDecision(id=uuid4(), rule_result_id=result.id, final_status=status, reason=reason,
                                  supplemental_evidence=tuple(supplemental_evidence), actor=trusted_actor, decided_at=self._now())
        return self._bundle.decisions.save_or_replace(task_id, decision)

    def complete(self, task_id: UUID):
        task = self.get(task_id)
        if task.state is not TaskState.READY_FOR_REVIEW:
            raise LifecycleError("INVALID_TASK_STATE", "completion requires a ready task", {"state": task.state.value})
        results = self._bundle.results.list_for_task(task_id)
        decisions = self._bundle.decisions.list_for_task(task_id)
        decided = {item.rule_result_id for item in decisions}
        remaining = sum(1 for result in results if result.initial_status is ReviewStatus.NEEDS_REVIEW and result.id not in decided)
        if remaining:
            raise LifecycleError("UNRESOLVED_REVIEW_ITEMS", "仍有待人工确认项", {"remaining": remaining})
        completed = task.model_copy(update={"state": TaskState.COMPLETED, "updated_at": self._now()})
        revision = self._bundle.complete_task(completed, decisions, self._now())
        self._cleanup_or_record(task_id, "completion")
        return completed, revision

    def reopen(self, task_id: UUID) -> ReviewTask:
        task = self.get(task_id)
        if task.state is not TaskState.COMPLETED:
            raise LifecycleError("INVALID_TASK_STATE", "reopen requires a completed task", {"state": task.state.value})
        reopened = task.model_copy(update={"state": TaskState.READY_FOR_REVIEW, "active_revision_no": task.active_revision_no + 1, "updated_at": self._now()})
        self._bundle.reopen_task(reopened, self._now())
        return reopened
