"""Public persistence adapter surface."""

from .repositories import (
    CompletedRevisionError,
    RepositoryBundle,
    RepositoryConflictError,
    InvalidEvaluationResultSetError,
    RepositoryError,
    RepositoryNotFoundError,
    SqliteDecisionRepository,
    SqliteResultRepository,
    SqliteRevisionRepository,
    SqliteTaskRepository,
    SqliteSourceFileRepository,
    SqliteStageFailureRepository,
    SqliteTemplateRepository,
    SqliteTemplateAuditRepository,
    repositories,
)

__all__ = [
    "CompletedRevisionError",
    "RepositoryBundle",
    "RepositoryConflictError",
    "InvalidEvaluationResultSetError",
    "RepositoryError",
    "RepositoryNotFoundError",
    "SqliteDecisionRepository",
    "SqliteResultRepository",
    "SqliteRevisionRepository",
    "SqliteTaskRepository",
    "SqliteSourceFileRepository",
    "SqliteStageFailureRepository",
    "SqliteTemplateRepository",
    "SqliteTemplateAuditRepository",
    "repositories",
]
