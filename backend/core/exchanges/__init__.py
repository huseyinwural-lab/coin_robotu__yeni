import os

from core.exchanges.binance_adapter import BinanceExecutionAdapter
from core.exchanges.sim_adapter import SimExecutionAdapter


def get_execution_adapter():
    execution_mode = str(os.environ.get("EXECUTION_MODE") or "sim").strip().lower()
    live_enabled = str(os.environ.get("LIVE_TRADING_ENABLED") or "false").strip().lower() == "true"
    testnet_enabled = str(os.environ.get("TESTNET_TRADING_ENABLED") or "false").strip().lower() == "true"
    live_route_approved = str(os.environ.get("LIVE_ROUTE_APPROVED") or "false").strip().lower() == "true"
    prod_freeze = str(os.environ.get("VENUE_PROD_FREEZE") or "false").strip().lower() == "true"
    env_lock = str(os.environ.get("VENUE_ENV_LOCK") or "").strip().lower()

    if execution_mode == "live":
        if env_lock in {"testnet", "live"} and env_lock != "live":
            raise RuntimeError("environment_lock_blocked")
        if prod_freeze:
            raise RuntimeError("prod_freeze_active")
        if live_enabled and live_route_approved:
            return BinanceExecutionAdapter(mode="live")
        raise RuntimeError("live_guard_blocked")

    if execution_mode == "testnet":
        if env_lock in {"testnet", "live"} and env_lock != "testnet":
            raise RuntimeError("environment_lock_blocked")
        if testnet_enabled and not live_enabled:
            return BinanceExecutionAdapter(mode="testnet")
        raise RuntimeError("testnet_guard_blocked")

    if execution_mode != "sim":
        raise RuntimeError("invalid_execution_mode")

    return SimExecutionAdapter()
