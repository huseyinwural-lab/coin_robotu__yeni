from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from model_domains.security_branding import MfaRecoveryApprovalVote, MfaRecoveryRequest
from models import User

DEFAULT_RECOVERY_REQUIRED_APPROVALS = 2
DEFAULT_RECOVERY_DELAY_MINUTES = 15


def _now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_recovery_tables(db: Session) -> None:
    for model in (MfaRecoveryRequest, MfaRecoveryApprovalVote):
        try:
            model.__table__.create(bind=db.bind, checkfirst=True)
        except Exception:
            continue


def create_recovery_request(
    db: Session,
    *,
    target_user_id: str,
    requested_by_user_id: str,
    reason: str,
    required_approvals: int = DEFAULT_RECOVERY_REQUIRED_APPROVALS,
    delay_minutes: int = DEFAULT_RECOVERY_DELAY_MINUTES,
) -> MfaRecoveryRequest:
    ensure_recovery_tables(db)
    row = MfaRecoveryRequest(
        user_id=target_user_id,
        requested_by_user_id=requested_by_user_id,
        reason=str(reason or "")[:2000],
        required_approvals=max(1, int(required_approvals or DEFAULT_RECOVERY_REQUIRED_APPROVALS)),
        approval_count=0,
        status="pending",
        ready_after=_now() + timedelta(minutes=max(1, int(delay_minutes or DEFAULT_RECOVERY_DELAY_MINUTES))),
    )
    db.add(row)
    db.flush()
    return row


def approve_recovery_request(
    db: Session,
    *,
    request_id: str,
    approver: User,
    note: str | None = None,
) -> MfaRecoveryRequest:
    ensure_recovery_tables(db)
    row = db.query(MfaRecoveryRequest).filter(MfaRecoveryRequest.id == request_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="recovery_request_not_found")
    if row.status not in {"pending", "approved_waiting_delay"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="recovery_request_not_pending")

    existing_vote = (
        db.query(MfaRecoveryApprovalVote)
        .filter(
            MfaRecoveryApprovalVote.recovery_request_id == request_id,
            MfaRecoveryApprovalVote.approver_user_id == approver.id,
        )
        .first()
    )
    if existing_vote is not None:
        return row

    vote = MfaRecoveryApprovalVote(
        recovery_request_id=request_id,
        approver_user_id=approver.id,
        decision="approved",
        note=str(note or "")[:1000] or None,
    )
    db.add(vote)
    db.flush()

    vote_count = (
        db.query(MfaRecoveryApprovalVote)
        .filter(
            MfaRecoveryApprovalVote.recovery_request_id == request_id,
            MfaRecoveryApprovalVote.decision == "approved",
        )
        .count()
    )
    row.approval_count = int(vote_count)
    if row.approval_count >= max(1, int(row.required_approvals or DEFAULT_RECOVERY_REQUIRED_APPROVALS)):
        row.status = "approved_waiting_delay"
    db.flush()
    return row


def finalize_recovery_request(
    db: Session,
    *,
    request_id: str,
    finalizer: User,
) -> MfaRecoveryRequest:
    ensure_recovery_tables(db)
    row = db.query(MfaRecoveryRequest).filter(MfaRecoveryRequest.id == request_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="recovery_request_not_found")

    if row.approval_count < max(1, int(row.required_approvals or DEFAULT_RECOVERY_REQUIRED_APPROVALS)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="recovery_approval_quorum_not_met")

    ready_after = row.ready_after if row.ready_after.tzinfo else row.ready_after.replace(tzinfo=timezone.utc)
    if _now() < ready_after:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="recovery_time_delay_not_elapsed")

    if row.status == "finalized":
        return row

    row.status = "finalized"
    row.finalized_at = _now()
    row.finalized_by_user_id = finalizer.id
    db.flush()
    return row


def list_recovery_requests(db: Session, *, status_filter: str | None = None, limit: int = 100) -> list[MfaRecoveryRequest]:
    ensure_recovery_tables(db)
    query = db.query(MfaRecoveryRequest)
    if status_filter:
        query = query.filter(MfaRecoveryRequest.status == str(status_filter).strip().lower())
    return query.order_by(MfaRecoveryRequest.created_at.desc()).limit(max(1, min(int(limit or 100), 500))).all()
