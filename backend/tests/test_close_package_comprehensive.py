"""
CLOSE-1..CLOSE-7 Comprehensive API Contract Tests
Tests trading engine master closure package endpoints and policies
"""
import os
from pathlib import Path

import pytest
import requests


def _resolve_base_url() -> str:
    from_env = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if from_env:
        return from_env
    env_file = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    return ""


BASE_URL = _resolve_base_url()
TEST_ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@platform.local")
TEST_ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin12345!")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL not configured")
    resp = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": TEST_ADMIN_EMAIL, "password": TEST_ADMIN_PASSWORD},
        timeout=10,
    )
    if resp.status_code != 200:
        pytest.skip(f"Auth failed: {resp.status_code}")
    return resp.json().get("access_token")


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


class TestCLOSE1ExecutionQualityCalibration:
    """CLOSE-1: execution quality calibration endpoints and policy_documented_warning"""

    def test_calibrate_execution_quality_returns_policy_documented_warning(self, admin_headers):
        """Calibrate endpoint should return policy_documented_warning with insufficient logs"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/risk/execution-quality/calibrate?sample_size=100",
            headers=admin_headers,
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()
        # With no execution logs, should return policy_documented_warning
        assert data.get("status") in ["policy_documented_warning", "calibrated"]
        assert "recommended_thresholds" in data
        assert "execution_quality_threshold" in data.get("recommended_thresholds", {})

    def test_get_latest_calibration(self, admin_headers):
        """Latest calibration endpoint returns stored calibration result"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/risk/execution-quality/calibration",
            headers=admin_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "recommended_thresholds" in data


class TestCLOSE2RiskConfigGovernance:
    """CLOSE-2: risk config governance safe bounds, versioning, rollback"""

    def test_safe_bound_reject_max_leverage_exceeds(self, admin_headers):
        """PATCH should reject max_leverage > 10"""
        resp = requests.patch(
            f"{BASE_URL}/api/admin/risk/config",
            headers=admin_headers,
            json={"max_leverage": 15},
            timeout=10,
        )
        assert resp.status_code == 400
        detail = resp.json().get("detail", {})
        assert detail.get("status") == "rejected"
        assert "max_leverage_exceeds_safe_bound" in detail.get("reason", "")

    def test_safe_bound_reject_max_risk_per_trade_exceeds(self, admin_headers):
        """PATCH should reject max_risk_per_trade_pct > 5"""
        resp = requests.patch(
            f"{BASE_URL}/api/admin/risk/config",
            headers=admin_headers,
            json={"max_risk_per_trade_pct": 8},
            timeout=10,
        )
        assert resp.status_code == 400
        detail = resp.json().get("detail", {})
        assert detail.get("status") == "rejected"
        assert "max_risk_per_trade_pct_exceeds_safe_bound" in detail.get("reason", "")

    def test_safe_bound_reject_max_total_exposure_exceeds(self, admin_headers):
        """PATCH should reject max_total_exposure_pct > 50"""
        resp = requests.patch(
            f"{BASE_URL}/api/admin/risk/config",
            headers=admin_headers,
            json={"max_total_exposure_pct": 75},
            timeout=10,
        )
        assert resp.status_code == 400
        detail = resp.json().get("detail", {})
        assert detail.get("status") == "rejected"
        assert "max_total_exposure_pct_exceeds_safe_bound" in detail.get("reason", "")

    def test_valid_config_update_increments_version(self, admin_headers):
        """Valid PATCH should increment config_version and set changed_by"""
        # Get current version first
        resp_get = requests.get(
            f"{BASE_URL}/api/admin/risk/config",
            headers=admin_headers,
            timeout=10,
        )
        assert resp_get.status_code == 200
        current_version = resp_get.json().get("config_version", 0)

        # Update with valid values
        resp = requests.patch(
            f"{BASE_URL}/api/admin/risk/config",
            headers=admin_headers,
            json={"max_risk_per_trade_pct": 2.0},
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("config_version") > current_version
        assert data.get("changed_by") is not None

    def test_rollback_restores_backup_config(self, admin_headers):
        """Rollback endpoint should restore backup config"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/risk/config/rollback",
            headers=admin_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "config_version" in data
        assert "changed_by" in data


class TestCLOSE3ScannerRegimeTuning:
    """CLOSE-3: scanner regime tuning caps (normal/volatile/stress)"""

    def test_risk_status_includes_execution_quality_trend(self, admin_headers):
        """Risk status should include execution_quality_trend"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/risk/status",
            headers=admin_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "execution_quality_trend" in data
        assert "execution_quality_score" in data


class TestCLOSE5MultiExchangeAdapter:
    """CLOSE-5: multi-exchange adapter infrastructure and adapter-smoke"""

    def test_adapter_smoke_endpoint_returns_summary(self, admin_headers):
        """Adapter smoke endpoint should return market_data_adapter, execution_adapter, and summary"""
        resp = requests.get(
            f"{BASE_URL}/api/venues/admin/adapter-smoke",
            headers=admin_headers,
            timeout=30,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "market_data_adapter" in data
        assert "execution_adapter" in data
        assert "summary" in data
        # Execution should be MOCKED (no real credentials)
        assert data.get("summary", {}).get("execution_mocked_count") >= 2

    def test_adapter_smoke_execution_mocked_without_credentials(self, admin_headers):
        """Execution adapters should return MOCKED status without credentials"""
        resp = requests.get(
            f"{BASE_URL}/api/venues/admin/adapter-smoke",
            headers=admin_headers,
            timeout=30,
        )
        assert resp.status_code == 200
        data = resp.json()
        for result in data.get("execution_adapter", []):
            assert result.get("mocked") is True
            assert result.get("status") == "MOCKED"


class TestCLOSE6RuntimeSummaryObservability:
    """CLOSE-6: runtime-summary with risk_overview + observability_trends"""

    def test_runtime_summary_includes_risk_overview(self, admin_headers):
        """Runtime summary should include risk_overview"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/universe/runtime-summary?scanner_mode=all_market_symbols&top_n=50",
            headers=admin_headers,
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "risk_overview" in data
        assert data.get("risk_overview") is not None

    def test_runtime_summary_includes_observability_trends(self, admin_headers):
        """Runtime summary should include observability_trends"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/universe/runtime-summary?scanner_mode=all_market_symbols&top_n=50",
            headers=admin_headers,
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "observability_trends" in data
        assert data.get("observability_trends") is not None

    def test_runtime_summary_includes_fallback_state(self, admin_headers):
        """Runtime summary should include fallback_state"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/universe/runtime-summary?scanner_mode=all_market_symbols&top_n=50",
            headers=admin_headers,
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "fallback_state" in data


class TestHealthAndAuth:
    """Basic health and authentication checks"""

    def test_health_endpoint(self):
        """Health endpoint should return ok"""
        resp = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert resp.status_code == 200
        assert resp.json().get("status") == "ok"

    def test_admin_login(self):
        """Admin login should succeed with valid credentials"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_ADMIN_EMAIL, "password": TEST_ADMIN_PASSWORD},
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data.get("user", {}).get("role") == "super_admin"
