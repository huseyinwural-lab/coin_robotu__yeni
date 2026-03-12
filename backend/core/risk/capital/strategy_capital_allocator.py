def allocate_strategy_capital(
    *,
    strategy_ids: list[str],
    portfolio_equity: float,
    capital_usage_by_strategy: dict,
    max_strategy_capital_ratio: float = 0.20,
    soft_warning_ratio: float = 0.15,
) -> dict:
    equity = max(float(portfolio_equity or 0.0), 1.0)
    rows: list[dict] = []

    for strategy in sorted(strategy_ids):
        budget = equity * max_strategy_capital_ratio
        warning_threshold = equity * soft_warning_ratio
        used = max(float(capital_usage_by_strategy.get(strategy) or 0.0), 0.0)
        available = max(budget - used, 0.0)

        risk_state = "NORMAL"
        if used > budget:
            risk_state = "LIMIT_HIT"
        elif used > warning_threshold:
            risk_state = "WARNING"

        rows.append(
            {
                "strategy_id": strategy,
                "strategy_capital_budget": round(budget, 4),
                "strategy_capital_used": round(used, 4),
                "strategy_capital_available": round(available, 4),
                "warning_threshold": round(warning_threshold, 4),
                "risk_state": risk_state,
            }
        )

    return {
        "max_strategy_capital_ratio": max_strategy_capital_ratio,
        "soft_warning_ratio": soft_warning_ratio,
        "strategy_allocation": rows,
    }
