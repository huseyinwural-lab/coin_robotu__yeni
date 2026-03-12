def evaluate_margin_utilization(margin_usage_pct: float) -> dict:
    if margin_usage_pct >= 80:
        state = "EMERGENCY"
        allowed = False
    elif margin_usage_pct >= 72:
        state = "CRITICAL"
        allowed = False
    elif margin_usage_pct > 60:
        state = "WARNING"
        allowed = True
    else:
        state = "SAFE"
        allowed = True
    return {
        "margin_usage": round(margin_usage_pct, 4),
        "margin_state": state,
        "policy_state": state,
        "new_position_allowed": allowed,
    }
