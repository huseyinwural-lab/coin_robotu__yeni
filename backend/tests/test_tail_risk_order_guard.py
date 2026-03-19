# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.risk.tail_risk.tail_risk_order_guard import evaluate_tail_risk_order_guard


def test_tail_risk_order_guard_rejects_when_pause_state():
    payload = evaluate_tail_risk_order_guard(
        strategy_id="trend_follow_v1",
        global_risk_score=94,
        risk_state="PAUSE",
        active_alerts=[{"event": "TRADE_ENGINE_PAUSED"}],
    )
    assert payload["action"] == "REJECT"
    assert payload["event"]["event"] == "TAIL_RISK_TRADE_REJECTED"
