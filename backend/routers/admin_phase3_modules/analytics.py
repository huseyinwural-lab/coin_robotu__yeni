
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import ExecutionManualAction, ExecutionStateTransition, FailedEvent, User
from routers.admin_phase3_modules.common import resolve_time_window, shape_response

router = APIRouter(tags=["admin_phase3_analytics"])


def _build_window_kpis(db: Session, *, start_at, end_at) -> dict:
    transitions = (
        db.query(ExecutionStateTransition)
        .filter(
            ExecutionStateTransition.occurred_at >= start_at,
            ExecutionStateTransition.occurred_at <= end_at,
        )
        .count()
    )
    failed_events = (
        db.query(FailedEvent)
        .filter(
            FailedEvent.created_at >= start_at,
            FailedEvent.created_at <= end_at,
        )
        .count()
    )
    manual_actions = (
        db.query(ExecutionManualAction)
        .filter(
            ExecutionManualAction.created_at >= start_at,
            ExecutionManualAction.created_at <= end_at,
        )
        .count()
    )
    return {
        "transitions": transitions,
        "failed_events": failed_events,
        "manual_actions": manual_actions,
    }


@router.get("/execution-analytics/kpi-before-after")
def execution_analytics_kpi_before_after(
    window: str = Query(default="24h"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    normalized, start_at, end_at = resolve_time_window(window)
    duration = end_at - start_at
    before_start = start_at - duration
    before_end = start_at

    after_kpis = _build_window_kpis(db, start_at=start_at, end_at=end_at)
    before_kpis = _build_window_kpis(db, start_at=before_start, end_at=before_end)

    cards = {}
    for key in ["transitions", "failed_events", "manual_actions"]:
        before_value = int(before_kpis.get(key, 0))
        after_value = int(after_kpis.get(key, 0))
        cards[key] = {
            "before": before_value,
            "after": after_value,
            "delta": after_value - before_value,
        }

    return shape_response(
        window=normalized,
        range_current={
            "from": start_at.isoformat(),
            "to": end_at.isoformat(),
        },
        range_previous={
            "from": before_start.isoformat(),
            "to": before_end.isoformat(),
        },
        cards=cards,
    )
