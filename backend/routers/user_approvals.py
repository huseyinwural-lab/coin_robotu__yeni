from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User, UserRole
from schemas import UserResponse
from services.audit_service import create_audit_log
from services.risk_policy_defaults_service import ensure_user_safe_default_risk_policy
from services.venue_service import ensure_user_venue_assignment

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
    ids = payload.get("ids") or []
    if not ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ids_required")

    users = db.query(User).filter(User.id.in_(ids), User.role == UserRole.USER).all()
    now = datetime.now(timezone.utc)
    for user in users:
        user.approval_status = "approved"
        user.is_active = True
        user.approved_at = now
        ensure_user_safe_default_risk_policy(db, user.id, commit=False)
        ensure_user_venue_assignment(
            db,
            user_id=user.id,
            exchange_code="binance",
            market_type="futures",
            environment="testnet",
            commit=False,
        )
    db.commit()

    create_audit_log(
        db,
        action="USER_APPROVAL_BULK_APPROVED",
        entity_type="user",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={"count": len(users), "user_ids": [user.id for user in users]},
    )
    return {"count": len(users), "user_ids": [user.id for user in users]}


@router.post("/bulk-reject")
def bulk_reject(
    payload: dict,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    ids = payload.get("ids") or []
    reason = (payload.get("reason") or "").strip()
    if not ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ids_required")
    if not reason:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="reject_reason_required")

    users = db.query(User).filter(User.id.in_(ids), User.role == UserRole.USER).all()
    now = datetime.now(timezone.utc)
    for user in users:
        user.approval_status = "rejected"
        user.is_active = False
        user.approved_at = None
        user.disabled_at = now
    db.commit()

    create_audit_log(
        db,
        action="USER_APPROVAL_BULK_REJECTED",
        entity_type="user",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={"count": len(users), "reason": reason, "user_ids": [user.id for user in users]},
    )
    return {"count": len(users), "user_ids": [user.id for user in users], "reason": reason}


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

    now = datetime.now(timezone.utc)
    for user in users:
        user.approval_status = "rejected"
        user.is_active = False
        user.approved_at = None
        user.disabled_at = now

    db.commit()
    create_audit_log(
        db,
        action="USER_APPROVAL_STALE_REJECTED",
        entity_type="user_approval",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={"count": len(users), "stale_days": stale_days, "reason": reason},
    )
    return {"count": len(users), "stale_days": stale_days, "reason": reason}
