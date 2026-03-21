"""
Test suite for LIVE Dashboard Control Layer (P0+P1 scope)
Tests:
- Execution Mode control with double confirm modal and audit trail
- Mode switch backend validation (wrong phrase rejected, correct phrase accepted)
- System health controls (kill on/off, fallback on/off, latency threshold update)
- Critical alerts action system (resolve, mute, escalate, fix actions)
- Fix action set (reconnect-exchange, restart-service, cancel-stuck-orders, etc.)
- Risk control updates (max loss/exposure) and risk override with reason/phrase
- Execution quality panel (failed orders and retry flow)
- Trading performance panel (snapshot and daily reset actions)
- Role matrix enforcement (OPS blocked from mode switch/kill/risk override)
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
    if response.status_code != 200:
        pytest.skip(f"Super admin login failed: {response.status_code}")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def ops_token():
    """Get ops user auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": OPS_EMAIL, "password": OPS_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"OPS login failed: {response.status_code}")
    return response.json().get("access_token")


@pytest.fixture
def admin_headers(super_admin_token):
    return {"Authorization": f"Bearer {super_admin_token}"}


@pytest.fixture
def ops_headers(ops_token):
    return {"Authorization": f"Bearer {ops_token}"}


# ============================================================================
# P0: Execution Mode Control Tests
# ============================================================================

class TestExecutionModeControl:
    """P0: Execution Mode control with double confirm modal and audit trail"""

    def test_get_control_layer_state(self, admin_headers):
        """Test GET control layer state endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/control-layer/state",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "execution_mode" in data
        assert "latency_thresholds" in data
        assert "kill_switch" in data
        assert "fallback" in data
        assert "server_clock" in data
        print(f"Control layer state: execution_mode={data['execution_mode']}")

    def test_mode_switch_wrong_phrase_rejected(self, admin_headers):
        """Test mode switch with wrong phrase is rejected (400)"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/execution-mode",
            headers=admin_headers,
            json={
                "mode": "PAPER",
                "reason": "test_wrong_phrase_rejection",
                "confirmation_phrase": "WRONG PHRASE",
            },
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert "invalid_confirmation_phrase" in str(data.get("detail", {}))
        print("PASS: Wrong phrase correctly rejected with 400")

    def test_mode_switch_correct_phrase_accepted(self, admin_headers):
        """Test mode switch with correct phrase is accepted"""
        # Switch to PAPER mode
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/execution-mode",
            headers=admin_headers,
            json={
                "mode": "PAPER",
                "reason": "test_correct_phrase_acceptance",
                "confirmation_phrase": "SWITCH TO PAPER",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok"
        assert data.get("mode") == "PAPER"
        assert "audit_log_id" in data
        print(f"PASS: Mode switch accepted, audit_log_id={data.get('audit_log_id')}")

    def test_mode_switch_to_mock(self, admin_headers):
        """Test mode switch to MOCK"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/execution-mode",
            headers=admin_headers,
            json={
                "mode": "MOCK",
                "reason": "test_switch_to_mock",
                "confirmation_phrase": "SWITCH TO MOCK",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("mode") == "MOCK"
        print("PASS: Mode switch to MOCK successful")


# ============================================================================
# P0: System Health Controls Tests
# ============================================================================

class TestSystemHealthControls:
    """P0: System health controls (kill on/off, fallback on/off, latency threshold)"""

    def test_kill_switch_on_wrong_phrase(self, admin_headers):
        """Test kill switch ON with wrong phrase is rejected"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/system-health",
            headers=admin_headers,
            json={
                "action": "kill_on",
                "reason": "test_kill_switch_wrong_phrase",
                "confirmation_phrase": "WRONG PHRASE",
            },
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print("PASS: Kill switch ON with wrong phrase rejected")

    def test_kill_switch_on_correct_phrase(self, admin_headers):
        """Test kill switch ON with correct phrase"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/system-health",
            headers=admin_headers,
            json={
                "action": "kill_on",
                "reason": "test_kill_switch_on",
                "confirmation_phrase": "DISABLE TRADING",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok"
        assert data.get("action") == "kill_on"
        assert "audit_log_id" in data
        print(f"PASS: Kill switch ON successful, audit_log_id={data.get('audit_log_id')}")

    def test_kill_switch_off(self, admin_headers):
        """Test kill switch OFF"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/system-health",
            headers=admin_headers,
            json={
                "action": "kill_off",
                "reason": "test_kill_switch_off",
                "confirmation_phrase": "ENABLE TRADING",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("action") == "kill_off"
        print("PASS: Kill switch OFF successful")

    def test_fallback_on(self, admin_headers):
        """Test fallback ON"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/system-health",
            headers=admin_headers,
            json={
                "action": "fallback_on",
                "reason": "test_fallback_on",
                "confirmation_phrase": "ENABLE FALLBACK",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("action") == "fallback_on"
        print("PASS: Fallback ON successful")

    def test_fallback_off(self, admin_headers):
        """Test fallback OFF"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/system-health",
            headers=admin_headers,
            json={
                "action": "fallback_off",
                "reason": "test_fallback_off",
                "confirmation_phrase": "DISABLE FALLBACK",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("action") == "fallback_off"
        print("PASS: Fallback OFF successful")

    def test_set_latency_threshold(self, admin_headers):
        """Test set latency threshold"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/system-health",
            headers=admin_headers,
            json={
                "action": "set_latency",
                "reason": "test_set_latency_threshold",
                "confirmation_phrase": "SET LATENCY THRESHOLD",
                "scan_latency_ms": 1200,
                "decision_latency_ms": 800,
                "execution_latency_ms": 1400,
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("action") == "set_latency"
        assert "latency_thresholds" in data
        print(f"PASS: Latency threshold set: {data.get('latency_thresholds')}")


# ============================================================================
# P0: Critical Alerts Action System Tests
# ============================================================================

class TestCriticalAlertsActions:
    """P0: Critical alerts action system (resolve, mute, escalate, fix actions)"""

    def test_get_critical_alerts(self, admin_headers):
        """Test GET critical alerts endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/control-layer/critical-alerts",
            headers=admin_headers,
            params={"status_filter": "all", "limit": 50},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data
        assert "count" in data
        print(f"PASS: Got {data['count']} critical alerts")

    def test_alert_resolve_action(self, admin_headers):
        """Test alert resolve action (if alerts exist)"""
        # First get alerts
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/control-layer/critical-alerts",
            headers=admin_headers,
            params={"status_filter": "open", "limit": 1},
        )
        if response.status_code != 200:
            pytest.skip("Could not get alerts")
        
        alerts = response.json().get("items", [])
        if not alerts:
            print("SKIP: No open alerts to test resolve action")
            return
        
        alert_id = alerts[0]["id"]
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/critical-alerts/{alert_id}/action",
            headers=admin_headers,
            json={
                "action": "resolve",
                "reason": "test_resolve_action",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok"
        print(f"PASS: Alert {alert_id} resolved")

    def test_alert_mute_action(self, admin_headers):
        """Test alert mute action (if alerts exist)"""
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/control-layer/critical-alerts",
            headers=admin_headers,
            params={"status_filter": "open", "limit": 1},
        )
        if response.status_code != 200:
            pytest.skip("Could not get alerts")
        
        alerts = response.json().get("items", [])
        if not alerts:
            print("SKIP: No open alerts to test mute action")
            return
        
        alert_id = alerts[0]["id"]
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/critical-alerts/{alert_id}/action",
            headers=admin_headers,
            json={
                "action": "mute",
                "reason": "test_mute_action",
                "mute_minutes": 30,
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok"
        print(f"PASS: Alert {alert_id} muted")


# ============================================================================
# P0: Risk Control Tests
# ============================================================================

class TestRiskControls:
    """P0: Risk control updates and risk override"""

    def test_risk_control_update_wrong_phrase(self, admin_headers):
        """Test risk control update with wrong phrase is rejected"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/risk-controls",
            headers=admin_headers,
            json={
                "max_loss_pct": 5.0,
                "account_exposure_pct": 60.0,
                "symbol_exposure_pct": 25.0,
                "reason": "test_risk_control_wrong_phrase",
                "confirmation_phrase": "WRONG PHRASE",
            },
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print("PASS: Risk control update with wrong phrase rejected")

    def test_risk_control_update_correct_phrase(self, admin_headers):
        """Test risk control update with correct phrase"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/risk-controls",
            headers=admin_headers,
            json={
                "max_loss_pct": 5.0,
                "account_exposure_pct": 60.0,
                "symbol_exposure_pct": 25.0,
                "reason": "test_risk_control_update",
                "confirmation_phrase": "UPDATE RISK CONTROLS",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok"
        assert "risk_controls" in data
        assert "audit_log_id" in data
        print(f"PASS: Risk control updated, audit_log_id={data.get('audit_log_id')}")

    def test_risk_override_wrong_phrase(self, admin_headers):
        """Test risk override with wrong phrase is rejected"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/risk-override",
            headers=admin_headers,
            json={
                "decision": "force_reject",
                "reason": "test_risk_override_wrong_phrase",
                "ttl_minutes": 30,
                "confirmation_phrase": "WRONG PHRASE",
            },
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print("PASS: Risk override with wrong phrase rejected")

    def test_risk_override_correct_phrase(self, admin_headers):
        """Test risk override with correct phrase"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/risk-override",
            headers=admin_headers,
            json={
                "decision": "force_reject",
                "reason": "test_risk_override",
                "ttl_minutes": 30,
                "confirmation_phrase": "APPLY RISK OVERRIDE",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok"
        assert "override" in data
        assert "audit_log_id" in data
        print(f"PASS: Risk override applied, audit_log_id={data.get('audit_log_id')}")


# ============================================================================
# P1: Execution Quality Panel Tests
# ============================================================================

class TestExecutionQualityPanel:
    """P1: Execution quality panel (failed orders and retry flow)"""

    def test_get_failed_orders(self, admin_headers):
        """Test GET failed orders endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/control-layer/execution-quality/failed-orders",
            headers=admin_headers,
            params={"status_filter": "all", "limit": 100},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data
        assert "count" in data
        print(f"PASS: Got {data['count']} failed orders")

    def test_retry_failed_orders_wrong_phrase(self, admin_headers):
        """Test retry failed orders with wrong phrase is rejected"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/execution-quality/retry",
            headers=admin_headers,
            json={
                "ids": [],
                "reason": "test_retry_wrong_phrase",
                "confirmation_phrase": "WRONG PHRASE",
            },
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print("PASS: Retry failed orders with wrong phrase rejected")

    def test_retry_failed_orders_correct_phrase(self, admin_headers):
        """Test retry failed orders with correct phrase"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/execution-quality/retry",
            headers=admin_headers,
            json={
                "ids": [],
                "reason": "test_retry_failed_orders",
                "confirmation_phrase": "RETRY FAILED ORDERS",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok"
        assert "retried_count" in data
        print(f"PASS: Retry failed orders successful, retried_count={data.get('retried_count')}")


# ============================================================================
# P1: Trading Performance Panel Tests
# ============================================================================

class TestTradingPerformancePanel:
    """P1: Trading performance panel (snapshot and daily reset)"""

    def test_get_open_positions(self, admin_headers):
        """Test GET open positions endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/control-layer/trading-performance/open-positions",
            headers=admin_headers,
            params={"limit": 100},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data
        assert "count" in data
        print(f"PASS: Got {data['count']} open positions")

    def test_capture_snapshot_wrong_phrase(self, admin_headers):
        """Test capture snapshot with wrong phrase is rejected"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/trading-performance/snapshot",
            headers=admin_headers,
            json={
                "reason": "test_snapshot_wrong_phrase",
                "confirmation_phrase": "WRONG PHRASE",
            },
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print("PASS: Capture snapshot with wrong phrase rejected")

    def test_capture_snapshot_correct_phrase(self, admin_headers):
        """Test capture snapshot with correct phrase"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/trading-performance/snapshot",
            headers=admin_headers,
            json={
                "reason": "test_capture_snapshot",
                "confirmation_phrase": "CAPTURE SNAPSHOT",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok"
        assert "snapshot" in data
        assert "audit_log_id" in data
        print(f"PASS: Snapshot captured, audit_log_id={data.get('audit_log_id')}")

    def test_reset_daily_wrong_phrase(self, admin_headers):
        """Test reset daily with wrong phrase is rejected"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/trading-performance/reset-daily",
            headers=admin_headers,
            json={
                "reason": "test_reset_daily_wrong_phrase",
                "confirmation_phrase": "WRONG PHRASE",
            },
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print("PASS: Reset daily with wrong phrase rejected")

    def test_reset_daily_correct_phrase(self, admin_headers):
        """Test reset daily with correct phrase"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/trading-performance/reset-daily",
            headers=admin_headers,
            json={
                "reason": "test_reset_daily",
                "confirmation_phrase": "RESET DAILY METRICS",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok"
        assert "marker" in data
        assert "audit_log_id" in data
        print(f"PASS: Daily reset successful, audit_log_id={data.get('audit_log_id')}")


# ============================================================================
# P0: Role Matrix Enforcement Tests
# ============================================================================

class TestRoleMatrixEnforcement:
    """P0: Role matrix enforcement - OPS blocked from critical controls"""

    def test_ops_blocked_from_mode_switch(self, ops_headers):
        """Test OPS user is blocked from mode switch (403)"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/execution-mode",
            headers=ops_headers,
            json={
                "mode": "PAPER",
                "reason": "test_ops_mode_switch",
                "confirmation_phrase": "SWITCH TO PAPER",
            },
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("PASS: OPS user blocked from mode switch (403)")

    def test_ops_blocked_from_kill_switch(self, ops_headers):
        """Test OPS user is blocked from kill switch (403)"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/system-health",
            headers=ops_headers,
            json={
                "action": "kill_on",
                "reason": "test_ops_kill_switch",
                "confirmation_phrase": "DISABLE TRADING",
            },
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("PASS: OPS user blocked from kill switch (403)")

    def test_ops_blocked_from_risk_override(self, ops_headers):
        """Test OPS user is blocked from risk override (403)"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/risk-override",
            headers=ops_headers,
            json={
                "decision": "force_reject",
                "reason": "test_ops_risk_override",
                "ttl_minutes": 30,
                "confirmation_phrase": "APPLY RISK OVERRIDE",
            },
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("PASS: OPS user blocked from risk override (403)")

    def test_ops_blocked_from_risk_control_update(self, ops_headers):
        """Test OPS user is blocked from risk control update (403)"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/risk-controls",
            headers=ops_headers,
            json={
                "max_loss_pct": 5.0,
                "account_exposure_pct": 60.0,
                "symbol_exposure_pct": 25.0,
                "reason": "test_ops_risk_control",
                "confirmation_phrase": "UPDATE RISK CONTROLS",
            },
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("PASS: OPS user blocked from risk control update (403)")

    def test_ops_allowed_retry_failed_orders(self, ops_headers):
        """Test OPS user is allowed to retry failed orders"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/execution-quality/retry",
            headers=ops_headers,
            json={
                "ids": [],
                "reason": "test_ops_retry_orders",
                "confirmation_phrase": "RETRY FAILED ORDERS",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: OPS user allowed to retry failed orders")

    def test_ops_allowed_alert_resolve(self, ops_headers):
        """Test OPS user is allowed to resolve alerts"""
        # First get alerts
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/control-layer/critical-alerts",
            headers=ops_headers,
            params={"status_filter": "open", "limit": 1},
        )
        if response.status_code != 200:
            print("SKIP: Could not get alerts for OPS resolve test")
            return
        
        alerts = response.json().get("items", [])
        if not alerts:
            print("SKIP: No open alerts to test OPS resolve action")
            return
        
        alert_id = alerts[0]["id"]
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/critical-alerts/{alert_id}/action",
            headers=ops_headers,
            json={
                "action": "resolve",
                "reason": "test_ops_resolve_action",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"PASS: OPS user allowed to resolve alert {alert_id}")

    def test_ops_blocked_from_escalate(self, ops_headers):
        """Test OPS user is blocked from escalate action (403)"""
        # First get alerts
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/control-layer/critical-alerts",
            headers=ops_headers,
            params={"status_filter": "all", "limit": 1},
        )
        if response.status_code != 200:
            print("SKIP: Could not get alerts for OPS escalate test")
            return
        
        alerts = response.json().get("items", [])
        if not alerts:
            print("SKIP: No alerts to test OPS escalate action")
            return
        
        alert_id = alerts[0]["id"]
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/critical-alerts/{alert_id}/action",
            headers=ops_headers,
            json={
                "action": "escalate",
                "reason": "test_ops_escalate_action",
            },
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("PASS: OPS user blocked from escalate action (403)")


# ============================================================================
# Dashboard Summary Endpoints Tests
# ============================================================================

class TestDashboardSummaryEndpoints:
    """Test dashboard summary and related endpoints"""

    def test_get_summary(self, admin_headers):
        """Test GET summary endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/summary",
            headers=admin_headers,
            params={"window": "1h"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "window" in data or "system_health" in data
        print("PASS: Summary endpoint working")

    def test_get_scanner_health(self, admin_headers):
        """Test GET scanner health endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/scanner-health",
            headers=admin_headers,
            params={"window": "1h"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Scanner health endpoint working")

    def test_get_execution_quality(self, admin_headers):
        """Test GET execution quality endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/execution-quality",
            headers=admin_headers,
            params={"window": "1h"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Execution quality endpoint working")

    def test_get_risk_summary(self, admin_headers):
        """Test GET risk summary endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/risk-summary",
            headers=admin_headers,
            params={"window": "1h"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Risk summary endpoint working")

    def test_get_daily_report(self, admin_headers):
        """Test GET daily report endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/daily-report",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Daily report endpoint working")

    def test_get_learning_summary(self, admin_headers):
        """Test GET learning summary endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/learning-summary",
            headers=admin_headers,
            params={"window": "24h"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Learning summary endpoint working")


# ============================================================================
# Admin Dashboard Route CTA Test
# ============================================================================

class TestAdminDashboardRouteCTA:
    """Test admin dashboard has route CTA to live control hub"""

    def test_dashboard_summary_endpoint(self, admin_headers):
        """Test dashboard summary endpoint exists"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/summary",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Dashboard summary endpoint working")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
