from datetime import datetime, timezone


def build_capital_governance_audit_events(
    *,
    capital_limit_events: list[dict],
    capital_drift_events: list[dict],
    capital_trade_reject_events: list[dict],
    capital_reallocation_rows: list[dict],
) -> list[dict]:
    now_iso = datetime.now(timezone.utc).isoformat()
    events: list[dict] = []

    for item in capital_limit_events:
        events.append(
            {
                "event": "CAPITAL_LIMIT_HIT",
                "strategy_id": item.get("strategy_id"),
                "budget": item.get("capital_budget", 0.0),
                "capital_used": item.get("capital_used", 0.0),
                "portfolio_equity": item.get("portfolio_equity", 0.0),
                "reason": item.get("reason") or [],
                "timestamp": item.get("timestamp") or now_iso,
            }
        )

    for item in capital_drift_events:
        events.append(
            {
                "event": "CAPITAL_BUDGET_DRIFT",
                "strategy_id": item.get("strategy_id"),
                "budget": item.get("capital_budget", 0.0),
                "capital_used": item.get("capital_used", 0.0),
                "portfolio_equity": item.get("portfolio_equity", 0.0),
                "reason": item.get("reasons") or [],
                "timestamp": item.get("timestamp") or now_iso,
            }
        )

    for item in capital_trade_reject_events:
        events.append(
            {
                "event": "CAPITAL_TRADE_REJECTED",
                "strategy_id": item.get("strategy_id"),
                "budget": item.get("budget", 0.0),
                "capital_used": item.get("capital_used", 0.0),
                "portfolio_equity": item.get("portfolio_equity", 0.0),
                "reason": item.get("reason") or [],
                "timestamp": item.get("timestamp") or now_iso,
            }
        )

    for item in capital_reallocation_rows:
        events.append(
            {
                "event": "CAPITAL_REALLOCATION",
                "strategy_id": item.get("strategy_id"),
                "budget": item.get("strategy_capital_budget", 0.0),
                "capital_used": item.get("strategy_capital_used", 0.0),
                "portfolio_equity": item.get("portfolio_equity", 0.0),
                "reason": ["PERIODIC_REALLOCATION"],
                "timestamp": now_iso,
            }
        )

    return events
