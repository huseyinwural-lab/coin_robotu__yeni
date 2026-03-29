"""
Execution Safety Namespace P0 Tests - Iteration 174
Tests for new /api/execution-safety/* namespace endpoints

Features tested:
- Gate standard schema: state/score/blockers/warnings/evaluated_at/correlation_id
- Hard blocker override: blockers varsa state BLOCKED
- Intent lifecycle canonical states: CREATED,SUBMITTED,ACKED,PARTIALLY_FILLED,FILLED,FAILED,CANCELED,RECONCILING,RECONCILED
- Quarantine required fields contract
- Recovery endpoints: /recovery, /recovery/{intent_id}/{action}, /recovery/batch
- Artifacts endpoints: /artifacts?intent_id=..., /artifacts/incident-export
- Deprecated legacy namespace /api/execution-readiness/* returns deprecated marker
"""

import os
from pathlib import Path
import pytest
import requests


def _resolve_base_url() -> str:
    env_url = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if env_url:
        return env_url.rstrip("/")
    frontend_env = Path("/app/frontend/.env")
    if frontend_env.exists():
        for line in frontend_env.read_text(encoding="utf-8").splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().strip('"').rstrip("/")
    return ""


BASE_URL = _resolve_base_url()
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def admin_session():
    """Get authenticated admin session with device_id header"""
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL is missing")
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Generate device_id for session binding
    import uuid
    device_id = f"test-device-{uuid.uuid4().hex}"
    session.headers.update({"X-Session-Device": device_id})
    
    # Login
    login_response = session.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    
    if login_response.status_code != 200:
        pytest.skip(f"Admin login failed: {login_response.status_code} - {login_response.text}")
    
    token = login_response.json().get("access_token")
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    
    return session


class TestExecutionSafetyGateEndpoint:
    """Tests for /api/execution-safety/gate endpoint"""
    
    def test_gate_returns_200(self, admin_session):
        """Gate endpoint should return 200 OK"""
        response = admin_session.get(f"{BASE_URL}/api/execution-safety/gate")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_gate_standard_schema_fields(self, admin_session):
        """Gate response must contain standard schema fields"""
        response = admin_session.get(f"{BASE_URL}/api/execution-safety/gate")
        assert response.status_code == 200
        
        data = response.json()
        
        # Required standard schema fields
        required_fields = ["state", "score", "blockers", "warnings", "evaluated_at", "correlation_id"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        # Validate field types
        assert isinstance(data["state"], str), "state must be string"
        assert isinstance(data["score"], (int, float)), "score must be numeric"
        assert isinstance(data["blockers"], list), "blockers must be list"
        assert isinstance(data["warnings"], list), "warnings must be list"
        assert isinstance(data["evaluated_at"], str), "evaluated_at must be string"
        assert isinstance(data["correlation_id"], str), "correlation_id must be string"
    
    def test_gate_state_values(self, admin_session):
        """Gate state must be one of READY, DEGRADED, BLOCKED"""
        response = admin_session.get(f"{BASE_URL}/api/execution-safety/gate")
        assert response.status_code == 200
        
        data = response.json()
        valid_states = {"READY", "DEGRADED", "BLOCKED"}
        assert data["state"] in valid_states, f"Invalid state: {data['state']}"
    
    def test_gate_hard_blocker_override(self, admin_session):
        """If blockers exist, state must be BLOCKED"""
        response = admin_session.get(f"{BASE_URL}/api/execution-safety/gate")
        assert response.status_code == 200
        
        data = response.json()
        blockers = data.get("blockers", [])
        state = data.get("state")
        
        # If blockers exist, state must be BLOCKED
        if blockers:
            assert state == "BLOCKED", f"State should be BLOCKED when blockers exist, got {state}"
        
        print(f"Gate state: {state}, blockers: {blockers}")
    
    def test_gate_force_refresh(self, admin_session):
        """Gate endpoint should accept force_refresh parameter"""
        response = admin_session.get(f"{BASE_URL}/api/execution-safety/gate?force_refresh=true")
        assert response.status_code == 200
        
        data = response.json()
        assert "state" in data
        assert "evaluated_at" in data


class TestExecutionSafetyIntentsEndpoint:
    """Tests for /api/execution-safety/intents endpoint"""
    
    def test_intents_returns_200(self, admin_session):
        """Intents endpoint should return 200 OK"""
        response = admin_session.get(f"{BASE_URL}/api/execution-safety/intents")
        assert response.status_code == 200
    
    def test_intents_response_structure(self, admin_session):
        """Intents response must have required structure"""
        response = admin_session.get(f"{BASE_URL}/api/execution-safety/intents")
        assert response.status_code == 200
        
        data = response.json()
        required_fields = ["total", "stuck_count", "state_counts", "items"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
    
    def test_intents_canonical_states(self, admin_session):
        """Intent state_counts must use canonical states"""
        response = admin_session.get(f"{BASE_URL}/api/execution-safety/intents")
        assert response.status_code == 200
        
        data = response.json()
        state_counts = data.get("state_counts", {})
        
        # Canonical states as per spec
        canonical_states = {
            "CREATED", "SUBMITTED", "ACKED", "PARTIALLY_FILLED", 
            "FILLED", "FAILED", "CANCELED", "RECONCILING", "RECONCILED"
        }
        
        for state in state_counts.keys():
            assert state in canonical_states, f"Non-canonical state found: {state}"
        
        print(f"State counts: {state_counts}")
    
    def test_intents_limit_parameter(self, admin_session):
        """Intents endpoint should respect limit parameter"""
        response = admin_session.get(f"{BASE_URL}/api/execution-safety/intents?limit=10")
        assert response.status_code == 200
        
        data = response.json()
        items = data.get("items", [])
        assert len(items) <= 10, f"Expected max 10 items, got {len(items)}"
    
    def test_intents_include_events(self, admin_session):
        """Intents endpoint should support include_events parameter"""
        response = admin_session.get(f"{BASE_URL}/api/execution-safety/intents?include_events=true&limit=5")
        assert response.status_code == 200
        
        data = response.json()
        # If items exist and include_events=true, items should have events field
        items = data.get("items", [])
        if items:
            # Events field should be present when include_events=true
            first_item = items[0]
            assert "events" in first_item, "events field should be present when include_events=true"


class TestExecutionSafetyQuarantineEndpoint:
    """Tests for /api/execution-safety/quarantine endpoint"""
    
    def test_quarantine_returns_200(self, admin_session):
        """Quarantine endpoint should return 200 OK"""
        response = admin_session.get(f"{BASE_URL}/api/execution-safety/quarantine")
        assert response.status_code == 200
    
    def test_quarantine_response_structure(self, admin_session):
        """Quarantine response must have required structure"""
        response = admin_session.get(f"{BASE_URL}/api/execution-safety/quarantine")
        assert response.status_code == 200
        
        data = response.json()
        required_fields = ["total", "items"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
    
    def test_quarantine_item_required_fields(self, admin_session):
        """Quarantine items must have required fields per contract"""
        response = admin_session.get(f"{BASE_URL}/api/execution-safety/quarantine")
        assert response.status_code == 200
        
        data = response.json()
        items = data.get("items", [])
        
        # Required fields per quarantine contract
        required_fields = [
            "quarantine_id", "correlation_id", "intent_id", "reason",
            "failure_stage", "retry_count", "first_seen_at", "last_seen_at",
            "payload_snapshot", "error_snapshot", "status"
        ]
        
        for item in items[:5]:  # Check first 5 items
            for field in required_fields:
                assert field in item, f"Missing required field in quarantine item: {field}"
        
        print(f"Quarantine total: {data.get('total')}")


class TestExecutionSafetyRecoveryEndpoints:
    """Tests for /api/execution-safety/recovery/* endpoints"""
    
    def test_recovery_overview_returns_200(self, admin_session):
        """Recovery overview endpoint should return 200 OK"""
        response = admin_session.get(f"{BASE_URL}/api/execution-safety/recovery")
        assert response.status_code == 200
    
    def test_recovery_overview_structure(self, admin_session):
        """Recovery overview must have required structure"""
        response = admin_session.get(f"{BASE_URL}/api/execution-safety/recovery")
        assert response.status_code == 200
        
        data = response.json()
        required_fields = ["active_stuck_intents", "quarantined_events", "replay_history"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
    
    def test_recovery_batch_invalid_action(self, admin_session):
        """Recovery batch should reject invalid action"""
        response = admin_session.post(
            f"{BASE_URL}/api/execution-safety/recovery/batch?action=invalid_action&limit=10"
        )
        assert response.status_code == 400
        
        data = response.json()
        assert "invalid_action" in str(data.get("detail", "")).lower()
    
    def test_recovery_batch_valid_actions(self, admin_session):
        """Recovery batch should accept valid actions"""
        valid_actions = ["retry", "cancel", "reconcile", "quarantine"]
        
        for action in valid_actions:
            response = admin_session.post(
                f"{BASE_URL}/api/execution-safety/recovery/batch?action={action}&limit=1"
            )
            # Should return 200 even if no items to process
            assert response.status_code == 200, f"Action {action} failed: {response.text}"
            
            data = response.json()
            assert "processed" in data
            assert "action" in data
    
    def test_recovery_policy_returns_200(self, admin_session):
        """Recovery policy endpoint should return 200 OK"""
        response = admin_session.get(f"{BASE_URL}/api/execution-safety/recovery/policy")
        assert response.status_code == 200
        
        data = response.json()
        assert "environments" in data
        assert "policy_id" in data
    
    def test_recovery_reconciliation_summary(self, admin_session):
        """Reconciliation summary endpoint should return 200 OK"""
        response = admin_session.get(f"{BASE_URL}/api/execution-safety/recovery/reconciliation-summary")
        assert response.status_code == 200
        
        data = response.json()
        required_fields = ["scanned_events", "duplicate_external_order_count", "stuck_intent_count"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
    
    def test_recovery_gate_trends(self, admin_session):
        """Gate trends endpoint should return 200 OK"""
        response = admin_session.get(f"{BASE_URL}/api/execution-safety/recovery/gate-trends?days=7")
        assert response.status_code == 200
        
        data = response.json()
        assert "days" in data
        assert "items" in data
    
    def test_recovery_intervention_audit(self, admin_session):
        """Intervention audit endpoint should return 200 OK"""
        response = admin_session.get(f"{BASE_URL}/api/execution-safety/recovery/intervention-audit")
        assert response.status_code == 200
        
        data = response.json()
        assert "total" in data
        assert "items" in data


class TestExecutionSafetyArtifactsEndpoints:
    """Tests for /api/execution-safety/artifacts/* endpoints"""
    
    def test_artifacts_requires_intent_id(self, admin_session):
        """Artifacts endpoint requires intent_id parameter"""
        response = admin_session.get(f"{BASE_URL}/api/execution-safety/artifacts")
        # Should return 422 (validation error) without required intent_id
        assert response.status_code == 422
    
    def test_artifacts_with_invalid_intent_id(self, admin_session):
        """Artifacts endpoint should return 404 for non-existent intent"""
        response = admin_session.get(f"{BASE_URL}/api/execution-safety/artifacts?intent_id=non_existent_intent_123")
        assert response.status_code == 404
        
        data = response.json()
        assert "intent_not_found" in str(data.get("detail", "")).lower()
    
    def test_incident_export_returns_200(self, admin_session):
        """Incident export endpoint should return 200 OK"""
        response = admin_session.get(f"{BASE_URL}/api/execution-safety/artifacts/incident-export")
        assert response.status_code == 200
    
    def test_incident_export_structure(self, admin_session):
        """Incident export must have required structure"""
        response = admin_session.get(f"{BASE_URL}/api/execution-safety/artifacts/incident-export")
        assert response.status_code == 200
        
        data = response.json()
        required_fields = [
            "schema_version", "package_type", "package_id", "generated_at",
            "gate_snapshot", "intents_snapshot", "quarantine_snapshot",
            "runbook_recommendations", "quarantine_replay_plan"
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        # Validate runbook_recommendations structure
        runbook = data.get("runbook_recommendations", [])
        assert isinstance(runbook, list), "runbook_recommendations must be list"
        
        # Validate quarantine_replay_plan structure
        replay_plan = data.get("quarantine_replay_plan", [])
        assert isinstance(replay_plan, list), "quarantine_replay_plan must be list"


class TestDeprecatedLegacyNamespace:
    """Tests for deprecated /api/execution-readiness/* namespace"""
    
    def test_legacy_gate_returns_deprecated_marker(self, admin_session):
        """Legacy gate endpoint should return deprecated marker"""
        response = admin_session.get(f"{BASE_URL}/api/execution-readiness/gate")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("deprecated") is True, "Legacy endpoint should have deprecated=true"
        assert "replacement_namespace" in data, "Legacy endpoint should have replacement_namespace"
        assert "/api/execution-safety/*" in data.get("replacement_namespace", "")
    
    def test_legacy_intents_returns_deprecated_marker(self, admin_session):
        """Legacy intents endpoint should return deprecated marker"""
        response = admin_session.get(f"{BASE_URL}/api/execution-readiness/intents")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("deprecated") is True
        assert "replacement_namespace" in data
    
    def test_legacy_quarantine_returns_deprecated_marker(self, admin_session):
        """Legacy quarantine endpoint should return deprecated marker"""
        response = admin_session.get(f"{BASE_URL}/api/execution-readiness/quarantine")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("deprecated") is True
        assert "replacement_namespace" in data
    
    def test_legacy_incident_export_returns_deprecated_marker(self, admin_session):
        """Legacy incident export endpoint should return deprecated marker"""
        response = admin_session.get(f"{BASE_URL}/api/execution-readiness/incident/export")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("deprecated") is True
        assert "replacement_namespace" in data


class TestExecutionSafetyObservability:
    """Tests for /api/execution-safety/observability endpoint"""
    
    def test_observability_returns_200(self, admin_session):
        """Observability endpoint should return 200 OK"""
        response = admin_session.get(f"{BASE_URL}/api/execution-safety/observability")
        assert response.status_code == 200
    
    def test_observability_structure(self, admin_session):
        """Observability response must have required structure"""
        response = admin_session.get(f"{BASE_URL}/api/execution-safety/observability")
        assert response.status_code == 200
        
        data = response.json()
        required_fields = [
            "current_gate_state", "blockers", "active_stuck_intents",
            "quarantined_events", "replay_history"
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"


class TestEnvironmentPolicyEndpoints:
    """Tests for environment policy endpoints"""
    
    def test_get_environment_policy(self, admin_session):
        """Get environment policy should return 200 OK"""
        response = admin_session.get(f"{BASE_URL}/api/execution-safety/recovery/policy")
        assert response.status_code == 200
        
        data = response.json()
        assert "environments" in data
        
        environments = data.get("environments", {})
        expected_envs = ["testnet", "staging", "live"]
        for env in expected_envs:
            assert env in environments, f"Missing environment: {env}"
    
    def test_update_environment_policy_invalid_env(self, admin_session):
        """Update policy should reject invalid environment"""
        response = admin_session.post(
            f"{BASE_URL}/api/execution-safety/recovery/policy/invalid_env",
            params={
                "enable_flag": True,
                "validation_status": "VALIDATED",
                "path_open": False
            }
        )
        assert response.status_code == 400
        
        data = response.json()
        assert "invalid_environment" in str(data.get("detail", "")).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
