import pytest
from fastapi.testclient import TestClient

from server import fastapi_app


ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def client():
    return TestClient(fastapi_app)


@pytest.fixture(scope="module")
def auth_headers(client):
    response = client.post(
        "/api/auth/login/admin",
        headers={"X-Session-Device": "devtestclientsessionid0123456789"},
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"admin login failed: {response.status_code}")
    token = response.json().get("access_token") or response.json().get("token")
    return {
        "Authorization": f"Bearer {token}",
        "X-Session-Device": "devtestclientsessionid0123456789",
    }


def test_execution_safety_gate_schema(client, auth_headers):
    response = client.get("/api/execution-safety/gate", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    for key in ["state", "score", "blockers", "warnings", "evaluated_at", "correlation_id"]:
        assert key in data
    assert data["state"] in {"READY", "DEGRADED", "BLOCKED"}
    assert isinstance(data["blockers"], list)
    assert isinstance(data["warnings"], list)


def test_execution_safety_gate_blocker_override(client, auth_headers):
    response = client.get("/api/execution-safety/gate", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    if data.get("blockers"):
        assert data.get("state") == "BLOCKED"


def test_execution_safety_intents_canonical_states(client, auth_headers):
    response = client.get("/api/execution-safety/intents?limit=20", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    expected_states = {
        "CREATED",
        "SUBMITTED",
        "ACKED",
        "PARTIALLY_FILLED",
        "FILLED",
        "FAILED",
        "CANCELED",
        "RECONCILING",
        "RECONCILED",
    }
    assert expected_states.issubset(set((data.get("state_counts") or {}).keys()))


def test_execution_safety_quarantine_required_fields(client, auth_headers):
    response = client.get("/api/execution-safety/quarantine?limit=10", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    if data["items"]:
        item = data["items"][0]
        for key in [
            "quarantine_id",
            "correlation_id",
            "intent_id",
            "reason",
            "failure_stage",
            "retry_count",
            "first_seen_at",
            "last_seen_at",
            "payload_snapshot",
            "error_snapshot",
            "status",
        ]:
            assert key in item


def test_execution_safety_recovery_invalid_action(client, auth_headers):
    response = client.post("/api/execution-safety/recovery/nonexistent-intent/invalid", headers=auth_headers)
    assert response.status_code in {400, 404}


def test_execution_safety_artifact_missing_intent(client, auth_headers):
    response = client.get("/api/execution-safety/artifacts?intent_id=nonexistent", headers=auth_headers)
    assert response.status_code == 404


def test_execution_safety_policy_roundtrip(client, auth_headers):
    update = client.post(
        "/api/execution-safety/recovery/policy/testnet?enable_flag=true&validation_status=VALIDATED&path_open=true",
        headers=auth_headers,
    )
    assert update.status_code == 200
    payload = update.json()
    assert payload.get("environments", {}).get("testnet", {}).get("validation_status") == "VALIDATED"
