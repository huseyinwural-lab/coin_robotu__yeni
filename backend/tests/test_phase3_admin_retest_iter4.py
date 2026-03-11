"""Iteration-4 retest: Phase-3 admin smoke + deterministic failed-events flow."""

import os

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    pytest.skip("REACT_APP_BACKEND_URL is required for public endpoint testing", allow_module_level=True)

API_BASE = f"{BASE_URL.rstrip('/')}/api"


@pytest.fixture(scope="module")
def api_client():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def admin_headers(api_client):
    # module: admin authentication for phase3 retest endpoints
    response = api_client.post(
        f"{API_BASE}/auth/login",
        json={"email": "admin@platform.dev", "password": "Admin12345!"},
        timeout=25,
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code}")
    data = response.json()
    token = data.get("access_token")
    assert isinstance(token, str) and token
    return {"Authorization": f"Bearer {token}"}


def test_phase3_admin_smoke_lists(api_client, admin_headers):
    # module: phase3 admin list endpoints - execution/exposure/state/backtest
    endpoints = [
        "/admin-phase3/execution-policies",
        "/admin-phase3/exposure-groups",
        "/admin-phase3/state-rebuild-logs",
        "/admin-phase3/backtest-cards",
    ]
    for endpoint in endpoints:
        response = api_client.get(f"{API_BASE}{endpoint}", headers=admin_headers, timeout=25)
        assert response.status_code == 200
        payload = response.json()
        assert isinstance(payload, list)


def test_state_rebuild_run_and_persistence(api_client, admin_headers):
    # module: state rebuild trigger + persistence in logs
    before = api_client.get(f"{API_BASE}/admin-phase3/state-rebuild-logs", headers=admin_headers, timeout=25)
    assert before.status_code == 200
    before_rows = before.json()

    run = api_client.post(f"{API_BASE}/admin-phase3/state-rebuild/run", headers=admin_headers, timeout=25)
    assert run.status_code == 200
    run_data = run.json()
    assert run_data["trigger_source"] == "manual_admin"
    assert run_data["status"] in ["completed", "running"]

    after = api_client.get(f"{API_BASE}/admin-phase3/state-rebuild-logs", headers=admin_headers, timeout=25)
    assert after.status_code == 200
    after_rows = after.json()
    assert len(after_rows) >= len(before_rows)
    assert any(item["id"] == run_data["id"] for item in after_rows)


def test_failed_events_seed_retry_resolve_deterministic(api_client, admin_headers):
    # module: failed events deterministic UI flow parity - seed -> retry -> resolve
    seeded = api_client.post(f"{API_BASE}/admin-phase3/failed-events/seed", headers=admin_headers, timeout=25)
    assert seeded.status_code == 200
    seeded_data = seeded.json()
    event_id = seeded_data["id"]
    assert isinstance(event_id, str) and event_id

    listed = api_client.get(f"{API_BASE}/admin-phase3/failed-events", headers=admin_headers, timeout=25)
    assert listed.status_code == 200
    rows = listed.json()
    row = next((item for item in rows if item["id"] == event_id), None)
    assert row is not None
    retry_before = row["retry_count"]

    retried = api_client.post(f"{API_BASE}/admin-phase3/failed-events/{event_id}/retry", headers=admin_headers, timeout=25)
    assert retried.status_code == 200
    retried_data = retried.json()
    assert retried_data["id"] == event_id
    assert retried_data["retry_count"] >= retry_before

    resolved = api_client.post(f"{API_BASE}/admin-phase3/failed-events/{event_id}/resolve", headers=admin_headers, timeout=25)
    assert resolved.status_code == 200
    resolved_data = resolved.json()
    assert resolved_data["id"] == event_id
    assert resolved_data["status"] == "resolved"

    listed_after = api_client.get(f"{API_BASE}/admin-phase3/failed-events", headers=admin_headers, timeout=25)
    assert listed_after.status_code == 200
    rows_after = listed_after.json()
    row_after = next((item for item in rows_after if item["id"] == event_id), None)
    assert row_after is not None
    assert row_after["status"] == "resolved"
