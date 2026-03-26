"""runtime smoke runs table

Revision ID: 20260326_0080
Revises: 20260326_0079
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20260326_0080"
down_revision = "20260326_0079"
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "runtime_smoke_runs"):
        return

    op.create_table(
        "runtime_smoke_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="PASS"),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("steps", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("trigger_source", sa.String(length=40), nullable=False, server_default="manual"),
        sa.Column("report_path", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_runtime_smoke_runs_status", "runtime_smoke_runs", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "runtime_smoke_runs"):
        op.drop_table("runtime_smoke_runs")
