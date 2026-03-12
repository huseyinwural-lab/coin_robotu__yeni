from datetime import datetime, timezone


def detect_capital_drift(
    strategy_allocation: list[dict],
    *,
    previous_usage: dict | None = None,
) -> dict:
    previous_usage = previous_usage or {}
    events: list[dict] = []
    by_strategy: dict[str, dict] = {}

    for row in strategy_allocation:
        strategy_id = str(row.get("strategy_id") or "unknown")
        used = float(row.get("strategy_capital_used") or 0.0)
        budget = max(float(row.get("strategy_capital_budget") or 0.0), 1.0)
        warning = float(row.get("warning_threshold") or 0.0)
        prev = max(float(previous_usage.get(strategy_id) or 0.0), 0.0)

        reasons: list[str] = []
        if used > budget:
            reasons.append("CAPITAL_USAGE_EXCEEDS_BUDGET")
        if used > warning:
            reasons.append("CAPITAL_USAGE_WARNING")
        growth_ratio = ((used - prev) / prev) if prev > 0 else 0.0
        if prev > 0 and growth_ratio > 0.35:
            reasons.append("CAPITAL_USAGE_GROWTH_ANOMALY")

        if reasons:
            severity = "HIGH" if "CAPITAL_USAGE_EXCEEDS_BUDGET" in reasons else "MEDIUM"
            events.append(
                {
                    "event": "CAPITAL_BUDGET_DRIFT",
                    "strategy_id": strategy_id,
                    "reasons": reasons,
                    "drift_severity": severity,
                    "capital_used": round(used, 4),
                    "capital_budget": round(budget, 4),
                    "growth_ratio": round(growth_ratio, 4),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

        by_strategy[strategy_id] = {
            "capital_used": round(used, 4),
            "capital_budget": round(budget, 4),
            "growth_ratio": round(growth_ratio, 4),
            "drift_state": "DRIFT" if reasons else "NORMAL",
            "reasons": reasons,
        }

    return {
        "capital_drift_events": events,
        "capital_drift_by_strategy": by_strategy,
    }
