import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.live.position_sync_engine import reconcile_position_state


def test_position_sync_engine_detects_drift():
    payload = reconcile_position_state(
        engine_positions=[{"symbol": "BTCUSDT", "position_size": 1.2, "entry_price": 100, "leverage": 3, "unrealized_pnl": 12}],
        exchange_positions=[{"symbol": "BTCUSDT", "position_size": 1.1, "entry_price": 100, "leverage": 3, "unrealized_pnl": 12}],
    )
    assert payload["position_sync_state"] == "DRIFT"
    assert payload["event"]["event"] == "POSITION_DRIFT_DETECTED"
