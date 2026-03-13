import json
import time

from db import redis_client


EXCHANGE_GLOBAL_BUCKET = "exchange:global"
EXCHANGE_MAX_REQUESTS_PER_MIN = 1200


class TokenBucketRateLimiter:
    def __init__(self, key_prefix: str, capacity: int, refill_per_second: float):
        self.key_prefix = key_prefix
        self.capacity = max(int(capacity), 1)
        self.refill_per_second = max(float(refill_per_second), 0.0001)

    def _bucket_key(self, bucket_id: str) -> str:
        normalized = str(bucket_id or "default").strip().lower()
        return f"ratelimit:{self.key_prefix}:{normalized}"

    def consume(self, bucket_id: str, tokens: float = 1.0) -> tuple[bool, float, float]:
        requested_tokens = max(float(tokens), 0.0001)
        now = time.time()
        key = self._bucket_key(bucket_id)

        raw = redis_client.get(key)
        tokens_available = float(self.capacity)
        updated_at = now

        if raw:
            try:
                parsed = json.loads(raw)
                tokens_available = float(parsed.get("tokens", self.capacity))
                updated_at = float(parsed.get("updated_at", now))
            except (TypeError, ValueError, json.JSONDecodeError):
                tokens_available = float(self.capacity)
                updated_at = now

        elapsed = max(now - updated_at, 0.0)
        tokens_available = min(float(self.capacity), tokens_available + elapsed * self.refill_per_second)

        if tokens_available < requested_tokens:
            missing_tokens = requested_tokens - tokens_available
            retry_after_seconds = missing_tokens / self.refill_per_second
            redis_client.set(
                key,
                json.dumps(
                    {
                        "tokens": round(tokens_available, 6),
                        "updated_at": now,
                    }
                ),
            )
            redis_client.expire(key, 120)
            return False, round(retry_after_seconds, 3), round(tokens_available, 3)

        remaining = tokens_available - requested_tokens
        redis_client.set(
            key,
            json.dumps(
                {
                    "tokens": round(remaining, 6),
                    "updated_at": now,
                }
            ),
        )
        redis_client.expire(key, 120)
        return True, 0.0, round(remaining, 3)


exchange_rate_limiter = TokenBucketRateLimiter(
    key_prefix=EXCHANGE_GLOBAL_BUCKET,
    capacity=EXCHANGE_MAX_REQUESTS_PER_MIN,
    refill_per_second=EXCHANGE_MAX_REQUESTS_PER_MIN / 60,
)


def consume_exchange_rate_limit(bucket_id: str = "binance", tokens: float = 1.0) -> tuple[bool, float, float]:
    return exchange_rate_limiter.consume(bucket_id=bucket_id, tokens=tokens)
