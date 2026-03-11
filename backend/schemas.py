from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


class BotProfileBase(BaseModel):
    name: str
    exchange: str = "binance"
    market_type: str = "spot"
    symbols: list[str]
    strategy_type: str
    timeframe: str = "15m"
    trend_timeframe: str = "1h"
    leverage: int = Field(default=3, ge=1, le=25)
    is_enabled: bool = True


class BotProfileCreate(BotProfileBase):
    pass


class BotProfileUpdate(BaseModel):
    name: str
    exchange: str
    market_type: str
    symbols: list[str]
    strategy_type: str
    timeframe: str
    trend_timeframe: str
    leverage: int = Field(default=3, ge=1, le=25)
    is_enabled: bool


class BotProfileResponse(BotProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    is_running: bool
    created_at: datetime
    updated_at: datetime


class RiskPolicyBase(BaseModel):
    name: str
    position_size_pct: float
    atr_stop_multiplier: float
    risk_reward_ratio: float
    daily_loss_cutoff_pct: float
    max_open_positions: int
    max_leverage: int = 3
    spread_limit_bps: int = 30
    slippage_limit_bps: int = 40
    min_liquidity_usdt: int = 100000


class RiskPolicyCreate(RiskPolicyBase):
    pass


class RiskPolicyUpdate(RiskPolicyBase):
    pass


class RiskPolicyResponse(RiskPolicyBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime


class StrategyTemplateBase(BaseModel):
    name: str
    strategy_type: str
    parameters: dict
    is_active: bool = True


class StrategyTemplateCreate(StrategyTemplateBase):
    pass


class StrategyTemplateUpdate(StrategyTemplateBase):
    pass


class StrategyTemplateResponse(StrategyTemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    actor_user_id: str | None
    actor_role: str
    action: str
    entity_type: str
    entity_id: str
    severity: str
    details: dict
    created_at: datetime


class MockOrderRequest(BaseModel):
    bot_profile_id: str
    symbol: str
    side: str
    quantity: float = Field(gt=0)


class ExecutionEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    bot_profile_id: str
    exchange: str
    symbol: str
    side: str
    quantity: float
    mock_price: float
    execution_status: str
    response_payload: dict
    note: str
    created_at: datetime


class AdminControlUpdate(BaseModel):
    max_leverage_cap: int = Field(default=5, ge=1, le=50)
    max_open_positions_cap: int = Field(default=10, ge=1, le=200)
    minimum_volume_usd: float = Field(default=1000000, ge=0)
    max_spread_bps: int = Field(default=40, ge=1, le=500)
    spot_universe: list[str] = Field(default_factory=list)
    futures_universe: list[str] = Field(default_factory=list)
    whitelist: list[str] = Field(default_factory=list)
    blacklist: list[str] = Field(default_factory=list)
    emergency_mode: bool = False
    disable_futures: bool = False


class AdminControlResponse(AdminControlUpdate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    updated_at: datetime


class UniversePreviewResponse(BaseModel):
    spot_symbols: list[str]
    futures_symbols: list[str]
    filters: dict
    generated_at: datetime


class SignalEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    bot_profile_id: str
    user_id: str
    symbol: str
    market_type: str
    timeframe: str
    strategy_id: str
    signal: str
    direction: str
    confidence: float
    reason_codes: list[str]
    generated_at: datetime


class PaperPositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    bot_profile_id: str
    symbol: str
    market_type: str
    side: str
    quantity: float
    leverage: int
    entry_price: float
    stop_loss: float
    take_profit: float
    status: str
    unrealized_pnl: float
    realized_pnl: float
    opened_at: datetime
    closed_at: datetime | None
    updated_at: datetime


class ManualClosePositionRequest(BaseModel):
    reason: str = "manual_close"


class PipelineMonitoringResponse(BaseModel):
    websocket_status: str
    heartbeat: str
    signal_rate_last_5m: int
    paper_trades_last_5m: int
    open_positions: int
    latency_ms: float
    queue_depth: int
    active_bots_running: int
    websocket_reconnects_5m: int
    idempotency_keys_5m: int
    duplicate_signals_blocked_5m: int
    execution_transitions_5m: int
    failed_events_pending: int
    failed_events_dead: int


class ExecutionPolicyBase(BaseModel):
    strategy_type: str
    execution_style: str
    order_preference: str
    timeout_seconds: int = Field(ge=1, le=120)
    fallback_behavior: str
    partial_fill_tolerance_pct: float = Field(ge=0, le=100)
    execution_urgency: str
    retry_limit: int = Field(ge=0, le=10)
    is_active: bool = True


class ExecutionPolicyCreate(ExecutionPolicyBase):
    pass


class ExecutionPolicyUpdate(ExecutionPolicyBase):
    pass


class ExecutionPolicyResponse(ExecutionPolicyBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime


class RiskExposureGroupBase(BaseModel):
    name: str
    label: str
    symbols: list[str]
    max_group_open_positions: int = Field(ge=1, le=200)
    max_group_directional_positions: int = Field(ge=1, le=200)
    max_group_risk_pct: float = Field(ge=1, le=100)


class RiskExposureGroupCreate(RiskExposureGroupBase):
    pass


class RiskExposureGroupUpdate(RiskExposureGroupBase):
    pass


class RiskExposureGroupResponse(RiskExposureGroupBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime


class FailedEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_type: str
    entity_type: str
    entity_id: str
    payload: dict
    error_message: str
    status: str
    retry_count: int
    max_retry: int
    next_retry_at: datetime | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None


class StateRebuildLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    rebuild_type: str
    status: str
    trigger_source: str
    details: dict
    started_at: datetime
    finished_at: datetime | None


class BacktestResultCardBase(BaseModel):
    strategy_type: str
    market_type: str
    timeframe: str
    sample_size: int = Field(ge=1)
    win_rate: float = Field(ge=0, le=100)
    max_drawdown: float = Field(ge=0, le=100)
    profit_factor: float = Field(ge=0)
    sharpe_like_score: float
    performance_summary: str
    risk_label: str
    period_start: str
    period_end: str


class BacktestResultCardCreate(BacktestResultCardBase):
    pass


class BacktestResultCardUpdate(BacktestResultCardBase):
    pass


class BacktestResultCardResponse(BacktestResultCardBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime


class ExecutionStateTransitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    execution_event_id: str
    state: str
    sequence: int
    details: dict
    occurred_at: datetime


class HardeningSummaryResponse(BaseModel):
    websocket_reconnects_5m: int
    idempotency_keys_5m: int
    duplicate_signals_blocked_5m: int
    execution_transitions_5m: int
    failed_events_pending: int
    failed_events_dead: int
    last_state_rebuild_status: str
    last_state_rebuild_at: datetime | None


class HardeningChecklistRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    score: float
    critical_blocked: bool
    readiness_status: str
    checklist_items: list[dict]
    summary: dict
    created_at: datetime