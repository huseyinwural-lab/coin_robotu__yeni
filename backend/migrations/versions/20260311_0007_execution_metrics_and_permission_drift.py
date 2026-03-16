"""phase4 execution metrics and permission drift

Revision ID: 20260311_0007
Revises: 20260311_0006
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260311_0007"
down_revision = "20260311_0006"
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

    if _table_exists(bind, "user_exchange_settings"):
        if not _column_exists(bind, "user_exchange_settings", "permissions_snapshot"):
            op.add_column("user_exchange_settings", sa.Column("permissions_snapshot", sa.JSON(), nullable=True))
            op.execute(sa.text("UPDATE user_exchange_settings SET permissions_snapshot = '[]' WHERE permissions_snapshot IS NULL"))
            op.alter_column("user_exchange_settings", "permissions_snapshot", existing_type=sa.JSON(), nullable=False)

        if not _column_exists(bind, "user_exchange_settings", "can_trade_snapshot"):
            op.add_column("user_exchange_settings", sa.Column("can_trade_snapshot", sa.Boolean(), nullable=True))

        if not _column_exists(bind, "user_exchange_settings", "validation_checked_at"):
            op.add_column("user_exchange_settings", sa.Column("validation_checked_at", sa.DateTime(timezone=True), nullable=True))

    if not _table_exists(bind, "execution_metrics"):
        op.create_table(
            "execution_metrics",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("symbol", sa.String(length=20), nullable=False),
            sa.Column("order_id", sa.String(length=80), nullable=False),
            sa.Column("exchange_order_id", sa.String(length=80), nullable=False),
            sa.Column("order_type", sa.String(length=20), nullable=False),
            sa.Column("side", sa.String(length=10), nullable=False),
            sa.Column("quote_qty", sa.Float(), nullable=False),
            sa.Column("mid_price", sa.Float(), nullable=False),
            sa.Column("mid_price_timestamp", sa.String(length=40), nullable=False),
            sa.Column("price_avg", sa.Float(), nullable=True),
            sa.Column("executed_qty", sa.Float(), nullable=True),
            sa.Column("slippage_pct", sa.Float(), nullable=True),
            sa.Column("execution_time_ms", sa.Float(), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("strategy_type", sa.String(length=50), nullable=False),
            sa.Column("volatility_regime", sa.String(length=20), nullable=False),
            sa.Column("volatility_pct", sa.Float(), nullable=False),
            sa.Column("execution_quality_score", sa.Float(), nullable=False),
            sa.Column("state_machine_path", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_execution_metrics_user_id", "execution_metrics", ["user_id"], unique=False)
        op.create_index("ix_execution_metrics_order_id", "execution_metrics", ["order_id"], unique=False)
        op.create_index("ix_execution_metrics_exchange_order_id", "execution_metrics", ["exchange_order_id"], unique=False)

    if not _table_exists(bind, "permission_drift_events"):
        op.create_table(
            "permission_drift_events",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("exchange", sa.String(length=30), nullable=False),
            sa.Column("old_permissions", sa.JSON(), nullable=False),
            sa.Column("new_permissions", sa.JSON(), nullable=False),
            sa.Column("old_can_trade", sa.Boolean(), nullable=True),
            sa.Column("new_can_trade", sa.Boolean(), nullable=True),
            sa.Column("is_critical", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_permission_drift_events_user_id", "permission_drift_events", ["user_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "permission_drift_events"):
        op.drop_index("ix_permission_drift_events_user_id", table_name="permission_drift_events")
        op.drop_table("permission_drift_events")

    if _table_exists(bind, "execution_metrics"):
        op.drop_index("ix_execution_metrics_exchange_order_id", table_name="execution_metrics")
        op.drop_index("ix_execution_metrics_order_id", table_name="execution_metrics")
        op.drop_index("ix_execution_metrics_user_id", table_name="execution_metrics")
        op.drop_table("execution_metrics")

    if _table_exists(bind, "user_exchange_settings"):
        if _column_exists(bind, "user_exchange_settings", "validation_checked_at"):
            op.drop_column("user_exchange_settings", "validation_checked_at")
        if _column_exists(bind, "user_exchange_settings", "can_trade_snapshot"):
            op.drop_column("user_exchange_settings", "can_trade_snapshot")
        if _column_exists(bind, "user_exchange_settings", "permissions_snapshot"):
            op.drop_column("user_exchange_settings", "permissions_snapshot")