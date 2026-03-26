from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User, UserRole
from schemas import UserResponse
from services.audit_service import create_audit_log
from services.onboarding_approval_service import execute_onboarding_decision

router = APIRouter(prefix="/admin/user-approvals", tags=["user_approvals"])


def _apply_sort(query, sort_by: str, sort_dir: str):
    sort_dir = sort_dir.lower()
    if sort_by == "email":
        column = User.email
    else:
        column = User.approval_requested_at
    if sort_dir == "desc":
        return query.order_by(column.desc())
    return query.order_by(column.asc())


@router.get("", response_model=list[UserResponse])
def list_user_approvals(
    status_filter: str = Query(default="pending", alias="status"),
    search: str | None = None,
    sort_by: str = Query(default="requested_at"),
    sort_dir: str = Query(default="asc"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(User).filter(User.role == UserRole.USER)
    if status_filter in {"pending", "approved", "rejected"}:
        query = query.filter(User.approval_status == status_filter)
    if search:
        query = query.filter(User.email.ilike(f"%{search}%"))
    query = _apply_sort(query, sort_by, sort_dir)
    return query.all()


@router.get("/email-suggestions")
def user_approval_email_suggestions(
    query: str = Query(default="", min_length=0),
    limit: int = Query(default=8, ge=1, le=30),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = db.query(User).filter(User.role == UserRole.USER)
    normalized = query.strip()
    if normalized:
        q = q.filter(User.email.ilike(f"%{normalized}%"))
    rows = q.order_by(User.email.asc()).limit(limit).all()
    return {"suggestions": [row.email for row in rows]}


@router.post("/bulk-approve")
def bulk_approve(
    payload: dict,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="bulk_approve_disabled")


@router.post("/bulk-reject")
def bulk_reject(
    payload: dict,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    ids = payload.get("ids") or []
    reason = (payload.get("reason") or "").strip()
    confirm_token = (payload.get("confirm_token") or "").strip()
    if not ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ids_required")
    if not reason:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="reject_reason_required")
    if confirm_token.upper() != "CONFIRM":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="double_confirmation_required")

    users = db.query(User).filter(User.id.in_(ids), User.role == UserRole.USER).all()
    rejected_ids: list[str] = []
    for user in users:
        result = execute_onboarding_decision(
            db,
            user_id=user.id,
            actor=current_admin,
            decision="reject",
            reason=reason,
            confirm_token="CONFIRM",
            decision_source="bulk_manual",
        )
        if str(result.get("approval_status")) == "rejected":
            rejected_ids.append(user.id)

    create_audit_log(
        db,
        action="USER_APPROVAL_BULK_REJECTED",
        entity_type="user",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={"count": len(rejected_ids), "reason": reason, "user_ids": rejected_ids},
    )
    return {"count": len(rejected_ids), "user_ids": rejected_ids, "reason": reason}


@router.post("/reject-stale")
def reject_stale_pending_approvals(
    payload: dict | None = None,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    payload = payload or {}
    stale_days = int(payload.get("stale_days") or 30)
    reason = (payload.get("reason") or f"stale_pending_over_{stale_days}_days").strip()
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(stale_days, 1))

    users = (
        db.query(User)
        .filter(
            User.role == UserRole.USER,
            User.approval_status == "pending",
            User.approval_requested_at <= cutoff,
        )
        .all()
    )

    rejected_ids: list[str] = []
    for user in users:
        result = execute_onboarding_decision(
            db,
            user_id=user.id,
            actor=current_admin,
            decision="reject",
            reason=reason,
            confirm_token="CONFIRM",
            decision_source="stale_auto_reject",
        )
        if str(result.get("approval_status")) == "rejected":
            rejected_ids.append(user.id)
    create_audit_log(
        db,
        action="USER_APPROVAL_STALE_REJECTED",
        entity_type="user_approval",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={"count": len(rejected_ids), "stale_days": stale_days, "reason": reason},
    )
    return {"count": len(rejected_ids), "stale_days": stale_days, "reason": reason}
