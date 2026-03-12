def calculate_funding_bias(funding_rate: float, funding_history: list[float] | None = None) -> dict:
    history = funding_history or []
    trend = 0.0
    if history:
        trend = (history[-1] - history[0]) if len(history) > 1 else history[-1]

    pressure = abs(funding_rate) + abs(trend)
    bias_direction = "NEUTRAL"
    if funding_rate > 0:
        bias_direction = "SHORT_BIAS"
    elif funding_rate < 0:
        bias_direction = "LONG_BIAS"

    if pressure >= 0.0015:
        state = "HIGH"
    elif pressure >= 0.0007:
        state = "MEDIUM"
    else:
        state = "LOW"

    bias_score = min(100.0, pressure * 100000)
    return {
        "funding_rate": funding_rate,
        "funding_trend": round(trend, 8),
        "funding_bias_score": round(bias_score, 4),
        "bias_direction": bias_direction,
        "funding_pressure_state": state,
    }
