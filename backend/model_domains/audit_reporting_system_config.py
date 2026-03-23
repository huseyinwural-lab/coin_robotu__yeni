import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from model_domains.shared import utcnow
from model_domains.runtime_scan_candidate import RuntimeScanCandidate

_runtime_scan_candidate_registered = RuntimeScanCandidate

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    actor_user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    actor_role: Mapped[str] = mapped_column(String(20), default="system")
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(120))
    severity: Mapped[str] = mapped_column(String(20), default="info")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class ExecutionEvent(Base):
    __tablename__ = "execution_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    bot_profile_id: Mapped[str] = mapped_column(String, ForeignKey("bot_profiles.id"), index=True)
    exchange: Mapped[str] = mapped_column(String(50), default="binance")
    symbol: Mapped[str] = mapped_column(String(30))
    side: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[float] = mapped_column(Float)
    mock_price: Mapped[float] = mapped_column(Float)
    execution_status: Mapped[str] = mapped_column(String(30), default="filled")
    source_type: Mapped[str] = mapped_column(String(20), default="production", index=True)
    environment: Mapped[str] = mapped_column(String(20), default="production", index=True)
    correlation_id: Mapped[str] = mapped_column(String(120), default="", index=True)
    triggered_by: Mapped[str] = mapped_column(String(120), default="system")
    parent_event_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    strategy_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    response_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str] = mapped_column(Text, default="MOCK execution only")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class PendingSignal(Base):
    __tablename__ = "pending_signals"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    signal_id: Mapped[str] = mapped_column(String, ForeignKey("signal_events.id"), index=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    strategy_code: Mapped[str] = mapped_column(String(80))
    confidence: Mapped[float] = mapped_column(Float, default=0)
    mode: Mapped[str] = mapped_column(String(20), default="ASSISTED")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    strategy_weight: Mapped[float] = mapped_column(Float, default=1.0)
    allocation_source: Mapped[str] = mapped_column(String(40), default="default_allocation")
    meta_engine_decision: Mapped[str] = mapped_column(String(30), default="ALLOW")
    previous_state: Mapped[str] = mapped_column(String(40), default="DETECTED")
    current_state: Mapped[str] = mapped_column(String(40), default="DETECTED", index=True)
    blocked_reason_code: Mapped[str] = mapped_column(String(60), default="")
    blocked_reason_message: Mapped[str] = mapped_column(String(220), default="")
    blocked_solution_hint: Mapped[str] = mapped_column(String(240), default="")
    requires_manual_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    execution_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    bot_profile_id: Mapped[str | None] = mapped_column(String, ForeignKey("bot_profiles.id"), nullable=True, index=True)
    risk_policy_id: Mapped[str | None] = mapped_column(String, ForeignKey("risk_policies.id"), nullable=True, index=True)
    exchange_connection_id: Mapped[str | None] = mapped_column(String, ForeignKey("user_exchange_connections.id"), nullable=True, index=True)
    created_order_intent_id: Mapped[str | None] = mapped_column(String, ForeignKey("user_execution_intents.id"), nullable=True, index=True)
    runtime_owner: Mapped[str] = mapped_column(String(120), default="")
    last_eligibility_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_transition_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    order_position_id: Mapped[str | None] = mapped_column(String, ForeignKey("paper_positions.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str] = mapped_column(Text, default="")

class FailedEvent(Base):
    __tablename__ = "failed_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(120), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str] = mapped_column(Text)
    failure_class: Mapped[str] = mapped_column(String(40), default="downstream_error", index=True)
    dead_letter_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_action_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    retry_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retry: Mapped[int] = mapped_column(Integer, default=5)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class StateRebuildLog(Base):
    __tablename__ = "state_rebuild_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    rebuild_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="started")
    trigger_source: Mapped[str] = mapped_column(String(30), default="startup")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class BacktestResultCard(Base):
    __tablename__ = "backtest_result_cards"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_type: Mapped[str] = mapped_column(String(50), index=True)
    market_type: Mapped[str] = mapped_column(String(20), default="spot")
    timeframe: Mapped[str] = mapped_column(String(10), default="15m")
    sample_size: Mapped[int] = mapped_column(Integer, default=100)
    win_rate: Mapped[float] = mapped_column(Float, default=0)
    max_drawdown: Mapped[float] = mapped_column(Float, default=0)
    profit_factor: Mapped[float] = mapped_column(Float, default=1)
    sharpe_like_score: Mapped[float] = mapped_column(Float, default=0)
    performance_summary: Mapped[str] = mapped_column(Text, default="")
    risk_label: Mapped[str] = mapped_column(String(20), default="medium")
    period_start: Mapped[str] = mapped_column(String(30), default="")
    period_end: Mapped[str] = mapped_column(String(30), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class HardeningChecklistRun(Base):
    __tablename__ = "hardening_checklist_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    score: Mapped[float] = mapped_column(Float, default=0)
    critical_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    readiness_status: Mapped[str] = mapped_column(String(20), default="blocked")
    checklist_items: Mapped[list[dict]] = mapped_column(JSON, default=list)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class UserExchangeSetting(Base):
    __tablename__ = "user_exchange_settings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), unique=True, index=True)
    exchange: Mapped[str] = mapped_column(String(30), default="binance")
    mode: Mapped[str] = mapped_column(String(20), default="testnet")
    api_key_encrypted: Mapped[str] = mapped_column(Text, default="")
    api_secret_encrypted: Mapped[str] = mapped_column(Text, default="")
    permissions_snapshot: Mapped[list[str]] = mapped_column(JSON, default=list)
    can_trade_snapshot: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_validation_success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    validation_snapshot_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    validation_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class UserExchangeConnection(Base):
    __tablename__ = "user_exchange_connections"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    account_label: Mapped[str] = mapped_column(String(80), default="default")
    exchange: Mapped[str] = mapped_column(String(30), default="binance")
    market_type: Mapped[str] = mapped_column(String(20), default="spot")
    environment: Mapped[str] = mapped_column(String(20), default="testnet")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    readiness_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    permission_snapshot: Mapped[list[str]] = mapped_column(JSON, default=list)
    api_key_encrypted: Mapped[str] = mapped_column(Text, default="")
    api_secret_encrypted: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class UserRiskSetting(Base):
    __tablename__ = "user_risk_settings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), unique=True, index=True)
    allocation_pct: Mapped[float] = mapped_column(Float, default=20)
    trade_risk_pct: Mapped[float] = mapped_column(Float, default=10)
    daily_loss_limit_pct: Mapped[float] = mapped_column(Float, default=3)
    compounding_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    base_capital: Mapped[float] = mapped_column(Float, default=10000)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class AlertPolicy(Base):
    __tablename__ = "alert_policies"

    id: Mapped[str] = mapped_column(String, primary_key=True, default="global")
    admin_notification_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    ops_webhook_url: Mapped[str] = mapped_column(Text, default="")
    monitoring_alert_log_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    execution_quality_warning_threshold: Mapped[float] = mapped_column(Float, default=60)
    execution_quality_critical_threshold: Mapped[float] = mapped_column(Float, default=40)
    permission_drift_warning_per_day: Mapped[int] = mapped_column(Integer, default=2)
    permission_drift_critical_per_day: Mapped[int] = mapped_column(Integer, default=5)
    gate_override_warning_per_day: Mapped[int] = mapped_column(Integer, default=2)
    gate_override_critical_per_day: Mapped[int] = mapped_column(Integer, default=5)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class AlertChannelConfig(Base):
    __tablename__ = "alert_channel_configs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default="global")
    resend_api_key_encrypted: Mapped[str] = mapped_column(Text, default="")
    sendgrid_api_key_encrypted: Mapped[str] = mapped_column(Text, default="")
    alert_from: Mapped[str] = mapped_column(String(255), default="")
    alert_to: Mapped[str] = mapped_column(Text, default="")
    slack_webhook_url_encrypted: Mapped[str] = mapped_column(Text, default="")
    telegram_bot_token_encrypted: Mapped[str] = mapped_column(Text, default="")
    telegram_chat_id: Mapped[str] = mapped_column(String(255), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class SystemAlert(Base):
    __tablename__ = "system_alerts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    alert_type: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="INFO")
    message: Mapped[str] = mapped_column(Text, default="")
    fingerprint: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    entity_key: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    root_cause_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    state_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    delivery_status: Mapped[dict] = mapped_column(JSON, default=dict)
    delivery_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")
    occurrences: Mapped[int] = mapped_column(Integer, default=1)
    last_triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ExecutionAlertDeliveryAttempt(Base):
    __tablename__ = "execution_alert_delivery_attempts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    alert_id: Mapped[str] = mapped_column(String, ForeignKey("system_alerts.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40), default="slack")
    destination_masked: Mapped[str] = mapped_column(String(255), default="")
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    request_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    request_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body_truncated: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    final_status: Mapped[str] = mapped_column(String(30), default="PENDING")
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_test: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class WeeklyReportArchive(Base):
    __tablename__ = "weekly_report_archives"

    report_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    report_type: Mapped[str] = mapped_column(String(40), default="weekly_ops")
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    timezone: Mapped[str] = mapped_column(String(40), default="Europe/Berlin")
    filename: Mapped[str] = mapped_column(String(200))
    storage_path: Mapped[str] = mapped_column(Text, default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(20), default="generated")
    trigger_source: Mapped[str] = mapped_column(String(20), default="scheduled")
    generated_by: Mapped[str] = mapped_column(String(120), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class ExchangeRegistry(Base):
    __tablename__ = "exchange_registry"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    exchange_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    exchange_name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="active")
    supported_market_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    supports_testnet: Mapped[bool] = mapped_column(Boolean, default=True)
    supports_live: Mapped[bool] = mapped_column(Boolean, default=False)
    health_status: Mapped[str] = mapped_column(String(20), default="healthy")
    rate_limit_status: Mapped[str] = mapped_column(String(20), default="ok")
    adapter_version: Mapped[str] = mapped_column(String(40), default="v1")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class ExchangeCapability(Base):
    __tablename__ = "exchange_capabilities"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    exchange_code: Mapped[str] = mapped_column(String(40), index=True)
    market_type: Mapped[str] = mapped_column(String(20), default="spot")
    supports_spot: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_futures: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_test_order: Mapped[bool] = mapped_column(Boolean, default=True)
    supports_quote_qty: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_reduce_only: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_leverage: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_margin_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_hedge_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class AllowedMarket(Base):
    __tablename__ = "allowed_markets"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    exchange_code: Mapped[str] = mapped_column(String(40), index=True)
    market_type: Mapped[str] = mapped_column(String(20))
    environment: Mapped[str] = mapped_column(String(20), default="testnet")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class UserVenueAssignment(Base):
    __tablename__ = "user_venue_assignments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    exchange_code: Mapped[str] = mapped_column(String(40), index=True)
    spot_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    futures_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    testnet_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    live_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class ExternalProviderCredential(Base):
    __tablename__ = "external_provider_credentials"

    provider: Mapped[str] = mapped_column(String(80), primary_key=True)
    api_key_encrypted: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
