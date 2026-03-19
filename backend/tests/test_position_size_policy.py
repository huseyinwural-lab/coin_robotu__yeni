# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.risk.capital.position_size_policy import apply_position_size_policy


def test_position_size_policy_applies_capital_and_risk_modifiers():
    payload = apply_position_size_policy(
        strategy_capital_available=800,
        strategy_capital_budget=2000,
        base_position_size_ratio=0.9,
        strategy_risk_weight=0.8,
        market_volatility_modifier=0.9,
        cluster_risk_modifier=0.7,
    )
    assert payload["adjusted_position_size_ratio"] < 0.9
    assert payload["capital_factor"] == 0.4
