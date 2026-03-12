from types import SimpleNamespace
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from services.portfolio_risk_service import DEFAULT_LIMITS, evaluate_portfolio_risk


def test_portfolio_risk_engine_allow_for_small_trade():
    result = evaluate_portfolio_risk(
        execution_intent={"symbol": "BTCUSDT", "notional": 50},
        current_positions=[{"symbol": "BTCUSDT", "notional": 200, "strategy_id": "spot_pullback_v1", "position_size": 0.01}],
        portfolio_state={"current_capital": 10000, "intraday_drawdown_pct": 0.5, "total_drawdown_pct": 1.0},
        strategy_context={"strategy_id": "spot_pullback_v1"},
        market_state={"volatility_pct": 2.1},
        limits=DEFAULT_LIMITS,
        clusters=[SimpleNamespace(cluster_id="L1", symbols=["BTCUSDT", "ETHUSDT"], risk_weight=1.0)],
    )
    assert result["decision"] == "ALLOW"
    assert result["risk_score"] < 0.45
    assert result["approval_required"] is False


def test_portfolio_risk_engine_reject_for_drawdown_breach():
    result = evaluate_portfolio_risk(
        execution_intent={"symbol": "BTCUSDT", "notional": 400},
        current_positions=[{"symbol": "ETHUSDT", "notional": 800, "strategy_id": "trend_v2", "position_size": 0.2}],
        portfolio_state={"current_capital": 10000, "intraday_drawdown_pct": 7.2, "total_drawdown_pct": 18.0},
        strategy_context={"strategy_id": "trend_v2"},
        market_state={"volatility_pct": 4.0},
        limits=DEFAULT_LIMITS,
        clusters=[SimpleNamespace(cluster_id="L1", symbols=["BTCUSDT", "ETHUSDT"], risk_weight=1.0)],
    )
    assert result["decision"] == "REJECT"
    assert "max_intraday_drawdown_breach" in result["risk_flags"]
    assert "max_total_drawdown_breach" in result["risk_flags"]
