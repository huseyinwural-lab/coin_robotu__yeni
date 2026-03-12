"""user scanner + signal queue tables

Revision ID: 20260312_0025
Revises: 20260311_0024
Create Date: 2026-03-12
"""

from alembic import op
import sqlalchemy as sa

revision = "20260312_0025"
down_revision = "20260311_0024"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "user_signal_modes"):
        op.create_table(
            "user_signal_modes",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("mode", sa.String(length=20), nullable=False, server_default="ASSISTED"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id"),
        )
        op.create_index("ix_user_signal_modes_user_id", "user_signal_modes", ["user_id"])

    if not _table_exists(bind, "user_scanner_results"):
        op.create_table(
            "user_scanner_results",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("run_id", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("symbol", sa.String(length=30), nullable=False),
            sa.Column("strategy_code", sa.String(length=80), nullable=False, server_default="spot_pullback_v1"),
            sa.Column("signal", sa.String(length=20), nullable=False, server_default="none"),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
            sa.Column("signal_score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("reason_codes", sa.JSON(), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_user_scanner_results_run_id", "user_scanner_results", ["run_id"])
        op.create_index("ix_user_scanner_results_user_id", "user_scanner_results", ["user_id"])
        op.create_index("ix_user_scanner_results_symbol", "user_scanner_results", ["symbol"])
        op.create_index("ix_user_scanner_results_generated_at", "user_scanner_results", ["generated_at"])

    if not _table_exists(bind, "pending_signals"):
        op.create_table(
            "pending_signals",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("signal_id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("symbol", sa.String(length=30), nullable=False),
            sa.Column("strategy_code", sa.String(length=80), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
            sa.Column("mode", sa.String(length=20), nullable=False, server_default="ASSISTED"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("order_position_id", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("decision_note", sa.Text(), nullable=False, server_default=""),
            sa.ForeignKeyConstraint(["order_position_id"], ["paper_positions.id"]),
            sa.ForeignKeyConstraint(["signal_id"], ["signal_events.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_pending_signals_signal_id", "pending_signals", ["signal_id"])
        op.create_index("ix_pending_signals_user_id", "pending_signals", ["user_id"])
        op.create_index("ix_pending_signals_symbol", "pending_signals", ["symbol"])
        op.create_index("ix_pending_signals_status", "pending_signals", ["status"])
        op.create_index("ix_pending_signals_order_position_id", "pending_signals", ["order_position_id"])


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "pending_signals"):
        op.drop_index("ix_pending_signals_order_position_id", table_name="pending_signals")
        op.drop_index("ix_pending_signals_status", table_name="pending_signals")
        op.drop_index("ix_pending_signals_symbol", table_name="pending_signals")
        op.drop_index("ix_pending_signals_user_id", table_name="pending_signals")
        op.drop_index("ix_pending_signals_signal_id", table_name="pending_signals")
        op.drop_table("pending_signals")

    if _table_exists(bind, "user_scanner_results"):
        op.drop_index("ix_user_scanner_results_generated_at", table_name="user_scanner_results")
        op.drop_index("ix_user_scanner_results_symbol", table_name="user_scanner_results")
        op.drop_index("ix_user_scanner_results_user_id", table_name="user_scanner_results")
        op.drop_index("ix_user_scanner_results_run_id", table_name="user_scanner_results")
        op.drop_table("user_scanner_results")

    if _table_exists(bind, "user_signal_modes"):
        op.drop_index("ix_user_signal_modes_user_id", table_name="user_signal_modes")
        op.drop_table("user_signal_modes")