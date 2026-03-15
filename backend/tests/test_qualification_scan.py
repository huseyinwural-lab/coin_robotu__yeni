from services.pipeline.cache_store import set_json
from services.qualification_scan_service import run_qualification_scan


class FakeCache:
    def __init__(self):
        self.store = {}

    def set(self, key, value):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)


def test_qualification_scan_scores_and_limits_candidates():
    cache = FakeCache()
    set_json(cache, "market:trend:BTCUSDT", {"strength": 0.8})
    set_json(cache, "market:breakout:BTCUSDT", {"ready": True})
    set_json(cache, "market:liquidity:BTCUSDT", {"slippage_bps": 12})

    set_json(cache, "market:trend:ETHUSDT", {"strength": 0.2})
    set_json(cache, "market:liquidity:ETHUSDT", {"slippage_bps": 70})

    payload = run_qualification_scan(
        cache,
        [
            {"symbol": "BTCUSDT", "discovery_score": 4.0},
            {"symbol": "ETHUSDT", "discovery_score": 4.0},
        ],
        max_candidates=1,
        snapshot_age_ms=30_000,
        freshness_bucket="normal",
    )

    assert payload["qualified_count"] == 1
    assert payload["qualified_candidate_symbols"] == ["BTCUSDT"]


def test_qualification_scan_filters_stale_candidates():
    cache = FakeCache()

    payload = run_qualification_scan(
        cache,
        [{"symbol": "BTCUSDT", "discovery_score": 2.0}],
        max_candidates=5,
        snapshot_age_ms=400_000,
        freshness_bucket="high",
    )

    assert payload["qualified_count"] == 0
    assert payload["stale_filtered_count"] == 1
