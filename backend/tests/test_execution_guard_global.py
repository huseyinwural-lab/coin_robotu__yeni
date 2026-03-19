# ruff: noqa: E402
import os
import sys
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from server import fastapi_app

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
pytestmark = pytest.mark.skipif(not BASE_URL, reason="REACT_APP_BACKEND_URL is required")


def _admin_headers():
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": "admin@platform.local", "password": "Admin12345!"},
        timeout=30,
    )
    assert response.status_code == 200
    token = response.json().get("access_token")
    assert token
    return {"Authorization": f"Bearer {token}"}


def test_guard_dependency_attached_to_global_trade_endpoints():
    target_paths = {
        "/api/user/open-position",
        "/api/user/execute-order",
        "/api/user/manual-trade",
        "/api/admin/approve-trade",
    }
    found = {}
    for route in fastapi_app.routes:
        path = getattr(route, "path", "")
        if path in target_paths and "POST" in getattr(route, "methods", set()):
            dep_names = {
                getattr(getattr(dep, "call", None), "__name__", "")
                for dep in getattr(route, "dependant", None).dependencies
            }
            found[path] = dep_names

    for path in target_paths:
        assert path in found, f"Route missing: {path}"
        assert any("execution_guard" in name for name in found[path]), f"Guard dependency missing on {path}"


def test_guard_returns_423_for_user_without_readiness():
    headers_admin = _admin_headers()
    email = f"guard-global-{uuid.uuid4().hex[:8]}@example.com"
    password = "GuardGlobal123!"

    register = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password},
        timeout=30,
    )
    assert register.status_code == 200
    user_id = register.json().get("id")

    approve = requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers=headers_admin,
        timeout=30,
    )
    assert approve.status_code == 200

    login = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": email, "password": password},
        timeout=30,
    )
    assert login.status_code == 200
    token = login.json().get("access_token")
    headers_user = {"Authorization": f"Bearer {token}"}

    response = requests.post(
        f"{BASE_URL}/api/user/manual-trade",
        headers=headers_user,
        json={"intent_token": "dummy_token", "preview_hash": "dummy_hash"},
        timeout=30,
    )
    assert response.status_code == 423
    assert response.json().get("detail") == "EXECUTION_BLOCKED_BY_READINESS"
