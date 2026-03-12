from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    role: str
    status: str
    is_active: bool
    approval_status: str
    approval_requested_at: datetime
    approved_at: datetime | None
    disabled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserRoleUpdateRequest(BaseModel):
    role: str


class UserStatusUpdateRequest(BaseModel):
    status: str


class AdminUserCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    role: str = "admin"


class AlertChannelConfigUpdateRequest(BaseModel):
    resend_api_key: str | None = None
    alert_from: str | None = None
    alert_to: str | None = None
    slack_webhook_url: str | None = None


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
    correlation_rejections_5m: int
    release_gate_status: str
    release_gate_last_checked: str
    execution_errors_5m: int
    risk_anomalies_5m: int
    global_trading_pause: bool
    kill_switch_reasons: list[str]


class KillSwitchStatusResponse(BaseModel):
    triggered: bool
    active: bool
    reasons: list[str]
    triggered_at: str | None = None


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


class RuntimeQuarantineEventResponse(BaseModel):
    id: str
    event_id: str
    event_type: str
    status: str
    retry_count: int
    max_retry: int
    reason_code: str | None = None
    error_message: str
    payload: dict
    created_at: datetime
    updated_at: datetime


class RuntimeStuckIntentResponse(BaseModel):
    intent_id: str
    strategy_id: str
    symbol: str
    status: str
    age_seconds: float
    last_event_at: datetime | None
    reason: str


class SystemAlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    alert_type: str
    severity: str
    message: str
    status: str
    occurrences: int
    last_triggered_at: datetime
    created_at: datetime
    updated_at: datetime
    details: dict
    fingerprint: str | None = None
    entity_key: str | None = None
    root_cause_code: str | None = None
    state_key: str | None = None
    delivery_status: dict


class WeeklyReportArchiveResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    report_id: str
    report_type: str
    period_start: datetime
    period_end: datetime
    generated_at: datetime
    timezone: str
    filename: str
    storage_path: str
    size_bytes: int
    sha256: str
    status: str
    trigger_source: str
    generated_by: str
    created_at: datetime
    updated_at: datetime


class RiskAnalyticsPoint(BaseModel):
    label: str
    value: int


class RiskAnalyticsSeriesPoint(BaseModel):
    date: str
    value: int


class RiskOrchestratorAnalyticsResponse(BaseModel):
    days: int
    generated_at: datetime
    risk_policy_hits: int
    kill_switch_events: int
    duplicate_intent_attempts: int
    reject_reason_distribution: list[RiskAnalyticsPoint]
    breach_by_day: list[RiskAnalyticsSeriesPoint]
    breach_by_strategy: list[RiskAnalyticsPoint]
    breach_by_symbol: list[RiskAnalyticsPoint]


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


class HardeningChecklistTrendResponse(BaseModel):
    average_score_last_5: float
    trend_alarm: bool
    critical_alarm: bool
    active_alerts: list[str]
    recent_runs: list[dict]


class CorrelationMatrixResponse(BaseModel):
    window: int
    symbols: list[str]
    matrix: dict


class LiveActivationConfigBase(BaseModel):
    exchange: str
    market_type: str
    safe_mode_enabled: bool
    live_mode_enabled: bool
    symbol_whitelist: list[str]
    max_position_pct: float = Field(ge=0.01, le=1.0)
    leverage_cap: int = Field(ge=1, le=3)
    max_trades_per_hour: int = Field(ge=1, le=60)
    max_notional_exposure: float = Field(ge=10)
    kill_switch_enabled: bool
    disable_futures: bool
    ip_whitelist_ready: bool
    trading_permission_ready: bool


class LiveActivationConfigUpdate(LiveActivationConfigBase):
    pass


class LiveActivationConfigResponse(LiveActivationConfigBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    updated_at: datetime


class LiveReadinessResponse(BaseModel):
    mode: str
    exchange: str
    market_type: str
    checks: list[dict]
    safe_limits: dict
    docs_references: list[str]


class PermissionCheckRequest(BaseModel):
    api_key: str | None = None
    api_secret: str | None = None


class PermissionCheckResponse(BaseModel):
    api_key_present: bool
    api_secret_present: bool
    masked_key: str
    credential_fingerprint: str
    status: str
    message: str
    controls: list[dict] = Field(default_factory=list)


class TestnetConnectivityResponse(BaseModel):
    status: str
    server_time: int | None
    rest_url: str
    ws_url: str
    message: str


class ExchangeValidateResponse(BaseModel):
    exchange: str
    market_type: str
    environment: str
    is_valid: bool
    permissions: list[str]
    can_trade: bool
    can_withdraw: bool
    reason_codes: list[str]
    capability_match: bool


class MarketTickerResponse(BaseModel):
    exchange: str
    environment: str
    symbol: str
    bid: float
    ask: float
    mid_price: float
    timestamp: str


class ExchangeTestOrderResponse(BaseModel):
    order_id: str
    exchange_order_id: str
    client_order_id: str
    exchange: str
    market_type: str
    environment: str
    price_avg: float | None
    executed_qty: float | None
    slippage_pct: float | None
    execution_time_ms: float | None
    status: str
    final_status: str
    failure_code: str | None
    submitted_at: datetime | None
    ack_at: datetime | None
    final_at: datetime | None
    validation_snapshot_id: str | None
    raw_exchange_status: dict
    state_machine_path: list[str]
    strategy_type: str
    volatility_regime: str
    volatility_pct: float


class ExecutionLifecycleEventResponse(BaseModel):
    event_name: str
    event_timestamp: datetime
    payload: dict


class ExchangeLifecycleEvidenceResponse(BaseModel):
    order_id: str
    exchange_order_id: str
    final_status: str
    submitted_at: datetime | None
    ack_at: datetime | None
    final_at: datetime | None
    timeline: list[ExecutionLifecycleEventResponse]


class UserReadinessChecklistResponse(BaseModel):
    readiness_status: str
    exchange: str | None = None
    market_type: str | None = None
    environment: str | None = None
    capability_match: bool | None = None
    has_api_key: bool
    has_api_secret: bool
    validation_success: bool
    can_trade: bool
    is_testnet_environment: bool
    is_validation_stale: bool
    validation_timestamp: datetime | None
    validation_snapshot_id: str | None
    stale_after_minutes: int
    last_error_reason: str


class ReleaseGateOverrideRequest(BaseModel):
    reason_code: str
    reason_note: str
    ttl_minutes: int = Field(default=30, ge=1, le=60)
    deploy_context: dict = Field(default_factory=dict)


class ReleaseGateOverrideResponse(BaseModel):
    override_id: str
    admin_user_id: str
    reason_code: str
    reason_note: str
    release_gate_snapshot: dict
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    deploy_context: dict
    used_deploy_count: int


class OverrideAnalyticsPointResponse(BaseModel):
    date: str
    blocked_gate_count: int
    override_count: int
    override_deploy_count: int


class OverrideAnalyticsResponse(BaseModel):
    days: int
    points: list[OverrideAnalyticsPointResponse]
    alert_source_breakdown: dict[str, int]


class AlertHistoryItemResponse(BaseModel):
    created_at: datetime
    action: str
    severity: str
    source: str
    details: dict


class UserRiskSettingsResponse(BaseModel):
    allocation_pct: float
    trade_risk_pct: float
    daily_loss_limit_pct: float
    compounding_enabled: bool
    base_capital: float


class UserRiskSettingsUpdate(BaseModel):
    allocation_pct: float
    trade_risk_pct: float
    daily_loss_limit_pct: float
    compounding_enabled: bool


class UserRiskPreviewResponse(BaseModel):
    market_type: str
    current_capital: float
    position_size: float
    risk_amount: float
    allocation_pct: float
    trade_allocation_amount: float
    trade_risk_pct: float
    max_trade_loss_amount: float
    total_capital_impact_pct: float
    compounding_enabled: bool
    next_trade_base_capital: float
    leverage: int | None = None
    margin_mode: str | None = None
    position_side: str | None = None
    estimated_liquidation_buffer_pct: float | None = None
    margin_usage_pct: float | None = None
    warnings: list[str]


class ReplayRunRequest(BaseModel):
    symbol: str = "BTCUSDT"
    timeframe: str = "15m"
    exchange: str = "binance"
    market_type: str = "futures"
    environment: str = "testnet"
    strategy_type: str = "trend_following"
    limit: int = Field(default=300, ge=120, le=1000)


class ReplayExecutionItemResponse(BaseModel):
    symbol: str
    timeframe: str
    signal: str
    direction: str
    market_price: float
    simulated_fill_price: float | None
    simulated_latency_ms: float | None
    simulated_slippage_pct: float | None
    lifecycle: list[str]
    status: str
    risk_tags: list[str]
    candle_timestamp: str


class ReplayRunResponse(BaseModel):
    run_id: str
    user_id: str
    exchange: str
    market_type: str
    environment: str
    symbol: str
    timeframe: str
    strategy_type: str
    candles_processed: int
    executions_count: int
    filled_count: int
    canceled_count: int
    avg_simulated_latency_ms: float
    avg_simulated_slippage_pct: float
    status: str
    started_at: datetime
    completed_at: datetime | None


class ReplayRunDetailResponse(ReplayRunResponse):
    metrics: dict
    executions: list[ReplayExecutionItemResponse]


class ReplayRiskSummaryResponse(BaseModel):
    schema_version: str
    run_id: str
    strategy_version: str
    max_drawdown: float
    sharpe: float
    win_rate: float
    profit_factor: float
    avg_slippage_bps: float
    volatility_bucket: str
    regime_bucket_distribution: dict[str, int]
    exposure_breach_count: int
    risk_reject_count: int
    evidence_type: str
    artifact_id: str | None = None
    export_file: str
    generated_at: datetime


class ExecutionCorrectionCreate(BaseModel):
    correction_type: str = "annotation"
    reason_code: str = "manual_correction"
    note: str = ""
    patch_payload: dict = Field(default_factory=dict)


class ExecutionCorrectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    execution_metric_id: str
    user_id: str
    correction_type: str
    reason_code: str
    note: str
    patch_payload: dict
    created_at: datetime


class LifecycleProofResponse(BaseModel):
    lifecycle_proof_status: str
    evidence_type: str
    exchange: str
    market_type: str
    environment: str
    reason_codes: list[str]
    exchange_artifact_id: str | None = None
    fallback_artifact_id: str | None = None
    exchange_evidence_file: str
    fallback_replay_evidence_file: str | None
    replay_run_id: str | None
    message: str
    generated_at: datetime


class ArtifactManifestItemResponse(BaseModel):
    artifact_id: str
    filename: str
    artifact_type: str
    sha256: str
    size: int
    created_at: str
    proof_id: str
    evidence_type: str
    status: str
    chain_position: int | None = None
    prev_chain_hash: str | None = None
    chain_hash: str | None = None


class ArtifactVerifyResponse(BaseModel):
    artifact_id: str
    filename: str
    sha256_expected: str
    sha256_actual: str
    verified: bool
    chain_position: int | None = None
    prev_chain_hash: str | None = None
    chain_hash: str | None = None
    chain_valid: bool
    chain_broken: bool
    chain_broken_index: int | None = None
    chain_broken_artifact_id: str | None = None


class ArtifactBatchVerifyItem(BaseModel):
    artifact_id: str
    filename: str | None = None
    artifact_type: str | None = None
    status: str
    reason_codes: list[str]


class ArtifactBatchVerifyResponse(BaseModel):
    total: int
    verified: int
    mismatch: int
    missing: int
    chain_broken: int
    chain_broken_index: int | None = None
    chain_broken_artifact_id: str | None = None
    items: list[ArtifactBatchVerifyItem]


class StrategyDefinitionCreate(BaseModel):
    name: str
    code: str
    description: str = ""


class StrategyVersionCreate(BaseModel):
    config_json: dict
    config_schema_version: str = "1.0"


class StrategyDefinitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_id: str
    name: str
    code: str
    description: str
    owner_type: str
    created_by: str
    status: str
    active_version_id: str | None
    created_at: datetime
    updated_at: datetime


class StrategyVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version_id: str
    strategy_id: str
    version_number: int
    config_json: dict
    config_schema_version: str
    created_by: str
    created_at: datetime
    version_hash: str


class StrategyDetailResponse(BaseModel):
    strategy: StrategyDefinitionResponse
    versions: list[StrategyVersionResponse]


class DecisionContextInput(BaseModel):
    context_id: str
    account_id: str | None = None
    timestamp_utc: str
    symbol: str
    timeframe: str
    market_snapshot: dict
    market_snapshot_hash: str
    position_state: dict
    risk_state: dict
    account_state_projection: dict
    strategy_version_id: str
    strategy_version_hash: str
    input_features: dict
    correlation_id: str


class DecisionResultResponse(BaseModel):
    decision_id: str
    action: str
    order_intent: dict
    size: float
    price_reference: dict
    confidence: float
    risk_score: float
    reason_codes: list[str]
    strategy_version_id: str | None
    context_hash: str
    decision_hash: str


class RuntimeDispatchRequest(BaseModel):
    strategy_id: str
    decision_context: DecisionContextInput


class RuntimeEventEnvelopeResponse(BaseModel):
    event_id: str
    event_type: str
    correlation_id: str
    causation_id: str | None
    partition_key: str
    created_at: str
    schema_version: str
    ordering: int
    payload: dict
    payload_hash: str


class ExecutionIntentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    intent_id: str
    strategy_id: str
    strategy_version_id: str
    account_id: str | None = None
    symbol: str
    side: str
    order_type: str
    quantity: float
    price_reference: dict
    decision_hash: str
    context_hash: str
    intent_hash: str
    correlation_id: str
    status: str
    created_at: datetime


class ExecutionIntentEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    intent_id: str
    event_type: str
    event_status: str
    external_order_id: str | None
    payload: dict
    created_at: datetime


class RuntimeDispatchResponse(BaseModel):
    decision_result: DecisionResultResponse
    execution_intent: dict | None
    emitted_events: list[RuntimeEventEnvelopeResponse]


class StrategyRegimeBindingCreate(BaseModel):
    strategy_version_id: str
    allowed_regimes: list[str] = Field(default_factory=list)
    blocked_regimes: list[str] = Field(default_factory=list)
    priority: int = 100
    gating_policy_version: str = "1.0"


class StrategyRegimeBindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    binding_id: str
    strategy_version_id: str
    allowed_regimes: list[str]
    blocked_regimes: list[str]
    priority: int
    gating_policy_version: str
    created_by: str
    created_at: datetime


class RegimeSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    regime_snapshot_id: str
    timestamp_utc: str
    symbol: str
    timeframe: str
    strategy_version_id: str
    volatility_regime: str
    trend_regime: str
    liquidity_regime: str
    market_state_features: dict
    feature_set_version: str
    regime_score: float
    regime_label: str
    regime_hash: str
    created_at: datetime


class RegimeEvaluationResponse(BaseModel):
    allowed: bool
    reason_code: str | None = None
    snapshot: RegimeSnapshotResponse
    binding_id: str | None = None


class StrategyRegimeOverviewResponse(BaseModel):
    bindings: list[StrategyRegimeBindingResponse]
    snapshots: list[RegimeSnapshotResponse]
    reject_distribution: dict[str, int]


class RiskOrchestratorPolicyResponse(BaseModel):
    reference_equity_usd: float
    account_max_notional_pct: float
    symbol_max_notional_pct: float
    strategy_max_concurrent_positions: int
    strategy_cooldown_seconds: int
    max_order_frequency_per_min: int
    max_order_burst_per_10s: int
    daily_loss_limit_pct: float
    duplicate_suppression_window_seconds: int
    updated_at: datetime | None = None


class RiskOrchestratorPolicyUpdate(BaseModel):
    reference_equity_usd: float
    account_max_notional_pct: float
    symbol_max_notional_pct: float
    strategy_max_concurrent_positions: int
    strategy_cooldown_seconds: int
    max_order_frequency_per_min: int
    max_order_burst_per_10s: int
    daily_loss_limit_pct: float
    duplicate_suppression_window_seconds: int


class RiskOrchestratorExposureResponse(BaseModel):
    key: str
    open_count: int
    notional: float


class RiskOrchestratorStatusResponse(BaseModel):
    policy: RiskOrchestratorPolicyResponse
    kill_switch_active: bool
    kill_switch_reasons: list[str]
    open_intents: int
    open_intents_by_symbol: list[RiskOrchestratorExposureResponse]
    open_intents_by_strategy: list[RiskOrchestratorExposureResponse]


class RiskOrchestratorRejectResponse(BaseModel):
    id: str
    created_at: datetime
    strategy_id: str | None = None
    strategy_version_id: str | None = None
    symbol: str | None = None
    reason_codes: list[str]
    details: dict


class RiskOrchestratorSupervisorBreach(BaseModel):
    breach_type: str
    key: str
    open_count: int
    notional: float
    limit_pct: float | None = None


class RiskOrchestratorSupervisorResponse(BaseModel):
    evaluated_at: datetime
    breaches: list[RiskOrchestratorSupervisorBreach]


class UserPortfolioOverviewResponse(BaseModel):
    current_capital: float
    available_balance: float
    open_position_balance: float
    closed_pnl: float
    compounding_enabled: bool
    next_base_capital: float


class AlertPolicyResponse(BaseModel):
    admin_notification_enabled: bool
    ops_webhook_url: str
    monitoring_alert_log_enabled: bool
    execution_quality_warning_threshold: float
    execution_quality_critical_threshold: float
    permission_drift_warning_per_day: int
    permission_drift_critical_per_day: int
    gate_override_warning_per_day: int
    gate_override_critical_per_day: int


class AlertPolicyUpdate(BaseModel):
    admin_notification_enabled: bool
    ops_webhook_url: str
    monitoring_alert_log_enabled: bool
    execution_quality_warning_threshold: float
    execution_quality_critical_threshold: float
    permission_drift_warning_per_day: int
    permission_drift_critical_per_day: int
    gate_override_warning_per_day: int
    gate_override_critical_per_day: int


class ActiveAlertResponse(BaseModel):
    code: str
    severity: str
    value: float
    threshold_warning: float
    threshold_critical: float


class ExchangeRegistryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    exchange_code: str
    exchange_name: str
    status: str
    supported_market_types: list[str]
    supports_testnet: bool
    supports_live: bool
    health_status: str
    rate_limit_status: str
    adapter_version: str
    updated_at: datetime


class ExchangeRegistryUpdate(BaseModel):
    status: str
    health_status: str
    rate_limit_status: str
    adapter_version: str


class ExchangeRegistryCreate(BaseModel):
    exchange_code: str
    exchange_name: str
    status: str = "active"
    supported_market_types: list[str] = Field(default_factory=lambda: ["spot", "futures"])
    supports_testnet: bool = True
    supports_live: bool = False
    health_status: str = "healthy"
    rate_limit_status: str = "ok"
    adapter_version: str = "v1"


class ExchangeCapabilityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    exchange_code: str
    market_type: str
    supports_spot: bool
    supports_futures: bool
    supports_test_order: bool
    supports_quote_qty: bool
    supports_reduce_only: bool
    supports_leverage: bool
    supports_margin_mode: bool
    supports_hedge_mode: bool
    updated_at: datetime


class ExchangeCapabilityUpdate(BaseModel):
    supports_test_order: bool
    supports_quote_qty: bool
    supports_reduce_only: bool
    supports_leverage: bool
    supports_margin_mode: bool
    supports_hedge_mode: bool


class ExchangeCapabilityCreate(BaseModel):
    exchange_code: str
    market_type: str
    supports_spot: bool
    supports_futures: bool
    supports_test_order: bool
    supports_quote_qty: bool
    supports_reduce_only: bool
    supports_leverage: bool
    supports_margin_mode: bool
    supports_hedge_mode: bool


class AllowedMarketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    exchange_code: str
    market_type: str
    environment: str
    enabled: bool
    updated_at: datetime


class AllowedMarketToggle(BaseModel):
    enabled: bool


class AllowedMarketCreate(BaseModel):
    exchange_code: str
    market_type: str
    environment: str
    enabled: bool = True


class UserVenueAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    exchange_code: str
    spot_allowed: bool
    futures_allowed: bool
    testnet_allowed: bool
    live_allowed: bool
    updated_at: datetime


class UserVenueAssignmentUpdate(BaseModel):
    user_id: str
    exchange_code: str
    spot_allowed: bool
    futures_allowed: bool
    testnet_allowed: bool
    live_allowed: bool


class UserVenueOptionResponse(BaseModel):
    exchange: str
    market_type: str
    environment: str
    venue_state: str


class VenueHealthSummaryResponse(BaseModel):
    exchange_health: dict[str, str]
    market_availability: dict[str, bool]
    capability_mismatch: list[str]
    adapter_error_status: dict[str, str]


class ExchangeSettingsUpdateRequest(BaseModel):
    exchange: str = "binance"
    mode: str = "testnet"
    api_key: str
    api_secret: str


class ExchangeSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    exchange: str
    mode: str
    has_api_key: bool
    has_api_secret: bool
    updated_at: datetime | None


class PermissionControlResult(BaseModel):
    key: str
    status: str
    reason: str
    timestamp: str


class PermissionStatusResponse(BaseModel):
    overall_status: str
    live_activation: str
    controls: list[PermissionControlResult]


class TestOrderResponse(BaseModel):
    execution_id: str
    symbol: str
    strategy_direction: str
    strategy_type: str
    volatility_regime: str
    volatility_pct: float
    status: str
    state_machine_path: list[str]
    expected_price: float
    fill_price: float | None
    slippage: float | None
    execution_latency: float | None
    execution_quality_score: float
    release_gate_status: str
    timestamp: str


class ExecutionQualitySummaryResponse(BaseModel):
    execution_id: str
    symbol: str
    status: str
    strategy_type: str
    volatility_regime: str
    volatility_pct: float
    expected_price: float
    fill_price: float | None
    slippage: float | None
    execution_latency: float | None
    execution_quality_score: float
    timestamp: datetime


class PermissionDriftPointResponse(BaseModel):
    date: str
    event_count: int
    critical_count: int


class PermissionDriftTrendResponse(BaseModel):
    days: int
    points: list[PermissionDriftPointResponse]
    affected_user_count: int
    latest_timestamp: datetime | None
    critical_drift_count: int


class ReleaseGateStatusResponse(BaseModel):
    status: str
    reasons: list[str]
    fail_reasons: list[str]
    warning_reasons: list[str]
    live_activation: str
    environment: str | None = None
    reason_code: str | None = None
    override_active: bool = False
    override_expires_at: datetime | None = None
    override_id: str | None = None


class LiveReadinessScoreResponse(BaseModel):
    readiness_score: float
    permission_ready: bool
    risk_engine_pass: bool
    execution_simulation_pass: bool
    correlation_model_pass: bool
    hardening_checklist_pass: bool
    release_gate_status: str
    live_activation: str
    critical_blockers: list[str]