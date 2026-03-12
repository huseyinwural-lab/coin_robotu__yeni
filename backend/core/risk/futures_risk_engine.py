from core.futures.position_model import FuturesPosition


DEFAULT_THRESHOLDS = {
    "max_leverage_per_trade": 5.0,
    "portfolio_leverage_limit": 2.5,
    "margin_usage_limit": 60.0,
    "liquidation_distance_min": 10.0,
}


def evaluate_futures_risk(position: FuturesPosition, portfolio_state: dict, thresholds: dict | None = None) -> dict:
    cfg = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    reasons: list[str] = []

    if position.leverage > cfg["max_leverage_per_trade"]:
        reasons.append("max_leverage_per_trade_exceeded")
    if float(portfolio_state.get("portfolio_leverage", 0.0)) > cfg["portfolio_leverage_limit"]:
        reasons.append("portfolio_leverage_limit_exceeded")
    if float(portfolio_state.get("margin_usage", 0.0)) > cfg["margin_usage_limit"]:
        reasons.append("margin_usage_limit_exceeded")
    if float(portfolio_state.get("distance_to_liquidation", 0.0)) < cfg["liquidation_distance_min"]:
        reasons.append("liquidation_distance_too_low")

    risk_score = min(100, len(reasons) * 25 + int(position.leverage * 5))
    return {
        "risk_check_result": "reject" if reasons else "allow",
        "risk_reason": reasons,
        "risk_score": risk_score,
    }
