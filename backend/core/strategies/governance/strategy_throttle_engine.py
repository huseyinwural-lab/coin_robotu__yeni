from datetime import datetime, timezone


LEVEL_CONFIG = {
    "NONE": {"confidence_cap": 1.0, "max_signals_per_cycle": 8, "max_position_ratio": 1.0},
    "L1": {"confidence_cap": 0.86, "max_signals_per_cycle": 5, "max_position_ratio": 0.78},
    "L2": {"confidence_cap": 0.74, "max_signals_per_cycle": 3, "max_position_ratio": 0.58},
    "L3": {"confidence_cap": 0.62, "max_signals_per_cycle": 1, "max_position_ratio": 0.35},
}
LEVEL_ORDER = ["NONE", "L1", "L2", "L3"]


def _level_from_health(score: float) -> str:
    if score < 28:
        return "L3"
    if score < 45:
        return "L2"
    if score < 62:
        return "L1"
    return "NONE"


def _max_level(level_a: str, level_b: str) -> str:
    rank_a = LEVEL_ORDER.index(level_a) if level_a in LEVEL_ORDER else 0
    rank_b = LEVEL_ORDER.index(level_b) if level_b in LEVEL_ORDER else 0
    return LEVEL_ORDER[max(rank_a, rank_b)]


def _step_down(level: str) -> str:
    if level not in LEVEL_ORDER:
        return "NONE"
    idx = LEVEL_ORDER.index(level)
    if idx == 0:
        return "NONE"
    return LEVEL_ORDER[idx - 1]


def build_strategy_throttle_state(
    health_rows: list[dict],
    decay_events: list[dict],
    *,
    previous_state: dict | None = None,
) -> dict:
    previous_state = previous_state or {}
    decay_map = {str(item.get("strategy")): item for item in decay_events}

    rows: list[dict] = []
    by_strategy: dict[str, dict] = {}
    throttled_count = 0

    for row in health_rows:
        strategy = str(row.get("strategy") or "unknown")
        score = float(row.get("strategy_health_score") or 0.0)
        previous = previous_state.get(strategy) or {}
        previous_level = str(previous.get("throttle_level") or "NONE")

        level = _level_from_health(score)
        event = decay_map.get(strategy)
        if event:
            severity = str(event.get("severity") or "MEDIUM").upper()
            if severity == "HIGH":
                level = _max_level(level, "L3")
            else:
                level = _max_level(level, "L2")
        elif score >= 72 and previous_level in {"L1", "L2", "L3"}:
            level = _step_down(previous_level)

        config = LEVEL_CONFIG[level]
        if level != "NONE":
            throttled_count += 1

        state = {
            "strategy": strategy,
            "throttle_level": level,
            "confidence_clamp": config["confidence_cap"],
            "max_signals_per_cycle": config["max_signals_per_cycle"],
            "max_position_ratio": config["max_position_ratio"],
            "recovery_condition": "health_score>=72_and_no_decay" if level != "NONE" else "n/a",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        rows.append(state)
        by_strategy[strategy] = state

    return {
        "strategy_throttle_state": rows,
        "by_strategy": by_strategy,
        "throttled_count": throttled_count,
    }
