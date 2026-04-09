from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from db import get_db, redis_client
from deps import require_user
from models import User
from services.pipeline.cache_store import get_json
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


def _safe_parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _scanner_engine_config_key(user_id: str) -> str:
    return f"user:scanner_engine:config:{user_id}"


def _scanner_engine_last_run_key(user_id: str) -> str:
    return f"user:scanner_engine:last_run:{user_id}"


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
    config = get_json(redis_client, _scanner_engine_config_key(current_user.id))
    if not isinstance(config, dict):
        config = {}

    last_run_payload = get_json(redis_client, _scanner_engine_last_run_key(current_user.id))
    if not isinstance(last_run_payload, dict):
        last_run_payload = {}

    auto_interval_minutes = int(config.get("auto_interval_minutes") or 3)
    if auto_interval_minutes not in {1, 3, 5}:
        auto_interval_minutes = 3

    interval_seconds = auto_interval_minutes * 60
    last_run_at = str(last_run_payload.get("generated_at") or "").strip() or None
    parsed_last_run = _safe_parse_iso(last_run_at)
    next_run_at = (parsed_last_run + timedelta(seconds=interval_seconds)).isoformat() if parsed_last_run else None

    return {
        "source": "user_scanner_engine_config",
        "auto_enabled": True,
        "signal_mode": "auto",
        "auto_interval_minutes": auto_interval_minutes,
        "interval_seconds": interval_seconds,
        "last_run_at": last_run_at,
        "next_run_at": next_run_at,
    }