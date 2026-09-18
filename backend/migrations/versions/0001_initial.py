"""Create the initial local-review persistence schema.

Revision ID: 0001
Revises:
Create Date: 2026-09-11
"""

from alembic import op
import sqlalchemy as sa


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("active_revision_no", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("template_version", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("execution_claim", sa.String(length=36), nullable=True),
        sa.CheckConstraint(
            "state IN ('CREATED', 'FILES_STAGED', 'PARSING', 'PARSED', "
            "'EVALUATING', 'READY_FOR_REVIEW', 'COMPLETED', 'FAILED')",
            name="ck_tasks_state",
        ),
        sa.CheckConstraint("active_revision_no >= 0", name="ck_tasks_active_revision_no"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "source_files",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("evidence_kinds_json", sa.Text(), nullable=False),
        sa.Column("original_name", sa.Text(), nullable=False),
        sa.Column("detected_format", sa.String(length=8), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("source_mtime_ns", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "role IN ('PRIMARY_REPORT', 'SUPPORTING_EVIDENCE')",
            name="ck_source_files_role",
        ),
        sa.CheckConstraint("size_bytes >= 0", name="ck_source_files_size_bytes"),
        sa.CheckConstraint("source_mtime_ns >= 0", name="ck_source_files_mtime"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "parse_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("source_file_id", sa.String(length=36), nullable=False),
        sa.Column("parser_version", sa.Text(), nullable=False),
        sa.Column("artifact_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["source_file_id"], ["source_files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "rule_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("rule_id", sa.String(length=32), nullable=False),
        sa.Column("initial_status", sa.String(length=32), nullable=False),
        sa.Column("basis_code", sa.Text(), nullable=False),
        sa.Column("basis_text", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("diagnostics_json", sa.Text(), nullable=False),
        sa.Column("engine_version", sa.Text(), nullable=False),
        sa.Column("active_revision_no", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "initial_status IN ('COMPLIANT', 'NON_COMPLIANT', "
            "'NOT_APPLICABLE', 'NEEDS_REVIEW')",
            name="ck_rule_results_initial_status",
        ),
        sa.CheckConstraint("active_revision_no >= 0", name="ck_rule_results_revision_no"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_id",
            "rule_id",
            "active_revision_no",
            name="uq_rule_results_task_rule_revision",
        ),
    )
    op.create_table(
        "review_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.Text(), nullable=False),
        sa.Column("result_snapshot", sa.Text(), nullable=False),
        sa.CheckConstraint("revision_no >= 1", name="ck_review_revisions_revision_no"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_id", "revision_no", name="uq_review_revisions_task_revision"
        ),
    )
    op.create_table(
        "manual_decisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("rule_result_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=True),
        sa.Column("active_revision_no", sa.Integer(), nullable=False),
        sa.Column("final_status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("supplemental_evidence_json", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("decided_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "final_status IN ('COMPLIANT', 'NON_COMPLIANT', 'NOT_APPLICABLE')",
            name="ck_manual_decisions_final_status",
        ),
        sa.CheckConstraint(
            "active_revision_no >= 0", name="ck_manual_decisions_active_revision_no"
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["review_revisions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["rule_result_id"], ["rule_results.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "revision_id",
            "rule_result_id",
            name="uq_manual_decisions_completed_revision_result",
        ),
        sa.UniqueConstraint(
            "task_id",
            "rule_result_id",
            "active_revision_no",
            name="uq_manual_decisions_task_result_active_revision",
        ),
    )
    op.create_table(
        "stage_failures",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("stage_failures")
    op.drop_table("manual_decisions")
    op.drop_table("review_revisions")
    op.drop_table("rule_results")
    op.drop_table("parse_artifacts")
    op.drop_table("source_files")
    op.drop_table("tasks")
