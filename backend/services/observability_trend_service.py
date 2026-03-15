from datetime import datetime, timezone

from services.pipeline.cache_store import get_json, set_json


TREND_EXECUTION_LATENCY = "admin:observability:trend:execution_latency"
TREND_RISK_VETO_RATE = "admin:observability:trend:risk_veto_rate"
TREND_SCANNER_CYCLE = "admin:observability:trend:scanner_cycle_latency"
TREND_FALLBACK_RATE = "admin:observability:trend:fallback_activation"


def append_trend_sample(cache, key: str, value: float, *, max_points: int = 240) -> list[dict]:
    rows = get_json(cache, key) or []
    rows.append(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "value": round(float(value), 6),
        }
    )
    if len(rows) > max_points:
        rows = rows[-max_points:]
    set_json(cache, key, rows)
    return rows


def record_runtime_observability_trends(
    cache,
    *,
    execution_latency_ms: float,
    scanner_cycle_latency_ms: float,
    risk_veto_rate: float,
    fallback_active: bool,
) -> None:
    append_trend_sample(cache, TREND_EXECUTION_LATENCY, execution_latency_ms)
    append_trend_sample(cache, TREND_SCANNER_CYCLE, scanner_cycle_latency_ms)
    append_trend_sample(cache, TREND_RISK_VETO_RATE, risk_veto_rate)
    append_trend_sample(cache, TREND_FALLBACK_RATE, 1.0 if fallback_active else 0.0)


def get_admin_observability_trends(cache) -> dict:
    return {
        "execution_latency_trend": get_json(cache, TREND_EXECUTION_LATENCY) or [],
        "risk_veto_rate_trend": get_json(cache, TREND_RISK_VETO_RATE) or [],
        "scanner_cycle_latency_trend": get_json(cache, TREND_SCANNER_CYCLE) or [],
        "fallback_activation_rate_trend": get_json(cache, TREND_FALLBACK_RATE) or [],
    }
