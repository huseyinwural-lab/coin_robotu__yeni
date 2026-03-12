import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.risk.tail_risk.liquidation_cascade_guard import detect_liquidation_cascade


def test_liquidation_cascade_guard_emits_alert():
    payload = detect_liquidation_cascade(
        {
            "rapid_price_drop_pct": -4.2,
            "liquidation_volume_spike": 2.5,
            "funding_rate_anomaly": 0.03,
        }
    )
    assert payload["active"] is True
    assert payload["event"]["event"] == "LIQUIDATION_CASCADE_ALERT"
