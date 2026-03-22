from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models import FailedEvent


def create_failed_event(
    db: Session,
    *,
    event_type: str,
    entity_type: str,
    entity_id: str,
    payload: dict,
    error_message: str,
    status: str = "pending",
    retry_count: int = 0,
    max_retry: int = 5,
    next_retry_at: datetime | None = None,
    failure_class: str = "downstream_error",
    dead_letter_reason: str | None = None,
    last_action_by: str | None = None,
    correlation_id: str | None = None,
    retry_reason: str | None = None,
    error_details: dict | None = None,
):
    failed_event = FailedEvent(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        error_message=error_message,
        failure_class=failure_class,
        dead_letter_reason=dead_letter_reason,
        last_action_by=last_action_by,
        correlation_id=correlation_id,
        retry_reason=retry_reason,
        error_details=error_details or {},
        status=status,
        retry_count=retry_count,
        max_retry=max_retry,
        next_retry_at=next_retry_at,
    )
    db.add(failed_event)
    db.commit()
    db.refresh(failed_event)
    return failed_event


def upsert_failed_event(
    db: Session,
    *,
    event_type: str,
    entity_type: str,
    entity_id: str,
    payload: dict,
    error_message: str,
    status: str,
    retry_count: int,
    max_retry: int,
    next_retry_at: datetime | None = None,
    failure_class: str = "downstream_error",
    dead_letter_reason: str | None = None,
    last_action_by: str | None = None,
    correlation_id: str | None = None,
    retry_reason: str | None = None,
    error_details: dict | None = None,
):
    existing = db.query(FailedEvent).filter(FailedEvent.entity_type == entity_type, FailedEvent.entity_id == entity_id).first()
    if existing is None:
        return create_failed_event(
            db,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
            error_message=error_message,
            status=status,
            retry_count=retry_count,
            max_retry=max_retry,
            next_retry_at=next_retry_at,
            failure_class=failure_class,
            dead_letter_reason=dead_letter_reason,
            last_action_by=last_action_by,
            correlation_id=correlation_id,
            retry_reason=retry_reason,
            error_details=error_details,
        )

    existing.event_type = event_type
    existing.payload = payload
    existing.error_message = error_message
    existing.failure_class = failure_class
    existing.dead_letter_reason = dead_letter_reason
    existing.last_action_by = last_action_by
    existing.correlation_id = correlation_id
    existing.retry_reason = retry_reason
    existing.error_details = error_details or {}
    existing.status = status
    existing.retry_count = retry_count
    existing.max_retry = max_retry
    existing.next_retry_at = next_retry_at
    existing.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(existing)
    return existing


def mark_failed_event_retry(db: Session, failed_event: FailedEvent, *, actor: str | None = None, retry_reason: str | None = None):
    failed_event.retry_count += 1
    if failed_event.retry_count >= failed_event.max_retry:
        failed_event.status = "dead"
        failed_event.dead_letter_reason = failed_event.dead_letter_reason or "max_retry_reached"
    else:
        failed_event.status = "retrying"
        failed_event.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=15)
    failed_event.last_action_by = actor
    failed_event.retry_reason = retry_reason
    db.commit()
    db.refresh(failed_event)
    return failed_event


def mark_failed_event_resolved(db: Session, failed_event: FailedEvent, *, actor: str | None = None):
    failed_event.status = "resolved"
    failed_event.resolved_at = datetime.now(timezone.utc)
    failed_event.last_action_by = actor
    db.commit()
    db.refresh(failed_event)
    return failed_event
