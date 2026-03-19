# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.live.live_readiness_guard import evaluate_live_readiness_guard


def test_live_readiness_guard_blocks_when_state_blocked():
    payload = evaluate_live_readiness_guard({"readiness_state": "BLOCKED", "readiness_confidence_score": 62})
    assert payload["action"] == "BLOCK"
    assert payload["event"]["event"] == "LIVE_READINESS_BLOCK"
