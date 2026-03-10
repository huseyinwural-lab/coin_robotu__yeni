from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db import get_db, redis_client
from deps import get_current_user
from exchange.binance_mock import BinanceMockAdapter
from models import BotProfile, ExecutionEvent, User, UserRole
from schemas import ExecutionEventResponse, MockOrderRequest
from services.audit_service import create_audit_log

router = APIRouter(prefix="/exchange", tags=["exchange"])
adapter = BinanceMockAdapter(redis_client)


@router.get("/mock/state")
def get_exchange_mock_state(current_user: User = Depends(get_current_user)):
    return {
        "adapter": adapter.healthcheck(),
        "last_order": redis_client.get("exchange:binance:mock:last_order"),
        "viewer_role": current_user.role.value,
    }


@router.get("/mock/events", response_model=list[ExecutionEventResponse])
def list_mock_events(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(ExecutionEvent)
    if current_user.role != UserRole.ADMIN:
        bot_ids = db.query(BotProfile.id).filter(BotProfile.user_id == current_user.id)
        query = query.filter(ExecutionEvent.bot_profile_id.in_(bot_ids))
    return query.order_by(ExecutionEvent.created_at.desc()).limit(50).all()


@router.post("/mock/execute", response_model=ExecutionEventResponse)
def execute_mock_order(
    payload: MockOrderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bot_query = db.query(BotProfile).filter(BotProfile.id == payload.bot_profile_id)
    if current_user.role != UserRole.ADMIN:
        bot_query = bot_query.filter(BotProfile.user_id == current_user.id)

    bot_profile = bot_query.first()
    if bot_profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot profile not found")

    result = adapter.execute_mock_order(payload.symbol, payload.side, payload.quantity)
    event = ExecutionEvent(
        bot_profile_id=bot_profile.id,
        exchange=bot_profile.exchange,
        symbol=result["symbol"],
        side=result["side"],
        quantity=result["quantity"],
        mock_price=result["mock_price"],
        execution_status=result["status"],
        response_payload=result,
        note="MOCK execution only. No live order sent.",
    )

    db.add(event)
    db.commit()
    db.refresh(event)
    create_audit_log(
        db,
        action="mock_execution_sent",
        entity_type="execution_event",
        entity_id=event.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        severity="warning",
        details={"exchange": bot_profile.exchange, "symbol": event.symbol, "side": event.side},
    )
    return event