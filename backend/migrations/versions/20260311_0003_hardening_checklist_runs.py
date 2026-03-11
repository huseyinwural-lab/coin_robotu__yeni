"""hardening checklist run table

Revision ID: 20260311_0003
Revises: 20260311_0002
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260311_0003"
down_revision = "20260311_0002"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "hardening_checklist_runs"):
        op.create_table(
            "hardening_checklist_runs",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("score", sa.Float(), nullable=False),
            sa.Column("critical_blocked", sa.Boolean(), nullable=False),
            sa.Column("readiness_status", sa.String(length=20), nullable=False),
            sa.Column("checklist_items", sa.JSON(), nullable=False),
            sa.Column("summary", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "hardening_checklist_runs"):
        op.drop_table("hardening_checklist_runs")