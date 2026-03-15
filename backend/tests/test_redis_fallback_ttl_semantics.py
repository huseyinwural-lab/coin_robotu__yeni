import time

try:
    from db import InMemoryRedis
except ModuleNotFoundError:
    from backend.db import InMemoryRedis


def test_ttl_expire_eviction_for_string_key():
    cache = InMemoryRedis()
    cache.set("ttl:key", "value")

    assert cache.expire("ttl:key", 1) is True
    assert cache.get("ttl:key") == "value"

    time.sleep(1.1)
    assert cache.get("ttl:key") is None


def test_ttl_expire_eviction_for_set_and_list_keys():
    cache = InMemoryRedis()

    cache.sadd("set:key", "A")
    assert cache.expire("set:key", 1) is True
    assert cache.sismember("set:key", "A") is True

    cache.rpush("list:key", "item-1")
    assert cache.expire("list:key", 1) is True

    time.sleep(1.1)
    assert cache.sismember("set:key", "A") is False
    assert cache.lpop("list:key") is None
