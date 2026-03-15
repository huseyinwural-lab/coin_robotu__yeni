from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from db import get_db, redis_client
from deps import require_admin
from models import User
from services.audit_service import create_audit_log
from services.execution_quality_calibration_service import (
    calibrate_execution_quality_thresholds,
    get_latest_execution_quality_calibration,
)
from services.risk_engine_service import (
    build_admin_risk_status,
    load_risk_config,
    patch_risk_config,
    reload_risk_config,
    rollback_risk_config,
)


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
    current = load_risk_config(redis_client)
    try:
        updated = patch_risk_config(redis_client, payload or {}, changed_by=current_admin.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "rejected",
                "reason": str(exc),
                "safe_bounds": {
                    "max_risk_per_trade_pct": 5.0,
                    "max_total_exposure_pct": 50.0,
                    "max_leverage": 10,
                },
            },
        )

    create_audit_log(
        db,
        action="admin_risk_config_updated",
        entity_type="risk_config",
        entity_id="global",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "config_version": int(updated.get("config_version") or 0),
            "changed_by": current_admin.id,
            "changed_at": updated.get("changed_at"),
            "updated_keys": sorted(list((payload or {}).keys())),
            "old_values": {key: current.get(key) for key in (payload or {}).keys()},
            "new_values": {key: updated.get(key) for key in (payload or {}).keys()},
        },
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


@router.post("/config/rollback")
def rollback_config(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    payload = rollback_risk_config(redis_client, changed_by=current_admin.id)
    create_audit_log(
        db,
        action="admin_risk_config_rollback",
        entity_type="risk_config",
        entity_id="global",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "config_version": int(payload.get("config_version") or 0),
            "changed_by": current_admin.id,
            "changed_at": payload.get("changed_at"),
            "rollback": True,
        },
    )
    return payload


@router.get("/status")
def risk_status(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    return build_admin_risk_status(db, redis_client)


@router.post("/execution-quality/calibrate")
def calibrate_execution_quality(
    sample_size: int = 400,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    report = calibrate_execution_quality_thresholds(db, redis_client, sample_size=max(50, min(int(sample_size), 2000)))
    recommended = report.get("recommended_thresholds") or {}
    if report.get("status") in {"calibrated", "policy_documented_warning"} and recommended:
        patch_payload = {
            "execution_quality_threshold": recommended.get("execution_quality_threshold"),
            "spread_threshold_bps": recommended.get("spread_threshold_bps"),
            "stale_data_threshold_ms": recommended.get("stale_data_threshold_ms"),
        }
        patch_risk_config(redis_client, patch_payload, changed_by=current_admin.id)
    create_audit_log(
        db,
        action="admin_risk_execution_quality_calibrated",
        entity_type="risk_config",
        entity_id="global",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "sample_size": int((report.get("dataset") or {}).get("sample_size") or 0),
            "false_allow_rate": report.get("false_allow_rate"),
            "false_block_rate": report.get("false_block_rate"),
            "false_reduce_rate": report.get("false_reduce_rate"),
            "recommended_thresholds": recommended,
        },
    )
    return report


@router.get("/execution-quality/calibration")
def latest_execution_quality_calibration(current_admin: User = Depends(require_admin)):
    _ = current_admin
    return get_latest_execution_quality_calibration(redis_client)
