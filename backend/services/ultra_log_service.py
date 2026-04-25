from __future__ import annotations

import json
import logging
import os
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from db import SessionLocal
from models import UltraLogConfig, UltraLogEvent

logger = logging.getLogger(__name__)

DURATION_OPTIONS_SECONDS = {
    "1h": 1 * 3600,
    "3h": 3 * 3600,
    "5h": 5 * 3600,
    "8h": 8 * 3600,
    "12h": 12 * 3600,
    "1d": 24 * 3600,
    "3d": 3 * 24 * 3600,
    "5d": 5 * 24 * 3600,
    "7d": 7 * 24 * 3600,
}

SENSITIVE_KEYS = {
    "token",
    "password",
    "secret",
    "api_key",
    "api_secret",
    "authorization",
    "cookie",
    "signature",
    "private_key",
}

DEFAULT_ULTRA_LOG_DIR = "/app/backend/logs/ultra_debug"
DEFAULT_NORMAL_LOG_DIR = "/var/log/supervisor"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_ultra_dir(config: UltraLogConfig | None = None) -> Path:
    if config is not None and (config.ultra_log_dir or "").strip():
        return Path(config.ultra_log_dir.strip())
    env_dir = str(os.environ.get("ULTRA_DEBUG_LOG_DIR") or "").strip()
    if env_dir:
        return Path(env_dir)
    return Path(DEFAULT_ULTRA_LOG_DIR)


def _safe_mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _dir_size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            try:
                total += child.stat().st_size
            except OSError:
                continue
    return round(total / (1024 * 1024), 3)


def _get_or_create_config(db) -> UltraLogConfig:
    row = db.query(UltraLogConfig).filter(UltraLogConfig.id == "global").first()
    if row is None:
        row = UltraLogConfig(id="global")
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _mask_value(key: str, value: Any):
    if any(secret_key in key.lower() for secret_key in SENSITIVE_KEYS):
        return "***MASKED***"

    if isinstance(value, dict):
        return {k: _mask_value(str(k), v) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask_value(key, item) for item in value]
    if isinstance(value, bytes):
        return {"type": "binary", "size_bytes": len(value)}
    if isinstance(value, str) and len(value) > 500:
        return f"{value[:500]}...<truncated:{len(value)}>"
    return value


def _mask_payload(payload: dict | None) -> dict:
    payload = payload or {}
    return {k: _mask_value(str(k), v) for k, v in payload.items()}


def summarize_request_body(body: bytes | None, content_type: str | None) -> dict:
    body = body or b""
    content_type = str(content_type or "")
    size = len(body)

    if size == 0:
        return {"type": "empty", "size_bytes": 0}

    if "multipart/form-data" in content_type:
        return {"type": "multipart", "size_bytes": size}

    if size > 64 * 1024:
        return {"type": "truncated", "size_bytes": size}

    if "application/json" in content_type:
        try:
            parsed = json.loads(body.decode("utf-8", errors="ignore"))
            if isinstance(parsed, dict):
                return {"type": "json", "size_bytes": size, "data": _mask_payload(parsed)}
            if isinstance(parsed, list):
                return {"type": "json_list", "size_bytes": size, "items": len(parsed)}
        except Exception:
            return {"type": "json_invalid", "size_bytes": size}

    preview = body.decode("utf-8", errors="ignore")
    return {"type": "text", "size_bytes": size, "preview": preview[:500]}


def _duration_seconds(duration_option: str) -> int:
    if duration_option not in DURATION_OPTIONS_SECONDS:
        raise ValueError("invalid_duration_option")
    return DURATION_OPTIONS_SECONDS[duration_option]


def _today_log_file(config: UltraLogConfig) -> Path:
    base = _resolve_ultra_dir(config)
    _safe_mkdir(base)
    stamp = _now().strftime("%Y%m%d")
    return base / f"ultra_debug_{stamp}.log"


def _append_file_line(config: UltraLogConfig, payload: dict) -> None:
    target = _today_log_file(config)
    line = json.dumps(payload, ensure_ascii=False)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _prune_ultra_dir_if_needed(config: UltraLogConfig) -> tuple[bool, str]:
    base = _resolve_ultra_dir(config)
    _safe_mkdir(base)
    limit_mb = int(config.max_ultra_log_mb or 512)
    usage = _dir_size_mb(base)
    if usage <= limit_mb:
        return True, ""

    files = sorted([f for f in base.glob("ultra_debug_*.log") if f.is_file()], key=lambda p: p.stat().st_mtime)
    for file_path in files[:-1]:
        try:
            file_path.unlink(missing_ok=True)
        except OSError:
            continue
        usage = _dir_size_mb(base)
        if usage <= limit_mb:
            return True, ""

    latest = files[-1] if files else None
    if latest and latest.exists():
        try:
            data = latest.read_bytes()
            keep = min(len(data), 2 * 1024 * 1024)
            latest.write_bytes(data[-keep:])
        except OSError:
            pass

    usage = _dir_size_mb(base)
    if usage > limit_mb:
        return False, "ultra_size_limit_exceeded"
    return True, ""


def _normal_log_limit_ok(config: UltraLogConfig) -> tuple[bool, str]:
    normal_dir = Path(DEFAULT_NORMAL_LOG_DIR)
    usage = _dir_size_mb(normal_dir)
    if usage <= int(config.max_normal_log_mb or 1024):
        return True, ""
    return False, "normal_size_limit_exceeded"


def _auto_shutdown_if_needed(db, config: UltraLogConfig) -> None:
    if not config.enabled:
        return

    now = _now()
    # Handle timezone-naive datetimes from SQLite
    expires_at = config.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    
    if expires_at and now >= expires_at:
        config.enabled = False
        config.auto_shutdown_reason = "duration_expired"
        config.updated_at = now
        db.commit()
        return

    ultra_ok, ultra_reason = _prune_ultra_dir_if_needed(config)
    if not ultra_ok:
        config.enabled = False
        config.auto_shutdown_reason = ultra_reason
        config.updated_at = now
        db.commit()
        return

    normal_ok, normal_reason = _normal_log_limit_ok(config)
    if not normal_ok:
        config.enabled = False
        config.auto_shutdown_reason = normal_reason
        config.updated_at = now
        db.commit()


def activate_ultra_log(
    db,
    *,
    duration_option: str,
    max_normal_log_mb: int,
    max_ultra_log_mb: int,
    ultra_log_dir: str,
    actor_user_id: str | None,
) -> UltraLogConfig:
    config = _get_or_create_config(db)
    seconds = _duration_seconds(duration_option)
    now = _now()
    config.enabled = True
    config.duration_option = duration_option
    config.started_at = now
    config.expires_at = now + timedelta(seconds=seconds)
    config.max_normal_log_mb = int(max_normal_log_mb)
    config.max_ultra_log_mb = int(max_ultra_log_mb)
    config.ultra_log_dir = (ultra_log_dir or "").strip()
    config.auto_shutdown_reason = ""
    config.updated_by_user_id = actor_user_id
    config.updated_at = now
    db.commit()
    db.refresh(config)
    _safe_mkdir(_resolve_ultra_dir(config))
    return config


def deactivate_ultra_log(db, *, reason: str, actor_user_id: str | None) -> UltraLogConfig:
    config = _get_or_create_config(db)
    config.enabled = False
    config.auto_shutdown_reason = (reason or "manual_deactivated")[:80]
    config.updated_by_user_id = actor_user_id
    config.updated_at = _now()
    db.commit()
    db.refresh(config)
    return config


def ultra_log_status(db) -> dict:
    config = _get_or_create_config(db)
    _auto_shutdown_if_needed(db, config)
    db.refresh(config)

    now = _now()
    remaining_seconds = 0
    if config.enabled and config.expires_at:
        # Handle timezone-naive datetimes from SQLite
        expires_at = config.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        remaining_seconds = max(0, int((expires_at - now).total_seconds()))

    normal_usage = _dir_size_mb(Path(DEFAULT_NORMAL_LOG_DIR))
    ultra_usage = _dir_size_mb(_resolve_ultra_dir(config))
    reason = config.auto_shutdown_reason or ""
    return {
        "enabled": bool(config.enabled),
        "duration_option": config.duration_option,
        "started_at": config.started_at,
        "expires_at": config.expires_at,
        "remaining_seconds": remaining_seconds,
        "max_normal_log_mb": int(config.max_normal_log_mb),
        "max_ultra_log_mb": int(config.max_ultra_log_mb),
        "normal_log_usage_mb": normal_usage,
        "ultra_log_usage_mb": ultra_usage,
        "ultra_log_dir": str(_resolve_ultra_dir(config)),
        "auto_shutdown_reason": reason,
        "auto_close_reason": reason,
    }


def list_ultra_log_events(db, *, limit: int = 200, category: str = ""):
    query = db.query(UltraLogEvent)
    if category:
        query = query.filter(UltraLogEvent.category == category)
    return query.order_by(UltraLogEvent.created_at.desc()).limit(limit).all()


def _persist_ultra_event(db, *, category: str, event_name: str, severity: str, payload: dict) -> None:
    config = _get_or_create_config(db)
    _auto_shutdown_if_needed(db, config)
    if not config.enabled:
        return

    sanitized_payload = _mask_payload(payload)
    row = UltraLogEvent(
        category=category,
        event_name=event_name,
        severity=severity,
        request_id=sanitized_payload.get("request_id"),
        session_id=sanitized_payload.get("session_id"),
        path=sanitized_payload.get("path"),
        method=sanitized_payload.get("method"),
        status_code=sanitized_payload.get("status_code"),
        duration_ms=sanitized_payload.get("duration_ms"),
        client_ip=sanitized_payload.get("client_ip"),
        actor_user_id=sanitized_payload.get("actor_user_id"),
        payload=sanitized_payload,
    )
    db.add(row)
    db.commit()

    file_event = {
        "event_id": row.id,
        "category": category,
        "event_name": event_name,
        "severity": severity,
        "created_at": row.created_at.isoformat() if row.created_at else _now().isoformat(),
        **sanitized_payload,
    }
    _append_file_line(config, file_event)
    _auto_shutdown_if_needed(db, config)


def safe_record_event(*, category: str, event_name: str, severity: str = "info", payload: dict | None = None) -> None:
    payload = payload or {}
    session = SessionLocal()
    try:
        _persist_ultra_event(
            session,
            category=category,
            event_name=event_name,
            severity=severity,
            payload=payload,
        )
    except Exception as exc:
        session.rollback()
        logger.warning("Ultra log event skipped: %s", exc)
    finally:
        session.close()


def classify_audit_category(action: str) -> str:
    normalized = (action or "").lower()
    if "scanner" in normalized or "signal" in normalized:
        return "scanner_signal"
    if "execution" in normalized or "order" in normalized:
        return "execution"
    if "exit" in normalized or "position" in normalized:
        return "position_exit"
    return "audit"
