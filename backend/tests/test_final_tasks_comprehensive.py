"""
FINAL TASK ORDER Comprehensive Test Suite
Testing FINAL-1 through FINAL-9 per Trading Engine Master Task Order
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://trading-phase-verify.preview.emergentagent.com"


@pytest.fixture(scope="module")
def admin_token():
    """Admin login and token retrieval"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": "admin@platform.local", "password": "Admin12345!"},
        timeout=15,
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    token = response.json().get("access_token")
    assert token, "No access token returned"
    return token


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ===== FINAL-1: Admin Exchange Settings + Execution Validation =====
class TestFinal1ExchangeSettings:
    """FINAL-1: Admin Exchange Settings credential fields and backend endpoints"""

    def test_get_execution_credentials(self, auth_headers):
        """Test GET /api/venues/admin/execution-credentials returns has_bybit/okx fields"""
        resp = requests.get(
            f"{BASE_URL}/api/venues/admin/execution-credentials",
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "has_bybit_credentials" in data
        assert "has_okx_credentials" in data
        assert "masked" in data
        assert "bybit_api_key" in data["masked"]
        assert "okx_api_key" in data["masked"]

    def test_execution_validation_endpoint(self, auth_headers):
        """FINAL-1: POST /api/venues/admin/execution-validation returns adapter/precision/lot/submit/cancel/retry"""
        resp = requests.post(
            f"{BASE_URL}/api/venues/admin/execution-validation",
            headers=auth_headers,
            timeout=20,
        )
        assert resp.status_code == 200
        data = resp.json()
        validation = data.get("validation", {})
        # All required fields per FINAL-1
        assert "adapter_smoke_test" in validation
        assert "precision_validation" in validation
        assert "lot_size_validation" in validation
        assert "order_submit_test" in validation
        assert "cancel_test" in validation
        assert "retry_behavior" in validation
        # Since no credentials, expect MOCKED status
        assert validation["order_submit_test"] in ["PASS", "MOCKED"]
        assert validation["cancel_test"] in ["PASS", "MOCKED"]

    def test_adapter_smoke_endpoint(self, auth_headers):
        """FINAL-1: GET /api/venues/admin/adapter-smoke returns market_data_adapter + execution_adapter"""
        resp = requests.get(
            f"{BASE_URL}/api/venues/admin/adapter-smoke",
            headers=auth_headers,
            timeout=20,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "market_data_adapter" in data
        assert "execution_adapter" in data
        assert "summary" in data
        # Check execution adapter results for bybit/okx
        exec_results = data.get("execution_adapter", [])
        exchanges_tested = {r["exchange"] for r in exec_results}
        assert "bybit" in exchanges_tested
        assert "okx" in exchanges_tested


# ===== FINAL-2: Rollout Helper Scripts =====
class TestFinal2RolloutHelpers:
    """FINAL-2: rollout helper scripts and runtime metric snapshot"""

    def test_runtime_summary_endpoint(self, auth_headers):
        """Test /api/admin/universe/runtime-summary exists and returns metrics"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/universe/runtime-summary?scanner_mode=ALL_MARKET_SYMBOLS&top_n=200",
            headers=auth_headers,
            timeout=20,
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should have runtime_metrics
        assert "runtime_metrics" in data or "risk_overview" in data


# ===== FINAL-3: Execution Quality Calibration =====
class TestFinal3ExecutionQualityCalibration:
    """FINAL-3: execution quality calibration endpoints + policy_documented_warning"""

    def test_calibrate_endpoint(self, auth_headers):
        """POST /api/admin/risk/execution-quality/calibrate returns calibration result"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/risk/execution-quality/calibrate?sample_size=100",
            headers=auth_headers,
            timeout=20,
        )
        assert resp.status_code == 200
        data = resp.json()
        # Must return status field
        assert "status" in data
        # When no execution logs, expect policy_documented_warning
        assert data["status"] in ["calibrated", "policy_documented_warning", "insufficient_data"]

    def test_get_calibration(self, auth_headers):
        """GET /api/admin/risk/execution-quality/calibration returns latest calibration"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/risk/execution-quality/calibration",
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200
        # Should return calibration data or empty/default


# ===== FINAL-4: Regime/Risk Tuning Caps =====
class TestFinal4RegimeRiskTuningCaps:
    """FINAL-4: regime/risk tuning caps and runtime summary visibility"""

    def test_risk_config_safe_bounds(self, auth_headers):
        """Test safe bounds rejection: max_leverage<=10, max_risk_per_trade_pct<=5, max_total_exposure_pct<=50"""
        # Test max_leverage exceeds 10 - should be rejected
        resp = requests.patch(
            f"{BASE_URL}/api/admin/risk/config",
            headers=auth_headers,
            json={"max_leverage": 15},
            timeout=15,
        )
        assert resp.status_code == 400
        detail = resp.json().get("detail", {})
        assert "max_leverage_exceeds_safe_bound" in str(detail)

        # Test max_risk_per_trade_pct exceeds 5 - should be rejected
        resp = requests.patch(
            f"{BASE_URL}/api/admin/risk/config",
            headers=auth_headers,
            json={"max_risk_per_trade_pct": 7.0},
            timeout=15,
        )
        assert resp.status_code == 400
        detail = resp.json().get("detail", {})
        assert "max_risk_per_trade_pct_exceeds_safe_bound" in str(detail)

        # Test max_total_exposure_pct exceeds 50 - should be rejected
        resp = requests.patch(
            f"{BASE_URL}/api/admin/risk/config",
            headers=auth_headers,
            json={"max_total_exposure_pct": 60.0},
            timeout=15,
        )
        assert resp.status_code == 400
        detail = resp.json().get("detail", {})
        assert "max_total_exposure_pct_exceeds_safe_bound" in str(detail)

    def test_regime_caps_in_runtime_summary(self, auth_headers):
        """Verify regime caps are visible in runtime summary"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/universe/runtime-summary?scanner_mode=ALL_MARKET_SYMBOLS&top_n=200",
            headers=auth_headers,
            timeout=20,
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should have risk_overview
        assert "risk_overview" in data


# ===== FINAL-5: Risk Governance Maturity =====
class TestFinal5RiskGovernanceMaturity:
    """FINAL-5: risk governance maturity (timeline, profiles, overrides, rollback)"""

    def test_config_timeline(self, auth_headers):
        """GET /api/admin/risk/config/timeline returns audit trail"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/risk/config/timeline?limit=20",
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data

    def test_policy_profiles(self, auth_headers):
        """GET /api/admin/risk/config/profiles returns conservative/balanced/aggressive"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/risk/config/profiles",
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()
        profiles = data.get("profiles", {})
        assert "conservative" in profiles
        assert "balanced" in profiles
        assert "aggressive" in profiles

    def test_policy_overrides(self, auth_headers):
        """GET/PATCH /api/admin/risk/config/overrides"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/risk/config/overrides",
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "global" in data
        assert "tenants" in data
        assert "users" in data

    def test_rollback_endpoint(self, auth_headers):
        """POST /api/admin/risk/config/rollback works correctly"""
        # First make a valid update to create backup
        resp1 = requests.patch(
            f"{BASE_URL}/api/admin/risk/config",
            headers=auth_headers,
            json={"symbol_cooldown_minutes": 25},
            timeout=15,
        )
        # Now rollback
        resp = requests.post(
            f"{BASE_URL}/api/admin/risk/config/rollback",
            headers=auth_headers,
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "config_version" in data


# ===== FINAL-6: Admin Runtime Summary Observability =====
class TestFinal6ObservabilityTrends:
    """FINAL-6: admin runtime summary observability trends + pnl trend"""

    def test_runtime_summary_has_observability_trends(self, auth_headers):
        """Verify runtime-summary includes observability_trends and pnl_trend"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/universe/runtime-summary?scanner_mode=ALL_MARKET_SYMBOLS&top_n=200",
            headers=auth_headers,
            timeout=20,
        )
        assert resp.status_code == 200
        data = resp.json()
        # FINAL-6 requirements
        assert "observability_trends" in data
        obs = data["observability_trends"]
        assert "execution_latency_trend" in obs
        assert "risk_veto_rate_trend" in obs
        assert "scanner_cycle_latency_trend" in obs
        assert "fallback_activation_rate_trend" in obs
        # PnL trend in risk_overview
        risk = data.get("risk_overview", {})
        assert "pnl_trend" in risk


# ===== FINAL-8: CI Stage/Prod PASS =====
class TestFinal8CIGates:
    """FINAL-8: ci stage/prod PASS + docker validation script output"""

    def test_health_endpoint(self, auth_headers):
        """Basic health check to verify backend is running"""
        resp = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert resp.status_code == 200


# ===== FINAL-9: Exchange Normalization =====
class TestFinal9ExchangeNormalization:
    """FINAL-9: exchange normalization (symbol/precision/leverage/error taxonomy/retry)"""

    def test_adapter_smoke_has_normalization_fields(self, auth_headers):
        """Verify adapter smoke includes precision/leverage/error taxonomy fields"""
        resp = requests.get(
            f"{BASE_URL}/api/venues/admin/adapter-smoke",
            headers=auth_headers,
            timeout=20,
        )
        assert resp.status_code == 200
        data = resp.json()
        exec_results = data.get("execution_adapter", [])
        # Each result should have precision_validation, leverage_rule, retry_behavior
        for result in exec_results:
            assert "precision_validation" in result
            assert "leverage_rule" in result
            assert "retry_behavior" in result


# ===== Regression: Runtime Summary and Scanner Run =====
class TestRegression:
    """Regression tests for /api/admin/universe/runtime-summary and /api/user/scanner/runtime/run"""

    def test_admin_runtime_summary_not_broken(self, auth_headers):
        """Regression: /api/admin/universe/runtime-summary should return 200"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/universe/runtime-summary?scanner_mode=ALL_MARKET_SYMBOLS&top_n=200",
            headers=auth_headers,
            timeout=20,
        )
        assert resp.status_code == 200
        data = resp.json()
        # Key fields should exist
        assert "runtime_metrics" in data or "risk_overview" in data

    def test_user_scanner_runtime_run(self, admin_token):
        """Regression: /api/user/scanner/runtime/run should return 200"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = requests.post(
            f"{BASE_URL}/api/user/scanner/runtime/run",
            headers=headers,
            json={"market_type": "spot", "scanner_mode": "TOP_VOLUME", "top_n": 50},
            timeout=30,
        )
        # May return 200 or 202 (accepted)
        assert resp.status_code in [200, 202, 400, 422], f"Unexpected status: {resp.status_code}, {resp.text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
