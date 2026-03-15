from services.discovery_scan_service import run_discovery_scan
from services.pipeline.cache_store import set_json


class FakeCache:
    def __init__(self):
        self.store = {}

    def set(self, key, value):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)


def test_discovery_scan_ranks_and_caps_candidates():
    cache = FakeCache()
    set_json(cache, "event:volume_spike:BTCUSDT", {"active": True})
    set_json(cache, "market:spread:BTCUSDT", {"spread_bps": 10})
    set_json(cache, "market:momentum:BTCUSDT", {"zscore": 1.8})
    set_json(cache, "market:volatility:BTCUSDT", {"atr_pct": 1.2})

    set_json(cache, "market:spread:ETHUSDT", {"spread_bps": 22})
    set_json(cache, "market:momentum:ETHUSDT", {"zscore": 0.1})

    payload = run_discovery_scan(
        cache,
        ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPBTC", "测试测试USDT"],
        max_candidates=2,
    )

    assert payload["universe_size"] == 3
    assert len(payload["discovery_candidates"]) == 2
    assert payload["discovery_candidate_symbols"][0] == "BTCUSDT"
    assert "测试测试USDT" not in payload["discovery_candidate_symbols"]
