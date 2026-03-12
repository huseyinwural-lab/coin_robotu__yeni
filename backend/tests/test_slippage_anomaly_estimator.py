import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.futures.microstructure.slippage_anomaly_estimator import SlippageAnomalyEstimator


def test_slippage_anomaly_estimator_anomaly_state():
    estimator = SlippageAnomalyEstimator()
    result = estimator.evaluate(
        {"spread_bps": 40},
        {"spread_bps": 40, "shock_ratio": 3.0},
        {"vacuum_score": 0.9},
    )
    assert result["slippage_state"] == "ANOMALY"
    assert result["anomaly_score"] >= 0.75


def test_slippage_anomaly_estimator_normal_state():
    estimator = SlippageAnomalyEstimator()
    result = estimator.evaluate(
        {"spread_bps": 5},
        {"spread_bps": 5, "shock_ratio": 1.1},
        {"vacuum_score": 0.1},
    )
    assert result["slippage_state"] == "NORMAL"
