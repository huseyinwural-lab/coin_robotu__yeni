import os
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

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


def test_release_gate_contract_reason_codes_and_blocking_metrics():
    headers = _admin_headers()
    response = requests.get(f"{BASE_URL}/api/admin/release-gate", headers=headers, timeout=30)
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("status") in {"PASS", "BLOCKED"}
    assert isinstance(payload.get("reason_codes"), list)
    assert isinstance(payload.get("blocking_metrics"), dict)
    if payload.get("status") == "BLOCKED":
        assert len(payload.get("reason_codes") or []) > 0
