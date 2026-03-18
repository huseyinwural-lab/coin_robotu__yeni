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


def test_execution_readiness_mode_field_present_and_valid():
    headers = _admin_headers()
    response = requests.get(f"{BASE_URL}/api/admin/execution-readiness", headers=headers, timeout=30)
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("mode") in {"MOCKED", "LIVE"}
