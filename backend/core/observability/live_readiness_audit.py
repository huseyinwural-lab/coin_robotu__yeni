from datetime import datetime, timezone


def build_live_readiness_audit_events(
    *,
    position_event: dict | None,
    order_event: dict | None,
    balance_event: dict | None,
    latency_event: dict | None,
    readiness_event: dict | None,
    readiness_block_event: dict | None,
) -> list[dict]:
    events: list[dict] = []
    for event in [position_event, order_event, balance_event, latency_event, readiness_event, readiness_block_event]:
        if not event:
            continue
        events.append(
            {
                **event,
                "timestamp": event.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            }
        )
    return events
