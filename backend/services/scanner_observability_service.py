import csv
import hashlib
import io
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from models import (
    IndicatorComputationCache,
    ScannerPerformanceSnapshot,
    UniverseRolloutState,
    UserScannerResult,
)
from services.pipeline.cache_store import get_json, set_json

ROLLOUT_STAGES = ["top_volume_subset", "mid_segment", "full_market"]


def _ensure_tables(db: Session) -> None:
    inspector = inspect(db.bind)
    table_names = set(inspector.get_table_names())
    for table in (
        IndicatorComputationCache.__table__,
        ScannerPerformanceSnapshot.__table__,
        UniverseRolloutState.__table__,
    ):
        if table.name not in table_names:
            table.create(bind=db.bind, checkfirst=True)


def _bucket_start(dt: datetime, *, granularity: str) -> datetime:
    if granularity == "day":
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return dt.replace(minute=0, second=0, microsecond=0)


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _cache_key(*, symbol: str, timeframe: str, bar_close_time: str, indicator_name: str, params_version: str) -> str:
    raw = f"{symbol}|{timeframe}|{bar_close_time}|{indicator_name}|{params_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_indicator_cache(
    db: Session,
    cache,
    *,
    symbol: str,
    timeframe: str,
    bar_close_time: str,
    indicator_name: str,
    params_version: str,
) -> dict | None:
    _ensure_tables(db)
    key = _cache_key(
        symbol=symbol,
        timeframe=timeframe,
        bar_close_time=bar_close_time,
        indicator_name=indicator_name,
        params_version=params_version,
    )
    redis_key = f"indicator_cache:{key}"
    cached = get_json(cache, redis_key)
    if cached:
        return cached

    row = db.query(IndicatorComputationCache).filter(IndicatorComputationCache.cache_key == key).first()
    if row is None:
        return None
    expires_at = _as_aware(row.expires_at)
    if expires_at and expires_at < datetime.now(timezone.utc):
        return None
    payload = dict(row.payload or {})
    set_json(cache, redis_key, payload)
    return payload


def set_indicator_cache(
    db: Session,
    cache,
    *,
    symbol: str,
    timeframe: str,
    bar_close_time: str,
    indicator_name: str,
    params_version: str,
    payload: dict,
    ttl_seconds: int = 3600,
) -> None:
    _ensure_tables(db)
    key = _cache_key(
        symbol=symbol,
        timeframe=timeframe,
        bar_close_time=bar_close_time,
        indicator_name=indicator_name,
        params_version=params_version,
    )
    redis_key = f"indicator_cache:{key}"
    set_json(cache, redis_key, payload)

    try:
        row = db.query(IndicatorComputationCache).filter(IndicatorComputationCache.cache_key == key).first()
        expiry = datetime.now(timezone.utc) + timedelta(seconds=max(60, ttl_seconds))
        if row is None:
            row = IndicatorComputationCache(
                cache_key=key,
                symbol=symbol,
                timeframe=timeframe,
                bar_close_time=str(bar_close_time),
                indicator_name=indicator_name,
                params_version=params_version,
                payload=payload,
                expires_at=expiry,
            )
            db.add(row)
        else:
            row.payload = payload
            row.expires_at = expiry
            row.updated_at = datetime.now(timezone.utc)
        db.flush()
    except Exception:
        db.rollback()


def get_rollout_state(db: Session) -> UniverseRolloutState:
    _ensure_tables(db)
    row = db.query(UniverseRolloutState).filter(UniverseRolloutState.id == "global").first()
    if row is None:
        row = UniverseRolloutState(
            id="global",
            current_stage="top_volume_subset",
            recommended_stage=None,
            recommendation_payload={},
            requires_admin_approval=True,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def record_scanner_perf_snapshot(db: Session, *, user_id: str, run_id: str, metrics: dict) -> ScannerPerformanceSnapshot:
    _ensure_tables(db)
    rollout = get_rollout_state(db)
    row = ScannerPerformanceSnapshot(
        user_id=user_id,
        run_id=run_id,
        stage=str(rollout.current_stage or "top_volume_subset"),
        metrics=metrics or {},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _kpi_score(metrics: dict) -> dict:
    cycle_latency = float(metrics.get("average_cycle_latency_ms") or metrics.get("cycle_duration_ms") or 0)
    stale_blocks = float(metrics.get("stale_blocks") or metrics.get("stale_block_count") or 0)
    evaluated = float(metrics.get("symbols_evaluated_this_cycle") or metrics.get("symbols_evaluated") or 0)
    dropped = float(metrics.get("dropped_evaluations") or metrics.get("dropped_symbol_count") or 0)
    stale_rate = stale_blocks / max(evaluated, 1.0)
    dropped_rate = dropped / max(evaluated, 1.0)
    healthy = cycle_latency <= 1500 and stale_rate <= 0.05 and dropped_rate <= 0.05
    return {
        "cycle_latency_ms": round(cycle_latency, 4),
        "stale_rate": round(stale_rate, 6),
        "dropped_rate": round(dropped_rate, 6),
        "healthy": healthy,
    }


def recommend_rollout_transition(db: Session, *, latest_metrics: dict) -> dict:
    rollout = get_rollout_state(db)
    stage = str(rollout.current_stage or "top_volume_subset")
    kpi = _kpi_score(latest_metrics)
    recommended_stage = stage
    decision = "hold"
    reason = "kpi_below_threshold"

    if kpi["healthy"]:
        if stage == "top_volume_subset":
            recommended_stage = "mid_segment"
            decision = "recommend_upgrade"
            reason = "healthy_for_upgrade"
        elif stage == "mid_segment":
            recommended_stage = "full_market"
            decision = "recommend_upgrade"
            reason = "healthy_for_upgrade"
        else:
            decision = "hold"
            reason = "already_full_market"

    payload = {
        "generated_at": datetime.now(timezone.utc),
        "current_stage": stage,
        "recommended_stage": recommended_stage,
        "decision": decision,
        "reason": reason,
        "kpi": kpi,
        "requires_admin_approval": True,
    }
    rollout.recommended_stage = recommended_stage
    rollout.recommendation_payload = {
        "decision": decision,
        "reason": reason,
        "kpi": kpi,
        "generated_at": payload["generated_at"].isoformat(),
    }
    rollout.requires_admin_approval = True
    db.commit()
    return payload


def approve_rollout_transition(db: Session, *, admin_user_id: str) -> dict:
    rollout = get_rollout_state(db)
    recommendation = rollout.recommendation_payload or {}
    target_stage = rollout.recommended_stage or rollout.current_stage
    if target_stage not in ROLLOUT_STAGES:
        target_stage = rollout.current_stage
    rollout.current_stage = target_stage
    rollout.approved_by = admin_user_id
    rollout.approved_at = datetime.now(timezone.utc)
    rollout.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {
        "current_stage": rollout.current_stage,
        "approved_by": admin_user_id,
        "approved_at": rollout.approved_at,
        "recommendation": recommendation,
    }


def get_perf_trend(db: Session, *, window: str = "24h") -> dict:
    _ensure_tables(db)
    now = datetime.now(timezone.utc)
    if window == "30d":
        since = now - timedelta(days=30)
        granularity = "day"
    elif window == "7d":
        since = now - timedelta(days=7)
        granularity = "day"
    else:
        since = now - timedelta(hours=24)
        granularity = "hour"

    rows = (
        db.query(ScannerPerformanceSnapshot)
        .filter(ScannerPerformanceSnapshot.created_at >= since)
        .order_by(ScannerPerformanceSnapshot.created_at.asc())
        .all()
    )

    buckets: dict[datetime, list[dict]] = defaultdict(list)
    for row in rows:
        bucket = _bucket_start(row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc), granularity=granularity)
        buckets[bucket].append(dict(row.metrics or {}))

    points = []
    for bucket in sorted(buckets.keys()):
        metrics = buckets[bucket]
        total_scanned = sum(float(item.get("total_active_symbols") or 0) for item in metrics)
        evaluated = sum(float(item.get("symbols_evaluated") or 0) for item in metrics)
        cycle_latency = sum(float(item.get("cycle_duration_ms") or 0) for item in metrics)
        stale_blocks = sum(float(item.get("stale_block_count") or 0) for item in metrics)
        dropped = sum(float(item.get("dropped_symbol_count") or 0) for item in metrics)
        points.append(
            {
                "bucket": bucket.isoformat(),
                "samples": len(metrics),
                "total_scanned_symbols": round(total_scanned, 4),
                "symbols_evaluated": round(evaluated, 4),
                "average_cycle_latency_ms": round(cycle_latency / max(len(metrics), 1), 4),
                "stale_blocks": round(stale_blocks, 4),
                "dropped_evaluations": round(dropped, 4),
            }
        )

    latest = points[-1] if points else {}
    return {
        "window": window,
        "granularity": granularity,
        "generated_at": now,
        "points": points,
        "latest": latest,
    }


def export_perf_trend_csv(db: Session, *, window: str = "24h") -> str:
    trend = get_perf_trend(db, window=window)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["bucket", "samples", "total_scanned_symbols", "symbols_evaluated", "average_cycle_latency_ms", "stale_blocks", "dropped_evaluations"])
    for point in trend.get("points", []):
        writer.writerow(
            [
                point.get("bucket"),
                point.get("samples"),
                point.get("total_scanned_symbols"),
                point.get("symbols_evaluated"),
                point.get("average_cycle_latency_ms"),
                point.get("stale_blocks"),
                point.get("dropped_evaluations"),
            ]
        )
    return output.getvalue()


def get_freshness_heatmap(db: Session, *, window: str = "24h") -> dict:
    now = datetime.now(timezone.utc)
    if window == "30d":
        since = now - timedelta(days=30)
    elif window == "7d":
        since = now - timedelta(days=7)
    else:
        since = now - timedelta(hours=24)

    rows = (
        db.query(UserScannerResult)
        .filter(UserScannerResult.generated_at >= since)
        .order_by(UserScannerResult.generated_at.desc())
        .limit(8000)
        .all()
    )

    heatmap: dict[str, dict] = defaultdict(lambda: {"total": 0, "stale": 0, "avg_snapshot_age": 0.0, "snapshot_samples": 0})
    for row in rows:
        payload = row.payload or {}
        symbol = str(row.symbol or "").upper() or "UNKNOWN"
        timeframe = str(payload.get("timeframe") or "15m").lower()
        key = f"{symbol}:{timeframe}"
        cell = heatmap[key]
        cell["total"] += 1
        age = payload.get("indicator_snapshot_age_sec")
        if isinstance(age, (int, float)):
            cell["avg_snapshot_age"] += float(age)
            cell["snapshot_samples"] += 1
        reasons = {str(item).lower() for item in (payload.get("reason_codes") or [])}
        if "stale_data_block" in reasons:
            cell["stale"] += 1

    items = []
    for key, value in heatmap.items():
        symbol, timeframe = key.split(":", 1)
        stale_rate = float(value["stale"]) / max(float(value["total"]), 1.0)
        avg_age = float(value["avg_snapshot_age"]) / max(float(value["snapshot_samples"]), 1.0)
        items.append(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "total": int(value["total"]),
                "stale": int(value["stale"]),
                "stale_rate": round(stale_rate, 6),
                "avg_snapshot_age": round(avg_age, 4),
            }
        )
    items.sort(key=lambda item: (item["stale_rate"], item["stale"], item["total"]), reverse=True)
    return {
        "window": window,
        "generated_at": now,
        "items": items[:500],
    }


def get_monitor_breakdown(db: Session, *, window: str = "7d") -> dict:
    now = datetime.now(timezone.utc)
    since = now - (timedelta(days=30) if window == "30d" else timedelta(days=7) if window == "7d" else timedelta(hours=24))

    snapshots = (
        db.query(ScannerPerformanceSnapshot)
        .filter(ScannerPerformanceSnapshot.created_at >= since)
        .order_by(ScannerPerformanceSnapshot.created_at.desc())
        .limit(5000)
        .all()
    )
    by_user: dict[str, dict] = defaultdict(lambda: {"runs": 0, "symbols_evaluated": 0.0, "stale_blocks": 0.0, "dropped": 0.0})
    for row in snapshots:
        key = str(row.user_id or "unknown")
        metrics = row.metrics or {}
        by_user[key]["runs"] += 1
        by_user[key]["symbols_evaluated"] += float(metrics.get("symbols_evaluated") or 0)
        by_user[key]["stale_blocks"] += float(metrics.get("stale_block_count") or 0)
        by_user[key]["dropped"] += float(metrics.get("dropped_symbol_count") or 0)

    user_items = []
    for user_id, item in by_user.items():
        evaluated = float(item["symbols_evaluated"])
        user_items.append(
            {
                "user_id": user_id,
                "runs": int(item["runs"]),
                "symbols_evaluated": round(evaluated, 4),
                "false_block_rate": round(float(item["stale_blocks"]) / max(evaluated, 1.0), 6),
                "missed_update_rate": round(float(item["dropped"]) / max(evaluated, 1.0), 6),
            }
        )
    user_items.sort(key=lambda item: item["symbols_evaluated"], reverse=True)

    result_rows = (
        db.query(UserScannerResult)
        .filter(UserScannerResult.generated_at >= since)
        .order_by(UserScannerResult.generated_at.desc())
        .limit(8000)
        .all()
    )
    regime_counts: dict[str, int] = defaultdict(int)
    for row in result_rows:
        regime = str((row.payload or {}).get("market_regime") or "unknown")
        regime_counts[regime] += 1

    regime_items = [{"regime": key, "count": value} for key, value in sorted(regime_counts.items(), key=lambda item: item[1], reverse=True)]
    return {
        "window": window,
        "generated_at": now,
        "user_breakdown": user_items[:200],
        "regime_breakdown": regime_items,
    }
