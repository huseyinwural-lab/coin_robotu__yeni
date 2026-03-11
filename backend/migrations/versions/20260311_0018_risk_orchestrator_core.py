"""risk orchestrator core

Revision ID: 20260311_0018
Revises: 20260311_0017
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa

revision = "20260311_0018"
down_revision = "20260311_0017"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns(table_name)}
    return column_name in columns


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "risk_orchestrator_policies"):
        op.create_table(
            "risk_orchestrator_policies",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("reference_equity_usd", sa.Float(), nullable=False),
            sa.Column("account_max_notional_pct", sa.Float(), nullable=False),
            sa.Column("symbol_max_notional_pct", sa.Float(), nullable=False),
            sa.Column("strategy_max_concurrent_positions", sa.Integer(), nullable=False),
            sa.Column("strategy_cooldown_seconds", sa.Integer(), nullable=False),
            sa.Column("max_order_frequency_per_min", sa.Integer(), nullable=False),
            sa.Column("max_order_burst_per_10s", sa.Integer(), nullable=False),
            sa.Column("daily_loss_limit_pct", sa.Float(), nullable=False),
            sa.Column("duplicate_suppression_window_seconds", sa.Integer(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if _table_exists(bind, "execution_intents") and not _column_exists(bind, "execution_intents", "account_id"):
        op.add_column("execution_intents", sa.Column("account_id", sa.String(length=120), nullable=True))
        op.create_index("ix_execution_intents_account_id", "execution_intents", ["account_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "execution_intents") and _column_exists(bind, "execution_intents", "account_id"):
        op.drop_index("ix_execution_intents_account_id", table_name="execution_intents")
        op.drop_column("execution_intents", "account_id")

    if _table_exists(bind, "risk_orchestrator_policies"):
        op.drop_table("risk_orchestrator_policies")
