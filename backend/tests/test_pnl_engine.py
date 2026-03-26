from datetime import datetime, timezone
import uuid

from core.pnl_engine import compute_runtime_pnl_positions
from db import SessionLocal
from models import ExecutionJob, Order, Position, User


def test_pnl_engine_unrealized_and_realized_fields_present():
    db = SessionLocal()
    try:
        user = db.query(User).order_by(User.created_at.asc()).first()
        assert user is not None

        job = ExecutionJob(
            idempotency_key=f"test-pnl-{uuid.uuid4()}",
            user_id=user.id,
            symbol="LTCUSDT",
            side="BUY",
            size=1.0,
            strategy_name="ema_rsi",
            state="FILLED",
        )
        db.add(job)
        db.flush()

        order = Order(
            execution_job_id=job.id,
            user_id=user.id,
            symbol="LTCUSDT",
            side="BUY",
            size=1.0,
            state="FILLED",
            external_order_id=f"TEST-{uuid.uuid4()}",
            avg_fill_price=100.0,
            filled_size=1.0,
            filled_at=datetime.now(timezone.utc),
        )
        db.add(order)

        position = Position(
            position_id=f"{user.id}:LTCUSDT:test:{uuid.uuid4()}",
            user_id=user.id,
            symbol="LTCUSDT",
            size=1.0,
            entry_price=100.0,
            current_price=105.0,
            unrealized_pnl=5.0,
            leverage=1,
            status="open",
            strategy_id=None,
            cluster_id=None,
            external_order_id=order.external_order_id,
            last_state_transition_at=datetime.now(timezone.utc),
        )
        db.add(position)
        db.commit()

        rows = compute_runtime_pnl_positions(db, user_id=user.id, symbol="LTCUSDT")
        assert len(rows) >= 1
        target = rows[0]
        for field in [
            "user_id",
            "symbol",
            "position_qty",
            "avg_entry_price",
            "mark_price",
            "realized_pnl",
            "unrealized_pnl",
            "fees",
            "funding",
            "net_pnl",
            "updated_at",
        ]:
            assert field in target
        assert float(target["unrealized_pnl"]) == 5.0
    finally:
        db.close()
