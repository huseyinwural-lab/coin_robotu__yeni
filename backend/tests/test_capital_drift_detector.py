# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.risk.capital.capital_drift_detector import detect_capital_drift


def test_capital_drift_detector_detects_budget_and_growth_anomaly():
    allocation = [
        {
            "strategy_id": "mean_reversion_v1",
            "strategy_capital_budget": 2000,
            "strategy_capital_used": 2300,
            "warning_threshold": 1500,
        }
    ]
    payload = detect_capital_drift(allocation, previous_usage={"mean_reversion_v1": 1300})
    assert len(payload["capital_drift_events"]) == 1
    event = payload["capital_drift_events"][0]
    assert event["event"] == "CAPITAL_BUDGET_DRIFT"
    assert "CAPITAL_USAGE_EXCEEDS_BUDGET" in event["reasons"]
