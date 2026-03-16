import enum
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from model_domains.shared import utcnow

class ReplayRun(Base):
    __tablename__ = "replay_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    exchange: Mapped[str] = mapped_column(String(30), default="binance")
    market_type: Mapped[str] = mapped_column(String(20), default="futures")
    environment: Mapped[str] = mapped_column(String(20), default="testnet")
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
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
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
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
