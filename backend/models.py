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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
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