# ruff: noqa: E402
import sys
import uuid
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.security import hash_password
from db import SessionLocal
from models import BotProfile, SignalEvent, User, UserExchangeConnection, UserRole, UserScannerResult
from services.bot_runtime_service import get_bot_runtime_detail, list_bot_runtime_summaries, start_bot_runtime


def _seed_user(db):
    user = User(
        email=f"bot-runtime-{uuid.uuid4().hex[:8]}@example.com",
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
            permission_snapshot=["read", "trade"],
            api_key_encrypted="x",
            api_secret_encrypted="y",
        )
    )
    db.commit()
    db.refresh(user)
    return user


def test_manual_symbol_source_runtime_detail():
    db = SessionLocal()
    try:
        user = _seed_user(db)
        bot = BotProfile(user_id=user.id, name="Manual Bot", exchange="binance", market_type="spot", symbol_source_type="manual", symbols=["BTCUSDT"], strategy_type="trend_following", timeframe="15m", trend_timeframe="1h", leverage=1, is_enabled=True)
        db.add(bot)
        db.commit()
        db.refresh(bot)
        start_payload = start_bot_runtime(db, bot=bot, actor_id=user.id)
        detail = get_bot_runtime_detail(db, bot=bot)
        assert start_payload["status"] == "RUNNING"
        assert detail["config_summary"]["symbol_source_type"] == "manual"
        assert detail["runtime_summary"]["symbol_source_summary"]["symbols"] == ["BTCUSDT"]
        assert detail["binding_validation"]["result"] == "ok"
    finally:
        db.close()


def test_scanner_symbol_source_error_when_empty():
    db = SessionLocal()
    try:
        user = _seed_user(db)
        bot = BotProfile(user_id=user.id, name="Scanner Bot", exchange="binance", market_type="spot", symbol_source_type="scanner", scanner_id="scanner-empty", symbols=[], strategy_type="trend_following", timeframe="15m", trend_timeframe="1h", leverage=1, is_enabled=True)
        db.add(bot)
        db.commit()
        db.refresh(bot)
        payload = start_bot_runtime(db, bot=bot, actor_id=user.id)
        assert payload["status"] == "ERROR"
        assert payload["binding_ok"] is False
    finally:
        db.close()


def test_scanner_symbol_source_resolves_and_logs_bindings():
    db = SessionLocal()
    try:
        user = _seed_user(db)
        db.add(UserScannerResult(user_id=user.id, run_id="scanner-empty", symbol="ETHUSDT", strategy_code="trend_following", signal="buy", confidence=0.8, signal_score=0.8, reason_codes=["scanner"], payload={}))
        db.commit()
        bot = BotProfile(user_id=user.id, name="Scanner Bot", exchange="binance", market_type="spot", symbol_source_type="scanner", scanner_id="scanner-empty", symbols=[], strategy_type="trend_following", timeframe="15m", trend_timeframe="1h", leverage=1, is_enabled=True)
        db.add(bot)
        db.commit()
        db.refresh(bot)
        db.add(SignalEvent(bot_profile_id=bot.id, user_id=user.id, symbol="ETHUSDT", market_type="spot", timeframe="15m", strategy_id="trend_following", signal="BUY", direction="long", confidence=0.8, reason_codes=["scanner"]))
        db.commit()
        start_payload = start_bot_runtime(db, bot=bot, actor_id=user.id)
        detail = get_bot_runtime_detail(db, bot=bot)
        summaries = list_bot_runtime_summaries(db, user_id=user.id)
        assert start_payload["status"] == "RUNNING"
        assert detail["runtime_summary"]["symbol_source_summary"]["source_type"] == "scanner"
        assert detail["runtime_summary"]["symbol_source_summary"]["symbols"] == ["ETHUSDT"]
        assert detail["runtime_summary"]["health"] in {"HEALTHY", "DEGRADED"}
        assert summaries[0]["binding_validation"]["strategy_bound"] is True
    finally:
        db.close()
