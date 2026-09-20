"""Add append-only template operation audit events.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-18
"""

from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "template_audit_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("template_id", sa.String(length=36), sa.ForeignKey("template_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("template_version", sa.Text(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("rule_id", sa.String(length=32), nullable=True),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.Text(), nullable=False),
        sa.Column("before_json", sa.Text(), nullable=True),
        sa.Column("after_json", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "action IN ('TEMPLATE_UPLOADED','RULE_CREATED','RULE_UPDATED','RULE_DELETED','TEMPLATE_PUBLISHED','TEMPLATE_RETIRED')",
            name="ck_template_audit_events_action",
        ),
        sa.CheckConstraint(
            "before_json IS NOT NULL OR after_json IS NOT NULL",
            name="ck_template_audit_events_snapshot",
        ),
    )
    op.create_index(
        "ix_template_audit_events_template_time",
        "template_audit_events",
        ["template_id", "occurred_at"],
    )
    op.create_index(
        "ix_template_audit_events_template_rule",
        "template_audit_events",
        ["template_id", "rule_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_template_audit_events_template_rule", table_name="template_audit_events")
    op.drop_index("ix_template_audit_events_template_time", table_name="template_audit_events")
    op.drop_table("template_audit_events")
