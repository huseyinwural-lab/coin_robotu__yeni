from __future__ import annotations

from fastapi import Request

from services.geoip_service import resolve_ip_location
from services.identity_control_service import resolve_client_ip, resolve_device_fingerprint


def build_security_audit_context(request: Request) -> dict:
    ip_address = resolve_client_ip(request)
    location = resolve_ip_location(ip_address)
    return {
        "ip_address": ip_address,
        "location": location,
        "device_fingerprint": resolve_device_fingerprint(request),
        "user_agent": str(request.headers.get("user-agent") or "")[:300],
    }
