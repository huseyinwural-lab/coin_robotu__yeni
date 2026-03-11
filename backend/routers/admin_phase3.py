from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import BacktestResultCard, BotProfile, ExecutionPolicy, FailedEvent, RiskExposureGroup, User
from schemas import (
    BacktestResultCardCreate,
    BacktestResultCardResponse,
    BacktestResultCardUpdate,
    ExecutionPolicyCreate,
    ExecutionPolicyResponse,
    ExecutionStateTransitionResponse,
    ExecutionPolicyUpdate,
    FailedEventResponse,
    HardeningSummaryResponse,
    RiskExposureGroupCreate,
    RiskExposureGroupResponse,
    RiskExposureGroupUpdate,
    StateRebuildLogResponse,
)
from services.audit_service import create_audit_log
from services.execution_policy_service import get_policy_for_strategy
from services.failed_event_service import create_failed_event, mark_failed_event_resolved, mark_failed_event_retry
from services.pipeline.cache_store import incr_counter
from services.pipeline.execution_engine import open_paper_position
from services.pipeline.runtime import pipeline_runtime
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


@router.post("/failed-events/seed", response_model=FailedEventResponse)
def seed_failed_event(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    existing = db.query(FailedEvent).filter(FailedEvent.status.in_(["pending", "retrying"]))
    latest = existing.order_by(FailedEvent.created_at.desc()).first()
    if latest:
        return latest

    seeded = create_failed_event(
        db,
        event_type="seeded_failed_event",
        entity_type="phase3_admin",
        entity_id="seed",
        payload={"source": "manual_seed_button", "hint": "for retry/resolve UI validation"},
        error_message="Seeded failed event for deterministic admin UI testing",
    )
    create_audit_log(
        db,
        action="failed_event_seeded",
        entity_type="failed_event",
        entity_id=seeded.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"event_type": seeded.event_type},
    )
    return seeded


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


@router.get("/hardening-summary", response_model=HardeningSummaryResponse)
def get_hardening_summary(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return pipeline_runtime.hardening_summary(db)


@router.get("/execution-state-transitions", response_model=list[ExecutionStateTransitionResponse])
def list_execution_state_transitions(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=200, ge=20, le=500),
):
    return pipeline_runtime.list_execution_state_transitions(db, limit)


@router.post("/execution-state-transitions/simulate")
def simulate_execution_state_flow(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    strategy_type: str = Query(default="breakout"),
    symbol: str = Query(default="BTCUSDT"),
    side: str = Query(default="long"),
):
    bot = (
        db.query(BotProfile)
        .filter(BotProfile.strategy_type == strategy_type)
        .order_by(BotProfile.created_at.desc())
        .first()
    )
    if bot is None:
        bot = db.query(BotProfile).order_by(BotProfile.created_at.desc()).first()
    if bot is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No bot profile found for simulation")

    user = db.query(User).filter(User.id == bot.user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bot owner not found")

    policy = get_policy_for_strategy(db, strategy_type)
    execution_result = open_paper_position(
        db,
        user=user,
        bot=bot,
        symbol=symbol.upper(),
        direction=side.lower(),
        market_price=100.0,
        quantity=0.01,
        leverage=1,
        stop_loss=98.0 if side.lower() == "long" else 102.0,
        take_profit=104.0 if side.lower() == "long" else 96.0,
        execution_policy={
            "style": policy.execution_style,
            "order_preference": policy.order_preference,
            "timeout_seconds": policy.timeout_seconds,
            "fallback_behavior": policy.fallback_behavior,
            "partial_fill_tolerance_pct": policy.partial_fill_tolerance_pct,
            "execution_urgency": policy.execution_urgency,
            "retry_limit": policy.retry_limit,
        },
        response_payload={"mode": "simulation", "trigger": "admin_manual"},
    )

    create_audit_log(
        db,
        action="execution_state_simulated",
        entity_type="execution_event",
        entity_id=execution_result["execution_event"].id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"strategy_type": strategy_type, "final_state": execution_result["final_state"]},
    )
    incr_counter(pipeline_runtime.cache, "metrics:state_transitions:5m", execution_result["transition_count"])

    return {
        "execution_event_id": execution_result["execution_event"].id,
        "final_state": execution_result["final_state"],
        "state_path": execution_result["state_path"],
    }
