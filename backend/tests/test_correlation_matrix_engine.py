# ruff: noqa: E402
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.risk.correlation.correlation_matrix_engine import build_correlation_matrix


class FakeCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value

    def expire(self, key, _ttl):
        _ = key
        return True


def _candles(multiplier: float):
    payload = []
    base = 100.0
    for idx in range(130):
        close = base * (1 + (idx / 4000) * multiplier)
        payload.append({"close": close})
    return payload


def test_correlation_matrix_deterministic_with_cache():
    cache = FakeCache()
    cache.set("market:candles:BTCUSDT:15m", json.dumps(_candles(1.0)))
    cache.set("market:candles:ETHUSDT:15m", json.dumps(_candles(1.1)))
    cache.set("market:candles:SOLUSDT:15m", json.dumps(_candles(0.9)))

    first = build_correlation_matrix(cache, ["BTC", "ETH", "SOL"], window=96, cache_ttl_seconds=60)
    second = build_correlation_matrix(cache, ["BTC", "ETH", "SOL"], window=96, cache_ttl_seconds=60)

    assert first == second
    assert first["symbols"] == ["BTC", "ETH", "SOL"]
    assert first["correlation_matrix"]["BTC"]["BTC"] == 1.0
