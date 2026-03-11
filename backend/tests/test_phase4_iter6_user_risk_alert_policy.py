"""
Phase-4 Iteration-6 Test Suite:
- CI artifacts: .github/workflows/stage-gate.yml ve prod-gate.yml
- scripts/run_release_gate_check.sh --env zorunluluğu
- scripts/ci_stage_gate.sh ve scripts/ci_prod_gate.sh
- GET/PUT /api/phase4/admin/alert-policy
- GET /api/phase4/admin/active-alerts
- GET /api/user-risk/settings, /api/user-risk/preview, /api/user-risk/overview
- PUT /api/user-risk/settings limit doğrulamaları
"""

import os
import subprocess
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"
TEST_USER_EMAIL = "TEST_phase4iter4@example.com"
TEST_USER_PASSWORD = "TestPassword123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin token for authenticated requests."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code}")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def user_token():
    """Get user token for authenticated requests."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"User login failed: {response.status_code}")
    return response.json().get("access_token")


class TestCIArtifacts:
    """CI wrapper script and workflow file tests"""

    def test_github_workflow_stage_gate_exists(self):
        """Verify .github/workflows/stage-gate.yml exists"""
        path = "/app/.github/workflows/stage-gate.yml"
        assert os.path.exists(path), f"stage-gate.yml not found at {path}"

    def test_github_workflow_prod_gate_exists(self):
        """Verify .github/workflows/prod-gate.yml exists"""
        path = "/app/.github/workflows/prod-gate.yml"
        assert os.path.exists(path), f"prod-gate.yml not found at {path}"

    def test_github_workflow_stage_gate_calls_wrapper(self):
        """Verify stage-gate.yml calls scripts/ci_stage_gate.sh"""
        path = "/app/.github/workflows/stage-gate.yml"
        with open(path, "r") as f:
            content = f.read()
        assert "ci_stage_gate.sh" in content, "stage-gate.yml should call ci_stage_gate.sh"

    def test_github_workflow_prod_gate_calls_wrapper(self):
        """Verify prod-gate.yml calls scripts/ci_prod_gate.sh"""
        path = "/app/.github/workflows/prod-gate.yml"
        with open(path, "r") as f:
            content = f.read()
        assert "ci_prod_gate.sh" in content, "prod-gate.yml should call ci_prod_gate.sh"

    def test_ci_stage_gate_script_exists(self):
        """Verify scripts/ci_stage_gate.sh exists"""
        path = "/app/scripts/ci_stage_gate.sh"
        assert os.path.exists(path), f"ci_stage_gate.sh not found at {path}"

    def test_ci_prod_gate_script_exists(self):
        """Verify scripts/ci_prod_gate.sh exists"""
        path = "/app/scripts/ci_prod_gate.sh"
        assert os.path.exists(path), f"ci_prod_gate.sh not found at {path}"

    def test_run_release_gate_check_script_exists(self):
        """Verify scripts/run_release_gate_check.sh exists"""
        path = "/app/scripts/run_release_gate_check.sh"
        assert os.path.exists(path), f"run_release_gate_check.sh not found at {path}"


class TestRunReleaseGateCheckScript:
    """Tests for run_release_gate_check.sh --env requirement"""

    def test_script_fails_without_env_arg(self):
        """Missing --env should exit code 2 with error message"""
        result = subprocess.run(
            ["/app/scripts/run_release_gate_check.sh"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2, f"Expected exit code 2, got {result.returncode}"
        assert "missing required argument" in result.stderr.lower(), f"Expected 'missing required argument' in stderr, got: {result.stderr}"

    def test_ci_stage_gate_calls_wrapper_with_env(self):
        """ci_stage_gate.sh should call run_release_gate_check.sh with --env=stage"""
        path = "/app/scripts/ci_stage_gate.sh"
        with open(path, "r") as f:
            content = f.read()
        assert "--env=stage" in content, "ci_stage_gate.sh should pass --env=stage"

    def test_ci_prod_gate_calls_wrapper_with_env(self):
        """ci_prod_gate.sh should call run_release_gate_check.sh with --env=prod"""
        path = "/app/scripts/ci_prod_gate.sh"
        with open(path, "r") as f:
            content = f.read()
        assert "--env=prod" in content, "ci_prod_gate.sh should pass --env=prod"


class TestAlertPolicyAPI:
    """GET/PUT /api/phase4/admin/alert-policy tests"""

    def test_get_alert_policy(self, admin_token):
        """GET /api/phase4/admin/alert-policy returns policy fields"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/admin/alert-policy",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        required_fields = [
            "admin_notification_enabled",
            "ops_webhook_url",
            "monitoring_alert_log_enabled",
            "execution_quality_warning_threshold",
            "execution_quality_critical_threshold",
            "permission_drift_warning_per_day",
            "permission_drift_critical_per_day",
            "gate_override_warning_per_day",
            "gate_override_critical_per_day",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    def test_put_alert_policy_update(self, admin_token):
        """PUT /api/phase4/admin/alert-policy updates thresholds"""
        new_policy = {
            "admin_notification_enabled": True,
            "ops_webhook_url": "",
            "monitoring_alert_log_enabled": True,
            "execution_quality_warning_threshold": 70,
            "execution_quality_critical_threshold": 50,
            "permission_drift_warning_per_day": 3,
            "permission_drift_critical_per_day": 6,
            "gate_override_warning_per_day": 3,
            "gate_override_critical_per_day": 6,
        }
        
        response = requests.put(
            f"{BASE_URL}/api/phase4/admin/alert-policy",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json=new_policy,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["execution_quality_warning_threshold"] == 70
        assert data["execution_quality_critical_threshold"] == 50
        assert data["permission_drift_warning_per_day"] == 3
        
        # Reset to defaults
        reset_policy = {
            "admin_notification_enabled": True,
            "ops_webhook_url": "",
            "monitoring_alert_log_enabled": True,
            "execution_quality_warning_threshold": 60,
            "execution_quality_critical_threshold": 40,
            "permission_drift_warning_per_day": 2,
            "permission_drift_critical_per_day": 5,
            "gate_override_warning_per_day": 2,
            "gate_override_critical_per_day": 5,
        }
        requests.put(
            f"{BASE_URL}/api/phase4/admin/alert-policy",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json=reset_policy,
        )

    def test_alert_policy_requires_admin(self, user_token):
        """Alert policy endpoints require admin role"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/admin/alert-policy",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code in [401, 403], f"Expected 401/403 for non-admin, got {response.status_code}"


class TestActiveAlertsAPI:
    """GET /api/phase4/admin/active-alerts tests"""

    def test_get_active_alerts(self, admin_token):
        """GET /api/phase4/admin/active-alerts returns alert list"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/admin/active-alerts",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of alerts"
        
        # If alerts exist, verify structure
        if len(data) > 0:
            alert = data[0]
            assert "code" in alert, "Alert should have 'code' field"
            assert "severity" in alert, "Alert should have 'severity' field"
            assert "value" in alert, "Alert should have 'value' field"
            assert "threshold_warning" in alert, "Alert should have 'threshold_warning' field"
            assert "threshold_critical" in alert, "Alert should have 'threshold_critical' field"

    def test_active_alerts_requires_admin(self, user_token):
        """Active alerts endpoint requires admin role"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/admin/active-alerts",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code in [401, 403], f"Expected 401/403 for non-admin, got {response.status_code}"


class TestUserRiskSettingsAPI:
    """GET /api/user-risk/settings endpoint tests"""

    def test_get_risk_settings(self, user_token):
        """GET /api/user-risk/settings returns risk configuration"""
        response = requests.get(
            f"{BASE_URL}/api/user-risk/settings",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        required_fields = [
            "allocation_pct",
            "trade_risk_pct",
            "daily_loss_limit_pct",
            "compounding_enabled",
            "base_capital",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"


class TestUserRiskPreviewAPI:
    """GET /api/user-risk/preview endpoint tests"""

    def test_get_risk_preview(self, user_token):
        """GET /api/user-risk/preview returns calculated preview"""
        response = requests.get(
            f"{BASE_URL}/api/user-risk/preview",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        required_fields = [
            "current_capital",
            "allocation_pct",
            "trade_allocation_amount",
            "trade_risk_pct",
            "max_trade_loss_amount",
            "total_capital_impact_pct",
            "compounding_enabled",
            "next_trade_base_capital",
            "warnings",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        assert isinstance(data["warnings"], list), "warnings should be a list"


class TestUserRiskOverviewAPI:
    """GET /api/user-risk/overview endpoint tests"""

    def test_get_portfolio_overview(self, user_token):
        """GET /api/user-risk/overview returns portfolio state"""
        response = requests.get(
            f"{BASE_URL}/api/user-risk/overview",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        required_fields = [
            "current_capital",
            "available_balance",
            "open_position_balance",
            "closed_pnl",
            "compounding_enabled",
            "next_base_capital",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"


class TestUserRiskSettingsValidation:
    """PUT /api/user-risk/settings limit validation tests"""

    def test_update_risk_settings_success(self, user_token):
        """PUT /api/user-risk/settings with valid values succeeds"""
        valid_payload = {
            "allocation_pct": 25,
            "trade_risk_pct": 15,
            "daily_loss_limit_pct": 5,
            "compounding_enabled": False,
        }
        response = requests.put(
            f"{BASE_URL}/api/user-risk/settings",
            headers={"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"},
            json=valid_payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["allocation_pct"] == 25
        assert data["trade_risk_pct"] == 15
        assert data["daily_loss_limit_pct"] == 5
        assert not data["compounding_enabled"]

    def test_allocation_pct_too_high_blocked(self, user_token):
        """allocation_pct > 50 should be rejected"""
        payload = {
            "allocation_pct": 60,
            "trade_risk_pct": 10,
            "daily_loss_limit_pct": 3,
            "compounding_enabled": True,
        }
        response = requests.put(
            f"{BASE_URL}/api/user-risk/settings",
            headers={"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"},
            json=payload,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        assert "1-50" in response.json().get("detail", ""), "Error should mention valid range"

    def test_allocation_pct_too_low_blocked(self, user_token):
        """allocation_pct < 1 should be rejected"""
        payload = {
            "allocation_pct": 0,
            "trade_risk_pct": 10,
            "daily_loss_limit_pct": 3,
            "compounding_enabled": True,
        }
        response = requests.put(
            f"{BASE_URL}/api/user-risk/settings",
            headers={"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"},
            json=payload,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"

    def test_trade_risk_pct_too_high_blocked(self, user_token):
        """trade_risk_pct > 25 should be rejected"""
        payload = {
            "allocation_pct": 20,
            "trade_risk_pct": 30,
            "daily_loss_limit_pct": 3,
            "compounding_enabled": True,
        }
        response = requests.put(
            f"{BASE_URL}/api/user-risk/settings",
            headers={"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"},
            json=payload,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        assert "1-25" in response.json().get("detail", ""), "Error should mention valid range"

    def test_daily_loss_limit_pct_too_high_blocked(self, user_token):
        """daily_loss_limit_pct > 10 should be rejected"""
        payload = {
            "allocation_pct": 20,
            "trade_risk_pct": 10,
            "daily_loss_limit_pct": 15,
            "compounding_enabled": True,
        }
        response = requests.put(
            f"{BASE_URL}/api/user-risk/settings",
            headers={"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"},
            json=payload,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        assert "1-10" in response.json().get("detail", ""), "Error should mention valid range"

    def test_restore_default_settings(self, user_token):
        """Restore default settings after tests"""
        payload = {
            "allocation_pct": 20,
            "trade_risk_pct": 10,
            "daily_loss_limit_pct": 3,
            "compounding_enabled": True,
        }
        requests.put(
            f"{BASE_URL}/api/user-risk/settings",
            headers={"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"},
            json=payload,
        )


class TestPermissionDriftAlertRouting:
    """Permission drift alert routing mechanism test"""

    def test_permission_drift_trend_endpoint(self, admin_token):
        """GET /api/phase4/admin/permission-drift-trend returns trend data"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/admin/permission-drift-trend?days=7",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "days" in data
        assert "points" in data
        assert "affected_user_count" in data
        assert "critical_drift_count" in data
        assert isinstance(data["points"], list)


class TestReadinessChecklistAndTestOrder:
    """User readiness checklist and test order blocked behavior"""

    def test_readiness_checklist_has_required_fields(self, user_token):
        """GET /api/exchange/readiness-checklist has all required fields"""
        response = requests.get(
            f"{BASE_URL}/api/exchange/readiness-checklist",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        required_fields = [
            "readiness_status",
            "has_api_key",
            "has_api_secret",
            "validation_success",
            "can_trade",
            "is_testnet_environment",
            "is_validation_stale",
            "stale_after_minutes",
            "last_error_reason",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    def test_test_order_blocked_without_valid_key(self, user_token):
        """POST /api/exchange/test-order returns blocked state without valid key"""
        response = requests.post(
            f"{BASE_URL}/api/exchange/test-order",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        # Should return 400 with awaiting_valid_key or blocked status
        assert response.status_code == 400, f"Expected 400 when key not valid, got {response.status_code}"
        detail = response.json().get("detail", {})
        if isinstance(detail, dict):
            status = detail.get("status", "")
            assert status in ["awaiting_valid_key", "blocked"], f"Expected awaiting_valid_key or blocked status, got: {status}"


class TestNavbarOverrideCountdown:
    """Navbar override countdown badge visibility test"""

    def test_release_gate_returns_override_fields(self, admin_token):
        """GET /api/phase4/admin/release-gate returns override fields for navbar"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/admin/release-gate?environment=prod",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Fields needed for navbar badge
        assert "status" in data
        assert "override_active" in data
        assert "override_expires_at" in data
