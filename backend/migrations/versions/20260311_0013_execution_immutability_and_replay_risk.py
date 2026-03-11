"""execution immutability events and replay risk tables

Revision ID: 20260311_0013
Revises: 20260311_0012
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260311_0013"
down_revision = "20260311_0012"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "execution_correction_events"):
        op.create_table(
            "execution_correction_events",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("execution_metric_id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("correction_type", sa.String(length=40), nullable=False, server_default="annotation"),
            sa.Column("reason_code", sa.String(length=40), nullable=False, server_default="manual_correction"),
            sa.Column("note", sa.Text(), nullable=False, server_default=""),
            sa.Column("patch_payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["execution_metric_id"], ["execution_metrics.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_execution_correction_events_execution_metric_id", "execution_correction_events", ["execution_metric_id"], unique=False)
        op.create_index("ix_execution_correction_events_user_id", "execution_correction_events", ["user_id"], unique=False)

    if not _table_exists(bind, "replay_equity_points"):
        op.create_table(
            "replay_equity_points",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("replay_run_id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("point_timestamp", sa.String(length=40), nullable=False),
            sa.Column("equity", sa.Float(), nullable=False),
            sa.Column("pnl_delta", sa.Float(), nullable=False),
            sa.Column("drawdown_pct", sa.Float(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["replay_run_id"], ["replay_runs.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_replay_equity_points_replay_run_id", "replay_equity_points", ["replay_run_id"], unique=False)
        op.create_index("ix_replay_equity_points_user_id", "replay_equity_points", ["user_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "replay_equity_points"):
        op.drop_index("ix_replay_equity_points_user_id", table_name="replay_equity_points")
        op.drop_index("ix_replay_equity_points_replay_run_id", table_name="replay_equity_points")
        op.drop_table("replay_equity_points")

    if _table_exists(bind, "execution_correction_events"):
        op.drop_index("ix_execution_correction_events_user_id", table_name="execution_correction_events")
        op.drop_index("ix_execution_correction_events_execution_metric_id", table_name="execution_correction_events")
        op.drop_table("execution_correction_events")
