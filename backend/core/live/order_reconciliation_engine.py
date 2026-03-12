from datetime import datetime, timezone


def reconcile_order_state(engine_orders: list[dict], exchange_orders: list[dict]) -> dict:
    by_exchange_id: dict[str, list[dict]] = {}
    for row in exchange_orders:
        order_id = str(row.get("order_id") or "")
        by_exchange_id.setdefault(order_id, []).append(row)

    issues: list[dict] = []
    corrections: list[dict] = []

    for engine in engine_orders:
        order_id = str(engine.get("order_id") or "")
        matched = by_exchange_id.get(order_id) or []
        if not matched:
            issues.append({"order_id": order_id, "issue": "MISSING_ORDER"})
            continue
        if len(matched) > 1:
            issues.append({"order_id": order_id, "issue": "DUPLICATE_ORDER"})

        exchange = matched[0]
        mismatch_fields: list[str] = []
        for field in ["symbol", "side", "price", "quantity", "status"]:
            if str(engine.get(field)) != str(exchange.get(field)):
                mismatch_fields.append(field)
        if mismatch_fields:
            issues.append({"order_id": order_id, "issue": "EXECUTION_MISMATCH", "fields": mismatch_fields})
            corrections.append({"order_id": order_id, "exchange_snapshot": exchange})

    state = "RECONCILED"
    if not exchange_orders:
        state = "UNVERIFIED"
    elif issues:
        state = "ERROR"

    event = None
    if issues:
        event = {
            "event": "ORDER_RECONCILIATION_ERROR",
            "issue_count": len(issues),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "order_reconciliation_state": state,
        "order_reconciliation_issues": issues,
        "order_state_correction": corrections,
        "event": event,
    }
