def compute_scaling_robustness_score(
    *,
    pnl_stability: float,
    slippage_impact: float,
    execution_quality: float,
    liquidity_stress: float,
    weights: dict,
) -> dict:
    normalized = {
        "pnl_stability": max(min(float(pnl_stability or 0.0), 100.0), 0.0),
        "slippage_impact": max(min(float(slippage_impact or 0.0), 100.0), 0.0),
        "execution_quality": max(min(float(execution_quality or 0.0), 100.0), 0.0),
        "liquidity_stress": max(min(float(liquidity_stress or 0.0), 100.0), 0.0),
    }

    score = sum(normalized[key] * float(weights.get(key, 0.25)) for key in normalized)
    state = "scalable"
    if score < 60:
        state = "unstable"
    elif score < 80:
        state = "caution"

    return {
        "scaling_robustness_score": round(score, 2),
        "robustness_state": state,
        "components": normalized,
        "weights": weights,
    }
