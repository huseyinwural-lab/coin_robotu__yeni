# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.risk.correlation.cluster_risk_governor import evaluate_cluster_risk


def test_cluster_risk_governor_emits_limit_hit_event():
    payload = evaluate_cluster_risk(
        cluster_exposures=[
            {
                "cluster_id": "CLUSTER_1",
                "symbols": ["BTC", "ETH"],
                "cluster_exposure": 0.41,
                "cluster_position_count": 4,
                "cluster_direction": "LONG",
                "cluster_exposure_notional": 4100,
            }
        ],
        cluster_exposure_limit=0.35,
        cluster_position_limit=3,
        cluster_direction_limit=0.85,
    )
    assert payload["risk_state"] == "ALERT"
    assert payload["cluster_risk_alerts"][0]["event"] == "CLUSTER_RISK_LIMIT_HIT"
