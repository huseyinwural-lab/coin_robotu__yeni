import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, event
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.USER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    approval_status: Mapped[str] = mapped_column(String(20), default="approved")
    approval_requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BotProfile(Base):
    __tablename__ = "bot_profiles"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    exchange: Mapped[str] = mapped_column(String(50), default="binance")
    market_type: Mapped[str] = mapped_column(String(20), default="spot")
    symbols: Mapped[list[str]] = mapped_column(JSON, default=list)
    strategy_type: Mapped[str] = mapped_column(String(50), default="trend_following")
    timeframe: Mapped[str] = mapped_column(String(10), default="15m")
    trend_timeframe: Mapped[str] = mapped_column(String(10), default="1h")
    leverage: Mapped[int] = mapped_column(Integer, default=3)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_running: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AdminControl(Base):
    __tablename__ = "admin_control"

    id: Mapped[str] = mapped_column(String, primary_key=True, default="global")
    max_leverage_cap: Mapped[int] = mapped_column(Integer, default=5)
    max_open_positions_cap: Mapped[int] = mapped_column(Integer, default=10)
    minimum_volume_usd: Mapped[float] = mapped_column(Float, default=1000000)
    max_spread_bps: Mapped[int] = mapped_column(Integer, default=40)
    spot_universe: Mapped[list[str]] = mapped_column(JSON, default=list)
    futures_universe: Mapped[list[str]] = mapped_column(JSON, default=list)
    whitelist: Mapped[list[str]] = mapped_column(JSON, default=list)
    blacklist: Mapped[list[str]] = mapped_column(JSON, default=list)
    emergency_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    disable_futures: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class RiskPolicy(Base):
    __tablename__ = "risk_policies"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    position_size_pct: Mapped[float] = mapped_column(Float)
    atr_stop_multiplier: Mapped[float] = mapped_column(Float)
    risk_reward_ratio: Mapped[float] = mapped_column(Float)
    daily_loss_cutoff_pct: Mapped[float] = mapped_column(Float)
    max_open_positions: Mapped[int] = mapped_column(Integer)
    max_leverage: Mapped[int] = mapped_column(Integer, default=3)
    spread_limit_bps: Mapped[int] = mapped_column(Integer, default=30)
    slippage_limit_bps: Mapped[int] = mapped_column(Integer, default=40)
    min_liquidity_usdt: Mapped[int] = mapped_column(Integer, default=100000)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class StrategyTemplate(Base):
    __tablename__ = "strategy_templates"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(120), unique=True)
    strategy_type: Mapped[str] = mapped_column(String(50))
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


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
    response_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str] = mapped_column(Text, default="MOCK execution only")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SignalEvent(Base):
    __tablename__ = "signal_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    bot_profile_id: Mapped[str] = mapped_column(String, ForeignKey("bot_profiles.id"), index=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(30))
    market_type: Mapped[str] = mapped_column(String(20))
    timeframe: Mapped[str] = mapped_column(String(10))
    strategy_id: Mapped[str] = mapped_column(String(50))
    signal: Mapped[str] = mapped_column(String(20))
    direction: Mapped[str] = mapped_column(String(10))
    confidence: Mapped[float] = mapped_column(Float)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PaperPosition(Base):
    __tablename__ = "paper_positions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    bot_profile_id: Mapped[str] = mapped_column(String, ForeignKey("bot_profiles.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    market_type: Mapped[str] = mapped_column(String(20), default="spot")
    side: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[float] = mapped_column(Float)
    leverage: Mapped[int] = mapped_column(Integer, default=3)
    entry_price: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float)
    take_profit: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="open")
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PositionLedgerEvent(Base):
    __tablename__ = "position_ledger_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    position_id: Mapped[str] = mapped_column(String, ForeignKey("paper_positions.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExecutionPolicy(Base):
    __tablename__ = "execution_policies"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_type: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    execution_style: Mapped[str] = mapped_column(String(20), default="balanced")
    order_preference: Mapped[str] = mapped_column(String(20), default="limit_first")
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=8)
    fallback_behavior: Mapped[str] = mapped_column(String(30), default="market_fallback")
    partial_fill_tolerance_pct: Mapped[float] = mapped_column(Float, default=50)
    execution_urgency: Mapped[str] = mapped_column(String(20), default="medium")
    retry_limit: Mapped[int] = mapped_column(Integer, default=2)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class RiskExposureGroup(Base):
    __tablename__ = "risk_exposure_groups"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(120))
    symbols: Mapped[list[str]] = mapped_column(JSON, default=list)
    max_group_open_positions: Mapped[int] = mapped_column(Integer, default=4)
    max_group_directional_positions: Mapped[int] = mapped_column(Integer, default=3)
    max_group_risk_pct: Mapped[float] = mapped_column(Float, default=20)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class FailedEvent(Base):
    __tablename__ = "failed_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(120), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str] = mapped_column(Text)
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


class ExecutionStateTransition(Base):
    __tablename__ = "execution_state_transitions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    execution_event_id: Mapped[str] = mapped_column(String, ForeignKey("execution_events.id"), index=True)
    state: Mapped[str] = mapped_column(String(30), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HardeningChecklistRun(Base):
    __tablename__ = "hardening_checklist_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    score: Mapped[float] = mapped_column(Float, default=0)
    critical_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    readiness_status: Mapped[str] = mapped_column(String(20), default="blocked")
    checklist_items: Mapped[list[dict]] = mapped_column(JSON, default=list)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LiveActivationConfig(Base):
    __tablename__ = "live_activation_config"

    id: Mapped[str] = mapped_column(String, primary_key=True, default="global")
    exchange: Mapped[str] = mapped_column(String(30), default="binance")
    market_type: Mapped[str] = mapped_column(String(20), default="futures_testnet")
    safe_mode_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    live_mode_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    symbol_whitelist: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["BTCUSDT"])
    max_position_pct: Mapped[float] = mapped_column(Float, default=0.1)
    leverage_cap: Mapped[int] = mapped_column(Integer, default=1)
    max_trades_per_hour: Mapped[int] = mapped_column(Integer, default=6)
    max_notional_exposure: Mapped[float] = mapped_column(Float, default=150)
    kill_switch_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    disable_futures: Mapped[bool] = mapped_column(Boolean, default=False)
    ip_whitelist_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    trading_permission_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


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


class TestnetExecutionLog(Base):
    __tablename__ = "testnet_execution_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(20), default="BTCUSDT")
    strategy_direction: Mapped[str] = mapped_column(String(10), default="long")
    expected_price: Mapped[float] = mapped_column(Float)
    fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    slippage: Mapped[float | None] = mapped_column(Float, nullable=True)
    execution_latency: Mapped[float | None] = mapped_column(Float, nullable=True)
    execution_quality_score: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(30), default="created")
    state_machine_path: Mapped[list[str]] = mapped_column(JSON, default=list)
    permission_snapshot: Mapped[list[dict]] = mapped_column(JSON, default=list)
    release_gate_status: Mapped[str] = mapped_column(String(20), default="BLOCKED")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ExecutionMetric(Base):
    __tablename__ = "execution_metrics"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(20), default="BTCUSDT")
    order_id: Mapped[str] = mapped_column(String(80), index=True)
    exchange_order_id: Mapped[str] = mapped_column(String(80), index=True)
    client_order_id: Mapped[str] = mapped_column(String(120), default="")
    order_type: Mapped[str] = mapped_column(String(20), default="MARKET")
    exchange: Mapped[str] = mapped_column(String(30), default="binance")
    market_type: Mapped[str] = mapped_column(String(20), default="futures")
    environment: Mapped[str] = mapped_column(String(20), default="testnet")
    side: Mapped[str] = mapped_column(String(10), default="BUY")
    quote_qty: Mapped[float] = mapped_column(Float, default=10)
    mid_price: Mapped[float] = mapped_column(Float)
    mid_price_timestamp: Mapped[str] = mapped_column(String(40), default="")
    price_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    executed_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    slippage_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    execution_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="NEW")
    final_status: Mapped[str] = mapped_column(String(30), default="NEW")
    failure_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    strategy_type: Mapped[str] = mapped_column(String(50), default="trend_following")
    volatility_regime: Mapped[str] = mapped_column(String(20), default="low")
    volatility_pct: Mapped[float] = mapped_column(Float, default=0)
    execution_quality_score: Mapped[float] = mapped_column(Float, default=0)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    final_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    validation_snapshot_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    raw_exchange_status: Mapped[dict] = mapped_column(JSON, default=dict)
    state_machine_path: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExecutionCorrectionEvent(Base):
    __tablename__ = "execution_correction_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    execution_metric_id: Mapped[str] = mapped_column(String, ForeignKey("execution_metrics.id"), index=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    correction_type: Mapped[str] = mapped_column(String(40), default="annotation")
    reason_code: Mapped[str] = mapped_column(String(40), default="manual_correction")
    note: Mapped[str] = mapped_column(Text, default="")
    patch_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExecutionLifecycleEvent(Base):
    __tablename__ = "execution_lifecycle_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    execution_metric_id: Mapped[str] = mapped_column(String, ForeignKey("execution_metrics.id"), index=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    event_name: Mapped[str] = mapped_column(String(40))
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class PermissionDriftEvent(Base):
    __tablename__ = "permission_drift_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    exchange: Mapped[str] = mapped_column(String(30), default="binance")
    old_permissions: Mapped[list[str]] = mapped_column(JSON, default=list)
    new_permissions: Mapped[list[str]] = mapped_column(JSON, default=list)
    old_can_trade: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    new_can_trade: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReleaseGateOverride(Base):
    __tablename__ = "release_gate_overrides"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    admin_user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    reason_code: Mapped[str] = mapped_column(String(40))
    reason_note: Mapped[str] = mapped_column(Text)
    release_gate_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    deploy_context: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_deploy_count: Mapped[int] = mapped_column(Integer, default=0)


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


class ReplayRun(Base):
    __tablename__ = "replay_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    exchange: Mapped[str] = mapped_column(String(30), default="binance")
    market_type: Mapped[str] = mapped_column(String(20), default="futures")
    environment: Mapped[str] = mapped_column(String(20), default="testnet")
    symbol: Mapped[str] = mapped_column(String(20), default="BTCUSDT")
    timeframe: Mapped[str] = mapped_column(String(10), default="15m")
    strategy_type: Mapped[str] = mapped_column(String(50), default="trend_following")
    candles_processed: Mapped[int] = mapped_column(Integer, default=0)
    executions_count: Mapped[int] = mapped_column(Integer, default=0)
    filled_count: Mapped[int] = mapped_column(Integer, default=0)
    canceled_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_simulated_latency_ms: Mapped[float] = mapped_column(Float, default=0)
    avg_simulated_slippage_pct: Mapped[float] = mapped_column(Float, default=0)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="completed")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReplayExecution(Base):
    __tablename__ = "replay_executions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    replay_run_id: Mapped[str] = mapped_column(String, ForeignKey("replay_runs.id"), index=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(20), default="BTCUSDT")
    timeframe: Mapped[str] = mapped_column(String(10), default="15m")
    signal: Mapped[str] = mapped_column(String(20), default="none")
    direction: Mapped[str] = mapped_column(String(10), default="none")
    market_price: Mapped[float] = mapped_column(Float)
    simulated_fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    simulated_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    simulated_slippage_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    lifecycle: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="SIM_CANCELED")
    risk_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    candle_timestamp: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReplayEquityPoint(Base):
    __tablename__ = "replay_equity_points"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    replay_run_id: Mapped[str] = mapped_column(String, ForeignKey("replay_runs.id"), index=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    point_timestamp: Mapped[str] = mapped_column(String(40), default="")
    equity: Mapped[float] = mapped_column(Float, default=0)
    pnl_delta: Mapped[float] = mapped_column(Float, default=0)
    drawdown_pct: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


@event.listens_for(ExecutionMetric, "before_update", propagate=True)
def _block_execution_metric_update(_, __, ___):
    raise ValueError("execution_metric_immutable")