import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.risk.tail_risk.global_risk_score_engine import compute_global_risk_score


def test_global_risk_score_engine_triggers_pause_threshold():
    payload = compute_global_risk_score(
        strategy_health_score=0,
        cluster_risk_state="ALERT",
        capital_drift_state="ALERT",
        tail_risk_score=100,
    )
    assert payload["global_risk_score"] > 90
    assert payload["risk_state"] == "PAUSE"
