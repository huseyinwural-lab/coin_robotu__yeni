from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from services.audit_service import create_audit_log
from services.futures_testnet_control_service import (
    build_testnet_execution_quality,
    build_testnet_execution_quality_rolling_7d,
    build_testnet_release_gate_status,
    build_testnet_status,
)
from services.pipeline.runtime import pipeline_runtime

router = APIRouter(prefix="/admin/futures/testnet", tags=["admin_futures_testnet_control"])


@router.get("/status")
def futures_testnet_status(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    status = build_testnet_status(db, pipeline_runtime.cache, current_admin.id)
    create_audit_log(
        db,
        action="FUTURES_TESTNET_STATUS_VIEWED",
        entity_type="futures_testnet_status",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={
            "testnet_enabled": status.get("testnet_enabled", False),
            "gate_status": (status.get("release_gate") or {}).get("status", "BLOCKED"),
        },
    )
    return status


@router.get("/release-gate")
def futures_testnet_release_gate(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    gate = build_testnet_release_gate_status(db)
    create_audit_log(
        db,
        action="FUTURES_TESTNET_RELEASE_GATE_VIEWED",
        entity_type="futures_testnet_release_gate",
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
def futures_testnet_execution_quality(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    payload = build_testnet_execution_quality(db, pipeline_runtime.cache, current_admin.id)
    create_audit_log(
        db,
        action="FUTURES_TESTNET_EXECUTION_QUALITY_VIEWED",
        entity_type="futures_testnet_execution_quality",
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
def futures_testnet_execution_quality_rolling(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    payload = build_testnet_execution_quality_rolling_7d(db, pipeline_runtime.cache, current_admin.id)
    create_audit_log(
        db,
        action="FUTURES_TESTNET_EXECUTION_QUALITY_ROLLING_VIEWED",
        entity_type="futures_testnet_execution_quality_rolling",
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
