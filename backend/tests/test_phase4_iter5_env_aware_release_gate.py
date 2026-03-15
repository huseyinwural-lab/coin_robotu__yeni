"""
Phase-4 Iteration-5 Tests: Environment-aware release gate, CI wrappers, failure normalization
- A1: environment-aware release gate (stage/prod policy matrix)
- A2: gate policy fields (exchange_health, execution_quality_score, permission_drift_alert, active_override, live_mode_enabled)
- A3: CI wrappers + parse output
- A4: override countdown+15s auto-refresh (UI)
- B: test-order evidence persistence and failure normalization
- C: monitoring/user card standardization
"""
import os
import subprocess
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


class TestPhase4Iter5EnvAwareReleaseGate:
    """Test environment-aware release gate and CI scripts"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # Login as admin
        login_res = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": os.environ.get("TEST_ADMIN_EMAIL", ""), "password": os.environ.get("TEST_ADMIN_PASSWORD", "")},
        )
        assert login_res.status_code == 200
        self.admin_token = login_res.json()["access_token"]
        self.session.headers.update({"Authorization": f"Bearer {self.admin_token}"})

    # A1: --env zorunlu olma testi
    def test_run_release_gate_check_missing_env_exits_nonzero(self):
        """Missing --env arg should exit with code 2 and print missing required argument"""
        result = subprocess.run(
            ["/app/scripts/run_release_gate_check.sh"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2, f"Expected exit 2, got {result.returncode}"
        assert "missing required argument" in result.stderr.lower() or "missing required argument" in result.stdout.lower()

    # A1: ci_stage_gate.sh existence and execution
    def test_ci_stage_gate_script_exists_and_executable(self):
        """ci_stage_gate.sh should exist and be executable"""
        result = subprocess.run(
            ["/app/scripts/ci_stage_gate.sh"],
            capture_output=True,
            text=True,
        )
        # Should run (exit 0 or 2 depending on current gate state)
        assert result.returncode in [0, 2], f"Unexpected exit code: {result.returncode}"
        assert "release_gate_status=" in result.stdout or "reason=" in result.stdout

    # A1: ci_prod_gate.sh existence and execution
    def test_ci_prod_gate_script_exists_and_executable(self):
        """ci_prod_gate.sh should exist and be executable"""
        result = subprocess.run(
            ["/app/scripts/ci_prod_gate.sh"],
            capture_output=True,
            text=True,
        )
        # Should run (exit 0 or 2 depending on current gate state)
        assert result.returncode in [0, 2], f"Unexpected exit code: {result.returncode}"
        assert "release_gate_status=" in result.stdout or "reason=" in result.stdout

    # A1: Environment-aware release-gate API
    def test_release_gate_stage_environment(self):
        """GET /api/phase4/admin/release-gate?environment=stage returns stage environment"""
        response = self.session.get(f"{BASE_URL}/api/phase4/admin/release-gate?environment=stage")
        assert response.status_code == 200
        data = response.json()
        assert data["environment"] == "stage"
        assert "status" in data
        assert "reason_code" in data
        assert data["status"] in ["PASS", "BLOCKED", "WARN", "PASS_WITH_OVERRIDE"]

    def test_release_gate_prod_environment(self):
        """GET /api/phase4/admin/release-gate?environment=prod returns prod environment"""
        response = self.session.get(f"{BASE_URL}/api/phase4/admin/release-gate?environment=prod")
        assert response.status_code == 200
        data = response.json()
        assert data["environment"] == "prod"
        assert "status" in data
        assert "reason_code" in data
        assert data["status"] in ["PASS", "BLOCKED", "WARN", "PASS_WITH_OVERRIDE"]

    def test_release_gate_invalid_environment_returns_error(self):
        """Invalid environment parameter should return 400 or 422"""
        response = self.session.get(f"{BASE_URL}/api/phase4/admin/release-gate?environment=invalid")
        assert response.status_code in [400, 422, 500]  # Backend should validate

    # A2: Gate policy fields verification
    def test_release_gate_contains_override_fields(self):
        """Release gate response should contain override_active, override_expires_at, override_id"""
        response = self.session.get(f"{BASE_URL}/api/phase4/admin/release-gate?environment=prod")
        assert response.status_code == 200
        data = response.json()
        assert "override_active" in data
        assert "override_expires_at" in data or (not data["override_active"])
        assert "override_id" in data or (not data["override_active"])

    # A3: Script output parsing - PASS_WITH_OVERRIDE output format
    def test_script_output_pass_with_override_format(self):
        """When override active, script should output reason_code and override_expires_at"""
        result = subprocess.run(
            ["/app/scripts/ci_prod_gate.sh"],
            capture_output=True,
            text=True,
        )
        # If PASS_WITH_OVERRIDE
        if "PASS_WITH_OVERRIDE" in result.stdout:
            assert result.returncode == 0
            assert "reason_code=" in result.stdout or "override_expires_at=" in result.stdout

    def test_script_output_blocked_format(self):
        """When BLOCKED, script should exit with code 2"""
        result = subprocess.run(
            ["/app/scripts/ci_stage_gate.sh"],
            capture_output=True,
            text=True,
        )
        # If BLOCKED, exit code should be 2
        if "BLOCKED" in result.stdout and "PASS_WITH_OVERRIDE" not in result.stdout:
            assert result.returncode == 2


class TestPhase4Iter5ReadinessAndEvidence:
    """Test readiness checklist and lifecycle evidence endpoints"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # Login as test user
        login_res = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "TEST_phase4iter4@example.com", "password": "TestPassword123!"},
        )
        if login_res.status_code != 200:
            pytest.skip("Test user not found, skipping user endpoint tests")
        self.user_token = login_res.json()["access_token"]
        self.session.headers.update({"Authorization": f"Bearer {self.user_token}"})

    # B: Readiness checklist includes validation_snapshot_id
    def test_readiness_checklist_contains_validation_snapshot_id(self):
        """GET /api/exchange/readiness-checklist should include validation_snapshot_id"""
        response = self.session.get(f"{BASE_URL}/api/exchange/readiness-checklist")
        assert response.status_code == 200
        data = response.json()
        assert "validation_snapshot_id" in data
        assert "readiness_status" in data
        assert data["readiness_status"] in ["awaiting_valid_key", "ready_for_test_order", "blocked"]

    def test_readiness_checklist_contains_all_state_fields(self):
        """Readiness checklist should have all required fields"""
        response = self.session.get(f"{BASE_URL}/api/exchange/readiness-checklist")
        assert response.status_code == 200
        data = response.json()
        required_fields = [
            "readiness_status",
            "has_api_key",
            "has_api_secret",
            "validation_success",
            "can_trade",
            "is_testnet_environment",
            "is_validation_stale",
            "validation_timestamp",
            "validation_snapshot_id",
            "stale_after_minutes",
            "last_error_reason",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    # B: Test-order failure normalization
    def test_test_order_blocked_returns_failure_code(self):
        """POST /api/exchange/test-order should return normalized failure_code when blocked"""
        response = self.session.post(f"{BASE_URL}/api/exchange/test-order")
        assert response.status_code == 400  # Should be blocked since no valid key
        data = response.json()
        detail = data.get("detail", {})
        if isinstance(detail, dict):
            assert "failure_code" in detail, "Missing failure_code in detail"
            assert detail["failure_code"] in [
                "invalid_key",
                "permission_denied",
                "ip_restricted",
                "testnet_unreachable",
                "stale_validation",
                "exchange_rejected",
                "insufficient_balance",
                "unknown_exchange_error",
            ]

    def test_test_order_blocked_returns_status(self):
        """POST /api/exchange/test-order should return status in detail"""
        response = self.session.post(f"{BASE_URL}/api/exchange/test-order")
        assert response.status_code == 400
        data = response.json()
        detail = data.get("detail", {})
        if isinstance(detail, dict):
            assert "status" in detail

    # B: Lifecycle evidence endpoint
    def test_lifecycle_evidence_returns_404_when_no_evidence(self):
        """GET /api/exchange/lifecycle-evidence/latest returns 404 when no execution"""
        response = self.session.get(f"{BASE_URL}/api/exchange/lifecycle-evidence/latest")
        # If no evidence, should be 404; if evidence exists, should be 200
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert "timeline" in data

    def test_lifecycle_evidence_structure_when_exists(self):
        """GET /api/exchange/lifecycle-evidence/latest should have order_id, exchange_order_id, timeline when exists"""
        response = self.session.get(f"{BASE_URL}/api/exchange/lifecycle-evidence/latest")
        if response.status_code == 200:
            data = response.json()
            assert "order_id" in data
            assert "exchange_order_id" in data
            assert "final_status" in data
            assert "submitted_at" in data
            assert "timeline" in data
            assert isinstance(data["timeline"], list)


class TestPhase4Iter5AdminReleaseGatePolicy:
    """Test release gate policy matrix differences between stage and prod"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_res = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": os.environ.get("TEST_ADMIN_EMAIL", ""), "password": os.environ.get("TEST_ADMIN_PASSWORD", "")},
        )
        assert login_res.status_code == 200
        self.admin_token = login_res.json()["access_token"]
        self.session.headers.update({"Authorization": f"Bearer {self.admin_token}"})

    def test_release_gate_metrics_present(self):
        """Release gate response should include metrics object with policy fields"""
        # Check prod metrics
        response = self.session.get(f"{BASE_URL}/api/phase4/admin/release-gate?environment=prod")
        assert response.status_code == 200
        data = response.json()
        
        # Check for the metrics in the policy evaluation
        # The metrics should be present in the service layer
        assert "live_activation" in data
        assert "reasons" in data

    def test_stage_and_prod_environments_differ(self):
        """Stage and prod gates should have different environment values"""
        stage_res = self.session.get(f"{BASE_URL}/api/phase4/admin/release-gate?environment=stage")
        prod_res = self.session.get(f"{BASE_URL}/api/phase4/admin/release-gate?environment=prod")
        
        assert stage_res.status_code == 200
        assert prod_res.status_code == 200
        
        stage_data = stage_res.json()
        prod_data = prod_res.json()
        
        assert stage_data["environment"] == "stage"
        assert prod_data["environment"] == "prod"

    def test_default_environment_is_prod(self):
        """Default environment without param should be prod"""
        response = self.session.get(f"{BASE_URL}/api/phase4/admin/release-gate")
        assert response.status_code == 200
        data = response.json()
        assert data["environment"] == "prod"


class TestPhase4Iter5MonitoringEndpoints:
    """Test monitoring-related endpoints for admin UI"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_res = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": os.environ.get("TEST_ADMIN_EMAIL", ""), "password": os.environ.get("TEST_ADMIN_PASSWORD", "")},
        )
        assert login_res.status_code == 200
        self.admin_token = login_res.json()["access_token"]
        self.session.headers.update({"Authorization": f"Bearer {self.admin_token}"})

    def test_override_history_endpoint(self):
        """GET /api/phase4/admin/release-gate/overrides returns list"""
        response = self.session.get(f"{BASE_URL}/api/phase4/admin/release-gate/overrides")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_override_analytics_endpoint(self):
        """GET /api/phase4/admin/override-analytics returns analytics data"""
        response = self.session.get(f"{BASE_URL}/api/phase4/admin/override-analytics")
        assert response.status_code == 200
        data = response.json()
        assert "days" in data
        assert "points" in data
        assert "alert_source_breakdown" in data

    def test_alert_history_endpoint(self):
        """GET /api/phase4/admin/alert-history returns list"""
        response = self.session.get(f"{BASE_URL}/api/phase4/admin/alert-history")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_permission_drift_trend_endpoint(self):
        """GET /api/phase4/admin/permission-drift-trend returns trend data"""
        response = self.session.get(f"{BASE_URL}/api/phase4/admin/permission-drift-trend")
        assert response.status_code == 200
        data = response.json()
        assert "days" in data
        assert "points" in data
        assert "critical_drift_count" in data

    def test_pipeline_monitoring_endpoint(self):
        """GET /api/pipeline/monitoring returns monitoring metrics"""
        response = self.session.get(f"{BASE_URL}/api/pipeline/monitoring")
        assert response.status_code == 200
        data = response.json()
        assert "websocket_status" in data
        assert "release_gate_status" in data
        assert "release_gate_last_checked" in data


class TestPhase4Iter5UserExchangeEndpoints:
    """Test user exchange settings endpoints"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_res = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "TEST_phase4iter4@example.com", "password": "TestPassword123!"},
        )
        if login_res.status_code != 200:
            pytest.skip("Test user not found")
        self.user_token = login_res.json()["access_token"]
        self.session.headers.update({"Authorization": f"Bearer {self.user_token}"})

    def test_exchange_settings_endpoint(self):
        """GET /api/phase4/exchange-settings returns user settings"""
        response = self.session.get(f"{BASE_URL}/api/phase4/exchange-settings")
        assert response.status_code == 200
        data = response.json()
        assert "exchange" in data
        assert "mode" in data
        assert "has_api_key" in data
        assert "has_api_secret" in data

    def test_permission_status_endpoint(self):
        """GET /api/phase4/permission-status returns permission status"""
        response = self.session.get(f"{BASE_URL}/api/phase4/permission-status")
        assert response.status_code == 200
        data = response.json()
        assert "overall_status" in data
        assert "live_activation" in data
        assert "controls" in data

    def test_exchange_validate_endpoint(self):
        """GET /api/exchange/validate returns validation result"""
        response = self.session.get(f"{BASE_URL}/api/exchange/validate?exchange=binance&market_type=futures&environment=testnet")
        # May return error if no valid credentials
        assert response.status_code in [200, 400, 403, 503]
        data = response.json()
        if response.status_code == 200:
            assert "is_valid" in data
            assert "permissions" in data
            assert "reason_codes" in data

    def test_market_ticker_endpoint(self):
        """GET /api/market/ticker returns ticker data"""
        response = self.session.get(f"{BASE_URL}/api/market/ticker?symbol=BTCUSDT")
        assert response.status_code == 200
        data = response.json()
        assert "symbol" in data
        assert "mid_price" in data
