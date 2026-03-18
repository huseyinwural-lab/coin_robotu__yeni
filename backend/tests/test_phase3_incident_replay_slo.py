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


def test_incident_replay_for_request_id(admin_headers: dict):
    request_id = f"phase3-{uuid.uuid4()}"
    session_id = f"phase3-session-{uuid.uuid4()}"

    trigger = requests.post(
        f"{BASE_URL}/api/admin/users/repair-venue-assignments",
        headers={**admin_headers, "X-Request-ID": request_id, "X-Session-ID": session_id},
        timeout=30,
    )
    assert trigger.status_code == 200, trigger.text

    replay = requests.get(
        f"{BASE_URL}/api/audit-logs/incident-replay",
        params={"request_id": request_id, "limit": 400},
        headers=admin_headers,
        timeout=30,
    )
    assert replay.status_code == 200, replay.text
    payload = replay.json()
    assert payload.get("summary", {}).get("step_count", 0) >= 1
    assert isinstance(payload.get("steps"), list)
    first = payload.get("steps", [])[0]
    assert "root_cause_type" in first
    assert "failure_stage" in first
    assert "primary_error_code" in first
    assert "confidence_score" in first
    assert "priority_level" in first
    assert "primary_cause" in first
    assert "root_cause_breakdown" in payload.get("summary", {})


def test_slo_sla_endpoint(admin_headers: dict):
    response = requests.get(
        f"{BASE_URL}/api/admin/system-alerts/slo-sla",
        params={"days": 14},
        headers=admin_headers,
        timeout=20,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("window_days") == 14
    metrics = payload.get("metrics") or {}
    assert "availability_pct" in metrics
    assert "mttr_minutes" in metrics


def test_slo_sla_trend_endpoint(admin_headers: dict):
    response = requests.get(
        f"{BASE_URL}/api/admin/system-alerts/slo-sla-trend",
        headers=admin_headers,
        timeout=20,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    points = payload.get("points") or []
    assert len(points) == 3
    window_set = {point.get("window_days") for point in points}
    assert window_set == {7, 30, 90}
    assert "anomaly_detection" in payload
    assert "signal" in (payload.get("anomaly_detection") or {})


def test_ops_alert_simulate_endpoint(admin_headers: dict):
    response = requests.post(
        f"{BASE_URL}/api/ops-alerts/simulate",
        headers=admin_headers,
        timeout=20,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "alert_id" in payload
    assert "delivery_status" in payload