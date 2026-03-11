"""execution context columns and replay engine tables

Revision ID: 20260311_0012
Revises: 20260311_0011
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260311_0012"
down_revision = "20260311_0011"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "execution_metrics"):
        columns_to_add = [
            ("exchange", sa.Column("exchange", sa.String(length=30), nullable=True)),
            ("market_type", sa.Column("market_type", sa.String(length=20), nullable=True)),
            ("environment", sa.Column("environment", sa.String(length=20), nullable=True)),
        ]
        for name, column in columns_to_add:
            if not _column_exists(bind, "execution_metrics", name):
                op.add_column("execution_metrics", column)

        op.execute(sa.text("UPDATE execution_metrics SET exchange = 'binance' WHERE exchange IS NULL"))
        op.execute(sa.text("UPDATE execution_metrics SET market_type = 'futures' WHERE market_type IS NULL"))
        op.execute(sa.text("UPDATE execution_metrics SET environment = 'testnet' WHERE environment IS NULL"))

        with op.batch_alter_table("execution_metrics") as batch_op:
            batch_op.alter_column("exchange", existing_type=sa.String(length=30), nullable=False, server_default="binance")
            batch_op.alter_column("market_type", existing_type=sa.String(length=20), nullable=False, server_default="futures")
            batch_op.alter_column("environment", existing_type=sa.String(length=20), nullable=False, server_default="testnet")

    if not _table_exists(bind, "replay_runs"):
        op.create_table(
            "replay_runs",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("exchange", sa.String(length=30), nullable=False),
            sa.Column("market_type", sa.String(length=20), nullable=False),
            sa.Column("environment", sa.String(length=20), nullable=False),
            sa.Column("symbol", sa.String(length=20), nullable=False),
            sa.Column("timeframe", sa.String(length=10), nullable=False),
            sa.Column("strategy_type", sa.String(length=50), nullable=False),
            sa.Column("candles_processed", sa.Integer(), nullable=False),
            sa.Column("executions_count", sa.Integer(), nullable=False),
            sa.Column("filled_count", sa.Integer(), nullable=False),
            sa.Column("canceled_count", sa.Integer(), nullable=False),
            sa.Column("avg_simulated_latency_ms", sa.Float(), nullable=False),
            sa.Column("avg_simulated_slippage_pct", sa.Float(), nullable=False),
            sa.Column("metrics", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_replay_runs_user_id", "replay_runs", ["user_id"], unique=False)

    if not _table_exists(bind, "replay_executions"):
        op.create_table(
            "replay_executions",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("replay_run_id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("symbol", sa.String(length=20), nullable=False),
            sa.Column("timeframe", sa.String(length=10), nullable=False),
            sa.Column("signal", sa.String(length=20), nullable=False),
            sa.Column("direction", sa.String(length=10), nullable=False),
            sa.Column("market_price", sa.Float(), nullable=False),
            sa.Column("simulated_fill_price", sa.Float(), nullable=True),
            sa.Column("simulated_latency_ms", sa.Float(), nullable=True),
            sa.Column("simulated_slippage_pct", sa.Float(), nullable=True),
            sa.Column("lifecycle", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("risk_tags", sa.JSON(), nullable=False),
            sa.Column("candle_timestamp", sa.String(length=40), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["replay_run_id"], ["replay_runs.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_replay_executions_replay_run_id", "replay_executions", ["replay_run_id"], unique=False)
        op.create_index("ix_replay_executions_user_id", "replay_executions", ["user_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "replay_executions"):
        op.drop_index("ix_replay_executions_user_id", table_name="replay_executions")
        op.drop_index("ix_replay_executions_replay_run_id", table_name="replay_executions")
        op.drop_table("replay_executions")

    if _table_exists(bind, "replay_runs"):
        op.drop_index("ix_replay_runs_user_id", table_name="replay_runs")
        op.drop_table("replay_runs")

    if _table_exists(bind, "execution_metrics"):
        with op.batch_alter_table("execution_metrics") as batch_op:
            if _column_exists(bind, "execution_metrics", "environment"):
                batch_op.drop_column("environment")
            if _column_exists(bind, "execution_metrics", "market_type"):
                batch_op.drop_column("market_type")
            if _column_exists(bind, "execution_metrics", "exchange"):
                batch_op.drop_column("exchange")
