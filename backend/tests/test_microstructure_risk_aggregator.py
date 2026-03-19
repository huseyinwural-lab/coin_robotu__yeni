# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.futures.microstructure.microstructure_risk_aggregator import MicrostructureRiskAggregator


def test_microstructure_risk_aggregator_blocked_level():
    aggregator = MicrostructureRiskAggregator()
    result = aggregator.aggregate(
        snapshot={"stale_data": False},
        spread_result={"spread_state": "SHOCK"},
        thinning_result={"thinning_state": "CRITICAL"},
        vacuum_result={"vacuum_score": 0.95},
        quote_result={"quote_stability_state": "CHAOTIC"},
        slippage_result={"anomaly_score": 0.9},
        disappearance_result={"liquidity_disappearance_score": 0.8, "affected_side": "LONG"},
    )
    assert result["risk_level"] in {"CRITICAL", "BLOCKED"}
    assert result["side_risk"] == "LONG"


def test_microstructure_risk_aggregator_safe_level():
    aggregator = MicrostructureRiskAggregator()
    result = aggregator.aggregate(
        snapshot={"stale_data": False},
        spread_result={"spread_state": "NORMAL"},
        thinning_result={"thinning_state": "NORMAL"},
        vacuum_result={"vacuum_score": 0.1},
        quote_result={"quote_stability_state": "STABLE"},
        slippage_result={"anomaly_score": 0.1},
        disappearance_result={"liquidity_disappearance_score": 0.1, "affected_side": "NONE"},
    )
    assert result["risk_level"] == "SAFE"
