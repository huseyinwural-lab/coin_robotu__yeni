import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.portfolio.strategy_attribution_engine import build_strategy_attribution


def test_strategy_attribution_returns_extended_fields():
    decisions = [
        {"strategy": "trend_follow_v1", "decision": "ALLOW", "confidence": 0.7, "reasons": []},
        {"strategy": "breakout_v1", "decision": "REJECT", "confidence": 0.6, "reasons": ["POLICY_BLOCK"]},
    ]
    paper_trades = [
        {
            "strategy": "trend_follow_v1",
            "paper_pnl": 0.004,
            "expected_slippage_bps": 5.5,
            "execution_latency_ms": 130,
        }
    ]
    payload = build_strategy_attribution(decisions, paper_trades)
    assert "portfolio_pnl_total" in payload
    rows = payload["strategy_attribution"]
    assert len(rows) >= 1
    trend_row = next(row for row in rows if row["strategy"] == "trend_follow_v1")
    assert "win_rate" in trend_row
    assert "avg_expected_slippage_bps" in trend_row
    assert "avg_execution_latency_ms" in trend_row
