from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models import User, UserOnboardingProfile, UserOnboardingWorkflowCase, UserOnboardingWorkflowStepLog, UserRole
from services.onboarding_approval_service import build_onboarding_context


WORKFLOW_STEPS = ["ops", "risk", "final"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sla_minutes() -> int:
    return max(5, int(os.getenv("ONBOARDING_WORKFLOW_SLA_MINUTES", "30") or "30"))


def _priority_score(context: dict) -> float:
    risk = float(context.get("risk_score") or 0)
    aml = str(context.get("aml_flag") or "clear")
    base = risk
    if aml in {"blacklist", "sanction_hit"}:
        base += 40
    if bool(context.get("approval_disabled", False)):
        base += 10
    return round(base, 2)


def _priority_level(risk_score: float) -> str:
    value = float(risk_score or 0)
    if value >= 70:
        return "HIGH"
    if value >= 35:
        return "NORMAL"
    return "LOW"


def _require_user(db: Session, user_id: str) -> User:
    row = db.query(User).filter(User.id == user_id, User.role == UserRole.USER).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    return row


def _next_step(current_step: str) -> str | None:
    try:
        index = WORKFLOW_STEPS.index(current_step)
    except ValueError:
        return None
    if index + 1 >= len(WORKFLOW_STEPS):
        return None
    return WORKFLOW_STEPS[index + 1]


def get_workflow_case(db: Session, user_id: str) -> UserOnboardingWorkflowCase | None:
    return db.query(UserOnboardingWorkflowCase).filter(UserOnboardingWorkflowCase.user_id == user_id).first()


def start_workflow_case(db: Session, *, user_id: str, assigned_admin_id: str | None, actor: User) -> UserOnboardingWorkflowCase:
    _require_user(db, user_id)
    context = build_onboarding_context(db, user_id)
    priority = _priority_score(context)
    case = get_workflow_case(db, user_id)
    if case is None:
        case = UserOnboardingWorkflowCase(user_id=user_id)
        db.add(case)

    case.workflow_status = "active"
    case.current_step = "ops"
    case.assigned_admin_id = assigned_admin_id or actor.id
    if not case.assigned_admin_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="assigned_to_required")
    case.priority_score = priority
    case.sla_due_at = _now() + timedelta(minutes=_sla_minutes())
    case.supervisor_queue = False
    case.workflow_metadata = {
        "started_by": actor.id,
        "decision_support": context.get("decision_support") or {},
    }
    db.commit()
    db.refresh(case)
    return case


def assign_workflow_owner(db: Session, *, user_id: str, assigned_admin_id: str, actor: User) -> UserOnboardingWorkflowCase:
    if not str(assigned_admin_id or "").strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="assigned_to_required")
    case = get_workflow_case(db, user_id)
    if case is None:
        case = start_workflow_case(db, user_id=user_id, assigned_admin_id=assigned_admin_id, actor=actor)
    case.assigned_admin_id = assigned_admin_id
    case.supervisor_queue = False
    case.workflow_metadata = {
        **(case.workflow_metadata or {}),
        "last_assigned_by": actor.id,
        "last_assigned_at": _now().isoformat(),
    }
    db.commit()
    db.refresh(case)
    return case


def complete_workflow_step(
    db: Session,
    *,
    user_id: str,
    step_name: str,
    actor: User,
    note: str | None,
) -> UserOnboardingWorkflowCase:
    case = get_workflow_case(db, user_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workflow_case_not_found")

    normalized_step = str(step_name or "").strip().lower()
    if normalized_step not in WORKFLOW_STEPS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_workflow_step")

    if normalized_step != case.current_step:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="workflow_step_sequence_violation")

    db.add(
        UserOnboardingWorkflowStepLog(
            workflow_case_id=case.id,
            user_id=user_id,
            step_name=normalized_step,
            step_status="completed",
            actor_user_id=actor.id,
            note=note,
        )
    )

    next_step = _next_step(normalized_step)
    if next_step is None:
        case.workflow_status = "completed"
        case.current_step = "completed"
        case.sla_due_at = None
        case.supervisor_queue = False
    else:
        case.workflow_status = "active"
        case.current_step = next_step
        case.sla_due_at = _now() + timedelta(minutes=_sla_minutes())
        case.supervisor_queue = False
    db.commit()
    db.refresh(case)
    return case


def list_priority_queue(db: Session, *, assigned_admin_id: str | None = None) -> list[dict]:
    query = db.query(UserOnboardingWorkflowCase).filter(UserOnboardingWorkflowCase.workflow_status == "active")
    if assigned_admin_id:
        query = query.filter(UserOnboardingWorkflowCase.assigned_admin_id == assigned_admin_id)
    rows = query.all()
    user_ids = [row.user_id for row in rows]
    risk_map: dict[str, float] = {}
    if user_ids:
        profile_rows = (
            db.query(UserOnboardingProfile.user_id, UserOnboardingProfile.risk_score)
            .filter(UserOnboardingProfile.user_id.in_(user_ids))
            .all()
        )
        for user_id, risk_score in profile_rows:
            risk_map[str(user_id)] = float(risk_score or 0)

    far_future = datetime.max.replace(tzinfo=timezone.utc)
    rows = sorted(
        rows,
        key=lambda row: (
            -(risk_map.get(str(row.user_id), 0.0)),
            row.sla_due_at if row.sla_due_at is not None else far_future,
        ),
    )

    payload = []
    for row in rows:
        risk_score = float(risk_map.get(str(row.user_id), 0.0))
        payload.append(
            {
                "workflow_case_id": row.id,
                "user_id": row.user_id,
                "current_step": row.current_step,
                "assigned_admin_id": row.assigned_admin_id,
                "assigned_to": row.assigned_admin_id,
                "priority_score": row.priority_score,
                "risk_score": risk_score,
                "priority_level": _priority_level(risk_score),
                "sla_due_at": row.sla_due_at.isoformat() if row.sla_due_at else None,
                "supervisor_queue": row.supervisor_queue,
                "workflow_status": row.workflow_status,
                "escalation_count": int(row.escalation_count or 0),
            }
        )
    return payload


def escalate_timed_out_cases(db: Session, *, actor: User, supervisor_admin_id: str | None = None) -> dict:
    now = _now()
    rows = (
        db.query(UserOnboardingWorkflowCase)
        .filter(
            UserOnboardingWorkflowCase.workflow_status == "active",
            UserOnboardingWorkflowCase.sla_due_at.is_not(None),
            UserOnboardingWorkflowCase.sla_due_at <= now,
        )
        .all()
    )
    escalated = 0
    for row in rows:
        row.workflow_status = "escalated"
        row.escalated_at = now
        row.escalation_count = int(row.escalation_count or 0) + 1
        row.supervisor_queue = True
        row.assigned_admin_id = supervisor_admin_id or row.assigned_admin_id
        row.sla_due_at = now + timedelta(minutes=_sla_minutes())
        db.add(
            UserOnboardingWorkflowStepLog(
                workflow_case_id=row.id,
                user_id=row.user_id,
                step_name=row.current_step,
                step_status="escalated",
                actor_user_id=actor.id,
                note="sla_timeout_escalation",
            )
        )
        escalated += 1
    db.commit()
    return {"escalated": escalated, "at": now.isoformat()}


def escalate_workflow_case(
    db: Session,
    *,
    user_id: str,
    actor: User,
    supervisor_admin_id: str | None = None,
    note: str | None = None,
    force: bool = True,
) -> UserOnboardingWorkflowCase:
    case = get_workflow_case(db, user_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workflow_case_not_found")
    if str(case.workflow_status or "") == "completed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="workflow_case_completed")

    now = _now()
    is_timed_out = bool(case.sla_due_at and case.sla_due_at <= now)
    if not is_timed_out and not force:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="workflow_case_not_timed_out")

    case.workflow_status = "escalated"
    case.escalated_at = now
    case.escalation_count = int(case.escalation_count or 0) + 1
    case.supervisor_queue = True
    case.assigned_admin_id = supervisor_admin_id or case.assigned_admin_id
    if not case.assigned_admin_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="assigned_to_required")
    case.sla_due_at = now + timedelta(minutes=_sla_minutes())

    db.add(
        UserOnboardingWorkflowStepLog(
            workflow_case_id=case.id,
            user_id=case.user_id,
            step_name=case.current_step,
            step_status="escalated",
            actor_user_id=actor.id,
            note=(note or "manual_escalation")[:500],
        )
    )
    db.commit()
    db.refresh(case)
    return case


def list_workflow_admin_candidates(db: Session) -> list[dict]:
    rows = (
        db.query(User)
        .filter(User.role.in_([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPS]), User.is_active.is_(True))
        .order_by(User.email.asc())
        .all()
    )
    payload: list[dict] = []
    for row in rows:
        payload.append(
            {
                "id": row.id,
                "email": row.email,
                "role": row.role.value if hasattr(row.role, "value") else str(row.role),
            }
        )
    return payload
