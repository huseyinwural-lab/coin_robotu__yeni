from __future__ import annotations

import importlib
import os
import hashlib
import json
import time
from base64 import urlsafe_b64encode
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

from core.config import settings
from db import redis_client
from models import AlertChannelConfig, FailedEvent

from sqlalchemy.orm import Session

RATE_LIMIT_PER_MIN = 5
CRITICAL_LIMIT_30M = 3
DEDUP_WINDOW_SECONDS = 600


def _test_mode_enabled() -> bool:
    return os.environ.get("ALERT_TEST_MODE", "").strip().lower() == "file_sink"


def _alert_test_sink_path() -> Path:
    return Path(
        os.environ.get("ALERT_TEST_SINK_FILE")
        or (Path(__file__).resolve().parents[2] / "artifacts" / "faz5_alert_delivery.log")
    )


def _append_test_sink(channel: str, payload: dict) -> dict:
    sink_path = _alert_test_sink_path()
    sink_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "channel": channel,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    with sink_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"status": "SENT_TEST_SINK", "sink_file": str(sink_path)}


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
    env_sendgrid_key = os.environ.get("SENDGRID_API_KEY") or os.environ.get("RESEND_API_KEY")
    env_sender = os.environ.get("FROM_EMAIL") or os.environ.get("ALERT_FROM")
    env_recipients = _parse_recipients(os.environ.get("TO_EMAIL") or os.environ.get("ALERT_TO"))
    env_telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    env_telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    env_slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL")

    sendgrid_key = env_sendgrid_key
    sender = env_sender
    recipients = env_recipients
    telegram_token = env_telegram_token
    telegram_chat_id = env_telegram_chat_id
    slack_webhook_url = env_slack_webhook_url
    source = "environment"

    row = _get_config_row(db)
    if row:
        row_sendgrid_key = ""
        if getattr(row, "sendgrid_api_key_encrypted", ""):
            row_sendgrid_key = decrypt_secret(row.sendgrid_api_key_encrypted)
        elif row.resend_api_key_encrypted:
            row_sendgrid_key = decrypt_secret(row.resend_api_key_encrypted)

        row_sender = (row.alert_from or "").strip()
        row_recipients = _parse_recipients(row.alert_to)
        row_telegram_token = decrypt_secret(row.telegram_bot_token_encrypted) if getattr(row, "telegram_bot_token_encrypted", "") else ""
        row_telegram_chat_id = (getattr(row, "telegram_chat_id", "") or "").strip()
        row_slack_webhook = decrypt_secret(row.slack_webhook_url_encrypted) if getattr(row, "slack_webhook_url_encrypted", "") else ""

        sendgrid_key = row_sendgrid_key
        sender = row_sender
        recipients = row_recipients
        telegram_token = row_telegram_token
        telegram_chat_id = row_telegram_chat_id
        slack_webhook_url = row_slack_webhook
        source = "admin_config"

    return {
        "sendgrid_api_key": sendgrid_key,
        "sender": sender,
        "recipients": recipients,
        "telegram_bot_token": telegram_token,
        "telegram_chat_id": telegram_chat_id,
        "slack_webhook_url": slack_webhook_url,
        "source": source,
    }


def upsert_alert_channel_config(
    db: Session,
    *,
    sendgrid_api_key: str | None = None,
    resend_api_key: str | None,
    alert_from: str | None,
    alert_to: str | None,
    telegram_bot_token: str | None = None,
    telegram_chat_id: str | None = None,
    slack_webhook_url: str | None,
) -> dict:
    row = _get_config_row(db)
    if row is None:
        row = AlertChannelConfig(id="global")
        db.add(row)

    effective_sendgrid = sendgrid_api_key if sendgrid_api_key is not None else resend_api_key
    if effective_sendgrid is not None:
        encrypted = encrypt_secret(effective_sendgrid.strip())
        row.sendgrid_api_key_encrypted = encrypted
        row.resend_api_key_encrypted = encrypted

    if resend_api_key is not None:
        row.resend_api_key_encrypted = encrypt_secret(resend_api_key.strip())
    if alert_from is not None:
        row.alert_from = alert_from.strip()
    if alert_to is not None:
        normalized = ",".join(_parse_recipients(alert_to))
        row.alert_to = normalized
    if telegram_bot_token is not None:
        row.telegram_bot_token_encrypted = encrypt_secret(telegram_bot_token.strip())
    if telegram_chat_id is not None:
        row.telegram_chat_id = telegram_chat_id.strip()
    if slack_webhook_url is not None:
        row.slack_webhook_url_encrypted = encrypt_secret(slack_webhook_url.strip())

    db.commit()
    db.refresh(row)
    return get_alert_config_public(db)


def get_alert_config_public(db: Session | None = None) -> dict:
    resolved = _resolve_config(db)
    sendgrid_key = resolved["sendgrid_api_key"]
    telegram_token = resolved["telegram_bot_token"]
    telegram_chat_id = resolved["telegram_chat_id"]
    slack_webhook_url = resolved["slack_webhook_url"]
    return {
        "source": resolved["source"],
        "alert_from": resolved["sender"] or "",
        "alert_to": resolved["recipients"],
        "telegram_chat_id": telegram_chat_id,
        "has_sendgrid_api_key": bool(sendgrid_key),
        "has_resend_api_key": bool(sendgrid_key),
        "has_telegram_bot_token": bool(telegram_token),
        "has_telegram_chat_id": bool(telegram_chat_id),
        "has_slack_webhook_url": bool(slack_webhook_url),
        "test_mode": _test_mode_enabled(),
        "masked": {
            "sendgrid_api_key": _mask_secret(sendgrid_key),
            "resend_api_key": _mask_secret(sendgrid_key),
            "telegram_bot_token": _mask_secret(telegram_token),
            "telegram_chat_id": _mask_secret(telegram_chat_id),
            "slack_webhook_url": _mask_secret(slack_webhook_url),
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
        "api_key": resolved["sendgrid_api_key"],
        "sender": resolved["sender"],
        "recipients": resolved["recipients"],
    }


def _slack_config(db: Session | None = None) -> dict:
    resolved = _resolve_config(db)
    return {
        "slack_webhook_url": resolved["slack_webhook_url"],
    }


def _telegram_config(db: Session | None = None) -> dict:
    resolved = _resolve_config(db)
    return {
        "telegram_bot_token": resolved["telegram_bot_token"],
        "telegram_chat_id": resolved["telegram_chat_id"],
    }


def channel_status(db: Session | None = None) -> dict:
    resend_cfg = _resend_config(db)
    slack_cfg = _slack_config(db)
    resolved = _resolve_config(db)
    test_mode = _test_mode_enabled()
    mock_slack = os.environ.get("ALERT_ALLOW_MOCK_SLACK", "true").strip().lower() in {"1", "true", "yes", "mock"}

    email_ready = bool((resend_cfg["api_key"] and resend_cfg["sender"] and resend_cfg["recipients"]) or test_mode)
    telegram_ready = bool((resolved["telegram_bot_token"] and resolved["telegram_chat_id"]) or test_mode)
    slack_ready = bool(slack_cfg["slack_webhook_url"] or test_mode or mock_slack)

    return {
        "email": "READY" if email_ready else "CONFIG_MISSING",
        "telegram": "READY" if telegram_ready else "CONFIG_MISSING",
        "slack": "READY" if slack_ready else "CONFIG_MISSING",
        "channel_status": {
            "email": "ACTIVE" if email_ready else "DISABLED",
            "telegram": "ACTIVE" if telegram_ready else "DISABLED",
            "slack": "ACTIVE" if slack_ready else "DISABLED",
        },
        "channel_status_overall": "READY" if (email_ready or telegram_ready or slack_ready) else "CONFIG_MISSING",
        "secret_status": {
            "sendgrid": "ready" if email_ready else "missing",
            "telegram": "ready" if telegram_ready else "missing",
            "slack": "ready" if slack_ready else "missing",
        },
        "dedup_window_seconds": DEDUP_WINDOW_SECONDS,
        "rate_limit_per_min": RATE_LIMIT_PER_MIN,
        "critical_limit_30m": CRITICAL_LIMIT_30M,
        "config_source": resolved["source"],
        "test_mode": test_mode,
    }


def send_email_alert(subject: str, html_content: str, severity: str, db: Session | None = None) -> dict:
    resend_cfg = _resend_config(db)
    if not (resend_cfg["api_key"] and resend_cfg["sender"] and resend_cfg["recipients"]):
        if _test_mode_enabled():
            return _append_test_sink(
                "email",
                {
                    "subject": subject,
                    "severity": severity,
                    "from": resend_cfg["sender"],
                    "to": resend_cfg["recipients"],
                    "html": html_content,
                },
            )
        return {"status": "CONFIG_MISSING", "reason": "missing_sendgrid_config"}

    allowed, reason = _check_rate_limit("email", severity)
    if not allowed:
        return {"status": "RATE_LIMITED", "reason": reason}

    try:
        sendgrid = importlib.import_module("sendgrid")
        mail_helpers = importlib.import_module("sendgrid.helpers.mail")
    except ModuleNotFoundError:
        return {"status": "LIB_MISSING", "reason": "sendgrid_not_installed"}

    retry_cfg = _retry_config()
    max_attempts = retry_cfg["max_attempts"]
    backoff_seconds = retry_cfg["backoff_seconds"]
    last_error = "unknown"
    for attempt in range(1, max_attempts + 1):
        try:
            client = sendgrid.SendGridAPIClient(resend_cfg["api_key"])
            mail = mail_helpers.Mail(
                from_email=resend_cfg["sender"],
                to_emails=resend_cfg["recipients"],
                subject=subject,
                html_content=html_content,
            )
            response = client.send(mail)
            if int(getattr(response, "status_code", 0)) >= 400:
                last_error = f"sendgrid_http_{getattr(response, 'status_code', 'unknown')}"
                if attempt < max_attempts:
                    time.sleep(backoff_seconds * attempt)
                    continue
                break
            return {"status": "SENT", "provider_id": str(getattr(response, "headers", {}).get("X-Message-Id", "")), "attempt": attempt}
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


def send_telegram_alert(message: str, severity: str, db: Session | None = None) -> dict:
    telegram_cfg = _telegram_config(db)
    token = telegram_cfg["telegram_bot_token"]
    chat_id = telegram_cfg["telegram_chat_id"]
    if not (token and chat_id):
        if _test_mode_enabled():
            return _append_test_sink(
                "telegram",
                {
                    "severity": severity,
                    "chat_id": chat_id,
                    "message": message,
                },
            )
        return {"status": "CONFIG_MISSING", "reason": "missing_telegram_config"}

    allowed, reason = _check_rate_limit("telegram", severity)
    if not allowed:
        return {"status": "RATE_LIMITED", "reason": reason}

    try:
        requests = importlib.import_module("requests")
    except ModuleNotFoundError:
        return {"status": "LIB_MISSING", "reason": "telegram_requests_not_installed"}

    retry_cfg = _retry_config()
    max_attempts = retry_cfg["max_attempts"]
    backoff_seconds = retry_cfg["backoff_seconds"]

    last_error = "unknown"
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": message[:4000]},
                timeout=10,
            )
            if response.status_code >= 400:
                last_error = f"telegram_http_{response.status_code}"
                if attempt < max_attempts:
                    time.sleep(backoff_seconds * attempt)
                    continue
                _record_failed_delivery(
                    db=db,
                    channel="telegram",
                    reason=last_error,
                    payload={"severity": severity, "message": message[:400]},
                    max_retry=max_attempts,
                )
                return {"status": "FAILED", "reason": last_error, "attempts": max_attempts}
            body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            if not body.get("ok", True):
                last_error = f"telegram_api_error:{body}"
                if attempt < max_attempts:
                    time.sleep(backoff_seconds * attempt)
                    continue
                return {"status": "FAILED", "reason": last_error, "attempts": max_attempts}
            return {"status": "SENT", "attempt": attempt}
        except Exception as exc:  # pragma: no cover - runtime retry branch
            last_error = str(exc)
            if attempt < max_attempts:
                time.sleep(backoff_seconds * attempt)

    _record_failed_delivery(
        db=db,
        channel="telegram",
        reason=last_error,
        payload={"severity": severity, "message": message[:400]},
        max_retry=max_attempts,
    )
    return {"status": "FAILED", "reason": last_error, "attempts": max_attempts}


def send_slack_alert(message: str, severity: str, db: Session | None = None, structured_payload: dict | None = None) -> dict:
    slack_cfg = _slack_config(db)
    webhook_url = (slack_cfg.get("slack_webhook_url") or "").strip()
    mock_mode_enabled = os.environ.get("ALERT_ALLOW_MOCK_SLACK", "true").strip().lower() in {"1", "true", "yes", "mock"}
    if (not webhook_url) or webhook_url.startswith("mock://"):
        if _test_mode_enabled() or mock_mode_enabled:
            sink_result = _append_test_sink(
                "slack",
                {
                    "severity": severity,
                    "message": message,
                    "mocked": True,
                    "configured_url": webhook_url,
                    "structured_payload": structured_payload or {},
                },
            )
            sink_result["status"] = "SENT_MOCKED"
            return sink_result
        return {"status": "CONFIG_MISSING", "reason": "missing_slack_webhook_url"}

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

    payload = structured_payload or {"text": message[:3000]}
    if not payload.get("text"):
        payload["text"] = message[:3000]
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.post(webhook_url, json=payload, timeout=10)
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
    details = alert_payload.get("details") or {}
    message = details.get("summary") or alert_payload.get("message") or alert_payload.get("alert_type")
    alert_type = alert_payload.get("alert_type", "system_alert")
    service = details.get("service") or "backend-api"
    environment = details.get("environment") or os.environ.get("APP_ENVIRONMENT", "dev")
    triggered_at = details.get("triggered_at") or datetime.now(timezone.utc).isoformat()
    correlation_id = details.get("correlation_id")

    subject = f"[{severity}] {alert_payload.get('alert_type', 'system_alert')}"
    html_lines = [
        f"<h3>{subject}</h3>",
        f"<p>{message}</p>",
        f"<p><strong>Service:</strong> {service}</p>",
        f"<p><strong>Environment:</strong> {environment}</p>",
        f"<p><strong>Triggered At:</strong> {triggered_at}</p>",
        f"<p><strong>Alert Type:</strong> {alert_type}</p>",
        f"<p><strong>Correlation ID:</strong> {correlation_id or '-'}</p>",
        f"<pre>{details}</pre>",
    ]
    html_content = "\n".join(html_lines)
    telegram_message = (
        f"{subject}\n"
        f"Service: {service}\n"
        f"Env: {environment}\n"
        f"At: {triggered_at}\n"
        f"Summary: {message}\n"
        f"Correlation: {correlation_id or '-'}"
    )
    webhook_payload = details.get("webhook_payload") or {}
    slack_payload = {
        "text": f"{subject} - {message}",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{subject}*\n{message}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Service*\n{service}"},
                    {"type": "mrkdwn", "text": f"*Env*\n{environment}"},
                    {"type": "mrkdwn", "text": f"*Correlation*\n{correlation_id or '-'}"},
                    {"type": "mrkdwn", "text": f"*Triggered At*\n{triggered_at}"},
                ],
            },
        ],
    }
    if webhook_payload:
        slack_payload["attachments"] = [
            {
                "color": "#dc2626" if severity.upper() == "CRITICAL" else "#f59e0b",
                "title": "Execution Alert Payload",
                "text": json.dumps(webhook_payload, ensure_ascii=False),
            }
        ]
    return {"subject": subject, "html": html_content, "telegram": telegram_message, "slack": slack_payload}


def dispatch_alert(alert_payload: dict, db: Session | None = None) -> dict:
    severity = alert_payload.get("severity", "INFO")
    alert_type = alert_payload.get("alert_type", "")
    routing = {
        "INFO": [],
        "WARNING": ["slack"],
        "CRITICAL": ["slack", "email"],
    }
    channels = routing.get(severity.upper(), [])
    forced_channels = alert_payload.get("force_channels")
    if isinstance(forced_channels, list) and forced_channels:
        channels = [str(item).lower() for item in forced_channels]
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

    if "telegram" not in channels:
        delivery_status["telegram"] = {"status": "CHANNEL_DISABLED"}
    elif readiness["telegram"] != "READY":
        delivery_status["telegram"] = {"status": "CHANNEL_DISABLED", "reason": "config_missing"}
    else:
        message = build_alert_message(alert_payload)
        delivery_status["telegram"] = send_telegram_alert(message["telegram"], severity, db)

    if "slack" not in channels:
        delivery_status["slack"] = {"status": "CHANNEL_DISABLED"}
    elif readiness["slack"] != "READY":
        delivery_status["slack"] = {"status": "CHANNEL_DISABLED", "reason": "config_missing"}
    else:
        message = build_alert_message(alert_payload)
        delivery_status["slack"] = send_slack_alert(
            message=message["subject"],
            severity=severity,
            db=db,
            structured_payload=message["slack"],
        )

    delivery_status["routing"] = channels
    delivery_status["config"] = channel_status(db)
    return delivery_status
