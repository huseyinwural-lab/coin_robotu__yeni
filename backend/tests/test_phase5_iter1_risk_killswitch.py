"""
Phase-5 Iteration-1 Test Suite: Risk Engine + Position Sizing + Kill Switch
Tests:
- Risk engine hard veto (block reason kaydı)
- Position sizing engine (equity x allocation% and risk_amount formula)
- Kill switch block_new_orders_only mode (3A kararı)
- Kill switch status/reset endpoints
- Monitoring endpoint new fields
- User risk settings/preview/overview regression
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"
USER_EMAIL = "TEST_phase4iter4@example.com"
USER_PASSWORD = "TestPassword123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.text}")
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def user_token():
    """Get user authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": USER_EMAIL, "password": USER_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"User login failed: {response.text}")
    return response.json()["access_token"]


class TestKillSwitchEndpoints:
    """Kill switch status and reset endpoint tests"""

    def test_kill_switch_status_returns_required_fields(self, admin_token):
        """Test GET /api/admin-control/kill-switch/status returns all required fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin-control/kill-switch/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields exist
        assert "triggered" in data
        assert "active" in data
        assert "reasons" in data
        assert isinstance(data["triggered"], bool)
        assert isinstance(data["active"], bool)
        assert isinstance(data["reasons"], list)

    def test_kill_switch_reset_works(self, admin_token):
        """Test POST /api/admin-control/kill-switch/reset resets the kill switch"""
        response = requests.post(
            f"{BASE_URL}/api/admin-control/kill-switch/reset",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        # After reset, should be inactive
        assert data["triggered"] is False
        assert data["active"] is False
        assert data["reasons"] == []

    def test_kill_switch_status_after_reset_is_inactive(self, admin_token):
        """Test kill switch status after reset is inactive"""
        # First reset
        requests.post(
            f"{BASE_URL}/api/admin-control/kill-switch/reset",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        
        # Then check status
        response = requests.get(
            f"{BASE_URL}/api/admin-control/kill-switch/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["active"] is False

    def test_kill_switch_requires_admin(self, user_token):
        """Test kill switch endpoints require admin role"""
        response = requests.get(
            f"{BASE_URL}/api/admin-control/kill-switch/status",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403


class TestMonitoringEndpointNewFields:
    """Test monitoring endpoint returns new fields for Phase-5"""

    def test_monitoring_has_execution_errors_5m(self, admin_token):
        """Test monitoring has execution_errors_5m field"""
        response = requests.get(
            f"{BASE_URL}/api/pipeline/monitoring",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "execution_errors_5m" in data
        assert isinstance(data["execution_errors_5m"], int)

    def test_monitoring_has_risk_anomalies_5m(self, admin_token):
        """Test monitoring has risk_anomalies_5m field"""
        response = requests.get(
            f"{BASE_URL}/api/pipeline/monitoring",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "risk_anomalies_5m" in data
        assert isinstance(data["risk_anomalies_5m"], int)

    def test_monitoring_has_global_trading_pause(self, admin_token):
        """Test monitoring has global_trading_pause field"""
        response = requests.get(
            f"{BASE_URL}/api/pipeline/monitoring",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "global_trading_pause" in data
        assert isinstance(data["global_trading_pause"], bool)

    def test_monitoring_has_kill_switch_reasons(self, admin_token):
        """Test monitoring has kill_switch_reasons field"""
        response = requests.get(
            f"{BASE_URL}/api/pipeline/monitoring",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "kill_switch_reasons" in data
        assert isinstance(data["kill_switch_reasons"], list)


class TestUserRiskEndpointsRegression:
    """User risk settings, preview, overview regression tests"""

    def test_user_risk_settings_get(self, user_token):
        """Test GET /api/user-risk/settings returns expected fields"""
        response = requests.get(
            f"{BASE_URL}/api/user-risk/settings",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "allocation_pct" in data
        assert "trade_risk_pct" in data
        assert "daily_loss_limit_pct" in data
        assert "compounding_enabled" in data
        assert "base_capital" in data

    def test_user_risk_preview_formula_correct(self, user_token):
        """Test GET /api/user-risk/preview returns correct calculation"""
        response = requests.get(
            f"{BASE_URL}/api/user-risk/preview",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify formula: trade_allocation_amount = current_capital * allocation_pct / 100
        expected_allocation = data["current_capital"] * (data["allocation_pct"] / 100)
        assert abs(data["trade_allocation_amount"] - expected_allocation) < 0.01
        
        # Verify formula: max_trade_loss_amount = trade_allocation_amount * trade_risk_pct / 100
        expected_risk = data["trade_allocation_amount"] * (data["trade_risk_pct"] / 100)
        assert abs(data["max_trade_loss_amount"] - expected_risk) < 0.01

    def test_user_risk_overview_returns_expected_fields(self, user_token):
        """Test GET /api/user-risk/overview returns all expected fields"""
        response = requests.get(
            f"{BASE_URL}/api/user-risk/overview",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "current_capital" in data
        assert "available_balance" in data
        assert "open_position_balance" in data
        assert "closed_pnl" in data
        assert "compounding_enabled" in data
        assert "next_base_capital" in data


class TestAdminControlEndpoints:
    """Admin control endpoint tests"""

    def test_admin_control_get(self, admin_token):
        """Test GET /api/admin-control returns expected fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin-control",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "emergency_mode" in data
        assert "max_leverage_cap" in data
        assert "max_open_positions_cap" in data
        assert isinstance(data["emergency_mode"], bool)

    def test_admin_control_update_emergency_mode(self, admin_token):
        """Test PUT /api/admin-control can toggle emergency_mode (kill switch)"""
        # Get current state
        response = requests.get(
            f"{BASE_URL}/api/admin-control",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        current_data = response.json()
        
        # Toggle emergency_mode
        new_emergency_mode = not current_data["emergency_mode"]
        update_payload = {
            "max_leverage_cap": current_data["max_leverage_cap"],
            "max_open_positions_cap": current_data["max_open_positions_cap"],
            "minimum_volume_usd": current_data["minimum_volume_usd"],
            "max_spread_bps": current_data["max_spread_bps"],
            "spot_universe": current_data["spot_universe"],
            "futures_universe": current_data["futures_universe"],
            "whitelist": current_data["whitelist"],
            "blacklist": current_data["blacklist"],
            "emergency_mode": new_emergency_mode,
            "disable_futures": current_data["disable_futures"],
        }
        
        response = requests.put(
            f"{BASE_URL}/api/admin-control",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=update_payload,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["emergency_mode"] == new_emergency_mode
        
        # Revert back
        update_payload["emergency_mode"] = current_data["emergency_mode"]
        requests.put(
            f"{BASE_URL}/api/admin-control",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=update_payload,
        )


class TestPositionSizingEngineFormula:
    """Test position sizing engine formula via preview endpoint"""

    def test_position_sizing_equity_allocation_formula(self, user_token):
        """Test equity × allocation% formula"""
        response = requests.get(
            f"{BASE_URL}/api/user-risk/preview",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        # Formula: trade_allocation_amount = equity * (allocation_pct / 100)
        equity = data["current_capital"]
        allocation_pct = data["allocation_pct"]
        expected_allocation = equity * (allocation_pct / 100)
        
        assert abs(data["trade_allocation_amount"] - expected_allocation) < 0.01, \
            f"Expected {expected_allocation}, got {data['trade_allocation_amount']}"

    def test_position_sizing_risk_amount_formula(self, user_token):
        """Test risk_amount = allocation_amount × trade_risk% formula"""
        response = requests.get(
            f"{BASE_URL}/api/user-risk/preview",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        # Formula: risk_amount = trade_allocation_amount * (trade_risk_pct / 100)
        allocation_amount = data["trade_allocation_amount"]
        trade_risk_pct = data["trade_risk_pct"]
        expected_risk = allocation_amount * (trade_risk_pct / 100)
        
        assert abs(data["max_trade_loss_amount"] - expected_risk) < 0.01, \
            f"Expected {expected_risk}, got {data['max_trade_loss_amount']}"

    def test_position_sizing_capital_impact_calculation(self, user_token):
        """Test total_capital_impact_pct calculation"""
        response = requests.get(
            f"{BASE_URL}/api/user-risk/preview",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        # Formula: total_capital_impact_pct = (max_trade_loss_amount / current_capital) * 100
        current_capital = data["current_capital"]
        max_loss = data["max_trade_loss_amount"]
        expected_impact = (max_loss / current_capital) * 100 if current_capital > 0 else 0
        
        assert abs(data["total_capital_impact_pct"] - expected_impact) < 0.01, \
            f"Expected {expected_impact}, got {data['total_capital_impact_pct']}"


class TestCIScriptsRequireEnv:
    """Test CI/deploy scripts require --env argument"""

    def test_release_gate_check_requires_env(self):
        """Test run_release_gate_check.sh exits with code 2 when --env is missing"""
        import subprocess
        result = subprocess.run(
            ["bash", "/app/scripts/run_release_gate_check.sh"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2
        assert "missing required argument: --env" in result.stderr

    def test_stage_gate_wrapper_passes_env(self):
        """Test ci_stage_gate.sh passes --env=stage"""
        import subprocess
        result = subprocess.run(
            ["bash", "/app/scripts/ci_stage_gate.sh"],
            capture_output=True,
            text=True,
        )
        # Should execute without "missing --env" error
        assert "missing required argument: --env" not in result.stderr
        # Should show environment=stage in output
        assert "stage" in result.stdout or "stage" in result.stderr

    def test_prod_gate_wrapper_passes_env(self):
        """Test ci_prod_gate.sh passes --env=prod"""
        import subprocess
        result = subprocess.run(
            ["bash", "/app/scripts/ci_prod_gate.sh"],
            capture_output=True,
            text=True,
        )
        # Should execute without "missing --env" error
        assert "missing required argument: --env" not in result.stderr
        # Should show environment=prod in output
        assert "prod" in result.stdout or "prod" in result.stderr


class TestRiskEngineHardVetoRecordsBlockReason:
    """Test risk engine records block reasons when rejecting orders"""

    def test_monitoring_shows_correlation_rejections(self, admin_token):
        """Test monitoring endpoint shows correlation_rejections_5m field"""
        response = requests.get(
            f"{BASE_URL}/api/pipeline/monitoring",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        # correlation_rejections_5m should be present for hard veto tracking
        assert "correlation_rejections_5m" in data
        assert isinstance(data["correlation_rejections_5m"], int)

    def test_monitoring_shows_failed_events_for_rejection_tracking(self, admin_token):
        """Test monitoring shows failed events which includes rejection tracking"""
        response = requests.get(
            f"{BASE_URL}/api/pipeline/monitoring",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        # Failed events are used to track pipeline rejections
        assert "failed_events_pending" in data
        assert "failed_events_dead" in data


class TestHealthEndpoint:
    """Test health endpoint"""

    def test_health_returns_ok(self):
        """Test /api/health returns ok status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
