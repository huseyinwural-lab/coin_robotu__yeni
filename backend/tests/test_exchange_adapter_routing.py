import os

from core.exchanges import get_execution_adapter
from core.exchanges.binance_adapter import BinanceExecutionAdapter
from core.exchanges.sim_adapter import SimExecutionAdapter


def test_adapter_default_is_sim():
    os.environ["EXECUTION_MODE"] = "sim"
    os.environ["LIVE_TRADING_ENABLED"] = "false"
    os.environ["TESTNET_TRADING_ENABLED"] = "false"
    adapter = get_execution_adapter()
    assert isinstance(adapter, SimExecutionAdapter)


def test_adapter_live_requires_double_guard():
    os.environ["EXECUTION_MODE"] = "live"
    os.environ["LIVE_TRADING_ENABLED"] = "false"
    adapter = get_execution_adapter()
    assert isinstance(adapter, SimExecutionAdapter)

    os.environ["LIVE_TRADING_ENABLED"] = "true"
    adapter = get_execution_adapter()
    assert isinstance(adapter, BinanceExecutionAdapter)
