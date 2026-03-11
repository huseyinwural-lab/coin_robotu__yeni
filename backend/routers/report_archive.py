import hashlib
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User, WeeklyReportArchive
from schemas import WeeklyReportArchiveResponse
from services.audit_service import create_audit_log
from services.system_alert_service import create_system_alert

router = APIRouter(prefix="/admin/reports", tags=["report_archive"])


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _compute_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


@router.get("/archive", response_model=list[WeeklyReportArchiveResponse])
def list_report_archives(
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


@router.get("/archive/{report_id}/download")
def download_report_archive(
    report_id: str,
    verify: bool = Query(default=False),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    report = db.query(WeeklyReportArchive).filter(WeeklyReportArchive.report_id == report_id).first()
    if report is None or report.status == "purged" or not report.storage_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report_not_found")

    path = Path(report.storage_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report_file_missing")

    if verify:
        checksum = _compute_sha(path)
        if checksum != report.sha256:
            create_system_alert(
                db,
                alert_type="weekly_report_integrity_failure",
                severity="WARNING",
                message="Weekly report checksum mismatch",
                details={"report_id": report.report_id, "expected": report.sha256, "actual": checksum},
                entity_key=report.report_id,
                root_cause_code="checksum_mismatch",
                state_key="checksum_mismatch",
            )
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="checksum_mismatch")

    create_audit_log(
        db,
        action="weekly_report_download",
        entity_type="weekly_report",
        entity_id=report.report_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={"report_id": report.report_id, "filename": report.filename, "verify": verify},
    )
    return FileResponse(path, filename=report.filename, media_type="text/csv")
