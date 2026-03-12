from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from db import get_db
from deps import require_user
from models import User
from schemas import UserWeeklyReportResponse
from services.user_weekly_reporting_service import ARTIFACT_ROOT, generate_weekly_user_report

router = APIRouter(prefix="/user/reports", tags=["user_reports"])


@router.get("/weekly", response_model=UserWeeklyReportResponse)
def weekly_report(
    week: str | None = Query(default=None),
    format: str | None = Query(default=None),
    include_artifacts: bool = Query(default=True),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    _ = format
    manifest = generate_weekly_user_report(db, current_user.id, week=week)
    summary = manifest.get("summary") or {}
    artifact_files = manifest.get("artifact_files") or {}
    report_id = manifest.get("report_id")

    if include_artifacts:
        links = {
            name: f"/api/user/reports/weekly/download/{report_id}/{name}"
            for name in artifact_files.keys()
        }
    else:
        links = {}

    return UserWeeklyReportResponse(
        report_id=report_id,
        week=f"{manifest['week_start'][:10]} -> {manifest['week_end'][:10]}",
        summary=summary,
        pnl=float(summary.get("weekly_pnl") or 0),
        win_rate=float(summary.get("win_rate") or 0),
        max_drawdown=float(summary.get("max_drawdown") or 0),
        strategy_contribution=summary.get("strategy_contribution") or {},
        download_links=links,
        status=str(summary.get("status") or "ready"),
    )


@router.get("/weekly/download/{report_id}/{artifact_name}")
def download_weekly_artifact(
    report_id: str,
    artifact_name: str,
    current_user: User = Depends(require_user),
):
    allowed = {"weekly_performance_report.pdf", "weekly_trades.csv", "weekly_strategy_stats.json", "report_manifest.json"}
    if artifact_name not in allowed:
        raise HTTPException(status_code=400, detail="unsupported_artifact")

    path = ARTIFACT_ROOT / current_user.id / report_id / artifact_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="artifact_not_found")

    media_type = "application/octet-stream"
    if artifact_name.endswith(".csv"):
        media_type = "text/csv"
    if artifact_name.endswith(".json"):
        media_type = "application/json"
    if artifact_name.endswith(".pdf"):
        media_type = "application/pdf"

    return FileResponse(Path(path), filename=artifact_name, media_type=media_type)