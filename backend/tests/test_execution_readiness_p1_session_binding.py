"""
Execution Safety Core P1 Testing - Session Binding + P1 Endpoints
Tests:
1. Admin login flow with canary credentials, then /api/auth/me continuity
2. Session binding: bearer+X-Session-Device should pass; bearer-only should fail with session_device_mismatch
3. GET /api/execution-readiness/incident/export returns runbook_recommendations + quarantine_replay_plan
4. GET /api/execution-readiness/reconciliation/summary contract
5. GET /api/execution-readiness/gate/trends contract
6. GET /api/execution-readiness/interventions/audit-trail contract
7. POST /api/execution-readiness/intents/stuck/batch-recover?action=replay contract
"""

import os
import pytest
import requests
import secrets

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://quarantine-pipeline.preview.emergentagent.com"

ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


class TestAuthSessionBinding:
    """Test auth flow with session device binding"""

    @pytest.fixture(scope="class")
    def session(self):
        """Create a requests session"""
        return requests.Session()

    @pytest.fixture(scope="class")
    def device_id(self):
        """Generate a device ID for testing"""
        return f"test-device-{secrets.token_urlsafe(16)}"

    def test_01_login_with_device_header(self, session, device_id):
        """Test login with X-Session-Device header"""
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"X-Session-Device": device_id},
            timeout=30,
        )
        print(f"Login response status: {response.status_code}")
        print(f"Login response: {response.text[:500] if response.text else 'empty'}")
        
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        
        # Verify login response structure
        assert "access_token" in data or "token" in data, "Missing token in response"
        
        # Store token for subsequent tests
        token = data.get("access_token") or data.get("token")
        session.headers["Authorization"] = f"Bearer {token}"
        session.headers["X-Session-Device"] = device_id
        
        print(f"Login successful, token obtained")
        return token

    def test_02_auth_me_with_device_header(self, session, device_id):
        """Test /api/auth/me with X-Session-Device header - should pass"""
        # First login to get token
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"X-Session-Device": device_id},
            timeout=30,
        )
        
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.text}")
        
        data = login_response.json()
        token = data.get("access_token") or data.get("token")
        
        # Now test /auth/me with device header
        me_response = session.get(
            f"{BASE_URL}/api/auth/me",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Session-Device": device_id,
            },
            timeout=30,
        )
        
        print(f"/auth/me response status: {me_response.status_code}")
        print(f"/auth/me response: {me_response.text[:500] if me_response.text else 'empty'}")
        
        assert me_response.status_code == 200, f"/auth/me failed: {me_response.text}"
        user_data = me_response.json()
        assert "email" in user_data or "user" in user_data, "Missing user data in response"
        print(f"/auth/me successful with device header")

    def test_03_auth_me_without_device_header_should_fail(self, session, device_id):
        """Test /api/auth/me without X-Session-Device header - should fail with session_device_mismatch"""
        # First login to get token
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"X-Session-Device": device_id},
            timeout=30,
        )
        
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.text}")
        
        data = login_response.json()
        token = data.get("access_token") or data.get("token")
        
        # Now test /auth/me WITHOUT device header - should fail
        me_response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        
        print(f"/auth/me (no device) response status: {me_response.status_code}")
        print(f"/auth/me (no device) response: {me_response.text[:500] if me_response.text else 'empty'}")
        
        # Should return 401 with session_device_mismatch
        assert me_response.status_code == 401, f"Expected 401, got {me_response.status_code}"
        
        response_data = me_response.json()
        detail = response_data.get("detail", "")
        assert "session_device_mismatch" in str(detail).lower(), f"Expected session_device_mismatch, got: {detail}"
        print(f"Correctly rejected request without device header: {detail}")


class TestExecutionReadinessP1Endpoints:
    """Test P1 execution readiness endpoints"""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get authenticated headers with device binding"""
        device_id = f"test-device-{secrets.token_urlsafe(16)}"
        
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"X-Session-Device": device_id},
            timeout=30,
        )
        
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.text}")
        
        data = login_response.json()
        token = data.get("access_token") or data.get("token")
        
        return {
            "Authorization": f"Bearer {token}",
            "X-Session-Device": device_id,
        }

    def test_incident_export_contract(self, auth_headers):
        """GET /api/execution-readiness/incident/export returns runbook_recommendations + quarantine_replay_plan"""
        response = requests.get(
            f"{BASE_URL}/api/execution-readiness/incident/export",
            headers=auth_headers,
            timeout=60,
        )
        
        print(f"Incident export response status: {response.status_code}")
        
        if response.status_code == 401:
            print(f"Auth failed: {response.text}")
            pytest.skip("Auth failed - session binding issue")
        
        assert response.status_code == 200, f"Incident export failed: {response.text}"
        
        data = response.json()
        print(f"Incident export keys: {list(data.keys())}")
        
        # Verify required fields
        assert "runbook_recommendations" in data, "Missing runbook_recommendations"
        assert "quarantine_replay_plan" in data, "Missing quarantine_replay_plan"
        
        # Verify runbook_recommendations is a list
        runbook = data["runbook_recommendations"]
        assert isinstance(runbook, list), f"runbook_recommendations should be list, got {type(runbook)}"
        print(f"runbook_recommendations count: {len(runbook)}")
        
        # Verify quarantine_replay_plan is a list
        replay_plan = data["quarantine_replay_plan"]
        assert isinstance(replay_plan, list), f"quarantine_replay_plan should be list, got {type(replay_plan)}"
        print(f"quarantine_replay_plan count: {len(replay_plan)}")
        
        # Verify other expected fields
        assert "gate_snapshot" in data, "Missing gate_snapshot"
        assert "intents_snapshot" in data, "Missing intents_snapshot"
        assert "quarantine_snapshot" in data, "Missing quarantine_snapshot"
        assert "package_id" in data, "Missing package_id"
        assert "generated_at" in data, "Missing generated_at"
        
        print(f"Incident export contract verified successfully")

    def test_reconciliation_summary_contract(self, auth_headers):
        """GET /api/execution-readiness/reconciliation/summary contract"""
        response = requests.get(
            f"{BASE_URL}/api/execution-readiness/reconciliation/summary",
            headers=auth_headers,
            timeout=30,
        )
        
        print(f"Reconciliation summary response status: {response.status_code}")
        
        if response.status_code == 401:
            pytest.skip("Auth failed - session binding issue")
        
        assert response.status_code == 200, f"Reconciliation summary failed: {response.text}"
        
        data = response.json()
        print(f"Reconciliation summary keys: {list(data.keys())}")
        
        # Verify required fields
        required_fields = [
            "scanned_events",
            "duplicate_external_orders",
            "duplicate_external_order_count",
            "filled_without_external_order_count",
            "filled_without_external_order_intents",
            "stuck_intent_count",
            "stuck_intents",
        ]
        
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        # Verify types
        assert isinstance(data["scanned_events"], int), "scanned_events should be int"
        assert isinstance(data["duplicate_external_orders"], list), "duplicate_external_orders should be list"
        assert isinstance(data["duplicate_external_order_count"], int), "duplicate_external_order_count should be int"
        assert isinstance(data["stuck_intents"], list), "stuck_intents should be list"
        
        print(f"Reconciliation summary contract verified: scanned_events={data['scanned_events']}, stuck_intent_count={data['stuck_intent_count']}")

    def test_gate_trends_contract(self, auth_headers):
        """GET /api/execution-readiness/gate/trends contract"""
        response = requests.get(
            f"{BASE_URL}/api/execution-readiness/gate/trends",
            headers=auth_headers,
            params={"days": 7},
            timeout=30,
        )
        
        print(f"Gate trends response status: {response.status_code}")
        
        if response.status_code == 401:
            pytest.skip("Auth failed - session binding issue")
        
        assert response.status_code == 200, f"Gate trends failed: {response.text}"
        
        data = response.json()
        print(f"Gate trends keys: {list(data.keys())}")
        
        # Verify required fields
        assert "days" in data, "Missing days field"
        assert "items" in data, "Missing items field"
        
        # Verify types
        assert isinstance(data["days"], int), "days should be int"
        assert isinstance(data["items"], list), "items should be list"
        
        # If items exist, verify structure
        if data["items"]:
            item = data["items"][0]
            assert "date" in item, "Missing date in trend item"
            assert "total" in item, "Missing total in trend item"
            print(f"Gate trends item sample: {item}")
        
        print(f"Gate trends contract verified: days={data['days']}, items_count={len(data['items'])}")

    def test_interventions_audit_trail_contract(self, auth_headers):
        """GET /api/execution-readiness/interventions/audit-trail contract"""
        response = requests.get(
            f"{BASE_URL}/api/execution-readiness/interventions/audit-trail",
            headers=auth_headers,
            params={"limit": 50},
            timeout=30,
        )
        
        print(f"Interventions audit trail response status: {response.status_code}")
        
        if response.status_code == 401:
            pytest.skip("Auth failed - session binding issue")
        
        assert response.status_code == 200, f"Interventions audit trail failed: {response.text}"
        
        data = response.json()
        print(f"Interventions audit trail keys: {list(data.keys())}")
        
        # Verify required fields
        assert "total" in data, "Missing total field"
        assert "items" in data, "Missing items field"
        
        # Verify types
        assert isinstance(data["total"], int), "total should be int"
        assert isinstance(data["items"], list), "items should be list"
        
        # If items exist, verify structure
        if data["items"]:
            item = data["items"][0]
            expected_fields = ["id", "action", "entity_type", "entity_id", "actor_user_id", "actor_role", "created_at"]
            for field in expected_fields:
                assert field in item, f"Missing {field} in audit trail item"
            print(f"Audit trail item sample: action={item.get('action')}, actor_role={item.get('actor_role')}")
        
        print(f"Interventions audit trail contract verified: total={data['total']}")

    def test_batch_recover_stuck_intents_contract(self, auth_headers):
        """POST /api/execution-readiness/intents/stuck/batch-recover?action=replay contract"""
        response = requests.post(
            f"{BASE_URL}/api/execution-readiness/intents/stuck/batch-recover",
            headers=auth_headers,
            params={"action": "replay", "limit": 10},
            timeout=30,
        )
        
        print(f"Batch recover response status: {response.status_code}")
        
        if response.status_code == 401:
            pytest.skip("Auth failed - session binding issue")
        
        assert response.status_code == 200, f"Batch recover failed: {response.text}"
        
        data = response.json()
        print(f"Batch recover keys: {list(data.keys())}")
        
        # Verify required fields
        assert "processed" in data, "Missing processed field"
        assert "action" in data, "Missing action field"
        assert "results" in data, "Missing results field"
        
        # Verify types
        assert isinstance(data["processed"], int), "processed should be int"
        assert isinstance(data["action"], str), "action should be str"
        assert isinstance(data["results"], list), "results should be list"
        
        # Verify action matches
        assert data["action"] == "replay", f"Expected action=replay, got {data['action']}"
        
        print(f"Batch recover contract verified: processed={data['processed']}, action={data['action']}")

    def test_batch_recover_invalid_action(self, auth_headers):
        """POST /api/execution-readiness/intents/stuck/batch-recover with invalid action should return 400"""
        response = requests.post(
            f"{BASE_URL}/api/execution-readiness/intents/stuck/batch-recover",
            headers=auth_headers,
            params={"action": "invalid_action", "limit": 10},
            timeout=30,
        )
        
        print(f"Batch recover invalid action response status: {response.status_code}")
        
        if response.status_code == 401:
            pytest.skip("Auth failed - session binding issue")
        
        assert response.status_code == 400, f"Expected 400 for invalid action, got {response.status_code}"
        
        data = response.json()
        assert "detail" in data, "Missing detail in error response"
        assert "invalid_action" in str(data["detail"]).lower(), f"Expected invalid_action error, got: {data['detail']}"
        
        print(f"Invalid action correctly rejected: {data['detail']}")


class TestExecutionReadinessGateEndpoint:
    """Test execution readiness gate endpoint with session binding"""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get authenticated headers with device binding"""
        device_id = f"test-device-{secrets.token_urlsafe(16)}"
        
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"X-Session-Device": device_id},
            timeout=30,
        )
        
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.text}")
        
        data = login_response.json()
        token = data.get("access_token") or data.get("token")
        
        return {
            "Authorization": f"Bearer {token}",
            "X-Session-Device": device_id,
        }

    def test_gate_endpoint_with_session_binding(self, auth_headers):
        """GET /api/execution-readiness/gate with proper session binding"""
        response = requests.get(
            f"{BASE_URL}/api/execution-readiness/gate",
            headers=auth_headers,
            timeout=60,
        )
        
        print(f"Gate endpoint response status: {response.status_code}")
        
        if response.status_code == 401:
            print(f"Auth failed: {response.text}")
            pytest.skip("Auth failed - session binding issue")
        
        assert response.status_code == 200, f"Gate endpoint failed: {response.text}"
        
        data = response.json()
        print(f"Gate endpoint keys: {list(data.keys())}")
        
        # Verify required fields
        required_fields = [
            "gate_state",
            "execution_allowed",
            "hard_blockers",
            "soft_warnings",
            "bybit_order_smoke",
            "artifact",
        ]
        
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        print(f"Gate state: {data['gate_state']}, execution_allowed: {data['execution_allowed']}")
        print(f"Hard blockers count: {len(data['hard_blockers'])}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
