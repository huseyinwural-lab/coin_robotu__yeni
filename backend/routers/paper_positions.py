from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db import get_db
from deps import get_current_user, is_admin_role
from models import PaperPosition, User
from schemas import ManualClosePositionRequest, PaperPositionResponse
from services.audit_service import create_audit_log
from services.pipeline.execution_engine import manual_close_position

router = APIRouter(prefix="/paper-positions", tags=["paper_positions"])


def _authorized_position(db: Session, position_id: str, current_user: User):
    query = db.query(PaperPosition).filter(PaperPosition.id == position_id)
    if not is_admin_role(current_user.role):
        query = query.filter(PaperPosition.user_id == current_user.id)
    position = query.first()
    if position is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position not found")
    return position


@router.get("", response_model=list[PaperPositionResponse])
def list_positions(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(PaperPosition)
    if not is_admin_role(current_user.role):
        query = query.filter(PaperPosition.user_id == current_user.id)
    return query.order_by(PaperPosition.opened_at.desc()).limit(200).all()


@router.post("/{position_id}/manual-close", response_model=PaperPositionResponse)
def close_position(
    position_id: str,
    payload: ManualClosePositionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    position = _authorized_position(db, position_id, current_user)
    if position.status != "open":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Position already closed")

    updated = manual_close_position(db, position, payload.reason)
    create_audit_log(
        db,
        action="trade_close",
        entity_type="paper_position",
        entity_id=updated.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"reason": payload.reason, "realized_pnl": updated.realized_pnl},
    )
    return updated