from fastapi import Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db import get_db
from deps import get_current_user, require_admin
from models import User, UserExecutionIntent
from services.execution_readiness_service import enforce_execution_guard_or_raise


def execution_guard_dependency(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce_execution_guard_or_raise(
        db,
        user_id=current_user.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        source="execution_guard_dependency",
    )


def execution_guard_admin_approve_trade_dependency(
    intent_id: str = Body(..., embed=True),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    intent = db.query(UserExecutionIntent).filter(UserExecutionIntent.id == intent_id).first()
    if intent is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="intent_not_found")

    enforce_execution_guard_or_raise(
        db,
        user_id=intent.user_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        source="admin_approve_trade_dependency",
    )
