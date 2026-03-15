import time

try:
    from db import InMemoryRedis
except ModuleNotFoundError:
    from backend.db import InMemoryRedis


def test_duplicate_suppression_window_resets_after_ttl():
    cache = InMemoryRedis()
    key = "dup:scanner:BTCUSDT"
    event_id = "evt-1"

    first = cache.sadd(key, event_id)
    cache.expire(key, 1)
    second = cache.sadd(key, event_id)

    assert first == 1
    assert second == 0
    assert cache.sismember(key, event_id) is True

    time.sleep(1.1)

    third = cache.sadd(key, event_id)
    assert third == 1
