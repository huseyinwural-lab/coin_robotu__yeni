import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.strategies.prefilters.crypto_universe_prefilter_v1 import CryptoUniversePrefilterV1


def test_crypto_universe_prefilter_v1_filters_by_liquidity_spread_and_tradability():
    prefilter = CryptoUniversePrefilterV1()
    rows = [
        {
            "symbol": "BTCUSDT",
            "liquidity_usd": 9_000_000,
            "spread_bps": 5,
            "volume_stability": 0.9,
            "volatility": 0.01,
            "futures_tradable": True,
        },
        {
            "symbol": "RISKYUSDT",
            "liquidity_usd": 100_000,
            "spread_bps": 90,
            "volume_stability": 0.1,
            "volatility": 0.2,
            "futures_tradable": False,
        },
    ]

    payload = prefilter.filter_universe(rows)
    assert "BTCUSDT" in payload["selected_symbols"]
    assert "RISKYUSDT" not in payload["selected_symbols"]
    assert any(item["symbol"] == "RISKYUSDT" for item in payload["rejected"])
