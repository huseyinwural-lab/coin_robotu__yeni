from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from db import get_db, redis_client
from deps import require_admin
from models import User
from services.audit_service import create_audit_log
from services.risk_engine_service import build_admin_risk_status, load_risk_config, patch_risk_config, reload_risk_config


router = APIRouter(prefix="/admin/risk", tags=["admin_risk_config"])


@router.get("/config")
def get_risk_config(current_admin: User = Depends(require_admin)):
    _ = current_admin
    return load_risk_config(redis_client)


@router.patch("/config")
def update_risk_config(
    payload: dict = Body(default={}),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    updated = patch_risk_config(redis_client, payload or {})
    create_audit_log(
        db,
        action="admin_risk_config_updated",
        entity_type="risk_config",
        entity_id="global",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"updated_keys": sorted(list((payload or {}).keys()))},
    )
    return updated


@router.post("/config/reload")
def reload_config(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    payload = reload_risk_config(redis_client)
    create_audit_log(
        db,
        action="admin_risk_config_reloaded",
        entity_type="risk_config",
        entity_id="global",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"status": "reloaded"},
    )
    return payload


@router.get("/status")
def risk_status(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    return build_admin_risk_status(db, redis_client)
