from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db import get_db
from deps import get_current_user, is_admin_role
from models import RiskPolicy, User
from schemas import RiskPolicyCreate, RiskPolicyResponse, RiskPolicyUpdate
from services.audit_service import create_audit_log

router = APIRouter(prefix="/risk-policies", tags=["risk_policies"])


def _authorized_risk_query(db: Session, policy_id: str, current_user: User):
    query = db.query(RiskPolicy).filter(RiskPolicy.id == policy_id)
    if not is_admin_role(current_user.role):
        query = query.filter(RiskPolicy.user_id == current_user.id)
    return query


@router.get("", response_model=list[RiskPolicyResponse])
def list_risk_policies(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(RiskPolicy)
    if not is_admin_role(current_user.role):
        query = query.filter(RiskPolicy.user_id == current_user.id)
    return query.order_by(RiskPolicy.created_at.desc()).all()


@router.post("", response_model=RiskPolicyResponse)
def create_risk_policy(
    payload: RiskPolicyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    risk_policy = RiskPolicy(user_id=current_user.id, **payload.model_dump())
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
        details={"name": risk_policy.name},
    )
    return risk_policy


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

    for key, value in payload.model_dump().items():
        setattr(risk_policy, key, value)

    db.commit()
    db.refresh(risk_policy)
    create_audit_log(
        db,
        action="risk_policy_updated",
        entity_type="risk_policy",
        entity_id=risk_policy.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"name": risk_policy.name},
    )
    return risk_policy