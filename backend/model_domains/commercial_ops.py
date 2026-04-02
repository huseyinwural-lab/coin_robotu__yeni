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
    environment: Mapped[str] = mapped_column(String(20), default="live", index=True)

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
    environment: Mapped[str] = mapped_column(String(20), default="live", index=True)

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
    environment: Mapped[str] = mapped_column(String(20), default="live", index=True)

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
    environment: Mapped[str] = mapped_column(String(20), default="live", index=True)
    symbol: Mapped[str] = mapped_column(String(30), default="", index=True)
    trade_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    component_type: Mapped[str] = mapped_column(String(30), default="fee", index=True)
    source_amount_usd: Mapped[float] = mapped_column(Float, default=0)
    share_rate: Mapped[float] = mapped_column(Float, default=0)
    revenue_amount_usd: Mapped[float] = mapped_column(Float, default=0, index=True)

    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UserEconomicsAggregate(Base):
    __tablename__ = "user_economics_aggregates"
    __table_args__ = (
        UniqueConstraint("user_id", "environment", name="uq_user_econ_user_env"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    environment: Mapped[str] = mapped_column(String(20), default="live", index=True)
    user_email: Mapped[str] = mapped_column(String(255), default="", index=True)

    ltv_usd: Mapped[float] = mapped_column(Float, default=0, index=True)
    revenue_contribution_usd: Mapped[float] = mapped_column(Float, default=0, index=True)
    realized_pnl_usd: Mapped[float] = mapped_column(Float, default=0)

    first_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    inactive_days: Mapped[int] = mapped_column(Integer, default=0, index=True)
    churned: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    cohort_month: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)

    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UserEconomicsSnapshot(Base):
    __tablename__ = "user_economics_snapshots"
    __table_args__ = (
        UniqueConstraint("snapshot_type", "snapshot_date", "environment", "user_id", name="uq_user_econ_snapshot_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    snapshot_type: Mapped[str] = mapped_column(String(20), default="daily", index=True)
    snapshot_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    environment: Mapped[str] = mapped_column(String(20), default="live", index=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    user_email: Mapped[str] = mapped_column(String(255), default="", index=True)

    ltv_usd: Mapped[float] = mapped_column(Float, default=0)
    revenue_contribution_usd: Mapped[float] = mapped_column(Float, default=0)
    realized_pnl_usd: Mapped[float] = mapped_column(Float, default=0)
    inactive_days: Mapped[int] = mapped_column(Integer, default=0)
    churned: Mapped[bool] = mapped_column(Boolean, default=False)
    cohort_month: Mapped[str | None] = mapped_column(String(20), nullable=True)
    segment: Mapped[str] = mapped_column(String(40), default="low_activity_low_revenue", index=True)

    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnalyticsSnapshot(Base):
    __tablename__ = "analytics_snapshots"
    __table_args__ = (
        UniqueConstraint("snapshot_type", "snapshot_date", "environment", name="uq_analytics_snapshot_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    snapshot_type: Mapped[str] = mapped_column(String(20), default="daily", index=True)
    environment: Mapped[str] = mapped_column(String(20), default="live", index=True)
    snapshot_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CommercialSubscriptionProfile(Base):
    __tablename__ = "commercial_subscription_profiles"
    __table_args__ = (UniqueConstraint("user_id", "environment", name="uq_commercial_sub_profile_user_env"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    environment: Mapped[str] = mapped_column(String(20), default="live", index=True)

    subscription_status: Mapped[str] = mapped_column(String(30), default="inactive", index=True)
    tier_code: Mapped[str] = mapped_column(String(40), default="free", index=True)
    billing_cycle: Mapped[str] = mapped_column(String(20), default="monthly")
    subscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    renewal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    subscription_fee_usd: Mapped[float] = mapped_column(Float, default=0)
    profit_share_rate: Mapped[float] = mapped_column(Float, default=0)
    details: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CommercialUsageEvent(Base):
    __tablename__ = "commercial_usage_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)
    environment: Mapped[str] = mapped_column(String(20), default="live", index=True)
    event_type: Mapped[str] = mapped_column(String(30), default="api_call", index=True)
    endpoint: Mapped[str] = mapped_column(String(160), default="/api/admin/commercial/overview", index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class CommercialExportManifest(Base):
    __tablename__ = "commercial_export_manifests"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    export_type: Mapped[str] = mapped_column(String(40), index=True)
    schema_version: Mapped[str] = mapped_column(String(20), default="v1")
    requested_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    filters_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    column_mapping: Mapped[dict] = mapped_column(JSON, default=dict)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    output_format: Mapped[str] = mapped_column(String(20), default="csv")
    checksum: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    artifact_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    delivery_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    retention_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retention_state: Mapped[str] = mapped_column(String(20), default="active", index=True)
    downloadable_state: Mapped[str] = mapped_column(String(20), default="ready", index=True)
    signed_download_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class CommercialExportSchedule(Base):
    __tablename__ = "commercial_export_schedules"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    export_type: Mapped[str] = mapped_column(String(40), index=True)
    schedule_period: Mapped[str] = mapped_column(String(20), default="daily", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    output_format: Mapped[str] = mapped_column(String(20), default="csv")
    requested_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    filters_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str] = mapped_column(String(20), default="never")
    running_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_token: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    max_retry: Mapped[int] = mapped_column(Integer, default=3)
    last_execution_window: Mapped[str | None] = mapped_column(String(80), nullable=True)
    stale_run_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    last_output_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CommercialExportAudit(Base):
    __tablename__ = "commercial_export_audits"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    export_id: Mapped[str] = mapped_column(String, index=True)
    actor_user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    actor_email: Mapped[str] = mapped_column(String(255), default="")
    export_type: Mapped[str] = mapped_column(String(40), index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    filters_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    file_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    artifact_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    delivery_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    reason_note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CommercialOperationalControlState(Base):
    __tablename__ = "commercial_operational_control_states"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), unique=True, index=True)
    trading_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    capital_frozen: Mapped[bool] = mapped_column(Boolean, default=False)
    withdraw_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    emergency_stop: Mapped[bool] = mapped_column(Boolean, default=False)
    reason_note: Mapped[str] = mapped_column(String(255), default="")
    updated_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CommercialOperationalControlTransition(Base):
    __tablename__ = "commercial_operational_control_transitions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    actor_user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    actor_email: Mapped[str] = mapped_column(String(255), default="")
    previous_state: Mapped[dict] = mapped_column(JSON, default=dict)
    next_state: Mapped[dict] = mapped_column(JSON, default=dict)
    previous_state_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    new_state_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    changed_fields: Mapped[list] = mapped_column(JSON, default=list)
    reason_note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CommercialAlertEvent(Base):
    __tablename__ = "commercial_alert_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    alert_type: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="warning", index=True)
    source: Mapped[str] = mapped_column(String(60), default="commercial_overview")
    entity_type: Mapped[str] = mapped_column(String(40), default="system")
    entity_id: Mapped[str] = mapped_column(String(120), default="global", index=True)
    title: Mapped[str] = mapped_column(String(160), default="")
    message: Mapped[str] = mapped_column(String(500), default="")
    suggested_action: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    triage_status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    escalation_level: Mapped[str] = mapped_column(String(20), default="none", index=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_to_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)
    assigned_to_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assignment_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    age_seconds: Mapped[int] = mapped_column(Integer, default=0)
    sla_state: Mapped[str] = mapped_column(String(20), default="within_sla", index=True)
    auto_escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    resolution_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
