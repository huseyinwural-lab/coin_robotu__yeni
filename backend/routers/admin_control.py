from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db import get_db, redis_client
from deps import require_admin
from models import AdminControl, User
from schemas import AdminControlResponse, AdminControlUpdate, KillSwitchStatusResponse, UniversePreviewResponse
from services.audit_service import create_audit_log
from services.pipeline.kill_switch_service import kill_switch_state, reset_kill_switch
from services.pipeline.runtime import pipeline_runtime
from services.pipeline.universe_engine import build_effective_universe

router = APIRouter(prefix="/admin-control", tags=["admin_control"])


def _get_control(db: Session) -> AdminControl:
    control = db.query(AdminControl).filter(AdminControl.id == "global").first()
    if control is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin control not initialized")
    return control


@router.get("", response_model=AdminControlResponse)
def get_admin_control(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _get_control(db)


@router.put("", response_model=AdminControlResponse)
def update_admin_control(
    payload: AdminControlUpdate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    control = _get_control(db)
    for key, value in payload.model_dump().items():
        setattr(control, key, value)
    db.commit()
    db.refresh(control)

    build_effective_universe(db, redis_client)
    create_audit_log(
        db,
        action="admin_control_updated",
        entity_type="admin_control",
        entity_id=control.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"max_leverage_cap": control.max_leverage_cap, "disable_futures": control.disable_futures},
    )
    return control


@router.get("/universe/preview", response_model=UniversePreviewResponse)
def preview_universe(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    payload = build_effective_universe(db, redis_client)
    return UniversePreviewResponse(
        spot_symbols=payload["spot_symbols"],
        futures_symbols=payload["futures_symbols"],
        filters=payload["filters"],
        generated_at=datetime.now(timezone.utc),
    )


@router.get("/kill-switch/status", response_model=KillSwitchStatusResponse)
def read_kill_switch_status(_: User = Depends(require_admin)):
    return KillSwitchStatusResponse(**kill_switch_state(pipeline_runtime.cache))


@router.post("/kill-switch/reset", response_model=KillSwitchStatusResponse)
def admin_reset_kill_switch(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    payload = reset_kill_switch(db, pipeline_runtime.cache)
    create_audit_log(
        db,
        action="kill_switch_reset",
        entity_type="kill_switch",
        entity_id="global",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={"status": "reset"},
    )
    return KillSwitchStatusResponse(**payload)