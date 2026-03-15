from datetime import datetime, timezone

from services.pipeline.cache_store import get_counter, get_json, set_json


FALLBACK_STATE_KEY = "scanner:runtime:fallback_state"


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def evaluate_top_volume_fallback(cache) -> dict:
    queue_state = get_json(cache, "scanner:queue:state") or {}
    perf_state = get_json(cache, "scanner:perf:latest:global") or {}
    runtime_state = get_json(cache, "scanner:runtime:latest:global") or {}
    runtime_metrics = runtime_state.get("runtime_metrics") or {}
    current_state = get_json(cache, FALLBACK_STATE_KEY) or {
        "active": False,
        "healthy_streak": 0,
        "last_trigger_metric": None,
        "last_exit_reason": None,
    }

    scan_latency_ms = _to_float(
        runtime_metrics.get("scan_latency_ms"),
        _to_float(perf_state.get("cycle_duration_ms"), _to_float(queue_state.get("cycle_latency_ms"), 0.0)),
    )
    decision_latency_ms = _to_float(runtime_metrics.get("decision_latency_ms"), 0.0)
    snapshot_age_ms = _to_float(runtime_metrics.get("snapshot_age_ms"), _to_float(perf_state.get("snapshot_age_avg_sec"), 0.0) * 1000.0)
    queue_depth = _to_int(runtime_metrics.get("queue_depth"), _to_int(queue_state.get("depth"), 0))
    candidate_count = _to_int(runtime_metrics.get("candidate_count"), 0)
    backpressure = _to_float(queue_state.get("worker_utilization"), 0.0)
    stale_reject_count = get_counter(cache, "risk:metrics:stale_reject_count")
    spread_reject_count = get_counter(cache, "risk:metrics:spread_reject_count")
    quality_warning_count = get_counter(cache, "risk:metrics:execution_quality_warning_count")
    quality_trend = get_json(cache, "risk:metrics:execution_quality_trend") or {}
    quality_ema = _to_float(quality_trend.get("ema_score"), 100.0)

    enter_reasons = []
    if scan_latency_ms > 4000:
        enter_reasons.append("latency_spike")
    if decision_latency_ms > 3000:
        enter_reasons.append("decision_latency_ms")
    if snapshot_age_ms > 150000:
        enter_reasons.append("snapshot_age_ms")
    if queue_depth > 50:
        enter_reasons.append("queue_depth")
    if backpressure > 0.9:
        enter_reasons.append("pipeline_backpressure")
    if stale_reject_count >= 10:
        enter_reasons.append("stale_reject_spike")
    if spread_reject_count >= 10:
        enter_reasons.append("spread_reject_spike")
    if quality_warning_count >= 20:
        enter_reasons.append("execution_quality_warning_spike")
    if quality_ema < 60:
        enter_reasons.append("execution_quality_drop")

    active = bool(current_state.get("active", False))
    healthy_streak = int(current_state.get("healthy_streak", 0))
    last_trigger_metric = current_state.get("last_trigger_metric")
    last_exit_reason = current_state.get("last_exit_reason")

    if enter_reasons:
        active = True
        healthy_streak = 0
        last_trigger_metric = enter_reasons[0]
    else:
        healthy_streak += 1
        if active and healthy_streak >= 3:
            active = False
            last_exit_reason = "recovery_cycles"

    discovery_cap = 300 if active else 700
    qualification_cap = 40 if active else 120
    decision_cap = 8 if active else 25
    scan_interval_seconds = 30 if active else 15

    payload = {
        "active": bool(active),
        "reason_code": str(last_trigger_metric or "none") if active else "none",
        "discovery_cap": discovery_cap,
        "qualification_cap": qualification_cap,
        "decision_cap": decision_cap,
        "scan_interval_seconds": scan_interval_seconds,
        "healthy_streak": healthy_streak,
        "last_trigger_metric": last_trigger_metric,
        "last_exit_reason": last_exit_reason,
        "metrics": {
            "scan_latency_ms": round(scan_latency_ms, 4),
            "decision_latency_ms": round(decision_latency_ms, 4),
            "snapshot_age_ms": round(snapshot_age_ms, 4),
            "queue_depth": queue_depth,
            "candidate_count": candidate_count,
            "pipeline_backpressure": round(backpressure, 6),
            "stale_reject_count": int(stale_reject_count),
            "spread_reject_count": int(spread_reject_count),
            "execution_quality_warning_count": int(quality_warning_count),
            "execution_quality_ema": round(quality_ema, 4),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    set_json(cache, FALLBACK_STATE_KEY, payload)
    return payload
