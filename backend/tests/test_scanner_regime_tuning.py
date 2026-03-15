from services.pipeline.cache_store import set_json
from services.scanner_regime_service import resolve_scanner_regime


class FakeCache:
    def __init__(self):
        self.store = {}

    def set(self, key, value):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)


def test_regime_profile_normal_uses_expected_caps():
    cache = FakeCache()
    set_json(cache, "market:regime:volatility", {"index": 0.2})
    set_json(cache, "market:regime:spread", {"regime": "normal"})
    set_json(cache, "risk:metrics:execution_quality_trend", {"ema_score": 85, "warning_rate": 0.05})

    payload = resolve_scanner_regime(cache, runtime_metrics={"scan_latency_ms": 1000, "queue_depth": 2}, fallback_active=False)
    assert payload["regime"] == "normal"
    assert payload["caps"] == {"discovery_cap": 700, "qualification_cap": 120, "decision_cap": 25}


def test_regime_profile_stress_on_latency_and_quality_drop():
    cache = FakeCache()
    set_json(cache, "market:regime:volatility", {"index": 0.8})
    set_json(cache, "market:regime:spread", {"regime": "stress"})
    set_json(cache, "risk:metrics:execution_quality_trend", {"ema_score": 50, "warning_rate": 0.45})

    payload = resolve_scanner_regime(cache, runtime_metrics={"scan_latency_ms": 4800, "queue_depth": 60}, fallback_active=True)
    assert payload["regime"] == "stress"
    assert payload["caps"] == {"discovery_cap": 300, "qualification_cap": 40, "decision_cap": 8}
    assert "execution_quality_drop" in payload["reasons"]
