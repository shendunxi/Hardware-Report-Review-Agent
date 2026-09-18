"""Freeze the selected template and rules on each review task.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-17
"""

from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("template_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("template_name", sa.Text(), nullable=True))
        batch.add_column(sa.Column("template_source_path", sa.Text(), nullable=True))
        batch.add_column(sa.Column("template_source_sha256", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("template_rules_snapshot", sa.Text(), nullable=True))
    op.execute("UPDATE tasks SET template_name = '硬件测试过程检查单', template_rules_snapshot = '[]' WHERE template_name IS NULL")


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.drop_column("template_rules_snapshot")
        batch.drop_column("template_source_sha256")
        batch.drop_column("template_source_path")
        batch.drop_column("template_name")
        batch.drop_column("template_id")
