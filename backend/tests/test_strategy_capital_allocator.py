# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.risk.capital.strategy_capital_allocator import allocate_strategy_capital


def test_strategy_capital_allocator_applies_budget_and_warning_limits():
    payload = allocate_strategy_capital(
        strategy_ids=["trend_follow_v1", "breakout_v1"],
        portfolio_equity=10000,
        capital_usage_by_strategy={"trend_follow_v1": 1700, "breakout_v1": 2300},
        max_strategy_capital_ratio=0.20,
        soft_warning_ratio=0.15,
    )
    rows = {row["strategy_id"]: row for row in payload["strategy_allocation"]}
    assert rows["trend_follow_v1"]["risk_state"] == "WARNING"
    assert rows["breakout_v1"]["risk_state"] == "LIMIT_HIT"
