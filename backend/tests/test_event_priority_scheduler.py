from services.event_priority_service import build_event_priority_distribution


class FakeCache:
    def __init__(self):
        self.store = {}

    def set(self, key, value):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)


def test_event_priority_distribution_high_for_spike_and_close():
    cache = FakeCache()
    cache.set("event:candle_close:BTCUSDT", '{"closed": true}')
    cache.set("event:volume_spike:BTCUSDT", '{"active": true}')
    cache.set("market:spread:BTCUSDT", '{"spread_bps": 35}')

    payload = build_event_priority_distribution(cache, ["BTCUSDT"], position_activity=True)

    assert payload["distribution"]["high"] == 1
    assert payload["top_priority_symbols"][0]["symbol"] == "BTCUSDT"
