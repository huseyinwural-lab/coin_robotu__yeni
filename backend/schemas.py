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
    first_name: str | None = Field(default=None, max_length=60)
    last_name: str | None = Field(default=None, max_length=60)
    full_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)


class EmailVerificationRequest(BaseModel):
    email: EmailStr


class EmailVerificationVerifyRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=12)


class EmailVerificationResponse(BaseModel):
    status: str
    email: str
    email_verified: bool
    expires_at: datetime | None = None
    verification_code: str | None = None
    message: str | None = None


class AuthOnboardingStatusResponse(BaseModel):
    email: str
    email_verified: bool
    approval_status: str
    is_active: bool
    full_name: str | None = None
    phone: str | None = None
    steps: list[dict] = Field(default_factory=list)


class OnboardingRiskFoundationRequest(BaseModel):
    risk_score: float = Field(ge=0, le=100)
    aml_flag: str = Field(default="clear")
    aml_reason: str | None = None
    api_key_validity: str = Field(default="unknown")
    balance_usd: float = Field(default=0)
    country_code: str | None = Field(default=None, max_length=8)
    leverage_permission: bool = False
    futures_capability: bool = False
    spot_capability: bool = True


class OnboardingKycReviewRequest(BaseModel):
    review_status: str
    review_note: str = Field(min_length=5, max_length=500)


class OnboardingDecisionRequest(BaseModel):
    decision: str
    reason: str = Field(default="", max_length=1000)
    explanation: str | None = Field(default=None, max_length=2000)
    confirm_token: str = ""


class OnboardingKycDocumentResponse(BaseModel):
    document_id: str
    file_name: str
    file_type: str
    review_status: str
    review_note: str | None = None
    uploaded_at: datetime | None = None


class OnboardingDecisionResponse(BaseModel):
    user_id: str
    approval_status: str
    is_active: bool
    decision_log_id: str
    decision_engine: dict = Field(default_factory=dict)
    decision_support: dict = Field(default_factory=dict)


class OnboardingContextResponse(BaseModel):
    user_id: str
    email: str
    approval_status: str
    account_age_days: int
    exchange_connections: list[dict] = Field(default_factory=list)
    api_key_validity: str
    balance_usd: float
    first_funding_at: str | None = None
    kyc_status: str
    kyc_documents: list[dict] = Field(default_factory=list)
    risk_score: float
    aml_flag: str
    aml_reason: str | None = None
    trading_eligibility: bool
    region_compliance: str
    leverage_permission: bool
    futures_capability: bool
    spot_capability: bool
    risk_flags: list[str] = Field(default_factory=list)
    approval_disabled: bool
    approval_disable_reasons: list[str] = Field(default_factory=list)
    missing_data_fields: list[str] = Field(default_factory=list)
    profile_last_updated_at: str | None = None
    api_preview: dict = Field(default_factory=dict)
    workflow_case: dict | None = None
    assigned_to: str | None = None
    last_decision_attempt: dict | None = None
    last_events: list[dict] = Field(default_factory=list)
    audit_trail_recent: list[dict] = Field(default_factory=list)
    decision_engine: dict = Field(default_factory=dict)
    decision_support: dict = Field(default_factory=dict)


class OnboardingWorkflowStartRequest(BaseModel):
    assigned_admin_id: str | None = None


class OnboardingWorkflowAssignRequest(BaseModel):
    assigned_admin_id: str


class OnboardingWorkflowStepCompleteRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class OnboardingWorkflowEscalateRequest(BaseModel):
    supervisor_admin_id: str | None = None
    note: str | None = Field(default=None, max_length=500)


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
    sendgrid_api_key: str | None = None
    resend_api_key: str | None = None
    alert_from: str | None = None
    alert_to: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    slack_webhook_url: str | None = None


class AuthResponse(BaseModel):
    access_token: str | None = None
    token: str | None = None
    token_type: str = "bearer"
    role: str | None = None
    user: UserResponse | None = None
    mfa_required: bool = False
    mfa_challenge_token: str | None = None
    mfa_methods: list[str] = Field(default_factory=list)
    mfa_expires_at: datetime | None = None
    mfa_grace_active: bool = False
    mfa_grace_expires_at: datetime | None = None
    mfa_setup_required: bool = False
    mfa_verified: bool = False
    requires_step_up: bool = False
    risk_level: str = "low"
    risk_reasons: list[str] = Field(default_factory=list)
    challenge_reason: str | None = None
    step_up_required: bool = False
    step_up_valid_until: datetime | None = None
    step_up_scope: list[str] = Field(default_factory=list)
    email_delivery_status: str | None = None
    email_code_preview: str | None = None


class MfaSettingsUpdateRequest(BaseModel):
    is_enabled: bool
    enabled_methods: list[str] = Field(default_factory=list)


class MfaSettingsResponse(BaseModel):
    is_enabled: bool
    enabled_methods: list[str] = Field(default_factory=list)
    totp_configured: bool
    totp_verified: bool
    email_otp_verified: bool
    backup_codes_remaining: int = 0
    mfa_enabled_not_verified: bool = False
    backup_download_required: bool = False
    mfa_grace_active: bool = False
    mfa_grace_expires_at: datetime | None = None
    last_verified_at: datetime | None = None
    updated_at: datetime | None = None


class MfaTotpSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str
    issuer: str
    account_name: str


class MfaTotpVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class MfaBackupCodesResponse(BaseModel):
    generated_codes: list[str] = Field(default_factory=list)
    backup_codes_remaining: int = 0
    generated_at: datetime


class MfaSecureActionRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    method: str = Field(min_length=4, max_length=20)
    code: str = Field(min_length=4, max_length=12)
    revoke_other_sessions: bool = False


class MfaChallengeVerifyRequest(BaseModel):
    challenge_token: str = Field(min_length=20, max_length=200)
    method: str = Field(min_length=4, max_length=20)
    code: str = Field(default="", max_length=12)


class AuthStepUpVerifyRequest(BaseModel):
    method: str = Field(min_length=4, max_length=20)
    code: str = Field(min_length=4, max_length=12)
    scope: list[str] = Field(default_factory=list)


class MfaChallengeCreateRequest(BaseModel):
    reason: str = Field(default="manual_challenge", min_length=3, max_length=80)


class MfaChallengeResendResponse(BaseModel):
    mfa_challenge_token: str
    email_delivery_status: str
    email_code_preview: str | None = None
    mfa_expires_at: datetime | None = None


class BrandSettingsUpdateRequest(BaseModel):
    app_name: str = Field(min_length=2, max_length=120)


class BrandSettingsResponse(BaseModel):
    app_name: str
    logo_url: str | None = None
    has_logo: bool = False
    updated_at: datetime | None = None


class PasswordResetRequestPayload(BaseModel):
    email: str = Field(min_length=3, max_length=200)


class PasswordResetRequestResponse(BaseModel):
    status: str
    message: str


class PasswordResetConfirmPayload(BaseModel):
    token: str = Field(min_length=12, max_length=512)
    new_password: str = Field(min_length=10, max_length=128)


class PasswordResetConfirmResponse(BaseModel):
    status: str
    message: str


class BotProfileBase(BaseModel):
    name: str
    exchange: str = "binance"
    market_type: str = "spot"
    symbol_source_type: str = "manual"
    scanner_id: str | None = None
    symbols: list[str]
    strategy_type: str
    strategy_template_id: str | None = None
    timeframe: str = "15m"
    trend_timeframe: str = "1h"
    leverage: int = Field(default=3, ge=1, le=25)
    is_enabled: bool = True


class BotProfileCreate(BotProfileBase):
    exchange_connection_id: str | None = None
    mode: str | None = "live_ready_disabled"
    strategy_template_ids: list[str] = Field(default_factory=list)
    risk_adaptive_confirmed: bool = False


class BotProfileUpdate(BaseModel):
    name: str
    exchange: str
    market_type: str
    exchange_connection_id: str | None = None
    symbol_source_type: str = "manual"
    scanner_id: str | None = None
    symbols: list[str]
    strategy_type: str
    strategy_template_id: str | None = None
    strategy_template_ids: list[str] = Field(default_factory=list)
    timeframe: str
    trend_timeframe: str
    leverage: int = Field(default=3, ge=1, le=25)
    is_enabled: bool
    mode: str | None = "live_ready_disabled"
    risk_adaptive_confirmed: bool = False


class BotProfileResponse(BotProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    is_running: bool
    is_deleted: bool = False
    symbol_resolution_snapshot: dict = Field(default_factory=dict)
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class BotRuntimeActionResponse(BaseModel):
    bot_id: str
    status: str
    mode: str
    strategy_id: str | None = None
    risk_profile_id: str | None = None
    execution_profile_id: str | None = None
    last_heartbeat: str | None = None
    runtime_context: dict = Field(default_factory=dict)
    binding_ok: bool | None = None
    actor_id: str | None = None


class BotRuntimeStatusResponse(BaseModel):
    id: str
    name: str
    exchange: str | None = None
    market_type: str | None = None
    strategy_type: str | None = None
    strategy_template_id: str | None = None
    strategy_template_ids: list[str] = Field(default_factory=list)
    risk_adaptive_confirmed: bool = False
    symbols: list[str] = Field(default_factory=list)
    leverage: int | None = None
    is_enabled: bool = True
    is_running: bool = False
    symbol_source_type: str = "manual"
    scanner_id: str | None = None
    selected_exchange_connection_id: str | None = None
    selected_exchange_connection_label: str | None = None
    status: str
    mode: str
    strategy_id: str | None = None
    risk_profile_id: str | None = None
    execution_profile_id: str | None = None
    last_heartbeat: str | None = None
    runtime_context: dict = Field(default_factory=dict)
    symbol_source: str = "manual"
    symbol_source_summary: dict = Field(default_factory=dict)
    binding_validation: dict = Field(default_factory=dict)
    compatibility: dict = Field(default_factory=dict)
    pnl: float = 0
    today_pnl: float = 0
    active_positions: int = 0
    last_signal: dict | None = None
    last_signal_at: datetime | None = None
    strategy_name: str | None = None
    health: str = "HEALTHY"


class BotRuntimeDetailResponse(BaseModel):
    config_summary: dict = Field(default_factory=dict)
    runtime_summary: dict = Field(default_factory=dict)
    strategy_binding: dict = Field(default_factory=dict)
    risk_binding: dict = Field(default_factory=dict)
    execution_binding: dict = Field(default_factory=dict)
    binding_validation: dict = Field(default_factory=dict)
    compatibility: dict = Field(default_factory=dict)
    last_execution_summary: dict = Field(default_factory=dict)


class BotRuntimePerformanceResponse(BaseModel):
    bot_id: str
    pnl: float
    win_rate: float
    drawdown: float
    trade_count: int
    avg_rr: float


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
    reason_note: str | None = None


class RiskPolicyUpdate(RiskPolicyBase):
    reason_note: str | None = None


class RiskPolicyResponse(RiskPolicyBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    version_group_id: str
    version_num: int
    lifecycle_state: str
    is_active: bool
    activated_at: datetime | None = None
    activated_by: str | None = None
    status_reason: str | None = None
    metadata_json: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class StrategyTemplateRequestBase(BaseModel):
    name: str
    strategy_type: str
    parameters: dict
    param_schema: dict = Field(default_factory=dict)
    logic_schema: dict = Field(default_factory=dict)
    indicator_schema: dict = Field(default_factory=dict)
    execution_profile_ref: str | None = None
    risk_hint_ref: str | None = None
    allowed_venues: list[str] = Field(default_factory=list)
    allowed_modes: list[str] = Field(default_factory=list)


class StrategyTemplateCreate(StrategyTemplateRequestBase):
    template_code: str | None = None
    backtest_result_ref: str | None = None
    reason_note: str | None = None


class StrategyTemplateUpdate(StrategyTemplateRequestBase):
    backtest_result_ref: str | None = None
    reason_note: str | None = None


class StrategyTemplateResponse(StrategyTemplateRequestBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    template_code: str
    version_group_id: str
    version_num: int
    lifecycle_state: str
    parent_template_id: str | None = None
    rollback_from_template_id: str | None = None
    backtest_result_ref: str | None = None
    last_validated_at: datetime | None = None
    is_active: bool
    created_by: str
    created_at: datetime
    updated_at: datetime


class StrategyTemplateReasonRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=400)


class StrategyTemplateCloneVersionRequest(BaseModel):
    name: str | None = None
    reason: str = Field(min_length=3, max_length=400)


class StrategyTemplatePreviewImpactRequest(BaseModel):
    volatility_regime: str = "normal"
    risk_regime: str = "balanced"
    market_regime: str = "neutral"


class StrategyTemplateResolvedConfigResponse(BaseModel):
    template_id: str
    template_code: str
    version_group_id: str
    version_num: int
    lifecycle_state: str
    effective_runtime_config: dict = Field(default_factory=dict)
    validation_result: dict = Field(default_factory=dict)


class StrategyTemplateDetailResponse(BaseModel):
    template: StrategyTemplateResponse
    current_active_version: StrategyTemplateResponse | None = None
    version_history: list[StrategyTemplateResponse] = Field(default_factory=list)
    param_editor_summary: dict = Field(default_factory=dict)
    scanner_bindings: dict = Field(default_factory=dict)
    bot_bindings: list[dict] = Field(default_factory=list)
    backtest_summary: dict = Field(default_factory=dict)
    execution_compatibility: dict = Field(default_factory=dict)
    related_trades: list[dict] = Field(default_factory=list)
    audit_timeline: list[dict] = Field(default_factory=list)
    promotion_eligibility: dict = Field(default_factory=dict)
    promotion_lifecycle: list[dict] = Field(default_factory=list)
    outcome_analytics: dict = Field(default_factory=dict)
    recent_outcomes: list[dict] = Field(default_factory=list)
    global_trace_spine: list[dict] = Field(default_factory=list)
    learning_feedback_loop: dict = Field(default_factory=dict)


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


class AuditTimelineItemResponse(BaseModel):
    id: str
    actor_user_id: str | None
    actor_role: str
    action: str
    entity_type: str
    entity_id: str
    severity: str
    details: dict
    request_id: str | None = None
    session_id: str | None = None
    route: str | None = None
    method: str | None = None
    created_at: datetime


class AuditTimelineResponse(BaseModel):
    total: int
    items: list[AuditTimelineItemResponse]
    deprecated: bool = False
    primary_endpoint: str | None = None


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
    source_type: str = "production"
    environment: str = "production"
    correlation_id: str = ""
    triggered_by: str = "system"
    parent_event_id: str | None = None
    strategy_id: str | None = None
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
    failure_class: str = "downstream_error"
    dead_letter_reason: str | None = None
    last_action_by: str | None = None
    correlation_id: str | None = None
    retry_reason: str | None = None
    error_details: dict = Field(default_factory=dict)
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
    delivery_provider: str | None = None
    last_attempt_at: datetime | None = None
    next_retry_at: datetime | None = None
    attempt_count: int | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None


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
    from_state: str | None = None
    to_state: str | None = None
    sequence: int
    latency_ms: float | None = None
    correlation_id: str | None = None
    source_type: str = "production"
    environment: str = "production"
    is_manual: bool = False
    details: dict
    occurred_at: datetime


class ExecutionStateControlQueryResponse(BaseModel):
    rows: list[ExecutionStateTransitionResponse]
    summary_counts: dict[str, int] = Field(default_factory=dict)
    state_counters: dict[str, int] = Field(default_factory=dict)


class ExecutionStateDetailResponse(BaseModel):
    execution_event: ExecutionEventResponse
    current_state: str
    previous_state: str | None = None
    full_state_path: list[str] = Field(default_factory=list)
    transition_count: int = 0
    dwell_time_seconds: float = 0
    transitions: list[ExecutionStateTransitionResponse] = Field(default_factory=list)


class ExecutionSimulationBatchRequest(BaseModel):
    scenarios: list[dict] = Field(default_factory=list)


class ExecutionSimulationBatchResponse(BaseModel):
    status: str
    total: int
    created: int
    records: list[dict] = Field(default_factory=list)


class ExecutionManualActionRequest(BaseModel):
    action_type: str
    reason_note: str
    correlation_id: str
    confirmation_phrase: str | None = None
    payload: dict = Field(default_factory=dict)


class IdempotencyCollisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    collision_id: str
    intent_id: str | None = None
    idempotency_key: str
    original_request: dict = Field(default_factory=dict)
    duplicate_request: dict = Field(default_factory=dict)
    actor: str
    correlation_id: str | None = None
    status: str
    resolution_action: str | None = None
    resolution_note: str | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime


class IdempotencyCollisionResolveRequest(BaseModel):
    action: str
    reason_note: str
    correlation_id: str


class ExecutionTraceTimelineItemResponse(BaseModel):
    stage: str
    actor: str
    payload: dict = Field(default_factory=dict)
    created_at: datetime


class ExecutionCorrelationTraceResponse(BaseModel):
    correlation_id: str
    chain: list[ExecutionTraceTimelineItemResponse] = Field(default_factory=list)
    intents: list[dict] = Field(default_factory=list)
    events: list[dict] = Field(default_factory=list)
    failures: list[FailedEventResponse] = Field(default_factory=list)


class ExecutionAnalyticsSnapshotSummaryResponse(BaseModel):
    snapshot_at: datetime
    filters: dict = Field(default_factory=dict)
    totals: dict = Field(default_factory=dict)
    latency_per_state: dict = Field(default_factory=dict)
    timeout_metrics: dict = Field(default_factory=dict)
    retry_metrics: dict = Field(default_factory=dict)
    failure_metrics: dict = Field(default_factory=dict)
    dead_letter_trend: list[dict] = Field(default_factory=list)


class IncidentSnapshotExportRequest(BaseModel):
    correlation_id: str | None = None
    execution_event_id: str | None = None
    time_from: str | None = None
    time_to: str | None = None
    compare_correlation_id: str | None = None
    compare_execution_event_id: str | None = None
    compare_time_from: str | None = None
    compare_time_to: str | None = None
    compare_enabled: bool = False
    search: str | None = None
    state: str | None = None
    status: str | None = None
    source_type: str | None = None
    symbol: str | None = None
    strategy: str | None = None
    order_id: str | None = None


class IncidentSnapshotExportResponse(BaseModel):
    status: str
    filename: str
    generated_at: datetime


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
    trading_enabled: bool = False
    max_total_exposure: float = Field(default=150, ge=0)
    max_active_positions: int = Field(default=3, ge=0)
    canary_enabled: bool = False
    canary_symbols: list[str] = Field(default_factory=list)
    canary_max_capital_usdt: float = Field(default=50, ge=0)
    canary_max_positions: int = Field(default=1, ge=0)
    disable_futures: bool
    ip_whitelist_ready: bool
    trading_permission_ready: bool


class LiveActivationConfigUpdate(LiveActivationConfigBase):
    pass


class LiveActivationConfigResponse(LiveActivationConfigBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    updated_at: datetime


class AdminKillSwitchRequest(BaseModel):
    trading_enabled: bool
    reason: str | None = None
    requested_by: str | None = None
    effective_at: datetime | None = None
    max_total_exposure: float | None = Field(default=None, ge=0)
    max_active_positions: int | None = Field(default=None, ge=0)


class AdminKillSwitchResponse(BaseModel):
    trading_enabled: bool
    max_total_exposure: float
    max_active_positions: int
    current_total_exposure: float
    current_active_positions: int
    open_positions_count: int
    pending_user_intents_count: int
    pending_runtime_intents_count: int
    reason_code: str
    idempotent: bool
    updated_at: datetime


class AdminCanaryStatusResponse(BaseModel):
    enabled: bool
    active_symbols: list[str]
    capital_used: float
    position_count: int
    violations: int
    error_rate: float
    latency_ms_p95: float
    order_fail_rate: float
    reject_rate: float
    pnl_drift: float
    alert_ids: list[str] = Field(default_factory=list)


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


class LiveConnectivityResponse(BaseModel):
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
    assignment_autofixed: bool = False


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
    symbol: str
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
    requested_leverage: int | None = None
    recommended_leverage: int | None = None
    applied_leverage: int | None = None
    leverage_policy_mode: str | None = None
    leverage_clamp_reasons: list[str] = Field(default_factory=list)


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
    is_live_environment: bool
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
    symbol: str
    timeframe: str = "15m"
    exchange: str = "binance"
    market_type: str = "futures"
    environment: str = "live"
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
    owner_user_id: str | None = None
    owner_name: str | None = None
    category: str = "general"
    tags: list[str] = Field(default_factory=list)


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
    owner_user_id: str | None = None
    owner_name: str
    category: str
    tags: list[str]
    created_by: str
    status: str
    active_version_id: str | None
    archived_at: datetime | None = None
    last_reviewed_at: datetime | None = None
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
    priority: int = Field(default=100, ge=1, le=1000)
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
    policy_version: int = 1
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
    trading_enabled: bool = True
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


class RiskOrchestratorPolicySimulationRequest(BaseModel):
    candidate_policy: RiskOrchestratorPolicyUpdate


class RiskOrchestratorPolicySimulationResponse(BaseModel):
    simulation_id: str
    result_status: str
    baseline_policy: dict
    candidate_policy: dict
    diff_summary: dict
    impacted_strategies: list[str]
    impacted_symbols: list[str]
    metrics: dict
    risk_score: float = 0
    classification: str = "SAFE"
    approval_flow: dict = Field(default_factory=dict)
    created_at: datetime


class RiskOrchestratorPolicyApplyRequest(BaseModel):
    simulation_id: str
    reason_note: str = Field(min_length=3, max_length=1000)
    double_confirmed: bool = False
    apply_with_override: bool = False
    approval_note: str | None = Field(default=None, max_length=1000)
    request_key: str | None = Field(default=None, max_length=160)
    expected_policy_version: int | None = None


class RiskOrchestratorPolicyApplyResponse(BaseModel):
    status: str
    flow_type: str
    simulation_id: str
    risk_score: float
    classification: str
    rule_path: str
    policy: RiskOrchestratorPolicyResponse | None = None
    approval_request_id: str | None = None
    decision_trace_id: str | None = None
    message: str


class RiskOrchestratorApprovalRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    approval_id: str
    request_key: str
    flow_type: str
    simulation_id: str
    classification: str
    priority: str
    risk_score: float
    state: str
    requested_by: str
    requested_role: str
    assigned_to: str | None = None
    assigned_at: datetime | None = None
    auto_assigned: bool = False
    reason_note: str
    override_used: bool
    second_approver_id: str | None = None
    second_approver_note: str | None = None
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    warning_escalated_at: datetime | None = None
    critical_escalated_at: datetime | None = None
    expired_at: datetime | None = None
    escalation_count: int = 0
    force_applied: bool = False
    expires_at: datetime
    context_payload: dict
    final_decision_trace_id: str | None = None
    last_activity_at: datetime
    created_at: datetime
    updated_at: datetime


class RiskOrchestratorApprovalQueueItemResponse(RiskOrchestratorApprovalRequestResponse):
    sla_remaining_seconds: int
    sla_stage: str


class RiskOrchestratorApprovalAssignRequest(BaseModel):
    assignee_id: str | None = None
    auto_assign: bool = False


class RiskOrchestratorForceApplyRequest(BaseModel):
    reason_note: str = Field(min_length=3, max_length=1000)


class RiskOrchestratorDecisionIntelligenceResponse(BaseModel):
    trace: "RiskOrchestratorDecisionTraceResponse"
    before_after_diff: dict
    risk_breakdown: dict
    why_decision: dict
    similar_patterns: list[dict]


class RiskOrchestratorRejectInsightItem(BaseModel):
    rule: str
    count: int
    window_minutes: int
    suggestion: str
    message: str


class RiskOrchestratorRejectInsightsResponse(BaseModel):
    window_minutes: int
    insights: list[RiskOrchestratorRejectInsightItem]


class RiskOrchestratorOperationalDashboardResponse(BaseModel):
    active_pending_approvals: int
    critical_queue: int
    unassigned: int
    my_approvals: int
    reject_spike_last_hour: int
    override_usage: dict
    risk_score_distribution: dict
    approval_throughput_last_hour: dict
    predictive_risk_signal: dict = Field(default_factory=dict)
    governance: dict = Field(default_factory=dict)
    cache_health: dict = Field(default_factory=dict)


class RiskOrchestratorApprovalDecisionRequest(BaseModel):
    decision_note: str = Field(min_length=3, max_length=1000)


class RiskOrchestratorDecisionTraceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trace_id: str
    flow_type: str
    simulation_id: str
    classification: str
    risk_score: float
    rule_path: str
    decision_state: str
    requested_by: str
    approver_id: str | None = None
    request_key: str
    reason_note: str
    approval_note: str | None = None
    payload: dict
    created_at: datetime


class RiskOrchestratorPolicyVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version_id: str
    version_no: int
    policy_payload: dict
    diff_payload: dict
    changed_by: str
    changed_role: str
    reason_note: str
    simulation_id: str | None = None
    approval_request_id: str | None = None
    reverted_from_version_id: str | None = None
    created_at: datetime


class RiskOrchestratorPolicyChangeRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_id: str
    status: str
    requested_by: str
    requested_role: str
    approved_by: str | None = None
    approval_note: str | None = None
    reason_note: str
    payload: dict
    simulation_id: str | None = None
    critical_fields: list[str] = Field(default_factory=list)
    double_confirmed: bool
    created_at: datetime
    updated_at: datetime
    decided_at: datetime | None = None


class RiskOrchestratorPolicyHistoryResponse(BaseModel):
    versions: list[RiskOrchestratorPolicyVersionResponse]
    change_requests: list[RiskOrchestratorPolicyChangeRequestResponse]


class RiskOrchestratorPolicyRevertRequest(BaseModel):
    reason_note: str = Field(min_length=3, max_length=1000)
    double_confirmed: bool = True
    apply_with_override: bool = False
    request_key: str | None = Field(default=None, max_length=160)
    simulation_id: str | None = None
    expected_policy_version: int | None = None


class RiskOrchestratorRevertSimulationResponse(BaseModel):
    version_id: str
    simulation: RiskOrchestratorPolicySimulationResponse


class RiskOrchestratorControlActionRequest(BaseModel):
    action_type: str
    reason_note: str = Field(min_length=3, max_length=1000)
    context: dict = Field(default_factory=dict)


class RiskOrchestratorControlActionResponse(BaseModel):
    intervention_id: str
    action_type: str
    status: str
    reason_note: str
    effective_state: dict
    created_at: datetime


class RiskOrchestratorManualOverrideCreateRequest(BaseModel):
    override_type: str
    target_key: str
    reason_note: str = Field(min_length=3, max_length=1000)
    max_notional_pct: float | None = None
    max_open_count: int | None = None
    block_new_adds: bool = False
    expires_in_minutes: int | None = Field(default=None, ge=1, le=10080)


class RiskOrchestratorManualOverrideDeactivateRequest(BaseModel):
    reason_note: str = Field(min_length=3, max_length=1000)


class RiskOrchestratorManualOverrideResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    override_id: str
    override_type: str
    target_key: str
    override_value: dict
    reason_note: str
    actor_id: str
    actor_role: str
    status: str
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    deactivated_at: datetime | None = None


class RiskOrchestratorOpenPositionResponse(BaseModel):
    position_id: str
    user_id: str
    strategy_id: str | None = None
    symbol: str
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    leverage: int
    cluster_id: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class RiskOrchestratorInterventionRequest(BaseModel):
    position_id: str | None = None
    action_type: str
    reason_note: str = Field(min_length=3, max_length=1000)
    target_symbol: str | None = None
    target_key: str | None = None
    payload: dict = Field(default_factory=dict)


class RiskOrchestratorInterventionResponse(BaseModel):
    intervention_id: str
    action_type: str
    status: str
    reason_note: str
    intent_id: str | None = None
    result_summary: dict
    created_at: datetime


class RiskOrchestratorAutoTriggerLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trigger_id: str
    breach_type: str
    target_key: str
    severity: str
    suggested_action: str
    payload: dict
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
    created_at: datetime


class RiskOrchestratorRejectDetailResponse(BaseModel):
    id: str
    created_at: datetime
    strategy_id: str | None = None
    strategy_version_id: str | None = None
    symbol: str | None = None
    reason_codes: list[str]
    root_cause: str | None = None
    details: dict


class RiskOrchestratorAuditTimelineItemResponse(BaseModel):
    event_id: str
    event_type: str
    actor_id: str | None = None
    actor_role: str | None = None
    status: str
    reason_note: str
    payload: dict
    created_at: datetime


class RiskOrchestratorAlertResponse(BaseModel):
    id: str
    alert_type: str
    severity: str
    status: str
    message: str
    details: dict
    created_at: datetime


class UserPortfolioOverviewResponse(BaseModel):
    current_capital: float
    available_balance: float
    open_position_balance: float
    closed_pnl: float
    compounding_enabled: bool
    next_base_capital: float


class UserExchangeConnectRequest(BaseModel):
    exchange: str = "binance"
    mode: str = "live"
    api_key: str
    api_secret: str


class UserExchangeConnectResponse(BaseModel):
    exchange: str
    mode: str
    has_api_key: bool
    has_api_secret: bool
    masked_api_key: str
    credential_fingerprint: str
    updated_at: datetime | None


class UserExchangeConnectionUpsertRequest(BaseModel):
    account_label: str
    exchange: str = "binance"
    market_type: str = "spot"
    environment: str = "live"
    is_default: bool = False
    api_key: str | None = None
    api_secret: str | None = None
    permission_snapshot: list[str] = Field(default_factory=list)
    readiness_snapshot: dict = Field(default_factory=dict)


class UserExchangeConnectionPatchRequest(BaseModel):
    account_label: str | None = None
    exchange: str | None = None
    market_type: str | None = None
    environment: str | None = None
    is_default: bool | None = None
    api_key: str | None = None
    api_secret: str | None = None
    permission_snapshot: list[str] | None = None
    readiness_snapshot: dict | None = None


class UserExchangeConnectionResponse(BaseModel):
    id: str
    user_id: str
    account_label: str
    exchange: str
    market_type: str
    environment: str
    is_default: bool
    readiness_snapshot: dict
    permission_snapshot: list[str]
    connection_health: str = "unknown"
    connection_health_reason: str | None = None
    can_trade_effective: bool = False
    last_validated_at: datetime | None = None
    is_reconnecting: bool = False
    next_retry_in_seconds: int | None = None
    retry_backoff_seconds: int = 0
    action_required: bool = False
    action_required_message: str | None = None
    validation_success_24h: int = 0
    validation_fail_24h: int = 0
    validation_success_rate_24h: float | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    health_bucket_metrics: dict = Field(default_factory=dict)
    current_jitter_p95_p50_ms: float | None = None
    current_jitter_stddev_ms: float | None = None
    health_last_transition_at: datetime | None = None
    health_history: list[dict] = Field(default_factory=list)
    liveness_latency_history: list[dict] = Field(default_factory=list)
    has_api_key: bool
    has_api_secret: bool
    masked_api_key: str
    credential_fingerprint: str
    global_activation_flag_key: str | None = None
    global_activation_active: bool = False
    effective_source: str = "unresolved"
    routing_preview: dict = Field(default_factory=dict)
    environment_valid: bool = False
    created_at: datetime
    updated_at: datetime


class UserPortfolioMapRequest(BaseModel):
    market_type: str = "spot"
    leverage: int = Field(default=1, ge=1, le=20)
    margin_mode: str = "cross"
    position_side: str = "BOTH"


class UserPortfolioMapResponse(BaseModel):
    market_type: str
    margin_mode: str
    position_side: str
    leverage: int | None
    current_capital: float
    available_balance: float
    open_notional: float
    open_unrealized_pnl: float
    closed_pnl: float
    allocation_pct: float
    trade_risk_pct: float
    daily_loss_limit_pct: float
    allocation_capital: float
    max_trade_loss: float
    daily_loss_limit_amount: float
    recommended_order_notional: float
    compounding_enabled: bool
    next_trade_base_capital: float
    open_positions_count: int
    warnings: list[str]


class UserPortfolioSnapshotResponse(BaseModel):
    total_wallet_balance: float = 0
    spot_wallet_balance: float = 0
    futures_wallet_balance: float = 0
    current_capital: float
    available_balance: float
    execution_mode: str = "live"
    open_notional: float
    open_unrealized_pnl: float
    closed_pnl: float
    open_positions_count: int
    closed_positions_count: int
    allocation_capital: float
    next_trade_base_capital: float
    compounding_enabled: bool


class UserPerformanceSnapshotResponse(BaseModel):
    lookback_days: int
    total_closed_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    realized_pnl_total: float
    unrealized_pnl_total: float
    roi_pct: float
    profit_factor: float
    avg_execution_quality: float
    execution_count: int


class UserTradeResponse(BaseModel):
    source: str
    trade_id: str
    symbol: str
    market_type: str | None = None
    side: str
    status: str
    quantity: float
    entry_price: float | None
    exit_price: float | None
    realized_pnl: float | None
    unrealized_pnl: float | None
    opened_at: datetime | None
    closed_at: datetime | None
    strategy_weight: float | None = None
    allocation_source: str | None = None
    meta_engine_decision: str | None = None
    trace_available: bool = False
    has_explainability: bool = False
    reconciliation_status: str | None = None
    strategy: str | None = None
    strategy_template_id: str | None = None
    strategy_version_id: str | None = None
    scan_run_id: str | None = None
    signal_id: str | None = None
    decision_card_id: str | None = None
    intent_id: str | None = None
    execution_trace_id: str | None = None


class UserSignalModeResponse(BaseModel):
    mode: str
    updated_at: datetime | None


class UserSignalModeUpdateRequest(BaseModel):
    mode: str = "ASSISTED"


class UserScannerRunRequest(BaseModel):
    mode: str | None = None
    max_results: int = Field(default=20, ge=5, le=100)
    symbol_source: str = "crypto"
    market_type: str = "all"
    symbol_selection_mode: str = "all_market_symbols"
    selected_symbols: list[str] = Field(default_factory=list)


class UserScannerRunResponse(BaseModel):
    run_id: str
    mode: str
    market_type: str
    result_count: int
    actionable_count: int
    queued_count: int
    pending_total: int
    generated_at: datetime
    selected_symbols: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    scanner_perf: dict = Field(default_factory=dict)


class UserScannerAutomationConfigUpdateRequest(BaseModel):
    auto_enabled: bool = True
    interval_seconds: int = Field(default=60, ge=30, le=120)
    max_results: int = Field(default=25, ge=5, le=100)
    symbol_source: str = "crypto"
    symbol_selection_mode: str = "all_market_symbols"
    selected_symbols: list[str] = Field(default_factory=list)


class UserScannerAutomationConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    auto_enabled: bool
    interval_seconds: int
    max_results: int
    symbol_source: str
    symbol_selection_mode: str
    selected_symbols: list[str] = Field(default_factory=list)
    last_run_id: str | None = None
    last_run_status: str
    last_actionable_count: int = 0
    last_run_error: str | None = None
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class UserScannerAutomationProfileCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    auto_enabled: bool = True
    is_active: bool = False
    interval_seconds: int = Field(default=60, ge=30, le=120)
    max_results: int = Field(default=25, ge=5, le=100)
    symbol_source: str = "crypto"
    symbol_selection_mode: str = "all_market_symbols"
    selected_symbols: list[str] = Field(default_factory=list)


class UserScannerAutomationProfileUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    auto_enabled: bool = True
    is_active: bool = False
    interval_seconds: int = Field(default=60, ge=30, le=120)
    max_results: int = Field(default=25, ge=5, le=100)
    symbol_source: str = "crypto"
    symbol_selection_mode: str = "all_market_symbols"
    selected_symbols: list[str] = Field(default_factory=list)


class UserScannerAutomationProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    name: str
    auto_enabled: bool
    is_active: bool
    interval_seconds: int
    max_results: int
    symbol_source: str
    symbol_selection_mode: str
    selected_symbols: list[str] = Field(default_factory=list)
    last_run_id: str | None = None
    last_run_status: str
    last_actionable_count: int = 0
    last_run_error: str | None = None
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class UserScannerSymbolSelectionUpdateRequest(BaseModel):
    scanner_id: str = Field(default="default", min_length=1, max_length=60)
    symbol_source: str = "crypto"
    symbol_selection_mode: str = "all_market_symbols"
    selected_symbols: list[str] = Field(default_factory=list)


class UserScannerSymbolSelectionResponse(BaseModel):
    id: str
    user_id: str
    scanner_id: str
    symbol_source: str
    symbol_selection_mode: str
    selected_symbols: list[str] = Field(default_factory=list)
    saved_at: datetime
    created_at: datetime
    updated_at: datetime


class UserScannerResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    user_id: str
    symbol: str
    quote_asset: str
    strategy_code: str
    signal: str
    confidence: float
    score: float | None = None
    signal_score: float
    reason_codes: list[str]
    explain: list[str] = Field(default_factory=list, min_length=1)
    payload: dict
    generated_at: datetime


class UserScannerAnomalyTrendPoint(BaseModel):
    label: str = Field(default="1m", min_length=1, max_length=16)
    total: int = Field(default=0, ge=0, le=2000)
    success: int = Field(default=0, ge=0, le=2000)
    fail: int = Field(default=0, ge=0, le=2000)
    success_ratio: float = Field(default=1, ge=0, le=1)


class UserScannerAnomalyAuditRequest(BaseModel):
    source: str = Field(default="scanner_ui", min_length=3, max_length=60)
    fail_ratio: float = Field(default=0, ge=0, le=1)
    total_requests: int = Field(default=0, ge=0, le=2000)
    failed_requests: int = Field(default=0, ge=0, le=2000)
    success_requests: int = Field(default=0, ge=0, le=2000)
    trend_window_minutes: int = Field(default=5, ge=1, le=60)
    trend_points: list[UserScannerAnomalyTrendPoint] = Field(default_factory=list, max_length=10)


class UserScannerAnomalyAuditResponse(BaseModel):
    status: str
    audit_log_id: str | None = None
    logged_at: datetime | None = None
    suppressed_count: int = 0
    suppress_reason: str | None = None
    payload_hash: str | None = None
    alert_severity: str | None = None
    mute_until: datetime | None = None


class AdminAnomalyAlertPolicyResponse(BaseModel):
    warning_threshold: float = Field(default=0.1, ge=0.01, le=0.99)
    critical_threshold: float = Field(default=0.2, ge=0.01, le=0.99)
    smart_mute_window_seconds: int = Field(default=300, ge=30, le=3600)
    smart_mute_trigger_count: int = Field(default=3, ge=2, le=20)
    smart_mute_duration_seconds: int = Field(default=900, ge=60, le=86400)
    notifications_enabled: bool = True
    notify_min_severity: str = Field(default="warning", pattern="^(warning|critical)$")
    webhook_urls: list[str] = Field(default_factory=list, max_length=5)
    updated_at: datetime


class AdminAnomalyAlertPolicyUpdateRequest(BaseModel):
    warning_threshold: float = Field(default=0.1, ge=0.01, le=0.99)
    critical_threshold: float = Field(default=0.2, ge=0.01, le=0.99)
    smart_mute_window_seconds: int = Field(default=300, ge=30, le=3600)
    smart_mute_trigger_count: int = Field(default=3, ge=2, le=20)
    smart_mute_duration_seconds: int = Field(default=900, ge=60, le=86400)
    notifications_enabled: bool = True
    notify_min_severity: str = Field(default="warning", pattern="^(warning|critical)$")
    webhook_urls: list[str] = Field(default_factory=list, max_length=5)


class AdminAnomalyMutePatternRequest(BaseModel):
    payload_hash: str = Field(min_length=16, max_length=128)
    duration_seconds: int = Field(default=900, ge=60, le=86400)
    reason: str = Field(default="manual_mute", min_length=3, max_length=120)


class AdminAnomalyMutePatternResponse(BaseModel):
    status: str
    payload_hash: str
    mute_until: datetime
    duration_seconds: int


class UserSignalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    signal_id: str
    user_id: str
    symbol: str
    market_type: str | None = None
    quote_asset: str | None = None
    strategy_code: str
    confidence: float
    mode: str
    status: str
    order_position_id: str | None
    created_at: datetime
    decided_at: datetime | None
    decision_note: str
    strategy_weight: float | None = None
    allocation_source: str | None = None
    meta_engine_decision: str | None = None
    previous_state: str | None = None
    current_state: str | None = None
    blocked_reason_code: str | None = None
    blocked_reason_message: str | None = None
    blocked_solution_hint: str | None = None
    requires_manual_approval: bool | None = None
    execution_eligible: bool | None = None
    bot_profile_id: str | None = None
    risk_policy_id: str | None = None
    exchange_connection_id: str | None = None
    created_order_intent_id: str | None = None
    runtime_owner: str | None = None
    last_eligibility_check_at: datetime | None = None
    execution_mode_label: str | None = None


class UserSignalDecisionRequest(BaseModel):
    note: str = ""


class UserSignalDecisionResponse(BaseModel):
    id: str
    status: str
    order_position_id: str | None
    decided_at: datetime | None
    decision_note: str
    current_state: str | None = None
    blocked_reason_code: str | None = None
    created_order_intent_id: str | None = None


class UserSignalDiagnoseResponse(BaseModel):
    id: str
    status: str
    current_state: str
    blocked_reason_code: str
    blocked_reason_message: str
    blocked_solution_hint: str
    requires_manual_approval: bool
    execution_eligible: bool
    bot_profile_id: str | None = None
    risk_policy_id: str | None = None
    exchange_connection_id: str | None = None
    created_order_intent_id: str | None = None
    runtime_owner: str
    last_eligibility_check_at: datetime | None = None
    actions_applied: list[str] = Field(default_factory=list)


class UserSignalsBulkFixResponse(BaseModel):
    scanned_count: int
    blocked_before: int
    fixed_count: int
    remaining_blocked: int
    updated_signal_ids: list[str] = Field(default_factory=list)
    actions_summary: dict = Field(default_factory=dict)


class DecisionReasonDetailResponse(BaseModel):
    code: str
    title: str
    description: str


class DecisionTraceItemResponse(BaseModel):
    trace_id: str
    trace_scope: str
    trace_type: str
    entity_id: str
    strategy_code: str | None
    decision_status: str
    portfolio_risk_score: float | None = None
    strategy_allocation_reason: str | None = None
    cluster_risk_flag: str | None = None
    meta_engine_decision: str | None = None
    position_action_reason: str | None = None
    risk_adjustment_reason: str | None = None
    strategy_override_reason: str | None = None
    hedge_recommendation: str | None = None
    risk_reduction_score: float | None = None
    correlation_basis: str | None = None
    reason_codes: list[str]
    reason_details: list[DecisionReasonDetailResponse]
    feature_snapshot: dict
    context_payload: dict
    created_at: datetime
    expires_at: datetime


class DecisionTraceTimelineResponse(BaseModel):
    entity_scope: str
    entity_id: str
    trace_count: int
    latest_trace: DecisionTraceItemResponse | None
    timeline: list[DecisionTraceItemResponse]


class StrategyExplainReasonStatResponse(BaseModel):
    code: str
    title: str
    description: str
    count: int


class StrategyExplainResponse(BaseModel):
    strategy_code: str
    lookback_days: int
    trace_count: int
    decision_distribution: dict[str, int]
    top_reason_codes: list[StrategyExplainReasonStatResponse]
    latest_examples: list[DecisionTraceItemResponse]


class TraceCoverageScopeResponse(BaseModel):
    scope: str
    total_events: int
    traced_events: int
    coverage_pct: float


class TraceCoverageResponse(BaseModel):
    window_days: int
    generated_at: datetime
    overall_total_events: int
    overall_traced_events: int
    overall_coverage_pct: float
    scopes: list[TraceCoverageScopeResponse]


class UserDashboardResponse(BaseModel):
    bot_count: int
    running_bot_count: int
    risk_policy_count: int
    current_capital: float
    available_balance: float
    open_positions_count: int
    pending_signals_count: int
    heartbeat: str | None


class UserScannerOverviewResponse(BaseModel):
    mode: str
    total_results: int
    pending_signals: int
    latest_run_id: str | None
    latest_generated_at: datetime | None


class SymbolUniverseRowResponse(BaseModel):
    symbol: str
    source: str
    exchange: str
    market_type: str
    quote_asset: str | None = None
    volume_24h: float | None = None
    is_tradable: bool = True
    company_name: str | None = None
    sector: str | None = None


class SymbolUniverseResponse(BaseModel):
    source: str
    mode: str
    exchange: str
    market_type: str
    rows: list[SymbolUniverseRowResponse] = Field(default_factory=list)
    selected_symbols: list[str] = Field(default_factory=list)
    skipped_symbols: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    has_provider_key: bool = True


class SymbolWatchlistCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    source: str = "crypto"
    exchange: str = "binance"
    market_type: str = "spot"
    symbols: list[str] = Field(default_factory=list)


class SymbolWatchlistUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    symbols: list[str] = Field(default_factory=list)


class SymbolWatchlistResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    name: str
    source: str
    exchange: str
    market_type: str
    symbols: list[str]
    created_at: datetime
    updated_at: datetime


class SymbolProviderConfigResponse(BaseModel):
    has_alpha_vantage_key: bool
    key_hint: str | None = None


class SymbolProviderConfigUpdateRequest(BaseModel):
    api_key: str = Field(min_length=6, max_length=200)


class IndicatorScreenerRunRequest(BaseModel):
    exchange: str = "binance"
    market_type: str = "spot"
    timeframe: str = "15m"
    query_expression: str = ""
    symbol_universe: list[str] | str | None = "all"
    limit: int = Field(default=50, ge=1, le=300)
    filter_payload: dict = Field(default_factory=dict)


class IndicatorScreenerRowResponse(BaseModel):
    index: int
    exchange: str
    market_type: str
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    scan_price: float
    volume: float
    rsi14: float
    rsi7: float
    ema20: float
    ema50: float
    sma20: float
    sma50: float
    fibo_161_8: float
    fibo_127_2: float
    fibo_100: float
    fibo_78_6: float
    matched_rules: list[str]
    matched_fields: list[str]
    condition_metric_values: dict[str, float] = Field(default_factory=dict)
    updated_at: str | None
    evaluated_at: str | None
    data_source: str | None
    cache_hit: bool
    fresh_fetch: bool
    last_candle_time: str | None
    volume_24h: float | None = None
    spread_pct_24h: float | None = None
    quote_asset: str | None = None
    is_tradable: bool = True
    margin_eligible: bool = False
    futures_eligible: bool = False
    leveraged_token: bool = False
    stablecoin_pair: bool = False
    signal_score: float | None = None
    confidence: float | None = None
    rr_estimate: float | None = None
    executable: bool = True
    executable_reasons: list[str] = Field(default_factory=list)
    stale_data: bool = False


class IndicatorScreenerRunResponse(BaseModel):
    matched_symbols: list[str]
    evaluated_count: int
    match_count: int
    query_valid: bool
    query_error: str | None
    calculation_timestamp: str
    rows: list[IndicatorScreenerRowResponse]
    evaluated_symbols: list[str]
    skipped_symbols: list[str]
    limit: int
    universe_mode: str | None = None
    universe_count: int | None = None
    exchange: str | None = None
    market_type: str | None = None
    timeframe: str | None = None
    applied_filters: dict = Field(default_factory=dict)
    active_filter_chips: list[dict] = Field(default_factory=list)
    result_state: str = "success"
    filter_error: str | None = None
    warnings: list[str] = Field(default_factory=list)


class IndicatorScreenerPresetResponse(BaseModel):
    preset_key: str
    title: str
    query_expression: str


class UserIndicatorSavedQueryCreateRequest(BaseModel):
    name: str = ""
    exchange: str = "binance"
    market_type: str = "spot"
    timeframe: str = "15m"
    query_expression: str
    symbol_universe: list[str] = Field(default_factory=list)
    filter_snapshot: dict = Field(default_factory=dict)
    schema_version: int = 1
    result_limit: int = Field(default=50, ge=1, le=300)


class UserIndicatorSavedQueryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    name: str
    exchange: str
    market_type: str
    timeframe: str
    query_expression: str
    symbol_universe: list[str]
    filter_snapshot: dict
    schema_version: int
    result_limit: int
    created_at: datetime
    updated_at: datetime


class UserIndicatorWatchlistCreateRequest(BaseModel):
    exchange: str = "binance"
    market_type: str = "spot"
    symbol: str
    note: str = ""
    context_snapshot: dict = Field(default_factory=dict)


class UserIndicatorWatchlistResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    exchange: str
    market_type: str
    symbol: str
    note: str
    context_snapshot: dict
    created_at: datetime


class UserWeeklyReportStubResponse(BaseModel):
    status: str
    report_id: str | None
    week: str | None
    pnl: float | None
    win_rate: float | None
    download_links: dict[str, str]
    detail: str


class UserWeeklyReportResponse(BaseModel):
    report_id: str
    week: str
    summary: dict
    pnl: float
    win_rate: float
    max_drawdown: float
    strategy_contribution: dict
    download_links: dict[str, str]
    status: str


class ExecutionIntentPreviewRequest(BaseModel):
    source_type: str = "manual"
    source_ref_id: str | None = None
    intent_type: str = "OPEN_POSITION"
    position_id: str | None = None
    market_type: str
    symbol: str
    side: str
    order_type: str
    position_size_mode: str = "fixed_notional"
    position_size_value: float = Field(default=10, gt=0)
    margin_mode: str | None = None
    leverage: int | None = None
    take_profit_mode: str = "none"
    take_profit_value: float = 0
    stop_loss_mode: str = "none"
    stop_loss_value: float = 0
    execution_mode: str = "manual"
    strategy_binding: str | None = None
    holding_profile: str = "intraday"
    size: float | None = Field(default=None, gt=0)
    reduce_only: bool = False
    price: float | None = None
    stop_price: float | None = None
    take_profit_price: float | None = None
    exchange_connection_id: str | None = None
    exchange: str | None = None
    environment: str | None = None
    account_label: str | None = None
    signal: str | None = None
    score: float | None = None
    strategy: str | None = None
    confidence: float | None = None
    timestamp: str | None = None
    scanner_signal_snapshot: dict = Field(default_factory=dict)


class ExecutionIntentPreviewResponse(BaseModel):
    intent_id: str
    intent_token: str
    preview_hash: str
    intent_type: str = "OPEN_POSITION"
    position_id: str | None = None
    validation_status: str
    reject_reason_codes: list[str]
    normalized_order_payload: dict
    risk_flags: list[str]
    queue_mode: str
    approval_required: bool
    intent_status: str
    meta_strategy_summary: dict = Field(default_factory=dict)
    portfolio_risk_impact: dict = Field(default_factory=dict)
    gate_decision: str = "ALLOW"
    meta_engine_decision: str = "ALLOW"
    size: float | None = None
    reduce_only: bool = False
    price: float | None = None
    stop_price: float | None = None
    take_profit_price: float | None = None
    strategy_conflict_warning: str | None = None
    allocation_adjustment_notice: str | None = None
    hedge_suggestion: dict = Field(default_factory=dict)
    risk_reduction_score: float | None = None
    venue_context: dict = Field(default_factory=dict)
    requested_leverage: int | None = None
    recommended_leverage: int | None = None
    applied_leverage: int | None = None
    leverage_policy_mode: str | None = None
    leverage_clamp_reasons: list[str] = Field(default_factory=list)
    execution_mode: str = "live"
    policy_decision: dict = Field(default_factory=dict)
    policy_trace: dict = Field(default_factory=dict)
    pipeline_stage_results: list[dict] = Field(default_factory=list)
    decision_trace: dict = Field(default_factory=dict)
    standardized_reject: dict | None = None
    rollout_mode: str = "shadow"


class TradingPreviewRateLimitResponse(BaseModel):
    allowed: bool
    retry_after_seconds: float = 0
    remaining_tokens: float


class TradingPreviewResponse(BaseModel):
    preview: ExecutionIntentPreviewResponse
    metrics: dict
    rate_limit: TradingPreviewRateLimitResponse


class ExecutionIntentSubmitRequest(BaseModel):
    intent_token: str
    preview_hash: str | None = None


class ExecutionIntentSubmitResponse(BaseModel):
    intent_id: str
    intent_status: str
    reason_codes: list[str]
    queue_state: str
    execution_mode: str = "live"
    policy_decision: dict = Field(default_factory=dict)
    pipeline_trace: list[dict] = Field(default_factory=list)
    explain: list[str] = Field(default_factory=list, min_length=1)


class OrderValidationRequest(BaseModel):
    symbol: str
    market_type: str = "spot"
    order_type: str = "market"
    side: str = "buy"
    price: float = 0
    size: float = 0
    leverage: int = 1
    margin_mode: str = "isolated"


class OrderValidationViolation(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)


class OrderValidationResponse(BaseModel):
    valid: bool
    violations: list[OrderValidationViolation] = Field(default_factory=list)
    execution_mode: str = "live"
    checks: dict = Field(default_factory=dict)
    explain: list[str] = Field(default_factory=list, min_length=1)


class AdminEmergencyStopRequest(BaseModel):
    reason: str = Field(default="manual_emergency_stop", min_length=3, max_length=220)


class AdminEmergencyStopResponse(BaseModel):
    status: str
    reason: str
    stop_all_bots_applied: bool
    closed_positions_count: int
    rejected_intents_count: int
    disable_futures_applied: bool
    emergency_mode_active: bool
    kill_switch_reasons: list[str]
    triggered_at: datetime


class ExecutionIntentCancelRequest(BaseModel):
    intent_token: str


class ExecutionIntentCancelResponse(BaseModel):
    intent_id: str
    intent_status: str
    cancelled: bool


class ExecutionPresetResponse(BaseModel):
    preset_code: str
    default_order_type: str
    default_tp_mode: str
    default_sl_mode: str
    default_risk_percent: float
    default_margin_mode: str | None
    default_leverage: int | None
    editable_fields: list[str]
    locked_fields: list[str]


class ExecutionIntentQueueItemResponse(BaseModel):
    id: str
    intent_token: str
    user_id: str
    user_email: str | None = None
    intent_type: str = "OPEN_POSITION"
    position_id: str | None = None
    symbol: str
    market_type: str
    side: str
    notional: float
    size: float | None = None
    reduce_only: bool = False
    price: float | None = None
    stop_price: float | None = None
    take_profit_price: float | None = None
    status: str
    risk_flags: list[str]
    reject_reason_codes: list[str]
    normalized_order_payload: dict
    risk_score: float | None = None
    gate_decision: str | None = None
    meta_engine_decision: str | None = None
    cluster_id: str | None = None
    risk_payload: dict = Field(default_factory=dict)
    operational_status: str = "retryable"
    expected_impact: dict = Field(default_factory=dict)
    detail_version: str | None = None
    snapshot_generated_at: datetime | None = None
    created_at: datetime


class PositionActionPreviewRequest(BaseModel):
    intent_type: str
    position_id: str
    symbol: str
    size: float = Field(gt=0)
    reduce_only: bool = True
    price: float | None = None
    stop_price: float | None = None
    take_profit_price: float | None = None


class PositionStateResponse(BaseModel):
    position_id: str
    symbol: str
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    leverage: int
    strategy_id: str | None
    cluster_id: str | None
    status: str
    execution_mode: str = "live"
    recommended_action: str | None = None
    risk_reduction_score: float | None = None
    hedge_suggestion: dict = Field(default_factory=dict)
    updated_at: datetime


class AdminPositionsMonitorResponse(BaseModel):
    generated_at: datetime
    open_positions: list[PositionStateResponse]
    cluster_exposure: dict[str, float]
    risk_level: str
    forced_liquidation_risk: float


class StrategyConflictResponse(BaseModel):
    conflict_detected: bool
    winning_strategy: str | None = None
    losing_strategy: str | None = None
    resolution_reason: str
    conflict_count: int = 0


class RebalanceGovernanceSummaryResponse(BaseModel):
    cadence_window_minutes: int = 30
    max_weight_shift_per_cycle: float = 0.12
    max_capital_shift_pct: float = 0.2
    drift_threshold: float = 0.08
    cadence_blocked_strategies: int = 0
    weight_shift_capped_strategies: int = 0
    capital_shift_capped_strategies: int = 0


class CapitalRebalanceEventResponse(BaseModel):
    strategy_id: str
    old_strategy_weight: float
    new_strategy_weight: float
    target_strategy_weight: float | None = None
    capital_shift: float
    throttle_signal: bool
    allocation_drift: float
    strategy_performance_delta: float
    risk_adjusted_return: float
    cadence_window_blocked: bool = False
    minutes_since_last_rebalance: float | None = None
    max_weight_shift_applied: bool = False
    max_capital_shift_applied: bool = False


class HedgeSuggestionResponse(BaseModel):
    hedge_symbol: str | None = None
    hedge_size: float = 0
    hedge_direction: str | None = None
    risk_reduction_score: float = 0
    correlation_basis: str = ""
    recommended_action: str = "monitor"


class AdminStrategyIntelligenceResponse(BaseModel):
    generated_at: datetime
    strategy_conflicts: list[StrategyConflictResponse]
    capital_rebalance_events: list[CapitalRebalanceEventResponse]
    hedge_suggestions: list[HedgeSuggestionResponse]
    governance_summary: RebalanceGovernanceSummaryResponse | None = None
    allocation_drift: float
    strategy_performance_delta: float
    risk_adjusted_return: float


class ManualOverrideRequest(BaseModel):
    scope: str = "strategy_intelligence"
    target_type: str = "user"
    target_id: str | None = None
    action_type: str
    reason: str = Field(min_length=8)
    simulation_id: str
    expires_at: datetime | None = None
    ttl_minutes: int | None = Field(default=None, ge=1, le=10080)
    confirmation_id: str | None = None
    previous_state: dict = Field(default_factory=dict)
    next_state: dict = Field(default_factory=dict)
    impact_preview: dict = Field(default_factory=dict)
    payload: dict = Field(default_factory=dict)


class ManualOverrideResponse(BaseModel):
    override_id: str
    admin_id: str
    actor_role: str | None = None
    scope: str = "strategy_intelligence"
    target_type: str = "user"
    target_id: str | None = None
    action_type: str
    reason: str
    simulation_id: str | None = None
    confirmation_id: str | None = None
    previous_state: dict = Field(default_factory=dict)
    next_state: dict = Field(default_factory=dict)
    impact_preview: dict = Field(default_factory=dict)
    expires_at: datetime | None = None
    current_status: str = "active"
    revoked_at: datetime | None = None
    revoked_by: str | None = None
    expiry_countdown_seconds: int | None = None
    linked_approval_request_id: str | None = None
    payload: dict
    timestamp: datetime


class ManualOverrideRevokeRequest(BaseModel):
    reason: str = Field(min_length=8)


class ManualOverrideRevokeResponse(BaseModel):
    override_id: str
    status: str
    revoked_at: datetime
    revoked_by: str
    message: str


class RiskSimulationRequest(BaseModel):
    user_id: str
    intent_payload: dict
    apply_override: bool = False
    override_action_type: str | None = None
    override_reason: str | None = None
    preset_scenario: str | None = None
    preset_overrides: dict = Field(default_factory=dict)


class RiskSimulationResponse(BaseModel):
    simulated_at: datetime
    simulation_id: str
    dry_run: bool = True
    simulation_payload: dict
    strategy_conflict: dict
    allocation_adjustment: dict
    hedge_suggestion: dict
    projected_risk_score: float
    projected_gate_decision: str
    projected_pnl: float = 0
    projected_drawdown: float = 0
    projected_exposure: float = 0
    projected_var: float = 0
    projected_liquidity_impact: float = 0
    exposure_change: float = 0
    var_change: float = 0
    liquidity_impact: float = 0
    confidence_adjusted_risk_score: float = 0
    before_state: dict = Field(default_factory=dict)
    after_state: dict = Field(default_factory=dict)
    decision_summary: dict = Field(default_factory=dict)
    risk_delta: float = 0
    decision_delta: str = "UNCHANGED"
    reasoned_output: str = ""
    expected_outcome: str = ""


class RiskBatchSimulationRequest(BaseModel):
    user_id: str
    symbols: list[str] = Field(default_factory=list)
    intent_payload: dict = Field(default_factory=dict)
    preset_scenario: str | None = None
    preset_overrides: dict = Field(default_factory=dict)


class RiskBatchSimulationItem(BaseModel):
    simulation_id: str
    symbol: str
    projected_risk_score: float
    projected_gate_decision: str
    risk_delta: float
    decision_delta: str
    confidence_adjusted_risk_score: float


class RiskBatchSimulationResponse(BaseModel):
    batch_id: str
    simulated_at: datetime
    total_symbols: int
    summary: dict = Field(default_factory=dict)
    items: list[RiskBatchSimulationItem] = Field(default_factory=list)


class RiskMatrixBatchSimulationRequest(BaseModel):
    user_id: str
    symbols: list[str] = Field(default_factory=list)
    strategy_bindings: list[str] = Field(default_factory=list)
    side: str = "buy"
    base_notional: float = 100
    volatility_pct: float = 3
    preset_scenario: str | None = None
    preset_overrides: dict = Field(default_factory=dict)


class RiskMatrixBatchSimulationItem(BaseModel):
    simulation_id: str
    symbol: str
    strategy_binding: str
    projected_risk_score: float
    confidence_adjusted_risk_score: float
    projected_gate_decision: str
    risk_delta: float
    decision_delta: str
    severity_band: str = "low"


class RiskMatrixBatchSimulationResponse(BaseModel):
    matrix_id: str
    simulated_at: datetime
    total_runs: int
    summary: dict = Field(default_factory=dict)
    items: list[RiskMatrixBatchSimulationItem] = Field(default_factory=list)


class RiskSimulationPresetItem(BaseModel):
    preset_key: str
    label: str
    description: str
    defaults: dict = Field(default_factory=dict)


class RiskSimulationPresetsResponse(BaseModel):
    items: list[RiskSimulationPresetItem] = Field(default_factory=list)


class SimulationHistoryItemResponse(BaseModel):
    run_id: str
    actor_id: str | None = None
    actor_role: str | None = None
    scope: str
    status: str
    request_mode: str = "single"
    symbols: list[str] = Field(default_factory=list)
    summary_hash: str | None = None
    input_payload: dict = Field(default_factory=dict)
    output_payload: dict = Field(default_factory=dict)
    approval_request_id: str | None = None
    decision_request_type: str | None = None
    decision_severity_band: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class SimulationHistoryResponse(BaseModel):
    items: list[SimulationHistoryItemResponse] = Field(default_factory=list)


class DecisionApprovalRequestResponse(BaseModel):
    request_id: str
    request_type: str
    status: str
    requested_by: str
    requested_role: str
    reason_note: str
    simulation_run_id: str | None = None
    payload: dict = Field(default_factory=dict)
    expires_at: datetime
    created_at: datetime
    decided_at: datetime | None = None
    approved_by: str | None = None
    review_note: str | None = None
    assigned_to: str | None = None
    ack_by: str | None = None
    ack_at: datetime | None = None
    target_type: str | None = None
    target_id: str | None = None
    simulation_required: bool = True
    simulation_present: bool = False
    preview_token: str | None = None
    risk_delta_score: float = 0
    severity_band: str = "low"
    impact_summary: dict = Field(default_factory=dict)
    deterministic_effect_preview: dict = Field(default_factory=dict)
    execution_effect: dict = Field(default_factory=dict)
    state_change: str | None = None
    recommendation_rank: int | None = None
    sla_countdown_seconds: int | None = None
    sla_state: str = "n/a"
    escalation_state: str = "none"
    explanation_summary: str = ""
    decision_factors: dict = Field(default_factory=dict)
    previous_state_snapshot: dict = Field(default_factory=dict)
    source_request_id: str | None = None
    linked_revert_request_id: str | None = None
    reverted_at: datetime | None = None
    reverted_by: str | None = None
    revert_reason: str | None = None


class EscalationCenterItemResponse(BaseModel):
    escalation_id: str
    linked_request_id: str
    linked_simulation_run_id: str | None = None
    state: str = "active"
    escalation_level: str = "L1"
    escalation_reason: str
    breach_age_seconds: int = 0
    current_owner: str
    ack_by: str | None = None
    ack_at: datetime | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None


class EscalationCenterResponse(BaseModel):
    active_breaches: list[EscalationCenterItemResponse] = Field(default_factory=list)
    acknowledged: list[EscalationCenterItemResponse] = Field(default_factory=list)
    resolved: list[EscalationCenterItemResponse] = Field(default_factory=list)


class EscalationAcknowledgeRequest(BaseModel):
    escalation_reason: str = Field(min_length=8)
    current_owner: str | None = None


class EscalationResolveRequest(BaseModel):
    escalation_reason: str = Field(min_length=8)


class EscalationAssignOwnerRequest(BaseModel):
    current_owner: str = Field(min_length=2)
    escalation_reason: str = Field(min_length=8)


class StrategyIntelligenceImportRequest(BaseModel):
    decision_requests: list[dict] = Field(default_factory=list)
    simulation_runs: list[dict] = Field(default_factory=list)


class StrategyIntelligenceImportResponse(BaseModel):
    imported_decision_requests: int = 0
    imported_simulation_runs: int = 0
    skipped_items: int = 0


class DecisionApprovalRequestsResponse(BaseModel):
    items: list[DecisionApprovalRequestResponse] = Field(default_factory=list)


class DecisionApprovalActionRequest(BaseModel):
    reason_note: str = Field(min_length=8)


class DecisionRequestAssignOwnerRequest(BaseModel):
    assigned_to: str = Field(min_length=2)


class DecisionRequestAckRequest(BaseModel):
    reason_note: str = Field(min_length=8)


class DecisionBulkActionRequest(BaseModel):
    action: str
    request_ids: list[str] = Field(default_factory=list)
    reason_note: str = Field(min_length=8)


class DecisionBulkActionResponse(BaseModel):
    action: str
    processed: int
    updated_request_ids: list[str] = Field(default_factory=list)


class DecisionRequestCreateRequest(BaseModel):
    target_type: str
    target_id: str
    reason_note: str = Field(min_length=8)
    simulation_run_id: str | None = None
    expires_at: datetime | None = None
    impact_summary: dict = Field(default_factory=dict)
    risk_delta_score: float | None = None


class DecisionRequestExecuteRequest(BaseModel):
    reason_note: str = Field(min_length=8)
    preview_token: str


class DecisionRequestRevertRequest(BaseModel):
    reason_note: str = Field(min_length=8)


class DecisionRequestPreviewResponse(BaseModel):
    request_id: str
    status: str
    preview_token: str
    risk_delta_score: float
    severity_band: str
    impact_summary: dict = Field(default_factory=dict)


class SimulationCompareCurrentResponse(BaseModel):
    run_id: str
    status: str
    before: dict = Field(default_factory=dict)
    current: dict = Field(default_factory=dict)
    compare_summary: dict = Field(default_factory=dict)


class ManualOverrideSubmissionResponse(BaseModel):
    status: str
    message: str
    request_id: str | None = None
    override: ManualOverrideResponse | None = None


class CommercialUsageLogItemResponse(BaseModel):
    log_id: str
    user_id: str
    user_email: str
    symbol: str
    side: str
    order_id: str
    execution_status: str
    order_type: str
    exchange: str
    pnl: float
    opened_at: datetime


class CommercialUsageLogsResponse(BaseModel):
    generated_at: datetime
    total: int
    items: list[CommercialUsageLogItemResponse]


class CommercialPnlUserResponse(BaseModel):
    user_id: str
    user_email: str
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float


class CommercialPnlSummaryResponse(BaseModel):
    user_count: int
    total_realized_pnl: float
    total_unrealized_pnl: float
    total_pnl: float


class CommercialPnlWindowResponse(BaseModel):
    range_start: datetime
    range_end: datetime
    summary: CommercialPnlSummaryResponse
    users: list[CommercialPnlUserResponse]


class CommercialCalendarMonthPnlResponse(CommercialPnlWindowResponse):
    month: str


class AdminCommercialTotalPnlResponse(BaseModel):
    generated_at: datetime
    last_30_days: CommercialPnlWindowResponse
    calendar_month: CommercialCalendarMonthPnlResponse


class AdminCommercialOverviewAppliedFiltersResponse(BaseModel):
    environment: str
    time_window: str
    from_ts: str | None = None
    to_ts: str | None = None
    range_start: datetime | None = None
    range_end: datetime | None = None


class AdminCommercialFinancialAccuracyResponse(BaseModel):
    record_count: int
    trade_count: int
    realized_gross_usd: float
    unrealized_gross_usd: float
    gross_total_usd: float
    realized_net_usd: float
    unrealized_net_usd: float
    net_total_usd: float
    net_vs_gross_delta_usd: float
    trading_fee_total_usd: float
    funding_total_usd: float
    commission_total_usd: float
    exchange_trade_count: int = 0
    internal_trade_count: int = 0
    missing_trade_count: int = 0
    duplicate_trade_count: int = 0
    balance_drift_usd: float = 0
    position_drift_usd: float = 0
    pnl_drift_usd: float = 0
    drift_within_tolerance: bool = True
    reconciliation_status: str = "unknown"


class AdminCommercialRevenueComponentResponse(BaseModel):
    component_type: str
    revenue_usd: float
    source_amount_usd: float
    share_rate_avg: float
    row_count: int


class AdminCommercialRevenueSymbolResponse(BaseModel):
    symbol: str
    revenue_usd: float


class AdminCommercialRevenueByUserResponse(BaseModel):
    user_id: str
    user_email: str
    revenue_usd: float


class AdminCommercialRevenueByPlanResponse(BaseModel):
    tier_code: str
    subscription_status: str
    billing_cycle: str
    revenue_usd: float


class AdminCommercialRevenueBySymbolResponse(BaseModel):
    symbol: str
    revenue_usd: float


class AdminCommercialRevenueModelResponse(BaseModel):
    total_revenue_usd: float
    component_breakdown: list[AdminCommercialRevenueComponentResponse] = Field(default_factory=list)
    top_symbols: list[AdminCommercialRevenueSymbolResponse] = Field(default_factory=list)
    row_count: int
    subscription_revenue_usd: float = 0
    platform_fee_revenue_usd: float = 0
    tier_fee_revenue_usd: float = 0
    profit_split_revenue_usd: float = 0
    manual_adjustment_revenue_usd: float = 0
    revenue_by_user: list[AdminCommercialRevenueByUserResponse] = Field(default_factory=list)
    revenue_by_plan: list[AdminCommercialRevenueByPlanResponse] = Field(default_factory=list)
    revenue_by_symbol: list[AdminCommercialRevenueBySymbolResponse] = Field(default_factory=list)


class AdminCommercialEconomicsTopUserResponse(BaseModel):
    user_id: str
    user_email: str
    ltv_usd: float
    revenue_contribution_usd: float
    realized_pnl_usd: float
    inactive_days: int
    churned: bool


class AdminCommercialUserEconomicsResponse(BaseModel):
    total_users: int
    paying_users: int
    churned_users: int
    total_ltv_usd: float
    total_revenue_contribution_usd: float
    total_realized_pnl_usd: float
    avg_ltv_usd: float
    avg_inactive_days: float
    arpu_usd: float = 0
    arppu_usd: float = 0
    churn_rate_pct: float = 0
    inactive_user_count: int = 0
    cohort_summary: list[dict] = Field(default_factory=list)
    signup_to_retention_summary: list[dict] = Field(default_factory=list)
    segment_distribution: dict[str, int] = Field(default_factory=dict)
    top_users: list[AdminCommercialEconomicsTopUserResponse] = Field(default_factory=list)
    top_profitability_users: list[AdminCommercialEconomicsTopUserResponse] = Field(default_factory=list)
    high_churn_risk_users: list[AdminCommercialEconomicsTopUserResponse] = Field(default_factory=list)


class AdminCommercialRiskSymbolExposureResponse(BaseModel):
    symbol: str
    exposure_usd: float


class AdminCommercialRiskSummaryResponse(BaseModel):
    open_position_count: int
    risk_exposure_usd: float
    high_drift_reconciliation_count: int
    latest_daily_loss_limit_pct: float | None = None
    trading_enabled: bool
    kill_switch_enabled: bool
    top_exposure_symbols: list[AdminCommercialRiskSymbolExposureResponse] = Field(default_factory=list)
    user_exposure_breakdown: list[dict] = Field(default_factory=list)
    strategy_exposure_breakdown: list[dict] = Field(default_factory=list)
    symbol_exposure_breakdown: list[AdminCommercialRiskSymbolExposureResponse] = Field(default_factory=list)
    open_positions: list[dict] = Field(default_factory=list)
    risk_limit_breach_count: int = 0
    breached_users: list[dict] = Field(default_factory=list)
    liquidation_risk_score: float = 0
    forced_liquidation_risk: str = "low"
    margin_risk_score: float = 0
    margin_risk_state: str = "stable"


class AdminCommercialUsageSymbolResponse(BaseModel):
    symbol: str
    trade_count: int
    notional_usd: float


class AdminCommercialUsageAnalyticsResponse(BaseModel):
    total_trades: int
    unique_users: int
    unique_symbols: int
    total_notional_usd: float
    avg_trade_notional_usd: float
    activity_days: int
    by_market_type: dict[str, int] = Field(default_factory=dict)
    by_exchange: dict[str, int] = Field(default_factory=dict)
    top_symbols: list[AdminCommercialUsageSymbolResponse] = Field(default_factory=list)
    request_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    error_rate_pct: float = 0
    avg_latency_ms: float = 0
    p95_latency_ms: float = 0
    rate_per_minute: float = 0
    api_usage_by_endpoint: list[dict] = Field(default_factory=list)
    event_type_distribution: list[dict] = Field(default_factory=list)


class AdminCommercialDataQualityResponse(BaseModel):
    status: str
    empty_data: bool
    stale_sources: list[str] = Field(default_factory=list)
    freshness_seconds: int | None = None
    stale_threshold_seconds: int
    latest_trade_at: datetime | None = None
    latest_pnl_at: datetime | None = None
    latest_reconciliation_at: datetime | None = None
    missing_data_alert: bool
    trade_count: int
    pnl_record_count: int
    duplicate_trade_count: int = 0
    duplicate_trade_status: str = "unknown"
    cross_source_validation_state: str = "unknown"
    missing_symbols: list[str] = Field(default_factory=list)
    missing_data_sources: list[str] = Field(default_factory=list)
    reconciliation_coverage_pct: float = 0
    last_successful_reconciliation_at: datetime | None = None
    freshness_by_source: dict[str, int | None] = Field(default_factory=dict)
    stale_source_count: int = 0


class AdminCommercialPnlBreakdownResponse(BaseModel):
    key: str
    realized_pnl_usd: float
    unrealized_pnl_usd: float
    total_pnl_usd: float
    trade_count: int


class AdminCommercialTrendPointResponse(BaseModel):
    bucket: str
    realized_pnl_usd: float
    unrealized_pnl_usd: float
    total_pnl_usd: float


class AdminCommercialPnlAnalyticsResponse(BaseModel):
    strategy_pnl_breakdown: list[AdminCommercialPnlBreakdownResponse] = Field(default_factory=list)
    symbol_pnl_breakdown: list[AdminCommercialPnlBreakdownResponse] = Field(default_factory=list)
    daily_pnl_trend: list[AdminCommercialTrendPointResponse] = Field(default_factory=list)
    weekly_pnl_trend: list[AdminCommercialTrendPointResponse] = Field(default_factory=list)
    realized_vs_unrealized_trend: list[AdminCommercialTrendPointResponse] = Field(default_factory=list)
    max_drawdown_usd: float = 0
    max_drawdown_pct: float = 0
    drawdown_series: list[dict] = Field(default_factory=list)


class AdminCommercialExportJobResponse(BaseModel):
    schedule_id: str
    export_type: str
    schedule_period: str
    is_active: bool
    output_format: str
    last_status: str
    last_run_at: datetime | None = None
    last_output_ref: str | None = None
    failure_reason: str | None = None
    retry_count: int = 0
    next_retry_at: datetime | None = None
    running_started_at: datetime | None = None
    stale_run_flag: bool = False
    retention_state: str | None = None
    downloadable_state: str | None = None


class AdminCommercialExportOpsResponse(BaseModel):
    scheduler_health: str = "unknown"
    pending_exports: int = 0
    delivered_exports: int = 0
    recent_export_jobs: list[AdminCommercialExportJobResponse] = Field(default_factory=list)
    recent_manifests: list[dict] = Field(default_factory=list)
    recent_audits: list[dict] = Field(default_factory=list)


class AdminCommercialAlertItemResponse(BaseModel):
    id: str
    alert_type: str
    severity: str
    source: str
    entity_type: str
    entity_id: str
    title: str
    message: str
    suggested_action: str
    triage_status: str = "new"
    acknowledged_at: datetime | None = None
    assigned_to_user_id: str | None = None
    assigned_to_email: str | None = None
    assigned_at: datetime | None = None
    assignment_note: str | None = None
    age_seconds: int = 0
    sla_state: str = "within_sla"
    auto_escalated: bool = False
    auto_escalated_at: datetime | None = None
    created_at: datetime


class AdminCommercialOperationalControlSummaryResponse(BaseModel):
    trading_enabled_count: int = 0
    emergency_stop_count: int = 0
    capital_frozen_count: int = 0
    withdraw_locked_count: int = 0
    recent_actions: list[dict] = Field(default_factory=list)


class AdminCommercialOverviewResponse(BaseModel):
    generated_at: datetime
    contract_version: str
    applied_filters: AdminCommercialOverviewAppliedFiltersResponse
    financial_accuracy: AdminCommercialFinancialAccuracyResponse
    revenue_model: AdminCommercialRevenueModelResponse
    user_economics: AdminCommercialUserEconomicsResponse
    pnl_analytics: AdminCommercialPnlAnalyticsResponse
    risk_summary: AdminCommercialRiskSummaryResponse
    usage_analytics: AdminCommercialUsageAnalyticsResponse
    data_quality: AdminCommercialDataQualityResponse
    export_ops: AdminCommercialExportOpsResponse
    alert_rail: list[AdminCommercialAlertItemResponse] = Field(default_factory=list)
    operational_controls: AdminCommercialOperationalControlSummaryResponse


class CommercialExportManifestCreateRequest(BaseModel):
    export_type: str
    schema_version: str = "v1"
    filters_snapshot: dict = Field(default_factory=dict)
    column_mapping: dict = Field(default_factory=dict)
    output_format: str = "csv"
    row_count: int = Field(default=0, ge=0)
    reason_note: str = Field(min_length=5, max_length=255)


class CommercialExportManifestResponse(BaseModel):
    export_id: str
    export_type: str
    schema_version: str
    requested_by: str
    requested_at: datetime
    output_format: str
    checksum: str
    status: str
    canonical_column_mapping: dict = Field(default_factory=dict)
    canonical_mapping_summary: dict = Field(default_factory=dict)


class CommercialExportScheduleCreateRequest(BaseModel):
    export_type: str
    schedule_period: str = Field(pattern="^(daily|weekly|monthly)$")
    output_format: str = "csv"
    filters_snapshot: dict = Field(default_factory=dict)
    max_retry: int = Field(default=3, ge=0, le=10)


class CommercialExportScheduleResponse(BaseModel):
    schedule_id: str
    export_type: str
    schedule_period: str
    output_format: str
    is_active: bool
    last_status: str
    last_run_at: datetime | None = None
    retry_count: int = 0
    next_retry_at: datetime | None = None
    running_started_at: datetime | None = None
    stale_run_flag: bool = False


class CommercialOperationalControlUpdateRequest(BaseModel):
    trading_enabled: bool
    capital_frozen: bool
    withdraw_locked: bool
    emergency_stop: bool
    reason_note: str = Field(min_length=5, max_length=255)


class CommercialOperationalControlResponse(BaseModel):
    user_id: str
    trading_enabled: bool
    capital_frozen: bool
    withdraw_locked: bool
    emergency_stop: bool
    reason_note: str
    updated_at: datetime


class CommercialAlertLifecycleUpdateRequest(BaseModel):
    triage_status: str = Field(pattern="^(new|acknowledged|investigating|resolved|ignored)$")
    escalation_level: str = Field(pattern="^(none|low|medium|high|critical)$")
    resolution_note: str | None = Field(default=None, max_length=500)
    acknowledge: bool = False


class CommercialAlertLifecycleResponse(BaseModel):
    alert_id: str
    triage_status: str
    escalation_level: str
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
    resolution_note: str | None = None
    resolution_at: datetime | None = None


class CommercialAlertBulkLifecycleRequest(BaseModel):
    alert_ids: list[str] = Field(min_length=1, max_length=100)
    triage_status: str | None = Field(default=None, pattern="^(new|acknowledged|investigating|resolved|ignored)$")
    escalation_level: str | None = Field(default=None, pattern="^(none|low|medium|high|critical)$")
    acknowledge: bool = False


class CommercialAlertAssignmentRequest(BaseModel):
    assigned_to_user_id: str
    assigned_to_email: str
    assignment_note: str = Field(min_length=3, max_length=500)


class UserFundWithdrawRequest(BaseModel):
    amount_usd: float = Field(gt=0)
    destination: str = Field(min_length=3, max_length=200)
    reason_note: str = Field(min_length=5, max_length=255)


class UserFundWithdrawResponse(BaseModel):
    status: str
    request_id: str
    reason_code: str | None = None


class CommercialP0IngestionRequest(BaseModel):
    target_user_id: str | None = None
    target_user_email: str | None = None
    environment: str = "live"
    market_types: list[str] = Field(default_factory=lambda: ["spot", "futures"])
    symbols: list[str] = Field(default_factory=list)
    start_ts: str | None = None
    end_ts: str | None = None
    limit_per_symbol: int = Field(default=500, ge=1, le=1000)


class CommercialP0IngestionResponse(BaseModel):
    status: str
    user_id: str
    user_email: str
    environment: str
    market_types: list[str]
    symbols: list[str]
    time_window: dict = Field(default_factory=dict)
    fetched: int
    inserted: int
    duplicate: int
    market_summary: dict = Field(default_factory=dict)
    revenue_sync: dict = Field(default_factory=dict)
    source: str
    generated_at: str


class CommercialP0PnlResponse(BaseModel):
    status: str
    user_id: str
    user_email: str
    environment: str
    trade_count: int
    realized: dict = Field(default_factory=dict)
    unrealized: dict = Field(default_factory=dict)
    fee_breakdown: dict = Field(default_factory=dict)
    net_total_usd: float
    record_id: str
    as_of: str | None = None


class CommercialP0ReconciliationRequest(BaseModel):
    target_user_id: str | None = None
    target_user_email: str | None = None
    environment: str = "live"
    market_types: list[str] = Field(default_factory=lambda: ["spot", "futures"])
    symbols: list[str] = Field(default_factory=list)
    start_ts: str | None = None
    end_ts: str | None = None
    limit_per_symbol: int = Field(default=500, ge=1, le=1000)
    drift_tolerance_usd: float | None = Field(default=None, gt=0)
    drift_tolerance_pct: float | None = Field(default=0.3, gt=0)


class CommercialP0ReconciliationResponse(BaseModel):
    status: str
    log_id: str
    user_id: str
    user_email: str
    environment: str
    markets: list[str]
    internal_trade_count: int
    exchange_trade_count: int
    missing_trade_count: int
    duplicate_trade_count: int
    balance_drift_usd: float
    position_drift_usd: float
    pnl_drift_usd: float
    drift_tolerance_usd: float
    drift_tolerance_pct: float | None = None
    drift_within_tolerance: bool
    freshness_seconds: int | None = None
    missing_data_alert: bool
    created_at: str | None = None


class CommercialP0DataQualityResponse(BaseModel):
    status: str
    user_id: str
    user_email: str
    environment: str
    freshness_seconds: dict = Field(default_factory=dict)
    missing_data_alert: bool
    market_alerts: dict = Field(default_factory=dict)
    latest_reconciliation: dict = Field(default_factory=dict)


class CommercialP0LiveGateResponse(BaseModel):
    status: str
    user_id: str
    user_email: str
    environment: str
    required_market_types: list[str] = Field(default_factory=list)
    controls: dict = Field(default_factory=dict)
    live_transition_ready: bool
    evidence: dict = Field(default_factory=dict)


class RevenueTopUserItem(BaseModel):
    user_id: str
    email: str
    revenue_usd: float


class RevenueTopSymbolItem(BaseModel):
    symbol: str
    revenue_usd: float


class RevenueDailyPoint(BaseModel):
    date: str
    total_revenue_usd: float
    fee_revenue_usd: float
    pnl_share_revenue_usd: float


class AdminRevenueSummaryResponse(BaseModel):
    status: str
    environment: str
    applied_filters: dict = Field(default_factory=dict)
    total_revenue_usd: float
    today_revenue_usd: float
    top_users: list[RevenueTopUserItem] = Field(default_factory=list)
    top_symbols: list[RevenueTopSymbolItem] = Field(default_factory=list)
    daily_revenue: list[RevenueDailyPoint] = Field(default_factory=list)
    generated_at: str


class UserEconomicsKpis(BaseModel):
    total_users: int
    paying_users: int
    churned_users: int
    churn_rate_pct: float
    total_revenue_usd: float
    arpu_usd: float
    arppu_usd: float
    avg_ltv_usd: float


class UserEconomicsUserRow(BaseModel):
    user_id: str
    email: str
    ltv_usd: float
    revenue_contribution_usd: float
    realized_pnl_usd: float
    inactive_days: int
    churned: bool
    cohort_month: str | None = None
    last_activity_at: str | None = None


class UserEconomicsTopSymbol(BaseModel):
    symbol: str
    revenue_usd: float


class UserEconomicsCohortRow(BaseModel):
    cohort_month: str
    users: int
    paying_users: int
    churned_users: int
    total_revenue_usd: float
    avg_ltv_usd: float


class AdminUserEconomicsResponse(BaseModel):
    status: str
    environment: str
    filters: dict = Field(default_factory=dict)
    sync: dict = Field(default_factory=dict)
    kpis: UserEconomicsKpis
    top_users: list[UserEconomicsUserRow] = Field(default_factory=list)
    churn_list: list[UserEconomicsUserRow] = Field(default_factory=list)
    top_symbols: list[UserEconomicsTopSymbol] = Field(default_factory=list)
    cohorts: list[UserEconomicsCohortRow] = Field(default_factory=list)
    rows: list[UserEconomicsUserRow] = Field(default_factory=list)
    generated_at: str


class RetentionTrendPoint(BaseModel):
    cohort: str
    period: str
    cohort_size: int
    active_users: int
    retention_rate_pct: float
    cohort_revenue_usd: float
    cohort_realized_pnl_usd: float


class AdminRetentionTrendResponse(BaseModel):
    status: str
    environment: str
    granularity: str
    lookback_periods: int
    points: list[RetentionTrendPoint] = Field(default_factory=list)
    generated_at: str


class SegmentCardResponse(BaseModel):
    segment: str
    users: int
    total_revenue_usd: float
    total_realized_pnl_usd: float


class AdminSegmentProfitabilityResponse(BaseModel):
    status: str
    environment: str
    churn_inactive_days: int
    segment_cards: list[SegmentCardResponse] = Field(default_factory=list)
    churn_risk_list: list[UserEconomicsUserRow] = Field(default_factory=list)
    reengagement_list: list[UserEconomicsUserRow] = Field(default_factory=list)
    generated_at: str


class UserEconomicsSnapshotRunResponse(BaseModel):
    status: str
    environment: str
    snapshot_type: str
    snapshot_date: str
    inserted: int
    updated: int
    rows: int


class UserEconomicsSnapshotTrendPoint(BaseModel):
    snapshot_date: str
    users: int
    churned_users: int
    churn_rate_pct: float
    total_revenue_usd: float
    avg_ltv_usd: float


class UserEconomicsSnapshotTrendResponse(BaseModel):
    status: str
    environment: str
    snapshot_type: str
    points: list[UserEconomicsSnapshotTrendPoint] = Field(default_factory=list)
    generated_at: str


class CommercialP0WebsocketBootstrapRequest(BaseModel):
    target_user_id: str | None = None
    target_user_email: str | None = None
    environment: str = "live"
    market_types: list[str] = Field(default_factory=lambda: ["spot", "futures"])


class CommercialP0WebsocketBootstrapResponse(BaseModel):
    status: str
    user_id: str
    user_email: str
    environment: str
    streams: dict = Field(default_factory=dict)
    note: str
    generated_at: str


class CommercialP0WsWorkerStartRequest(BaseModel):
    target_user_id: str | None = None
    target_user_email: str | None = None
    environment: str = "live"
    market_types: list[str] = Field(default_factory=lambda: ["spot", "futures"])


class CommercialP0WsWorkerStopRequest(BaseModel):
    target_user_id: str | None = None
    target_user_email: str | None = None
    environment: str = "live"
    market_types: list[str] = Field(default_factory=list)


class CommercialP0WsWorkerResponse(BaseModel):
    status: str
    worker: dict | None = None
    worker_key: str | None = None
    stopped_count: int | None = None


class CommercialP0WsWorkerStatusResponse(BaseModel):
    status: str
    workers: list[dict] = Field(default_factory=list)
    count: int = 0


class LearningImpactSimulationRequest(BaseModel):
    strategy_id: str | None = None
    strategy_ids: list[str] = Field(default_factory=list)
    family: str | None = None
    symbol_cluster: list[str] = Field(default_factory=list)
    scenario: str = "base"
    recommendation_type: str = "decrease_weight_recommendation"
    suggested_weight_multiplier: float | None = Field(default=None, ge=0.1, le=3.0)


class LearningImpactSimulationResponse(BaseModel):
    schema_version: str
    engine_version: str
    simulated_at: datetime
    scope: str
    strategy_id: str | None = None
    strategy_ids: list[str] = Field(default_factory=list)
    family: str | None = None
    symbol_cluster: list[str] = Field(default_factory=list)
    scenario: str = "base"
    recommendation_type: str
    read_only: bool = True
    projected_risk_score: float
    projected_gate_decision: str
    expected_hit_rate_delta: float
    expected_avg_return_delta: float
    allocation_drift_delta: float
    hedge_effect_score: float
    baseline_metrics: dict = Field(default_factory=dict)
    projected_metrics: dict = Field(default_factory=dict)
    delta_metrics: dict = Field(default_factory=dict)
    sample_coverage: dict = Field(default_factory=dict)
    baseline: dict = Field(default_factory=dict)
    counterfactual_replay: dict = Field(default_factory=dict)
    portfolio_impact: dict = Field(default_factory=dict)
    risk_aware_view: dict = Field(default_factory=dict)
    interaction_effects: dict = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)


class UserLearningImpactSimulationRequest(BaseModel):
    symbol: str | None = None
    strategy_id: str | None = None
    family: str | None = None
    recommendation_type: str = "decrease_weight_recommendation"
    suggested_weight_multiplier: float | None = Field(default=None, ge=0.1, le=3.0)


class UserLearningSuggestionCreateRequest(BaseModel):
    symbol: str | None = None
    strategy_id: str | None = None
    family: str | None = None
    recommendation_type: str
    simulation_payload: dict = Field(default_factory=dict)
    note: str = ""


class UserLearningSuggestionResponse(BaseModel):
    id: str
    user_id: str
    symbol: str | None = None
    strategy_id: str | None = None
    family: str | None = None
    recommendation_type: str
    simulation_payload: dict = Field(default_factory=dict)
    note: str = ""
    status: str
    created_at: datetime


class PortfolioRiskLimitsResponse(BaseModel):
    max_portfolio_leverage: float
    max_symbol_exposure: float
    max_cluster_exposure: float
    max_strategy_exposure: float
    max_single_trade_risk: float
    max_intraday_drawdown: float
    max_total_drawdown: float


class PortfolioRiskLimitsUpdate(BaseModel):
    max_portfolio_leverage: float = Field(gt=0)
    max_symbol_exposure: float = Field(gt=0)
    max_cluster_exposure: float = Field(gt=0)
    max_strategy_exposure: float = Field(gt=0)
    max_single_trade_risk: float = Field(gt=0)
    max_intraday_drawdown: float = Field(gt=0)
    max_total_drawdown: float = Field(gt=0)


class RiskClusterUpsertRequest(BaseModel):
    cluster_id: str
    symbols: list[str]
    cluster_type: str
    correlation_score: float
    risk_weight: float = Field(gt=0)


class RiskClusterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cluster_id: str
    symbols: list[str]
    cluster_type: str
    correlation_score: float
    risk_weight: float
    updated_at: datetime


class StrategyAllocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_id: str
    capital_weight: float
    max_capital: float
    current_capital: float
    confidence_score: float
    performance_score: float
    state: str
    expected_return: float
    realized_return: float
    signal_decay: float
    execution_quality_score: float
    revision_id: int = 1
    updated_by: str | None = None
    change_reason: str | None = None
    updated_at: datetime
    state_reason_code: str | None = None
    state_reason_detail: str | None = None
    is_drift_override: bool = False
    drawdown_pct: float = 0
    exposure_ratio_pct: float = 0
    suggested_reduced_capital: float = 0
    is_auto_reduce_candidate: bool = False
    trend_5d_line: str = "5g trend unavailable"
    trend_5d_available: bool = False


class StrategyAllocationSummaryItem(BaseModel):
    strategy_id: str
    current_capital: float
    max_capital: float
    overflow: float


class StrategyAllocationDrawdownCandidate(BaseModel):
    strategy_id: str
    drawdown_pct: float
    current_capital: float
    suggested_reduced_capital: float
    enforced_required: bool
    reason_code: str


class StrategyAllocationSummaryResponse(BaseModel):
    total_strategies: int
    total_weight: float
    weight_balance_delta: float
    total_capital: float
    used_capital: float
    available_capital: float
    over_allocated_count: int
    over_allocated_strategies: list[StrategyAllocationSummaryItem] = Field(default_factory=list)
    total_exposure_ratio_pct: float = 0
    exposure_warning_threshold_pct: float = 80
    exposure_warning_state: str = "NORMAL"
    drawdown_threshold_pct: float = 8
    drawdown_enforce_threshold_pct: float = 12
    drawdown_candidates: list[StrategyAllocationDrawdownCandidate] = Field(default_factory=list)


class StrategyAllocationUpdateRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    capital_weight: float | None = Field(default=None, ge=0, le=1)
    max_capital: float | None = Field(default=None, ge=0)
    current_capital: float | None = Field(default=None, ge=0)
    state: str | None = None
    reason_note: str | None = None
    confirm_primary: str | None = None
    confirm_secondary: str | None = None


class StrategyAllocationCreateRequest(BaseModel):
    strategy_id: str
    capital_weight: float = Field(default=0, ge=0, le=1)
    max_capital: float = Field(default=0, ge=0)
    current_capital: float = Field(default=0, ge=0)
    state: str = "ACTIVE"
    reason_note: str | None = None


class StrategyAllocationBulkUpdateItem(BaseModel):
    strategy_id: str
    expected_revision: int = Field(ge=1)
    capital_weight: float | None = Field(default=None, ge=0, le=1)
    max_capital: float | None = Field(default=None, ge=0)
    current_capital: float | None = Field(default=None, ge=0)
    state: str | None = None
    confirm_primary: str | None = None
    confirm_secondary: str | None = None


class StrategyAllocationBulkUpdateRequest(BaseModel):
    updates: list[StrategyAllocationBulkUpdateItem]
    auto_normalize: bool = False
    reason_note: str | None = None


class StrategyAllocationThrottleToggleRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    confirm_primary: str
    confirm_secondary: str
    reason_note: str | None = None


class StrategyAllocationReasonNoteRequest(BaseModel):
    reason_note: str


class StrategyAllocationNormalizeRequest(BaseModel):
    reason_note: str
    expected_revisions: dict[str, int] = Field(default_factory=dict)


class StrategyAllocationStateHistoryEntry(BaseModel):
    trace_id: str
    strategy_id: str
    action_type: str
    previous_state: str | None = None
    new_state: str | None = None
    reason_code: str | None = None
    reason_detail: str | None = None
    admin_id: str
    timestamp: datetime


class StrategyAllocationStateHistoryResponse(BaseModel):
    rows: list[StrategyAllocationStateHistoryEntry] = Field(default_factory=list)


class StrategyAllocationActionEnvelope(BaseModel):
    status: str
    message: str
    trace_id: str
    summary: StrategyAllocationSummaryResponse | None = None


class StrategyAllocationRebalanceSuggestRequest(BaseModel):
    strategy_ids: list[str] = Field(default_factory=list)


class StrategyAllocationRebalanceSuggestionRow(BaseModel):
    strategy_id: str
    current_weight: float
    suggested_weight: float
    delta: float
    confidence: float
    performance_norm: float
    decay: float
    score: float


class StrategyAllocationRebalanceSuggestionResponse(BaseModel):
    status: str
    message: str
    trace_id: str
    selection_count: int = 0
    applied_budget: float = 0
    suggestions: list[StrategyAllocationRebalanceSuggestionRow] = Field(default_factory=list)


class StrategyAllocationSnapshotItem(BaseModel):
    snapshot_id: str
    created_at: datetime
    created_by: str
    reason_note: str
    strategy_count: int
    total_weight: float
    total_capital: float
    used_capital: float
    source_request_id: str | None = None
    restored_at: datetime | None = None
    restored_by: str | None = None


class StrategyAllocationSnapshotsResponse(BaseModel):
    rows: list[StrategyAllocationSnapshotItem] = Field(default_factory=list)


class StrategyAllocationSnapshotCreateResponse(BaseModel):
    status: str
    message: str
    snapshot: StrategyAllocationSnapshotItem | None = None
    trace_id: str


class StrategyAllocationSnapshotRestoreRequest(BaseModel):
    reason_note: str
    expected_revisions: dict[str, int] = Field(default_factory=dict)


class StrategyAllocationRevertRequest(BaseModel):
    reason_note: str


class StrategyAllocationWhatIfRequest(BaseModel):
    strategy_ids: list[str] = Field(default_factory=list)


class StrategyAllocationWhatIfRow(BaseModel):
    strategy_id: str
    current_weight: float
    suggested_weight: float
    weight_delta: float
    confidence: float
    performance_norm: float
    decay: float
    projected_return_delta_pct: float
    projected_risk_delta_pct: float


class StrategyAllocationWhatIfResponse(BaseModel):
    status: str
    message: str
    trace_id: str
    read_only: bool = True
    selection_count: int = 0
    projected_portfolio_return_delta_pct: float = 0
    projected_portfolio_risk_delta_pct: float = 0
    rows: list[StrategyAllocationWhatIfRow] = Field(default_factory=list)


class StrategyAllocationApprovalRequestItem(BaseModel):
    request_id: str
    request_type: str | None = None
    action_type: str
    target_type: str | None = None
    target_id: str | None = None
    status: str
    requested_by: str
    requested_role: str | None = None
    reason_note: str
    created_at: datetime
    requested_at: datetime | None = None
    expires_at: datetime
    payload: dict = Field(default_factory=dict)
    revision_context: dict = Field(default_factory=dict)
    stale_state: str | None = None
    stale_reason_code: str | None = None
    stale_conflicts: list[dict] = Field(default_factory=list)
    review_note: str | None = None
    reviewed_at: datetime | None = None
    explanation_summary: str = ""
    decision_factors: dict = Field(default_factory=dict)
    previous_state_snapshot: dict = Field(default_factory=dict)
    source_request_id: str | None = None
    linked_revert_request_id: str | None = None
    reverted_at: datetime | None = None
    reverted_by: str | None = None
    revert_reason: str | None = None


class StrategyAllocationApprovalRequestsResponse(BaseModel):
    rows: list[StrategyAllocationApprovalRequestItem] = Field(default_factory=list)



class CanonicalStrategyRegistryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_id: str
    strategy_family: str
    direction: str
    market_regime: str
    entry_logic_version: str
    exit_logic_version: str
    risk_profile: str
    is_enabled: bool
    priority: int
    cooldown_policy: str
    weight: float
    entry_long: dict = Field(default_factory=dict)
    entry_short: dict = Field(default_factory=dict)
    exit_long: dict = Field(default_factory=dict)
    exit_short: dict = Field(default_factory=dict)
    stop_loss: dict = Field(default_factory=dict)
    take_profit: dict = Field(default_factory=dict)
    invalidation: dict = Field(default_factory=dict)
    signal_score: dict = Field(default_factory=dict)
    invalid_state_rules: list[str] = Field(default_factory=list)
    cooldown_rules: dict = Field(default_factory=dict)
    risk_rules: dict = Field(default_factory=dict)
    is_legacy_candidate: bool = False
    in_production_path: bool = True
    last_50_signal_quality: float = 0
    false_allow_rate: float = 0
    false_reject_rate: float = 0
    cooldown_state: str = "ready"
    risk_block_reason: str | None = None
    forced_disable_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class CanonicalStrategyRegistryUpdateRequest(BaseModel):
    direction: str | None = None
    market_regime: str | None = None
    is_enabled: bool | None = None
    priority: int | None = None
    cooldown_policy: str | None = None
    weight: float | None = Field(default=None, ge=0)
    risk_profile: str | None = None
    forced_disable_reason: str | None = None


class StrategyFamilyGateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    schema_version: str = "sprint3.v1"
    engine_version: str = "canonical-engine.v3"
    generated_at: datetime | None = None
    family: str
    is_enabled: bool
    long_threshold: float
    short_threshold: float
    min_strategy_count: int
    max_conflict_score: float
    regime_match_required: bool
    risk_clear_required: bool
    reversal_extra_confirmation: bool
    created_at: datetime
    updated_at: datetime


class StrategyFamilyGateUpdateItem(BaseModel):
    family: str
    is_enabled: bool | None = None
    long_threshold: float | None = Field(default=None, ge=0)
    short_threshold: float | None = Field(default=None, ge=0)
    min_strategy_count: int | None = Field(default=None, ge=1)
    max_conflict_score: float | None = Field(default=None, ge=0)
    regime_match_required: bool | None = None
    risk_clear_required: bool | None = None
    reversal_extra_confirmation: bool | None = None


class StrategyFamilyGateBulkUpdateRequest(BaseModel):
    items: list[StrategyFamilyGateUpdateItem] = Field(default_factory=list)


class DecisionCardStrategyContribution(BaseModel):
    strategy_id: str
    family: str
    direction: str
    raw_signal: str
    normalized_score: float
    weight: float
    contribution_score: float
    status: str


class DecisionCardResponse(BaseModel):
    schema_version: str
    engine_version: str
    generated_at: datetime
    symbol: str
    market_regime: str
    decision: str
    confidence: float
    long_score: float
    short_score: float
    dominant_family: str | None = None
    supporting_families: list[str] = Field(default_factory=list)
    top_contributors: list[DecisionCardStrategyContribution] = Field(default_factory=list)
    top_strategies: list[DecisionCardStrategyContribution] = Field(default_factory=list)
    entry_zone: dict = Field(default_factory=dict)
    stop_loss: float | None = None
    take_profit_1: float | None = None
    take_profit_2: float | None = None
    invalidation: dict = Field(default_factory=dict)
    blocked_reason: str | None = None
    block_category: str | None = None
    cooldown_remaining: int = 0
    risk_block: str | None = None
    risk_state: dict = Field(default_factory=dict)
    confidence_adjustment: float = 0
    learning_badges: list[str] = Field(default_factory=list)
    learning_quality_score: float | None = None
    updated_at: datetime


class DecisionCardEnvelopeResponse(BaseModel):
    schema_version: str
    engine_version: str
    generated_at: datetime
    items: list[DecisionCardResponse] = Field(default_factory=list)


class SymbolExplainabilityResponse(BaseModel):
    schema_version: str
    engine_version: str
    generated_at: datetime
    symbol: str
    final_decision: str
    long_score: float
    short_score: float
    winning_side: str
    decision_confidence: float
    source_strategies: list[DecisionCardStrategyContribution] = Field(default_factory=list)
    family_scores: dict = Field(default_factory=dict)
    blocked_reason_current: str | None = None
    blocked_reason_timeline: list[dict] = Field(default_factory=list)
    risk_state: dict = Field(default_factory=dict)
    cooldown_state: dict = Field(default_factory=dict)
    regime_state: dict = Field(default_factory=dict)
    explanation_templates: list[str] = Field(default_factory=list)


class BlockedReasonTimelineEnvelopeResponse(BaseModel):
    schema_version: str
    engine_version: str
    generated_at: datetime
    symbol: str
    items: list[dict] = Field(default_factory=list)



class AdminExecutionQueueDecisionRequest(BaseModel):
    note: str = ""
    reason: str = ""
    read_acknowledged: bool = False
    double_confirmation: bool = False
    execute_confirmation: bool = False
    override_execute: bool = False
    detail_version: str | None = None


class AdminExecutionQueueDecisionResponse(BaseModel):
    intent_id: str
    status: str
    admin_note: str
    execution_mode: str = "live"
    detail_version: str | None = None


class ExecutionIntentHistoryItemResponse(BaseModel):
    id: str
    action: str
    actor_user_id: str | None = None
    actor_role: str | None = None
    reason: str | None = None
    details: dict = Field(default_factory=dict)
    created_at: datetime


class ExecutionIntentDetailResponse(BaseModel):
    intent_id: str
    detail_version: str
    order_preview: dict = Field(default_factory=dict)
    normalized_payload: dict = Field(default_factory=dict)
    intent_metadata: dict = Field(default_factory=dict)
    risk_payload: dict = Field(default_factory=dict)
    gate_decision: dict = Field(default_factory=dict)
    expected_impact: dict = Field(default_factory=dict)


class AdminExecutionQueueBulkDecisionRequest(BaseModel):
    intent_ids: list[str] = Field(default_factory=list)
    action: str
    reason: str = ""
    read_acknowledged: bool = False
    double_confirmation: bool = False


class AdminExecutionQueueBulkDecisionResponse(BaseModel):
    action: str
    processed_count: int
    failed_count: int
    processed_intent_ids: list[str] = Field(default_factory=list)
    failures: list[dict] = Field(default_factory=list)


class AdminExecutionQueueControlRequest(BaseModel):
    reason: str = ""


class AdminExecutionQueueControlResponse(BaseModel):
    paused: bool
    paused_by: str | None = None
    paused_reason: str | None = None
    paused_at: str | None = None
    updated_at: str | None = None


class AdminExecutionQueueEditRequest(BaseModel):
    notional: float | None = None
    size: float | None = None
    price: float | None = None
    stop_price: float | None = None
    take_profit_price: float | None = None
    reason: str = ""


class AdminExecutionQueueEditResponse(BaseModel):
    intent_id: str
    status: str
    diff: dict = Field(default_factory=dict)
    detail_version: str | None = None


class ExecutionDecisionGateConfigResponse(BaseModel):
    execution_decision_gate_enforced: bool = True
    thresholds: dict = Field(default_factory=dict)


class ExecutionDecisionGateConfigUpdateRequest(BaseModel):
    execution_decision_gate_enforced: bool | None = None
    thresholds: dict = Field(default_factory=dict)


class AdminExecutionIntentOwnerRevalidateResponse(BaseModel):
    intent_id: str
    owner_user_id: str
    connection_id: str
    can_trade: bool
    reason_codes: list[str] = Field(default_factory=list)
    connection_health: str = "unknown"
    readiness_status: str = "unknown"
    response_code: int = 200


class ExecutionReadinessResponse(BaseModel):
    exchange_connection: str
    permissions: str
    latency_ms: int
    order_test: str
    mode: str
    final_status: str
    mocked_flag: bool = False
    override_active: bool = False
    reason_codes: list[str] = Field(default_factory=list)
    execution_proof: dict = Field(default_factory=dict)
    mocked_paths: bool = False
    readiness_state: str | None = None
    execution_allowed: bool | None = None
    go_live_allowed: bool | None = None


class GuardTelemetryReasonResponse(BaseModel):
    reason: str
    count: int


class GuardTelemetryResponse(BaseModel):
    blocked_24h: int = 0
    override_24h: int = 0
    top_reasons: list[GuardTelemetryReasonResponse] = Field(default_factory=list)


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
    supports_live: bool = True
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
    live_allowed: bool
    updated_at: datetime


class UserVenueAssignmentUpdate(BaseModel):
    user_id: str
    exchange_code: str
    spot_allowed: bool
    futures_allowed: bool
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
    market_type: str = "spot"
    mode: str = "live"
    api_key: str
    api_secret: str


class ExchangeSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    exchange: str
    mode: str
    has_api_key: bool
    has_api_secret: bool
    updated_at: datetime | None


class AdminExchangeCredentialCreateRequest(BaseModel):
    scope_type: str = "global"
    scope_id: str | None = None
    exchange: str = "binance"
    market_type: str = "spot"
    purpose: str = "market_data"
    environment: str = "live"
    api_key: str
    api_secret: str
    passphrase: str | None = None
    base_url_override: str | None = None
    ip_binding_note: str | None = None
    is_default: bool = False


class AdminExchangeCredentialPatchRequest(BaseModel):
    scope_type: str | None = None
    scope_id: str | None = None
    purpose: str | None = None
    api_key: str | None = None
    api_secret: str | None = None
    passphrase: str | None = None
    base_url_override: str | None = None
    ip_binding_note: str | None = None
    is_default: bool | None = None
    is_active: bool | None = None


class AdminExchangeCredentialRotateRequest(BaseModel):
    api_key: str
    api_secret: str
    passphrase: str | None = None


class AdminExchangeCredentialResponse(BaseModel):
    id: str
    scope_type: str
    scope_id: str | None = None
    exchange: str
    market_type: str
    purpose: str
    environment: str
    base_url_override: str | None = None
    ip_binding_note: str | None = None
    is_active: bool
    is_default: bool
    approval_status: str
    approved_by: str | None = None
    approved_at: datetime | None = None
    created_by: str | None = None
    updated_by: str | None = None
    has_api_key: bool
    has_api_secret: bool
    masked_api_key: str
    credential_fingerprint: str
    last_probe_status: str | None = None
    last_probe_message: str | None = None
    last_probe_meta: dict = Field(default_factory=dict)
    permission_scope: dict = Field(default_factory=dict)
    permission_scope_validation: dict = Field(default_factory=dict)
    lifecycle_status: str = "pending"
    secret_provider: str = "local"
    last_probe_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CredentialAssignmentRuleUpsertRequest(BaseModel):
    exchange: str = "binance"
    market_type: str = "spot"
    environment: str = "live"
    tenant_id: str | None = None
    user_id: str | None = None
    preferred_source: str = "user"
    fallback_enabled: bool = False


class CredentialAssignmentRuleResponse(BaseModel):
    id: str
    exchange: str
    market_type: str
    environment: str
    tenant_id: str | None = None
    user_id: str | None = None
    preferred_source: str
    fallback_enabled: bool
    updated_by: str | None = None
    created_at: datetime
    updated_at: datetime


class CredentialResolutionPreviewResponse(BaseModel):
    request_id: str
    resolved_at: str
    selected_credential_id: str
    source: str
    masked_api_key: str
    masked_fingerprint: str
    exchange: str
    market_type: str
    environment: str
    purpose: str
    fallback_chain: list[str] = Field(default_factory=lambda: ["user", "tenant_admin", "global_admin"])
    selected_probe_status: str | None = None
    selected_probe_message: str | None = None
    effective_base_url: str | None = None
    audit_metadata: dict = Field(default_factory=dict)


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
    reason_codes: list[str] = Field(default_factory=list)
    blocking_metrics: dict = Field(default_factory=dict)
    live_activation: str
    environment: str | None = None
    reason_code: str | None = None
    deploy_enable_flag: bool = False
    override_active: bool = False
    override_expires_at: datetime | None = None
    override_id: str | None = None


class ProdConfigFieldStatusResponse(BaseModel):
    key: str
    source: str
    present: bool
    editable: bool
    masked_value: str
    validation_error: str | None = None


class ProdConfigRemediationItemResponse(BaseModel):
    code: str
    title: str
    current_state: str
    expected_state: str
    target_field: str | None = None
    check_action: str


class ProdConfigCheckResultResponse(BaseModel):
    check_name: str
    status: str
    artifact_path: str
    detail: str | None = None


class ProdConfigRemediationStateResponse(BaseModel):
    release_gate_status: str
    release_gate_reason_codes: list[str] = Field(default_factory=list)
    deploy_enable_allowed: bool
    remediation_allowed: bool
    fields: list[ProdConfigFieldStatusResponse] = Field(default_factory=list)
    remediation_items: list[ProdConfigRemediationItemResponse] = Field(default_factory=list)
    preflight_status: str = "UNKNOWN"
    secret_readiness_status: str = "UNKNOWN"
    final_release_gate_decision: str = "UNKNOWN"
    checks: list[ProdConfigCheckResultResponse] = Field(default_factory=list)


class ProdConfigSaveRequest(BaseModel):
    database_url: str | None = None
    redis_url: str | None = None
    jwt_secret: str | None = None
    exchange_credentials_encryption_key: str | None = None
    admin_bootstrap_email: str | None = None
    admin_bootstrap_password: str | None = None
    react_app_backend_url: str | None = None
    resend_api_key: str | None = None
    alert_from: str | None = None
    alert_to: str | None = None


class ProdConfigSaveResponse(BaseModel):
    status: str
    changed_keys: list[str] = Field(default_factory=list)
    validation_errors: dict[str, str] = Field(default_factory=dict)


class ProdConfigRunCheckResponse(BaseModel):
    status: str
    artifact_path: str
    check_name: str
    summary: dict = Field(default_factory=dict)


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


class ProductionGateChecklistItemResponse(BaseModel):
    item_key: str
    title: str
    required: bool = True
    checked: bool = False
    updated_at: datetime | None = None
    updated_by_user_id: str | None = None


class ProductionGateCheckItemResponse(BaseModel):
    check_key: str
    title: str
    status: str
    blocking: bool
    fail_reason: str | None = None
    remediation: str | None = None
    remediation_payload: dict = Field(default_factory=dict)
    last_run_at: datetime | None = None
    stale: bool = False
    flapping_detail: dict = Field(default_factory=dict)


class ProductionGateOverrideSummaryResponse(BaseModel):
    override_id: str
    reason_code: str
    reason_text: str
    expires_at: datetime
    created_at: datetime
    revoked_at: datetime | None = None
    created_by_user_id: str


class ProductionGateAuditItemResponse(BaseModel):
    id: str
    action: str
    severity: str
    actor_user_id: str | None = None
    actor_role: str
    details: dict = Field(default_factory=dict)
    created_at: datetime


class ProductionGateStatusResponse(BaseModel):
    configured_state: str
    effective_state: str
    deploy_allowed: bool
    checklist_complete: bool
    checks_all_pass: bool
    has_stale_or_running: bool
    blocked_reason_codes: list[str] = Field(default_factory=list)
    blocked_reason_text: str | None = None
    release_gate_contract: str = "UNKNOWN"
    validation_block_http_status: int = 400
    deploy_block_http_status: int = 403
    checklist: list[ProductionGateChecklistItemResponse] = Field(default_factory=list)
    checks: list[ProductionGateCheckItemResponse] = Field(default_factory=list)
    active_override: ProductionGateOverrideSummaryResponse | None = None
    risk_score: int = 0
    risk_level: str = "LOW"
    risk_factors: dict = Field(default_factory=dict)
    risk_explanation: list[str] = Field(default_factory=list)
    risk_model_version: str = "v2-explainable"
    flapping_checks: list[str] = Field(default_factory=list)
    policy_bypass_applied: bool = False
    policy_blocking_mode: str = "FULL"
    updated_at: datetime
    updated_by_user_id: str | None = None
    audit_history: list[ProductionGateAuditItemResponse] = Field(default_factory=list)


class ProductionGateChecklistUpdateRequest(BaseModel):
    checked: bool


class ProductionGateStateUpdateRequest(BaseModel):
    target_state: str = Field(pattern="^(NO_GO|GO)$")
    reason_code: str = Field(min_length=2, max_length=80)
    reason_text: str = Field(min_length=5, max_length=600)


class ProductionGateOverrideCreateRequest(BaseModel):
    reason_code: str = Field(
        pattern="^(INCIDENT_MITIGATION|THIRD_PARTY_DEGRADATION|HOTFIX_VALIDATED|MANUAL_RISK_ACCEPTANCE)$"
    )
    reason_text: str = Field(min_length=12, max_length=1000)
    ttl_minutes: int = Field(default=30, ge=1, le=30)


class ProductionGateModeTransitionRequest(BaseModel):
    target_mode: str = Field(pattern="^(LIVE|SIM|PAPER|MOCK)$")
    reason_text: str = Field(min_length=8, max_length=600)
    confirmation_phrase: str = Field(min_length=5, max_length=80)


class LiveGateWizardProgressUpdateRequest(BaseModel):
    completed_step_ids: list[int] = Field(default_factory=list)


class LiveGateWizardProgressResponse(BaseModel):
    user_id: str
    completed_step_ids: list[int] = Field(default_factory=list)
    updated_at: datetime


class ProductionGateExportResponse(BaseModel):
    exported_at: datetime
    gate: ProductionGateStatusResponse


class ProductionGateApiKeyTestResultResponse(BaseModel):
    exchange: str
    market_type: str
    environment: str
    connection_id: str
    status: str
    success: bool
    fail_reason: str | None = None
    response_summary: dict = Field(default_factory=dict)
    runbook_ref: str | None = None
    remediation: str | None = None
    last_tested_at: datetime


class ProductionGatePermissionBreakdownItemResponse(BaseModel):
    exchange: str
    market_type: str
    environment: str
    read_status: str
    write_status: str
    trade_status: str
    reason_codes: list[str] = Field(default_factory=list)
    fail_reason: str | None = None
    remediation: str | None = None
    runbook_ref: str | None = None
    last_checked_at: datetime | None = None


class ProductionGateExchangeHealthItemResponse(BaseModel):
    exchange: str
    market_type: str
    environment: str
    connection_status: str
    auth_status: str
    permission_status: str
    fail_reason: str | None = None
    remediation: str | None = None
    runbook_ref: str | None = None
    last_checked_at: datetime | None = None


class ProductionGateModeHistoryItemResponse(BaseModel):
    changed_at: datetime
    actor_user_id: str | None = None
    actor_role: str
    from_mode: str
    to_mode: str
    reason: str | None = None
    request_id: str | None = None
    trace_id: str | None = None


class ProductionGateOrderScenarioItemResponse(BaseModel):
    scenario_key: str
    label: str
    side: str
    size_bucket: str
    status: str
    latency_ms: float | None = None
    response_summary: str | None = None
    error_summary: str | None = None
    last_run_at: datetime | None = None


class ProductionGateOpsOverviewResponse(BaseModel):
    active_fail_count: int
    active_fail_codes: list[str] = Field(default_factory=list)
    risk_score: int = 0
    risk_level: str = "LOW"
    api_key_tests: list[ProductionGateApiKeyTestResultResponse] = Field(default_factory=list)
    permission_breakdown: list[ProductionGatePermissionBreakdownItemResponse] = Field(default_factory=list)
    exchange_health: list[ProductionGateExchangeHealthItemResponse] = Field(default_factory=list)
    mode_history: list[ProductionGateModeHistoryItemResponse] = Field(default_factory=list)
    order_scenarios: list[ProductionGateOrderScenarioItemResponse] = Field(default_factory=list)


class ProductionGateApiKeyTestRunRequest(BaseModel):
    connection_id: str | None = None
    exchange: str | None = None


class ProductionGateOrderScenarioRunRequest(BaseModel):
    scenario_key: str | None = None


class ProductionGateCheckHistoryItemResponse(BaseModel):
    check_key: str
    status: str
    timestamp: datetime
    latency_ms: float | None = None
    error_code: str | None = None
    run_id: str
    flapping: bool = False
    flapping_detail: dict = Field(default_factory=dict)


class ProductionGateCheckHistoryResponse(BaseModel):
    items: list[ProductionGateCheckHistoryItemResponse] = Field(default_factory=list)
    trend_summary: dict = Field(default_factory=dict)
    flapping_checks: list[str] = Field(default_factory=list)
    flapping_config: dict = Field(default_factory=dict)


class ProductionGateCheckCompareItemResponse(BaseModel):
    check_key: str
    run_id: str
    timestamp: datetime
    previous_result: str
    new_result: str
    previous_latency_ms: float | None = None
    new_latency_ms: float | None = None
    latency_delta_ms: float | None = None
    state_delta: str
    run_count: int = 0
    improvement: bool = False
    fail_to_pass: bool = False
    stability_score: float = 0.0
    explanation: list[str] = Field(default_factory=list)


class ProductionGateCheckCompareResponse(BaseModel):
    items: list[ProductionGateCheckCompareItemResponse] = Field(default_factory=list)


class ProductionGateOverrideAnalyticsResponse(BaseModel):
    override_count: int
    override_rate: float
    reason_distribution: dict = Field(default_factory=dict)
    top_override_checks: list[dict] = Field(default_factory=list)
    expiry_count: int
    revoke_count: int
    expiry_vs_revoke_ratio: dict = Field(default_factory=dict)
    timeline: list[dict] = Field(default_factory=list)


class ProductionGateTimelineEventResponse(BaseModel):
    audit_id: str
    request_id: str | None = None
    event_type: str
    category: str
    timestamp: datetime
    title: str
    details: dict = Field(default_factory=dict)


class ProductionGateTimelineResponse(BaseModel):
    items: list[ProductionGateTimelineEventResponse] = Field(default_factory=list)


class CapabilityDiscoveryRequest(BaseModel):
    exchange_code: str
    market_type: str = "spot"
    environment: str = "live"
    symbols: list[str] = Field(default_factory=list)


class MarketPolicyLayerUpdateRequest(BaseModel):
    exchange_code: str
    market_type: str
    environment: str = "live"
    symbol_rules: list[dict] = Field(default_factory=list)
    restricted_symbol_classes: list[str] = Field(default_factory=list)
    risk_tier_defaults: dict = Field(default_factory=dict)


class RoutingPolicyUpsertRequest(BaseModel):
    user_id: str
    strategy_id: str
    default_venue: str | None = None
    preferred_venues: list[str] = Field(default_factory=list)
    blocked_venues: list[str] = Field(default_factory=list)
    capital_allocation: list[dict] = Field(default_factory=list)
    execution_policy_override: dict = Field(default_factory=dict)


class RoutingPreviewRequest(BaseModel):
    user_id: str
    strategy_id: str
    symbol: str
    market_type: str
    environment: str
    order_side: str = "BUY"
    order_size_usd: float = 0


class CapabilityMatrixOverrideRequest(BaseModel):
    exchange_code: str
    market_type: str
    environment: str = "live"
    symbol: str
    support_level: str | None = None
    supports_leverage: bool | None = None
    supports_reduce_only: bool | None = None
    supports_margin_mode: bool | None = None
    supports_hedge_mode: bool | None = None
    note: str | None = None


class FailoverAutoTriggerThresholds(BaseModel):
    latency_ms: float = 1200
    error_rate_pct: float = 20
    validation_failure_pct: float = 25


class FailoverManualOverridePayload(BaseModel):
    force_route: str | None = None
    force_disable: list[str] = Field(default_factory=list)
    reason: str | None = None


class FailoverPolicyUpsertRequest(BaseModel):
    user_id: str
    strategy_id: str
    market_type: str
    environment: str = "live"
    primary_venue: str
    secondary_venue: str | None = None
    fallback_chain: list[str] = Field(default_factory=list)
    auto_reroute_enabled: bool = True
    auto_trigger_thresholds: FailoverAutoTriggerThresholds = Field(default_factory=FailoverAutoTriggerThresholds)
    manual_override: FailoverManualOverridePayload | None = None


class FailoverManualOverrideRequest(BaseModel):
    user_id: str
    strategy_id: str
    market_type: str
    environment: str = "live"
    force_route: str | None = None
    force_disable: list[str] = Field(default_factory=list)
    reason: str | None = None
    clear_override: bool = False


class ValidationCenterRerunRequest(BaseModel):
    user_id: str | None = None
    strategy_id: str | None = None
    market_type: str | None = None
    environment: str = "live"


class ConflictAutoRemediationApplyRequest(BaseModel):
    reason_code: str
    entity_id: str
    mode: str = "dry_run"
    approval_request_id: str | None = None
    comment: str | None = None

