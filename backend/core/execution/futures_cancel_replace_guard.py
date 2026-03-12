from core.execution.futures_execution_contract import FuturesExecutionRequest


class FuturesCancelReplaceGuard:
    def block_duplicate_entry(self, request: FuturesExecutionRequest, open_orders: list[dict]) -> dict:
        duplicate = next(
            (
                order
                for order in open_orders
                if str(order.get("decision_trace_id")) == request.decision_trace_id
                and str(order.get("symbol", "")).upper() == request.symbol
                and str(order.get("side", "")).upper() == request.side
                and str(order.get("status", "")).upper() in {"NEW", "PARTIALLY_FILLED"}
            ),
            None,
        )
        if duplicate:
            return {
                "blocked": True,
                "reason_code": "DUPLICATE_EXPOSURE_BLOCKED",
                "existing_order_id": duplicate.get("order_id"),
            }
        return {"blocked": False, "reason_code": "PASS", "existing_order_id": None}

    def reconcile_after_cancel(self, order_state: dict) -> dict:
        state = str(order_state.get("status") or "UNKNOWN").upper()
        if state == "CANCELED":
            return {"can_replace": True, "reason_code": "CANCELLED_RECONCILED"}
        if state == "PARTIALLY_FILLED":
            return {"can_replace": False, "reason_code": "PARTIAL_FILL_REPLACE_BLOCKED"}
        return {"can_replace": False, "reason_code": "ORDER_NOT_CANCELLED"}
