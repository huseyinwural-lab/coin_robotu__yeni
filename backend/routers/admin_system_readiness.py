from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from schemas import ProdConfigRemediationStateResponse, ProdConfigSaveRequest
from services.audit_service import create_audit_log
from services.futures_live_readiness_service import get_futures_live_readiness, get_futures_readiness_score
from services.prod_config_remediation_service import (
    build_masked_update_preview,
    build_prod_config_remediation_state,
    remediation_summary_for_audit,
    save_prod_config_updates,
    validate_prod_config_updates,
)
from services.pipeline.runtime import pipeline_runtime

router = APIRouter(prefix="/admin/system", tags=["admin_system_readiness"])


@router.get("/live-readiness")
def system_live_readiness(refresh: bool = False, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    payload = get_futures_live_readiness(db, pipeline_runtime.cache, current_admin.id, refresh=refresh)
    create_audit_log(
        db,
        action="SYSTEM_LIVE_READINESS_VIEWED",
        entity_type="system_live_readiness",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning" if payload.get("readiness_state") != "READY" else "info",
        details={"readiness_score": payload.get("readiness_score", 0.0), "readiness_state": payload.get("readiness_state")},
    )
    return payload


@router.get("/readiness-score")
def system_readiness_score(refresh: bool = False, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    payload = get_futures_readiness_score(db, pipeline_runtime.cache, current_admin.id, refresh=refresh)
    create_audit_log(
        db,
        action="SYSTEM_READINESS_SCORE_VIEWED",
        entity_type="system_readiness_score",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning" if payload.get("readiness_state") != "READY" else "info",
        details={"readiness_score": payload.get("readiness_score", 0.0), "readiness_state": payload.get("readiness_state")},
    )
    return payload


@router.get("/remediate-config", response_model=ProdConfigRemediationStateResponse)
def prod_config_remediation_state(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    payload = build_prod_config_remediation_state(db)
    return ProdConfigRemediationStateResponse(**payload)


@router.post("/remediate-config", response_model=ProdConfigRemediationStateResponse)
def prod_config_remediate(
    request: ProdConfigSaveRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    updates, validation_errors = validate_prod_config_updates(request.model_dump())
    if validation_errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"validation_errors": validation_errors},
        )

    changed_keys, _ = save_prod_config_updates(updates)
    if updates:
        create_audit_log(
            db,
            action="PROD_CONFIG_SAVED",
            entity_type="system_config",
            entity_id="prod_runtime",
            actor_user_id=current_admin.id,
            actor_role=current_admin.role.value,
            severity="warning",
            details={
                "changed_keys": changed_keys,
                "masked_updates": build_masked_update_preview(updates),
            },
        )

    state = build_prod_config_remediation_state(db)
    create_audit_log(
        db,
        action="PROD_PREFLIGHT_RUN",
        entity_type="system_config",
        entity_id="prod_runtime",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info" if state.get("release_gate_status") == "PASS" else "warning",
        details=remediation_summary_for_audit(state),
    )

    return ProdConfigRemediationStateResponse(**state)
