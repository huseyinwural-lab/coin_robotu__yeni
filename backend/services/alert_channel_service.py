from __future__ import annotations

import importlib
import os
import hashlib
import time
from base64 import urlsafe_b64encode
from datetime import datetime, timezone
from typing import Any

from cryptography.fernet import Fernet

from core.config import settings
from db import redis_client
from models import AlertChannelConfig, FailedEvent

from sqlalchemy.orm import Session

RATE_LIMIT_PER_MIN = 5
CRITICAL_LIMIT_30M = 3
DEDUP_WINDOW_SECONDS = 600


def _retry_config() -> dict:
    max_attempts = max(int(os.environ.get("ALERT_DELIVERY_MAX_RETRY", "2")), 1)
    backoff_seconds = max(float(os.environ.get("ALERT_DELIVERY_BACKOFF_SECONDS", "0.8")), 0.1)
    return {"max_attempts": max_attempts, "backoff_seconds": backoff_seconds}


def _record_failed_delivery(
    *,
    db: Session | None,
    channel: str,
    reason: str,
    payload: dict,
    max_retry: int,
) -> None:
    if db is None:
        return
    failed_event = FailedEvent(
        event_type=f"alert_delivery_{channel}",
        entity_type="system_alert_delivery",
        entity_id=payload.get("alert_type") or "manual_delivery",
        payload=payload,
        error_message=str(reason)[:1000],
        status="pending",
        retry_count=0,
        max_retry=max_retry,
        next_retry_at=datetime.now(timezone.utc),
    )
    db.add(failed_event)
    db.commit()


def _parse_recipients(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _mask_secret(raw: str | None) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _build_crypto() -> Fernet:
    digest = hashlib.sha256(settings.jwt_secret.encode()).digest()
    return Fernet(urlsafe_b64encode(digest))


def encrypt_secret(raw: str) -> str:
    if not raw:
        return ""
    return _build_crypto().encrypt(raw.encode()).decode()


def decrypt_secret(raw_encrypted: str) -> str:
    if not raw_encrypted:
        return ""
    return _build_crypto().decrypt(raw_encrypted.encode()).decode()


def _get_config_row(db: Session | None) -> AlertChannelConfig | None:
    if db is None:
        return None
    return db.query(AlertChannelConfig).filter(AlertChannelConfig.id == "global").first()


def _resolve_config(db: Session | None = None) -> dict:
    env_api_key = os.environ.get("RESEND_API_KEY")
    env_sender = os.environ.get("ALERT_FROM")
    env_recipients = _parse_recipients(os.environ.get("ALERT_TO"))
    env_webhook = os.environ.get("SLACK_WEBHOOK_URL")

    api_key = env_api_key
    sender = env_sender
    recipients = env_recipients
    webhook_url = env_webhook
    source = "environment"

    row = _get_config_row(db)
    if row:
        row_api_key = decrypt_secret(row.resend_api_key_encrypted) if row.resend_api_key_encrypted else ""
        row_sender = (row.alert_from or "").strip()
        row_recipients = _parse_recipients(row.alert_to)
        row_webhook = decrypt_secret(row.slack_webhook_url_encrypted) if row.slack_webhook_url_encrypted else ""

        api_key = row_api_key
        sender = row_sender
        recipients = row_recipients
        webhook_url = row_webhook
        source = "admin_config"

    return {
        "api_key": api_key,
        "sender": sender,
        "recipients": recipients,
        "webhook_url": webhook_url,
        "source": source,
    }


def upsert_alert_channel_config(
    db: Session,
    *,
    resend_api_key: str | None,
    alert_from: str | None,
    alert_to: str | None,
    slack_webhook_url: str | None,
) -> dict:
    row = _get_config_row(db)
    if row is None:
        row = AlertChannelConfig(id="global")
        db.add(row)

    if resend_api_key is not None:
        row.resend_api_key_encrypted = encrypt_secret(resend_api_key.strip())
    if alert_from is not None:
        row.alert_from = alert_from.strip()
    if alert_to is not None:
        normalized = ",".join(_parse_recipients(alert_to))
        row.alert_to = normalized
    if slack_webhook_url is not None:
        row.slack_webhook_url_encrypted = encrypt_secret(slack_webhook_url.strip())

    db.commit()
    db.refresh(row)
    return get_alert_config_public(db)


def get_alert_config_public(db: Session | None = None) -> dict:
    resolved = _resolve_config(db)
    return {
        "source": resolved["source"],
        "alert_from": resolved["sender"] or "",
        "alert_to": resolved["recipients"],
        "has_resend_api_key": bool(resolved["api_key"]),
        "has_slack_webhook_url": bool(resolved["webhook_url"]),
        "masked": {
            "resend_api_key": _mask_secret(resolved["api_key"]),
            "slack_webhook_url": _mask_secret(resolved["webhook_url"]),
        },
    }


def _rate_limit_key(channel: str, window: str) -> str:
    return f"alerts:rate:{channel}:{window}"


def _check_rate_limit(channel: str, severity: str) -> tuple[bool, str | None]:
    now = datetime.now(timezone.utc)
    minute_window = now.strftime("%Y%m%d%H%M")
    minute_key = _rate_limit_key(channel, minute_window)
    count = redis_client.incr(minute_key)
    redis_client.expire(minute_key, 70)
    if count > RATE_LIMIT_PER_MIN:
        return False, "rate_limit_per_min"

    if severity.upper() == "CRITICAL":
        critical_window = now.strftime("%Y%m%d%H") + f"-{now.minute // 30}"
        critical_key = _rate_limit_key(f"{channel}:critical", critical_window)
        critical_count = redis_client.incr(critical_key)
        redis_client.expire(critical_key, 1900)
        if critical_count > CRITICAL_LIMIT_30M:
            return False, "critical_rate_limit"

    return True, None


def _resend_config(db: Session | None = None) -> dict:
    resolved = _resolve_config(db)
    return {
        "api_key": resolved["api_key"],
        "sender": resolved["sender"],
        "recipients": resolved["recipients"],
    }


def _slack_config(db: Session | None = None) -> dict:
    resolved = _resolve_config(db)
    return {
        "webhook_url": resolved["webhook_url"],
    }


def channel_status(db: Session | None = None) -> dict:
    resend_cfg = _resend_config(db)
    slack_cfg = _slack_config(db)
    resolved = _resolve_config(db)

    email_ready = bool(resend_cfg["api_key"] and resend_cfg["sender"] and resend_cfg["recipients"])
    slack_ready = bool(slack_cfg["webhook_url"])

    return {
        "email": "READY" if email_ready else "CONFIG_MISSING",
        "slack": "READY" if slack_ready else "CONFIG_MISSING",
        "channel_status": {
            "email": "ACTIVE" if email_ready else "DISABLED",
            "slack": "ACTIVE" if slack_ready else "DISABLED",
        },
        "channel_status_overall": "READY" if (email_ready or slack_ready) else "CONFIG_MISSING",
        "secret_status": {
            "resend": "ready" if email_ready else "missing",
            "slack": "ready" if slack_ready else "missing",
        },
        "dedup_window_seconds": DEDUP_WINDOW_SECONDS,
        "rate_limit_per_min": RATE_LIMIT_PER_MIN,
        "critical_limit_30m": CRITICAL_LIMIT_30M,
        "config_source": resolved["source"],
    }


def send_email_alert(subject: str, html_content: str, severity: str, db: Session | None = None) -> dict:
    resend_cfg = _resend_config(db)
    if not (resend_cfg["api_key"] and resend_cfg["sender"] and resend_cfg["recipients"]):
        return {"status": "CONFIG_MISSING", "reason": "missing_resend_config"}

    allowed, reason = _check_rate_limit("email", severity)
    if not allowed:
        return {"status": "RATE_LIMITED", "reason": reason}

    try:
        resend = importlib.import_module("resend")
    except ModuleNotFoundError:
        return {"status": "LIB_MISSING", "reason": "resend_not_installed"}

    retry_cfg = _retry_config()
    max_attempts = retry_cfg["max_attempts"]
    backoff_seconds = retry_cfg["backoff_seconds"]
    params = {
        "from": resend_cfg["sender"],
        "to": resend_cfg["recipients"],
        "subject": subject,
        "html": html_content,
    }
    resend.api_key = resend_cfg["api_key"]

    last_error = "unknown"
    for attempt in range(1, max_attempts + 1):
        try:
            response = resend.Emails.send(params)
            return {"status": "SENT", "provider_id": response.get("id"), "attempt": attempt}
        except Exception as exc:  # pragma: no cover - runtime retry branch
            last_error = str(exc)
            if attempt < max_attempts:
                time.sleep(backoff_seconds * attempt)

    _record_failed_delivery(
        db=db,
        channel="email",
        reason=last_error,
        payload={"subject": subject, "severity": severity, "recipients": resend_cfg["recipients"]},
        max_retry=max_attempts,
    )
    return {"status": "FAILED", "reason": last_error, "attempts": max_attempts}


def send_slack_alert(message: str, severity: str, db: Session | None = None) -> dict:
    slack_cfg = _slack_config(db)
    if not slack_cfg["webhook_url"]:
        return {"status": "CONFIG_MISSING", "reason": "missing_slack_webhook"}

    allowed, reason = _check_rate_limit("slack", severity)
    if not allowed:
        return {"status": "RATE_LIMITED", "reason": reason}

    try:
        requests = importlib.import_module("requests")
    except ModuleNotFoundError:
        return {"status": "LIB_MISSING", "reason": "requests_not_installed"}

    retry_cfg = _retry_config()
    max_attempts = retry_cfg["max_attempts"]
    backoff_seconds = retry_cfg["backoff_seconds"]

    last_error = "unknown"
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.post(slack_cfg["webhook_url"], json={"text": message}, timeout=10)
            if response.status_code >= 400:
                last_error = f"slack_http_{response.status_code}"
                if attempt < max_attempts:
                    time.sleep(backoff_seconds * attempt)
                    continue
                _record_failed_delivery(
                    db=db,
                    channel="slack",
                    reason=last_error,
                    payload={"severity": severity, "message": message[:400]},
                    max_retry=max_attempts,
                )
                return {"status": "FAILED", "reason": last_error, "attempts": max_attempts}
            return {"status": "SENT", "attempt": attempt}
        except Exception as exc:  # pragma: no cover - runtime retry branch
            last_error = str(exc)
            if attempt < max_attempts:
                time.sleep(backoff_seconds * attempt)

    _record_failed_delivery(
        db=db,
        channel="slack",
        reason=last_error,
        payload={"severity": severity, "message": message[:400]},
        max_retry=max_attempts,
    )
    return {"status": "FAILED", "reason": last_error, "attempts": max_attempts}


def build_alert_message(alert_payload: dict) -> dict:
    severity = alert_payload.get("severity", "INFO")
    message = alert_payload.get("message") or alert_payload.get("alert_type")
    details = alert_payload.get("details") or {}
    subject = f"[{severity}] {alert_payload.get('alert_type', 'system_alert')}"
    html_lines = [
        f"<h3>{subject}</h3>",
        f"<p>{message}</p>",
        f"<pre>{details}</pre>",
    ]
    html_content = "\n".join(html_lines)
    slack_message = f"*{subject}*\n{message}\n```{details}```"
    return {"subject": subject, "html": html_content, "slack": slack_message}


def dispatch_alert(alert_payload: dict, db: Session | None = None) -> dict:
    severity = alert_payload.get("severity", "INFO")
    alert_type = alert_payload.get("alert_type", "")
    routing = {
        "INFO": [],
        "WARNING": ["email"],
        "CRITICAL": ["email", "slack"],
    }
    channels = routing.get(severity.upper(), [])
    if alert_type == "weekly_ops_report_generated":
        channels = ["email"]
    delivery_status: dict[str, Any] = {}
    readiness = channel_status(db)

    if "email" not in channels:
        delivery_status["email"] = {"status": "CHANNEL_DISABLED"}
    elif readiness["email"] != "READY":
        delivery_status["email"] = {"status": "CHANNEL_DISABLED", "reason": "config_missing"}
    else:
        message = build_alert_message(alert_payload)
        delivery_status["email"] = send_email_alert(message["subject"], message["html"], severity, db)

    if "slack" not in channels:
        delivery_status["slack"] = {"status": "CHANNEL_DISABLED"}
    elif readiness["slack"] != "READY":
        delivery_status["slack"] = {"status": "CHANNEL_DISABLED", "reason": "config_missing"}
    else:
        message = build_alert_message(alert_payload)
        delivery_status["slack"] = send_slack_alert(message["slack"], severity, db)

    delivery_status["routing"] = channels
    delivery_status["config"] = channel_status(db)
    return delivery_status
