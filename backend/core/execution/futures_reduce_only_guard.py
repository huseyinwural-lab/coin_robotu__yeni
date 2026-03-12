from core.execution.futures_execution_contract import FuturesExecutionRequest


class FuturesReduceOnlyGuard:
    def evaluate(self, request: FuturesExecutionRequest, current_position: dict) -> dict:
        if not request.reduce_only:
            return {"pass": True, "reason_code": "PASS", "audit_path": "normal_order_path"}

        qty = float(current_position.get("quantity") or 0.0)
        side = str(current_position.get("side") or "NONE").upper()
        if qty <= 0:
            return {
                "pass": False,
                "reason_code": "REDUCE_ONLY_NO_OPEN_POSITION",
                "audit_path": "reduce_only_reject",
            }

        if side == "LONG" and request.side == "BUY":
            return {
                "pass": False,
                "reason_code": "REDUCE_ONLY_WOULD_INCREASE_LONG",
                "audit_path": "reduce_only_reject",
            }
        if side == "SHORT" and request.side == "SELL":
            return {
                "pass": False,
                "reason_code": "REDUCE_ONLY_WOULD_INCREASE_SHORT",
                "audit_path": "reduce_only_reject",
            }

        return {
            "pass": True,
            "reason_code": "PASS",
            "audit_path": "reduce_only_liquidation_adl_policy_path",
        }
