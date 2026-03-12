def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def compute_tail_risk_score(market_metrics: dict) -> dict:
    volatility_pct = float(market_metrics.get("volatility_pct") or 0.0)
    liquidation_pressure_input = float(market_metrics.get("liquidation_pressure_input") or 0.0)
    liquidity_depth_score = float(market_metrics.get("liquidity_depth_score") or 0.0)
    spread_bps = float(market_metrics.get("spread_bps") or 0.0)

    volatility_score = _clamp(volatility_pct * 9.5)
    liquidation_pressure = _clamp(liquidation_pressure_input * 100)
    liquidity_score = _clamp((1 - liquidity_depth_score) * 100)
    spread_anomaly = _clamp(spread_bps * 0.9)

    tail_risk_score = (
        volatility_score * 0.32
        + liquidation_pressure * 0.28
        + liquidity_score * 0.22
        + spread_anomaly * 0.18
    )

    fallback_applied = False
    if market_metrics.get("fallback_mode"):
        tail_risk_score = max(tail_risk_score, 62.0)
        fallback_applied = True

    return {
        "volatility_score": round(volatility_score, 2),
        "liquidation_pressure": round(liquidation_pressure, 2),
        "liquidity_score": round(liquidity_score, 2),
        "spread_anomaly": round(spread_anomaly, 2),
        "tail_risk_score": round(_clamp(tail_risk_score), 2),
        "fallback_applied": fallback_applied,
    }
