import json

LATENCY_THRESHOLDS_KEY = "control_layer:latency_thresholds"
DEFAULT_LATENCY_THRESHOLDS = {
    "scan_latency_ms": 1500,
    "decision_latency_ms": 900,
    "execution_latency_ms": 1600,
}


def _decode(value):
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def get_latency_thresholds(cache) -> dict:
    raw = _decode(cache.get(LATENCY_THRESHOLDS_KEY))
    if not raw:
        return dict(DEFAULT_LATENCY_THRESHOLDS)
    try:
        payload = json.loads(raw)
    except Exception:
        return dict(DEFAULT_LATENCY_THRESHOLDS)

    return {
        "scan_latency_ms": float(payload.get("scan_latency_ms") or DEFAULT_LATENCY_THRESHOLDS["scan_latency_ms"]),
        "decision_latency_ms": float(payload.get("decision_latency_ms") or DEFAULT_LATENCY_THRESHOLDS["decision_latency_ms"]),
        "execution_latency_ms": float(payload.get("execution_latency_ms") or DEFAULT_LATENCY_THRESHOLDS["execution_latency_ms"]),
    }


def set_latency_thresholds(cache, thresholds: dict) -> dict:
    normalized = {
        "scan_latency_ms": float(thresholds.get("scan_latency_ms") or DEFAULT_LATENCY_THRESHOLDS["scan_latency_ms"]),
        "decision_latency_ms": float(thresholds.get("decision_latency_ms") or DEFAULT_LATENCY_THRESHOLDS["decision_latency_ms"]),
        "execution_latency_ms": float(thresholds.get("execution_latency_ms") or DEFAULT_LATENCY_THRESHOLDS["execution_latency_ms"]),
    }
    cache.set(LATENCY_THRESHOLDS_KEY, json.dumps(normalized))
    return normalized
