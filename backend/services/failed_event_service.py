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
):
    failed_event = FailedEvent(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        error_message=error_message,
        status="pending",
        retry_count=0,
        max_retry=5,
    )
    db.add(failed_event)
    db.commit()
    db.refresh(failed_event)
    return failed_event


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
