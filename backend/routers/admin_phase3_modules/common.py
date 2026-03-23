import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from db import redis_client
from models import User
from services.audit_service import create_audit_log

PREVIEW_PREFIX = "admin_phase3:preview"
PREVIEW_TTL_SECONDS = 900


def role_value(user: User) -> str:
    role = getattr(user, "role", None)
    return role.value if hasattr(role, "value") else str(role)


def ensure_super_admin(user: User) -> None:
    if role_value(user) != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin required")


def ensure_reason(reason: str, *, field_name: str = "reason", min_length: int = 3) -> str:
    value = str(reason or "").strip()
    if len(value) < min_length:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name}_must_be_at_least_{min_length}_chars",
        )
    return value


def parse_iso_datetime(raw_value: str | None, *, field_name: str) -> datetime | None:
    if raw_value is None:
        return None
    normalized = str(raw_value).strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{field_name}_invalid_iso") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def resolve_time_window(window: str | None, *, default_hours: int = 24) -> tuple[str, datetime, datetime]:
    mapping = {
        "24h": 24,
        "7d": 24 * 7,
        "30d": 24 * 30,
    }
    normalized = str(window or "24h").strip().lower()
    if normalized not in mapping:
        normalized = "24h"
    hours = mapping[normalized] if normalized in mapping else default_hours
    end_at = datetime.now(timezone.utc)
    start_at = end_at - timedelta(hours=hours)
    return normalized, start_at, end_at


def shape_response(*, status_value: str = "success", message: str | None = None, **payload: object) -> dict:
    response = {
        "status": status_value,
    }
    if message:
        response["message"] = message
    response.update(payload)
    return response


def write_audit_event(
    db: Session,
    *,
    user: User,
    action: str,
    entity_type: str,
    entity_id: str,
    details: dict,
    severity: str = "info",
) -> None:
    create_audit_log(
        db,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=user.id,
        actor_role=role_value(user),
        severity=severity,
        details=details,
    )


def save_preview_payload(payload: dict) -> str:
    token = str(uuid.uuid4())
    key = f"{PREVIEW_PREFIX}:{token}"
    redis_client.set(key, json.dumps(payload, ensure_ascii=False))
    redis_client.expire(key, PREVIEW_TTL_SECONDS)
    return token


def read_preview_payload(token: str) -> dict | None:
    key = f"{PREVIEW_PREFIX}:{token}"
    raw = redis_client.get(key)
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def save_json_config(key: str, payload: dict) -> None:
    redis_client.set(key, json.dumps(payload, ensure_ascii=False))


def read_json_config(key: str, fallback: dict) -> dict:
    raw = redis_client.get(key)
    if not raw:
        return fallback
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else fallback
    except Exception:
        return fallback
