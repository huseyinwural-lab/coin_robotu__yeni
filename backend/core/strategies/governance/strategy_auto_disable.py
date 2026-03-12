from datetime import datetime, timezone


def evaluate_strategy_auto_disable(
    health_rows: list[dict],
    *,
    decay_state: dict,
    lifecycle_registry: dict,
    health_disable_threshold: float = 22.0,
    repeated_decay_limit: int = 3,
    pnl_drawdown_limit: float = -0.004,
) -> dict:
    rows: list[dict] = []
    by_strategy: dict[str, dict] = {}
    disable_events: list[dict] = []

    for row in health_rows:
        strategy = str(row.get("strategy") or "unknown")
        health_score = float(row.get("strategy_health_score") or 0.0)
        pnl_rolling = float(row.get("strategy_pnl_rolling") or 0.0)
        drawdown_state = str(row.get("drawdown_state") or "NORMAL")
        decay = decay_state.get(strategy) or {}
        repeated_decay_count = int(decay.get("repeated_decay_count") or 0)

        current_lifecycle = str((lifecycle_registry.get(strategy) or {}).get("lifecycle_state") or "ACTIVE")
        if current_lifecycle == "DISABLED":
            state = {
                "strategy": strategy,
                "disable_state": "DISABLED",
                "should_disable": True,
                "reasons": ["ALREADY_DISABLED"],
                "controlled_recovery_state": "OBSERVE_ONLY",
                "health_score": round(health_score, 2),
                "drawdown_state": drawdown_state,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            rows.append(state)
            by_strategy[strategy] = state
            continue

        reasons: list[str] = []
        if health_score < health_disable_threshold:
            reasons.append("HEALTH_SCORE_UNDER_THRESHOLD")
        if repeated_decay_count >= repeated_decay_limit:
            reasons.append("REPEATED_DECAY_LIMIT_REACHED")
        if pnl_rolling <= pnl_drawdown_limit or drawdown_state == "LIMIT_BREACH":
            reasons.append("PNL_DRAWDOWN_LIMIT_EXCEEDED")

        should_disable = len(reasons) >= 2
        state = {
            "strategy": strategy,
            "disable_state": "DISABLED" if should_disable else "ACTIVE",
            "should_disable": should_disable,
            "reasons": reasons,
            "controlled_recovery_state": "LOCKED" if should_disable else "NOT_REQUIRED",
            "health_score": round(health_score, 2),
            "drawdown_state": drawdown_state,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        rows.append(state)
        by_strategy[strategy] = state

        if should_disable:
            disable_events.append(
                {
                    "strategy": strategy,
                    "event": "STRATEGY_DISABLED",
                    "severity": "CRITICAL",
                    "reasons": reasons,
                    "health_score": round(health_score, 2),
                    "repeated_decay_count": repeated_decay_count,
                    "drawdown_state": drawdown_state,
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                }
            )

    return {
        "strategy_disable_state": rows,
        "by_strategy": by_strategy,
        "disabled_count": len([item for item in rows if item.get("disable_state") == "DISABLED"]),
        "disable_events": disable_events,
    }
