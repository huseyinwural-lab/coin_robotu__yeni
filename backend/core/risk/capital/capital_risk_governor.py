from datetime import datetime, timezone


def enforce_capital_risk(strategy_allocation: list[dict], capital_drift_events: list[dict]) -> dict:
    drift_map = {str(item.get("strategy_id")): item for item in capital_drift_events}
    actions: list[dict] = []
    events: list[dict] = []

    for row in strategy_allocation:
        strategy_id = str(row.get("strategy_id") or "unknown")
        used = float(row.get("strategy_capital_used") or 0.0)
        budget = float(row.get("strategy_capital_budget") or 0.0)
        risk_state = str(row.get("risk_state") or "NORMAL")
        drift = drift_map.get(strategy_id)

        action = "ALLOW"
        position_size_multiplier = 1.0
        risk_downshift = False
        reason: list[str] = []

        if risk_state == "LIMIT_HIT":
            action = "REJECT_TRADE"
            position_size_multiplier = 0.0
            risk_downshift = True
            reason.append("CAPITAL_LIMIT_BREACH")
        elif risk_state == "WARNING" or drift:
            action = "REDUCE_POSITION_SIZE"
            position_size_multiplier = 0.65
            risk_downshift = True
            reason.append("CAPITAL_WARNING")

        action_row = {
            "strategy_id": strategy_id,
            "action": action,
            "position_size_multiplier": position_size_multiplier,
            "risk_downshift": risk_downshift,
            "reason": reason,
        }
        actions.append(action_row)

        if action in {"REJECT_TRADE", "REDUCE_POSITION_SIZE"}:
            events.append(
                {
                    "event": "CAPITAL_LIMIT_HIT",
                    "strategy_id": strategy_id,
                    "capital_used": round(used, 4),
                    "capital_budget": round(budget, 4),
                    "reason": reason,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

    return {
        "capital_risk_actions": actions,
        "capital_limit_events": events,
    }
