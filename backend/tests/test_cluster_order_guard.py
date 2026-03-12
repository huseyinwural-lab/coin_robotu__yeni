import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.risk.correlation.cluster_order_guard import evaluate_cluster_order_guard


def test_cluster_order_guard_rejects_trade_when_exposure_limit_exceeded():
    decision = evaluate_cluster_order_guard(
        order={"symbol": "BTCUSDT", "side": "LONG", "position_notional": 900, "position_size_ratio": 0.9},
        clusters=[{"cluster_id": "CLUSTER_1", "symbols": ["BTC", "ETH"]}],
        cluster_exposures=[{"cluster_id": "CLUSTER_1", "cluster_exposure_notional": 3000}],
        portfolio_equity=10000,
        cluster_exposure_limit=0.35,
    )
    assert decision["action"] == "REJECT"
    assert decision["event"]["event"] == "CLUSTER_TRADE_REJECTED"


def test_cluster_order_guard_reduces_size_near_limit():
    decision = evaluate_cluster_order_guard(
        order={"symbol": "ETHUSDT", "side": "LONG", "position_notional": 300, "position_size_ratio": 0.8},
        clusters=[{"cluster_id": "CLUSTER_1", "symbols": ["BTC", "ETH"]}],
        cluster_exposures=[{"cluster_id": "CLUSTER_1", "cluster_exposure_notional": 3200}],
        portfolio_equity=10000,
        cluster_exposure_limit=0.35,
    )
    assert decision["action"] == "REDUCE_SIZE"
    assert decision["adjusted_position_size_ratio"] < 0.8
