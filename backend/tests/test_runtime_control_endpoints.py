"""
Runtime Control & Recovery Layer API Tests
Tests for /api/runtime/* endpoints including:
- WS control (reconnect, force-new-session)
- Pipeline control (resync, flush)
- Release gate runtime recheck
- Override lifecycle (create, list, cancel, history)
- Guard telemetry
- Heartbeat/service controls
- Exchange monitoring
- Alert history actions
- Alert policy controls
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


@pytest.fixture(scope="module")
def super_admin_token():
    """Get super_admin auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Super admin login failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def ops_token():
    """Get ops auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": OPS_EMAIL, "password": OPS_PASSWORD},
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Ops login failed: {response.status_code} - {response.text}")


@pytest.fixture
def super_admin_headers(super_admin_token):
    return {"Authorization": f"Bearer {super_admin_token}", "Content-Type": "application/json"}


@pytest.fixture
def ops_headers(ops_token):
    return {"Authorization": f"Bearer {ops_token}", "Content-Type": "application/json"}


class TestRuntimeWSControl:
    """WS control endpoints - require super_admin + confirmation phrase"""

    def test_ws_health_accessible(self, super_admin_headers):
        """GET /runtime/ws/health should return WS state"""
        response = requests.get(f"{BASE_URL}/api/runtime/ws/health", headers=super_admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "state" in data
        assert "connection_logs" in data
        assert "multi_connection_state" in data
        print(f"WS health: state={data.get('state')}")

    def test_ws_reconnect_requires_super_admin(self, ops_headers):
        """POST /runtime/ws/reconnect should reject non-super_admin"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/ws/reconnect",
            headers=ops_headers,
            json={"reason": "test_reconnect", "confirmation_phrase": "RECONNECT WS"},
        )
        assert response.status_code == 403
        print(f"WS reconnect RBAC check passed: {response.status_code}")

    def test_ws_reconnect_requires_correct_phrase(self, super_admin_headers):
        """POST /runtime/ws/reconnect should reject wrong phrase"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/ws/reconnect",
            headers=super_admin_headers,
            json={"reason": "test_reconnect", "confirmation_phrase": "WRONG PHRASE"},
        )
        assert response.status_code == 400
        data = response.json()
        assert "expected_phrase" in str(data.get("detail", {}))
        print(f"WS reconnect phrase check passed: {response.status_code}")

    def test_ws_reconnect_success(self, super_admin_headers):
        """POST /runtime/ws/reconnect with correct phrase should succeed"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/ws/reconnect",
            headers=super_admin_headers,
            json={"reason": "test_reconnect_from_pytest", "confirmation_phrase": "RECONNECT WS"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        assert "trace_id" in data
        assert "audit_log_id" in data
        print(f"WS reconnect success: trace_id={data.get('trace_id')}")

    def test_ws_force_new_session_requires_super_admin(self, ops_headers):
        """POST /runtime/ws/force-new-session should reject non-super_admin"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/ws/force-new-session",
            headers=ops_headers,
            json={"reason": "test_new_session", "confirmation_phrase": "FORCE NEW WS SESSION"},
        )
        assert response.status_code == 403
        print(f"WS force-new-session RBAC check passed: {response.status_code}")

    def test_ws_force_new_session_success(self, super_admin_headers):
        """POST /runtime/ws/force-new-session with correct phrase should succeed"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/ws/force-new-session",
            headers=super_admin_headers,
            json={"reason": "test_force_new_session_from_pytest", "confirmation_phrase": "FORCE NEW WS SESSION"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        assert "trace_id" in data
        assert "audit_log_id" in data
        print(f"WS force-new-session success: trace_id={data.get('trace_id')}")


class TestRuntimePipelineControl:
    """Pipeline control endpoints - require super_admin + confirmation phrase"""

    def test_pipeline_resync_requires_super_admin(self, ops_headers):
        """POST /runtime/pipeline/resync should reject non-super_admin"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/pipeline/resync",
            headers=ops_headers,
            json={"reason": "test_resync", "confirmation_phrase": "FORCE PIPELINE RESYNC"},
        )
        assert response.status_code == 403
        print(f"Pipeline resync RBAC check passed: {response.status_code}")

    def test_pipeline_resync_success(self, super_admin_headers):
        """POST /runtime/pipeline/resync with correct phrase should succeed"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/pipeline/resync",
            headers=super_admin_headers,
            json={"reason": "test_resync_from_pytest", "confirmation_phrase": "FORCE PIPELINE RESYNC"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        assert "trace_id" in data
        assert "audit_log_id" in data
        print(f"Pipeline resync success: trace_id={data.get('trace_id')}")

    def test_pipeline_flush_requires_super_admin(self, ops_headers):
        """POST /runtime/pipeline/flush should reject non-super_admin"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/pipeline/flush",
            headers=ops_headers,
            json={"reason": "test_flush", "confirmation_phrase": "FLUSH PIPELINE", "queue_type": "all"},
        )
        assert response.status_code == 403
        print(f"Pipeline flush RBAC check passed: {response.status_code}")

    def test_pipeline_flush_success(self, super_admin_headers):
        """POST /runtime/pipeline/flush with correct phrase should succeed"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/pipeline/flush",
            headers=super_admin_headers,
            json={"reason": "test_flush_from_pytest", "confirmation_phrase": "FLUSH PIPELINE", "queue_type": "all"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        assert "trace_id" in data
        assert "audit_log_id" in data
        print(f"Pipeline flush success: trace_id={data.get('trace_id')}")


class TestRuntimeGateControl:
    """Release gate runtime endpoints"""

    def test_gate_status_accessible(self, super_admin_headers):
        """GET /runtime/gate/status should return gate details"""
        response = requests.get(f"{BASE_URL}/api/runtime/gate/status", headers=super_admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "reason_codes" in data
        assert "reasons" in data
        print(f"Gate status: status={data.get('status')}, reason_codes={data.get('reason_codes')}")

    def test_gate_recheck_requires_super_admin(self, ops_headers):
        """POST /runtime/gate/recheck should reject non-super_admin"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/gate/recheck",
            headers=ops_headers,
            json={"reason": "test_recheck", "confirmation_phrase": "RECHECK RELEASE GATE"},
        )
        assert response.status_code == 403
        print(f"Gate recheck RBAC check passed: {response.status_code}")

    def test_gate_recheck_success(self, super_admin_headers):
        """POST /runtime/gate/recheck with correct phrase should succeed"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/gate/recheck",
            headers=super_admin_headers,
            json={"reason": "test_recheck_from_pytest", "confirmation_phrase": "RECHECK RELEASE GATE"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        assert "gate" in data
        assert "scripts" in data
        assert "trace_id" in data
        assert "audit_log_id" in data
        print(f"Gate recheck success: gate_status={data.get('gate', {}).get('status')}")


class TestRuntimeOverrideLifecycle:
    """Override lifecycle endpoints - create, list, cancel, history"""

    def test_override_active_list(self, super_admin_headers):
        """GET /runtime/override/active should return active overrides"""
        response = requests.get(f"{BASE_URL}/api/runtime/override/active", headers=super_admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "max_ttl_minutes" in data
        print(f"Active overrides: count={len(data.get('items', []))}, max_ttl={data.get('max_ttl_minutes')}")

    def test_override_history(self, super_admin_headers):
        """GET /runtime/override/history should return override history"""
        response = requests.get(f"{BASE_URL}/api/runtime/override/history", headers=super_admin_headers, params={"limit": 50})
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "count" in data
        print(f"Override history: count={data.get('count')}")

    def test_override_create_requires_super_admin(self, ops_headers):
        """POST /runtime/override/create should reject non-super_admin"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/override/create",
            headers=ops_headers,
            json={
                "override_type": "risk_override",
                "scope": "global",
                "ttl_minutes": 30,
                "reason": "test_override",
                "confirmation_phrase": "CREATE OVERRIDE",
            },
        )
        assert response.status_code == 403
        print(f"Override create RBAC check passed: {response.status_code}")

    def test_override_create_and_cancel_lifecycle(self, super_admin_headers):
        """Full override lifecycle: create -> verify -> cancel -> verify"""
        # Create override
        create_response = requests.post(
            f"{BASE_URL}/api/runtime/override/create",
            headers=super_admin_headers,
            json={
                "override_type": "test_override",
                "scope": "pytest_test",
                "ttl_minutes": 5,
                "reason": "test_override_lifecycle_from_pytest",
                "confirmation_phrase": "CREATE OVERRIDE",
            },
        )
        assert create_response.status_code == 200
        create_data = create_response.json()
        assert create_data.get("status") == "ok"
        assert "override" in create_data
        override_id = create_data["override"]["override_id"]
        print(f"Override created: id={override_id}")

        # Verify in active list
        active_response = requests.get(f"{BASE_URL}/api/runtime/override/active", headers=super_admin_headers)
        assert active_response.status_code == 200
        active_data = active_response.json()
        active_ids = [item.get("override_id") for item in active_data.get("items", [])]
        assert override_id in active_ids
        print(f"Override verified in active list")

        # Cancel override
        cancel_response = requests.post(
            f"{BASE_URL}/api/runtime/override/{override_id}/cancel",
            headers=super_admin_headers,
            json={"reason": "test_cancel_from_pytest", "confirmation_phrase": "CANCEL OVERRIDE"},
        )
        assert cancel_response.status_code == 200
        cancel_data = cancel_response.json()
        assert cancel_data.get("status") == "ok"
        assert cancel_data.get("result", {}).get("cancelled") is True
        print(f"Override cancelled: id={override_id}")

        # Verify removed from active list
        active_response2 = requests.get(f"{BASE_URL}/api/runtime/override/active", headers=super_admin_headers)
        assert active_response2.status_code == 200
        active_data2 = active_response2.json()
        active_ids2 = [item.get("override_id") for item in active_data2.get("items", [])]
        assert override_id not in active_ids2
        print(f"Override verified removed from active list")

    def test_override_max_ttl_cap_enforced(self, super_admin_headers):
        """Override TTL should be validated at max_ttl_minutes (120) - API rejects values > 120"""
        # Test that exceeding max TTL is rejected by validation
        response = requests.post(
            f"{BASE_URL}/api/runtime/override/create",
            headers=super_admin_headers,
            json={
                "override_type": "test_ttl_cap",
                "scope": "pytest_ttl_test",
                "ttl_minutes": 999,  # Exceeds max - should be rejected
                "reason": "test_ttl_cap_from_pytest",
                "confirmation_phrase": "CREATE OVERRIDE",
            },
        )
        # API should reject with 422 validation error
        assert response.status_code == 422
        print(f"TTL cap enforced via validation: status={response.status_code}")

        # Test that max TTL (120) is accepted
        response2 = requests.post(
            f"{BASE_URL}/api/runtime/override/create",
            headers=super_admin_headers,
            json={
                "override_type": "test_ttl_max",
                "scope": "pytest_ttl_max_test",
                "ttl_minutes": 120,  # Max allowed
                "reason": "test_ttl_max_from_pytest",
                "confirmation_phrase": "CREATE OVERRIDE",
            },
        )
        assert response2.status_code == 200
        data = response2.json()
        override = data.get("override", {})
        assert override.get("ttl_minutes") == 120
        print(f"Max TTL accepted: ttl_minutes={override.get('ttl_minutes')}")

        # Cleanup - cancel the override
        override_id = override.get("override_id")
        if override_id:
            requests.post(
                f"{BASE_URL}/api/runtime/override/{override_id}/cancel",
                headers=super_admin_headers,
                json={"reason": "cleanup", "confirmation_phrase": "CANCEL OVERRIDE"},
            )


class TestRuntimeGuardTelemetry:
    """Guard telemetry endpoint"""

    def test_guard_telemetry_accessible(self, super_admin_headers):
        """GET /runtime/guard/telemetry should return blocked trades and reasons"""
        response = requests.get(f"{BASE_URL}/api/runtime/guard/telemetry", headers=super_admin_headers, params={"limit": 100})
        assert response.status_code == 200
        data = response.json()
        assert "blocked_trade_list" in data
        assert "top_reasons" in data
        assert "override_impacted_trades" in data
        print(f"Guard telemetry: blocked={len(data.get('blocked_trade_list', []))}, top_reasons={len(data.get('top_reasons', []))}")


class TestRuntimeHeartbeatService:
    """Heartbeat and service control endpoints"""

    def test_heartbeat_check(self, super_admin_headers):
        """POST /runtime/heartbeat/check should return health status"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/heartbeat/check",
            headers=super_admin_headers,
            json={"lag_threshold_seconds": 60},
        )
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "lag_seconds" in data
        assert "warning_triggered" in data
        print(f"Heartbeat check: status={data.get('status')}, lag={data.get('lag_seconds')}")

    def test_service_restart_requires_super_admin(self, ops_headers):
        """POST /runtime/service/restart should reject non-super_admin"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/service/restart",
            headers=ops_headers,
            json={"service": "all", "reason": "test_restart", "confirmation_phrase": "RESTART SERVICE"},
        )
        assert response.status_code == 403
        print(f"Service restart RBAC check passed: {response.status_code}")


class TestRuntimeExchangeMonitoring:
    """Exchange monitoring endpoints"""

    def test_exchange_monitoring_accessible(self, super_admin_headers):
        """GET /runtime/exchange/monitoring should return drift and connection details"""
        response = requests.get(f"{BASE_URL}/api/runtime/exchange/monitoring", headers=super_admin_headers, params={"limit": 100})
        assert response.status_code == 200
        data = response.json()
        assert "drift_details" in data
        assert "connection_details" in data
        assert "trend" in data
        print(f"Exchange monitoring: drift={len(data.get('drift_details', []))}, connections={len(data.get('connection_details', []))}")


class TestRuntimeAlertHistory:
    """Alert history and actions endpoints"""

    def test_alerts_history_accessible(self, super_admin_headers):
        """GET /runtime/alerts/history should return alert list"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/alerts/history",
            headers=super_admin_headers,
            params={"status_filter": "all", "limit": 100},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "count" in data
        print(f"Alerts history: count={data.get('count')}")


class TestRuntimeAlertPolicy:
    """Alert policy control endpoints"""

    def test_alert_policy_get(self, super_admin_headers):
        """GET /runtime/alert-policy should return current policy"""
        response = requests.get(f"{BASE_URL}/api/runtime/alert-policy", headers=super_admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "policy" in data
        assert "versions" in data
        policy = data.get("policy", {})
        assert "execution_quality_warning_threshold" in policy
        assert "execution_quality_critical_threshold" in policy
        print(f"Alert policy: warning={policy.get('execution_quality_warning_threshold')}, critical={policy.get('execution_quality_critical_threshold')}")

    def test_alert_policy_update_requires_super_admin(self, ops_headers):
        """PUT /runtime/alert-policy should reject non-super_admin"""
        response = requests.put(
            f"{BASE_URL}/api/runtime/alert-policy",
            headers=ops_headers,
            json={
                "execution_quality_warning_threshold": 60,
                "execution_quality_critical_threshold": 40,
                "permission_drift_warning_per_day": 2,
                "permission_drift_critical_per_day": 5,
                "reason": "test_update",
                "confirmation_phrase": "UPDATE ALERT POLICY",
            },
        )
        assert response.status_code == 403
        print(f"Alert policy update RBAC check passed: {response.status_code}")

    def test_alert_policy_test_alert_requires_super_admin(self, ops_headers):
        """POST /runtime/alert-policy/test-alert should reject non-super_admin"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/alert-policy/test-alert",
            headers=ops_headers,
            json={"reason": "test_alert", "confirmation_phrase": "SEND TEST ALERT"},
        )
        assert response.status_code == 403
        print(f"Test alert RBAC check passed: {response.status_code}")

    def test_alert_policy_test_alert_success(self, super_admin_headers):
        """POST /runtime/alert-policy/test-alert with correct phrase should succeed"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/alert-policy/test-alert",
            headers=super_admin_headers,
            json={"reason": "test_alert_from_pytest", "confirmation_phrase": "SEND TEST ALERT"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        assert "alert_id" in data
        assert "trace_id" in data
        print(f"Test alert created: alert_id={data.get('alert_id')}")


class TestRuntimeHardeningAnalytics:
    """Hardening analytics endpoint"""

    def test_hardening_analytics_accessible(self, super_admin_headers):
        """GET /runtime/hardening/analytics should return runtime audit events"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/hardening/analytics",
            headers=super_admin_headers,
            params={"time_window_hours": 24},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "count" in data
        print(f"Hardening analytics: count={data.get('count')}")


class TestRuntimeActionAudit:
    """Action audit endpoints"""

    def test_action_audit_list(self, super_admin_headers):
        """GET /runtime/action-audit should return audit list"""
        response = requests.get(
            f"{BASE_URL}/api/runtime/action-audit",
            headers=super_admin_headers,
            params={"since_hours": 24, "limit": 100},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "count" in data
        print(f"Action audit: count={data.get('count')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
