from datetime import datetime, timezone

from services.pipeline.cache_store import get_counter, get_json, set_json


SCANNER_REGIME_STATE_KEY = "scanner:regime:latest"

REGIME_PROFILES = {
    "normal": {"discovery_cap": 700, "qualification_cap": 120, "decision_cap": 25},
    "volatile": {"discovery_cap": 500, "qualification_cap": 80, "decision_cap": 15},
    "stress": {"discovery_cap": 300, "qualification_cap": 40, "decision_cap": 8},
}


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def resolve_scanner_regime(cache, *, runtime_metrics: dict, fallback_active: bool) -> dict:
    volatility_index = _to_float((get_json(cache, "market:regime:volatility") or {}).get("index"), 0.0)
    if volatility_index <= 0:
        volatility_index = _to_float((get_json(cache, "scanner:perf:latest:global") or {}).get("volatility_index"), 0.0)

    spread_regime = str((get_json(cache, "market:regime:spread") or {}).get("regime") or "normal").lower()
    latency_ms = _to_float(runtime_metrics.get("scan_latency_ms"), 0.0)
    queue_depth = int(runtime_metrics.get("queue_depth") or 0)
    quality_trend = get_json(cache, "risk:metrics:execution_quality_trend") or {}
    quality_ema = _to_float(quality_trend.get("ema_score"), 100.0)
    warning_rate = _to_float(quality_trend.get("warning_rate"), 0.0)

    regime = "normal"
    reasons: list[str] = []

    if fallback_active:
        regime = "stress"
        reasons.append("fallback_active")

    if queue_depth >= 50 or latency_ms >= 4500:
        regime = "stress"
        reasons.append("latency_or_queue_stress")
    elif queue_depth >= 20 or latency_ms >= 2500:
        regime = "volatile"
        reasons.append("latency_or_queue_volatile")

    if volatility_index >= 0.75:
        regime = "stress"
        reasons.append("volatility_index_high")
    elif volatility_index >= 0.45 and regime != "stress":
        regime = "volatile"
        reasons.append("volatility_index_moderate")

    if spread_regime in {"stress", "wide"}:
        regime = "stress"
        reasons.append("spread_regime_stress")
    elif spread_regime in {"volatile", "elevated"} and regime != "stress":
        regime = "volatile"
        reasons.append("spread_regime_volatile")

    if quality_ema < 55 or warning_rate > 0.35:
        regime = "stress"
        reasons.append("execution_quality_drop")
    elif quality_ema < 70 and regime == "normal":
        regime = "volatile"
        reasons.append("execution_quality_soft_drop")

    caps = dict(REGIME_PROFILES[regime])
    stale_reject = int(get_counter(cache, "risk:metrics:stale_reject_count"))
    spread_reject = int(get_counter(cache, "risk:metrics:spread_reject_count"))
    if stale_reject >= 20 or spread_reject >= 20:
        regime = "stress"
        caps = dict(REGIME_PROFILES["stress"])
        reasons.append("quality_reject_spike")

    payload = {
        "regime": regime,
        "caps": caps,
        "reasons": sorted(set(reasons)) or ["steady_state"],
        "inputs": {
            "volatility_index": round(volatility_index, 6),
            "spread_regime": spread_regime,
            "latency_ms": round(latency_ms, 4),
            "queue_depth": queue_depth,
            "execution_quality_ema": round(quality_ema, 4),
            "execution_quality_warning_rate": round(warning_rate, 6),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    set_json(cache, SCANNER_REGIME_STATE_KEY, payload)
    return payload


def get_latest_scanner_regime(cache) -> dict:
    return get_json(cache, SCANNER_REGIME_STATE_KEY) or {
        "regime": "normal",
        "caps": dict(REGIME_PROFILES["normal"]),
        "reasons": ["not_initialized"],
    }
