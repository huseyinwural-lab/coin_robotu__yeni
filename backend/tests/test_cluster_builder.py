# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.risk.correlation.correlation_cluster_builder import build_correlation_clusters


def test_cluster_builder_groups_high_correlation_symbols():
    matrix_payload = {
        "symbols": ["BTC", "ETH", "SOL", "AVAX"],
        "correlation_matrix": {
            "BTC": {"BTC": 1.0, "ETH": 0.82, "SOL": 0.78, "AVAX": 0.74},
            "ETH": {"BTC": 0.82, "ETH": 1.0, "SOL": 0.81, "AVAX": 0.79},
            "SOL": {"BTC": 0.78, "ETH": 0.81, "SOL": 1.0, "AVAX": 0.77},
            "AVAX": {"BTC": 0.74, "ETH": 0.79, "SOL": 0.77, "AVAX": 1.0},
        },
    }
    payload = build_correlation_clusters(matrix_payload, threshold=0.75)
    assert len(payload["correlation_clusters"]) == 1
    cluster = payload["correlation_clusters"][0]
    assert cluster["symbols"] == ["AVAX", "BTC", "ETH", "SOL"]
