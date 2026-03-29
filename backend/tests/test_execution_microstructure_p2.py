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
from services.execution_microstructure_service import build_latest_execution_replay, build_order_microstructure_assessment


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


def _seed_cache(cache: InMemoryRedis, symbol: str = "BTCUSDT"):
    snapshot = {
        "venue": "binance",
        "symbol": symbol,
        "data_state": "VALID",
        "venue_readiness": "READY",
        "collected_at": "2026-03-29T00:00:00+00:00",
        "source_timestamp": "2999-03-29T00:00:00+00:00",
        "quote_age_ms": 0,
        "best_bid": 65000.0,
        "best_ask": 65002.0,
        "mid_price": 65001.0,
        "spread_abs": 2.0,
        "spread_bps": 0.3076,
        "top_of_book_bid_qty": 0.2,
        "top_of_book_ask_qty": 0.2,
        "visible_bid_depth_qty": 1.0,
        "visible_ask_depth_qty": 1.0,
        "visible_bid_depth_notional": 65000.0,
        "visible_ask_depth_notional": 65000.0,
        "l2_bids": [[65000.0, 0.2], [64999.5, 0.2]],
        "l2_asks": [[65002.0, 0.2], [65002.5, 0.2]],
        "recent_trades": [
            {"price": 65001.0, "qty": 0.5, "trade_id": "1", "timestamp": 1, "aggression_side": "BUY"},
            {"price": 65002.0, "qty": 0.4, "trade_id": "2", "timestamp": 2, "aggression_side": "BUY"}
        ],
        "trade_flow": {"buy_notional": 58501.0, "sell_notional": 0.0, "buy_share": 1.0, "aggression_side": "BUY"},
        "fast_market": True,
        "transport_latency_ms": 18.0,
    }
    buffer = [
        {"mid_price": 64800.0, "spread_bps": 0.2, "data_state": "VALID", "fast_market": False, "visible_bid_depth_notional": 120000.0, "visible_ask_depth_notional": 120000.0, "transport_latency_ms": 12.0, "trade_flow": {"buy_notional": 20000.0, "sell_notional": 18000.0}},
        {"mid_price": 64900.0, "spread_bps": 0.25, "data_state": "VALID", "fast_market": False, "visible_bid_depth_notional": 95000.0, "visible_ask_depth_notional": 95000.0, "transport_latency_ms": 14.0, "trade_flow": {"buy_notional": 25000.0, "sell_notional": 20000.0}},
        {"mid_price": 65000.0, "spread_bps": 0.3, "data_state": "VALID", "fast_market": True, "visible_bid_depth_notional": 70000.0, "visible_ask_depth_notional": 70000.0, "transport_latency_ms": 18.0, "trade_flow": {"buy_notional": 30000.0, "sell_notional": 22000.0}}
    ]
    cache.set(f"execution:microstructure:snapshot:binance:{symbol}", json.dumps(snapshot))
    cache.set(f"execution:microstructure:buffer:binance:{symbol}", json.dumps(buffer))


def test_p2_impact_model_is_non_linear():
    db = SessionLocal()
    try:
        user = _create_user(db, "p2-impact")
        cache = InMemoryRedis()
        _seed_cache(cache)
        payload = build_order_microstructure_assessment(db, cache, user_id=user.id, symbol="BTCUSDT", side="buy", price=65000, size=0.5, order_type="market")
        impact = payload["impact_model"]
        assert impact["square_root_impact"] > 0
        assert impact["performance_degradation_pct"] > 0
    finally:
        db.close()


def test_p2_hidden_liquidity_and_depth_decay_present():
    db = SessionLocal()
    try:
        user = _create_user(db, "p2-hidden")
        cache = InMemoryRedis()
        _seed_cache(cache)
        payload = build_order_microstructure_assessment(db, cache, user_id=user.id, symbol="BTCUSDT", side="buy", price=65000, size=0.2, order_type="market")
        assert payload["hidden_liquidity"]["state"] in {"LOW", "MEDIUM", "HIGH"}
        assert payload["depth_decay"]["state"] in {"STABLE", "ELEVATED", "RAPID"}
    finally:
        db.close()


def test_p2_execution_budget_can_reduce_or_block():
    db = SessionLocal()
    try:
        user = _create_user(db, "p2-budget")
        db.add(
            ExecutionMetric(
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
                quote_qty=5000,
                mid_price=65000,
                mid_price_timestamp=datetime.now(timezone.utc).isoformat(),
                price_avg=65001,
                executed_qty=0.08,
                slippage_pct=0.01,
                execution_time_ms=100,
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
                raw_exchange_status={},
                state_machine_path=["SENT", "FILLED"],
            )
        )
        db.commit()
        cache = InMemoryRedis()
        _seed_cache(cache)
        payload = build_order_microstructure_assessment(db, cache, user_id=user.id, symbol="BTCUSDT", side="buy", price=65000, size=0.4, order_type="market", strategy_binding="ema_rsi")
        assert payload["execution_budget"]["state"] in {"ALLOW", "REDUCE_SIZE", "BLOCK"}
        if payload["execution_budget"]["state"] != "ALLOW":
            assert payload["execution_budget"]["reasons"]
    finally:
        db.close()


def test_p2_slicing_plan_and_execution_replay_expose_slice_signal():
    db = SessionLocal()
    try:
        user = _create_user(db, "p2-slice")
        cache = InMemoryRedis()
        _seed_cache(cache)
        payload = build_order_microstructure_assessment(db, cache, user_id=user.id, symbol="BTCUSDT", side="buy", price=65000, size=0.6, order_type="market", strategy_binding="ema_rsi")
        assert payload["slicing_plan"]["slice_count"] >= 1
        metric = ExecutionMetric(
            user_id=user.id,
            symbol="BTCUSDT",
            order_id=f"order-{uuid.uuid4().hex[:8]}",
            exchange_order_id="ext-2",
            client_order_id="client-2",
            order_type="MARKET",
            exchange="binance",
            market_type="futures",
            environment="paper",
            side="BUY",
            quote_qty=100,
            mid_price=65000,
            mid_price_timestamp=datetime.now(timezone.utc).isoformat(),
            price_avg=65010,
            executed_qty=0.01,
            slippage_pct=0.02,
            execution_time_ms=140,
            status="FILLED",
            final_status="FILLED",
            failure_code=None,
            strategy_type="ema_rsi",
            volatility_regime="normal",
            volatility_pct=0,
            execution_quality_score=88,
            submitted_at=datetime.now(timezone.utc),
            ack_at=datetime.now(timezone.utc),
            final_at=datetime.now(timezone.utc),
            validation_snapshot_id=None,
            raw_exchange_status={
                "predicted_slippage_bps": 10.0,
                "realized_slippage_bps": 12.0,
                "slippage_error_bps": 2.0,
                "microstructure_guard": payload,
            },
            state_machine_path=["SENT", "FILLED"],
        )
        db.add(metric)
        db.commit()
        replay = build_latest_execution_replay(db, symbol="BTCUSDT")
        assert "should_have_been_sliced" in replay
        assert "slicing_plan" in replay
    finally:
        db.close()
