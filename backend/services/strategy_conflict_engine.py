import json
from pathlib import Path

RULES_PATH = Path("/app/config/strategy_conflict_rules.json")

STATE_PRIORITY = {
    "ACTIVE": 3,
    "THROTTLED": 2,
    "DISABLED": 1,
}


def load_conflict_rules() -> dict:
    if not RULES_PATH.exists():
        return {
            "rules": {
                "confidence_priority": True,
                "performance_priority": True,
                "risk_priority": True,
                "meta_override": True,
            },
            "policy_order": ["meta_override", "confidence_priority", "performance_priority", "risk_priority"],
        }
    try:
        payload = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    return {
        "rules": {
            "confidence_priority": True,
            "performance_priority": True,
            "risk_priority": True,
            "meta_override": True,
        },
        "policy_order": ["meta_override", "confidence_priority", "performance_priority", "risk_priority"],
    }


def _metric_bundle(strategy_id: str, confidence_score: float, strategy_stats: dict) -> dict:
    stats = strategy_stats.get(strategy_id, {}) if isinstance(strategy_stats, dict) else {}
    return {
        "strategy_id": strategy_id,
        "confidence": float(confidence_score or 0),
        "performance_score": float(stats.get("performance_score", 0) or 0),
        "signal_decay": float(stats.get("signal_decay", 0) or 0),
        "state": str(stats.get("state", "ACTIVE") or "ACTIVE").upper(),
    }


def _compare_by_rule(rule_name: str, a: dict, b: dict) -> str | None:
    if rule_name == "meta_override":
        a_rank = STATE_PRIORITY.get(a["state"], 0)
        b_rank = STATE_PRIORITY.get(b["state"], 0)
        if a_rank > b_rank:
            return "a"
        if b_rank > a_rank:
            return "b"
        return None

    if rule_name == "confidence_priority":
        if a["confidence"] > b["confidence"]:
            return "a"
        if b["confidence"] > a["confidence"]:
            return "b"
        return None

    if rule_name == "performance_priority":
        if a["performance_score"] > b["performance_score"]:
            return "a"
        if b["performance_score"] > a["performance_score"]:
            return "b"
        return None

    if rule_name == "risk_priority":
        a_risk = a["signal_decay"]
        b_risk = b["signal_decay"]
        if a_risk < b_risk:
            return "a"
        if b_risk < a_risk:
            return "b"
        return None

    return None


def resolve_signal_conflict(
    *,
    focus_signal: dict,
    opposing_signal: dict,
    strategy_stats: dict,
    conflict_rules: dict | None = None,
) -> dict:
    rules = conflict_rules or load_conflict_rules()
    policy_order = rules.get("policy_order") or ["meta_override", "confidence_priority", "performance_priority", "risk_priority"]

    a = _metric_bundle(str(focus_signal.get("strategy_id") or "unknown_strategy"), float(focus_signal.get("confidence_score") or 0), strategy_stats)
    b = _metric_bundle(str(opposing_signal.get("strategy_id") or "unknown_strategy"), float(opposing_signal.get("confidence_score") or 0), strategy_stats)

    winning = a
    losing = b
    resolution_rule = "default_focus_priority"

    for rule_name in policy_order:
        decision = _compare_by_rule(rule_name, a, b)
        if decision == "a":
            winning, losing = a, b
            resolution_rule = rule_name
            break
        if decision == "b":
            winning, losing = b, a
            resolution_rule = rule_name
            break

    return {
        "conflict_detected": True,
        "winning_strategy": winning["strategy_id"],
        "losing_strategy": losing["strategy_id"],
        "resolution_reason": resolution_rule,
        "winning_signal_direction": focus_signal.get("signal_direction")
        if winning["strategy_id"] == focus_signal.get("strategy_id")
        else opposing_signal.get("signal_direction"),
    }


def detect_conflicts_for_signal(
    *,
    active_signals: list[dict],
    strategy_id: str,
    symbol: str,
    signal_direction: str,
    confidence_score: float,
    strategy_stats: dict,
    conflict_rules: dict | None = None,
) -> dict:
    direction = str(signal_direction or "").lower()
    opposite_direction = "sell" if direction in {"buy", "long"} else "buy"
    if direction in {"short"}:
        opposite_direction = "buy"

    opposite_candidates = [
        item
        for item in active_signals
        if str(item.get("symbol") or "").upper() == str(symbol or "").upper()
        and str(item.get("strategy_id") or "") != strategy_id
        and str(item.get("signal_direction") or "").lower() in {opposite_direction, "short" if opposite_direction == "sell" else "long"}
    ]

    if not opposite_candidates:
        return {
            "conflict_detected": False,
            "winning_strategy": strategy_id,
            "losing_strategy": None,
            "resolution_reason": "no_conflict",
            "conflict_count": 0,
        }

    focus_signal = {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "signal_direction": signal_direction,
        "confidence_score": confidence_score,
    }

    resolved_list: list[dict] = []
    for candidate in opposite_candidates:
        resolved = resolve_signal_conflict(
            focus_signal=focus_signal,
            opposing_signal=candidate,
            strategy_stats=strategy_stats,
            conflict_rules=conflict_rules,
        )
        resolved_list.append(resolved)

    focus_wins = sum(1 for item in resolved_list if item["winning_strategy"] == strategy_id)
    if focus_wins >= len(resolved_list) / 2:
        winning_strategy = strategy_id
        losing_strategy = resolved_list[0]["losing_strategy"]
        resolution_reason = f"focus_strategy_wins_{focus_wins}_of_{len(resolved_list)}"
    else:
        winning_strategy = resolved_list[0]["winning_strategy"]
        losing_strategy = strategy_id
        resolution_reason = "opposing_strategy_priority"

    return {
        "conflict_detected": True,
        "winning_strategy": winning_strategy,
        "losing_strategy": losing_strategy,
        "resolution_reason": resolution_reason,
        "conflict_count": len(opposite_candidates),
        "details": resolved_list,
    }
