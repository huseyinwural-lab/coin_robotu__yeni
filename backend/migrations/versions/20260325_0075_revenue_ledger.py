"""revenue ledger table for commercial ops p1

Revision ID: 20260325_0075
Revises: 20260325_0074
Create Date: 2026-03-25
"""

from alembic import op
import sqlalchemy as sa


revision = "20260325_0075"
down_revision = "20260325_0074"
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "revenue_ledger"):
        return

    op.create_table(
        "revenue_ledger",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("trade_id", sa.String(), sa.ForeignKey("commercial_trades.id"), nullable=False),
        sa.Column("exchange", sa.String(length=30), nullable=False, server_default="binance"),
        sa.Column("market_type", sa.String(length=20), nullable=False, server_default="spot"),
        sa.Column("environment", sa.String(length=20), nullable=False, server_default="live"),
        sa.Column("symbol", sa.String(length=30), nullable=False, server_default=""),
        sa.Column("trade_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("component_type", sa.String(length=30), nullable=False, server_default="fee"),
        sa.Column("source_amount_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("share_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("revenue_amount_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("trade_id", "component_type", name="uq_revenue_ledger_trade_component"),
    )

    for name, cols in [
        ("ix_revenue_ledger_user_id", ["user_id"]),
        ("ix_revenue_ledger_trade_id", ["trade_id"]),
        ("ix_revenue_ledger_exchange", ["exchange"]),
        ("ix_revenue_ledger_market_type", ["market_type"]),
        ("ix_revenue_ledger_environment", ["environment"]),
        ("ix_revenue_ledger_symbol", ["symbol"]),
        ("ix_revenue_ledger_trade_time", ["trade_time"]),
        ("ix_revenue_ledger_component_type", ["component_type"]),
        ("ix_revenue_ledger_revenue_amount_usd", ["revenue_amount_usd"]),
    ]:
        op.create_index(name, "revenue_ledger", cols)


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "revenue_ledger"):
        op.drop_table("revenue_ledger")
