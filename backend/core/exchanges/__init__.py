import os

from core.exchanges.binance_adapter import BinanceExecutionAdapter


def get_execution_adapter():
    execution_mode = str(os.environ.get("EXECUTION_MODE") or "live").strip().lower()
    prod_freeze = str(os.environ.get("VENUE_PROD_FREEZE") or "false").strip().lower() == "true"
    env_lock = str(os.environ.get("VENUE_ENV_LOCK") or "").strip().lower()

    if execution_mode != "live":
        raise RuntimeError("live_only_mode_enforced")
    if env_lock and env_lock != "live":
        raise RuntimeError("environment_lock_blocked")
    if prod_freeze:
        raise RuntimeError("prod_freeze_active")

    return BinanceExecutionAdapter(mode="live")
