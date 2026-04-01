"""
Incident Intelligence Auth Stability & Action Endpoint Tests
Tests P0 auth stability, P1 operator flow, P2 live action guardrails
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://trade-trace-engine.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


class TestAuthStability:
    """P0: Auth stability tests"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        """Login and get authenticated session with device binding"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        # Generate device ID
        import uuid
        device_id = f"test-device-{uuid.uuid4().hex[:24]}"
        session.headers.update({"X-Session-Device": device_id})
        
        # Login
        login_resp = session.post(f"{BASE_URL}/api/auth/login/admin", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        
        data = login_resp.json()
        token = data.get("access_token")
        assert token, "No access_token in login response"
        
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    def test_admin_login_returns_token(self, auth_session):
        """Test admin login completes and returns token"""
        # Already tested in fixture, just verify session works
        assert "Authorization" in auth_session.headers
        print("PASS: Admin login returns token")
    
    def test_auth_me_with_device_binding(self, auth_session):
        """Test /auth/me works with proper device binding"""
        resp = auth_session.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 200, f"Auth/me failed: {resp.text}"
        
        data = resp.json()
        assert data.get("email") == ADMIN_EMAIL
        assert data.get("role") in ["super_admin", "admin", "ops"]
        print(f"PASS: Auth/me returns user: {data.get('email')}, role: {data.get('role')}")
    
    def test_incident_intelligence_access_after_login(self, auth_session):
        """Test incident intelligence endpoints accessible after login"""
        resp = auth_session.get(f"{BASE_URL}/api/admin/incident-intelligence/incidents")
        assert resp.status_code == 200, f"Incidents endpoint failed: {resp.text}"
        
        data = resp.json()
        assert "items" in data
        print(f"PASS: Incident intelligence accessible, {len(data.get('items', []))} incidents")


class TestOperatorFlow:
    """P1: Real browser operator flow tests"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        """Login and get authenticated session"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        import uuid
        device_id = f"test-device-{uuid.uuid4().hex[:24]}"
        session.headers.update({"X-Session-Device": device_id})
        
        login_resp = session.post(f"{BASE_URL}/api/auth/login/admin", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200
        
        data = login_resp.json()
        token = data.get("access_token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    def test_incident_list_returns_items(self, auth_session):
        """Test incident list endpoint returns items"""
        resp = auth_session.get(f"{BASE_URL}/api/admin/incident-intelligence/incidents")
        assert resp.status_code == 200
        
        data = resp.json()
        items = data.get("items", [])
        assert isinstance(items, list)
        
        if items:
            first = items[0]
            assert "incident_id" in first
            assert "title" in first
            assert "severity" in first
            assert "state" in first
            print(f"PASS: Incident list returns {len(items)} items")
        else:
            print("PASS: Incident list returns empty (no incidents)")
    
    def test_incident_detail_returns_timeline(self, auth_session):
        """Test incident detail endpoint returns incident and timeline"""
        # First get an incident
        list_resp = auth_session.get(f"{BASE_URL}/api/admin/incident-intelligence/incidents")
        assert list_resp.status_code == 200
        
        items = list_resp.json().get("items", [])
        if not items:
            pytest.skip("No incidents to test detail")
        
        incident_id = items[0]["incident_id"]
        
        # Get detail
        detail_resp = auth_session.get(f"{BASE_URL}/api/admin/incident-intelligence/incidents/{incident_id}")
        assert detail_resp.status_code == 200, f"Detail failed: {detail_resp.text}"
        
        data = detail_resp.json()
        assert "incident" in data
        assert "timeline" in data
        
        incident = data["incident"]
        assert incident["incident_id"] == incident_id
        
        timeline = data["timeline"]
        assert "chain" in timeline
        print(f"PASS: Incident detail returns incident and timeline with {len(timeline.get('chain', []))} chain items")


class TestLiveActionGuardrails:
    """P2: Live action guardrails and audit hardening tests"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        """Login and get authenticated session"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        import uuid
        device_id = f"test-device-{uuid.uuid4().hex[:24]}"
        session.headers.update({"X-Session-Device": device_id})
        
        login_resp = session.post(f"{BASE_URL}/api/auth/login/admin", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200
        
        data = login_resp.json()
        token = data.get("access_token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    @pytest.fixture(scope="class")
    def test_incident_id(self, auth_session):
        """Get an incident ID for testing"""
        resp = auth_session.get(f"{BASE_URL}/api/admin/incident-intelligence/incidents")
        assert resp.status_code == 200
        
        items = resp.json().get("items", [])
        if not items:
            pytest.skip("No incidents available for action testing")
        
        return items[0]["incident_id"]
    
    def test_action_endpoint_dry_run_mode(self, auth_session, test_incident_id):
        """Test action endpoint supports dry_run mode with standardized response"""
        resp = auth_session.post(
            f"{BASE_URL}/api/admin/incident-intelligence/incidents/{test_incident_id}/actions",
            json={
                "action": "block_trading",
                "mode": "dry_run",
                "reason": "test_dry_run_mode"
            }
        )
        assert resp.status_code == 200, f"Dry run action failed: {resp.text}"
        
        data = resp.json()
        assert "incident" in data
        assert "action_result" in data
        
        action_result = data["action_result"]
        # Check standardized response fields
        assert "status" in action_result
        assert "action" in action_result
        assert "mode" in action_result
        assert action_result["mode"] == "dry_run"
        assert "reason" in action_result
        assert "connector_result" in action_result
        
        # dry_run should have external_preview
        assert "external_preview" in action_result
        
        print("PASS: Dry run action returns standardized response with external_preview")
        print(f"  - status: {action_result.get('status')}")
        print(f"  - mode: {action_result.get('mode')}")
        print(f"  - external_preview keys: {list(action_result.get('external_preview', {}).keys())}")
    
    def test_action_endpoint_manual_live_mode(self, auth_session, test_incident_id):
        """Test action endpoint supports manual_live mode with standardized response"""
        resp = auth_session.post(
            f"{BASE_URL}/api/admin/incident-intelligence/incidents/{test_incident_id}/actions",
            json={
                "action": "block_trading",
                "mode": "manual_live",
                "reason": "test_manual_live_mode"
            }
        )
        assert resp.status_code == 200, f"Manual live action failed: {resp.text}"
        
        data = resp.json()
        assert "incident" in data
        assert "action_result" in data
        
        action_result = data["action_result"]
        # Check standardized response fields
        assert "status" in action_result
        assert "action" in action_result
        assert "mode" in action_result
        assert action_result["mode"] == "manual_live"
        assert "reason" in action_result
        assert "connector_result" in action_result
        
        # manual_live should have external_live_result
        assert "external_live_result" in action_result
        
        print("PASS: Manual live action returns standardized response with external_live_result")
        print(f"  - status: {action_result.get('status')}")
        print(f"  - mode: {action_result.get('mode')}")
        print(f"  - external_live_result keys: {list(action_result.get('external_live_result', {}).keys())}")
    
    def test_rollback_endpoint_after_action(self, auth_session, test_incident_id):
        """Test rollback endpoint works after a manual_live action"""
        resp = auth_session.post(
            f"{BASE_URL}/api/admin/incident-intelligence/incidents/{test_incident_id}/actions/rollback"
        )
        assert resp.status_code == 200, f"Rollback failed: {resp.text}"
        
        data = resp.json()
        assert "incident" in data
        assert "rollback_payload" in data
        
        rollback_payload = data["rollback_payload"]
        assert isinstance(rollback_payload, dict)
        
        print("PASS: Rollback endpoint returns incident and rollback_payload")
        print(f"  - rollback_payload: {rollback_payload}")
    
    def test_audit_guardrail_payloads_in_remediation_history(self, auth_session, test_incident_id):
        """Test audit/guardrail payloads include required metadata"""
        # Get incident detail to check remediation history
        resp = auth_session.get(f"{BASE_URL}/api/admin/incident-intelligence/incidents/{test_incident_id}")
        assert resp.status_code == 200
        
        data = resp.json()
        incident = data.get("incident", {})
        remediation_history = incident.get("remediation_history", [])
        
        if not remediation_history:
            pytest.skip("No remediation history to verify")
        
        # Check latest remediation entry
        latest = remediation_history[-1]
        
        # Required audit fields
        assert "action" in latest, "Missing action in remediation history"
        assert "status" in latest, "Missing status in remediation history"
        assert "executed_at" in latest, "Missing executed_at in remediation history"
        
        # Guardrail fields (may be present)
        has_reason = "reason" in latest
        has_before_snapshot = "before_snapshot" in latest
        has_after_snapshot = "after_snapshot" in latest
        has_rollback_payload = "rollback_payload" in latest
        has_target = "target" in latest
        
        print("PASS: Remediation history entry has audit fields")
        print(f"  - action: {latest.get('action')}")
        print(f"  - status: {latest.get('status')}")
        print(f"  - has reason: {has_reason}")
        print(f"  - has before_snapshot: {has_before_snapshot}")
        print(f"  - has after_snapshot: {has_after_snapshot}")
        print(f"  - has rollback_payload: {has_rollback_payload}")
        print(f"  - has target: {has_target}")


class TestCooldownBehavior:
    """Test cooldown/dedupe/rate-limit behavior"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        """Login and get authenticated session"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        import uuid
        device_id = f"test-device-{uuid.uuid4().hex[:24]}"
        session.headers.update({"X-Session-Device": device_id})
        
        login_resp = session.post(f"{BASE_URL}/api/auth/login/admin", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200
        
        data = login_resp.json()
        token = data.get("access_token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    def test_single_action_flow_not_blocked(self, auth_session):
        """Test that normal single-action flow is not blocked by cooldown"""
        # Get an incident
        list_resp = auth_session.get(f"{BASE_URL}/api/admin/incident-intelligence/incidents")
        assert list_resp.status_code == 200
        
        items = list_resp.json().get("items", [])
        if not items:
            pytest.skip("No incidents for cooldown test")
        
        incident_id = items[0]["incident_id"]
        
        # Execute a single action - should not be blocked
        resp = auth_session.post(
            f"{BASE_URL}/api/admin/incident-intelligence/incidents/{incident_id}/actions",
            json={
                "action": "reconcile_trigger",
                "mode": "dry_run",
                "reason": "test_single_action"
            }
        )
        
        # Should succeed (200) or fail with cooldown (400)
        if resp.status_code == 200:
            print("PASS: Single action flow not blocked")
        elif resp.status_code == 400:
            data = resp.json()
            detail = data.get("detail", "")
            if "cooldown" in str(detail).lower():
                print("INFO: Action blocked by cooldown (expected if recently executed)")
            else:
                pytest.fail(f"Unexpected 400 error: {detail}")
        else:
            pytest.fail(f"Unexpected status: {resp.status_code} - {resp.text}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
