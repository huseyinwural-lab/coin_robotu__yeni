from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import BacktestResultCard, ExecutionPolicy, FailedEvent, RiskExposureGroup, User
from schemas import (
    BacktestResultCardCreate,
    BacktestResultCardResponse,
    BacktestResultCardUpdate,
    ExecutionPolicyCreate,
    ExecutionPolicyResponse,
    ExecutionPolicyUpdate,
    FailedEventResponse,
    RiskExposureGroupCreate,
    RiskExposureGroupResponse,
    RiskExposureGroupUpdate,
    StateRebuildLogResponse,
)
from services.audit_service import create_audit_log
from services.failed_event_service import mark_failed_event_resolved, mark_failed_event_retry
from services.state_rebuild_service import run_state_rebuild

router = APIRouter(prefix="/admin-phase3", tags=["admin_phase3"])


@router.get("/execution-policies", response_model=list[ExecutionPolicyResponse])
def list_execution_policies(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(ExecutionPolicy).order_by(ExecutionPolicy.strategy_type.asc()).all()


@router.post("/execution-policies", response_model=ExecutionPolicyResponse)
def create_execution_policy(
    payload: ExecutionPolicyCreate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    existing = db.query(ExecutionPolicy).filter(ExecutionPolicy.strategy_type == payload.strategy_type).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Policy already exists for strategy")
    policy = ExecutionPolicy(**payload.model_dump())
    db.add(policy)
    db.commit()
    db.refresh(policy)
    create_audit_log(
        db,
        action="execution_policy_created",
        entity_type="execution_policy",
        entity_id=policy.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"strategy_type": policy.strategy_type, "style": policy.execution_style},
    )
    return policy


@router.put("/execution-policies/{policy_id}", response_model=ExecutionPolicyResponse)
def update_execution_policy(
    policy_id: str,
    payload: ExecutionPolicyUpdate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    policy = db.query(ExecutionPolicy).filter(ExecutionPolicy.id == policy_id).first()
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution policy not found")
    for key, value in payload.model_dump().items():
        setattr(policy, key, value)
    db.commit()
    db.refresh(policy)
    create_audit_log(
        db,
        action="execution_policy_updated",
        entity_type="execution_policy",
        entity_id=policy.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"strategy_type": policy.strategy_type, "style": policy.execution_style},
    )
    return policy


@router.get("/exposure-groups", response_model=list[RiskExposureGroupResponse])
def list_exposure_groups(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(RiskExposureGroup).order_by(RiskExposureGroup.name.asc()).all()


@router.post("/exposure-groups", response_model=RiskExposureGroupResponse)
def create_exposure_group(
    payload: RiskExposureGroupCreate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    existing = db.query(RiskExposureGroup).filter(RiskExposureGroup.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Exposure group already exists")
    group = RiskExposureGroup(**payload.model_dump())
    db.add(group)
    db.commit()
    db.refresh(group)
    create_audit_log(
        db,
        action="exposure_group_created",
        entity_type="risk_exposure_group",
        entity_id=group.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"name": group.name},
    )
    return group


@router.put("/exposure-groups/{group_id}", response_model=RiskExposureGroupResponse)
def update_exposure_group(
    group_id: str,
    payload: RiskExposureGroupUpdate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    group = db.query(RiskExposureGroup).filter(RiskExposureGroup.id == group_id).first()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exposure group not found")
    for key, value in payload.model_dump().items():
        setattr(group, key, value)
    db.commit()
    db.refresh(group)
    create_audit_log(
        db,
        action="exposure_group_updated",
        entity_type="risk_exposure_group",
        entity_id=group.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"name": group.name},
    )
    return group


@router.get("/failed-events", response_model=list[FailedEventResponse])
def list_failed_events(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=200, ge=20, le=500),
):
    return db.query(FailedEvent).order_by(FailedEvent.created_at.desc()).limit(limit).all()


@router.post("/failed-events/{event_id}/retry", response_model=FailedEventResponse)
def retry_failed_event(event_id: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    failed_event = db.query(FailedEvent).filter(FailedEvent.id == event_id).first()
    if failed_event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Failed event not found")
    return mark_failed_event_retry(db, failed_event)


@router.post("/failed-events/{event_id}/resolve", response_model=FailedEventResponse)
def resolve_failed_event(event_id: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    failed_event = db.query(FailedEvent).filter(FailedEvent.id == event_id).first()
    if failed_event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Failed event not found")
    return mark_failed_event_resolved(db, failed_event)


@router.get("/state-rebuild-logs", response_model=list[StateRebuildLogResponse])
def list_state_rebuild_logs(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    from models import StateRebuildLog

    return db.query(StateRebuildLog).order_by(StateRebuildLog.started_at.desc()).limit(200).all()


@router.post("/state-rebuild/run", response_model=StateRebuildLogResponse)
def trigger_state_rebuild(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rebuild_log = run_state_rebuild(db, trigger_source="manual_admin")
    create_audit_log(
        db,
        action="state_rebuild_triggered",
        entity_type="state_rebuild",
        entity_id=rebuild_log.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"status": rebuild_log.status},
    )
    return rebuild_log


@router.get("/backtest-cards", response_model=list[BacktestResultCardResponse])
def list_backtest_cards(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(BacktestResultCard).order_by(BacktestResultCard.updated_at.desc()).all()


@router.post("/backtest-cards", response_model=BacktestResultCardResponse)
def create_backtest_card(
    payload: BacktestResultCardCreate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    card = BacktestResultCard(**payload.model_dump())
    db.add(card)
    db.commit()
    db.refresh(card)
    create_audit_log(
        db,
        action="backtest_card_created",
        entity_type="backtest_card",
        entity_id=card.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"strategy": card.strategy_type, "risk_label": card.risk_label},
    )
    return card


@router.put("/backtest-cards/{card_id}", response_model=BacktestResultCardResponse)
def update_backtest_card(
    card_id: str,
    payload: BacktestResultCardUpdate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    card = db.query(BacktestResultCard).filter(BacktestResultCard.id == card_id).first()
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest card not found")
    for key, value in payload.model_dump().items():
        setattr(card, key, value)
    db.commit()
    db.refresh(card)
    create_audit_log(
        db,
        action="backtest_card_updated",
        entity_type="backtest_card",
        entity_id=card.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"strategy": card.strategy_type, "risk_label": card.risk_label},
    )
    return card
