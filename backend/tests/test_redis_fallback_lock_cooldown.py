import time

try:
    from db import InMemoryRedis
except ModuleNotFoundError:
    from backend.db import InMemoryRedis


def test_lock_key_can_be_reacquired_after_expire():
    cache = InMemoryRedis()
    lock_key = "lock:scanner:ETHUSDT"

    cache.set(lock_key, "1")
    assert cache.expire(lock_key, 1) is True
    assert cache.get(lock_key) == "1"

    time.sleep(1.1)
    assert cache.get(lock_key) is None

    cache.set(lock_key, "1")
    assert cache.get(lock_key) == "1"


def test_queue_move_respects_expire_aware_behavior():
    cache = InMemoryRedis()
    source = "queue:pending"
    destination = "queue:processing"

    cache.rpush(source, "job-1")
    assert cache.expire(source, 1) is True
    time.sleep(1.1)

    moved = cache.brpoplpush(source, destination)
    assert moved is None
