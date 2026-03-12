import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.live.readiness_score_engine import compute_readiness_score


def test_readiness_score_engine_returns_blocked_under_threshold():
    payload = compute_readiness_score(
        position_sync_state="DRIFT",
        order_reconciliation_state="ERROR",
        balance_integrity_state="ALERT",
        exchange_latency_state="ALERT",
    )
    assert payload["readiness_confidence_score"] < 70
    assert payload["readiness_state"] == "BLOCKED"
