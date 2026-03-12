from datetime import datetime, timezone


def evaluate_capital_order_guard(
    *,
    strategy_id: str,
    projected_order_notional: float,
    strategy_budget_row: dict,
    portfolio_registry: dict,
    cluster_risk_state: str,
) -> dict:
    budget = float(strategy_budget_row.get("strategy_capital_budget") or 0.0)
    used = float(strategy_budget_row.get("strategy_capital_used") or 0.0)
    warning = float(strategy_budget_row.get("warning_threshold") or 0.0)
    available_portfolio = float(portfolio_registry.get("available_capital") or 0.0)
    order_notional = max(float(projected_order_notional or 0.0), 0.0)

    reasons: list[str] = []
    action = "ALLOW"
    size_multiplier = 1.0

    if used + order_notional > budget:
        action = "REJECT"
        size_multiplier = 0.0
        reasons.append("STRATEGY_BUDGET_LIMIT")
    elif used + order_notional > warning:
        action = "REDUCE_SIZE"
        size_multiplier = 0.6
        reasons.append("STRATEGY_BUDGET_WARNING")

    if available_portfolio < order_notional * 0.5:
        action = "REDUCE_SIZE" if action != "REJECT" else action
        size_multiplier = min(size_multiplier, 0.5)
        reasons.append("PORTFOLIO_RISK_LIMIT")

    if cluster_risk_state == "ALERT":
        if action == "ALLOW":
            action = "REDUCE_SIZE"
            size_multiplier = min(size_multiplier, 0.7)
        reasons.append("CLUSTER_RISK_ALIGNMENT")

    event = None
    if action == "REJECT":
        event = {
            "event": "CAPITAL_TRADE_REJECTED",
            "strategy_id": strategy_id,
            "budget": round(budget, 4),
            "capital_used": round(used, 4),
            "projected_notional": round(order_notional, 4),
            "reason": reasons,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "action": action,
        "size_multiplier": round(size_multiplier, 4),
        "reason": reasons,
        "event": event,
    }
