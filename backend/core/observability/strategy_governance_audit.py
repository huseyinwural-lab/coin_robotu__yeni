from datetime import datetime, timezone


def build_strategy_governance_audit_events(
    *,
    health_rows: list[dict],
    decay_events: list[dict],
    throttle_rows: list[dict],
    disable_events: list[dict],
    lifecycle_transitions: list[dict],
) -> list[dict]:
    health_map = {str(item.get("strategy")): item for item in health_rows}
    throttle_map = {str(item.get("strategy")): item for item in throttle_rows}

    events: list[dict] = []

    for event in decay_events:
        strategy = str(event.get("strategy") or "unknown")
        events.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": "STRATEGY_DECAY_DETECTED",
                "strategy": strategy,
                "trigger_reason": event.get("decay_reason_codes") or [],
                "health_snapshot": health_map.get(strategy, {}),
                "throttle_state": throttle_map.get(strategy, {}),
                "lifecycle_state": "THROTTLED" if throttle_map.get(strategy, {}).get("throttle_level") != "NONE" else "ACTIVE",
            }
        )

    for event in disable_events:
        strategy = str(event.get("strategy") or "unknown")
        events.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": "STRATEGY_DISABLED",
                "strategy": strategy,
                "trigger_reason": event.get("reasons") or [],
                "health_snapshot": health_map.get(strategy, {}),
                "throttle_state": throttle_map.get(strategy, {}),
                "lifecycle_state": "DISABLED",
            }
        )

    for transition in lifecycle_transitions:
        strategy = str(transition.get("strategy") or "unknown")
        to_state = str(transition.get("to") or "ACTIVE")
        event_name = "STRATEGY_RECOVERED" if to_state == "ACTIVE" else "STRATEGY_THROTTLED"
        events.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": event_name,
                "strategy": strategy,
                "trigger_reason": [transition.get("reason")],
                "health_snapshot": health_map.get(strategy, {}),
                "throttle_state": throttle_map.get(strategy, {}),
                "lifecycle_state": to_state,
            }
        )

    return events
