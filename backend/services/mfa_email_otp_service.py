from __future__ import annotations

import os
from datetime import datetime, timezone

import resend
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail


def _resolve_sender_email() -> str:
    sender = (
        os.environ.get("MFA_OTP_FROM_EMAIL")
        or os.environ.get("PASSWORD_RESET_FROM_EMAIL")
        or os.environ.get("FROM_EMAIL")
        or ""
    ).strip()
    if not sender:
        raise RuntimeError("MFA_OTP_FROM_EMAIL_missing")
    return sender


def _build_subject() -> str:
    return "Güvenlik Doğrulama Kodu"


def _build_html(code: str, ttl_minutes: int) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return (
        "<div style='font-family:Arial,sans-serif;line-height:1.6'>"
        "<h2 style='margin:0 0 12px'>MFA Doğrulama Kodu</h2>"
        f"<p>Doğrulama kodunuz: <strong style='font-size:18px;letter-spacing:2px'>{code}</strong></p>"
        f"<p>Bu kod {ttl_minutes} dakika geçerlidir.</p>"
        f"<p style='color:#64748b'>Oluşturulma zamanı: {now}</p>"
        "<p>Eğer bu giriş denemesi size ait değilse hesabınızı hemen güvence altına alın.</p>"
        "</div>"
    )


def send_mfa_email_otp(recipient_email: str, *, code: str, ttl_minutes: int) -> dict:
    to_email = str(recipient_email or "").strip()
    if not to_email:
        raise RuntimeError("mfa_otp_recipient_missing")

    sender = _resolve_sender_email()
    subject = _build_subject()
    html = _build_html(code, ttl_minutes)

    resend_key = (os.environ.get("RESEND_API_KEY") or "").strip()
    sendgrid_key = (os.environ.get("SENDGRID_API_KEY") or "").strip()

    if resend_key:
        resend.api_key = resend_key
        response = resend.Emails.send(
            {
                "from": sender,
                "to": [to_email],
                "subject": subject,
                "html": html,
            }
        )
        return {
            "provider": "resend",
            "delivery_id": response.get("id"),
            "recipient": to_email,
            "status": "SENT",
        }

    if sendgrid_key:
        client = SendGridAPIClient(sendgrid_key)
        mail = Mail(
            from_email=sender,
            to_emails=[to_email],
            subject=subject,
            html_content=html,
        )
        response = client.send(mail)
        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code < 200 or status_code >= 300:
            raise RuntimeError(f"sendgrid_status_{status_code}")
        return {
            "provider": "sendgrid",
            "delivery_id": (response.headers or {}).get("X-Message-Id") if hasattr(response, "headers") else None,
            "recipient": to_email,
            "status": "SENT",
        }

    raise RuntimeError("MFA_OTP_PROVIDER_NOT_CONFIGURED")
