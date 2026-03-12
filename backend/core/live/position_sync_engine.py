from datetime import datetime, timezone


def reconcile_position_state(engine_positions: list[dict], exchange_positions: list[dict]) -> dict:
    exchange_map = {str(item.get("symbol") or "").upper(): item for item in exchange_positions}
    drifts: list[dict] = []
    corrections: list[dict] = []

    for engine in engine_positions:
        symbol = str(engine.get("symbol") or "").upper()
        exchange = exchange_map.get(symbol)
        if not exchange:
            drifts.append({"symbol": symbol, "reason": "MISSING_ON_EXCHANGE"})
            continue

        checks = {
            "position_size": abs(float(engine.get("position_size") or 0.0) - float(exchange.get("position_size") or 0.0)),
            "entry_price": abs(float(engine.get("entry_price") or 0.0) - float(exchange.get("entry_price") or 0.0)),
            "leverage": abs(float(engine.get("leverage") or 0.0) - float(exchange.get("leverage") or 0.0)),
            "unrealized_pnl": abs(float(engine.get("unrealized_pnl") or 0.0) - float(exchange.get("unrealized_pnl") or 0.0)),
        }
        mismatches = [key for key, delta in checks.items() if delta > 1e-6]
        if mismatches:
            drifts.append({"symbol": symbol, "reason": "FIELD_MISMATCH", "fields": mismatches})
            corrections.append({"symbol": symbol, "exchange_snapshot": exchange})

    state = "SYNCED"
    if not exchange_positions:
        state = "UNVERIFIED"
    elif drifts:
        state = "DRIFT"

    event = None
    if drifts:
        event = {
            "event": "POSITION_DRIFT_DETECTED",
            "drift_count": len(drifts),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "position_sync_state": state,
        "position_drifts": drifts,
        "sync_correction": corrections,
        "event": event,
    }
