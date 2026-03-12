class FuturesExecutionReconciler:
    def reconcile(self, *, submitted: bool, exchange_status: str, executed_qty: float) -> dict:
        status = str(exchange_status or "UNKNOWN").upper()
        qty = float(executed_qty or 0.0)

        if not submitted:
            state = "unknown_needs_reconcile"
        elif status in {"NEW", "ACCEPTED"}:
            state = "accepted"
        elif status in {"PARTIALLY_FILLED"}:
            state = "partially_filled"
        elif status in {"FILLED"}:
            state = "filled"
        elif status in {"CANCELED", "CANCELLED"}:
            state = "cancelled"
        elif status in {"REJECTED", "EXPIRED"}:
            state = "rejected"
        else:
            state = "unknown_needs_reconcile"

        if state == "accepted" and qty > 0:
            state = "partially_filled"

        return {
            "state": state,
            "submitted": submitted,
            "exchange_status": status,
            "executed_qty": round(qty, 8),
        }
