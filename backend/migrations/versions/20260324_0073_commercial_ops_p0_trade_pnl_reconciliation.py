"""commercial ops p0 trade pnl reconciliation tables

Revision ID: 20260324_0073
Revises: 20260324_0072
Create Date: 2026-03-24
"""

from alembic import op
import sqlalchemy as sa


revision = "20260324_0073"
down_revision = "20260324_0072"
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "commercial_trades"):
        op.create_table(
            "commercial_trades",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("connection_id", sa.String(), sa.ForeignKey("user_exchange_connections.id"), nullable=True),
            sa.Column("exchange", sa.String(length=30), nullable=False, server_default="binance"),
            sa.Column("market_type", sa.String(length=20), nullable=False, server_default="spot"),
            sa.Column("environment", sa.String(length=20), nullable=False, server_default="testnet"),
            sa.Column("symbol", sa.String(length=30), nullable=False),
            sa.Column("base_asset", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("quote_asset", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("side", sa.String(length=10), nullable=False, server_default="BUY"),
            sa.Column("position_side", sa.String(length=20), nullable=True),
            sa.Column("exchange_trade_id", sa.String(length=120), nullable=False),
            sa.Column("order_id", sa.String(length=120), nullable=True),
            sa.Column("client_order_id", sa.String(length=120), nullable=True),
            sa.Column("trade_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("executed_qty", sa.Float(), nullable=False, server_default="0"),
            sa.Column("executed_price", sa.Float(), nullable=False, server_default="0"),
            sa.Column("quote_qty", sa.Float(), nullable=False, server_default="0"),
            sa.Column("commission_amount", sa.Float(), nullable=False, server_default="0"),
            sa.Column("commission_asset", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("commission_usd", sa.Float(), nullable=False, server_default="0"),
            sa.Column("funding_fee_amount", sa.Float(), nullable=False, server_default="0"),
            sa.Column("funding_fee_asset", sa.String(length=20), nullable=True),
            sa.Column("funding_fee_usd", sa.Float(), nullable=False, server_default="0"),
            sa.Column("realized_pnl_amount", sa.Float(), nullable=False, server_default="0"),
            sa.Column("realized_pnl_asset", sa.String(length=20), nullable=True),
            sa.Column("realized_pnl_usd", sa.Float(), nullable=False, server_default="0"),
            sa.Column("is_buyer", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("is_maker", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("source", sa.String(length=20), nullable=False, server_default="rest"),
            sa.Column("raw_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint(
                "user_id",
                "exchange",
                "market_type",
                "environment",
                "exchange_trade_id",
                name="uq_commercial_trade_user_scope",
            ),
        )
        op.create_index("ix_commercial_trades_user_id", "commercial_trades", ["user_id"])
        op.create_index("ix_commercial_trades_connection_id", "commercial_trades", ["connection_id"])
        op.create_index("ix_commercial_trades_exchange", "commercial_trades", ["exchange"])
        op.create_index("ix_commercial_trades_market_type", "commercial_trades", ["market_type"])
        op.create_index("ix_commercial_trades_environment", "commercial_trades", ["environment"])
        op.create_index("ix_commercial_trades_symbol", "commercial_trades", ["symbol"])
        op.create_index("ix_commercial_trades_base_asset", "commercial_trades", ["base_asset"])
        op.create_index("ix_commercial_trades_quote_asset", "commercial_trades", ["quote_asset"])
        op.create_index("ix_commercial_trades_exchange_trade_id", "commercial_trades", ["exchange_trade_id"])
        op.create_index("ix_commercial_trades_order_id", "commercial_trades", ["order_id"])
        op.create_index("ix_commercial_trades_client_order_id", "commercial_trades", ["client_order_id"])
        op.create_index("ix_commercial_trades_trade_time", "commercial_trades", ["trade_time"])
        op.create_index("ix_commercial_trades_ingested_at", "commercial_trades", ["ingested_at"])

    if not _has_table(bind, "pnl_records"):
        op.create_table(
            "pnl_records",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("exchange", sa.String(length=30), nullable=False, server_default="binance"),
            sa.Column("market_type", sa.String(length=20), nullable=False, server_default="all"),
            sa.Column("environment", sa.String(length=20), nullable=False, server_default="testnet"),
            sa.Column("as_of", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("window_start", sa.DateTime(timezone=True), nullable=True),
            sa.Column("window_end", sa.DateTime(timezone=True), nullable=True),
            sa.Column("trade_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("trading_fee_usd", sa.Float(), nullable=False, server_default="0"),
            sa.Column("commission_usd", sa.Float(), nullable=False, server_default="0"),
            sa.Column("funding_usd", sa.Float(), nullable=False, server_default="0"),
            sa.Column("realized_gross_usd", sa.Float(), nullable=False, server_default="0"),
            sa.Column("unrealized_gross_usd", sa.Float(), nullable=False, server_default="0"),
            sa.Column("realized_net_usd", sa.Float(), nullable=False, server_default="0"),
            sa.Column("unrealized_net_usd", sa.Float(), nullable=False, server_default="0"),
            sa.Column("net_total_usd", sa.Float(), nullable=False, server_default="0"),
            sa.Column("pnl_source", sa.String(length=80), nullable=False, server_default="canonical_trade_engine_v1"),
            sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_pnl_records_user_id", "pnl_records", ["user_id"])
        op.create_index("ix_pnl_records_exchange", "pnl_records", ["exchange"])
        op.create_index("ix_pnl_records_market_type", "pnl_records", ["market_type"])
        op.create_index("ix_pnl_records_environment", "pnl_records", ["environment"])
        op.create_index("ix_pnl_records_as_of", "pnl_records", ["as_of"])

    if not _has_table(bind, "exchange_reconciliation_logs"):
        op.create_table(
            "exchange_reconciliation_logs",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("connection_id", sa.String(), sa.ForeignKey("user_exchange_connections.id"), nullable=True),
            sa.Column("exchange", sa.String(length=30), nullable=False, server_default="binance"),
            sa.Column("market_type", sa.String(length=20), nullable=False, server_default="all"),
            sa.Column("environment", sa.String(length=20), nullable=False, server_default="testnet"),
            sa.Column("run_source", sa.String(length=40), nullable=False, server_default="manual"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="running"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("requested_symbols", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
            sa.Column("internal_trade_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("exchange_trade_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("missing_trade_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("duplicate_trade_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("balance_drift_usd", sa.Float(), nullable=False, server_default="0"),
            sa.Column("position_drift_usd", sa.Float(), nullable=False, server_default="0"),
            sa.Column("pnl_drift_usd", sa.Float(), nullable=False, server_default="0"),
            sa.Column("drift_tolerance_usd", sa.Float(), nullable=False, server_default="5"),
            sa.Column("drift_within_tolerance", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("freshness_seconds", sa.Integer(), nullable=True),
            sa.Column("missing_data_alert", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("missing_symbols", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
            sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_exchange_reconciliation_logs_user_id", "exchange_reconciliation_logs", ["user_id"])
        op.create_index("ix_exchange_reconciliation_logs_connection_id", "exchange_reconciliation_logs", ["connection_id"])
        op.create_index("ix_exchange_reconciliation_logs_exchange", "exchange_reconciliation_logs", ["exchange"])
        op.create_index("ix_exchange_reconciliation_logs_market_type", "exchange_reconciliation_logs", ["market_type"])
        op.create_index("ix_exchange_reconciliation_logs_environment", "exchange_reconciliation_logs", ["environment"])
        op.create_index("ix_exchange_reconciliation_logs_status", "exchange_reconciliation_logs", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "exchange_reconciliation_logs"):
        op.drop_table("exchange_reconciliation_logs")
    if _has_table(bind, "pnl_records"):
        op.drop_table("pnl_records")
    if _has_table(bind, "commercial_trades"):
        op.drop_table("commercial_trades")
