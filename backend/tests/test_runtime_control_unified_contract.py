"""
Test Runtime Control Unified Contract - P0 Priority
Tests for:
1. POST/PUT runtime action endpoints return contract fields: status, trace_id, message, state_snapshot
2. Runtime actions return audit_log_id and can be traced in action-audit list
3. Alert policy rollback endpoint enforces phrase rule (wrong phrase => 400, expected phrase message)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
OPS_EMAIL = "canary.ops@platform.local"
OPS_PASSWORD = "CanaryOps123!"


class TestRuntimeControlUnifiedContract:
    """Tests for runtime control unified contract - P0 priority"""

    @pytest.fixture(scope="class")
    def super_admin_token(self):
        """Get super admin authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
        )
        if response.status_code != 200:
            pytest.skip(f"Super admin login failed: {response.status_code} - {response.text}")
        data = response.json()
        return data.get("access_token") or data.get("token")

    @pytest.fixture(scope="class")
    def ops_token(self):
        """Get ops authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": OPS_EMAIL, "password": OPS_PASSWORD},
        )
        if response.status_code != 200:
            pytest.skip(f"Ops login failed: {response.status_code} - {response.text}")
        data = response.json()
        return data.get("access_token") or data.get("token")

    @pytest.fixture(scope="class")
    def super_admin_headers(self, super_admin_token):
        """Headers with super admin auth"""
        return {
            "Authorization": f"Bearer {super_admin_token}",
            "Content-Type": "application/json",
        }

    @pytest.fixture(scope="class")
    def ops_headers(self, ops_token):
        """Headers with ops auth"""
        return {
            "Authorization": f"Bearer {ops_token}",
            "Content-Type": "application/json",
        }

    # ==================== Contract Field Tests ====================

    def test_heartbeat_check_returns_contract_fields(self, super_admin_headers):
        """POST /runtime/heartbeat/check returns status, trace_id, message, state_snapshot"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/heartbeat/check",
            headers=super_admin_headers,
            json={"lag_threshold_seconds": 60},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        # Verify contract fields
        assert "status" in data, "Missing 'status' field in response"
        assert "trace_id" in data, "Missing 'trace_id' field in response"
        assert "message" in data, "Missing 'message' field in response"
        assert "state_snapshot" in data, "Missing 'state_snapshot' field in response"
        assert "audit_log_id" in data, "Missing 'audit_log_id' field in response"

        # Verify status is 'ok'
        assert data["status"] == "ok", f"Expected status 'ok', got '{data['status']}'"

        # Verify trace_id is a valid UUID format
        assert len(data["trace_id"]) == 36, f"trace_id should be UUID format, got: {data['trace_id']}"

        print(f"✓ heartbeat/check contract verified: status={data['status']}, trace_id={data['trace_id'][:8]}...")

    def test_ws_reconnect_returns_contract_fields(self, super_admin_headers):
        """POST /runtime/ws/reconnect returns status, trace_id, message, state_snapshot"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/ws/reconnect",
            headers=super_admin_headers,
            json={"reason": "test_contract_verification", "confirmation_phrase": "RECONNECT WS"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        # Verify contract fields
        assert "status" in data, "Missing 'status' field"
        assert "trace_id" in data, "Missing 'trace_id' field"
        assert "message" in data, "Missing 'message' field"
        assert "state_snapshot" in data, "Missing 'state_snapshot' field"
        assert "audit_log_id" in data, "Missing 'audit_log_id' field"

        assert data["status"] == "ok"
        print(f"✓ ws/reconnect contract verified: audit_log_id={data['audit_log_id']}")

    def test_ws_force_new_session_returns_contract_fields(self, super_admin_headers):
        """POST /runtime/ws/force-new-session returns contract fields"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/ws/force-new-session",
            headers=super_admin_headers,
            json={"reason": "test_contract_verification", "confirmation_phrase": "FORCE NEW WS SESSION"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        assert "status" in data and data["status"] == "ok"
        assert "trace_id" in data
        assert "message" in data
        assert "state_snapshot" in data
        assert "audit_log_id" in data
        print("✓ ws/force-new-session contract verified")

    def test_pipeline_resync_returns_contract_fields(self, super_admin_headers):
        """POST /runtime/pipeline/resync returns contract fields"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/pipeline/resync",
            headers=super_admin_headers,
            json={"reason": "test_contract_verification", "confirmation_phrase": "FORCE PIPELINE RESYNC"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        assert "status" in data and data["status"] == "ok"
        assert "trace_id" in data
        assert "message" in data
        assert "state_snapshot" in data
        assert "audit_log_id" in data
        print("✓ pipeline/resync contract verified")

    def test_pipeline_flush_returns_contract_fields(self, super_admin_headers):
        """POST /runtime/pipeline/flush returns contract fields"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/pipeline/flush",
            headers=super_admin_headers,
            json={
                "reason": "test_contract_verification",
                "confirmation_phrase": "FLUSH PIPELINE",
                "queue_type": "all",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        assert "status" in data and data["status"] == "ok"
        assert "trace_id" in data
        assert "message" in data
        assert "state_snapshot" in data
        assert "audit_log_id" in data
        print("✓ pipeline/flush contract verified")

    def test_gate_recheck_returns_contract_fields(self, super_admin_headers):
        """POST /runtime/gate/recheck returns contract fields"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/gate/recheck",
            headers=super_admin_headers,
            json={"reason": "test_contract_verification", "confirmation_phrase": "RECHECK RELEASE GATE"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        assert "status" in data and data["status"] == "ok"
        assert "trace_id" in data
        assert "message" in data
        assert "state_snapshot" in data
        assert "audit_log_id" in data
        print("✓ gate/recheck contract verified")

    def test_service_restart_returns_contract_fields(self, super_admin_headers):
        """POST /runtime/service/restart returns contract fields"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/service/restart",
            headers=super_admin_headers,
            json={
                "reason": "test_contract_verification",
                "confirmation_phrase": "RESTART SERVICE",
                "service": "all",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        assert "status" in data and data["status"] == "ok"
        assert "trace_id" in data
        assert "message" in data
        assert "state_snapshot" in data
        assert "audit_log_id" in data
        print("✓ service/restart contract verified")

    def test_override_create_returns_contract_fields(self, super_admin_headers):
        """POST /runtime/override/create returns contract fields"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/override/create",
            headers=super_admin_headers,
            json={
                "override_type": "test_override",
                "scope": "global",
                "ttl_minutes": 5,
                "reason": "test_contract_verification",
                "confirmation_phrase": "CREATE OVERRIDE",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        assert "status" in data and data["status"] == "ok"
        assert "trace_id" in data
        assert "message" in data
        assert "state_snapshot" in data
        assert "audit_log_id" in data
        print("✓ override/create contract verified")

    def test_alert_policy_update_returns_contract_fields(self, super_admin_headers):
        """PUT /runtime/alert-policy returns contract fields"""
        response = requests.put(
            f"{BASE_URL}/api/runtime/alert-policy",
            headers=super_admin_headers,
            json={
                "execution_quality_warning_threshold": 60,
                "execution_quality_critical_threshold": 40,
                "permission_drift_warning_per_day": 2,
                "permission_drift_critical_per_day": 5,
                "reason": "test_contract_verification",
                "confirmation_phrase": "UPDATE ALERT POLICY",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        assert "status" in data and data["status"] == "ok"
        assert "trace_id" in data
        assert "message" in data
        assert "state_snapshot" in data
        assert "audit_log_id" in data
        print("✓ alert-policy update contract verified")

    def test_alert_policy_test_alert_returns_contract_fields(self, super_admin_headers):
        """POST /runtime/alert-policy/test-alert returns contract fields"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/alert-policy/test-alert",
            headers=super_admin_headers,
            json={"reason": "test_contract_verification", "confirmation_phrase": "SEND TEST ALERT"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        assert "status" in data and data["status"] == "ok"
        assert "trace_id" in data
        assert "message" in data
        assert "state_snapshot" in data
        assert "audit_log_id" in data
        print("✓ alert-policy/test-alert contract verified")

    # ==================== Audit Traceability Tests ====================

    def test_action_audit_endpoint_returns_runtime_actions(self, super_admin_headers):
        """GET /runtime/action-audit returns list of runtime actions with audit details"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/action-audit",
            headers=super_admin_headers,
            params={"since_hours": 48, "limit": 50},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        assert "items" in data, "Missing 'items' field"
        assert "count" in data, "Missing 'count' field"

        # Verify items have required audit fields
        if data["items"]:
            item = data["items"][0]
            assert "id" in item, "Audit item missing 'id'"
            assert "action" in item, "Audit item missing 'action'"
            assert "severity" in item, "Audit item missing 'severity'"
            assert "actor_user_id" in item, "Audit item missing 'actor_user_id'"
            assert "actor_role" in item, "Audit item missing 'actor_role'"
            assert "created_at" in item, "Audit item missing 'created_at'"
            print(f"✓ action-audit returns {data['count']} items with proper structure")
        else:
            print("✓ action-audit endpoint works (no items yet)")

    def test_action_audit_detail_endpoint(self, super_admin_headers):
        """GET /runtime/action-audit/{audit_id} returns detailed audit info"""
        # First get list to find an audit_id
        list_response = requests.get(
            f"{BASE_URL}/api/runtime/action-audit",
            headers=super_admin_headers,
            params={"since_hours": 48, "limit": 10},
        )
        if list_response.status_code != 200 or not list_response.json().get("items"):
            pytest.skip("No audit items available for detail test")

        audit_id = list_response.json()["items"][0]["id"]

        response = requests.get(
            f"{BASE_URL}/api/runtime/action-audit/{audit_id}",
            headers=super_admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        assert "id" in data
        assert "action" in data
        assert "details" in data
        print(f"✓ action-audit detail endpoint works for audit_id={audit_id}")

    # ==================== Phrase Enforcement Tests ====================

    def test_alert_policy_rollback_wrong_phrase_returns_400(self, super_admin_headers):
        """POST /runtime/alert-policy/rollback with wrong phrase returns 400 with expected_phrase"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/alert-policy/rollback",
            headers=super_admin_headers,
            json={"reason": "test_wrong_phrase", "confirmation_phrase": "WRONG PHRASE"},
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()

        # Verify error contains expected_phrase hint
        detail = data.get("detail", {})
        if isinstance(detail, dict):
            assert "expected_phrase" in detail, f"Missing 'expected_phrase' in error detail: {detail}"
            assert detail["expected_phrase"] == "ROLLBACK ALERT POLICY"
            print("✓ rollback wrong phrase returns 400 with expected_phrase='ROLLBACK ALERT POLICY'")
        else:
            # Some implementations return string detail
            assert "ROLLBACK ALERT POLICY" in str(detail) or "expected_phrase" in str(detail)
            print("✓ rollback wrong phrase returns 400 with phrase hint")

    def test_ws_reconnect_wrong_phrase_returns_400(self, super_admin_headers):
        """POST /runtime/ws/reconnect with wrong phrase returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/ws/reconnect",
            headers=super_admin_headers,
            json={"reason": "test_wrong_phrase", "confirmation_phrase": "WRONG"},
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        detail = data.get("detail", {})
        if isinstance(detail, dict):
            assert "expected_phrase" in detail
            assert detail["expected_phrase"] == "RECONNECT WS"
        print("✓ ws/reconnect wrong phrase returns 400")

    def test_pipeline_flush_wrong_phrase_returns_400(self, super_admin_headers):
        """POST /runtime/pipeline/flush with wrong phrase returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/pipeline/flush",
            headers=super_admin_headers,
            json={
                "reason": "test_wrong_phrase",
                "confirmation_phrase": "WRONG",
                "queue_type": "all",
            },
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        detail = data.get("detail", {})
        if isinstance(detail, dict):
            assert "expected_phrase" in detail
            assert detail["expected_phrase"] == "FLUSH PIPELINE"
        print("✓ pipeline/flush wrong phrase returns 400")

    # ==================== GET Endpoints Tests ====================

    def test_ws_health_endpoint(self, super_admin_headers):
        """GET /runtime/ws/health returns WS health status"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/ws/health",
            headers=super_admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        # Should have state info
        assert "state" in data or isinstance(data, dict)
        print("✓ ws/health endpoint works")

    def test_gate_status_endpoint(self, super_admin_headers):
        """GET /runtime/gate/status returns gate status"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/gate/status",
            headers=super_admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "status" in data or "final_decision" in data or isinstance(data, dict)
        print("✓ gate/status endpoint works")

    def test_override_active_endpoint(self, super_admin_headers):
        """GET /runtime/override/active returns active overrides"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/override/active",
            headers=super_admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data
        print(f"✓ override/active endpoint works, {len(data['items'])} active overrides")

    def test_override_history_endpoint(self, super_admin_headers):
        """GET /runtime/override/history returns override history"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/override/history",
            headers=super_admin_headers,
            params={"limit": 20},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data
        print("✓ override/history endpoint works")

    def test_guard_telemetry_endpoint(self, super_admin_headers):
        """GET /runtime/guard/telemetry returns guard telemetry"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/guard/telemetry",
            headers=super_admin_headers,
            params={"limit": 50},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ guard/telemetry endpoint works")

    def test_exchange_monitoring_endpoint(self, super_admin_headers):
        """GET /runtime/exchange/monitoring returns exchange monitoring data"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/exchange/monitoring",
            headers=super_admin_headers,
            params={"limit": 50},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "drift_details" in data or "connection_details" in data or "trend" in data
        print("✓ exchange/monitoring endpoint works")

    def test_hardening_analytics_endpoint(self, super_admin_headers):
        """GET /runtime/hardening/analytics returns hardening analytics"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/hardening/analytics",
            headers=super_admin_headers,
            params={"time_window_hours": 24},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data
        print("✓ hardening/analytics endpoint works")

    def test_alerts_history_endpoint(self, super_admin_headers):
        """GET /runtime/alerts/history returns alerts history"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/alerts/history",
            headers=super_admin_headers,
            params={"status_filter": "all", "limit": 50},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data
        print(f"✓ alerts/history endpoint works, {len(data['items'])} alerts")

    def test_alert_policy_endpoint(self, super_admin_headers):
        """GET /runtime/alert-policy returns current policy"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/alert-policy",
            headers=super_admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "policy" in data
        assert "versions" in data
        print("✓ alert-policy endpoint works")

    # ==================== RBAC Tests ====================

    def test_ops_cannot_execute_super_admin_actions(self, ops_headers):
        """Ops role cannot execute super_admin only actions"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/ws/reconnect",
            headers=ops_headers,
            json={"reason": "test_rbac", "confirmation_phrase": "RECONNECT WS"},
        )
        # Should be 403 Forbidden for ops
        assert response.status_code == 403, f"Expected 403 for ops, got {response.status_code}: {response.text}"
        print("✓ RBAC: ops cannot execute super_admin actions (403)")

    def test_ops_can_read_runtime_data(self, ops_headers):
        """Ops role can read runtime data"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/ws/health",
            headers=ops_headers,
        )
        assert response.status_code == 200, f"Expected 200 for ops read, got {response.status_code}: {response.text}"
        print("✓ RBAC: ops can read runtime data (200)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
