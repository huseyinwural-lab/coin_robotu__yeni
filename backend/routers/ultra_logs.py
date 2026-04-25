from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from schemas import (
    UltraLogActivateRequest,
    UltraLogDeactivateRequest,
    UltraLogEventResponse,
    UltraLogStatusResponse,
)
from services.audit_service import create_audit_log
from services.ultra_log_service import (
    DURATION_OPTIONS_SECONDS,
    activate_ultra_log,
    deactivate_ultra_log,
    list_ultra_log_events,
    ultra_log_status,
)

router = APIRouter(prefix="/admin/ultra-log", tags=["ultra_log"])


@router.get("/status", response_model=UltraLogStatusResponse)
def get_ultra_log_status(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return UltraLogStatusResponse(**ultra_log_status(db))


@router.post("/activate", response_model=UltraLogStatusResponse)
def activate_ultra_log_endpoint(
    payload: UltraLogActivateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if payload.duration_option not in DURATION_OPTIONS_SECONDS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_duration_option")

    row = activate_ultra_log(
        db,
        duration_option=payload.duration_option,
        max_normal_log_mb=payload.max_normal_log_mb,
        max_ultra_log_mb=payload.max_ultra_log_mb,
        ultra_log_dir=payload.ultra_log_dir or "",
        actor_user_id=current_admin.id,
    )

    create_audit_log(
        db,
        action="ultra_log_activated",
        entity_type="ultra_log",
        entity_id=row.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "duration_option": payload.duration_option,
            "max_normal_log_mb": payload.max_normal_log_mb,
            "max_ultra_log_mb": payload.max_ultra_log_mb,
            "ultra_log_dir": payload.ultra_log_dir or "",
        },
    )
    return UltraLogStatusResponse(**ultra_log_status(db))


@router.post("/deactivate", response_model=UltraLogStatusResponse)
def deactivate_ultra_log_endpoint(
    payload: UltraLogDeactivateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = deactivate_ultra_log(db, reason=payload.reason, actor_user_id=current_admin.id)
    create_audit_log(
        db,
        action="ultra_log_deactivated",
        entity_type="ultra_log",
        entity_id=row.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"reason": payload.reason},
    )
    return UltraLogStatusResponse(**ultra_log_status(db))


@router.get("/events", response_model=list[UltraLogEventResponse])
def get_ultra_log_events(
    limit: int = Query(default=200, ge=10, le=2000),
    category: str = Query(default="", max_length=40),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_ultra_log_events(db, limit=limit, category=category)
