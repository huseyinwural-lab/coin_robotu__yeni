from __future__ import annotations

import os


def is_temporary_mfa_bypass_user(email: str) -> bool:
    normalized = str(email or "").strip().lower()
    if not normalized:
        return False
    raw = str(os.environ.get("MFA_TEMP_BYPASS_EMAILS") or "canary.admin@platform.local")
    allowlist = {item.strip().lower() for item in raw.split(",") if item.strip()}
    return normalized in allowlist
