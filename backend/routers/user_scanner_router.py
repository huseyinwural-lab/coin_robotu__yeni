from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from db import get_db, redis_client
from deps import require_user
from models import User
from services.scanner_runtime import get_runtime_snapshot, run_scanner_runtime
from services.user_scanner_operations_service import (
    build_user_scanner_daily_report,
    build_user_scanner_live_readiness,
    export_user_scanner_daily_report_csv,
)


router = APIRouter(prefix="/user/scanner/runtime", tags=["user_scanner_runtime"])


@router.post("/run")
def run_runtime_scan(
    symbol_selection_mode: str = Query(default="all_market_symbols"),
    max_results: int = Query(default=120, ge=10, le=500),
    selected_symbols: str = Query(default=""),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    selected_list = [item.strip().upper() for item in selected_symbols.split(",") if item.strip()]
    return run_scanner_runtime(
        db,
        redis_client,
        user_id=current_user.id,
        symbol_selection_mode=symbol_selection_mode,
        selected_symbols=selected_list,
        symbol_source="crypto",
        max_results=max_results,
    )


@router.get("/snapshot")
def get_runtime_scan_snapshot(
    current_user: User = Depends(require_user),
):
    return get_runtime_snapshot(redis_client, user_id=current_user.id)


@router.get("/live-readiness")
def get_runtime_live_readiness(
    window: str = Query(default="24h", pattern="^(1h|6h|24h)$"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return build_user_scanner_live_readiness(db, current_user.id, redis_client, window=window)


@router.get("/daily-report")
def get_runtime_daily_report(
    window: str = Query(default="24h", pattern="^(1h|6h|24h)$"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return build_user_scanner_daily_report(db, current_user.id, redis_client, window=window)


@router.get("/daily-report/export")
def get_runtime_daily_report_export(
    format: str = Query(default="json", pattern="^(json|csv)$"),
    window: str = Query(default="24h", pattern="^(1h|6h|24h)$"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    report = build_user_scanner_daily_report(db, current_user.id, redis_client, window=window)
    if format == "csv":
        content = export_user_scanner_daily_report_csv(report)
        filename = f"scanner_daily_report_{report.get('date', 'latest')}.csv"
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    return report
