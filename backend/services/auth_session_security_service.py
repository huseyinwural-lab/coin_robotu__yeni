from __future__ import annotations

import secrets

from fastapi import Request, Response

DEVICE_COOKIE_NAME = "device_id"
DEVICE_HEADER_NAME = "x-session-device"
DEVICE_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 30


def _is_valid_device_id(value: str | None) -> bool:
    normalized = str(value or "").strip()
    if len(normalized) < 24 or len(normalized) > 128:
        return False
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    return all(char in allowed for char in normalized)


def _request_is_secure(request: Request) -> bool:
    forwarded_proto = str(request.headers.get("x-forwarded-proto") or "").strip().lower()
    if forwarded_proto == "https":
        return True
    return bool(request.url.scheme == "https")


def resolve_or_create_device_id(request: Request) -> tuple[str, bool]:
    existing = str(request.cookies.get(DEVICE_COOKIE_NAME) or "").strip()
    if _is_valid_device_id(existing):
        return existing, False
    header_device = str(request.headers.get(DEVICE_HEADER_NAME) or "").strip()
    if _is_valid_device_id(header_device):
        return header_device, False
    return secrets.token_urlsafe(32), True


def set_device_cookie(response: Response, request: Request, *, device_id: str) -> None:
    response.set_cookie(
        key=DEVICE_COOKIE_NAME,
        value=str(device_id or "").strip(),
        max_age=DEVICE_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=_request_is_secure(request),
        samesite="lax",
        path="/",
    )
