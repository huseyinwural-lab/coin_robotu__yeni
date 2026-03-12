import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.risk.capital.portfolio_capital_registry import build_portfolio_capital_registry


def test_portfolio_capital_registry_builds_deterministic_snapshot():
    payload = build_portfolio_capital_registry(
        portfolio_equity=10000,
        used_margin=1300,
        allocated_capital=4500,
        risk_budget_ratio=0.8,
    )
    assert payload["portfolio_equity"] == 10000
    assert payload["used_margin"] == 1300
    assert payload["allocated_capital"] == 4500
    assert payload["risk_budget_total"] == 8000
    assert payload["available_capital"] == 4200
