import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.futures.leverage.portfolio_leverage_guard import PortfolioLeverageGuard


def test_portfolio_guard_reduces_when_portfolio_leverage_high():
    result = PortfolioLeverageGuard().evaluate(portfolio_leverage=2.6, proposed_leverage=4.2)
    assert result["portfolio_adjustment_factor"] == 0.55
    assert result["guarded_leverage_cap"] <= 5.0


def test_portfolio_guard_no_reduction_when_healthy():
    result = PortfolioLeverageGuard().evaluate(portfolio_leverage=1.4, proposed_leverage=3.2)
    assert result["portfolio_adjustment_factor"] == 1.0
