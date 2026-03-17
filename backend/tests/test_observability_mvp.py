import os
import uuid
import zipfile
from io import BytesIO
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


def test_health_response_includes_request_id_header():
    request_id = f"health-{uuid.uuid4()}"
    response = requests.get(
        f"{BASE_URL}/api/health",
        headers={"X-Request-ID": request_id},
        timeout=20,
    )
    assert response.status_code == 200, response.text
    assert response.headers.get("X-Request-ID") == request_id


def test_audit_timeline_carries_request_and_session_context(admin_headers: dict):
    request_id = f"obs-{uuid.uuid4()}"
    session_id = f"session-{uuid.uuid4()}"

    action_response = requests.post(
        f"{BASE_URL}/api/admin/users/repair-venue-assignments",
        headers={
            **admin_headers,
            "X-Request-ID": request_id,
            "X-Session-ID": session_id,
        },
        timeout=30,
    )
    assert action_response.status_code == 200, action_response.text

    timeline_response = requests.get(
        f"{BASE_URL}/api/audit-logs/timeline",
        params={"action": "USER_VENUE_ASSIGNMENT_BULK_REPAIRED", "limit": 20},
        headers=admin_headers,
        timeout=20,
    )
    assert timeline_response.status_code == 200, timeline_response.text
    payload = timeline_response.json()
    assert "items" in payload
    assert payload["total"] >= 1

    match = next((item for item in payload["items"] if item.get("request_id") == request_id), None)
    assert match is not None, "request_id not found in timeline records"
    assert match.get("session_id") == session_id
    assert match.get("route") == "/api/admin/users/repair-venue-assignments"
    assert match.get("method") == "POST"


def test_audit_retention_prune_endpoint(admin_headers: dict):
    response = requests.post(
        f"{BASE_URL}/api/audit-logs/admin/retention/prune",
        params={"days": 90},
        headers=admin_headers,
        timeout=30,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("days") == 90
    assert int(payload.get("deleted_count", 0)) >= 0


def test_incident_export_zip_contains_incident_and_summary(admin_headers: dict):
    response = requests.get(
        f"{BASE_URL}/api/audit-logs/admin/incident-export",
        params={"limit": 120},
        headers=admin_headers,
        timeout=40,
    )
    assert response.status_code == 200, response.text
    assert "application/zip" in response.headers.get("content-type", "")

    archive = zipfile.ZipFile(BytesIO(response.content))
    names = set(archive.namelist())
    assert "incident.json" in names
    assert "summary.json" in names


def test_incident_export_requires_auth():
    response = requests.get(
        f"{BASE_URL}/api/audit-logs/admin/incident-export",
        timeout=20,
    )
    assert response.status_code == 401, response.text
