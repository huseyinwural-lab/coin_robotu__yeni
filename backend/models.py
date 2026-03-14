import enum
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    OPS = "ops"
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
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    @property
    def status(self) -> str:
        return "active" if self.is_active else "disabled"


class UserOnboardingProfile(Base):
    __tablename__ = "user_onboarding_profiles"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), unique=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_code: Mapped[str | None] = mapped_column(String(12), nullable=True)
    verification_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


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


class RiskOrchestratorPolicy(Base):
    __tablename__ = "risk_orchestrator_policies"

    id: Mapped[str] = mapped_column(String, primary_key=True, default="global")
    reference_equity_usd: Mapped[float] = mapped_column(Float, default=10000)
    account_max_notional_pct: Mapped[float] = mapped_column(Float, default=60)
    symbol_max_notional_pct: Mapped[float] = mapped_column(Float, default=25)
    strategy_max_concurrent_positions: Mapped[int] = mapped_column(Integer, default=3)
    strategy_cooldown_seconds: Mapped[int] = mapped_column(Integer, default=60)
    max_order_frequency_per_min: Mapped[int] = mapped_column(Integer, default=6)
    max_order_burst_per_10s: Mapped[int] = mapped_column(Integer, default=3)
    daily_loss_limit_pct: Mapped[float] = mapped_column(Float, default=5)
    duplicate_suppression_window_seconds: Mapped[int] = mapped_column(Integer, default=300)
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


class UserSignalMode(Base):
    __tablename__ = "user_signal_modes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), unique=True, index=True)
    mode: Mapped[str] = mapped_column(String(20), default="ASSISTED")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UserScannerResult(Base):
    __tablename__ = "user_scanner_results"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    strategy_code: Mapped[str] = mapped_column(String(80), default="spot_pullback_v1")
    signal: Mapped[str] = mapped_column(String(20), default="none")
    confidence: Mapped[float] = mapped_column(Float, default=0)
    signal_score: Mapped[float] = mapped_column(Float, default=0)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class UserScannerAutomationConfig(Base):
    __tablename__ = "user_scanner_automation_configs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), unique=True, index=True)
    auto_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=180)
    max_results: Mapped[int] = mapped_column(Integer, default=25)
    symbol_source: Mapped[str] = mapped_column(String(20), default="crypto")
    symbol_selection_mode: Mapped[str] = mapped_column(String(40), default="all_market_symbols")
    selected_symbols: Mapped[list[str]] = mapped_column(JSON, default=list)
    last_run_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_run_status: Mapped[str] = mapped_column(String(20), default="idle")
    last_actionable_count: Mapped[int] = mapped_column(Integer, default=0)
    last_run_error: Mapped[str | None] = mapped_column(String(240), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UserScannerAutomationProfile(Base):
    __tablename__ = "user_scanner_automation_profiles"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(80), default="default", index=True)
    auto_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=180)
    max_results: Mapped[int] = mapped_column(Integer, default=25)
    symbol_source: Mapped[str] = mapped_column(String(20), default="crypto")
    symbol_selection_mode: Mapped[str] = mapped_column(String(40), default="all_market_symbols")
    selected_symbols: Mapped[list[str]] = mapped_column(JSON, default=list)
    last_run_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_run_status: Mapped[str] = mapped_column(String(20), default="idle")
    last_actionable_count: Mapped[int] = mapped_column(Integer, default=0)
    last_run_error: Mapped[str | None] = mapped_column(String(240), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UserIndicatorSavedQuery(Base):
    __tablename__ = "user_indicator_saved_queries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    exchange: Mapped[str] = mapped_column(String(30), default="binance")
    market_type: Mapped[str] = mapped_column(String(20), default="spot")
    timeframe: Mapped[str] = mapped_column(String(10), default="15m")
    query_expression: Mapped[str] = mapped_column(Text, default="")
    symbol_universe: Mapped[list[str]] = mapped_column(JSON, default=list)
    filter_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    result_limit: Mapped[int] = mapped_column(Integer, default=50)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UserIndicatorWatchlist(Base):
    __tablename__ = "user_indicator_watchlist"
    __table_args__ = (
        UniqueConstraint("user_id", "exchange", "market_type", "symbol", name="uq_user_indicator_watchlist_symbol"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    exchange: Mapped[str] = mapped_column(String(30), default="binance")
    market_type: Mapped[str] = mapped_column(String(20), default="spot")
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    context_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
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


class UserExecutionIntent(Base):
    __tablename__ = "user_execution_intents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(30), default="manual")
    source_ref_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    intent_type: Mapped[str] = mapped_column(String(40), default="OPEN_POSITION", index=True)
    position_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="PREVIEWED", index=True)
    intent_token: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    preview_hash: Mapped[str] = mapped_column(String(120), index=True)
    queue_mode: Mapped[str] = mapped_column(String(20), default="ASSISTED")
    approval_required: Mapped[bool] = mapped_column(Boolean, default=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    market_type: Mapped[str] = mapped_column(String(20), default="spot")
    side: Mapped[str] = mapped_column(String(10), default="buy")
    notional: Mapped[float] = mapped_column(Float, default=0)
    size: Mapped[float] = mapped_column(Float, default=0)
    reduce_only: Mapped[bool] = mapped_column(Boolean, default=False)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    normalized_order_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    reject_reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    risk_flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    risk_score: Mapped[float] = mapped_column(Float, default=0)
    gate_decision: Mapped[str] = mapped_column(String(30), default="ALLOW")
    meta_engine_decision: Mapped[str] = mapped_column(String(30), default="ALLOW")
    cluster_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    admin_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    admin_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UserDecisionTrace(Base):
    __tablename__ = "user_decision_traces"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    trace_scope: Mapped[str] = mapped_column(String(20), default="signal", index=True)
    trace_type: Mapped[str] = mapped_column(String(40), default="decision")
    entity_id: Mapped[str] = mapped_column(String(120), index=True)
    strategy_code: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    decision_status: Mapped[str] = mapped_column(String(40), default="UNKNOWN", index=True)
    portfolio_risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    strategy_allocation_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cluster_risk_flag: Mapped[str | None] = mapped_column(String(80), nullable=True)
    meta_engine_decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    position_action_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    risk_adjustment_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    strategy_override_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    hedge_recommendation: Mapped[str | None] = mapped_column(String(160), nullable=True)
    risk_reduction_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    correlation_basis: Mapped[str | None] = mapped_column(String(160), nullable=True)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    reason_details: Mapped[list[dict]] = mapped_column(JSON, default=list)
    feature_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    context_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc) + timedelta(days=90),
        index=True,
    )


class StrategyObservabilityEvent(Base):
    __tablename__ = "strategy_observability_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    selection_cycle_id: Mapped[str] = mapped_column(String(120), index=True)
    audit_log_id: Mapped[str | None] = mapped_column(String, ForeignKey("audit_logs.id"), nullable=True, index=True)
    bot_profile_id: Mapped[str | None] = mapped_column(String, ForeignKey("bot_profiles.id"), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    strategy_id: Mapped[str] = mapped_column(String(80), index=True)
    strategy_name: Mapped[str] = mapped_column(String(120), default="SPOT_TREND_PULLBACK")
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    market_regime: Mapped[str] = mapped_column(String(30), default="RANGING", index=True)
    multiplier_version: Mapped[str] = mapped_column(String(20), default="v1")
    multiplier_set: Mapped[dict] = mapped_column(JSON, default=dict)
    base_score: Mapped[float] = mapped_column(Float, default=0)
    adjusted_score: Mapped[float] = mapped_column(Float, default=0)
    score_delta: Mapped[float] = mapped_column(Float, default=0)
    selection_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trend_strength: Mapped[str | None] = mapped_column(String(20), nullable=True)
    relative_volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    hard_gate_pass: Mapped[bool] = mapped_column(Boolean, default=False)
    threshold_pass: Mapped[bool] = mapped_column(Boolean, default=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    event_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


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
    symbol_whitelist: Mapped[list[str]] = mapped_column(JSON, default=list)
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


class AlertChannelConfig(Base):
    __tablename__ = "alert_channel_configs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default="global")
    resend_api_key_encrypted: Mapped[str] = mapped_column(Text, default="")
    alert_from: Mapped[str] = mapped_column(String(255), default="")
    alert_to: Mapped[str] = mapped_column(Text, default="")
    slack_webhook_url_encrypted: Mapped[str] = mapped_column(Text, default="")
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
    status: Mapped[str] = mapped_column(String(20), default="open")
    occurrences: Mapped[int] = mapped_column(Integer, default=1)
    last_triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


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


class RiskPolicyAuditEvent(Base):
    __tablename__ = "risk_policy_audit_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    replay_run_id: Mapped[str] = mapped_column(String, ForeignKey("replay_runs.id"), index=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    strategy_version: Mapped[str] = mapped_column(String(120), default="unknown-v1")
    regime_bucket: Mapped[str] = mapped_column(String(40), default="normal")
    drawdown: Mapped[float] = mapped_column(Float, default=0)
    exposure_breach: Mapped[int] = mapped_column(Integer, default=0)
    reject_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StrategyDefinition(Base):
    __tablename__ = "strategy_definitions"

    strategy_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(120), index=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    owner_type: Mapped[str] = mapped_column(String(20), default="admin")
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    active_version_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class RiskCluster(Base):
    __tablename__ = "risk_clusters"

    cluster_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    symbols: Mapped[list[str]] = mapped_column(JSON, default=list)
    cluster_type: Mapped[str] = mapped_column(String(60), default="custom")
    correlation_score: Mapped[float] = mapped_column(Float, default=0)
    risk_weight: Mapped[float] = mapped_column(Float, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PortfolioExposureSnapshot(Base):
    __tablename__ = "portfolio_exposure_snapshot"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    position_size: Mapped[float] = mapped_column(Float, default=0)
    notional: Mapped[float] = mapped_column(Float, default=0)
    strategy_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    cluster_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    exposure_weight: Mapped[float] = mapped_column(Float, default=0)


class Position(Base):
    __tablename__ = "positions"

    position_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    size: Mapped[float] = mapped_column(Float, default=0)
    entry_price: Mapped[float] = mapped_column(Float, default=0)
    current_price: Mapped[float] = mapped_column(Float, default=0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0)
    leverage: Mapped[int] = mapped_column(Integer, default=1)
    strategy_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    cluster_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ManualOverrideLog(Base):
    __tablename__ = "manual_override_log"

    override_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=lambda: str(uuid.uuid4()))
    admin_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(80), index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class StrategyAllocation(Base):
    __tablename__ = "strategy_allocations"

    strategy_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    capital_weight: Mapped[float] = mapped_column(Float, default=1)
    max_capital: Mapped[float] = mapped_column(Float, default=10000)
    current_capital: Mapped[float] = mapped_column(Float, default=0)
    confidence_score: Mapped[float] = mapped_column(Float, default=0)
    performance_score: Mapped[float] = mapped_column(Float, default=0)
    state: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    expected_return: Mapped[float] = mapped_column(Float, default=0)
    realized_return: Mapped[float] = mapped_column(Float, default=0)
    signal_decay: Mapped[float] = mapped_column(Float, default=0)
    execution_quality_score: Mapped[float] = mapped_column(Float, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class StrategyVersion(Base):
    __tablename__ = "strategy_versions"
    __table_args__ = (UniqueConstraint("strategy_id", "version_number", name="uq_strategy_versions_strategy_version"),)

    version_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id: Mapped[str] = mapped_column(String, ForeignKey("strategy_definitions.strategy_id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    config_schema_version: Mapped[str] = mapped_column(String(30), default="1.0")
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    version_hash: Mapped[str] = mapped_column(String(128), index=True)


class StrategyRegimeBinding(Base):
    __tablename__ = "strategy_regime_bindings"

    binding_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_version_id: Mapped[str] = mapped_column(String, ForeignKey("strategy_versions.version_id"), index=True)
    allowed_regimes: Mapped[list[str]] = mapped_column(JSON, default=list)
    blocked_regimes: Mapped[list[str]] = mapped_column(JSON, default=list)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    gating_policy_version: Mapped[str] = mapped_column(String(30), default="1.0")
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CanonicalStrategyRegistry(Base):
    __tablename__ = "canonical_strategy_registry"

    strategy_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    strategy_family: Mapped[str] = mapped_column(String(60), index=True)
    direction: Mapped[str] = mapped_column(String(10), default="both")
    market_regime: Mapped[str] = mapped_column(String(40), default="any")
    entry_logic_version: Mapped[str] = mapped_column(String(40), default="v1")
    exit_logic_version: Mapped[str] = mapped_column(String(40), default="v1")
    risk_profile: Mapped[str] = mapped_column(String(40), default="balanced")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    cooldown_policy: Mapped[str] = mapped_column(String(80), default="symbol:180s")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    entry_long: Mapped[dict] = mapped_column(JSON, default=dict)
    entry_short: Mapped[dict] = mapped_column(JSON, default=dict)
    exit_long: Mapped[dict] = mapped_column(JSON, default=dict)
    exit_short: Mapped[dict] = mapped_column(JSON, default=dict)
    stop_loss: Mapped[dict] = mapped_column(JSON, default=dict)
    take_profit: Mapped[dict] = mapped_column(JSON, default=dict)
    invalidation: Mapped[dict] = mapped_column(JSON, default=dict)
    signal_score: Mapped[dict] = mapped_column(JSON, default=dict)
    invalid_state_rules: Mapped[list[str]] = mapped_column(JSON, default=list)
    cooldown_rules: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_rules: Mapped[dict] = mapped_column(JSON, default=dict)
    is_legacy_candidate: Mapped[bool] = mapped_column(Boolean, default=False)
    in_production_path: Mapped[bool] = mapped_column(Boolean, default=True)
    last_50_signal_quality: Mapped[float] = mapped_column(Float, default=0.0)
    false_allow_rate: Mapped[float] = mapped_column(Float, default=0.0)
    false_reject_rate: Mapped[float] = mapped_column(Float, default=0.0)
    cooldown_state: Mapped[str] = mapped_column(String(20), default="ready")
    risk_block_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    forced_disable_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class StrategyFamilyGate(Base):
    __tablename__ = "strategy_family_gates"

    family: Mapped[str] = mapped_column(String(30), primary_key=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    long_threshold: Mapped[float] = mapped_column(Float, default=5.0)
    short_threshold: Mapped[float] = mapped_column(Float, default=5.0)
    min_strategy_count: Mapped[int] = mapped_column(Integer, default=1)
    max_conflict_score: Mapped[float] = mapped_column(Float, default=2.0)
    regime_match_required: Mapped[bool] = mapped_column(Boolean, default=True)
    risk_clear_required: Mapped[bool] = mapped_column(Boolean, default=True)
    reversal_extra_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class LearningDecisionEvent(Base):
    __tablename__ = "learning_decision_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    decision: Mapped[str] = mapped_column(String(20), default="NO_TRADE", index=True)
    source_strategies: Mapped[list[dict]] = mapped_column(JSON, default=list)
    family_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    regime_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_favorable_excursion: Mapped[float] = mapped_column(Float, default=0)
    max_adverse_excursion: Mapped[float] = mapped_column(Float, default=0)
    hold_duration_minutes: Mapped[float] = mapped_column(Float, default=0)
    outcome_label: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    pnl_normalized: Mapped[float] = mapped_column(Float, default=0)
    stop_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    tp_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    timed_exit: Mapped[bool] = mapped_column(Boolean, default=False)
    invalidated: Mapped[bool] = mapped_column(Boolean, default=False)
    strategy_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    strategy_family: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    scanner_result_id: Mapped[str | None] = mapped_column(String, ForeignKey("user_scanner_results.id"), nullable=True, unique=True, index=True)
    pending_signal_id: Mapped[str | None] = mapped_column(String, ForeignKey("pending_signals.id"), nullable=True, unique=True, index=True)
    position_id: Mapped[str | None] = mapped_column(String, ForeignKey("paper_positions.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class StrategyOutcomeMemory(Base):
    __tablename__ = "strategy_outcome_memory"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id: Mapped[str] = mapped_column(String(120), index=True)
    direction: Mapped[str] = mapped_column(String(10), default="both")
    regime: Mapped[str] = mapped_column(String(30), default="any")
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    hit_rate: Mapped[float] = mapped_column(Float, default=0)
    avg_return: Mapped[float] = mapped_column(Float, default=0)
    avg_mfe: Mapped[float] = mapped_column(Float, default=0)
    avg_mae: Mapped[float] = mapped_column(Float, default=0)
    false_allow_rate: Mapped[float] = mapped_column(Float, default=0)
    false_reject_rate: Mapped[float] = mapped_column(Float, default=0)
    recent_rolling_score: Mapped[float] = mapped_column(Float, default=0)
    decay_adjusted_quality_score: Mapped[float] = mapped_column(Float, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class FamilyOutcomeMemory(Base):
    __tablename__ = "family_outcome_memory"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    family: Mapped[str] = mapped_column(String(30), index=True)
    regime: Mapped[str] = mapped_column(String(30), default="any")
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    hit_rate: Mapped[float] = mapped_column(Float, default=0)
    avg_return: Mapped[float] = mapped_column(Float, default=0)
    volatility_success: Mapped[float] = mapped_column(Float, default=0)
    conflict_success: Mapped[float] = mapped_column(Float, default=0)
    solo_vs_combo_success: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class LearningRecommendation(Base):
    __tablename__ = "learning_recommendations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    family: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    recommendation_type: Mapped[str] = mapped_column(String(30), index=True)
    recommendation_value: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str] = mapped_column(String(280), default="")
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    is_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RegimeSnapshot(Base):
    __tablename__ = "regime_snapshots"

    regime_snapshot_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp_utc: Mapped[str] = mapped_column(String(40), index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    timeframe: Mapped[str] = mapped_column(String(10), index=True)
    strategy_version_id: Mapped[str] = mapped_column(String, ForeignKey("strategy_versions.version_id"), index=True)
    volatility_regime: Mapped[str] = mapped_column(String(40), default="normal")
    trend_regime: Mapped[str] = mapped_column(String(40), default="flat")
    liquidity_regime: Mapped[str] = mapped_column(String(40), default="normal")
    market_state_features: Mapped[dict] = mapped_column(JSON, default=dict)
    feature_set_version: Mapped[str] = mapped_column(String(30), default="1.0")
    regime_score: Mapped[float] = mapped_column(Float, default=0)
    regime_label: Mapped[str] = mapped_column(String(50), index=True)
    regime_hash: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExecutionIntent(Base):
    __tablename__ = "execution_intents"

    intent_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id: Mapped[str] = mapped_column(String, ForeignKey("strategy_definitions.strategy_id"), index=True)
    strategy_version_id: Mapped[str] = mapped_column(String, ForeignKey("strategy_versions.version_id"), index=True)
    account_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    symbol: Mapped[str] = mapped_column(String(20), default="BTCUSDT")
    side: Mapped[str] = mapped_column(String(20), default="BUY")
    order_type: Mapped[str] = mapped_column(String(20), default="MARKET")
    quantity: Mapped[float] = mapped_column(Float, default=0)
    price_reference: Mapped[dict] = mapped_column(JSON, default=dict)
    decision_hash: Mapped[str] = mapped_column(String(128), index=True)
    context_hash: Mapped[str] = mapped_column(String(128), index=True)
    intent_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    correlation_id: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExecutionIntentEvent(Base):
    __tablename__ = "execution_intent_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    intent_id: Mapped[str] = mapped_column(String, ForeignKey("execution_intents.intent_id"), index=True)
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    event_status: Mapped[str] = mapped_column(String(20), default="pending")
    external_order_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DecisionTraceHot(Base):
    __tablename__ = "decision_trace_hot"

    trace_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    correlation_id: Mapped[str] = mapped_column(String(120), index=True)
    strategy_version_id: Mapped[str] = mapped_column(String, ForeignKey("strategy_versions.version_id"), index=True)
    context_hash: Mapped[str] = mapped_column(String(128), index=True)
    decision_hash: Mapped[str] = mapped_column(String(128), index=True)
    intent_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    context_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    decision_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    intent_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DecisionTraceCold(Base):
    __tablename__ = "decision_trace_cold"

    archive_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    correlation_id: Mapped[str] = mapped_column(String(120), index=True)
    strategy_version_id: Mapped[str] = mapped_column(String, ForeignKey("strategy_versions.version_id"), index=True)
    context_hash: Mapped[str] = mapped_column(String(128), index=True)
    decision_hash: Mapped[str] = mapped_column(String(128), index=True)
    intent_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    artifact_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    lifecycle_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    terminal_state: Mapped[str] = mapped_column(String(30), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExternalProviderCredential(Base):
    __tablename__ = "external_provider_credentials"

    provider: Mapped[str] = mapped_column(String(80), primary_key=True)
    api_key_encrypted: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SymbolSelectionWatchlist(Base):
    __tablename__ = "symbol_selection_watchlists"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    source: Mapped[str] = mapped_column(String(20), default="crypto", index=True)
    exchange: Mapped[str] = mapped_column(String(50), default="binance")
    market_type: Mapped[str] = mapped_column(String(20), default="spot")
    symbols: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UserScannerSymbolSelection(Base):
    __tablename__ = "user_scanner_symbol_selections"
    __table_args__ = (
        UniqueConstraint("user_id", "scanner_id", name="uq_user_scanner_symbol_selection"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    scanner_id: Mapped[str] = mapped_column(String(60), default="default", index=True)
    selected_symbols: Mapped[list[str]] = mapped_column(JSON, default=list)
    symbol_source: Mapped[str] = mapped_column(String(20), default="crypto")
    symbol_selection_mode: Mapped[str] = mapped_column(String(40), default="all_market_symbols")
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UserLearningSimulationSuggestion(Base):
    __tablename__ = "user_learning_simulation_suggestions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    symbol: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    strategy_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    family: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    recommendation_type: Mapped[str] = mapped_column(String(40), default="decrease_weight_recommendation", index=True)
    simulation_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str] = mapped_column(String(280), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)


class IndicatorComputationCache(Base):
    __tablename__ = "indicator_computation_cache"
    __table_args__ = (
        UniqueConstraint("cache_key", name="uq_indicator_computation_cache_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    cache_key: Mapped[str] = mapped_column(String(280), index=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    timeframe: Mapped[str] = mapped_column(String(12), index=True)
    bar_close_time: Mapped[str] = mapped_column(String(64), index=True)
    indicator_name: Mapped[str] = mapped_column(String(80), index=True)
    params_version: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ScannerPerformanceSnapshot(Base):
    __tablename__ = "scanner_performance_snapshots"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)
    run_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    stage: Mapped[str] = mapped_column(String(40), default="top_volume_subset", index=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class UniverseRolloutState(Base):
    __tablename__ = "universe_rollout_state"

    id: Mapped[str] = mapped_column(String, primary_key=True, default="global")
    current_stage: Mapped[str] = mapped_column(String(40), default="top_volume_subset")
    recommended_stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    recommendation_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    requires_admin_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    approved_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


@event.listens_for(ExecutionMetric, "before_update", propagate=True)
def _block_execution_metric_update(_, __, ___):
    raise ValueError("execution_metric_immutable")


@event.listens_for(StrategyVersion, "before_update", propagate=True)
def _block_strategy_version_update(_, __, ___):
    raise ValueError("strategy_version_immutable")


@event.listens_for(ExecutionIntent, "before_update", propagate=True)
def _block_execution_intent_update(_, __, ___):
    raise ValueError("execution_intent_immutable")


@event.listens_for(StrategyRegimeBinding, "before_update", propagate=True)
def _block_strategy_regime_binding_update(_, __, ___):
    raise ValueError("strategy_regime_binding_immutable")