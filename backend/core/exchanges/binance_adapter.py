import os

from core.exchanges.base_adapter import BaseExecutionAdapter


class BinanceExecutionAdapter(BaseExecutionAdapter):
    adapter_name = "binance"

    def submit_order(self, payload: dict) -> dict:
        execution_mode = str(os.environ.get("EXECUTION_MODE") or "sim").strip().lower()
        live_enabled = str(os.environ.get("LIVE_TRADING_ENABLED") or "false").strip().lower() == "true"
        testnet_enabled = str(os.environ.get("TESTNET_TRADING_ENABLED") or "false").strip().lower() == "true"

        if execution_mode == "live" and not live_enabled:
            raise RuntimeError("live_guard_blocked")
        if execution_mode == "testnet" and not testnet_enabled:
            raise RuntimeError("testnet_guard_blocked")
        if execution_mode not in {"live", "testnet"}:
            raise RuntimeError("invalid_binance_mode")

        mode_prefix = "LIVE" if execution_mode == "live" else "TESTNET"
        return {
            "external_order_id": f"{mode_prefix}-{str(payload.get('execution_job_id') or '')[:12]}",
            "states": ["SENT", "FILLED"],
            "avg_fill_price": float(payload.get("mark_price") or 1.0),
            "filled_size": float(payload.get("size") or 0.0),
        }
