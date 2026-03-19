# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.strategies.prefilters.relative_strength_cluster_scanner_v2 import RelativeStrengthClusterScannerV2


def test_relative_strength_cluster_scanner_v2_resolves_cluster_or_market_benchmark():
    scanner = RelativeStrengthClusterScannerV2()
    rows = [
        {"symbol": "BTCUSDT", "return_20": 0.03, "liquidity_usd": 20_000_000, "spread_bps": 4, "cluster": "majors"},
        {"symbol": "ETHUSDT", "return_20": 0.05, "liquidity_usd": 15_000_000, "spread_bps": 6, "cluster": "majors"},
        {"symbol": "SOLUSDT", "return_20": 0.07, "liquidity_usd": 12_000_000, "spread_bps": 8, "cluster": "majors"},
    ]

    alias_mode = scanner.scan(rows, benchmark_mode="btc")
    cluster_mode = scanner.scan(rows, benchmark_mode="cluster")
    market_mode = scanner.scan(rows, benchmark_mode="market")

    assert alias_mode["benchmark_mode"] == "cluster"
    assert alias_mode["benchmark_mode_requested"] == "btc"
    assert cluster_mode["benchmark_mode"] == "cluster"
    assert market_mode["benchmark_mode"] == "market"
    assert "SOLUSDT" in alias_mode["selected_symbols"]
