import os
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
def super_admin_token() -> str:
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code} {response.text}")
    role = (response.json().get("user") or {}).get("role")
    if role != "super_admin":
        pytest.skip(f"super_admin required, got: {role}")
    return response.json().get("access_token")


def test_admin_commercial_usage_logs(super_admin_token: str):
    response = requests.get(
        f"{BASE_URL}/api/admin/commercial/usage-logs",
        headers={"Authorization": f"Bearer {super_admin_token}"},
        timeout=20,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "generated_at" in data
    assert "total" in data
    assert "items" in data


def test_admin_commercial_total_pnl(super_admin_token: str):
    response = requests.get(
        f"{BASE_URL}/api/admin/commercial/total-pnl",
        headers={"Authorization": f"Bearer {super_admin_token}"},
        timeout=20,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "last_30_days" in data
    assert "calendar_month" in data
    assert "summary" in data["last_30_days"]
    assert "summary" in data["calendar_month"]


def test_admin_commercial_monthly_export(super_admin_token: str):
    response = requests.get(
        f"{BASE_URL}/api/admin/commercial/monthly-pnl/export",
        headers={"Authorization": f"Bearer {super_admin_token}"},
        params={"month": "2026-03"},
        timeout=30,
    )
    assert response.status_code == 200, response.text
    content_type = response.headers.get("content-type", "")
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in content_type
    assert len(response.content) > 1000