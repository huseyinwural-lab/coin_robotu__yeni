import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from model_domains.shared import utcnow


class CommercialTrade(Base):
    __tablename__ = "commercial_trades"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "exchange",
            "market_type",
            "environment",
            "exchange_trade_id",
            name="uq_commercial_trade_user_scope",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    connection_id: Mapped[str | None] = mapped_column(String, ForeignKey("user_exchange_connections.id"), nullable=True, index=True)

    exchange: Mapped[str] = mapped_column(String(30), default="binance", index=True)
    market_type: Mapped[str] = mapped_column(String(20), default="spot", index=True)
    environment: Mapped[str] = mapped_column(String(20), default="testnet", index=True)

    symbol: Mapped[str] = mapped_column(String(30), index=True)
    base_asset: Mapped[str] = mapped_column(String(20), default="", index=True)
    quote_asset: Mapped[str] = mapped_column(String(20), default="", index=True)
    side: Mapped[str] = mapped_column(String(10), default="BUY")
    position_side: Mapped[str | None] = mapped_column(String(20), nullable=True)

    exchange_trade_id: Mapped[str] = mapped_column(String(120), index=True)
    order_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    client_order_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)

    trade_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    executed_qty: Mapped[float] = mapped_column(Float, default=0)
    executed_price: Mapped[float] = mapped_column(Float, default=0)
    quote_qty: Mapped[float] = mapped_column(Float, default=0)

    commission_amount: Mapped[float] = mapped_column(Float, default=0)
    commission_asset: Mapped[str] = mapped_column(String(20), default="")
    commission_usd: Mapped[float] = mapped_column(Float, default=0)

    funding_fee_amount: Mapped[float] = mapped_column(Float, default=0)
    funding_fee_asset: Mapped[str | None] = mapped_column(String(20), nullable=True)
    funding_fee_usd: Mapped[float] = mapped_column(Float, default=0)

    realized_pnl_amount: Mapped[float] = mapped_column(Float, default=0)
    realized_pnl_asset: Mapped[str | None] = mapped_column(String(20), nullable=True)
    realized_pnl_usd: Mapped[float] = mapped_column(Float, default=0)

    is_buyer: Mapped[bool] = mapped_column(Boolean, default=False)
    is_maker: Mapped[bool] = mapped_column(Boolean, default=False)

    source: Mapped[str] = mapped_column(String(20), default="rest")
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)

    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PnlRecord(Base):
    __tablename__ = "pnl_records"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)

    exchange: Mapped[str] = mapped_column(String(30), default="binance", index=True)
    market_type: Mapped[str] = mapped_column(String(20), default="all", index=True)
    environment: Mapped[str] = mapped_column(String(20), default="testnet", index=True)

    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    trade_count: Mapped[int] = mapped_column(Integer, default=0)
    trading_fee_usd: Mapped[float] = mapped_column(Float, default=0)
    commission_usd: Mapped[float] = mapped_column(Float, default=0)
    funding_usd: Mapped[float] = mapped_column(Float, default=0)

    realized_gross_usd: Mapped[float] = mapped_column(Float, default=0)
    unrealized_gross_usd: Mapped[float] = mapped_column(Float, default=0)
    realized_net_usd: Mapped[float] = mapped_column(Float, default=0)
    unrealized_net_usd: Mapped[float] = mapped_column(Float, default=0)
    net_total_usd: Mapped[float] = mapped_column(Float, default=0)

    pnl_source: Mapped[str] = mapped_column(String(80), default="canonical_trade_engine_v1")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExchangeReconciliationLog(Base):
    __tablename__ = "exchange_reconciliation_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    connection_id: Mapped[str | None] = mapped_column(String, ForeignKey("user_exchange_connections.id"), nullable=True, index=True)

    exchange: Mapped[str] = mapped_column(String(30), default="binance", index=True)
    market_type: Mapped[str] = mapped_column(String(20), default="all", index=True)
    environment: Mapped[str] = mapped_column(String(20), default="testnet", index=True)

    run_source: Mapped[str] = mapped_column(String(40), default="manual")
    status: Mapped[str] = mapped_column(String(20), default="running", index=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    requested_symbols: Mapped[list[str]] = mapped_column(JSON, default=list)
    internal_trade_count: Mapped[int] = mapped_column(Integer, default=0)
    exchange_trade_count: Mapped[int] = mapped_column(Integer, default=0)
    missing_trade_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_trade_count: Mapped[int] = mapped_column(Integer, default=0)

    balance_drift_usd: Mapped[float] = mapped_column(Float, default=0)
    position_drift_usd: Mapped[float] = mapped_column(Float, default=0)
    pnl_drift_usd: Mapped[float] = mapped_column(Float, default=0)
    drift_tolerance_usd: Mapped[float] = mapped_column(Float, default=5)
    drift_within_tolerance: Mapped[bool] = mapped_column(Boolean, default=False)

    freshness_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    missing_data_alert: Mapped[bool] = mapped_column(Boolean, default=False)
    missing_symbols: Mapped[list[str]] = mapped_column(JSON, default=list)

    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RevenueLedger(Base):
    __tablename__ = "revenue_ledger"
    __table_args__ = (
        UniqueConstraint("trade_id", "component_type", name="uq_revenue_ledger_trade_component"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    trade_id: Mapped[str] = mapped_column(String, ForeignKey("commercial_trades.id"), index=True)

    exchange: Mapped[str] = mapped_column(String(30), default="binance", index=True)
    market_type: Mapped[str] = mapped_column(String(20), default="spot", index=True)
    environment: Mapped[str] = mapped_column(String(20), default="testnet", index=True)
    symbol: Mapped[str] = mapped_column(String(30), default="", index=True)
    trade_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    component_type: Mapped[str] = mapped_column(String(30), default="fee", index=True)
    source_amount_usd: Mapped[float] = mapped_column(Float, default=0)
    share_rate: Mapped[float] = mapped_column(Float, default=0)
    revenue_amount_usd: Mapped[float] = mapped_column(Float, default=0, index=True)

    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
