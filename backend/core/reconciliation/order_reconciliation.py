from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.exchanges import get_execution_adapter
from models import ExecutionJob, Order


OPEN_STATES = {"CREATED", "SENT", "PARTIALLY_FILLED"}


def run_order_reconciliation(db: Session, *, limit: int = 100) -> dict:
    adapter = get_execution_adapter()
    orders = (
        db.query(Order)
        .filter(Order.state.in_(OPEN_STATES), Order.external_order_id.isnot(None))
        .order_by(Order.updated_at.desc())
        .limit(max(1, min(limit, 300)))
        .all()
    )

    checked = 0
    mismatches = 0
    corrected = 0
    issues: list[dict] = []

    for order in orders:
        checked += 1
        try:
            status_payload = adapter.get_order_status(symbol=order.symbol, order_id=order.external_order_id)
        except Exception as exc:  # noqa: BLE001
            issues.append({"order_id": order.id, "issue": "status_fetch_failed", "error": str(exc)[:200]})
            continue

        exchange_state = str(status_payload.get("status") or "").upper()
        if not exchange_state:
            continue

        if exchange_state != str(order.state).upper():
            mismatches += 1
            previous_state = str(order.state)
            order.state = exchange_state
            order.last_state_transition_at = datetime.now(timezone.utc)
            if exchange_state == "FILLED":
                order.filled_size = float(status_payload.get("executed_qty") or order.filled_size or order.size or 0)
                order.avg_fill_price = float(status_payload.get("avg_fill_price") or order.avg_fill_price or 0)
                order.filled_at = datetime.now(timezone.utc)

                job = db.query(ExecutionJob).filter(ExecutionJob.id == order.execution_job_id).first()
                if job is not None:
                    job.state = "FILLED"
                    job.filled_at = datetime.now(timezone.utc)
            elif exchange_state in {"CANCELED", "FAILED"}:
                job = db.query(ExecutionJob).filter(ExecutionJob.id == order.execution_job_id).first()
                if job is not None:
                    job.state = exchange_state
                    job.failed_at = datetime.now(timezone.utc)

            corrected += 1
            issues.append(
                {
                    "order_id": order.id,
                    "issue": "state_mismatch_corrected",
                    "previous_state": previous_state,
                    "exchange_state": exchange_state,
                }
            )

    db.commit()
    return {
        "status": "ok",
        "checked_orders": checked,
        "mismatches": mismatches,
        "corrected": corrected,
        "issues": issues,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
