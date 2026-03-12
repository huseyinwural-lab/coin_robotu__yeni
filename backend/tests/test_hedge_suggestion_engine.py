import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from services.hedging_suggestion_engine import detect_hedge_opportunity


def test_hedge_suggestion_engine_produces_hedge_when_cluster_concentration_high():
    result = detect_hedge_opportunity(
        portfolio_exposure={
            "total_notional": 100000,
            "cluster_exposure": {
                "L1": 72000,
                "L2": 18000,
            },
        },
        cluster_risk={"L1": 0.72, "L2": 0.18},
        market_correlation={"L1": 0.84, "L2": 0.55},
        volatility=8.5,
    )
    assert result["hedge_symbol"] is not None
    assert result["hedge_size"] > 0
    assert result["hedge_direction"] in {"buy", "sell"}
    assert result["risk_reduction_score"] > 0
