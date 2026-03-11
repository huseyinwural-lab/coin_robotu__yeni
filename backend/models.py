import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
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