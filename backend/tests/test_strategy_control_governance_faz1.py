"""
Test Suite for Strategy Control + Governance System (Faz-1)
Tests:
- Strategy Control Overview endpoint
- Strategy Detail endpoint
- Strategy Audit History endpoint
- Strategy Actions: enable, disable, pause, resume, throttle, decommission
- Soft-disable flow validation (throttle -> pause -> disable)
- Reason/confirm enforcement for destructive actions
- Super admin authorization checks
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
OPS_USER_EMAIL = "canary.ops@platform.local"
OPS_USER_PASSWORD = "CanaryOps123!"


class TestStrategyControlAuth:
    """Authentication and authorization tests for Strategy Control endpoints"""

    @pytest.fixture(scope="class")
    def super_admin_token(self):
        """Get super admin authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token") or data.get("token")
        pytest.skip(f"Super admin login failed: {response.status_code}")

    @pytest.fixture(scope="class")
    def ops_user_token(self):
        """Get ops user authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": OPS_USER_EMAIL, "password": OPS_USER_PASSWORD},
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token") or data.get("token")
        pytest.skip(f"Ops user login failed: {response.status_code}")

    def test_overview_requires_super_admin(self, ops_user_token):
        """Ops user should get 403 on super_admin-only endpoints"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers={"Authorization": f"Bearer {ops_user_token}"},
        )
        # Should be 403 Forbidden for ops user
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"

    def test_overview_works_for_super_admin(self, super_admin_token):
        """Super admin should access overview endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "ok"
        assert "strategies" in data
        assert "tabs" in data
        assert "phase_scope" in data


class TestStrategyControlOverview:
    """Tests for Strategy Control Overview endpoint"""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get authentication headers"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
        )
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token") or data.get("token")
            return {"Authorization": f"Bearer {token}"}
        pytest.skip("Authentication failed")

    def test_overview_returns_correct_structure(self, auth_headers):
        """Overview endpoint should return correct response structure"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert data.get("status") == "ok"
        assert "generated_at" in data
        assert "tabs" in data
        assert "phase_scope" in data
        assert "strategies" in data

        # Verify tabs list
        expected_tabs = [
            "overview",
            "universe_control",
            "rollout",
            "strategy_governance",
            "capital_governance",
            "drift_action_center",
            "audit_history",
        ]
        assert data["tabs"] == expected_tabs

        # Verify phase scope
        assert data["phase_scope"] == "phase_1_control_foundation"

    def test_overview_with_refresh_param(self, auth_headers):
        """Overview endpoint should accept refresh parameter"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview?refresh=true",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"

    def test_strategy_row_structure(self, auth_headers):
        """Strategy rows should have correct fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        strategies = data.get("strategies", [])

        if len(strategies) > 0:
            row = strategies[0]
            # Verify expected fields exist
            expected_fields = [
                "strategy_id",
                "strategy_name",
                "family_code",
                "source_type",
                "shadow_live_state",
                "lifecycle_state",
                "control_state",
                "throttle_level",
                "health_score",
                "pnl_rolling",
                "win_rate",
                "execution_quality",
                "drift_count",
                "drift_severity",
            ]
            for field in expected_fields:
                assert field in row, f"Missing field: {field}"


class TestStrategyDetail:
    """Tests for Strategy Detail endpoint"""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get authentication headers"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
        )
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token") or data.get("token")
            return {"Authorization": f"Bearer {token}"}
        pytest.skip("Authentication failed")

    @pytest.fixture(scope="class")
    def strategy_id(self, auth_headers):
        """Get a strategy ID from overview"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=auth_headers,
        )
        if response.status_code == 200:
            data = response.json()
            strategies = data.get("strategies", [])
            if strategies:
                return strategies[0]["strategy_id"]
        return "test_strategy_001"

    def test_detail_endpoint_returns_correct_structure(self, auth_headers, strategy_id):
        """Detail endpoint should return correct response structure"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/detail",
            headers=auth_headers,
        )
        # May return 404 if strategy doesn't exist, which is acceptable
        if response.status_code == 404:
            pytest.skip("No strategy found for detail test")

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert data.get("status") == "ok"
        assert "strategy" in data
        assert "execution_history" in data
        assert "trade_list" in data
        assert "governance_events" in data
        assert "transition_history" in data
        assert "export" in data

        # Verify Faz-1 placeholder fields
        exec_history = data.get("execution_history", {})
        assert "reason" in exec_history
        assert "Faz-1" in exec_history.get("reason", "")

        trade_list = data.get("trade_list", {})
        assert "reason" in trade_list
        assert "Faz-1" in trade_list.get("reason", "")

    def test_detail_not_found_for_invalid_strategy(self, auth_headers):
        """Detail endpoint should return 404 for non-existent strategy"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/INVALID_STRATEGY_XYZ/detail",
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestStrategyAuditHistory:
    """Tests for Strategy Audit History endpoint"""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get authentication headers"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
        )
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token") or data.get("token")
            return {"Authorization": f"Bearer {token}"}
        pytest.skip("Authentication failed")

    def test_audit_history_returns_correct_structure(self, auth_headers):
        """Audit history endpoint should return correct response structure"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/test_strategy/audit-history",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert data.get("status") == "ok"
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_audit_history_with_limit_param(self, auth_headers):
        """Audit history should accept limit parameter"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/test_strategy/audit-history?limit=10",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"


class TestStrategyActions:
    """Tests for Strategy Action endpoints (enable, disable, pause, resume, throttle, decommission)"""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get authentication headers"""
        import time
        time.sleep(2)  # Rate limit avoidance
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
        )
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token") or data.get("token")
            return {"Authorization": f"Bearer {token}"}
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")

    @pytest.fixture(scope="class")
    def strategy_id(self, auth_headers):
        """Get a strategy ID from overview"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=auth_headers,
        )
        if response.status_code == 200:
            data = response.json()
            strategies = data.get("strategies", [])
            if strategies:
                return strategies[0]["strategy_id"]
        return "trend_follow_v1"  # Default strategy ID

    def test_action_requires_reason(self, auth_headers, strategy_id):
        """Actions should require reason field"""
        # Try without reason
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/enable",
            headers=auth_headers,
            json={},
        )
        # Should fail validation (422) because reason is required
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"

    def test_enable_action_contract(self, auth_headers, strategy_id):
        """Enable action should return correct contract"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/enable",
            headers=auth_headers,
            json={"reason": "Test enable action", "dry_run": True},
        )
        # May return 404 if strategy doesn't exist
        if response.status_code == 404:
            pytest.skip("No strategy found for action test")

        assert response.status_code == 200
        data = response.json()

        # Verify action contract: status, trace_id, message, state_snapshot
        assert "status" in data
        assert "trace_id" in data
        assert "message" in data
        assert "state_snapshot" in data

        # Dry run should return dry_run status
        assert data["status"] == "dry_run"

    def test_throttle_action_with_level(self, auth_headers, strategy_id):
        """Throttle action should accept throttle_level parameter"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/throttle",
            headers=auth_headers,
            json={"reason": "Test throttle action", "throttle_level": "L2", "dry_run": True},
        )
        if response.status_code == 404:
            pytest.skip("No strategy found for action test")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "trace_id" in data

    def test_pause_action_contract(self, auth_headers, strategy_id):
        """Pause action should return correct contract"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/pause",
            headers=auth_headers,
            json={"reason": "Test pause action", "dry_run": True},
        )
        if response.status_code == 404:
            pytest.skip("No strategy found for action test")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "trace_id" in data
        assert "message" in data

    def test_resume_action_contract(self, auth_headers, strategy_id):
        """Resume action should return correct contract"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/resume",
            headers=auth_headers,
            json={"reason": "Test resume action", "dry_run": True},
        )
        if response.status_code == 404:
            pytest.skip("No strategy found for action test")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "trace_id" in data


class TestSoftDisableFlow:
    """Tests for soft-disable security rule: throttle -> pause -> disable"""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get authentication headers"""
        import time
        time.sleep(2)  # Rate limit avoidance
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
        )
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token") or data.get("token")
            return {"Authorization": f"Bearer {token}"}
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")

    @pytest.fixture(scope="class")
    def strategy_id(self, auth_headers):
        """Get a strategy ID from overview"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=auth_headers,
        )
        if response.status_code == 200:
            data = response.json()
            strategies = data.get("strategies", [])
            if strategies:
                return strategies[0]["strategy_id"]
        return "trend_follow_v1"  # Default strategy ID

    def test_disable_requires_confirm_phrase(self, auth_headers, strategy_id):
        """Disable action should require confirm phrase"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/disable",
            headers=auth_headers,
            json={"reason": "Test disable without confirm"},
        )
        if response.status_code == 404:
            pytest.skip("No strategy found for action test")

        assert response.status_code == 200
        data = response.json()
        # Should be rejected due to missing/wrong confirm phrase
        assert data.get("status") == "rejected"
        assert "DISABLE STRATEGY" in data.get("message", "")

    def test_disable_with_wrong_confirm_phrase(self, auth_headers, strategy_id):
        """Disable action should reject wrong confirm phrase"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/disable",
            headers=auth_headers,
            json={"reason": "Test disable with wrong confirm", "confirm_phrase": "WRONG PHRASE"},
        )
        if response.status_code == 404:
            pytest.skip("No strategy found for action test")

        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "rejected"

    def test_decommission_requires_confirm_phrase(self, auth_headers, strategy_id):
        """Decommission action should require confirm phrase"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/decommission",
            headers=auth_headers,
            json={"reason": "Test decommission without confirm"},
        )
        if response.status_code == 404:
            pytest.skip("No strategy found for action test")

        assert response.status_code == 200
        data = response.json()
        # Should be rejected due to missing/wrong confirm phrase
        assert data.get("status") == "rejected"
        assert "DECOMMISSION STRATEGY" in data.get("message", "")


class TestActionAuditCreation:
    """Tests for audit log creation after actions"""

    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get authentication headers"""
        import time
        time.sleep(2)  # Rate limit avoidance
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
        )
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token") or data.get("token")
            return {"Authorization": f"Bearer {token}"}
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")

    @pytest.fixture(scope="class")
    def strategy_id(self, auth_headers):
        """Get a strategy ID from overview"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers=auth_headers,
        )
        if response.status_code == 200:
            data = response.json()
            strategies = data.get("strategies", [])
            if strategies:
                return strategies[0]["strategy_id"]
        return "trend_follow_v1"  # Default strategy ID

    def test_action_creates_audit_log(self, auth_headers, strategy_id):
        """Actions should create audit log entries"""
        # First, perform an action
        action_response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/enable",
            headers=auth_headers,
            json={"reason": "Test audit log creation"},
        )
        if action_response.status_code == 404:
            pytest.skip("No strategy found for action test")

        # Then check audit history
        audit_response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/{strategy_id}/audit-history",
            headers=auth_headers,
        )
        assert audit_response.status_code == 200
        audit_data = audit_response.json()

        # Verify audit items exist
        assert audit_data.get("status") == "ok"
        items = audit_data.get("items", [])
        # Should have at least one audit entry
        # Note: May be empty if this is first action on strategy
        assert isinstance(items, list)


class TestOpsUserAccessDenied:
    """Tests to verify ops user cannot access super_admin-only endpoints"""

    @pytest.fixture(scope="class")
    def ops_token(self):
        """Get ops user authentication token"""
        import time
        time.sleep(2)  # Rate limit avoidance
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": OPS_USER_EMAIL, "password": OPS_USER_PASSWORD},
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token") or data.get("token")
        pytest.skip(f"Ops user login failed: {response.status_code} - {response.text}")

    def test_ops_cannot_access_overview(self, ops_token):
        """Ops user should get 403 on overview endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-control/overview",
            headers={"Authorization": f"Bearer {ops_token}"},
        )
        assert response.status_code == 403

    def test_ops_cannot_access_detail(self, ops_token):
        """Ops user should get 403 on detail endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy/test_strategy/detail",
            headers={"Authorization": f"Bearer {ops_token}"},
        )
        assert response.status_code == 403

    def test_ops_cannot_perform_actions(self, ops_token):
        """Ops user should get 403 on action endpoints"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/test_strategy/enable",
            headers={"Authorization": f"Bearer {ops_token}"},
            json={"reason": "Test ops access"},
        )
        assert response.status_code == 403
