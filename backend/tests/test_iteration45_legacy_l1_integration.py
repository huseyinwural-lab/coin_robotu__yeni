"""
Test Suite: Phase L1 Integration Testing (iteration_45)
Features tested:
- POST /api/admin/futures/strategy/run-paper-cycle: legacy_formula_observability field populated
- 4 canonical strategies: momentum_volume_breakout_v3, volatility_breakout_v2, adaptive_level_breakout_v2, oscillator_composite_reversion_v2
- 3+ prefilters/scanners: crypto_universe_prefilter_v1, volatility_contraction_prefilter, relative_strength_cluster_scanner_v2
- Legacy strategy lifecycle state DISABLED with allowed_total=0 (shadow only lock)
- New metric columns: family_code, source_type=legacy_formula, shadow_status, signal_frequency, shadow_pnl, false_breakout_rate, confidence_drift
- Regression: /api/admin/futures/strategy-performance, /api/admin/futures/strategy-execution-quality, /api/admin/futures/strategy-governance return 200
"""

import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")

LEGACY_STRATEGY_IDS = {
    "momentum_volume_breakout_v3",
    "volatility_breakout_v2",
    "adaptive_level_breakout_v2",
    "oscillator_composite_reversion_v2",
}
LEGACY_PREFILTER_IDS = {
    "crypto_universe_prefilter_v1",
    "volatility_contraction_prefilter",
    "relative_strength_cluster_scanner_v2",
    "relative_strength_cluster_scanner_v2_alt",
}
REQUIRED_LEGACY_METRIC_FIELDS = {
    "strategy",
    "family_code",
    "source_type",
    "shadow_status",
    "signal_frequency",
    "shadow_pnl",
    "false_breakout_rate",
    "confidence_drift",
}


@pytest.fixture(scope="module")
def admin_headers():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL not set")
    login = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    if login.status_code != 200:
        pytest.skip(f"Admin login failed: {login.text}")
    token = login.json().get("access_token")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


class TestRunPaperCycleLegacyObservability:
    """Verify POST /api/admin/futures/strategy/run-paper-cycle returns legacy_formula_observability"""
    
    def test_run_paper_cycle_returns_200(self, admin_headers):
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        payload = response.json()
        assert "legacy_formula_observability" in payload, "Missing legacy_formula_observability field"
        assert isinstance(payload["legacy_formula_observability"], list), "legacy_formula_observability should be a list"
    
    def test_legacy_observability_has_4_canonical_strategies(self, admin_headers):
        """Verify 4 canonical strategy rows present"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        rows = payload.get("legacy_formula_observability", [])
        
        strategy_names = {row.get("strategy") for row in rows if row.get("role") == "strategy"}
        found_canonical = strategy_names & LEGACY_STRATEGY_IDS
        assert len(found_canonical) == 4, f"Expected 4 canonical strategies, found: {found_canonical}"
    
    def test_legacy_observability_has_prefilters_and_scanners(self, admin_headers):
        """Verify 3+ prefilter/scanner rows present"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        rows = payload.get("legacy_formula_observability", [])
        
        prefilter_scanner_rows = [
            row for row in rows
            if row.get("role") in ("prefilter", "scanner")
        ]
        assert len(prefilter_scanner_rows) >= 3, f"Expected 3+ prefilters/scanners, found {len(prefilter_scanner_rows)}"
        
        prefilter_names = {row.get("strategy") for row in prefilter_scanner_rows}
        expected_prefilters = {"crypto_universe_prefilter_v1", "volatility_contraction_prefilter", "relative_strength_cluster_scanner_v2"}
        assert expected_prefilters.issubset(prefilter_names), f"Missing expected prefilters: {expected_prefilters - prefilter_names}"
    
    def test_legacy_rows_have_required_metric_columns(self, admin_headers):
        """Verify family_code, source_type, shadow_status, signal_frequency, shadow_pnl, false_breakout_rate, confidence_drift columns"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        rows = payload.get("legacy_formula_observability", [])
        
        for row in rows:
            missing_fields = REQUIRED_LEGACY_METRIC_FIELDS - set(row.keys())
            assert not missing_fields, f"Row {row.get('strategy')} missing fields: {missing_fields}"
    
    def test_legacy_strategies_have_source_type_legacy_formula(self, admin_headers):
        """Verify source_type = legacy_formula for all legacy rows"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        rows = payload.get("legacy_formula_observability", [])
        
        for row in rows:
            assert row.get("source_type") == "legacy_formula", f"Row {row.get('strategy')} source_type is {row.get('source_type')}"
    
    def test_legacy_strategies_have_shadow_status_shadow_only(self, admin_headers):
        """Verify shadow_status = SHADOW_ONLY for all legacy rows"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        rows = payload.get("legacy_formula_observability", [])
        
        for row in rows:
            assert row.get("shadow_status") == "SHADOW_ONLY", f"Row {row.get('strategy')} shadow_status is {row.get('shadow_status')}"


class TestLegacyStrategyLifecycleLock:
    """Verify legacy strategies are DISABLED with allowed_total=0 (shadow only lock)"""
    
    def test_legacy_strategy_lifecycle_state_disabled(self, admin_headers):
        """Verify lifecycle_state = DISABLED for all 4 canonical strategies"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        
        lifecycle_rows = payload.get("lifecycle_state", [])
        lifecycle_map = {row.get("strategy"): row.get("lifecycle_state") for row in lifecycle_rows}
        
        for strategy_id in LEGACY_STRATEGY_IDS:
            assert strategy_id in lifecycle_map, f"Strategy {strategy_id} not in lifecycle_state"
            assert lifecycle_map[strategy_id] == "DISABLED", f"Strategy {strategy_id} lifecycle_state is {lifecycle_map[strategy_id]}"
    
    def test_legacy_strategy_allowed_total_is_zero(self, admin_headers):
        """Verify allowed_total = 0 for all 4 canonical strategies (shadow only - no live orders)"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        
        signal_distribution = payload.get("strategy_signal_distribution", [])
        signal_map = {row.get("strategy"): row for row in signal_distribution}
        
        for strategy_id in LEGACY_STRATEGY_IDS:
            assert strategy_id in signal_map, f"Strategy {strategy_id} not in signal_distribution"
            allowed_total = int(signal_map[strategy_id].get("allowed_total", -1))
            assert allowed_total == 0, f"Strategy {strategy_id} allowed_total is {allowed_total}, expected 0"
    
    def test_legacy_strategy_disable_state(self, admin_headers):
        """Verify disable_state = DISABLED for legacy strategies"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        payload = response.json()
        
        disable_rows = payload.get("disable_state", [])
        disable_map = {row.get("strategy"): row for row in disable_rows}
        
        for strategy_id in LEGACY_STRATEGY_IDS:
            assert strategy_id in disable_map, f"Strategy {strategy_id} not in disable_state"
            assert disable_map[strategy_id].get("disable_state") == "DISABLED", \
                f"Strategy {strategy_id} disable_state is {disable_map[strategy_id].get('disable_state')}"


class TestRegressionAdminFuturesEndpoints:
    """Regression tests: /api/admin/futures/strategy-performance, strategy-execution-quality, strategy-governance return 200"""
    
    def test_strategy_performance_endpoint_returns_200(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-performance",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        payload = response.json()
        # Verify key fields exist
        assert "strategy_registry" in payload
        assert "legacy_formula_observability" in payload
        assert "strategy_signal_distribution" in payload
    
    def test_strategy_execution_quality_endpoint_returns_200(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-execution-quality",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        payload = response.json()
        # Verify key fields exist
        assert "legacy_formula_observability" in payload
        assert "strategy_execution_quality" in payload
        assert "rolling_7d_tuning_score" in payload
    
    def test_strategy_governance_endpoint_returns_200(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-governance",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        payload = response.json()
        # Verify key fields exist
        assert "legacy_formula_observability" in payload
        assert "lifecycle_state" in payload
        assert "disable_state" in payload
    
    def test_strategy_health_endpoint_returns_200(self, admin_headers):
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/strategy-health",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        payload = response.json()
        assert "strategy_health_score" in payload
        assert "legacy_formula_observability" in payload


class TestLegacyFormulaMetricValues:
    """Verify legacy metric columns have correct data types"""
    
    def test_signal_frequency_is_integer(self, admin_headers):
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        rows = response.json().get("legacy_formula_observability", [])
        
        for row in rows:
            assert isinstance(row.get("signal_frequency"), int), \
                f"signal_frequency should be int for {row.get('strategy')}"
    
    def test_shadow_pnl_is_numeric(self, admin_headers):
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        rows = response.json().get("legacy_formula_observability", [])
        
        for row in rows:
            assert isinstance(row.get("shadow_pnl"), (int, float)), \
                f"shadow_pnl should be numeric for {row.get('strategy')}"
    
    def test_false_breakout_rate_is_numeric(self, admin_headers):
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        rows = response.json().get("legacy_formula_observability", [])
        
        for row in rows:
            assert isinstance(row.get("false_breakout_rate"), (int, float)), \
                f"false_breakout_rate should be numeric for {row.get('strategy')}"
    
    def test_confidence_drift_is_numeric(self, admin_headers):
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        rows = response.json().get("legacy_formula_observability", [])
        
        for row in rows:
            assert isinstance(row.get("confidence_drift"), (int, float)), \
                f"confidence_drift should be numeric for {row.get('strategy')}"
    
    def test_family_code_is_string(self, admin_headers):
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        rows = response.json().get("legacy_formula_observability", [])
        
        for row in rows:
            assert row.get("family_code") is None or isinstance(row.get("family_code"), str), \
                f"family_code should be string for {row.get('strategy')}"


class TestPrefilterScannerDiagnostic:
    """Verify prefilter/scanner rows contain diagnostic field"""
    
    def test_prefilters_have_diagnostic_field(self, admin_headers):
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/strategy/run-paper-cycle",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        rows = response.json().get("legacy_formula_observability", [])
        
        prefilter_rows = [row for row in rows if row.get("role") in ("prefilter", "scanner")]
        for row in prefilter_rows:
            assert "diagnostic" in row, f"Prefilter {row.get('strategy')} missing diagnostic field"
            assert isinstance(row["diagnostic"], dict), f"diagnostic should be dict for {row.get('strategy')}"
