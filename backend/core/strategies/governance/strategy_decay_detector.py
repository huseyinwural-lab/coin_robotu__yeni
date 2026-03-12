from datetime import datetime, timezone


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def detect_strategy_decay(
    health_rows: list[dict],
    *,
    previous_state: dict | None = None,
    min_observation_threshold: int = 4,
    persistence_threshold: int = 2,
) -> dict:
    previous_state = previous_state or {}
    updated_state: dict[str, dict] = {}
    events: list[dict] = []

    for row in health_rows:
        strategy = str(row.get("strategy") or "unknown")
        current_state = previous_state.get(strategy) or {}
        previous_persistence = _safe_int(current_state.get("persistence_count"), 0)
        repeated_decay_count = _safe_int(current_state.get("repeated_decay_count"), 0)

        observation_count = _safe_int(row.get("observation_count"), 0)
        if observation_count < min_observation_threshold:
            updated_state[strategy] = {
                "strategy": strategy,
                "persistence_count": max(0, previous_persistence - 1),
                "repeated_decay_count": repeated_decay_count,
                "last_decay_reasons": [],
                "state": "INSUFFICIENT_DATA",
                "last_updated_at": datetime.now(timezone.utc).isoformat(),
            }
            continue

        triggers: list[str] = []
        if float(row.get("strategy_pnl_rolling") or 0.0) < -0.0016:
            triggers.append("PNL_DETERIORATION")
        if float(row.get("strategy_win_rate_rolling") or 0.0) < 0.36:
            triggers.append("WIN_RATE_COLLAPSE")
        if float(row.get("strategy_confidence_vs_result") or 0.0) > 0.52:
            triggers.append("CONFIDENCE_RESULT_DIVERGENCE")
        if float(row.get("strategy_execution_quality") or 0.0) < 0.45:
            triggers.append("EXECUTION_QUALITY_DEGRADATION")

        triggered = len(triggers) > 0
        persistence_count = previous_persistence + 1 if triggered else max(0, previous_persistence - 1)
        is_structural = triggered and persistence_count >= persistence_threshold

        if is_structural:
            repeated_decay_count += 1
            decay_type = "MULTI_TRIGGER" if len(triggers) >= 2 else "SINGLE_TRIGGER"
            severity = "HIGH" if len(triggers) >= 3 or repeated_decay_count >= 4 else "MEDIUM"
            events.append(
                {
                    "strategy": strategy,
                    "event": "STRATEGY_DECAY_DETECTED",
                    "severity": severity,
                    "decay_type": decay_type,
                    "decay_reason_codes": triggers,
                    "persistence_count": persistence_count,
                    "repeated_decay_count": repeated_decay_count,
                    "observation_count": observation_count,
                    "noise_state": "STRUCTURAL",
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                }
            )

        updated_state[strategy] = {
            "strategy": strategy,
            "persistence_count": persistence_count,
            "repeated_decay_count": repeated_decay_count,
            "last_decay_reasons": triggers,
            "state": "DECAY" if triggered else "STABLE",
            "last_updated_at": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "strategy_decay_events": events,
        "decay_state": updated_state,
        "event_count": len(events),
    }
