from datetime import datetime, timezone

# ruff: noqa: E402
import inspect
import sys
import types
import uuid
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.security import hash_password
from db import InMemoryRedis, SessionLocal
from models import ExecutionJob, ExecutionMetric, Order, User, UserExchangeConnection, UserRiskSetting, UserRole
from services.execution_microstructure_service import build_order_microstructure_assessment
from services.execution_readiness_service import validate_order_precheck
from core import execution_engine


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
    db.add(
        UserRiskSetting(
            user_id=user.id,
            allocation_pct=20,
            trade_risk_pct=10,
            daily_loss_limit_pct=3,
            compounding_enabled=True,
            base_capital=10000,
        )
    )
    db.commit()
    db.refresh(user)
    return user


def _seed_snapshot(cache, symbol: str = "BTCUSDT"):
    cache.set(
        f"execution:microstructure:snapshot:binance:{symbol}",
        """{
            "venue": "binance",
            "symbol": "BTCUSDT",
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
            "l2_bids": [[65000.0, 1.0]],
            "l2_asks": [[65001.0, 1.0]],
            "recent_trades": [{"price": 65000.0, "qty": 0.1, "trade_id": "1", "timestamp": 1, "aggression_side": "BUY"}],
            "trade_flow": {"buy_notional": 6500.0, "sell_notional": 0.0, "buy_share": 1.0, "aggression_side": "BUY"},
            "fast_market": false
        }""",
    )


def test_microstructure_assessment_blocks_without_snapshot():
    db = SessionLocal()
    try:
        user = _create_user(db, "micro-block")
        result = build_order_microstructure_assessment(
            db,
            InMemoryRedis(),
            user_id=user.id,
            symbol="BTCUSDT",
            side="buy",
            price=65000,
            size=0.01,
            order_type="market",
        )
        assert result["state"] == "BLOCK"
        assert result["market_snapshot"]["data_state"] == "INVALID"
    finally:
        db.close()


def test_microstructure_assessment_reduces_size_on_capacity_pressure():
    db = SessionLocal()
    try:
        user = _create_user(db, "micro-reduce")
        cache = InMemoryRedis()
        _seed_snapshot(cache)
        result = build_order_microstructure_assessment(
            db,
            cache,
            user_id=user.id,
            symbol="BTCUSDT",
            side="buy",
            price=65000,
            size=1.0,
            order_type="market",
        )
        assert result["state"] in {"REDUCE_SIZE", "BLOCK"}
        assert float(result["adjusted_size"]) <= 1.0
    finally:
        db.close()


def test_validate_order_precheck_returns_microstructure_guard_payload(monkeypatch):
    db = SessionLocal()
    try:
        user = _create_user(db, "precheck-micro")
        cache = InMemoryRedis()
        _seed_snapshot(cache)
        import services.pipeline.runtime as runtime_module

        monkeypatch.setattr(runtime_module, "pipeline_runtime", types.SimpleNamespace(cache=cache))
        result = validate_order_precheck(
            db,
            user_id=user.id,
            symbol="BTCUSDT",
            market_type="futures",
            order_type="market",
            side="buy",
            price=65000,
            size=0.05,
            leverage=2,
            margin_mode="isolated",
        )
        assert "microstructure_guard" in result
        assert result["microstructure_guard"]["market_snapshot"]["data_state"] == "VALID"
    finally:
        db.close()


def test_runtime_submit_signal_has_microstructure_precheck_binding():
    source = inspect.getsource(execution_engine.submit_signal)
    assert "validate_order_precheck" in source


def test_runtime_execution_metric_records_predicted_vs_realized_slippage():
    db = SessionLocal()
    try:
        user = _create_user(db, "metric-micro")
        job = ExecutionJob(
            user_id=user.id,
            idempotency_key=f"metric-{uuid.uuid4().hex[:8]}",
            symbol="BTCUSDT",
            side="BUY",
            size=0.01,
            strategy_name="ema_rsi",
            state="FILLED",
            meta_payload={
                "mark_price": 65000.0,
                "microstructure_guard": {
                    "selected_venue": "binance",
                    "slippage_prediction": {"expected_slippage_bps": 4.5},
                },
            },
            created_at=datetime.now(timezone.utc),
            sent_at=datetime.now(timezone.utc),
            filled_at=datetime.now(timezone.utc),
            total_ms=120,
            execution_ms=80,
        )
        db.add(job)
        db.flush()
        order = Order(
            execution_job_id=job.id,
            user_id=user.id,
            symbol="BTCUSDT",
            side="BUY",
            size=0.01,
            state="FILLED",
            avg_fill_price=65010.0,
            filled_size=0.01,
            sent_at=datetime.now(timezone.utc),
            filled_at=datetime.now(timezone.utc),
        )
        db.add(order)
        db.flush()

        execution_engine._record_execution_metric(db, job=job, order=order, exchange_result={"states": ["SENT", "FILLED"]})
        db.commit()

        metric = db.query(ExecutionMetric).filter(ExecutionMetric.order_id == order.id).first()
        assert metric is not None
        assert (metric.raw_exchange_status or {}).get("predicted_slippage_bps") == 4.5
        assert (metric.raw_exchange_status or {}).get("slippage_error_bps") is not None
    finally:
        db.close()
