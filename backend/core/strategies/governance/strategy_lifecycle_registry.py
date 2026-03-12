from datetime import datetime, timezone


ACTIVE = "ACTIVE"
THROTTLED = "THROTTLED"
DISABLED = "DISABLED"


def _new_state(strategy: str, reason: str = "BOOTSTRAP") -> dict:
    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "strategy": strategy,
        "lifecycle_state": ACTIVE,
        "last_transition_at": now_iso,
        "last_transition_reason": reason,
        "transition_history": [
            {
                "from": None,
                "to": ACTIVE,
                "reason": reason,
                "at": now_iso,
            }
        ],
    }


def apply_lifecycle_transitions(
    *,
    strategy_ids: list[str],
    existing_registry: dict | None,
    throttle_by_strategy: dict,
    disable_by_strategy: dict,
) -> dict:
    existing_registry = existing_registry or {}
    transitions: list[dict] = []
    invalid_transitions: list[dict] = []
    registry: dict[str, dict] = {}

    for strategy in strategy_ids:
        current = (existing_registry.get(strategy) or _new_state(strategy)).copy()
        current_state = str(current.get("lifecycle_state") or ACTIVE)
        next_state = current_state
        reason = "NO_CHANGE"

        disable_state = disable_by_strategy.get(strategy) or {}
        throttle_state = throttle_by_strategy.get(strategy) or {}
        throttle_level = str(throttle_state.get("throttle_level") or "NONE")

        if disable_state.get("should_disable"):
            next_state = DISABLED
            reason = "AUTO_DISABLE_POLICY"
        elif current_state != DISABLED and throttle_level != "NONE":
            next_state = THROTTLED
            reason = f"THROTTLE_{throttle_level}"
        elif current_state != DISABLED and throttle_level == "NONE":
            next_state = ACTIVE
            reason = "HEALTH_RECOVERY"
        elif current_state == DISABLED and throttle_level == "NONE":
            next_state = DISABLED
            reason = "DISABLED_LOCKED_CONTROLLED_RECOVERY"

        now_iso = datetime.now(timezone.utc).isoformat()
        if current_state == DISABLED and next_state in {ACTIVE, THROTTLED}:
            invalid_transitions.append(
                {
                    "strategy": strategy,
                    "from": current_state,
                    "to": next_state,
                    "reason": "DISABLED_STATE_LOCK",
                    "at": now_iso,
                }
            )
            next_state = DISABLED
            reason = "DISABLED_STATE_LOCK"

        if next_state != current_state:
            transitions.append(
                {
                    "strategy": strategy,
                    "from": current_state,
                    "to": next_state,
                    "reason": reason,
                    "at": now_iso,
                }
            )
            history = list(current.get("transition_history") or [])
            history.append({"from": current_state, "to": next_state, "reason": reason, "at": now_iso})
            current["transition_history"] = history[-50:]
            current["last_transition_at"] = now_iso
            current["last_transition_reason"] = reason

        current["strategy"] = strategy
        current["lifecycle_state"] = next_state
        registry[strategy] = current

    return {
        "registry": registry,
        "transitions": transitions,
        "invalid_transitions": invalid_transitions,
    }


def enforce_strategy_lifecycle_on_decisions(
    decisions: list[dict],
    *,
    lifecycle_registry: dict | None,
    throttle_by_strategy: dict | None,
) -> tuple[list[dict], dict]:
    lifecycle_registry = lifecycle_registry or {}
    throttle_by_strategy = throttle_by_strategy or {}

    accepted_by_strategy: dict[str, int] = {}
    disabled_blocked_total = 0
    throttled_modified_total = 0
    throttled_rejected_total = 0
    updated: list[dict] = []

    for decision in decisions:
        row = {**decision}
        strategy = str(row.get("strategy") or row.get("strategy_id") or "unknown")
        lifecycle_state = str((lifecycle_registry.get(strategy) or {}).get("lifecycle_state") or ACTIVE)
        throttle = throttle_by_strategy.get(strategy) or {}
        throttle_level = str(throttle.get("throttle_level") or "NONE")

        row["lifecycle_state"] = lifecycle_state
        row["throttle_level"] = throttle_level

        if row.get("decision") != "ALLOW":
            updated.append(row)
            continue

        if lifecycle_state == DISABLED:
            disabled_blocked_total += 1
            row["decision"] = "REJECT"
            row["reason_code"] = "GATE_REJECT"
            row["decision_layer"] = "GOVERNANCE"
            row["reasons"] = sorted(set((row.get("reasons") or []) + ["STRATEGY_DISABLED_HARD_BLOCK"]))
            updated.append(row)
            continue

        if throttle_level != "NONE":
            throttled_modified_total += 1
            confidence_cap = float(throttle.get("confidence_clamp") or 1.0)
            max_position_ratio = float(throttle.get("max_position_ratio") or 1.0)
            max_signals_per_cycle = int(throttle.get("max_signals_per_cycle") or 8)

            current_confidence = float(row.get("confidence") or 0.0)
            row["confidence"] = round(min(current_confidence, confidence_cap), 4)

            leverage_decision = {**(row.get("leverage_decision") or {})}
            old_size = float(leverage_decision.get("position_size_ratio") or 1.0)
            leverage_decision["position_size_ratio"] = round(min(old_size, max_position_ratio), 4)
            row["leverage_decision"] = leverage_decision

            accepted_count = accepted_by_strategy.get(strategy, 0) + 1
            accepted_by_strategy[strategy] = accepted_count
            if accepted_count > max_signals_per_cycle:
                throttled_rejected_total += 1
                row["decision"] = "REJECT"
                row["reason_code"] = "GATE_REJECT"
                row["decision_layer"] = "GOVERNANCE"
                row["reasons"] = sorted(set((row.get("reasons") or []) + ["STRATEGY_THROTTLE_FREQUENCY"]))

        updated.append(row)

    summary = {
        "disabled_blocked_total": disabled_blocked_total,
        "throttled_modified_total": throttled_modified_total,
        "throttled_rejected_total": throttled_rejected_total,
    }
    return updated, summary
