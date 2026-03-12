import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.risk.tail_risk.exchange_outage_guard import evaluate_exchange_health


def test_exchange_outage_guard_triggers_trade_pause():
    payload = evaluate_exchange_health(
        {
            "api_latency_ms": 1700,
            "ack_delay_ms": 2100,
            "order_reject_rate": 0.3,
            "heartbeat_age_sec": 45,
        }
    )
    assert payload["active"] is True
    assert payload["trade_pause"] is True
    assert payload["event"]["event"] == "EXCHANGE_HEALTH_ALERT"
