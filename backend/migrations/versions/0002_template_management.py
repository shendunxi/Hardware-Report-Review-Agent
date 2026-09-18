"""Add persisted template versions and version-scoped rules.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-17
"""

from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "template_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_filename", sa.Text(), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_size_bytes", sa.Integer(), nullable=False),
        sa.Column("source_mtime_ns", sa.Integer(), nullable=False),
        sa.Column("source_rows", sa.Integer(), nullable=False),
        sa.Column("effective_rules", sa.Integer(), nullable=False),
        sa.Column("validation_json", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("published_at", sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'RETIRED')", name="ck_template_versions_status"),
        sa.CheckConstraint("source_size_bytes >= 0", name="ck_template_versions_size"),
        sa.CheckConstraint("source_mtime_ns >= 0", name="ck_template_versions_mtime"),
        sa.CheckConstraint("source_rows >= 0", name="ck_template_versions_source_rows"),
        sa.CheckConstraint("effective_rules >= 0", name="ck_template_versions_effective_rules"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", name="uq_template_versions_name_version"),
    )
    op.create_table(
        "template_rules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("rule_id", sa.String(length=32), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=True),
        sa.Column("source_sequence", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("verifiable_requirement", sa.Text(), nullable=False),
        sa.Column("required_materials", sa.Text(), nullable=False),
        sa.Column("main_judgment", sa.String(length=32), nullable=False),
        sa.Column("confirmed_boundary", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint("source_row IS NULL OR source_row >= 1", name="ck_template_rules_source_row"),
        sa.CheckConstraint("source_sequence >= 1", name="ck_template_rules_sequence"),
        sa.CheckConstraint("enabled IN (0, 1)", name="ck_template_rules_enabled"),
        sa.CheckConstraint("main_judgment IN ('RULE','RULE_PLUS_AI','AI','MANUAL','DISABLED')", name="ck_template_rules_judgment"),
        sa.ForeignKeyConstraint(["template_id"], ["template_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id", "rule_id", name="uq_template_rules_template_rule"),
        sa.UniqueConstraint("template_id", "source_sequence", name="uq_template_rules_template_sequence"),
    )


def downgrade() -> None:
    op.drop_table("template_rules")
    op.drop_table("template_versions")
