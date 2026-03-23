"""
Production Gate P1 Comprehensive Tests

Covers:
- GET /api/phase4/admin/production-gate/ops-overview payload correctness
- POST /api/phase4/admin/production-gate/api-key-tests/run (fail and success paths)
- GET /api/phase4/admin/production-gate/mode-history
- POST /api/phase4/admin/production-gate/order-scenarios/rerun (PASS+FAIL scenarios)
- GET /api/phase4/admin/production-gate/export/raw with scope/date filters
- 403 hard-block enforcement for LIVE mode transition when NO_GO
- 400 validation errors for invalid inputs
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def authed_session() -> requests.Session:
    """Authenticated session for super admin"""
    session = requests.Session()
    login = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
        timeout=30,
    )
    assert login.status_code == 200, f"Login failed: {login.status_code} {login.text}"
    token = login.json().get("access_token")
    assert token, "Missing access token"
    session.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return session


# ============================================================================
# OPS OVERVIEW TESTS
# ============================================================================

class TestOpsOverview:
    """Tests for GET /api/phase4/admin/production-gate/ops-overview"""

    def test_ops_overview_returns_200(self, authed_session: requests.Session):
        """Verify ops-overview endpoint returns 200"""
        response = authed_session.get(f"{BASE_URL}/api/phase4/admin/production-gate/ops-overview", timeout=30)
        assert response.status_code == 200, response.text

    def test_ops_overview_payload_structure(self, authed_session: requests.Session):
        """Verify all required fields are present in ops-overview response"""
        response = authed_session.get(f"{BASE_URL}/api/phase4/admin/production-gate/ops-overview", timeout=30)
        assert response.status_code == 200
        data = response.json()

        required_fields = [
            "active_fail_count",
            "active_fail_codes",
            "api_key_tests",
            "permission_breakdown",
            "exchange_health",
            "mode_history",
            "order_scenarios",
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

    def test_ops_overview_field_types(self, authed_session: requests.Session):
        """Verify field types in ops-overview response"""
        response = authed_session.get(f"{BASE_URL}/api/phase4/admin/production-gate/ops-overview", timeout=30)
        data = response.json()

        assert isinstance(data["active_fail_count"], int)
        assert isinstance(data["active_fail_codes"], list)
        assert isinstance(data["api_key_tests"], list)
        assert isinstance(data["permission_breakdown"], list)
        assert isinstance(data["exchange_health"], list)
        assert isinstance(data["mode_history"], list)
        assert isinstance(data["order_scenarios"], list)


# ============================================================================
# API KEY TESTS
# ============================================================================

class TestApiKeyTests:
    """Tests for POST /api/phase4/admin/production-gate/api-key-tests/run"""

    def test_api_key_test_run_returns_200(self, authed_session: requests.Session):
        """Verify api-key-tests/run endpoint returns 200"""
        response = authed_session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/api-key-tests/run",
            json={},
            timeout=60,
        )
        assert response.status_code == 200, response.text

    def test_api_key_test_run_returns_test_results(self, authed_session: requests.Session):
        """Verify api-key-tests/run returns test results with required fields"""
        response = authed_session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/api-key-tests/run",
            json={},
            timeout=60,
        )
        assert response.status_code == 200
        data = response.json()
        rows = data.get("api_key_tests") or []
        assert len(rows) >= 1, "Expected at least one api_key_tests row"

        row = rows[0]
        required_fields = [
            "exchange", "market_type", "environment", "connection_id",
            "status", "success", "response_summary", "last_tested_at"
        ]
        for field in required_fields:
            assert field in row, f"Missing API key test field: {field}"

    def test_api_key_test_status_values(self, authed_session: requests.Session):
        """Verify api-key-tests status is PASS or FAIL"""
        response = authed_session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/api-key-tests/run",
            json={},
            timeout=60,
        )
        data = response.json()
        rows = data.get("api_key_tests") or []
        for row in rows:
            assert row["status"] in {"PASS", "FAIL"}, f"Invalid status: {row['status']}"
            assert isinstance(row["success"], bool)

    def test_api_key_test_with_exchange_filter(self, authed_session: requests.Session):
        """Verify api-key-tests/run with exchange filter"""
        response = authed_session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/api-key-tests/run",
            json={"exchange": "binance"},
            timeout=60,
        )
        assert response.status_code == 200, response.text

    def test_api_key_test_runbook_ref_present(self, authed_session: requests.Session):
        """Verify runbook_ref is present for failed tests"""
        response = authed_session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/api-key-tests/run",
            json={},
            timeout=60,
        )
        data = response.json()
        rows = data.get("api_key_tests") or []
        for row in rows:
            if row["status"] == "FAIL":
                # runbook_ref should be present for failures
                assert "runbook_ref" in row, "Missing runbook_ref for failed test"


# ============================================================================
# PERMISSION BREAKDOWN TESTS
# ============================================================================

class TestPermissionBreakdown:
    """Tests for permission_breakdown in ops-overview"""

    def test_permission_breakdown_structure(self, authed_session: requests.Session):
        """Verify permission_breakdown has required fields"""
        response = authed_session.get(f"{BASE_URL}/api/phase4/admin/production-gate/ops-overview", timeout=30)
        data = response.json()
        rows = data.get("permission_breakdown") or []
        assert len(rows) >= 1, "Expected at least one permission row"

        row = rows[0]
        required_fields = ["exchange", "read_status", "write_status", "trade_status"]
        for field in required_fields:
            assert field in row, f"Missing permission field: {field}"

    def test_permission_breakdown_status_values(self, authed_session: requests.Session):
        """Verify permission status values are valid"""
        response = authed_session.get(f"{BASE_URL}/api/phase4/admin/production-gate/ops-overview", timeout=30)
        data = response.json()
        rows = data.get("permission_breakdown") or []
        
        valid_statuses = {"PASS", "FAIL", "UNKNOWN"}
        for row in rows:
            assert row["read_status"] in valid_statuses
            assert row["write_status"] in valid_statuses
            assert row["trade_status"] in valid_statuses

    def test_permission_breakdown_runbook_for_failures(self, authed_session: requests.Session):
        """Verify runbook_ref is present for permission failures"""
        response = authed_session.get(f"{BASE_URL}/api/phase4/admin/production-gate/ops-overview", timeout=30)
        data = response.json()
        rows = data.get("permission_breakdown") or []
        
        for row in rows:
            if row.get("fail_reason"):
                assert "runbook_ref" in row, "Missing runbook_ref for permission failure"


# ============================================================================
# EXCHANGE HEALTH TESTS
# ============================================================================

class TestExchangeHealth:
    """Tests for exchange_health in ops-overview"""

    def test_exchange_health_structure(self, authed_session: requests.Session):
        """Verify exchange_health has required fields"""
        response = authed_session.get(f"{BASE_URL}/api/phase4/admin/production-gate/ops-overview", timeout=30)
        data = response.json()
        rows = data.get("exchange_health") or []
        assert len(rows) >= 1, "Expected at least one exchange health row"

        row = rows[0]
        required_fields = ["exchange", "connection_status", "auth_status", "permission_status", "last_checked_at"]
        for field in required_fields:
            assert field in row, f"Missing health field: {field}"

    def test_exchange_health_status_values(self, authed_session: requests.Session):
        """Verify exchange health status values are valid"""
        response = authed_session.get(f"{BASE_URL}/api/phase4/admin/production-gate/ops-overview", timeout=30)
        data = response.json()
        rows = data.get("exchange_health") or []
        
        valid_statuses = {"PASS", "FAIL", "UNKNOWN"}
        for row in rows:
            assert row["connection_status"] in valid_statuses
            assert row["auth_status"] in valid_statuses
            assert row["permission_status"] in valid_statuses

    def test_exchange_health_remediation_for_failures(self, authed_session: requests.Session):
        """Verify remediation is present for health failures"""
        response = authed_session.get(f"{BASE_URL}/api/phase4/admin/production-gate/ops-overview", timeout=30)
        data = response.json()
        rows = data.get("exchange_health") or []
        
        for row in rows:
            if row.get("fail_reason"):
                assert "remediation" in row, "Missing remediation for health failure"
                assert "runbook_ref" in row, "Missing runbook_ref for health failure"


# ============================================================================
# MODE HISTORY TESTS
# ============================================================================

class TestModeHistory:
    """Tests for GET /api/phase4/admin/production-gate/mode-history"""

    def test_mode_history_returns_200(self, authed_session: requests.Session):
        """Verify mode-history endpoint returns 200"""
        response = authed_session.get(f"{BASE_URL}/api/phase4/admin/production-gate/mode-history?limit=20", timeout=30)
        assert response.status_code == 200, response.text

    def test_mode_history_returns_list(self, authed_session: requests.Session):
        """Verify mode-history returns a list"""
        response = authed_session.get(f"{BASE_URL}/api/phase4/admin/production-gate/mode-history?limit=20", timeout=30)
        data = response.json()
        assert isinstance(data, list)

    def test_mode_history_item_structure(self, authed_session: requests.Session):
        """Verify mode-history items have required fields"""
        response = authed_session.get(f"{BASE_URL}/api/phase4/admin/production-gate/mode-history?limit=20", timeout=30)
        rows = response.json()
        
        if len(rows) > 0:
            row = rows[0]
            required_fields = ["changed_at", "actor_role", "from_mode", "to_mode"]
            for field in required_fields:
                assert field in row, f"Missing mode history field: {field}"

    def test_mode_history_limit_parameter(self, authed_session: requests.Session):
        """Verify mode-history respects limit parameter"""
        response = authed_session.get(f"{BASE_URL}/api/phase4/admin/production-gate/mode-history?limit=5", timeout=30)
        rows = response.json()
        assert len(rows) <= 5


# ============================================================================
# ORDER SCENARIO MATRIX TESTS
# ============================================================================

class TestOrderScenarioMatrix:
    """Tests for POST /api/phase4/admin/production-gate/order-scenarios/rerun"""

    def test_order_scenarios_rerun_returns_200(self, authed_session: requests.Session):
        """Verify order-scenarios/rerun endpoint returns 200"""
        response = authed_session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/order-scenarios/rerun",
            json={},
            timeout=60,
        )
        assert response.status_code == 200, response.text

    def test_order_scenarios_returns_full_matrix(self, authed_session: requests.Session):
        """Verify order-scenarios/rerun returns full scenario matrix"""
        response = authed_session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/order-scenarios/rerun",
            json={},
            timeout=60,
        )
        data = response.json()
        rows = data.get("order_scenarios") or []
        assert len(rows) >= 5, "Expected full scenario matrix (at least 5 scenarios)"

    def test_order_scenarios_contains_pass_and_fail(self, authed_session: requests.Session):
        """Verify order-scenarios contains both PASS and FAIL scenarios"""
        response = authed_session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/order-scenarios/rerun",
            json={},
            timeout=60,
        )
        data = response.json()
        rows = data.get("order_scenarios") or []
        
        statuses = {str(item.get("status") or "") for item in rows}
        assert "PASS" in statuses, "Expected at least one PASS scenario"
        assert "FAIL" in statuses, "Expected at least one FAIL scenario (invalid_zero_qty)"

    def test_order_scenario_item_structure(self, authed_session: requests.Session):
        """Verify order scenario items have required fields"""
        response = authed_session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/order-scenarios/rerun",
            json={},
            timeout=60,
        )
        data = response.json()
        rows = data.get("order_scenarios") or []
        
        for row in rows:
            required_fields = ["scenario_key", "label", "side", "size_bucket", "status", "last_run_at"]
            for field in required_fields:
                assert field in row, f"Missing order scenario field: {field}"

    def test_order_scenario_single_rerun(self, authed_session: requests.Session):
        """Verify single scenario rerun works"""
        response = authed_session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/order-scenarios/rerun",
            json={"scenario_key": "buy_small"},
            timeout=60,
        )
        assert response.status_code == 200, response.text

    def test_order_scenario_invalid_key_returns_400(self, authed_session: requests.Session):
        """Verify invalid scenario_key returns 400"""
        response = authed_session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/order-scenarios/rerun",
            json={"scenario_key": "invalid_nonexistent_scenario"},
            timeout=60,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"


# ============================================================================
# EXPORT TESTS
# ============================================================================

class TestExportRaw:
    """Tests for GET /api/phase4/admin/production-gate/export/raw"""

    def test_export_raw_returns_200(self, authed_session: requests.Session):
        """Verify export/raw endpoint returns 200"""
        response = authed_session.get(f"{BASE_URL}/api/phase4/admin/production-gate/export/raw", timeout=30)
        assert response.status_code == 200, response.text

    def test_export_raw_with_scope_full(self, authed_session: requests.Session):
        """Verify export/raw with scope=full"""
        response = authed_session.get(
            f"{BASE_URL}/api/phase4/admin/production-gate/export/raw",
            params={"scope": "full"},
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("scope") == "full"

    def test_export_raw_with_scope_summary(self, authed_session: requests.Session):
        """Verify export/raw with scope=summary"""
        response = authed_session.get(
            f"{BASE_URL}/api/phase4/admin/production-gate/export/raw",
            params={"scope": "summary"},
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("scope") == "summary"

    def test_export_raw_with_scope_audit(self, authed_session: requests.Session):
        """Verify export/raw with scope=audit"""
        response = authed_session.get(
            f"{BASE_URL}/api/phase4/admin/production-gate/export/raw",
            params={"scope": "audit"},
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("scope") == "audit"

    def test_export_raw_with_date_filters(self, authed_session: requests.Session):
        """Verify export/raw with date_from and date_to filters"""
        date_from = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        date_to = datetime.now(timezone.utc).isoformat()

        response = authed_session.get(
            f"{BASE_URL}/api/phase4/admin/production-gate/export/raw",
            params={"scope": "summary", "date_from": date_from, "date_to": date_to},
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "filters" in data
        assert data["filters"].get("date_from") is not None
        assert data["filters"].get("date_to") is not None

    def test_export_raw_payload_structure(self, authed_session: requests.Session):
        """Verify export/raw payload has required structure"""
        response = authed_session.get(f"{BASE_URL}/api/phase4/admin/production-gate/export/raw", timeout=30)
        data = response.json()
        
        required_fields = ["exported_at", "scope", "filters", "gate", "ops_summary", "export_payload"]
        for field in required_fields:
            assert field in data, f"Missing export field: {field}"

    def test_export_raw_invalid_date_format_returns_400(self, authed_session: requests.Session):
        """Verify invalid date format returns 400"""
        response = authed_session.get(
            f"{BASE_URL}/api/phase4/admin/production-gate/export/raw",
            params={"date_from": "invalid-date-format"},
            timeout=30,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"


# ============================================================================
# HARD BLOCK (403) TESTS
# ============================================================================

class TestHardBlock403:
    """Tests for 403 hard-block enforcement"""

    def test_mode_transition_to_live_blocked_when_no_go(self, authed_session: requests.Session):
        """Verify LIVE mode transition is blocked (403) when gate is NO_GO"""
        # First ensure gate is in NO_GO state
        authed_session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/state",
            json={
                "target_state": "NO_GO",
                "reason_code": "TEST_BLOCK",
                "reason_text": "Testing 403 hard-block enforcement"
            },
            timeout=30,
        )
        
        # Attempt LIVE transition - should be blocked with 403
        response = authed_session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/mode-transition",
            json={
                "target_mode": "LIVE",
                "reason_text": "Test LIVE transition",
                "confirmation_phrase": "SWITCH TO LIVE"
            },
            timeout=30,
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"

    def test_live_config_enable_blocked_when_no_go(self, authed_session: requests.Session):
        """Verify live_mode_enabled is blocked (403) when gate is NO_GO"""
        # First ensure gate is in NO_GO state
        authed_session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/state",
            json={
                "target_state": "NO_GO",
                "reason_code": "TEST_BLOCK",
                "reason_text": "Testing 403 hard-block enforcement"
            },
            timeout=30,
        )
        
        # Get current config
        config_response = authed_session.get(f"{BASE_URL}/api/phase4/live-config", timeout=30)
        if config_response.status_code != 200:
            pytest.skip("Could not get live-config")
        
        config = config_response.json()
        config["live_mode_enabled"] = True
        
        # Attempt to enable live mode - should be blocked with 403
        response = authed_session.put(
            f"{BASE_URL}/api/phase4/live-config",
            json=config,
            timeout=30,
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"


# ============================================================================
# VALIDATION (400) TESTS
# ============================================================================

class TestValidation400:
    """Tests for 400 validation errors"""

    def test_mode_transition_invalid_confirmation_phrase(self, authed_session: requests.Session):
        """Verify invalid confirmation phrase returns 400"""
        response = authed_session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/mode-transition",
            json={
                "target_mode": "PAPER",
                "reason_text": "Test transition",
                "confirmation_phrase": "WRONG PHRASE"
            },
            timeout=30,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"

    def test_state_update_missing_reason_code(self, authed_session: requests.Session):
        """Verify missing reason_code returns 400 or 422 (validation error)"""
        response = authed_session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/state",
            json={
                "target_state": "NO_GO",
                "reason_code": "",  # Empty reason code
                "reason_text": "Test reason"
            },
            timeout=30,
        )
        assert response.status_code in {400, 422}, f"Expected 400/422, got {response.status_code}"

    def test_state_update_missing_reason_text(self, authed_session: requests.Session):
        """Verify short reason_text returns 400 or 422 (validation error)"""
        response = authed_session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/state",
            json={
                "target_state": "NO_GO",
                "reason_code": "TEST",
                "reason_text": "ab"  # Too short (< 5 chars)
            },
            timeout=30,
        )
        assert response.status_code in {400, 422}, f"Expected 400/422, got {response.status_code}"

    def test_override_invalid_reason_code(self, authed_session: requests.Session):
        """Verify invalid override reason_code returns 400 or 422 (validation error)"""
        response = authed_session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/override",
            json={
                "reason_code": "INVALID_CODE",
                "reason_text": "This is a test override reason text",
                "ttl_minutes": 15
            },
            timeout=30,
        )
        assert response.status_code in {400, 422}, f"Expected 400/422, got {response.status_code}"

    def test_override_ttl_exceeds_max(self, authed_session: requests.Session):
        """Verify ttl_minutes > 30 returns 400 or 422 (validation error)"""
        response = authed_session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/override",
            json={
                "reason_code": "INCIDENT_MITIGATION",
                "reason_text": "This is a test override reason text",
                "ttl_minutes": 60  # Exceeds max of 30
            },
            timeout=30,
        )
        assert response.status_code in {400, 422}, f"Expected 400/422, got {response.status_code}"


# ============================================================================
# RUNBOOK REFERENCE TESTS
# ============================================================================

class TestRunbookReferences:
    """Tests for runbook references in responses"""

    def test_checks_have_runbook_refs(self, authed_session: requests.Session):
        """Verify automated checks have runbook_ref in remediation_payload"""
        response = authed_session.get(
            f"{BASE_URL}/api/phase4/admin/production-gate?refresh_checks=true",
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        
        checks = data.get("checks") or []
        for check in checks:
            if check.get("status") != "PASS":
                payload = check.get("remediation_payload") or {}
                assert "runbook_ref" in payload, f"Missing runbook_ref for check: {check.get('check_key')}"

    def test_runbook_refs_follow_pattern(self, authed_session: requests.Session):
        """Verify runbook_ref follows RBK-* pattern"""
        response = authed_session.get(
            f"{BASE_URL}/api/phase4/admin/production-gate?refresh_checks=true",
            timeout=30,
        )
        data = response.json()
        
        checks = data.get("checks") or []
        for check in checks:
            payload = check.get("remediation_payload") or {}
            runbook_ref = payload.get("runbook_ref")
            if runbook_ref:
                assert runbook_ref.startswith("RBK-"), f"Invalid runbook_ref pattern: {runbook_ref}"
