# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.risk.tail_risk.tail_risk_detector import compute_tail_risk_score


def test_tail_risk_detector_returns_deterministic_score():
    payload = compute_tail_risk_score(
        {
            "volatility_pct": 4.0,
            "liquidation_pressure_input": 0.7,
            "liquidity_depth_score": 0.4,
            "spread_bps": 18,
        }
    )
    assert 0 <= payload["tail_risk_score"] <= 100
    assert "volatility_score" in payload
    assert "liquidation_pressure" in payload
