def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def evaluate_execution_quality(
    *,
    snapshot_age_ms: float,
    spread_bps: float,
    slippage_pct: float,
    execution_latency_ms: float,
    orderbook_depth_score: float,
    partial_fill_rate: float = 0.0,
    reject_rate: float = 0.0,
    stale_threshold_ms: float,
    spread_threshold_bps: float,
    max_slippage_pct: float,
    execution_quality_threshold: float,
) -> dict:
    stale_ratio = snapshot_age_ms / max(stale_threshold_ms, 1.0)
    spread_ratio = spread_bps / max(spread_threshold_bps, 0.1)
    slippage_ratio = slippage_pct / max(max_slippage_pct, 0.1)
    latency_ratio = execution_latency_ms / 3000.0
    depth_penalty = 1.0 - _clamp(orderbook_depth_score, 0.0, 1.0)
    partial_fill_penalty = _clamp(partial_fill_rate, 0.0, 1.0)
    reject_penalty = _clamp(reject_rate, 0.0, 1.0)

    weighted_penalty = (
        _clamp(stale_ratio, 0.0, 3.0) * 0.24
        + _clamp(spread_ratio, 0.0, 3.0) * 0.22
        + _clamp(slippage_ratio, 0.0, 3.0) * 0.16
        + _clamp(latency_ratio, 0.0, 3.0) * 0.12
        + _clamp(depth_penalty, 0.0, 1.0) * 0.10
        + partial_fill_penalty * 0.08
        + reject_penalty * 0.08
    )
    score = round(max(0.0, 100.0 - (weighted_penalty * 40.0)), 4)

    if score < min(execution_quality_threshold * 0.7, 45.0) or stale_ratio >= 2.0 or spread_ratio >= 2.0:
        severity = "severe"
        recommendation = "BLOCK"
    elif score < execution_quality_threshold or stale_ratio >= 1.0 or spread_ratio >= 1.0:
        severity = "medium"
        recommendation = "PASS"
    elif score < min(95.0, execution_quality_threshold + 10):
        severity = "mild"
        recommendation = "REDUCE_SIZE"
    else:
        severity = "normal"
        recommendation = "ALLOW"

    return {
        "score": score,
        "severity": severity,
        "recommendation": recommendation,
        "components": {
            "stale_ratio": round(_clamp(stale_ratio, 0.0, 10.0), 6),
            "spread_ratio": round(_clamp(spread_ratio, 0.0, 10.0), 6),
            "slippage_ratio": round(_clamp(slippage_ratio, 0.0, 10.0), 6),
            "latency_ratio": round(_clamp(latency_ratio, 0.0, 10.0), 6),
            "depth_penalty": round(_clamp(depth_penalty, 0.0, 1.0), 6),
            "partial_fill_rate": round(partial_fill_penalty, 6),
            "reject_rate": round(reject_penalty, 6),
        },
        "metrics": {
            "snapshot_age_ms": round(snapshot_age_ms, 4),
            "spread_bps": round(spread_bps, 4),
            "slippage_pct": round(slippage_pct, 4),
            "execution_latency_ms": round(execution_latency_ms, 4),
            "orderbook_depth_score": round(orderbook_depth_score, 4),
            "partial_fill_rate": round(partial_fill_penalty, 6),
            "reject_rate": round(reject_penalty, 6),
        },
    }
