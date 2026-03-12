from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from services.audit_service import create_audit_log
from services.futures_strategy_service import get_futures_strategy_status, run_futures_strategy_paper_cycle
from services.pipeline.runtime import pipeline_runtime

router = APIRouter(prefix="/admin/futures/strategy", tags=["admin_futures_strategy"])


@router.get("/status")
def futures_strategy_status(
    refresh: bool = False,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    status = get_futures_strategy_status(db, pipeline_runtime.cache, current_admin.id, refresh=refresh)
    create_audit_log(
        db,
        action="FUTURES_STRATEGY_STATUS_VIEWED",
        entity_type="futures_strategy_status",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={
            "signals": (status.get("metrics") or {}).get("futures_strategy_signal_total", 0),
            "allowed": (status.get("metrics") or {}).get("futures_strategy_allowed_total", 0),
            "rejected": (status.get("metrics") or {}).get("futures_strategy_rejected_total", 0),
        },
    )
    return status


@router.post("/run-paper-cycle")
def run_futures_strategy_cycle(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    status = run_futures_strategy_paper_cycle(db, pipeline_runtime.cache, current_admin.id)
    create_audit_log(
        db,
        action="FUTURES_STRATEGY_PAPER_CYCLE_RUN",
        entity_type="futures_strategy_cycle",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={
            "strategy": status.get("strategy"),
            "signals": (status.get("metrics") or {}).get("futures_strategy_signal_total", 0),
            "allowed": (status.get("metrics") or {}).get("futures_strategy_allowed_total", 0),
        },
    )
    return status
