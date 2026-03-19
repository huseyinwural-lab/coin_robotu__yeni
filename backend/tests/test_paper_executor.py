# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.execution.futures_paper_executor import FuturesPaperExecutor


def test_paper_executor_creates_synthetic_lifecycle():
    executor = FuturesPaperExecutor()
    result = executor.simulate(
        strategy_signal={"side": "LONG", "confidence": 0.8},
        market_state={"latest_price": 100, "spread_bps": 20, "trend_strength": 0.005},
    )
    assert result["paper_position_opened"] is True
    assert result["paper_position_closed"] is True
    assert isinstance(result["paper_pnl"], float)
    assert result["events"][0]["event"] == "paper_position_opened"
    assert result["events"][1]["event"] == "paper_position_closed"


def test_paper_executor_noop_for_none_signal():
    executor = FuturesPaperExecutor()
    result = executor.simulate(
        strategy_signal={"side": "NONE", "confidence": 0.0},
        market_state={"latest_price": 100, "spread_bps": 20, "trend_strength": 0.005},
    )
    assert result["paper_position_opened"] is False
    assert result["paper_pnl"] == 0.0
