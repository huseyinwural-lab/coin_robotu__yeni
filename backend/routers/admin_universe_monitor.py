from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from db import get_db, redis_client
from deps import require_admin
from models import User, UserScannerResult
from services.pipeline.universe_engine import debug_effective_universe
from services.pipeline.cache_store import get_json
from services.scanner_observability_service import (
    approve_rollout_transition,
    export_perf_trend_csv,
    get_freshness_heatmap,
    get_monitor_breakdown,
    get_perf_trend,
    get_rollout_state,
    recommend_rollout_transition,
)


router = APIRouter(prefix="/admin/universe-monitor", tags=["admin_universe_monitor"])


def _reason_set(item: UserScannerResult) -> set[str]:
    payload = item.payload or {}
    reason_codes = payload.get("reason_codes") or []
    merged = set(str(code or "").strip().lower() for code in reason_codes if str(code or "").strip())
    merged.update(str(code or "").strip().lower() for code in (item.reason_codes or []) if str(code or "").strip())
    blocked_reason = str(payload.get("blocked_reason_current") or "").strip().lower()
    if blocked_reason:
        merged.add(blocked_reason)
    return merged


@router.get("")
def admin_universe_monitor_summary(
    market_type: str = Query(default="spot", pattern="^(spot|futures)$"),
    scanner_mode: str = Query(default="ALL_MARKET_SYMBOLS"),
    top_n: int = Query(default=200, ge=1, le=1000),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    debug_payload = debug_effective_universe(
        db,
        redis_client,
        market_type=market_type,
        scanner_mode=scanner_mode,
        selected_symbols=[],
        top_n=top_n,
    )

    recent_rows = (
        db.query(UserScannerResult)
        .order_by(UserScannerResult.generated_at.desc())
        .limit(2000)
        .all()
    )

    permission_codes = {
        "symbol_not_allowed",
        "symbol_permission_block",
        "symbol_not_allowed_by_whitelist",
        "symbol_not_allowed_by_live_config",
    }
    risk_codes = {
        "risk_limit_blocked",
        "max_positions_reached",
        "position_limit_reached",
        "risk_blocked",
    }
    liquidity_codes = {
        "liquidity_volume_low",
        "liquidity_spread_high",
        "data_unavailable",
    }

    blocked_by_permission = 0
    blocked_by_risk = 0
    blocked_by_liquidity = 0
    scanned_symbols = set()
    for row in recent_rows:
        symbol = str(row.symbol or "").upper().strip()
        if symbol:
            scanned_symbols.add(symbol)
        reasons = _reason_set(row)
        if reasons.intersection(permission_codes):
            blocked_by_permission += 1
        if reasons.intersection(risk_codes):
            blocked_by_risk += 1
        if reasons.intersection(liquidity_codes):
            blocked_by_liquidity += 1

    queue_state = get_json(redis_client, "scanner:queue:state") or {}
    perf_state = get_json(redis_client, "scanner:perf:latest:global") or {}

    return {
        "market_type": market_type,
        "scanner_mode": debug_payload.get("scanner_mode"),
        "total_exchange_symbols": debug_payload.get("market_symbols_count", 0),
        "active_scan_symbols": debug_payload.get("after_scanner_mode", 0),
        "total_scanned_symbols": int(perf_state.get("total_active_symbols") or debug_payload.get("after_scanner_mode", 0)),
        "symbols_evaluated_this_cycle": int(perf_state.get("symbols_evaluated") or 0),
        "average_cycle_latency_ms": float(perf_state.get("cycle_duration_ms") or queue_state.get("cycle_latency_ms") or 0),
        "avg_symbol_eval_ms": float(perf_state.get("avg_symbol_eval_ms") or 0),
        "snapshot_age_avg_sec": perf_state.get("snapshot_age_avg_sec"),
        "queue_depth": int(queue_state.get("depth") or 0),
        "blocked_by_permission": blocked_by_permission,
        "blocked_by_risk": blocked_by_risk,
        "blocked_by_liquidity": blocked_by_liquidity,
        "stale_blocks": int(queue_state.get("stale_blocks") or perf_state.get("stale_block_count") or 0),
        "dropped_evaluations": int(queue_state.get("dropped_jobs") or 0) + int(perf_state.get("dropped_symbol_count") or 0),
        "worker_utilization": float(queue_state.get("worker_utilization") or 0),
        "top_slow_strategies": list(perf_state.get("top_slow_strategies") or []),
        "top_slow_symbols": list(perf_state.get("top_slow_symbols") or []),
        "recent_scanned_symbols": len(scanned_symbols),
        "final_symbols": debug_payload.get("final_symbols", []),
        "generated_at": datetime.now(timezone.utc),
    }


@router.get("/trends")
def admin_universe_monitor_trends(
    window: str = Query(default="24h", pattern="^(24h|7d|30d)$"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return get_perf_trend(db, window=window)


@router.get("/export.csv")
def admin_universe_monitor_export_csv(
    window: str = Query(default="24h", pattern="^(24h|7d|30d)$"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    content = export_perf_trend_csv(db, window=window)
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=universe_monitor_{window}.csv"},
    )


@router.get("/breakdown")
def admin_universe_monitor_breakdown(
    window: str = Query(default="7d", pattern="^(24h|7d|30d)$"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return get_monitor_breakdown(db, window=window)


@router.get("/freshness-heatmap")
def admin_freshness_heatmap(
    window: str = Query(default="24h", pattern="^(24h|7d|30d)$"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    return get_freshness_heatmap(db, window=window)


@router.get("/rollout/status")
def admin_rollout_status(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    row = get_rollout_state(db)
    return {
        "current_stage": row.current_stage,
        "recommended_stage": row.recommended_stage,
        "recommendation_payload": row.recommendation_payload or {},
        "requires_admin_approval": bool(row.requires_admin_approval),
        "approved_by": row.approved_by,
        "approved_at": row.approved_at,
        "updated_at": row.updated_at,
    }


@router.post("/rollout/recommend")
def admin_rollout_recommend(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    latest = get_json(redis_client, "scanner:perf:latest:global") or {}
    return recommend_rollout_transition(db, latest_metrics=latest)


@router.post("/rollout/approve")
def admin_rollout_approve(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return approve_rollout_transition(db, admin_user_id=current_admin.id)
