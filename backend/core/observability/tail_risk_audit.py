from datetime import datetime, timezone


def build_tail_risk_audit_events(
    *,
    tail_risk_score: float,
    detector_events: list[dict],
    global_events: list[dict],
    order_events: list[dict],
    affected_symbols: list[str],
) -> list[dict]:
    now_iso = datetime.now(timezone.utc).isoformat()
    output: list[dict] = []

    output.append(
        {
            "event": "TAIL_RISK_ALERT",
            "risk_score": round(float(tail_risk_score or 0.0), 2),
            "trigger_source": [str(item.get("event")) for item in detector_events],
            "affected_symbols": affected_symbols,
            "timestamp": now_iso,
        }
    )

    for event in detector_events:
        output.append(
            {
                "event": event.get("event"),
                "risk_score": round(float(tail_risk_score or 0.0), 2),
                "trigger_source": event.get("reason") or [],
                "affected_symbols": affected_symbols,
                "timestamp": event.get("timestamp") or now_iso,
            }
        )

    for event in global_events:
        output.append(
            {
                "event": event.get("event"),
                "risk_score": round(float(tail_risk_score or 0.0), 2),
                "trigger_source": ["GLOBAL_RISK_SCORE_ENGINE"],
                "affected_symbols": affected_symbols,
                "timestamp": event.get("timestamp") or now_iso,
            }
        )

    for event in order_events:
        output.append(
            {
                "event": "TAIL_RISK_TRADE_REJECTED",
                "risk_score": round(float(tail_risk_score or 0.0), 2),
                "trigger_source": event.get("reason") or [],
                "affected_symbols": affected_symbols,
                "timestamp": event.get("timestamp") or now_iso,
            }
        )

    return output
