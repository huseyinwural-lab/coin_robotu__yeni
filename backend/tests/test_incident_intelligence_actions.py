# Incident Intelligence Action Connectors Tests
# Tests: block_trading, reduce_leverage, reconcile_trigger, rollback, policies endpoint
# Auto-remediation external side effects remain SAFE/MOCK-ORIENTED

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import pytest
from fastapi.testclient import TestClient
from server import app
from db import SessionLocal
from models import User, UserRole
from core.security import hash_password

# Test credentials
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def client():
    """TestClient instance"""
    return TestClient(app)


@pytest.fixture(scope="module")
def admin_user():
    """Create or get admin user for testing"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        if not user:
            user = User(
                email=ADMIN_EMAIL,
                password_hash=hash_password(ADMIN_PASSWORD),
                role=UserRole.ADMIN,
                is_active=True,
                approval_status="approved",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return user
    finally:
        db.close()


@pytest.fixture(scope="module")
def auth_headers(client, admin_user):
    """Authenticate and get headers"""
    response = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.status_code}")
    token = response.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def incident_id(client, auth_headers):
    """Get or create an incident for testing"""
    # First run engine to ensure incidents exist
    client.post("/api/admin/incident-intelligence/engine/run?window_minutes=60", headers=auth_headers)
    
    # Get incidents
    response = client.get("/api/admin/incident-intelligence/incidents", headers=auth_headers)
    if response.status_code != 200:
        pytest.skip("Could not get incidents")
    
    items = response.json().get("items", [])
    if not items:
        pytest.skip("No incidents available for testing")
    
    return items[0].get("incident_id")


class TestIncidentActionConnectors:
    """Test action connector endpoints - block_trading, reduce_leverage, reconcile_trigger"""

    def test_block_trading_action(self, client, auth_headers, incident_id):
        """POST /incidents/{id}/actions with block_trading should return 200"""
        response = client.post(
            f"/api/admin/incident-intelligence/incidents/{incident_id}/actions",
            json={"action": "block_trading", "mode": "manual"},
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "incident" in data, "Missing incident in response"
        assert "action_result" in data, "Missing action_result in response"
        
        # Verify action result
        action_result = data.get("action_result", {})
        assert action_result.get("action") == "block_trading", "Action should be block_trading"
        assert action_result.get("status") == "executed", "Status should be executed"
        assert "connector_result" in action_result, "Missing connector_result"
        
        # Verify incident state updated
        incident = data.get("incident", {})
        assert incident.get("state") == "MITIGATED", "Incident state should be MITIGATED after block_trading"

    def test_reduce_leverage_action(self, client, auth_headers, incident_id):
        """POST /incidents/{id}/actions with reduce_leverage should return 200"""
        response = client.post(
            f"/api/admin/incident-intelligence/incidents/{incident_id}/actions",
            json={"action": "reduce_leverage", "mode": "manual"},
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "incident" in data, "Missing incident in response"
        assert "action_result" in data, "Missing action_result in response"
        
        # Verify action result
        action_result = data.get("action_result", {})
        assert action_result.get("action") == "reduce_leverage", "Action should be reduce_leverage"
        assert action_result.get("status") == "executed", "Status should be executed"
        assert "connector_result" in action_result, "Missing connector_result"
        
        # Verify connector result has leverage info
        connector_result = action_result.get("connector_result", {})
        assert "previous_leverage_cap" in connector_result or "current_leverage_cap" in connector_result, \
            "Connector result should have leverage cap info"

    def test_reconcile_trigger_action(self, client, auth_headers, incident_id):
        """POST /incidents/{id}/actions with reconcile_trigger should return 200"""
        response = client.post(
            f"/api/admin/incident-intelligence/incidents/{incident_id}/actions",
            json={"action": "reconcile_trigger", "mode": "manual"},
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "incident" in data, "Missing incident in response"
        assert "action_result" in data, "Missing action_result in response"
        
        # Verify action result
        action_result = data.get("action_result", {})
        assert action_result.get("action") == "reconcile_trigger", "Action should be reconcile_trigger"
        assert action_result.get("status") == "executed", "Status should be executed"

    def test_invalid_action_returns_400(self, client, auth_headers, incident_id):
        """POST /incidents/{id}/actions with invalid action should return 400"""
        response = client.post(
            f"/api/admin/incident-intelligence/incidents/{incident_id}/actions",
            json={"action": "invalid_action_xyz", "mode": "manual"},
            headers=auth_headers,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"


class TestIncidentRollback:
    """Test rollback endpoint"""

    def test_rollback_after_block_trading(self, client, auth_headers, incident_id):
        """POST /incidents/{id}/actions/rollback should rollback last action"""
        # First execute block_trading to have something to rollback
        client.post(
            f"/api/admin/incident-intelligence/incidents/{incident_id}/actions",
            json={"action": "block_trading", "mode": "manual"},
            headers=auth_headers,
        )
        
        # Now rollback
        response = client.post(
            f"/api/admin/incident-intelligence/incidents/{incident_id}/actions/rollback",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "incident" in data, "Missing incident in response"
        assert "rollback_payload" in data, "Missing rollback_payload in response"
        
        # Verify rollback payload
        rollback_payload = data.get("rollback_payload", {})
        assert "trading_enabled" in rollback_payload, "Rollback payload should have trading_enabled"

    def test_rollback_nonexistent_incident_returns_404(self, client, auth_headers):
        """POST /incidents/{id}/actions/rollback with nonexistent incident should return 404"""
        response = client.post(
            "/api/admin/incident-intelligence/incidents/nonexistent-incident-id/actions/rollback",
            headers=auth_headers,
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"


class TestIncidentPolicies:
    """Test policies endpoint"""

    def test_get_policies_returns_200(self, client, auth_headers):
        """GET /policies should return 200 with policy config"""
        response = client.get("/api/admin/incident-intelligence/policies", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify policy domains exist
        assert "execution" in data, "Missing execution policy domain"
        assert "risk" in data, "Missing risk policy domain"
        assert "system" in data, "Missing system policy domain"
        assert "exchange" in data, "Missing exchange policy domain"
        
        # Verify policy structure
        for domain in ["execution", "risk", "system", "exchange"]:
            policies = data.get(domain, [])
            assert isinstance(policies, list), f"{domain} policies should be a list"
            if policies:
                policy = policies[0]
                assert "action" in policy, f"Missing action in {domain} policy"
                assert "severity" in policy, f"Missing severity in {domain} policy"
                assert "approval_mode" in policy, f"Missing approval_mode in {domain} policy"

    def test_put_policies_returns_200(self, client, auth_headers):
        """PUT /policies should update and return policy config"""
        # Get current policies
        get_response = client.get("/api/admin/incident-intelligence/policies", headers=auth_headers)
        current_policies = get_response.json()
        
        # Update with same policies (no change)
        response = client.put(
            "/api/admin/incident-intelligence/policies",
            json={"execution": current_policies.get("execution", [])},
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response has policy domains
        assert "execution" in data, "Missing execution in response"


class TestIncidentActionHistory:
    """Test that actions are recorded in remediation_history"""

    def test_action_recorded_in_history(self, client, auth_headers, incident_id):
        """Actions should be recorded in incident remediation_history"""
        # Execute an action
        client.post(
            f"/api/admin/incident-intelligence/incidents/{incident_id}/actions",
            json={"action": "block_trading", "mode": "manual"},
            headers=auth_headers,
        )
        
        # Get incident detail
        response = client.get(
            f"/api/admin/incident-intelligence/incidents/{incident_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        incident = data.get("incident", {})
        history = incident.get("remediation_history", [])
        
        # Verify history has entries
        assert len(history) > 0, "remediation_history should have entries after action"
        
        # Verify latest entry has required fields
        latest = history[-1]
        assert "action" in latest, "History entry should have action"
        assert "status" in latest, "History entry should have status"
        assert "executed_at" in latest, "History entry should have executed_at"
