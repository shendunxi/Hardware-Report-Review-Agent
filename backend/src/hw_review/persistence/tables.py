"""Database-neutral SQLAlchemy Core schema for local persistence."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

from hw_review.domain.enums import FileRole, FinalStatus, ReviewStatus, TaskState, TemplateAuditAction, TemplateStatus


metadata = MetaData()


def _enum_check(column_name: str, values: tuple[str, ...], name: str) -> CheckConstraint:
    literals = ", ".join(repr(value) for value in values)
    return CheckConstraint(f"{column_name} IN ({literals})", name=name)


tasks = Table(
    "tasks",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("state", String(32), nullable=False),
    Column("active_revision_no", Integer, nullable=False),
    Column("display_name", Text, nullable=False),
    Column("template_version", Text, nullable=False),
    Column("template_id", String(36), nullable=True),
    Column("template_name", Text, nullable=True),
    Column("template_source_path", Text, nullable=True),
    Column("template_source_sha256", String(64), nullable=True),
    Column("template_rules_snapshot", Text, nullable=True),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Column("execution_claim", String(36), nullable=True),
    _enum_check("state", tuple(item.value for item in TaskState), "ck_tasks_state"),
    CheckConstraint("active_revision_no >= 0", name="ck_tasks_active_revision_no"),
)

source_files = Table(
    "source_files",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("task_id", String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
    Column("role", String(32), nullable=False),
    Column("evidence_kinds_json", Text, nullable=False),
    Column("original_name", Text, nullable=False),
    Column("detected_format", String(8), nullable=False),
    Column("path", Text, nullable=False),
    Column("size_bytes", Integer, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("source_mtime_ns", Integer, nullable=False),
    _enum_check("role", tuple(item.value for item in FileRole), "ck_source_files_role"),
    CheckConstraint("size_bytes >= 0", name="ck_source_files_size_bytes"),
    CheckConstraint("source_mtime_ns >= 0", name="ck_source_files_mtime"),
)

parse_artifacts = Table(
    "parse_artifacts",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("task_id", String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
    Column(
        "source_file_id",
        String(36),
        ForeignKey("source_files.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("parser_version", Text, nullable=False),
    Column("artifact_json", Text, nullable=False),
    Column("created_at", Text, nullable=False),
)

rule_results = Table(
    "rule_results",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("task_id", String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
    Column("rule_id", String(32), nullable=False),
    Column("initial_status", String(32), nullable=False),
    Column("basis_code", Text, nullable=False),
    Column("basis_text", Text, nullable=False),
    Column("evidence_json", Text, nullable=False),
    Column("diagnostics_json", Text, nullable=False),
    Column("engine_version", Text, nullable=False),
    Column("active_revision_no", Integer, nullable=False),
    Column("created_at", Text, nullable=False),
    _enum_check(
        "initial_status",
        tuple(item.value for item in ReviewStatus),
        "ck_rule_results_initial_status",
    ),
    CheckConstraint("active_revision_no >= 0", name="ck_rule_results_revision_no"),
    UniqueConstraint(
        "task_id",
        "rule_id",
        "active_revision_no",
        name="uq_rule_results_task_rule_revision",
    ),
)

review_revisions = Table(
    "review_revisions",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("task_id", String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
    Column("revision_no", Integer, nullable=False),
    Column("completed_at", Text, nullable=False),
    Column("result_snapshot", Text, nullable=False),
    CheckConstraint("revision_no >= 1", name="ck_review_revisions_revision_no"),
    UniqueConstraint("task_id", "revision_no", name="uq_review_revisions_task_revision"),
)

manual_decisions = Table(
    "manual_decisions",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("task_id", String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
    Column(
        "rule_result_id",
        String(36),
        ForeignKey("rule_results.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "revision_id",
        String(36),
        ForeignKey("review_revisions.id", ondelete="CASCADE"),
        nullable=True,
    ),
    Column("active_revision_no", Integer, nullable=False),
    Column("final_status", String(32), nullable=False),
    Column("reason", Text, nullable=False),
    Column("supplemental_evidence_json", Text, nullable=False),
    Column("actor", Text, nullable=False),
    Column("decided_at", Text, nullable=False),
    _enum_check(
        "final_status",
        tuple(item.value for item in FinalStatus),
        "ck_manual_decisions_final_status",
    ),
    CheckConstraint(
        "active_revision_no >= 0", name="ck_manual_decisions_active_revision_no"
    ),
    UniqueConstraint(
        "task_id",
        "rule_result_id",
        "active_revision_no",
        name="uq_manual_decisions_task_result_active_revision",
    ),
    UniqueConstraint(
        "revision_id",
        "rule_result_id",
        name="uq_manual_decisions_completed_revision_result",
    ),
)

stage_failures = Table(
    "stage_failures",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("task_id", String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
    Column("stage", Text, nullable=False),
    Column("code", Text, nullable=False),
    Column("message", Text, nullable=False),
    Column("occurred_at", Text, nullable=False),
)

template_versions = Table(
    "template_versions",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("name", Text, nullable=False),
    Column("version", Text, nullable=False),
    Column("status", String(32), nullable=False),
    Column("source_filename", Text, nullable=False),
    Column("source_path", Text, nullable=False),
    Column("source_sha256", String(64), nullable=False),
    Column("source_size_bytes", Integer, nullable=False),
    Column("source_mtime_ns", Integer, nullable=False),
    Column("source_rows", Integer, nullable=False),
    Column("effective_rules", Integer, nullable=False),
    Column("validation_json", Text, nullable=False),
    Column("created_by", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Column("published_at", Text, nullable=True),
    _enum_check("status", tuple(item.value for item in TemplateStatus), "ck_template_versions_status"),
    CheckConstraint("source_size_bytes >= 0", name="ck_template_versions_size"),
    CheckConstraint("source_mtime_ns >= 0", name="ck_template_versions_mtime"),
    CheckConstraint("source_rows >= 0", name="ck_template_versions_source_rows"),
    CheckConstraint("effective_rules >= 0", name="ck_template_versions_effective_rules"),
    UniqueConstraint("name", "version", name="uq_template_versions_name_version"),
)

template_rules = Table(
    "template_rules",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("template_id", String(36), ForeignKey("template_versions.id", ondelete="CASCADE"), nullable=False),
    Column("rule_id", String(32), nullable=False),
    Column("source_row", Integer, nullable=True),
    Column("source_sequence", Integer, nullable=False),
    Column("summary", Text, nullable=False),
    Column("verifiable_requirement", Text, nullable=False),
    Column("required_materials", Text, nullable=False),
    Column("main_judgment", String(32), nullable=False),
    Column("confirmed_boundary", Text, nullable=False),
    Column("enabled", Integer, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    CheckConstraint("source_row IS NULL OR source_row >= 1", name="ck_template_rules_source_row"),
    CheckConstraint("source_sequence >= 1", name="ck_template_rules_sequence"),
    CheckConstraint("enabled IN (0, 1)", name="ck_template_rules_enabled"),
    CheckConstraint("main_judgment IN ('RULE','RULE_PLUS_AI','AI','MANUAL','DISABLED')", name="ck_template_rules_judgment"),
    UniqueConstraint("template_id", "rule_id", name="uq_template_rules_template_rule"),
    UniqueConstraint("template_id", "source_sequence", name="uq_template_rules_template_sequence"),
)

template_audit_events = Table(
    "template_audit_events",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("template_id", String(36), ForeignKey("template_versions.id", ondelete="RESTRICT"), nullable=False),
    Column("template_version", Text, nullable=False),
    Column("action", String(32), nullable=False),
    Column("rule_id", String(32), nullable=True),
    Column("actor", Text, nullable=False),
    Column("occurred_at", Text, nullable=False),
    Column("before_json", Text, nullable=True),
    Column("after_json", Text, nullable=True),
    _enum_check("action", tuple(item.value for item in TemplateAuditAction), "ck_template_audit_events_action"),
    CheckConstraint("before_json IS NOT NULL OR after_json IS NOT NULL", name="ck_template_audit_events_snapshot"),
)

Index("ix_template_audit_events_template_time", template_audit_events.c.template_id, template_audit_events.c.occurred_at)
Index("ix_template_audit_events_template_rule", template_audit_events.c.template_id, template_audit_events.c.rule_id)
