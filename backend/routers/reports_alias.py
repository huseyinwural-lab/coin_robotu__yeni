from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User, WeeklyReportArchive
from schemas import WeeklyReportArchiveResponse

router = APIRouter(prefix="/reports", tags=["reports_alias"])


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@router.get("/archive", response_model=list[WeeklyReportArchiveResponse])
def list_report_archives_alias(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    report_type: str | None = None,
    status_filter: str = Query(default="all"),
    trigger_source: str = Query(default="all"),
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 100,
):
    _ = current_admin
    parsed_from = _parse_iso(date_from)
    parsed_to = _parse_iso(date_to)

    query = db.query(WeeklyReportArchive)
    if report_type:
        query = query.filter(WeeklyReportArchive.report_type == report_type)
    if status_filter != "all":
        query = query.filter(WeeklyReportArchive.status == status_filter)
    if trigger_source != "all":
        query = query.filter(WeeklyReportArchive.trigger_source == trigger_source)
    if parsed_from:
        query = query.filter(WeeklyReportArchive.generated_at >= parsed_from)
    if parsed_to:
        query = query.filter(WeeklyReportArchive.generated_at <= parsed_to)

    rows = query.order_by(WeeklyReportArchive.generated_at.desc()).limit(limit).all()
    return [WeeklyReportArchiveResponse.model_validate(row) for row in rows]
