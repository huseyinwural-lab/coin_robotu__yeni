# ruff: noqa: E402
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.security import hash_password
from db import InMemoryRedis, SessionLocal
from models import ExecutionMetric, User, UserExchangeConnection, UserRiskSetting, UserRole
from services.execution_microstructure_service import (
    REPLAY_FILE,
    build_latest_execution_replay,
    build_microstructure_venue_summary,
    build_order_microstructure_assessment,
    get_microstructure_replay,
)


def _create_user(db, prefix: str) -> User:
    user = User(
        email=f"{prefix}-{uuid.uuid4().hex[:8]}@example.com",
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
            market_type="futures",
            environment="paper",
            is_default=True,
            readiness_snapshot={"connection_health": "online", "can_trade": True},
            permission_snapshot=["trade"],
            api_key_encrypted="x",
            api_secret_encrypted="y",
        )
    )
    db.add(UserRiskSetting(user_id=user.id, allocation_pct=20, trade_risk_pct=10, daily_loss_limit_pct=3, compounding_enabled=True, base_capital=10000))
    db.commit()
    db.refresh(user)
    return user


def _seed_p1_cache(cache: InMemoryRedis, symbol: str = "BTCUSDT"):
    snapshot = {
        "venue": "binance",
        "symbol": symbol,
        "data_state": "VALID",
        "venue_readiness": "READY",
        "collected_at": "2026-03-29T00:00:00+00:00",
        "source_timestamp": "2999-03-29T00:00:00+00:00",
        "quote_age_ms": 0,
        "best_bid": 65000.0,
        "best_ask": 65001.0,
        "mid_price": 65000.5,
        "spread_abs": 1.0,
        "spread_bps": 0.1538,
        "top_of_book_bid_qty": 0.5,
        "top_of_book_ask_qty": 0.5,
        "visible_bid_depth_qty": 4.0,
        "visible_ask_depth_qty": 4.0,
        "visible_bid_depth_notional": 260000.0,
        "visible_ask_depth_notional": 260000.0,
        "l2_bids": [[65000.0, 1.0], [64999.5, 1.2]],
        "l2_asks": [[65001.0, 1.0], [65001.5, 1.2]],
        "recent_trades": [{"price": 65000.0, "qty": 0.1, "trade_id": "1", "timestamp": 1, "aggression_side": "BUY"}],
        "trade_flow": {"buy_notional": 6500.0, "sell_notional": 0.0, "buy_share": 1.0, "aggression_side": "BUY"},
        "fast_market": False,
        "transport_latency_ms": 12.0,
    }
    cache.set(f"execution:microstructure:snapshot:binance:{symbol}", json.dumps(snapshot))
    buffer_rows = [
        {"mid_price": 64800.0, "spread_bps": 0.12, "data_state": "VALID", "fast_market": False, "visible_bid_depth_notional": 240000.0, "visible_ask_depth_notional": 240000.0, "transport_latency_ms": 11.0},
        {"mid_price": 64920.0, "spread_bps": 0.13, "data_state": "VALID", "fast_market": False, "visible_bid_depth_notional": 250000.0, "visible_ask_depth_notional": 250000.0, "transport_latency_ms": 12.0},
        {"mid_price": 65000.0, "spread_bps": 0.15, "data_state": "VALID", "fast_market": False, "visible_bid_depth_notional": 260000.0, "visible_ask_depth_notional": 260000.0, "transport_latency_ms": 13.0},
    ]
    cache.set(f"execution:microstructure:buffer:binance:{symbol}", json.dumps(buffer_rows))


def test_p1_slippage_decomposition_and_recommendation_present():
    db = SessionLocal()
    try:
        user = _create_user(db, "p1-slippage")
        cache = InMemoryRedis()
        _seed_p1_cache(cache)
        result = build_order_microstructure_assessment(
            db,
            cache,
            user_id=user.id,
            symbol="BTCUSDT",
            side="buy",
            price=65000,
            size=0.02,
            order_type="market",
        )
        assert "slippage_decomposition" in result
        assert set(result["slippage_decomposition"].keys()) == {"spread_bps", "impact_bps", "timing_bps", "retry_cost_bps"}
        assert "market_regime" in result
        assert "execution_recommendation" in result
    finally:
        db.close()


def test_p1_venue_summary_exposes_health_and_liquidity_stress():
    cache = InMemoryRedis()
    _seed_p1_cache(cache)
    summary = build_microstructure_venue_summary(cache, ["BTCUSDT"])
    assert "venue_health_score" in summary["venues"]["binance"]
    assert "liquidity_stress_score" in summary["venues"]["binance"]


def test_p1_microstructure_replay_reader_filters_symbol():
    replay_symbol = f"REPLAY{uuid.uuid4().hex[:6]}"
    REPLAY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with REPLAY_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"captured_at": datetime.now(timezone.utc).isoformat(), "venue": "binance", "symbol": replay_symbol, "data_state": "VALID"}) + "\n")
    payload = get_microstructure_replay(symbol=replay_symbol, venue="binance", limit=5)
    assert payload["items"]
    assert payload["items"][-1]["symbol"] == replay_symbol


def test_p1_latest_execution_replay_explains_slippage_metric():
    db = SessionLocal()
    try:
        user = _create_user(db, "p1-replay")
        metric = ExecutionMetric(
            user_id=user.id,
            symbol="BTCUSDT",
            order_id=f"order-{uuid.uuid4().hex[:8]}",
            exchange_order_id="ext-1",
            client_order_id="client-1",
            order_type="MARKET",
            exchange="binance",
            market_type="futures",
            environment="paper",
            side="BUY",
            quote_qty=100,
            mid_price=65000,
            mid_price_timestamp=datetime.now(timezone.utc).isoformat(),
            price_avg=65005,
            executed_qty=0.01,
            slippage_pct=0.01,
            execution_time_ms=120,
            status="FILLED",
            final_status="FILLED",
            failure_code=None,
            strategy_type="ema_rsi",
            volatility_regime="normal",
            volatility_pct=0,
            execution_quality_score=90,
            submitted_at=datetime.now(timezone.utc),
            ack_at=datetime.now(timezone.utc),
            final_at=datetime.now(timezone.utc),
            validation_snapshot_id=None,
            raw_exchange_status={
                "predicted_slippage_bps": 4.0,
                "realized_slippage_bps": 5.0,
                "slippage_error_bps": 1.0,
                "microstructure_guard": {
                    "selected_venue": "binance",
                    "slippage_decomposition": {"spread_bps": 1.0, "impact_bps": 3.0, "timing_bps": 1.0, "retry_cost_bps": 0.0},
                },
            },
            state_machine_path=["SENT", "FILLED"],
        )
        db.add(metric)
        db.commit()
        payload = build_latest_execution_replay(db, symbol="BTCUSDT")
        assert payload["status"] == "ok"
        assert payload["root_cause"] in {"prediction_match", "market_impact", "fast_market", "timing_delay"}
    finally:
        db.close()
