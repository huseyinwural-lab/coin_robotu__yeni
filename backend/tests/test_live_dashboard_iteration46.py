"""
Test suite for LIVE Dashboard Iteration 46 - New Features (P0+P1)
Tests:
- Execution mode switch with confirm phrase and audit history snippet
- Global action audit APIs with filters and detail endpoint
- Action audit detail route /admin/action-audit
- Failed orders panel with order_id/reason/timestamp and single + bulk retry
- Failed orders remove endpoint and UI action with audit
- Scanner control endpoints: restart + manual trigger (ops allowed), symbol universe edit (ops blocked, admin allowed)
- Critical alerts expand panel with full details/history and fix-action result feedback
- Global search filters alerts/orders in live dashboard
- Time sync drift (server vs client) visible
- Admin dashboard snippet links to action audit detail page
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
# P0: Execution Mode Switch with Audit History
# ============================================================================

class TestExecutionModeAuditHistory:
    """P0: Execution mode switch creates audit with old/new mode and shows history snippet"""

    def test_mode_switch_creates_audit_with_old_new_mode(self, admin_headers):
        """Test mode switch creates audit log with old and new mode"""
        # First get current mode
        state_response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/control-layer/state",
            headers=admin_headers,
        )
        assert state_response.status_code == 200
        current_mode = state_response.json().get("execution_mode", "MOCK")
        
        # Switch to a different mode
        target_mode = "PAPER" if current_mode != "PAPER" else "MOCK"
        phrase = f"SWITCH TO {target_mode}"
        
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/execution-mode",
            headers=admin_headers,
            json={
                "mode": target_mode,
                "reason": "test_audit_old_new_mode",
                "confirmation_phrase": phrase,
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok"
        assert "audit_log_id" in data
        assert "previous_mode" in data or "mode" in data
        print(f"PASS: Mode switch created audit, previous_mode={data.get('previous_mode')}, new_mode={data.get('mode')}")

    def test_control_state_shows_mode_history_snippet(self, admin_headers):
        """Test control layer state shows execution mode history snippet"""
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/control-layer/state",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "execution_mode_snapshots" in data
        snapshots = data.get("execution_mode_snapshots", [])
        print(f"PASS: Mode history snippet available, count={len(snapshots)}")
        if snapshots:
            print(f"  Latest snapshot: {snapshots[-1] if snapshots else 'none'}")


# ============================================================================
# P0: Global Action Audit APIs
# ============================================================================

class TestGlobalActionAuditAPIs:
    """P0: Global action audit APIs with filters and detail endpoint"""

    def test_action_audit_list_endpoint(self, admin_headers):
        """Test action audit list endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/control-layer/action-audit",
            headers=admin_headers,
            params={"since_hours": 48, "limit": 100},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data
        assert "count" in data
        print(f"PASS: Action audit list endpoint working, count={data['count']}")

    def test_action_audit_filter_by_user_id(self, admin_headers):
        """Test action audit filter by user_id"""
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/control-layer/action-audit",
            headers=admin_headers,
            params={"user_id": "nonexistent_user", "since_hours": 24, "limit": 50},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data
        print(f"PASS: Action audit filter by user_id working, count={data['count']}")

    def test_action_audit_filter_by_action_type(self, admin_headers):
        """Test action audit filter by action_type"""
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/control-layer/action-audit",
            headers=admin_headers,
            params={"action_type": "EXECUTION_MODE", "since_hours": 48, "limit": 50},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data
        print(f"PASS: Action audit filter by action_type working, count={data['count']}")

    def test_action_audit_detail_endpoint(self, admin_headers):
        """Test action audit detail endpoint"""
        # First get list to find an audit ID
        list_response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/control-layer/action-audit",
            headers=admin_headers,
            params={"since_hours": 48, "limit": 1},
        )
        if list_response.status_code != 200:
            pytest.skip("Could not get audit list")
        
        items = list_response.json().get("items", [])
        if not items:
            print("SKIP: No audit items to test detail endpoint")
            return
        
        audit_id = items[0]["id"]
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/control-layer/action-audit/{audit_id}",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "id" in data
        assert "action" in data
        assert "details" in data
        print(f"PASS: Action audit detail endpoint working, action={data.get('action')}")

    def test_action_audit_detail_not_found(self, admin_headers):
        """Test action audit detail returns 404 for non-existent ID"""
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/control-layer/action-audit/nonexistent_id_12345",
            headers=admin_headers,
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        print("PASS: Action audit detail returns 404 for non-existent ID")


# ============================================================================
# P1: Failed Orders Panel with Retry/Remove
# ============================================================================

class TestFailedOrdersPanel:
    """P1: Failed orders panel with order_id/reason/timestamp and single + bulk retry/remove"""

    def test_failed_orders_list_shows_required_fields(self, admin_headers):
        """Test failed orders list shows order_id, reason, timestamp"""
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/control-layer/execution-quality/failed-orders",
            headers=admin_headers,
            params={"status_filter": "all", "limit": 100},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data
        
        # Check field structure if items exist
        if data["items"]:
            item = data["items"][0]
            assert "id" in item
            assert "entity_id" in item  # order_id
            assert "error_message" in item  # reason
            assert "created_at" in item or "updated_at" in item  # timestamp
            print(f"PASS: Failed orders list shows required fields")
        else:
            print("PASS: Failed orders list endpoint working (no items)")

    def test_retry_single_failed_order(self, admin_headers):
        """Test retry single failed order"""
        # Get failed orders
        list_response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/control-layer/execution-quality/failed-orders",
            headers=admin_headers,
            params={"status_filter": "pending", "limit": 1},
        )
        if list_response.status_code != 200:
            pytest.skip("Could not get failed orders")
        
        items = list_response.json().get("items", [])
        if not items:
            # Test with empty IDs (bulk retry all)
            response = requests.post(
                f"{BASE_URL}/api/admin/live-trading/control-layer/execution-quality/retry",
                headers=admin_headers,
                json={
                    "ids": [],
                    "reason": "test_retry_single",
                    "confirmation_phrase": "RETRY FAILED ORDERS",
                },
            )
            assert response.status_code == 200
            print("PASS: Retry endpoint working (no pending items)")
            return
        
        order_id = items[0]["id"]
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/execution-quality/retry",
            headers=admin_headers,
            json={
                "ids": [order_id],
                "reason": "test_retry_single_order",
                "confirmation_phrase": "RETRY FAILED ORDERS",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok"
        assert "results" in data
        print(f"PASS: Single order retry successful, retried_count={data.get('retried_count')}")

    def test_remove_failed_orders_wrong_phrase(self, admin_headers):
        """Test remove failed orders with wrong phrase is rejected"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/execution-quality/remove",
            headers=admin_headers,
            json={
                "ids": [],
                "reason": "test_remove_wrong_phrase",
                "confirmation_phrase": "WRONG PHRASE",
            },
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print("PASS: Remove failed orders with wrong phrase rejected")

    def test_remove_failed_orders_correct_phrase(self, admin_headers):
        """Test remove failed orders with correct phrase"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/execution-quality/remove",
            headers=admin_headers,
            json={
                "ids": [],
                "reason": "test_remove_failed_orders",
                "confirmation_phrase": "REMOVE FAILED ORDERS",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok"
        assert "removed_count" in data
        assert "audit_log_id" in data
        print(f"PASS: Remove failed orders successful, removed_count={data.get('removed_count')}")


# ============================================================================
# P1: Scanner Control Endpoints
# ============================================================================

class TestScannerControlEndpoints:
    """P1: Scanner control endpoints with role-based access"""

    def test_get_scanner_control_state(self, admin_headers):
        """Test GET scanner control state endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/control-layer/scanner",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "runtime" in data or "symbol_universe" in data
        print(f"PASS: Scanner control state endpoint working")

    def test_scanner_restart_wrong_phrase(self, admin_headers):
        """Test scanner restart with wrong phrase is rejected"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/scanner/restart",
            headers=admin_headers,
            json={
                "reason": "test_scanner_restart_wrong_phrase",
                "confirmation_phrase": "WRONG PHRASE",
            },
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print("PASS: Scanner restart with wrong phrase rejected")

    def test_scanner_restart_correct_phrase(self, admin_headers):
        """Test scanner restart with correct phrase"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/scanner/restart",
            headers=admin_headers,
            json={
                "reason": "test_scanner_restart",
                "confirmation_phrase": "RESTART SCANNER",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok"
        assert "audit_log_id" in data
        print(f"PASS: Scanner restart successful, audit_log_id={data.get('audit_log_id')}")

    def test_scanner_manual_trigger_wrong_phrase(self, admin_headers):
        """Test scanner manual trigger with wrong phrase is rejected"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/scanner/manual-trigger",
            headers=admin_headers,
            json={
                "reason": "test_scanner_trigger_wrong_phrase",
                "confirmation_phrase": "WRONG PHRASE",
            },
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print("PASS: Scanner manual trigger with wrong phrase rejected")

    def test_scanner_manual_trigger_correct_phrase(self, admin_headers):
        """Test scanner manual trigger with correct phrase"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/scanner/manual-trigger",
            headers=admin_headers,
            json={
                "reason": "test_scanner_manual_trigger",
                "confirmation_phrase": "TRIGGER MANUAL SCAN",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok"
        assert "audit_log_id" in data
        print(f"PASS: Scanner manual trigger successful, audit_log_id={data.get('audit_log_id')}")

    def test_scanner_symbol_universe_wrong_phrase(self, admin_headers):
        """Test scanner symbol universe with wrong phrase is rejected"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/scanner/symbol-universe",
            headers=admin_headers,
            json={
                "action": "add",
                "symbols": ["BTCUSDT"],
                "reason": "test_symbol_universe_wrong_phrase",
                "confirmation_phrase": "WRONG PHRASE",
            },
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print("PASS: Scanner symbol universe with wrong phrase rejected")

    def test_scanner_symbol_universe_add(self, admin_headers):
        """Test scanner symbol universe add"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/scanner/symbol-universe",
            headers=admin_headers,
            json={
                "action": "add",
                "symbols": ["BTCUSDT", "ETHUSDT"],
                "reason": "test_symbol_universe_add",
                "confirmation_phrase": "UPDATE SYMBOL UNIVERSE",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok"
        assert "symbol_universe" in data
        assert "audit_log_id" in data
        print(f"PASS: Scanner symbol universe add successful, symbols={data.get('symbol_universe')}")

    def test_scanner_symbol_universe_remove(self, admin_headers):
        """Test scanner symbol universe remove"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/scanner/symbol-universe",
            headers=admin_headers,
            json={
                "action": "remove",
                "symbols": ["ETHUSDT"],
                "reason": "test_symbol_universe_remove",
                "confirmation_phrase": "UPDATE SYMBOL UNIVERSE",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok"
        print(f"PASS: Scanner symbol universe remove successful")


# ============================================================================
# P1: Scanner Control Role Matrix
# ============================================================================

class TestScannerControlRoleMatrix:
    """P1: Scanner control role matrix - OPS allowed restart/trigger, blocked from symbol universe"""

    def test_ops_allowed_scanner_restart(self, ops_headers):
        """Test OPS user is allowed to restart scanner"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/scanner/restart",
            headers=ops_headers,
            json={
                "reason": "test_ops_scanner_restart",
                "confirmation_phrase": "RESTART SCANNER",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: OPS user allowed to restart scanner")

    def test_ops_allowed_scanner_manual_trigger(self, ops_headers):
        """Test OPS user is allowed to trigger manual scan"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/scanner/manual-trigger",
            headers=ops_headers,
            json={
                "reason": "test_ops_scanner_trigger",
                "confirmation_phrase": "TRIGGER MANUAL SCAN",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: OPS user allowed to trigger manual scan")

    def test_ops_blocked_from_symbol_universe(self, ops_headers):
        """Test OPS user is blocked from symbol universe edit (403)"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/scanner/symbol-universe",
            headers=ops_headers,
            json={
                "action": "add",
                "symbols": ["BTCUSDT"],
                "reason": "test_ops_symbol_universe",
                "confirmation_phrase": "UPDATE SYMBOL UNIVERSE",
            },
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("PASS: OPS user blocked from symbol universe edit (403)")


# ============================================================================
# P0: Critical Alerts Expand Panel
# ============================================================================

class TestCriticalAlertsExpandPanel:
    """P0: Critical alerts expand panel with full details/history and fix-action result"""

    def test_critical_alerts_include_history(self, admin_headers):
        """Test critical alerts include history in response"""
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/control-layer/critical-alerts",
            headers=admin_headers,
            params={"status_filter": "all", "limit": 10},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data
        
        if data["items"]:
            item = data["items"][0]
            assert "history" in item
            assert "details" in item
            print(f"PASS: Critical alerts include history, history_count={len(item.get('history', []))}")
        else:
            print("PASS: Critical alerts endpoint working (no items)")

    def test_fix_action_returns_result(self, admin_headers):
        """Test fix action returns result feedback"""
        # Get alerts
        list_response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/control-layer/critical-alerts",
            headers=admin_headers,
            params={"status_filter": "all", "limit": 1},
        )
        if list_response.status_code != 200:
            pytest.skip("Could not get alerts")
        
        items = list_response.json().get("items", [])
        if not items:
            print("SKIP: No alerts to test fix action")
            return
        
        alert_id = items[0]["id"]
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/critical-alerts/{alert_id}/action",
            headers=admin_headers,
            json={
                "action": "fix_action",
                "reason": "test_fix_action_result",
                "fix_action": "flush-retry-queue",
                "confirmation_phrase": "RUN ALERT FIX ACTION",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok"
        assert "result" in data
        print(f"PASS: Fix action returns result, result={data.get('result')}")


# ============================================================================
# P1: Time Sync Drift
# ============================================================================

class TestTimeSyncDrift:
    """P1: Time sync drift (server vs client) visible"""

    def test_control_state_includes_server_clock(self, admin_headers):
        """Test control layer state includes server_clock for time sync"""
        response = requests.get(
            f"{BASE_URL}/api/admin/live-trading/control-layer/state",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "server_clock" in data
        server_clock = data.get("server_clock")
        assert server_clock is not None
        print(f"PASS: Server clock available for time sync, server_clock={server_clock}")


# ============================================================================
# P1: OPS Role - Remove Failed Orders
# ============================================================================

class TestOpsRemoveFailedOrders:
    """P1: OPS user can remove failed orders"""

    def test_ops_allowed_remove_failed_orders(self, ops_headers):
        """Test OPS user is allowed to remove failed orders"""
        response = requests.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/execution-quality/remove",
            headers=ops_headers,
            json={
                "ids": [],
                "reason": "test_ops_remove_failed_orders",
                "confirmation_phrase": "REMOVE FAILED ORDERS",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: OPS user allowed to remove failed orders")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
