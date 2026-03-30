import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
from deps import get_current_user, is_admin_role
from models import RiskPolicy, User
from schemas import RiskPolicyCreate, RiskPolicyResponse, RiskPolicyUpdate
from services.audit_service import build_critical_action_details, create_audit_log


class RiskPolicyReasonRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=400)


class RiskPolicyPreviewRequest(BaseModel):
    current_daily_pnl_pct: float = 0.0
    current_open_positions: int = 0
    current_leverage: int = 1
    current_spread_bps: float = 0.0
    current_slippage_bps: float = 0.0

router = APIRouter(prefix="/risk-policies", tags=["risk_policies"])


def _authorized_risk_query(db: Session, policy_id: str, current_user: User):
    query = db.query(RiskPolicy).filter(RiskPolicy.id == policy_id)
    if not is_admin_role(current_user.role):
        query = query.filter(RiskPolicy.user_id == current_user.id)
    return query


def _now():
    return datetime.now(timezone.utc)


def _serialize_policy(row: RiskPolicy) -> RiskPolicyResponse:
    return RiskPolicyResponse.model_validate(row)


def _active_policy(db: Session, user_id: str) -> RiskPolicy | None:
    return (
        db.query(RiskPolicy)
        .filter(RiskPolicy.user_id == user_id, RiskPolicy.is_active.is_(True))
        .order_by(RiskPolicy.activated_at.desc().nullslast(), RiskPolicy.updated_at.desc())
        .first()
    )


def _policy_preview(row: RiskPolicy, payload: RiskPolicyPreviewRequest) -> dict:
    projected_position_size = round(10000 * (float(row.position_size_pct or 0.0) / 100.0), 4)
    daily_loss_cutoff_hit = float(payload.current_daily_pnl_pct or 0.0) >= float(row.daily_loss_cutoff_pct or 0.0)
    concurrent_trade_capacity = max(int(row.max_open_positions or 0) - int(payload.current_open_positions or 0), 0)
    spread_block_risk = float(payload.current_spread_bps or 0.0) > float(row.spread_limit_bps or 0.0)
    slippage_block_risk = float(payload.current_slippage_bps or 0.0) > float(row.slippage_limit_bps or 0.0)
    leverage_block_risk = int(payload.current_leverage or 1) > int(row.max_leverage or 1)
    return {
        "position_size_effect": projected_position_size,
        "daily_loss_cutoff_effect": {"limit_pct": row.daily_loss_cutoff_pct, "would_block": daily_loss_cutoff_hit},
        "concurrent_trades_effect": {"limit": row.max_open_positions, "remaining_capacity": concurrent_trade_capacity},
        "leverage_cap_effect": {"limit": row.max_leverage, "current": payload.current_leverage, "would_block": leverage_block_risk},
        "spread_slippage_risk": {"spread_block": spread_block_risk, "slippage_block": slippage_block_risk},
        "estimated_trade_capacity": concurrent_trade_capacity,
    }


def _policy_status_reason(row: RiskPolicy, active_row: RiskPolicy | None) -> str:
    if row.is_active:
        return row.status_reason or "active_policy_selected"
    if row.lifecycle_state == "rolled_back":
        return "disabled_due_to_rollback"
    if active_row and active_row.version_group_id == row.version_group_id and active_row.id != row.id:
        return "replaced_by_newer_version"
    return row.status_reason or "policy_draft_only"


@router.get("", response_model=list[RiskPolicyResponse])
def list_risk_policies(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(RiskPolicy)
    if not is_admin_role(current_user.role):
        query = query.filter(RiskPolicy.user_id == current_user.id)
    rows = query.order_by(RiskPolicy.is_active.desc(), RiskPolicy.updated_at.desc()).all()
    active_row = _active_policy(db, current_user.id)
    for row in rows:
        row.status_reason = _policy_status_reason(row, active_row)
    return [_serialize_policy(row) for row in rows]


@router.post("", response_model=RiskPolicyResponse)
def create_risk_policy(
    payload: RiskPolicyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = payload.model_dump(exclude={"reason_note"})
    risk_policy = RiskPolicy(user_id=current_user.id, version_group_id=str(uuid.uuid4()), version_num=1, lifecycle_state="draft", is_active=False, status_reason="policy_draft_only", metadata_json={"history": []}, **data)
    db.add(risk_policy)
    db.commit()
    db.refresh(risk_policy)

    create_audit_log(
        db,
        action="risk_policy_created",
        entity_type="risk_policy",
        entity_id=risk_policy.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details=build_critical_action_details(actor=current_user.id, reason=payload.reason_note or "create", scope="risk_policy:create", before_state={}, after_state={"policy_id": risk_policy.id}),
    )
    return _serialize_policy(risk_policy)


@router.put("/{policy_id}", response_model=RiskPolicyResponse)
def update_risk_policy(
    policy_id: str,
    payload: RiskPolicyUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    risk_policy = _authorized_risk_query(db, policy_id, current_user).first()
    if risk_policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk policy not found")

    next_version = int(risk_policy.version_num or 1) + 1
    data = payload.model_dump(exclude={"reason_note"})
    new_row = RiskPolicy(
        user_id=risk_policy.user_id,
        version_group_id=risk_policy.version_group_id,
        version_num=next_version,
        lifecycle_state="draft",
        is_active=False,
        status_reason="policy_draft_only",
        metadata_json={
            "history": [
                {"changed_at": _now().isoformat(), "changed_by": current_user.id, "reason": payload.reason_note or "update", "from_policy_id": risk_policy.id}
            ],
            "previous_policy_id": risk_policy.id,
        },
        **data,
    )
    db.add(new_row)
    db.commit()
    db.refresh(new_row)
    create_audit_log(
        db,
        action="risk_policy_updated",
        entity_type="risk_policy",
        entity_id=new_row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details=build_critical_action_details(actor=current_user.id, reason=payload.reason_note or "update", scope="risk_policy:update", before_state={"policy_id": risk_policy.id, "version": risk_policy.version_num}, after_state={"policy_id": new_row.id, "version": new_row.version_num}),
    )
    return _serialize_policy(new_row)


@router.post("/{policy_id}/preview-impact")
def preview_risk_policy_impact(policy_id: str, payload: RiskPolicyPreviewRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    risk_policy = _authorized_risk_query(db, policy_id, current_user).first()
    if risk_policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk policy not found")
    return _policy_preview(risk_policy, payload)


@router.post("/{policy_id}/activate", response_model=RiskPolicyResponse)
def activate_risk_policy(policy_id: str, payload: RiskPolicyReasonRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    risk_policy = _authorized_risk_query(db, policy_id, current_user).first()
    if risk_policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk policy not found")
    db.query(RiskPolicy).filter(RiskPolicy.user_id == current_user.id).update({RiskPolicy.is_active: False})
    risk_policy.is_active = True
    risk_policy.lifecycle_state = "active"
    risk_policy.activated_at = _now()
    risk_policy.activated_by = current_user.id
    risk_policy.status_reason = "active_policy_selected"
    risk_policy.metadata_json = {**(risk_policy.metadata_json or {}), "enforce": {"last_enforced_at": _now().isoformat(), "last_reject_reason": None, "max_daily_loss_hit_count": 0, "concurrent_trade_block_count": 0, "spread_slippage_block_count": 0, "effective_config_source": "active_policy"}}
    db.commit()
    db.refresh(risk_policy)
    create_audit_log(db, action="risk_policy_activated", entity_type="risk_policy", entity_id=risk_policy.id, actor_user_id=current_user.id, actor_role=current_user.role.value, details=build_critical_action_details(actor=current_user.id, reason=payload.reason, scope="risk_policy:activate", before_state={}, after_state={"policy_id": risk_policy.id, "version": risk_policy.version_num}))
    return _serialize_policy(risk_policy)


@router.get("/{policy_id}/history")
def risk_policy_history(policy_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    risk_policy = _authorized_risk_query(db, policy_id, current_user).first()
    if risk_policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk policy not found")
    rows = db.query(RiskPolicy).filter(RiskPolicy.version_group_id == risk_policy.version_group_id).order_by(RiskPolicy.version_num.desc()).all()
    return {"items": [_serialize_policy(row).model_dump() for row in rows]}


@router.post("/{policy_id}/rollback", response_model=RiskPolicyResponse)
def rollback_risk_policy(policy_id: str, payload: RiskPolicyReasonRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    risk_policy = _authorized_risk_query(db, policy_id, current_user).first()
    if risk_policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk policy not found")
    previous_id = (risk_policy.metadata_json or {}).get("previous_policy_id")
    if not previous_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="rollback_target_missing")
    target = _authorized_risk_query(db, previous_id, current_user).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="rollback_target_not_found")
    db.query(RiskPolicy).filter(RiskPolicy.user_id == current_user.id).update({RiskPolicy.is_active: False})
    target.is_active = True
    target.lifecycle_state = "active"
    target.activated_at = _now()
    target.activated_by = current_user.id
    target.status_reason = "rollback_applied"
    risk_policy.lifecycle_state = "rolled_back"
    db.commit()
    db.refresh(target)
    create_audit_log(db, action="risk_policy_rollback", entity_type="risk_policy", entity_id=target.id, actor_user_id=current_user.id, actor_role=current_user.role.value, details=build_critical_action_details(actor=current_user.id, reason=payload.reason, scope="risk_policy:rollback", before_state={"rolled_back_policy": risk_policy.id}, after_state={"active_policy": target.id}))
    return _serialize_policy(target)