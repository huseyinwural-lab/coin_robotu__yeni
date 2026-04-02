from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from services.audit_service import create_audit_log
from services.futures_live_control_service import (
    build_live_execution_quality,
    build_live_execution_quality_rolling_7d,
    build_live_release_gate_status,
    build_live_status,
)
from services.pipeline.runtime import pipeline_runtime

router = APIRouter(prefix="/admin/futures/live", tags=["admin_futures_live_control"])


@router.get("/status")
def futures_live_status(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    status = build_live_status(db, pipeline_runtime.cache, current_admin.id)
    create_audit_log(
        db,
        action="FUTURES_LIVE_STATUS_VIEWED",
        entity_type="futures_live_status",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={
            "live_enabled": status.get("live_enabled", False),
            "gate_status": (status.get("release_gate") or {}).get("status", "BLOCKED"),
        },
    )
    return status


@router.get("/release-gate")
def futures_live_release_gate(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    gate = build_live_release_gate_status(db)
    create_audit_log(
        db,
        action="FUTURES_LIVE_RELEASE_GATE_VIEWED",
        entity_type="futures_live_release_gate",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning" if gate.get("status") == "BLOCKED" else "info",
        details={
            "status": gate.get("status"),
            "order_path_open": gate.get("order_path_open", False),
            "reasons": gate.get("reasons", []),
        },
    )
    return gate


@router.get("/execution-quality")
def futures_live_execution_quality(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    payload = build_live_execution_quality(db, pipeline_runtime.cache, current_admin.id)
    create_audit_log(
        db,
        action="FUTURES_LIVE_EXECUTION_QUALITY_VIEWED",
        entity_type="futures_live_execution_quality",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={
            "reject_rate": payload.get("reject_rate", 0.0),
            "quality_score": payload.get("execution_quality_score", 0.0),
        },
    )
    return payload


@router.get("/execution-quality/rolling-7d")
def futures_live_execution_quality_rolling(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    payload = build_live_execution_quality_rolling_7d(db, pipeline_runtime.cache, current_admin.id)
    create_audit_log(
        db,
        action="FUTURES_LIVE_EXECUTION_QUALITY_ROLLING_VIEWED",
        entity_type="futures_live_execution_quality_rolling",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={
            "latest_score": payload.get("latest_score", 0.0),
            "point_count": len(payload.get("points", [])),
        },
    )
    return payload
