def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _calculate_score(item: dict) -> float:
    performance_score = _safe_float(item.get("performance_score"), 0)
    sharpe_like = _safe_float(item.get("execution_quality_score"), 0) / 100
    drawdown_penalty = _safe_float(item.get("signal_decay"), 0)
    risk_score = _safe_float(item.get("risk_score"), 0)
    return (performance_score * 0.45) + (sharpe_like * 35) + ((1 - drawdown_penalty) * 15) + ((1 - risk_score) * 5)


def run_dynamic_capital_rebalance(strategy_performance: list[dict], drift_threshold: float = 0.08) -> dict:
    if not strategy_performance:
        return {
            "allocation_drift": 0.0,
            "strategy_performance_delta": 0.0,
            "risk_adjusted_return": 0.0,
            "events": [],
        }

    scored = []
    total_score = 0.0
    for item in strategy_performance:
        score = max(_calculate_score(item), 0.0001)
        total_score += score
        scored.append({**item, "_score": score})

    events: list[dict] = []
    aggregate_drift = 0.0
    performance_deltas: list[float] = []
    risk_adjusted_returns: list[float] = []

    for item in scored:
        strategy_id = str(item.get("strategy_id") or "unknown_strategy")
        current_weight = _safe_float(item.get("capital_weight"), 1)
        target_weight = round(item["_score"] / total_score, 6)
        capital_usage = _safe_float(item.get("current_capital"), 0)
        max_capital = max(_safe_float(item.get("max_capital"), 1), 1)
        usage_ratio = capital_usage / max_capital
        allocation_drift = round(abs(target_weight - current_weight), 6)
        aggregate_drift += allocation_drift

        capital_shift = round((target_weight - current_weight) * max_capital, 4)
        throttle_signal = allocation_drift > drift_threshold or usage_ratio > 0.95

        performance_delta = round(_safe_float(item.get("performance_score"), 0) - _safe_float(item.get("confidence_score"), 0), 6)
        risk_adjusted_return = round(
            _safe_float(item.get("realized_return"), 0) - _safe_float(item.get("signal_decay"), 0) * 2,
            6,
        )

        performance_deltas.append(performance_delta)
        risk_adjusted_returns.append(risk_adjusted_return)

        events.append(
            {
                "strategy_id": strategy_id,
                "old_strategy_weight": round(current_weight, 6),
                "new_strategy_weight": target_weight,
                "capital_shift": capital_shift,
                "throttle_signal": bool(throttle_signal),
                "allocation_drift": allocation_drift,
                "strategy_performance_delta": performance_delta,
                "risk_adjusted_return": risk_adjusted_return,
            }
        )

    strategy_performance_delta = round(sum(performance_deltas) / max(len(performance_deltas), 1), 6)
    risk_adjusted_return = round(sum(risk_adjusted_returns) / max(len(risk_adjusted_returns), 1), 6)
    return {
        "allocation_drift": round(aggregate_drift / max(len(events), 1), 6),
        "strategy_performance_delta": strategy_performance_delta,
        "risk_adjusted_return": risk_adjusted_return,
        "events": events,
    }
