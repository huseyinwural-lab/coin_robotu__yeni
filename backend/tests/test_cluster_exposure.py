from types import SimpleNamespace
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from services.portfolio_risk_service import DEFAULT_LIMITS, evaluate_portfolio_risk


def test_cluster_exposure_breach_sets_cluster_flag():
    limits = {**DEFAULT_LIMITS, "max_cluster_exposure": 10.0}
    result = evaluate_portfolio_risk(
        execution_intent={"symbol": "BTCUSDT", "notional": 1200},
        current_positions=[
            {"symbol": "ETHUSDT", "notional": 900, "strategy_id": "spot_pullback_v1", "position_size": 0.2},
        ],
        portfolio_state={"current_capital": 10000, "intraday_drawdown_pct": 1.0, "total_drawdown_pct": 1.0},
        strategy_context={"strategy_id": "spot_pullback_v1"},
        market_state={"volatility_pct": 3.2},
        limits=limits,
        clusters=[SimpleNamespace(cluster_id="L1", symbols=["BTCUSDT", "ETHUSDT"], risk_weight=1.0)],
    )
    assert result["cluster_id"] == "L1"
    assert "max_cluster_exposure_breach" in result["risk_flags"]
    assert result["cluster_exposure_pct"] > limits["max_cluster_exposure"]
