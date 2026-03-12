from datetime import datetime, timezone


def validate_balance_integrity(engine_balance: dict, exchange_balance: dict) -> dict:
    if not exchange_balance:
        return {
            "balance_integrity_state": "UNVERIFIED",
            "balance_drift": [],
            "event": None,
        }

    drift: list[dict] = []
    for field in ["wallet_balance", "available_balance", "used_margin"]:
        engine_value = float(engine_balance.get(field) or 0.0)
        exchange_value = float(exchange_balance.get(field) or 0.0)
        if abs(engine_value - exchange_value) > 1e-6:
            drift.append(
                {
                    "field": field,
                    "engine_value": round(engine_value, 4),
                    "exchange_value": round(exchange_value, 4),
                }
            )

    state = "INTACT" if not drift else "ALERT"
    event = None
    if drift:
        event = {
            "event": "BALANCE_INTEGRITY_ALERT",
            "drift_count": len(drift),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "balance_integrity_state": state,
        "balance_drift": drift,
        "event": event,
    }
