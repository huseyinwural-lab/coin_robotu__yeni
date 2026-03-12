from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from services.audit_service import create_audit_log
from services.futures_strategy_service import get_futures_decision_diagnostics
from services.pipeline.runtime import pipeline_runtime

router = APIRouter(prefix="/admin/futures", tags=["admin_futures_decision_diagnostics"])


@router.get("/decision-diagnostics")
def futures_decision_diagnostics(
    refresh: bool = False,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    diagnostics = get_futures_decision_diagnostics(db, pipeline_runtime.cache, current_admin.id, refresh=refresh)
    create_audit_log(
        db,
        action="FUTURES_DECISION_DIAGNOSTICS_VIEWED",
        entity_type="futures_decision_diagnostics",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={
            "false_allow_count": diagnostics.get("false_allow_count", 0),
            "false_reject_count": diagnostics.get("false_reject_count", 0),
            "gate_reason_distribution_size": len(diagnostics.get("gate_reason_distribution") or {}),
        },
    )
    return diagnostics
