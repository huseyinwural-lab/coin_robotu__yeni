import uuid
from datetime import datetime, timedelta

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from model_domains.shared import utcnow

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

class UserExecutionIntent(Base):
    __tablename__ = "user_execution_intents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # FAZ-2 sözleşmesi: persistence tarafında tekillik garantisi intent_id ile sağlanır.
    intent_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, default=lambda: str(uuid.uuid4()))
    # idempotency_key: canonical payload hash'i (intent_id üretim girdisi) - audit/debug amaçlı saklanır.
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True, index=True)
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

class ExecutionStateTransition(Base):
    __tablename__ = "execution_state_transitions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    execution_event_id: Mapped[str] = mapped_column(String, ForeignKey("execution_events.id"), index=True)
    state: Mapped[str] = mapped_column(String(30), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

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
    trading_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    max_total_exposure: Mapped[float] = mapped_column(Float, default=150)
    max_active_positions: Mapped[int] = mapped_column(Integer, default=3)
    canary_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    canary_symbols: Mapped[list[str]] = mapped_column(JSON, default=list)
    canary_max_capital_usdt: Mapped[float] = mapped_column(Float, default=50)
    canary_max_positions: Mapped[int] = mapped_column(Integer, default=1)
    disable_futures: Mapped[bool] = mapped_column(Boolean, default=False)
    ip_whitelist_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    trading_permission_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class TestnetExecutionLog(Base):
    __tablename__ = "testnet_execution_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
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
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
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


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    run_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    actor_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)
    actor_role: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(60), default="strategy_intelligence", index=True)
    status: Mapped[str] = mapped_column(String(30), default="preview", index=True)
    request_mode: Mapped[str] = mapped_column(String(20), default="single")
    symbols: Mapped[dict] = mapped_column(JSON, default=list)
    summary_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    input_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    output_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    approval_request_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SimulationScenarioItem(Base):
    __tablename__ = "simulation_scenario_items"

    scenario_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(String(120), ForeignKey("simulation_runs.run_id"), index=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    scenario_label: Mapped[str] = mapped_column(String(80), default="default")
    input_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    output_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_delta: Mapped[float] = mapped_column(Float, default=0)
    decision_delta: Mapped[str] = mapped_column(String(40), default="UNCHANGED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class DecisionApprovalRequest(Base):
    __tablename__ = "decision_approval_requests"

    request_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=lambda: str(uuid.uuid4()))
    request_type: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    requested_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    requested_role: Mapped[str] = mapped_column(String(40), default="admin")
    reason_note: Mapped[str] = mapped_column(Text, default="")
    simulation_run_id: Mapped[str | None] = mapped_column(String(120), ForeignKey("simulation_runs.run_id"), nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    ack_by: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    target_type: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    target_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    explanation_summary: Mapped[str] = mapped_column(Text, default="")
    decision_factors: Mapped[dict] = mapped_column(JSON, default=dict)
    previous_state_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    source_request_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    linked_revert_request_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    reverted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reverted_by: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    revert_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class EscalationCenterItem(Base):
    __tablename__ = "escalation_center_items"

    escalation_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=lambda: str(uuid.uuid4()))
    linked_request_id: Mapped[str] = mapped_column(String(120), ForeignKey("decision_approval_requests.request_id"), index=True)
    linked_simulation_run_id: Mapped[str | None] = mapped_column(String(120), ForeignKey("simulation_runs.run_id"), nullable=True, index=True)
    state: Mapped[str] = mapped_column(String(30), default="active", index=True)
    escalation_level: Mapped[str] = mapped_column(String(20), default="L1")
    escalation_reason: Mapped[str] = mapped_column(Text, default="")
    breach_age_seconds: Mapped[int] = mapped_column(Integer, default=0)
    current_owner: Mapped[str] = mapped_column(String(120), default="unassigned", index=True)
    ack_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)
    ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

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
    revision_id: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str] = mapped_column(String(120), default="system")
    change_reason: Mapped[str] = mapped_column(Text, default="manual_update")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class StrategyAllocationSnapshot(Base):
    __tablename__ = "strategy_allocation_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    reason_note: Mapped[str] = mapped_column(Text, default="")
    strategy_count: Mapped[int] = mapped_column(Integer, default=0)
    total_weight: Mapped[float] = mapped_column(Float, default=0)
    total_capital: Mapped[float] = mapped_column(Float, default=0)
    used_capital: Mapped[float] = mapped_column(Float, default=0)
    summary_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    rows_payload: Mapped[list[dict]] = mapped_column(JSON, default=list)
    revision_map: Mapped[dict] = mapped_column(JSON, default=dict)
    source_request_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    restored_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)


class StrategyAllocationApprovalRequest(Base):
    __tablename__ = "strategy_allocation_approval_requests"

    request_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=lambda: str(uuid.uuid4()))
    request_type: Mapped[str] = mapped_column(String(100), default="strategy_allocation")
    action_type: Mapped[str] = mapped_column(String(80), index=True)
    target_type: Mapped[str] = mapped_column(String(80), default="unknown")
    target_id: Mapped[str] = mapped_column(String(160), default="unknown")
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    requested_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    requested_role: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reason_note: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    revision_context: Mapped[dict] = mapped_column(JSON, default=dict)
    stale_state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    stale_reason_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    stale_conflicts: Mapped[list[dict]] = mapped_column(JSON, default=list)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    rejected_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    explanation_summary: Mapped[str] = mapped_column(Text, default="")
    decision_factors: Mapped[dict] = mapped_column(JSON, default=dict)
    previous_state_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    source_request_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    linked_revert_request_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    reverted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reverted_by: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    revert_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: utcnow() + timedelta(hours=24))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class ExecutionIntent(Base):
    __tablename__ = "execution_intents"

    intent_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id: Mapped[str] = mapped_column(String, ForeignKey("strategy_definitions.strategy_id"), index=True)
    strategy_version_id: Mapped[str] = mapped_column(String, ForeignKey("strategy_versions.version_id"), index=True)
    account_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
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
