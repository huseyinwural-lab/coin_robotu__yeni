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
):
    failed_event = FailedEvent(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        error_message=error_message,
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
        )

    existing.event_type = event_type
    existing.payload = payload
    existing.error_message = error_message
    existing.status = status
    existing.retry_count = retry_count
    existing.max_retry = max_retry
    existing.next_retry_at = next_retry_at
    existing.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(existing)
    return existing


def mark_failed_event_retry(db: Session, failed_event: FailedEvent):
    failed_event.retry_count += 1
    if failed_event.retry_count >= failed_event.max_retry:
        failed_event.status = "dead"
    else:
        failed_event.status = "retrying"
        failed_event.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=15)
    db.commit()
    db.refresh(failed_event)
    return failed_event


def mark_failed_event_resolved(db: Session, failed_event: FailedEvent):
    failed_event.status = "resolved"
    failed_event.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(failed_event)
    return failed_event
