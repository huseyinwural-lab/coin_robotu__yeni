from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import ExecutionManualAction, ExecutionStateTransition, FailedEvent, User
from routers.admin_phase3_modules.common import parse_iso_datetime, shape_response

router = APIRouter(tags=["admin_phase3_export"])


def _count_snapshot_scope(
    db: Session,
    *,
    scope_type: str,
    scope_value: str | None,
    time_from: str | None,
    time_to: str | None,
) -> dict:
    scope = str(scope_type or "").strip().lower()
    value = str(scope_value or "").strip()

    transitions_query = db.query(ExecutionStateTransition)
    failed_query = db.query(FailedEvent)
    manual_query = db.query(ExecutionManualAction)

    if scope == "correlation_id":
        if not value:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="scope_value_required")
        transitions_query = transitions_query.filter(ExecutionStateTransition.correlation_id == value)
        failed_query = failed_query.filter(FailedEvent.correlation_id == value)
        manual_query = manual_query.filter(ExecutionManualAction.correlation_id == value)
    elif scope == "execution_event_id":
        if not value:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="scope_value_required")
        transitions_query = transitions_query.filter(ExecutionStateTransition.execution_event_id == value)
        # FailedEvent doesn't have execution_event_id column, filter by correlation_id from transitions
        transition_correlations = [
            row.correlation_id
            for row in db.query(ExecutionStateTransition.correlation_id)
            .filter(ExecutionStateTransition.execution_event_id == value)
            .distinct()
            .all()
            if row.correlation_id
        ]
        if transition_correlations:
            failed_query = failed_query.filter(FailedEvent.correlation_id.in_(transition_correlations))
        else:
            failed_query = failed_query.filter(FailedEvent.id == "")  # No results
        # ExecutionManualAction only has execution_event_id, not entity_id
        manual_query = manual_query.filter(ExecutionManualAction.execution_event_id == value)
    elif scope == "time_range":
        from_at = parse_iso_datetime(time_from, field_name="time_from")
        to_at = parse_iso_datetime(time_to, field_name="time_to")
        if from_at is None or to_at is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="time_range_requires_time_from_and_time_to")
        if to_at < from_at:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="time_range_invalid")
        transitions_query = transitions_query.filter(
            ExecutionStateTransition.occurred_at >= from_at,
            ExecutionStateTransition.occurred_at <= to_at,
        )
        failed_query = failed_query.filter(
            FailedEvent.created_at >= from_at,
            FailedEvent.created_at <= to_at,
        )
        manual_query = manual_query.filter(
            ExecutionManualAction.created_at >= from_at,
            ExecutionManualAction.created_at <= to_at,
        )
    else:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="scope_type_invalid")

    events_count = transitions_query.count()
    failed_count = failed_query.count()
    dead_letter_count = transitions_query.filter(ExecutionStateTransition.state.in_(["failed", "rejected", "cancelled"])).count()
    manual_count = manual_query.count()

    return {
        "events": events_count,
        "failures": failed_count,
        "transitions": events_count,
        "dead_letter": dead_letter_count,
        "manual_actions": manual_count,
    }


@router.get("/incident-snapshots/export/filter-options")
def incident_snapshot_export_filter_options(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = db
    return shape_response(
        filter_scope_priority=["correlation_id", "execution_event_id", "time_range"],
        allowed_filter_values={
            "state": [
                "created",
                "submitted",
                "acknowledged",
                "partially_filled",
                "timeout",
                "fallback_submitted",
                "filled",
                "rejected",
                "failed",
                "cancelled",
            ],
            "status": ["filled", "timeout", "rejected", "failed", "cancelled", "submitted", "pending"],
            "source_type": ["production", "paper", "simulation", "replay"],
        },
        compare_mode_rules={
            "scope_type_must_match": True,
            "supported_compare_types": ["correlation_id", "execution_event_id", "time_range"],
        },
    )


@router.get("/incident-snapshots/preview")
def incident_snapshot_preview(
    scope_type: str = Query(...),
    scope_value: str | None = Query(default=None),
    time_from: str | None = Query(default=None),
    time_to: str | None = Query(default=None),
    compare_scope_type: str | None = Query(default=None),
    compare_scope_value: str | None = Query(default=None),
    compare_time_from: str | None = Query(default=None),
    compare_time_to: str | None = Query(default=None),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    primary_preview = _count_snapshot_scope(
        db,
        scope_type=scope_type,
        scope_value=scope_value,
        time_from=time_from,
        time_to=time_to,
    )
    compare_preview = None
    if compare_scope_type:
        compare_preview = _count_snapshot_scope(
            db,
            scope_type=compare_scope_type,
            scope_value=compare_scope_value,
            time_from=compare_time_from,
            time_to=compare_time_to,
        )

    return shape_response(
        preview=primary_preview,
        compare_preview=compare_preview,
    )
