import os
import uuid
from pathlib import Path

import pytest
import requests


def _resolve_base_url() -> str:
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if direct:
        return direct
    env_file = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    if env_file.exists():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            if raw_line.startswith("REACT_APP_BACKEND_URL="):
                return raw_line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


BASE_URL = _resolve_base_url()
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@platform.local")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin12345!")


@pytest.fixture(scope="module")
def admin_headers() -> dict:
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert response.status_code == 200, response.text
    token = response.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


def _register_user() -> str:
    email = f"venue_auto_{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPass123!"
    response = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_single_approve_auto_creates_venue_assignment(admin_headers: dict):
    user_id = _register_user()

    approve = requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers=admin_headers,
        timeout=20,
    )
    assert approve.status_code == 200, approve.text

    assignments = requests.get(
        f"{BASE_URL}/api/venues/admin/user-assignments",
        params={"user_id": user_id},
        headers=admin_headers,
        timeout=20,
    )
    assert assignments.status_code == 200, assignments.text
    rows = assignments.json()
    assert len(rows) >= 1
    binance_rows = [row for row in rows if row.get("exchange_code") == "binance"]
    assert len(binance_rows) >= 1
    assert bool(binance_rows[0].get("futures_allowed")) is True
    assert bool(binance_rows[0].get("testnet_allowed")) is True


def test_bulk_approve_auto_creates_venue_assignment(admin_headers: dict):
    user_id = _register_user()

    bulk = requests.post(
        f"{BASE_URL}/api/admin/user-approvals/bulk-approve",
        headers=admin_headers,
        json={"ids": [user_id]},
        timeout=20,
    )
    assert bulk.status_code == 200, bulk.text

    assignments = requests.get(
        f"{BASE_URL}/api/venues/admin/user-assignments",
        params={"user_id": user_id},
        headers=admin_headers,
        timeout=20,
    )
    assert assignments.status_code == 200, assignments.text
    rows = assignments.json()
    assert len(rows) >= 1
    assert any(row.get("exchange_code") == "binance" for row in rows)
