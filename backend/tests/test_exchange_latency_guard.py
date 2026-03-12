import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.live.exchange_latency_guard import evaluate_exchange_latency


def test_exchange_latency_guard_detects_alert_state():
    payload = evaluate_exchange_latency(
        {"order_ack_latency": 1500, "api_response_latency": 1200, "websocket_delay": 1000, "heartbeat_gap": 30}
    )
    assert payload["exchange_latency_state"] == "ALERT"
    assert payload["event"]["event"] == "EXCHANGE_LATENCY_ALERT"
