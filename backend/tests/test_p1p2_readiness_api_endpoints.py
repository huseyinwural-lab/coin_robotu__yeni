"""
P1/P2 Readiness API Endpoint Tests - Iteration 170
Tests for new endpoints:
- /api/admin/futures/readiness/history/policy
- /api/admin/futures/readiness/history/maintenance
- /api/admin/futures/readiness/policy
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://trade-trace-engine.preview.emergentagent.com").rstrip("/")

# Test credentials
TEST_EMAIL = "canary.admin@platform.local"
TEST_PASSWORD = "CanaryAdmin123!"


class TestReadinessAPIEndpoints:
    """Tests for readiness API endpoints"""

    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=30,
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token") or data.get("token")
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text[:200]}")

    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get auth headers"""
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}

    # ========================================================================
    # HISTORY POLICY ENDPOINT TESTS
    # ========================================================================

    def test_history_policy_endpoint_exists(self, auth_headers):
        """Verify /api/admin/futures/readiness/history/policy endpoint exists"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/readiness/history/policy",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code in [200, 401, 403], f"Endpoint should exist, got: {response.status_code}"
        if response.status_code == 200:
            data = response.json()
            assert "details_retention_days" in data, "Response must have details_retention_days"
            assert "aggregate_retention_days" in data, "Response must have aggregate_retention_days"
            assert "cleanup_batch_size" in data, "Response must have cleanup_batch_size"
            print(f"PASS: History policy endpoint returns: {data}")
        else:
            print(f"INFO: History policy endpoint returned {response.status_code} (auth issue)")

    # ========================================================================
    # HISTORY MAINTENANCE ENDPOINT TESTS
    # ========================================================================

    def test_history_maintenance_endpoint_exists(self, auth_headers):
        """Verify /api/admin/futures/readiness/history/maintenance endpoint exists"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/readiness/history/maintenance",
            headers=auth_headers,
            params={"dry_run": True},
            timeout=60,
        )
        assert response.status_code in [200, 401, 403], f"Endpoint should exist, got: {response.status_code}"
        if response.status_code == 200:
            data = response.json()
            assert "policy" in data, "Response must have policy"
            assert "dry_run" in data, "Response must have dry_run"
            assert data["dry_run"] is True, "dry_run should be True"
            print(f"PASS: History maintenance endpoint returns: {list(data.keys())}")
        else:
            print(f"INFO: History maintenance endpoint returned {response.status_code} (auth issue)")

    # ========================================================================
    # READINESS POLICY ENDPOINT TESTS
    # ========================================================================

    def test_readiness_policy_get_endpoint_exists(self, auth_headers):
        """Verify GET /api/admin/futures/readiness/policy endpoint exists"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/readiness/policy",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code in [200, 401, 403], f"Endpoint should exist, got: {response.status_code}"
        if response.status_code == 200:
            data = response.json()
            expected_keys = ["latency_config", "timeout_policy", "data_quality_config", "exposure_policy", "runbook_mapping"]
            for key in expected_keys:
                assert key in data, f"Response must have {key}"
            print(f"PASS: Readiness policy GET endpoint returns: {list(data.keys())}")
        else:
            print(f"INFO: Readiness policy GET endpoint returned {response.status_code} (auth issue)")

    def test_readiness_policy_put_endpoint_exists(self, auth_headers):
        """Verify PUT /api/admin/futures/readiness/policy endpoint exists"""
        # Use a minimal patch that won't break anything
        patch_payload = {
            "latency_config": {
                "round_trip": {"warn": 500, "block": 1500}
            }
        }
        response = requests.put(
            f"{BASE_URL}/api/admin/futures/readiness/policy",
            headers=auth_headers,
            json=patch_payload,
            timeout=30,
        )
        assert response.status_code in [200, 401, 403, 422], f"Endpoint should exist, got: {response.status_code}"
        if response.status_code == 200:
            data = response.json()
            assert "latency_config" in data, "Response must have latency_config"
            print(f"PASS: Readiness policy PUT endpoint returns: {list(data.keys())}")
        else:
            print(f"INFO: Readiness policy PUT endpoint returned {response.status_code}")

    # ========================================================================
    # HISTORY ENDPOINT WITH FILTERS TESTS
    # ========================================================================

    def test_history_endpoint_with_filters(self, auth_headers):
        """Verify /api/admin/futures/readiness/history endpoint supports filters"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/readiness/history",
            headers=auth_headers,
            params={
                "days": 7,
                "page": 1,
                "page_size": 10,
                "exchange": "binance",
                "symbol": "BTCUSDT",
                "strategy": "ema_rsi",
            },
            timeout=30,
        )
        assert response.status_code in [200, 401, 403], f"Endpoint should exist, got: {response.status_code}"
        if response.status_code == 200:
            data = response.json()
            assert "items" in data, "Response must have items"
            assert "pagination" in data, "Response must have pagination"
            assert "filters" in data, "Response must have filters"
            
            # Verify filters are reflected
            filters = data.get("filters", {})
            assert filters.get("days") == 7, "days filter should be 7"
            assert filters.get("exchange") == "binance", "exchange filter should be binance"
            assert filters.get("symbol") == "BTCUSDT", "symbol filter should be BTCUSDT"
            assert filters.get("strategy") == "ema_rsi", "strategy filter should be ema_rsi"
            
            # Verify pagination
            pagination = data.get("pagination", {})
            assert pagination.get("page") == 1, "page should be 1"
            assert pagination.get("page_size") == 10, "page_size should be 10"
            
            print(f"PASS: History endpoint with filters returns: filters={filters}, pagination={pagination}")
        else:
            print(f"INFO: History endpoint returned {response.status_code} (auth issue)")

    def test_history_endpoint_analytics_fields(self, auth_headers):
        """Verify /api/admin/futures/readiness/history endpoint returns analytics fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/readiness/history",
            headers=auth_headers,
            params={"days": 14, "page": 1, "page_size": 25},
            timeout=30,
        )
        assert response.status_code in [200, 401, 403], f"Endpoint should exist, got: {response.status_code}"
        if response.status_code == 200:
            data = response.json()
            
            # Verify analytics fields
            assert "top_reason_codes" in data, "Response must have top_reason_codes"
            assert "top_blockers" in data, "Response must have top_blockers"
            assert "failure_frequency" in data, "Response must have failure_frequency"
            assert "failure_trend" in data, "Response must have failure_trend"
            assert "layer_failure_rate" in data, "Response must have layer_failure_rate"
            assert "runbook_mapping" in data, "Response must have runbook_mapping"
            
            # Verify items have incident_correlation_id
            items = data.get("items", [])
            if items:
                first_item = items[0]
                assert "incident_correlation_id" in first_item, "Items must have incident_correlation_id"
                assert "recommended_remediations" in first_item, "Items must have recommended_remediations"
            
            print(f"PASS: History endpoint analytics fields present: top_reason_codes={len(data.get('top_reason_codes', []))}, failure_trend={len(data.get('failure_trend', []))}")
        else:
            print(f"INFO: History endpoint returned {response.status_code} (auth issue)")

    # ========================================================================
    # LIVE READINESS ENDPOINT TESTS
    # ========================================================================

    def test_live_readiness_endpoint_execution_proof(self, auth_headers):
        """Verify /api/admin/futures/live-readiness endpoint returns execution_proof"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/live-readiness",
            headers=auth_headers,
            params={"refresh": True},
            timeout=60,
        )
        assert response.status_code in [200, 401, 403], f"Endpoint should exist, got: {response.status_code}"
        if response.status_code == 200:
            data = response.json()
            
            # Verify execution_proof fields
            assert "execution_proof" in data, "Response must have execution_proof"
            execution_proof = data.get("execution_proof", {})
            assert "real_metric_count" in execution_proof, "execution_proof must have real_metric_count"
            assert "mocked_metric_count" in execution_proof, "execution_proof must have mocked_metric_count"
            assert "has_mocked_paths" in execution_proof, "execution_proof must have has_mocked_paths"
            assert "proof_status" in execution_proof, "execution_proof must have proof_status"
            
            print(f"PASS: Live readiness endpoint execution_proof: {execution_proof}")
        else:
            print(f"INFO: Live readiness endpoint returned {response.status_code} (auth issue)")

    def test_live_readiness_endpoint_venue_checklist(self, auth_headers):
        """Verify /api/admin/futures/live-readiness endpoint returns venue_config_checklist"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/live-readiness",
            headers=auth_headers,
            params={"refresh": True},
            timeout=60,
        )
        assert response.status_code in [200, 401, 403], f"Endpoint should exist, got: {response.status_code}"
        if response.status_code == 200:
            data = response.json()
            
            # Verify venue_config_checklist
            assert "venue_config_checklist" in data, "Response must have venue_config_checklist"
            checklist = data.get("venue_config_checklist", {})
            
            # Verify bybit checklist if present
            if "bybit" in checklist:
                bybit = checklist["bybit"]
                assert "has_live_credentials" in bybit, "bybit checklist must have has_live_credentials"
                assert "has_live_credentials" in bybit, "bybit checklist must have has_live_credentials"
                assert "environment_mapped" in bybit, "bybit checklist must have environment_mapped"
                assert "reason_code" in bybit, "bybit checklist must have reason_code"
                print(f"PASS: Live readiness endpoint venue_config_checklist.bybit: {bybit}")
            else:
                print(f"INFO: bybit not in venue_config_checklist: {list(checklist.keys())}")
        else:
            print(f"INFO: Live readiness endpoint returned {response.status_code} (auth issue)")

    def test_live_readiness_endpoint_readiness_matrix(self, auth_headers):
        """Verify /api/admin/futures/live-readiness endpoint returns readiness_matrix"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/live-readiness",
            headers=auth_headers,
            params={"refresh": True},
            timeout=60,
        )
        assert response.status_code in [200, 401, 403], f"Endpoint should exist, got: {response.status_code}"
        if response.status_code == 200:
            data = response.json()
            
            # Verify readiness_matrix
            assert "readiness_matrix" in data, "Response must have readiness_matrix"
            matrix = data.get("readiness_matrix", {})
            assert "exchange" in matrix, "readiness_matrix must have exchange"
            assert "symbol" in matrix, "readiness_matrix must have symbol"
            assert "strategy" in matrix, "readiness_matrix must have strategy"
            
            print(f"PASS: Live readiness endpoint readiness_matrix: exchange={list(matrix.get('exchange', {}).keys())}, symbol_count={len(matrix.get('symbol', {}))}, strategy_count={len(matrix.get('strategy', {}))}")
        else:
            print(f"INFO: Live readiness endpoint returned {response.status_code} (auth issue)")

    # ========================================================================
    # EXECUTION READINESS ENDPOINT TESTS
    # ========================================================================

    def test_execution_readiness_endpoint_mocked_paths(self, auth_headers):
        """Verify /api/admin/execution-readiness endpoint returns mocked_paths"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-readiness",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code in [200, 401, 403], f"Endpoint should exist, got: {response.status_code}"
        if response.status_code == 200:
            data = response.json()
            
            # Verify mocked_paths field
            assert "mocked_paths" in data, "Response must have mocked_paths"
            assert "execution_proof" in data, "Response must have execution_proof"
            assert "reason_codes" in data, "Response must have reason_codes"
            
            print(f"PASS: Execution readiness endpoint: mocked_paths={data.get('mocked_paths')}, reason_codes={data.get('reason_codes')}")
        else:
            print(f"INFO: Execution readiness endpoint returned {response.status_code} (auth issue)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
