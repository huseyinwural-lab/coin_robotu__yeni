from __future__ import annotations

from math import ceil

from fastapi import HTTPException, Request, status

from services.rate_limiter_service import TokenBucketRateLimiter


AUTH_LOGIN_LIMIT_PER_MINUTE = 5
AUTH_LOGIN_WINDOW_SECONDS = 60

_auth_login_rate_limiter = TokenBucketRateLimiter(
    key_prefix="auth_login",
    capacity=AUTH_LOGIN_LIMIT_PER_MINUTE,
    refill_per_second=AUTH_LOGIN_LIMIT_PER_MINUTE / AUTH_LOGIN_WINDOW_SECONDS,
)


def resolve_client_ip(request: Request) -> str:
    forwarded_for = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded_for:
        first = forwarded_for.split(",", 1)[0].strip()
        if first:
            return first
    real_ip = (request.headers.get("x-real-ip") or "").strip()
    if real_ip:
        return real_ip
    if request.client and request.client.host:
        return str(request.client.host).strip()
    return "unknown"


def enforce_login_rate_limit(request: Request, endpoint_scope: str) -> None:
    client_ip = resolve_client_ip(request)
    bucket_id = f"{endpoint_scope}:{client_ip}"
    allowed, retry_after_seconds, _remaining_tokens = _auth_login_rate_limiter.consume(bucket_id=bucket_id, tokens=1.0)
    if allowed:
        return

    retry_after = max(int(ceil(retry_after_seconds)), 1)
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="login_rate_limit_exceeded",
        headers={"Retry-After": str(retry_after)},
    )
