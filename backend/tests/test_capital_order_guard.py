import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.risk.capital.capital_order_guard import evaluate_capital_order_guard


def test_capital_order_guard_rejects_when_budget_exceeded():
    payload = evaluate_capital_order_guard(
        strategy_id="breakout_v1",
        projected_order_notional=700,
        strategy_budget_row={"strategy_capital_budget": 2000, "strategy_capital_used": 1500, "warning_threshold": 1500},
        portfolio_registry={"available_capital": 5000},
        cluster_risk_state="NORMAL",
    )
    assert payload["action"] == "REJECT"
    assert payload["event"]["event"] == "CAPITAL_TRADE_REJECTED"


def test_capital_order_guard_reduces_size_on_warning():
    payload = evaluate_capital_order_guard(
        strategy_id="trend_follow_v1",
        projected_order_notional=200,
        strategy_budget_row={"strategy_capital_budget": 2000, "strategy_capital_used": 1400, "warning_threshold": 1500},
        portfolio_registry={"available_capital": 5000},
        cluster_risk_state="ALERT",
    )
    assert payload["action"] == "REDUCE_SIZE"
    assert payload["size_multiplier"] < 1.0
