import json
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def set_json(cache, key: str, payload: dict):
    cache.set(key, json.dumps(payload))


def get_json(cache, key: str) -> dict | None:
    raw = cache.get(key)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def append_candle(cache, key: str, candle: dict, max_len: int = 400):
    candles = get_json(cache, key) or []
    candles.append(candle)
    cache.set(key, json.dumps(candles[-max_len:]))


def read_candles(cache, key: str) -> list[dict]:
    return get_json(cache, key) or []


def incr_counter(cache, key: str, amount: int = 1) -> int:
    if hasattr(cache, "incr"):
        return int(cache.incr(key, amount))
    current = int(cache.get(key) or 0) + amount
    cache.set(key, str(current))
    return current


def get_counter(cache, key: str) -> int:
    raw = cache.get(key)
    return int(raw) if raw else 0