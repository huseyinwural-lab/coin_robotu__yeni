import hashlib

from core.exchanges.base_adapter import BaseExecutionAdapter


class SimExecutionAdapter(BaseExecutionAdapter):
    adapter_name = "sim"

    def submit_order(self, payload: dict) -> dict:
        idem = str(payload.get("idempotency_key") or payload.get("execution_job_id") or "sim")
        seed = int(hashlib.sha256(idem.encode("utf-8")).hexdigest()[:8], 16)

        states = ["SENT"]
        if seed % 3 == 0:
            states.append("PARTIALLY_FILLED")
        if seed % 7 == 0:
            states.append("FAILED")
        else:
            states.append("FILLED")

        return {
            "external_order_id": f"SIM-{idem[:12]}",
            "states": states,
            "avg_fill_price": float(payload.get("mark_price") or 1.0),
            "filled_size": float(payload.get("size") or 0.0),
        }
