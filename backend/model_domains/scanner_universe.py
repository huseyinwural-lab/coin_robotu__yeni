import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from model_domains.shared import utcnow

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
    current_stage: Mapped[str] = mapped_column(String(40), default="full_market")
    recommended_stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    recommendation_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    requires_admin_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    approved_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class ScannerFallbackEvent(Base):
    __tablename__ = "scanner_fallback_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(20), index=True)  # trigger | exit
    requested_mode: Mapped[str] = mapped_column(String(40), default="all_market_symbols")
    effective_mode: Mapped[str] = mapped_column(String(40), default="all_market_symbols")
    trigger_metric: Mapped[str | None] = mapped_column(String(80), nullable=True)
    threshold_breach: Mapped[dict] = mapped_column(JSON, default=dict)
    exit_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cycle_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

