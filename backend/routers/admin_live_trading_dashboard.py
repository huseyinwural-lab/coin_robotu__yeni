from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from db import get_db, redis_client
from deps import require_admin
from models import User
from services.live_trading_dashboard_service import (
    build_daily_report,
    build_execution_quality_summary,
    build_learning_summary,
    build_live_trading_summary,
    build_risk_summary,
    build_scanner_health,
    export_daily_report_csv,
)

router = APIRouter(prefix="/admin/live-trading", tags=["admin_live_trading_dashboard"])


@router.get("/summary")
def admin_live_trading_summary(
    window: str = Query(default="1h", pattern="^(1h|6h|24h)$"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return build_live_trading_summary(db, redis_client, window=window)


@router.get("/scanner-health")
def admin_live_trading_scanner_health(
    window: str = Query(default="1h", pattern="^(1h|6h|24h)$"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return build_scanner_health(db, redis_client, window=window)


@router.get("/execution-quality")
def admin_live_trading_execution_quality(
    window: str = Query(default="1h", pattern="^(1h|6h|24h)$"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return build_execution_quality_summary(db, window=window)


@router.get("/risk-summary")
def admin_live_trading_risk_summary(
    window: str = Query(default="1h", pattern="^(1h|6h|24h)$"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return build_risk_summary(db, redis_client, window=window)


@router.get("/daily-report")
def admin_live_trading_daily_report(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return build_daily_report(db, redis_client)


@router.get("/learning-summary")
def admin_live_trading_learning_summary(
    window: str = Query(default="24h", pattern="^(1h|6h|24h)$"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return build_learning_summary(db, window=window)


@router.get("/daily-report/export")
def admin_live_trading_daily_report_export(
    format: str = Query(default="json", pattern="^(json|csv)$"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    report = build_daily_report(db, redis_client)
    if format == "csv":
        content = export_daily_report_csv(report)
        filename = f"live_trading_daily_report_{report.get('date', 'latest')}.csv"
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    return report
