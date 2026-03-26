import uuid

from core.reconciliation.order_reconciliation import run_order_reconciliation
from db import SessionLocal
from models import ExecutionJob, Order, User


def test_order_reconciliation_runs_and_returns_contract():
    db = SessionLocal()
    try:
        user = db.query(User).order_by(User.created_at.asc()).first()
        assert user is not None

        job = ExecutionJob(
            idempotency_key=f"recon-{uuid.uuid4()}",
            user_id=user.id,
            symbol="BTCUSDT",
            side="BUY",
            size=0.1,
            strategy_name="ema_rsi",
            state="SENT",
        )
        db.add(job)
        db.flush()

        order = Order(
            execution_job_id=job.id,
            user_id=user.id,
            symbol="BTCUSDT",
            side="BUY",
            size=0.1,
            state="SENT",
            external_order_id=f"SIM-RECON-TEST-{uuid.uuid4()}",
        )
        db.add(order)
        db.commit()

        result = run_order_reconciliation(db, limit=10)
        assert result.get("status") == "ok"
        assert "checked_orders" in result
        assert "mismatches" in result
    finally:
        db.close()
