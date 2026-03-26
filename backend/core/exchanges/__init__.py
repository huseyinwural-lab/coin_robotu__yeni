import os

from core.exchanges.binance_adapter import BinanceExecutionAdapter
from core.exchanges.sim_adapter import SimExecutionAdapter


def get_execution_adapter():
    execution_mode = str(os.environ.get("EXECUTION_MODE") or "sim").strip().lower()
    live_enabled = str(os.environ.get("LIVE_TRADING_ENABLED") or "false").strip().lower() == "true"
    testnet_enabled = str(os.environ.get("TESTNET_TRADING_ENABLED") or "false").strip().lower() == "true"

    if execution_mode == "live" and live_enabled:
        return BinanceExecutionAdapter()
    if execution_mode == "testnet" and testnet_enabled:
        return BinanceExecutionAdapter()
    return SimExecutionAdapter()
