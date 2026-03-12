from datetime import datetime, timezone


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _avg(values: list[float], default: float = 0.0) -> float:
    if not values:
        return default
    return sum(values) / len(values)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _history_rows_for_strategy(history: list[dict], strategy: str) -> list[dict]:
    rows: list[dict] = []
    for entry in history:
        metrics = entry.get("strategy_metrics") or []
        attribution = entry.get("strategy_attribution") or []
        metric_row = next((item for item in metrics if str(item.get("strategy")) == strategy), None)
        attribution_row = next((item for item in attribution if str(item.get("strategy")) == strategy), None)
        if metric_row or attribution_row:
            rows.append(
                {
                    "metric": metric_row or {},
                    "attribution": attribution_row or {},
                    "ts": entry.get("ts"),
                }
            )
    return rows


def build_strategy_health_snapshot(
    *,
    history: list[dict],
    strategy_metrics: list[dict],
    strategy_attribution: list[dict],
    window_size: int = 84,
    min_observation_threshold: int = 3,
) -> dict:
    strategy_ids = sorted({str(item.get("strategy") or "unknown") for item in strategy_metrics})
    if not strategy_ids:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "strategies": [],
            "by_strategy": {},
            "window_size": window_size,
            "min_observation_threshold": min_observation_threshold,
        }

    attribution_map = {str(item.get("strategy")): item for item in strategy_attribution}
    rows: list[dict] = []

    for strategy in strategy_ids:
        current_metric = next((item for item in strategy_metrics if str(item.get("strategy")) == strategy), {})
        current_attr = attribution_map.get(strategy, {})

        raw_history = _history_rows_for_strategy(history[-window_size:], strategy)
        pnl_rolling = [_safe_float(item.get("metric", {}).get("paper_pnl")) for item in raw_history]
        win_rate_rolling = [_safe_float(item.get("attribution", {}).get("win_rate"), 0.5) for item in raw_history]
        quality_rolling = [_safe_float(item.get("metric", {}).get("execution_quality"), 0.5) for item in raw_history]

        confidence_alignment_rolling: list[float] = []
        for item in raw_history:
            confidence = _safe_float(item.get("metric", {}).get("avg_confidence"), 0.5)
            pnl = _safe_float(item.get("metric", {}).get("paper_pnl"), 0.0)
            expected = 1.0 if pnl > 0 else 0.0
            confidence_alignment_rolling.append(abs(confidence - expected))

        if not pnl_rolling:
            pnl_rolling = [_safe_float(current_metric.get("paper_pnl"), 0.0)]
        if not win_rate_rolling:
            win_rate_rolling = [_safe_float(current_attr.get("win_rate"), 0.5)]
        if not quality_rolling:
            quality_rolling = [_safe_float(current_metric.get("execution_quality"), 0.5)]
        if not confidence_alignment_rolling:
            current_confidence = _safe_float(current_metric.get("avg_confidence"), 0.5)
            current_pnl = _safe_float(current_metric.get("paper_pnl"), 0.0)
            confidence_alignment_rolling = [abs(current_confidence - (1.0 if current_pnl > 0 else 0.0))]

        observation_count = len(raw_history)
        avg_pnl = _avg(pnl_rolling, 0.0)
        avg_win_rate = _avg(win_rate_rolling, 0.5)
        avg_quality = _avg(quality_rolling, 0.5)
        avg_divergence = _avg(confidence_alignment_rolling, 0.5)

        pnl_component = _clamp(50 + avg_pnl * 15000, 0, 100)
        win_rate_component = _clamp(avg_win_rate * 100, 0, 100)
        execution_quality_component = _clamp(avg_quality * 100, 0, 100)
        confidence_alignment_component = _clamp((1 - avg_divergence) * 100, 0, 100)

        score = (
            pnl_component * 0.32
            + win_rate_component * 0.24
            + execution_quality_component * 0.24
            + confidence_alignment_component * 0.20
        )

        missing_components: list[str] = []
        if not current_metric:
            missing_components.append("current_metric")
        if not current_attr:
            missing_components.append("current_attribution")
        if observation_count < min_observation_threshold:
            score = min(score, 62.0)
            missing_components.append("insufficient_observation")

        drawdown_state = "NORMAL"
        min_pnl = min(pnl_rolling) if pnl_rolling else 0.0
        if min_pnl <= -0.005:
            drawdown_state = "LIMIT_BREACH"
        elif min_pnl <= -0.0025:
            drawdown_state = "ELEVATED"

        row = {
            "strategy": strategy,
            "strategy_pnl_rolling": round(avg_pnl, 6),
            "strategy_win_rate_rolling": round(avg_win_rate, 4),
            "strategy_execution_quality": round(avg_quality, 4),
            "strategy_confidence_vs_result": round(avg_divergence, 4),
            "strategy_health_score": round(_clamp(score, 0, 100), 2),
            "health_components": {
                "pnl_component": round(pnl_component, 2),
                "win_rate_component": round(win_rate_component, 2),
                "execution_quality_component": round(execution_quality_component, 2),
                "confidence_alignment_component": round(confidence_alignment_component, 2),
            },
            "observation_count": observation_count,
            "min_observation_threshold": min_observation_threshold,
            "data_state": "CONTROLLED_DEGRADE" if "insufficient_observation" in missing_components else "HEALTHY",
            "missing_components": missing_components,
            "drawdown_state": drawdown_state,
            "last_updated_at": datetime.now(timezone.utc).isoformat(),
        }
        rows.append(row)

    by_strategy = {row["strategy"]: row for row in rows}
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategies": rows,
        "by_strategy": by_strategy,
        "window_size": window_size,
        "min_observation_threshold": min_observation_threshold,
    }
