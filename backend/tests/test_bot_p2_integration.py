# ruff: noqa: E402
import sys
import uuid
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.security import hash_password
from db import SessionLocal
from models import BotProfile, User, UserExchangeConnection, UserRole
from services.bot_runtime_service import aggregate_bot_portfolio_control, start_bot_runtime
from services.unified_control_room_service import build_unified_control_room


def _seed_user(db):
    user = User(
        email=f"bot-p2-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("Pass1234!Aa"),
        role=UserRole.USER,
        is_active=True,
        approval_status="approved",
    )
    db.add(user)
    db.flush()
    db.add(
        UserExchangeConnection(
            user_id=user.id,
            account_label="default",
            exchange="binance",
            market_type="spot",
            environment="paper",
            is_default=True,
            readiness_snapshot={"connection_health": "online", "can_trade": True},
            permission_snapshot=["trade"],
            api_key_encrypted="x",
            api_secret_encrypted="y",
        )
    )
    db.commit()
    db.refresh(user)
    return user


def test_bot_portfolio_control_and_unified_room_embed():
    db = SessionLocal()
    try:
        user = _seed_user(db)
        for name, symbol in [("Bot A", ["BTCUSDT"]), ("Bot B", ["ETHUSDT"])]:
            bot = BotProfile(user_id=user.id, name=name, exchange="binance", market_type="spot", symbol_source_type="manual", symbols=symbol, strategy_type="trend_following", timeframe="15m", trend_timeframe="1h", leverage=1, is_enabled=True)
            db.add(bot)
            db.commit()
            db.refresh(bot)
            start_bot_runtime(db, bot=bot, actor_id=user.id)

        portfolio = aggregate_bot_portfolio_control(db, user_id=user.id)
        control_room = build_unified_control_room(db, user_id=user.id, window="7d")

        assert "allocator" in portfolio
        assert isinstance(portfolio["allocator"], list)
        assert "bots_overview" in control_room["live_operations"]
        assert "bot_portfolio_control" in control_room["risk_market_context"]["capital_pressure"]
    finally:
        db.close()
