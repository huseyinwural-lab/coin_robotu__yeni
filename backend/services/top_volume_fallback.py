from datetime import datetime, timezone

from services.pipeline.cache_store import get_json, set_json


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
    current_state = get_json(cache, FALLBACK_STATE_KEY) or {
        "active": False,
        "healthy_streak": 0,
        "last_trigger_metric": None,
        "last_exit_reason": None,
    }

    scan_latency_ms = _to_float(perf_state.get("cycle_duration_ms"), _to_float(queue_state.get("cycle_latency_ms"), 0.0))
    market_data_age_ms = _to_float(perf_state.get("snapshot_age_avg_sec"), 0.0) * 1000.0
    queue_depth = _to_int(queue_state.get("depth"), 0)
    backpressure = _to_float(queue_state.get("worker_utilization"), 0.0)

    enter_reasons = []
    if scan_latency_ms > 4000:
        enter_reasons.append("scan_latency_ms")
    if market_data_age_ms > 150000:
        enter_reasons.append("market_data_age_ms")
    if queue_depth > 50:
        enter_reasons.append("queue_depth")
    if backpressure > 0.9:
        enter_reasons.append("pipeline_backpressure")

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

    payload = {
        "active": bool(active),
        "healthy_streak": healthy_streak,
        "last_trigger_metric": last_trigger_metric,
        "last_exit_reason": last_exit_reason,
        "metrics": {
            "scan_latency_ms": round(scan_latency_ms, 4),
            "market_data_age_ms": round(market_data_age_ms, 4),
            "queue_depth": queue_depth,
            "pipeline_backpressure": round(backpressure, 6),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    set_json(cache, FALLBACK_STATE_KEY, payload)
    return payload
