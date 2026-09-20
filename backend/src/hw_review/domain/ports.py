"""Runtime-checkable generic interfaces that isolate domain services from adapters."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol, TypeVar, runtime_checkable
from uuid import UUID

from pydantic import BaseModel

from .enums import EvidenceKind

if TYPE_CHECKING:
    from ..services.semantic_judge import JudgeOutcome, JudgeRequest
    from .models import EvidenceLocator


TStagedFile = TypeVar("TStagedFile", bound=BaseModel, contravariant=True)
TReportDocument = TypeVar("TReportDocument", bound=BaseModel, covariant=True)
TTask = TypeVar("TTask", bound=BaseModel)
TResult = TypeVar("TResult", bound=BaseModel)
TDecision = TypeVar("TDecision", bound=BaseModel, contravariant=True)
TStoredDecision = TypeVar("TStoredDecision", bound=BaseModel)
TRevision = TypeVar("TRevision", bound=BaseModel, covariant=True)
TSnapshot = TypeVar("TSnapshot", bound=BaseModel, contravariant=True)


@runtime_checkable
class DocumentParser(Protocol[TStagedFile, TReportDocument]):
    def parse(self, staged: TStagedFile) -> TReportDocument: ...


@runtime_checkable
class TaskRepository(Protocol[TTask]):
    def create(self, task: TTask) -> TTask: ...

    def get(self, task_id: UUID) -> TTask: ...

    def update(self, task: TTask) -> TTask: ...


@runtime_checkable
class ResultRepository(Protocol[TResult]):
    def replace_all(self, task_id: UUID, results: tuple[TResult, ...]) -> None: ...

    def list_for_task(self, task_id: UUID) -> tuple[TResult, ...]: ...


@runtime_checkable
class DecisionRepository(Protocol[TStoredDecision]):
    def save_or_replace(
        self, task_id: UUID, decision: TStoredDecision
    ) -> TStoredDecision: ...

    def list_for_task(self, task_id: UUID) -> tuple[TStoredDecision, ...]: ...


@runtime_checkable
class RevisionRepository(Protocol[TDecision, TRevision, TSnapshot]):
    def complete(self, task_id: UUID, decisions: tuple[TDecision, ...]) -> TRevision: ...

    def update_snapshot(self, revision_id: UUID, snapshot: TSnapshot) -> TRevision: ...


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...


@runtime_checkable
class DocumentQuery(Protocol):
    def find_text(
        self, patterns: tuple[str, ...]
    ) -> tuple[EvidenceLocator, ...]: ...

    def find_nonempty_labels(
        self, labels: tuple[str, ...]
    ) -> dict[str, EvidenceLocator]: ...

    def has_evidence_kind(self, kind: EvidenceKind) -> bool: ...


@runtime_checkable
class SemanticJudge(Protocol):
    """Decide semantic rules from a normalized report with locally-mapped evidence.

    Implementations must never raise for an individual rule: a failed call has to
    degrade that rule to ``NEEDS_REVIEW`` so an unverifiable verdict is never
    reported as compliance.
    """

    def judge(self, request: JudgeRequest) -> JudgeOutcome: ...
