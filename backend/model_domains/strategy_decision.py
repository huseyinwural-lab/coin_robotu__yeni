import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from model_domains.shared import utcnow

class BotProfile(Base):
    __tablename__ = "bot_profiles"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    exchange: Mapped[str] = mapped_column(String(50), default="binance")
    market_type: Mapped[str] = mapped_column(String(20), default="spot")
    symbol_source_type: Mapped[str] = mapped_column(String(20), default="manual")
    scanner_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    symbols: Mapped[list[str]] = mapped_column(JSON, default=list)
    symbol_resolution_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    strategy_type: Mapped[str] = mapped_column(String(50), default="trend_following")
    strategy_template_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    timeframe: Mapped[str] = mapped_column(String(10), default="15m")
    trend_timeframe: Mapped[str] = mapped_column(String(10), default="1h")
    leverage: Mapped[int] = mapped_column(Integer, default=3)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_running: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
    strategy_version_id: Mapped[str | None] = mapped_column(String, ForeignKey("strategy_versions.version_id"), nullable=True, index=True)
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

class StrategyDefinition(Base):
    __tablename__ = "strategy_definitions"

    strategy_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(120), index=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    owner_type: Mapped[str] = mapped_column(String(20), default="admin")
    owner_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)
    owner_name: Mapped[str] = mapped_column(String(120), default="ops")
    category: Mapped[str] = mapped_column(String(80), default="general", index=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    active_version_id: Mapped[str | None] = mapped_column(String, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
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


class StrategyVersionLifecycle(Base):
    __tablename__ = "strategy_version_lifecycle"

    lifecycle_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id: Mapped[str] = mapped_column(String, ForeignKey("strategy_definitions.strategy_id"), index=True)
    strategy_version_id: Mapped[str] = mapped_column(String, ForeignKey("strategy_versions.version_id"), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_production: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    lifecycle_state: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    validation_status: Mapped[str] = mapped_column(String(20), default="pending")
    validation_errors_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    compatibility_status: Mapped[str] = mapped_column(String(20), default="pending")
    compatibility_report_json: Mapped[dict] = mapped_column(JSON, default=dict)
    dry_run_status: Mapped[str] = mapped_column(String(20), default="pending")
    dry_run_report_json: Mapped[dict] = mapped_column(JSON, default=dict)
    rollout_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rolled_back_from_version_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class StrategyPromotionRequest(Base):
    __tablename__ = "strategy_promotion_requests"

    request_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id: Mapped[str] = mapped_column(String, ForeignKey("strategy_definitions.strategy_id"), index=True)
    strategy_version_id: Mapped[str] = mapped_column(String, ForeignKey("strategy_versions.version_id"), index=True)
    requested_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    requested_role: Mapped[str] = mapped_column(String(40), default="admin")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    request_note: Mapped[str] = mapped_column(Text, default="")
    approval_note: Mapped[str] = mapped_column(Text, default="")
    require_validation: Mapped[bool] = mapped_column(Boolean, default=True)
    require_dry_run: Mapped[bool] = mapped_column(Boolean, default=True)
    requested_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)
    rejected_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: utcnow() + timedelta(hours=24), index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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
