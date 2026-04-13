# ruff: noqa: E402
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.pipeline.cache_store import (
    append_candle,
    get_counter,
    get_json,
    incr_counter,
    read_candles,
    set_json,
    utc_now_iso,
)


class FakeCache:
    """In-memory cache mimicking Redis get/set/incr interface."""

    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value

    def incr(self, key, amount=1):
        current = int(self.store.get(key) or 0) + amount
        self.store[key] = str(current)
        return current


# ---------------------------------------------------------------------------
# utc_now_iso tests
# ---------------------------------------------------------------------------

class TestUtcNowIso:
    def test_returns_iso_format_string(self):
        result = utc_now_iso()
        assert isinstance(result, str)
        assert "T" in result
        # Should be parseable
        from datetime import datetime
        datetime.fromisoformat(result)


# ---------------------------------------------------------------------------
# set_json / get_json tests
# ---------------------------------------------------------------------------

class TestSetGetJson:
    def test_set_and_get_roundtrip(self):
        cache = FakeCache()
        data = {"key": "value", "count": 42}
        set_json(cache, "test:key", data)
        result = get_json(cache, "test:key")
        assert result == data

    def test_get_missing_key_returns_none(self):
        cache = FakeCache()
        result = get_json(cache, "nonexistent")
        assert result is None

    def test_get_corrupt_json_returns_none(self):
        cache = FakeCache()
        cache.set("bad:key", "not valid json {{{")
        result = get_json(cache, "bad:key")
        assert result is None

    def test_overwrite_existing_key(self):
        cache = FakeCache()
        set_json(cache, "k", {"v": 1})
        set_json(cache, "k", {"v": 2})
        assert get_json(cache, "k") == {"v": 2}

    def test_nested_data(self):
        cache = FakeCache()
        data = {"a": {"b": {"c": [1, 2, 3]}}}
        set_json(cache, "nested", data)
        assert get_json(cache, "nested") == data


# ---------------------------------------------------------------------------
# append_candle / read_candles tests
# ---------------------------------------------------------------------------

class TestAppendCandle:
    def test_append_single_candle(self):
        cache = FakeCache()
        append_candle(cache, "candles:BTC", {"open": 100, "close": 101})
        result = read_candles(cache, "candles:BTC")
        assert len(result) == 1
        assert result[0]["open"] == 100

    def test_append_multiple_candles(self):
        cache = FakeCache()
        for i in range(5):
            append_candle(cache, "candles:BTC", {"close": 100 + i})
        result = read_candles(cache, "candles:BTC")
        assert len(result) == 5
        assert result[0]["close"] == 100
        assert result[4]["close"] == 104

    def test_append_respects_max_len(self):
        cache = FakeCache()
        for i in range(10):
            append_candle(cache, "candles:BTC", {"idx": i}, max_len=5)
        result = read_candles(cache, "candles:BTC")
        assert len(result) == 5
        # Should keep the last 5
        assert result[0]["idx"] == 5
        assert result[4]["idx"] == 9

    def test_read_candles_empty(self):
        cache = FakeCache()
        result = read_candles(cache, "nonexistent")
        assert result == []


# ---------------------------------------------------------------------------
# incr_counter / get_counter tests
# ---------------------------------------------------------------------------

class TestCounters:
    def test_incr_from_zero(self):
        cache = FakeCache()
        result = incr_counter(cache, "counter:test")
        assert result == 1

    def test_incr_by_custom_amount(self):
        cache = FakeCache()
        result = incr_counter(cache, "counter:test", 5)
        assert result == 5

    def test_incr_accumulates(self):
        cache = FakeCache()
        incr_counter(cache, "counter:test")
        incr_counter(cache, "counter:test")
        result = incr_counter(cache, "counter:test")
        assert result == 3

    def test_get_counter_default_zero(self):
        cache = FakeCache()
        result = get_counter(cache, "nonexistent")
        assert result == 0

    def test_get_counter_after_increment(self):
        cache = FakeCache()
        incr_counter(cache, "counter:test", 7)
        result = get_counter(cache, "counter:test")
        assert result == 7

    def test_incr_without_redis_incr_method(self):
        """Test fallback path when cache doesn't have incr method."""

        class SimpleFakeCache:
            def __init__(self):
                self.store = {}

            def get(self, key):
                return self.store.get(key)

            def set(self, key, value):
                self.store[key] = value

        cache = SimpleFakeCache()
        result = incr_counter(cache, "counter:test")
        assert result == 1
        result = incr_counter(cache, "counter:test")
        assert result == 2
