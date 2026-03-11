from __future__ import annotations

import importlib
import os
from datetime import datetime, timezone
from typing import Any

from db import redis_client

RATE_LIMIT_PER_MIN = 5
CRITICAL_LIMIT_30M = 3
DEDUP_WINDOW_SECONDS = 600


def _parse_recipients(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


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


def _resend_config() -> dict:
    return {
        "api_key": os.environ.get("RESEND_API_KEY"),
        "sender": os.environ.get("ALERT_FROM"),
        "recipients": _parse_recipients(os.environ.get("ALERT_TO")),
    }


def _slack_config() -> dict:
    return {
        "webhook_url": os.environ.get("SLACK_WEBHOOK_URL"),
    }


def channel_status() -> dict:
    resend_cfg = _resend_config()
    slack_cfg = _slack_config()

    email_ready = bool(resend_cfg["api_key"] and resend_cfg["sender"] and resend_cfg["recipients"])
    slack_ready = bool(slack_cfg["webhook_url"])

    return {
        "email": "READY" if email_ready else "CONFIG_MISSING",
        "slack": "READY" if slack_ready else "CONFIG_MISSING",
        "dedup_window_seconds": DEDUP_WINDOW_SECONDS,
        "rate_limit_per_min": RATE_LIMIT_PER_MIN,
        "critical_limit_30m": CRITICAL_LIMIT_30M,
    }


def send_email_alert(subject: str, html_content: str, severity: str) -> dict:
    resend_cfg = _resend_config()
    if not (resend_cfg["api_key"] and resend_cfg["sender"] and resend_cfg["recipients"]):
        return {"status": "CONFIG_MISSING", "reason": "missing_resend_config"}

    allowed, reason = _check_rate_limit("email", severity)
    if not allowed:
        return {"status": "RATE_LIMITED", "reason": reason}

    try:
        resend = importlib.import_module("resend")
    except ModuleNotFoundError:
        return {"status": "LIB_MISSING", "reason": "resend_not_installed"}

    try:
        resend.api_key = resend_cfg["api_key"]
        params = {
            "from": resend_cfg["sender"],
            "to": resend_cfg["recipients"],
            "subject": subject,
            "html": html_content,
        }
        response = resend.Emails.send(params)
        return {"status": "SENT", "provider_id": response.get("id")}
    except Exception as exc:
        return {"status": "FAILED", "reason": str(exc)}


def send_slack_alert(message: str, severity: str) -> dict:
    slack_cfg = _slack_config()
    if not slack_cfg["webhook_url"]:
        return {"status": "CONFIG_MISSING", "reason": "missing_slack_webhook"}

    allowed, reason = _check_rate_limit("slack", severity)
    if not allowed:
        return {"status": "RATE_LIMITED", "reason": reason}

    try:
        requests = importlib.import_module("requests")
    except ModuleNotFoundError:
        return {"status": "LIB_MISSING", "reason": "requests_not_installed"}

    try:
        response = requests.post(slack_cfg["webhook_url"], json={"text": message}, timeout=10)
        if response.status_code >= 400:
            return {"status": "FAILED", "reason": f"slack_http_{response.status_code}"}
        return {"status": "SENT"}
    except Exception as exc:
        return {"status": "FAILED", "reason": str(exc)}


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


def dispatch_alert(alert_payload: dict) -> dict:
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

    if "email" not in channels:
        delivery_status["email"] = {"status": "CHANNEL_DISABLED"}
    else:
        message = build_alert_message(alert_payload)
        delivery_status["email"] = send_email_alert(message["subject"], message["html"], severity)

    if "slack" not in channels:
        delivery_status["slack"] = {"status": "CHANNEL_DISABLED"}
    else:
        message = build_alert_message(alert_payload)
        delivery_status["slack"] = send_slack_alert(message["slack"], severity)

    delivery_status["routing"] = channels
    delivery_status["config"] = channel_status()
    return delivery_status
