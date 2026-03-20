from datetime import timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from schemas import AdminCanaryStatusResponse, AdminKillSwitchRequest, AdminKillSwitchResponse
from services.execution_safety_service import canary_status_snapshot, execution_safety_snapshot, update_execution_safety_state

router = APIRouter(prefix="/admin", tags=["admin_execution_safety"])


def _to_response(snapshot: dict, *, reason_code: str, idempotent: bool) -> AdminKillSwitchResponse:
    config = snapshot["config"]
    updated_at = config.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return AdminKillSwitchResponse(
        trading_enabled=bool(snapshot["trading_enabled"]),
        max_total_exposure=float(snapshot["max_total_exposure"]),
        max_active_positions=int(snapshot["max_active_positions"]),
        current_total_exposure=float(snapshot["current_total_exposure"]),
        current_active_positions=int(snapshot["current_active_positions"]),
        open_positions_count=int(snapshot["open_positions_count"]),
        pending_user_intents_count=int(snapshot["pending_user_intents_count"]),
        pending_runtime_intents_count=int(snapshot["pending_runtime_intents_count"]),
        reason_code=reason_code,
        idempotent=idempotent,
        updated_at=updated_at,
    )


@router.post("/kill-switch", response_model=AdminKillSwitchResponse)
def set_kill_switch(
    payload: AdminKillSwitchRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    snapshot = update_execution_safety_state(
        db,
        trading_enabled=payload.trading_enabled,
        reason=payload.reason,
        requested_by=payload.requested_by,
        effective_at=payload.effective_at.isoformat() if payload.effective_at else None,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        max_total_exposure=payload.max_total_exposure,
        max_active_positions=payload.max_active_positions,
    )
    return _to_response(snapshot, reason_code=str(snapshot["reason_code"]), idempotent=bool(snapshot["idempotent"]))


@router.get("/kill-switch", response_model=AdminKillSwitchResponse)
def get_kill_switch_state(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    snapshot = execution_safety_snapshot(db)
    reason_code = "TRADING_ENABLED" if snapshot.get("trading_enabled") else "TRADING_DISABLED"
    return _to_response(snapshot, reason_code=reason_code, idempotent=True)


@router.get("/canary-status", response_model=AdminCanaryStatusResponse)
def get_canary_status(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    payload = canary_status_snapshot(db)
    return AdminCanaryStatusResponse(**payload)
