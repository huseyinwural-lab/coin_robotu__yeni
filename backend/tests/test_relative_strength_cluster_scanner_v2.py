import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.strategies.prefilters.relative_strength_cluster_scanner_v2 import RelativeStrengthClusterScannerV2


def test_relative_strength_cluster_scanner_v2_uses_btc_or_cluster_benchmark():
    scanner = RelativeStrengthClusterScannerV2()
    rows = [
        {"symbol": "BTCUSDT", "return_20": 0.03, "liquidity_usd": 20_000_000, "spread_bps": 4, "cluster": "majors"},
        {"symbol": "ETHUSDT", "return_20": 0.05, "liquidity_usd": 15_000_000, "spread_bps": 6, "cluster": "majors"},
        {"symbol": "SOLUSDT", "return_20": 0.07, "liquidity_usd": 12_000_000, "spread_bps": 8, "cluster": "majors"},
    ]

    btc_mode = scanner.scan(rows, benchmark_mode="btc")
    cluster_mode = scanner.scan(rows, benchmark_mode="cluster")

    assert btc_mode["benchmark_mode"] == "btc"
    assert cluster_mode["benchmark_mode"] == "cluster"
    assert "SOLUSDT" in btc_mode["selected_symbols"]
