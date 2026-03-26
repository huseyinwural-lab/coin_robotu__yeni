from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx

from db import SessionLocal
from models import User, UserRole
from services.admin_commercial_service import build_admin_commercial_overview


REQUIRED_OVERVIEW_BLOCKS = [
    "financial_accuracy",
    "revenue_model",
    "user_economics",
    "pnl_analytics",
    "risk_summary",
    "usage_analytics",
    "data_quality",
    "export_ops",
    "alert_rail",
    "operational_controls",
]


def _resolve_internal_smoke_actor(db):
    bootstrap_email = str(os.getenv("ADMIN_BOOTSTRAP_EMAIL") or "").strip().lower()
    if bootstrap_email:
        actor = (
            db.query(User)
            .filter(
                User.email == bootstrap_email,
                User.is_active.is_(True),
                User.status == "active",
            )
            .first()
        )
        if actor is not None:
            return actor

    return (
        db.query(User)
        .filter(
            User.role.in_([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPS]),
            User.is_active.is_(True),
            User.status == "active",
        )
        .first()
    )


def run_commercial_preview_smoke_gate() -> dict:
    db = SessionLocal()
    started_at = datetime.now(timezone.utc)
    try:
        admin_user = _resolve_internal_smoke_actor(db)
        if admin_user is None:
            raise RuntimeError("smoke_admin_missing")

        overview = build_admin_commercial_overview(
            db,
            time_window="last_30_days",
            environment="live",
            from_ts=None,
            to_ts=None,
        )
        missing = [key for key in REQUIRED_OVERVIEW_BLOCKS if key not in overview]
        if missing:
            raise RuntimeError(f"smoke_missing_blocks:{','.join(missing)}")

        return {
            "status": "pass",
            "started_at": started_at.isoformat(),
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "checked_blocks": REQUIRED_OVERVIEW_BLOCKS,
            "missing_blocks": [],
            "checks": {
                "overview_internal": {
                    "status_code": 200,
                    "status": "pass",
                }
            },
        }
    finally:
        db.close()


async def run_commercial_preview_http_gate_once(
    *,
    base_url: str,
    admin_email: str,
    admin_password: str,
    timeout_seconds: float = 75.0,
) -> dict:
    normalized_base_url = str(base_url or "").strip().rstrip("/")
    if not normalized_base_url:
        raise RuntimeError("preview_smoke_base_url_missing")
    if not admin_email or not admin_password:
        raise RuntimeError("preview_smoke_admin_credentials_missing")

    started_at = datetime.now(timezone.utc).isoformat()
    checks: dict[str, dict] = {}

    timeout = httpx.Timeout(connect=10.0, read=timeout_seconds, write=15.0, pool=15.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        health_response = await client.get(f"{normalized_base_url}/api/health")
        checks["api_health"] = {
            "status_code": health_response.status_code,
            "status": "pass" if health_response.status_code == 200 else "fail",
        }
        if health_response.status_code != 200:
            raise RuntimeError(f"preview_smoke_health_failed:{health_response.status_code}")

        login_response = await client.post(
            f"{normalized_base_url}/api/auth/login",
            json={"email": admin_email, "password": admin_password, "panel": "admin"},
        )
        login_json = login_response.json() if login_response.headers.get("content-type", "").startswith("application/json") else {}
        access_token = str(login_json.get("access_token") or "").strip()
        checks["auth_login"] = {
            "status_code": login_response.status_code,
            "status": "pass" if login_response.status_code == 200 and bool(access_token) else "fail",
        }
        if login_response.status_code != 200 or not access_token:
            raise RuntimeError(f"preview_smoke_login_failed:{login_response.status_code}")

        commercial_route = await client.get(f"{normalized_base_url}/admin/commercial-ops")
        checks["commercial_route"] = {
            "status_code": commercial_route.status_code,
            "status": "pass" if commercial_route.status_code == 200 else "fail",
        }
        if commercial_route.status_code != 200:
            raise RuntimeError(f"preview_smoke_commercial_route_failed:{commercial_route.status_code}")

        overview_response = await client.get(
            f"{normalized_base_url}/api/admin/commercial/overview",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        overview_json = (
            overview_response.json()
            if overview_response.headers.get("content-type", "").startswith("application/json")
            else {}
        )
        missing_blocks = [key for key in REQUIRED_OVERVIEW_BLOCKS if key not in overview_json]
        checks["overview_fetch"] = {
            "status_code": overview_response.status_code,
            "status": "pass" if overview_response.status_code == 200 and not missing_blocks else "fail",
            "missing_blocks": missing_blocks,
        }
        if overview_response.status_code != 200 or missing_blocks:
            raise RuntimeError(f"preview_smoke_overview_failed:{overview_response.status_code}")

    return {
        "status": "pass",
        "started_at": started_at,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "missing_blocks": [],
    }
