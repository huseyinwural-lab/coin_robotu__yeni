from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from db import get_db
from deps import require_user
from models import User
from services.user_live_dashboard_service import (
    build_user_live_daily_report,
    build_user_live_execution_quality,
    build_user_live_performance,
    build_user_live_positions,
    build_user_live_queue,
    build_user_live_risk,
    build_user_live_runtime_snapshot,
    build_user_strategy_performance_bridge,
    build_user_live_strategies,
    build_user_live_summary,
    build_user_live_trades,
    export_user_live_daily_report_csv,
)

router = APIRouter(prefix="/user/live", tags=["user_live_dashboard"])


@router.get("/summary")
def user_live_summary(
    window: str = Query(default="1h", pattern="^(1h|6h|24h)$"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return build_user_live_summary(db, current_user.id, window=window)


@router.get("/positions")
def user_live_positions(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return build_user_live_positions(db, current_user.id, limit=limit, offset=offset)


@router.get("/performance")
def user_live_performance(
    window: str = Query(default="24h", pattern="^(1h|6h|24h)$"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return build_user_live_performance(db, current_user.id, window=window)


@router.get("/risk")
def user_live_risk(
    window: str = Query(default="24h", pattern="^(1h|6h|24h)$"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return build_user_live_risk(db, current_user.id, window=window)


@router.get("/execution-quality")
def user_live_execution_quality(
    window: str = Query(default="24h", pattern="^(1h|6h|24h)$"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return build_user_live_execution_quality(db, current_user.id, window=window)


@router.get("/strategies")
def user_live_strategies(
    window: str = Query(default="24h", pattern="^(1h|6h|24h)$"),
    limit: int = Query(default=20, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return build_user_live_strategies(db, current_user.id, window=window, limit=limit, offset=offset)


@router.get("/trades")
def user_live_trades(
    window: str = Query(default="24h", pattern="^(1h|6h|24h)$"),
    limit: int = Query(default=120, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return build_user_live_trades(db, current_user.id, window=window, limit=limit, offset=offset)


@router.get("/daily-report")
def user_live_daily_report(
    window: str = Query(default="24h", pattern="^(1h|6h|24h)$"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return build_user_live_daily_report(db, current_user.id, window=window)


@router.get("/daily-report/export")
def user_live_daily_report_export(
    format: str = Query(default="json", pattern="^(json|csv)$"),
    window: str = Query(default="24h", pattern="^(1h|6h|24h)$"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    report = build_user_live_daily_report(db, current_user.id, window=window)
    if format == "csv":
        content = export_user_live_daily_report_csv(report)
        filename = f"user_live_daily_report_{report.get('date', 'latest')}.csv"
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    return report


@router.get("/queue")
def user_live_queue(
    limit: int = Query(default=20, ge=1, le=200),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return build_user_live_queue(db, current_user.id, limit=limit)


@router.get("/runtime-snapshot")
def user_live_runtime_snapshot(
    window: str = Query(default="1h", pattern="^(1h|6h|24h)$"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return build_user_live_runtime_snapshot(db, current_user.id, window=window)


@router.get("/strategy-performance")
def user_strategy_performance(
    window: str = Query(default="24h", pattern="^(1h|6h|24h|7d|30d)$"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return build_user_strategy_performance_bridge(db, current_user.id, window=window)


@router.get("/scheduler/next-run")
def user_scheduler_next_run(current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    raise HTTPException(status_code=status.HTTP_410_GONE, detail={"code": "PURE_LIVE_410", "message": "scheduler automation kaldırıldı"})