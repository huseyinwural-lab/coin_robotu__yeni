# ruff: noqa: E402
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.execution_engine import _create_or_get_order, handle_execution_result, submit_signal
from core.live.order_reconciliation_engine import reconcile_order_state
from core.live.position_sync_engine import reconcile_position_state
from core.risk_engine import evaluate_risk
from core.security import hash_password
from db import SessionLocal
from models import ExecutionJob, Position, User, UserRole
from services.execution_intent_service import build_execution_intent_detail


def _seed_user(db):
    user = User(
        email=f"cali-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("Pass1234!Aa"),
        role=UserRole.USER,
        is_active=True,
        approval_status="approved",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _allowing_precheck(*args, **kwargs):
    size = float(kwargs.get("size") or 0.0)
    return {
        "valid": True,
        "adjustments": {"adjusted_size": size},
        "microstructure_guard": {"state": "ALLOW", "selected_venue": "binance", "slippage_prediction": {"expected_slippage_bps": 1.0}},
    }


def test_order_lifecycle_sent_partial_full_creates_position(monkeypatch):
    db = SessionLocal()
    try:
        user = _seed_user(db)
        job = ExecutionJob(
            idempotency_key=f"cali-life-{uuid.uuid4().hex[:8]}",
            user_id=user.id,
            symbol="BTCUSDT",
            side="BUY",
            size=0.1,
            strategy_name="ema_rsi",
            state="CREATED",
            meta_payload={"mark_price": 100.0, "microstructure_guard": {"selected_venue": "binance", "slippage_prediction": {"expected_slippage_bps": 1.0}}},
        )
        db.add(job)
        db.flush()
        order = _create_or_get_order(db, job=job)
        result = handle_execution_result(
            db,
            job=job,
            order=order,
            exchange_result={
                "external_order_id": f"EXT-{uuid.uuid4().hex[:8]}",
                "avg_fill_price": 101.0,
                "filled_size": 0.1,
                "states": ["SENT", "PARTIALLY_FILLED", "FILLED"],
            },
        )
        db.refresh(order)
        db.refresh(job)
        position = db.query(Position).filter(Position.user_id == user.id, Position.symbol == "BTCUSDT").first()
        assert result["state"] == "FILLED"
        assert order.state == "FILLED"
        assert job.state == "FILLED"
        assert position is not None
        assert float(position.size) == 0.1
    finally:
        db.close()


def test_duplicate_guard_blocks_second_submit(monkeypatch):
    import core.execution_engine as execution_engine

    db = SessionLocal()
    try:
        user = _seed_user(db)
        monkeypatch.setattr(execution_engine, "validate_order_precheck", _allowing_precheck)
        monkeypatch.setattr(execution_engine, "evaluate_canary_constraints", lambda *args, **kwargs: {"allowed": True})
        monkeypatch.setattr(execution_engine, "run_risk_checks", lambda *args, **kwargs: {"allowed": True, "reject_reason": None, "reject_reasons": []})
        monkeypatch.setattr(execution_engine, "evaluate_auto_kill_switch", lambda *args, **kwargs: {"active": False})
        key = f"dup-{uuid.uuid4().hex[:8]}"
        first = submit_signal(db, user_id=user.id, signal={"symbol": "ETHUSDT", "side": "BUY", "size": 0.1, "strategy_name": "ema_rsi", "mark_price": 120, "leverage": 1}, idempotency_key=key)
        second = submit_signal(db, user_id=user.id, signal={"symbol": "ETHUSDT", "side": "BUY", "size": 0.1, "strategy_name": "ema_rsi", "mark_price": 120, "leverage": 1}, idempotency_key=key)
        assert first["status"] == "enqueued"
        assert second["status"] == "duplicate"
    finally:
        db.close()


def test_risk_guard_blocks_on_limits():
    db = SessionLocal()
    try:
        user = _seed_user(db)
        result = evaluate_risk(
            db,
            user_id=user.id,
            symbol="BTCUSDT",
            side="BUY",
            size=1.0,
            leverage=10,
            mark_price=2000,
            limits={"max_position_pct": 1.0, "per_user_notional_cap": 100.0, "leverage_cap": 2, "max_daily_loss_usd": 250.0},
        )
        assert result["allowed"] is False
        assert "leverage_cap_exceeded" in result["reject_reasons"]
    finally:
        db.close()


def test_state_parity_reconciliation_detects_mismatch_and_pnl_is_explicit():
    order_recon = reconcile_order_state(
        engine_orders=[{"order_id": "1", "symbol": "BTCUSDT", "side": "BUY", "price": 100, "quantity": 1, "status": "SENT"}],
        exchange_orders=[{"order_id": "1", "symbol": "BTCUSDT", "side": "BUY", "price": 100, "quantity": 1, "status": "FILLED"}],
    )
    pos_recon = reconcile_position_state(
        engine_positions=[{"symbol": "BTCUSDT", "position_size": 1.0, "entry_price": 100, "leverage": 2, "unrealized_pnl": 5}],
        exchange_positions=[{"symbol": "BTCUSDT", "position_size": 1.1, "entry_price": 100, "leverage": 2, "unrealized_pnl": 5}],
    )
    assert order_recon["order_reconciliation_state"] == "ERROR"
    assert pos_recon["position_sync_state"] == "DRIFT"


def test_order_reconciliation_partial_fill_and_cancel_mismatch_edge_cases():
    partial = reconcile_order_state(
        engine_orders=[{"order_id": "2", "symbol": "ETHUSDT", "side": "BUY", "price": 100, "quantity": 1, "status": "PARTIALLY_FILLED"}],
        exchange_orders=[{"order_id": "2", "symbol": "ETHUSDT", "side": "BUY", "price": 100, "quantity": 1, "status": "FILLED"}],
    )
    canceled = reconcile_order_state(
        engine_orders=[{"order_id": "3", "symbol": "SOLUSDT", "side": "SELL", "price": 50, "quantity": 2, "status": "SENT"}],
        exchange_orders=[{"order_id": "3", "symbol": "SOLUSDT", "side": "SELL", "price": 50, "quantity": 2, "status": "CANCELED"}],
    )
    assert partial["order_reconciliation_state"] == "ERROR"
    assert canceled["order_reconciliation_state"] == "ERROR"


def test_position_sync_reconnect_rebuild_unverified_state():
    payload = reconcile_position_state(
        engine_positions=[{"symbol": "BNBUSDT", "position_size": 1.0, "entry_price": 100, "leverage": 2, "unrealized_pnl": 4}],
        exchange_positions=[],
    )
    assert payload["position_sync_state"] == "UNVERIFIED"


def test_execution_intent_detail_answers_why_order_exists():
    db = SessionLocal()
    try:
        from models import UserExecutionIntent

        user = _seed_user(db)
        intent = UserExecutionIntent(
            id=str(uuid.uuid4()),
            intent_id=f"intent-{uuid.uuid4().hex[:8]}",
            user_id=user.id,
            source_type="scanner",
            symbol="BTCUSDT",
            market_type="futures",
            side="buy",
            status="QUEUED",
            intent_type="OPEN_POSITION",
            queue_mode="ASSISTED",
            approval_required=True,
            intent_token=f"intent-token-{uuid.uuid4().hex[:8]}",
            preview_hash=f"preview-{uuid.uuid4().hex[:8]}",
            size=0.1,
            notional=100.0,
            risk_score=22.0,
            gate_decision="ALLOW",
            meta_engine_decision="ALLOW",
            normalized_order_payload={"source_type": "scanner", "scanner_signal_snapshot": {"signal_id": "sig-1"}, "decision_trace": [{"strategy_id": "ema_rsi", "reason": "momentum breakout"}]},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(intent)
        db.commit()
        detail = build_execution_intent_detail(db, intent)
        assert detail["order_preview"]["symbol"] == "BTCUSDT"
        assert detail["gate_decision"]["gate_decision"] == "ALLOW"
        assert "expected_impact" in detail
    finally:
        db.close()
