def apply_position_size_policy(
    *,
    strategy_capital_available: float,
    strategy_capital_budget: float,
    base_position_size_ratio: float,
    strategy_risk_weight: float,
    market_volatility_modifier: float,
    cluster_risk_modifier: float,
) -> dict:
    budget = max(float(strategy_capital_budget or 0.0), 1.0)
    available = max(float(strategy_capital_available or 0.0), 0.0)
    base_ratio = max(min(float(base_position_size_ratio or 0.0), 1.0), 0.0)

    capital_factor = max(min(available / budget, 1.0), 0.0)
    risk_factor = max(min(float(strategy_risk_weight or 1.0), 1.0), 0.0)
    vol_factor = max(min(float(market_volatility_modifier or 1.0), 1.0), 0.2)
    cluster_factor = max(min(float(cluster_risk_modifier or 1.0), 1.0), 0.2)

    adjusted_ratio = base_ratio * capital_factor * risk_factor * vol_factor * cluster_factor
    return {
        "base_position_size_ratio": round(base_ratio, 4),
        "capital_factor": round(capital_factor, 4),
        "strategy_risk_weight": round(risk_factor, 4),
        "market_volatility_modifier": round(vol_factor, 4),
        "cluster_risk_modifier": round(cluster_factor, 4),
        "adjusted_position_size_ratio": round(max(0.05, min(adjusted_ratio, 1.0)), 4),
    }
