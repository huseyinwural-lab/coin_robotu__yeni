from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.execution_engine import consume_execution_queue_once, submit_signal
from core.strategy_engine import generate_strategy_signal
from db import get_db
from deps import get_current_user, require_admin
from models import ExecutionJob, Order, User


router = APIRouter(prefix="/runtime", tags=["runtime_execution"])


class StrategySignalRequest(BaseModel):
    symbol: str
    closes: list[float] = Field(min_length=30)
    strategy_name: str = "ema_rsi"


class ExecutionSubmitRequest(BaseModel):
    symbol: str
    side: str
    size: float = Field(gt=0)
    confidence: float = 0.0
    strategy_name: str = "ema_rsi"
    timestamp: str | None = None
    mark_price: float = Field(default=1.0, gt=0)
    leverage: int = Field(default=1, ge=1)
    idempotency_key: str | None = None


@router.post("/strategy/signal")
def produce_strategy_signal(payload: StrategySignalRequest, _: User = Depends(require_admin)):
    signal = generate_strategy_signal(
        symbol=payload.symbol,
        closes=payload.closes,
        strategy_name=payload.strategy_name,
    )
    if signal is None:
        return {"status": "no_signal", "signal": None}
    return {"status": "ok", "signal": signal}


@router.post("/execution/submit")
def submit_execution(payload: ExecutionSubmitRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        result = submit_signal(
            db,
            user_id=current_user.id,
            signal={
                "symbol": payload.symbol,
                "side": payload.side,
                "size": payload.size,
                "confidence": payload.confidence,
                "strategy_name": payload.strategy_name,
                "timestamp": payload.timestamp,
                "mark_price": payload.mark_price,
                "leverage": payload.leverage,
            },
            idempotency_key=payload.idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return result


@router.post("/execution/worker/process-once")
def process_execution_queue_once(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    result = consume_execution_queue_once(db)
    return result or {"status": "queue_empty"}


@router.get("/execution/jobs/{execution_job_id}")
def get_execution_job(execution_job_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.query(ExecutionJob).filter(ExecutionJob.id == execution_job_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="execution_job_not_found")
    if current_user.role.value == "user" and row.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return {
        "id": row.id,
        "idempotency_key": row.idempotency_key,
        "state": row.state,
        "symbol": row.symbol,
        "side": row.side,
        "size": row.size,
        "strategy_name": row.strategy_name,
        "reject_reason": row.reject_reason,
        "fail_reason": row.fail_reason,
        "retry_count": row.retry_count,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_state_transition_at": row.last_state_transition_at.isoformat() if row.last_state_transition_at else None,
    }


@router.get("/execution/orders/{order_id}")
def get_order(order_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.query(Order).filter(Order.id == order_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="order_not_found")
    if current_user.role.value == "user" and row.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return {
        "id": row.id,
        "execution_job_id": row.execution_job_id,
        "symbol": row.symbol,
        "side": row.side,
        "size": row.size,
        "state": row.state,
        "external_order_id": row.external_order_id,
        "filled_size": row.filled_size,
        "avg_fill_price": row.avg_fill_price,
        "reject_reason": row.reject_reason,
        "fail_reason": row.fail_reason,
        "last_state_transition_at": row.last_state_transition_at.isoformat() if row.last_state_transition_at else None,
    }
