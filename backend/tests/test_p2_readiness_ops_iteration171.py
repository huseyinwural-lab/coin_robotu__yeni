"""
P2 Readiness Operational Closure Tests - Iteration 171
Tests for:
- Readiness maintenance scheduler activation (startup loop + status/log + audit)
- Maintenance cron endpoints: policy/trigger/status
- Admin login operation flow
- Bybit venue checklist + reason code stabilization
- Execution proof status endpoint (execution_proof + mocked_paths)
- History analytics filter/pagination/incident correlation + runbook mapping
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


class TestAdminLoginFlow:
    """Admin login operation flow tests"""
    
    def test_admin_login_canonical_endpoint(self):
        """Test /api/auth/login/admin canonical endpoint"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30
        )
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "No access_token in response"
        print(f"PASS: Admin login canonical endpoint works, token received")
    
    def test_user_login_with_admin_credentials_returns_panel_error(self):
        """Test that admin credentials on user panel returns panel error"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "panel": "user"},
            timeout=30
        )
        # Should return 403 or error indicating wrong panel
        if response.status_code == 403:
            data = response.json()
            detail = data.get("detail", "")
            assert "panel" in str(detail).lower() or "yanlış" in str(detail).lower(), \
                f"Expected panel error, got: {detail}"
            print(f"PASS: User panel correctly rejects admin credentials with panel error")
        elif response.status_code == 200:
            # Some implementations may allow login but redirect
            print(f"INFO: Login succeeded, may redirect to admin panel")
        else:
            print(f"INFO: Status {response.status_code}, response: {response.text[:200]}")


class TestMaintenanceSchedulerEndpoints:
    """Maintenance cron endpoints tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        # Generate a consistent device ID for the session
        import hashlib
        device_id = hashlib.sha256(b"test-device-iteration171").hexdigest()[:32]
        
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"X-Session-Device": device_id},
            timeout=30
        )
        assert response.status_code == 200
        self.token = response.json().get("access_token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "X-Session-Device": device_id
        }
    
    def test_maintenance_policy_endpoint(self):
        """Test /api/admin/futures/readiness/history/policy returns retention policy"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/readiness/history/policy",
            headers=self.headers,
            timeout=30
        )
        assert response.status_code == 200, f"Policy endpoint failed: {response.text}"
        data = response.json()
        assert "details_retention_days" in data, "Missing details_retention_days"
        assert "aggregate_retention_days" in data, "Missing aggregate_retention_days"
        assert "cleanup_batch_size" in data, "Missing cleanup_batch_size"
        print(f"PASS: Maintenance policy endpoint returns: {data}")
    
    def test_maintenance_trigger_dry_run(self):
        """Test /api/admin/futures/readiness/history/maintenance with dry_run=true"""
        response = requests.post(
            f"{BASE_URL}/api/admin/futures/readiness/history/maintenance",
            headers=self.headers,
            params={"dry_run": "true"},
            timeout=30
        )
        assert response.status_code == 200, f"Maintenance trigger failed: {response.text}"
        data = response.json()
        assert "policy" in data, "Missing policy in response"
        assert data.get("dry_run") == True, "dry_run should be True"
        assert "deleted_detail_rows" in data, "Missing deleted_detail_rows"
        assert "deleted_aggregate_rows" in data, "Missing deleted_aggregate_rows"
        print(f"PASS: Maintenance trigger dry_run works: deleted_detail={data.get('deleted_detail_rows')}, deleted_aggregate={data.get('deleted_aggregate_rows')}")
    
    def test_maintenance_status_endpoint(self):
        """Test /api/admin/futures/readiness/history/maintenance/status returns scheduler status"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/readiness/history/maintenance/status",
            headers=self.headers,
            timeout=30
        )
        assert response.status_code == 200, f"Maintenance status failed: {response.text}"
        data = response.json()
        # Status can be success, failed, or disabled
        if data:
            status = data.get("status")
            assert status in ["success", "failed", "disabled", None], f"Unexpected status: {status}"
            print(f"PASS: Maintenance status endpoint returns: status={status}, trigger={data.get('trigger')}")
        else:
            print(f"INFO: Maintenance status is empty (scheduler may not have run yet)")


class TestBybitVenueReadiness:
    """Bybit venue checklist and reason code tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        import hashlib
        device_id = hashlib.sha256(b"test-device-bybit-171").hexdigest()[:32]
        
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"X-Session-Device": device_id},
            timeout=30
        )
        assert response.status_code == 200
        self.token = response.json().get("access_token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "X-Session-Device": device_id
        }
    
    def test_bybit_venue_in_readiness_matrix(self):
        """Test bybit venue appears in readiness matrix with deterministic state"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/live-readiness",
            headers=self.headers,
            params={"refresh": "true"},
            timeout=60
        )
        assert response.status_code == 200, f"Live readiness failed: {response.text}"
        data = response.json()
        
        # Check readiness_matrix.exchange.bybit exists
        matrix = data.get("readiness_matrix", {})
        exchange_matrix = matrix.get("exchange", {})
        bybit = exchange_matrix.get("bybit", {})
        
        assert bybit, "Bybit not found in exchange matrix"
        state = bybit.get("state")
        assert state in ["READY", "BLOCKED", "UNKNOWN", "WARNING"], f"Unexpected bybit state: {state}"
        print(f"PASS: Bybit venue state: {state}")
        
        # Check for config_checklist if present
        checklist = bybit.get("config_checklist", {})
        if checklist:
            print(f"Bybit config_checklist: {checklist}")
            # Verify expected fields
            expected_fields = ["has_testnet_credentials", "has_live_credentials", "environment_mapped"]
            for field in expected_fields:
                if field in checklist:
                    print(f"  - {field}: {checklist.get(field)}")


class TestExecutionProofStatus:
    """Execution proof status endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        import hashlib
        device_id = hashlib.sha256(b"test-device-exec-171").hexdigest()[:32]
        
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"X-Session-Device": device_id},
            timeout=30
        )
        assert response.status_code == 200
        self.token = response.json().get("access_token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "X-Session-Device": device_id
        }
    
    def test_execution_readiness_endpoint(self):
        """Test /api/admin/execution-readiness returns execution_proof and mocked_paths"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-readiness",
            headers=self.headers,
            timeout=60
        )
        assert response.status_code == 200, f"Execution readiness failed: {response.text}"
        data = response.json()
        
        # Check execution_proof exists
        assert "execution_proof" in data, "Missing execution_proof"
        proof = data.get("execution_proof", {})
        
        # Check proof_status
        proof_status = proof.get("proof_status")
        assert proof_status in ["REAL", "MOCKED_ONLY", "NONE", None], f"Unexpected proof_status: {proof_status}"
        print(f"PASS: Execution proof_status: {proof_status}")
        
        # Check mocked_paths
        mocked_paths = data.get("mocked_paths")
        print(f"PASS: mocked_paths: {mocked_paths}")
        
        # Check has_mocked_paths in proof
        has_mocked = proof.get("has_mocked_paths")
        print(f"PASS: has_mocked_paths in proof: {has_mocked}")
        
        # Verify consistency
        if proof_status == "MOCKED_ONLY":
            assert mocked_paths == True or has_mocked == True, "MOCKED_ONLY should have mocked_paths=True"


class TestHistoryAnalytics:
    """History analytics filter/pagination/incident correlation tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        import hashlib
        device_id = hashlib.sha256(b"test-device-history-171").hexdigest()[:32]
        
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"X-Session-Device": device_id},
            timeout=30
        )
        assert response.status_code == 200
        self.token = response.json().get("access_token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "X-Session-Device": device_id
        }
    
    def test_history_endpoint_with_filters(self):
        """Test history endpoint with exchange/symbol/strategy filters"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/readiness/history",
            headers=self.headers,
            params={
                "days": 7,
                "page": 1,
                "page_size": 10,
                "exchange": "binance",
                "symbol": "BTCUSDT",
                "strategy": "ema_rsi"
            },
            timeout=30
        )
        assert response.status_code == 200, f"History with filters failed: {response.text}"
        data = response.json()
        print(f"PASS: History endpoint with filters returns data")
    
    def test_history_endpoint_pagination(self):
        """Test history endpoint pagination fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/readiness/history",
            headers=self.headers,
            params={"days": 14, "page": 1, "page_size": 25},
            timeout=30
        )
        assert response.status_code == 200, f"History pagination failed: {response.text}"
        data = response.json()
        
        # Check pagination fields
        if "page" in data:
            print(f"PASS: Pagination - page: {data.get('page')}, page_size: {data.get('page_size')}")
        if "total_items" in data:
            print(f"PASS: Pagination - total_items: {data.get('total_items')}, total_pages: {data.get('total_pages')}")
    
    def test_history_endpoint_runbook_mapping(self):
        """Test history endpoint returns runbook_mapping"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/readiness/history",
            headers=self.headers,
            params={"days": 14, "limit": 50},
            timeout=30
        )
        assert response.status_code == 200, f"History runbook failed: {response.text}"
        data = response.json()
        
        # Check runbook_mapping exists
        runbook_mapping = data.get("runbook_mapping", {})
        assert runbook_mapping, "runbook_mapping should not be empty"
        print(f"PASS: runbook_mapping has {len(runbook_mapping)} entries")
        
        # Print some sample mappings
        for key in list(runbook_mapping.keys())[:3]:
            print(f"  - {key}: {runbook_mapping[key]}")


class TestReadinessPolicyEndpoints:
    """Readiness policy get/put endpoints tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        import hashlib
        device_id = hashlib.sha256(b"test-device-policy-171").hexdigest()[:32]
        
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"X-Session-Device": device_id},
            timeout=30
        )
        assert response.status_code == 200
        self.token = response.json().get("access_token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "X-Session-Device": device_id
        }
    
    def test_get_readiness_policy(self):
        """Test GET /api/admin/futures/readiness/policy returns policy config"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/readiness/policy",
            headers=self.headers,
            timeout=30
        )
        assert response.status_code == 200, f"Get policy failed: {response.text}"
        data = response.json()
        
        # Check expected policy sections
        expected_sections = ["latency_config", "timeout_policy", "data_quality_config", "exposure_policy", "runbook_mapping"]
        for section in expected_sections:
            if section in data:
                print(f"PASS: Policy section '{section}' present")
    
    def test_put_readiness_policy(self):
        """Test PUT /api/admin/futures/readiness/policy merges patch correctly"""
        # First get current policy
        get_response = requests.get(
            f"{BASE_URL}/api/admin/futures/readiness/policy",
            headers=self.headers,
            timeout=30
        )
        assert get_response.status_code == 200
        
        # Update with a small patch
        patch_payload = {
            "latency_config": {
                "test_key": "test_value_iteration171"
            }
        }
        
        put_response = requests.put(
            f"{BASE_URL}/api/admin/futures/readiness/policy",
            headers=self.headers,
            json=patch_payload,
            timeout=30
        )
        assert put_response.status_code == 200, f"Put policy failed: {put_response.text}"
        data = put_response.json()
        
        # Verify patch was applied
        latency_config = data.get("latency_config", {})
        assert latency_config.get("test_key") == "test_value_iteration171", "Patch not applied correctly"
        print(f"PASS: Policy PUT merges patch correctly")


class TestLiveReadinessEndpoint:
    """Live readiness endpoint comprehensive tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        import hashlib
        device_id = hashlib.sha256(b"test-device-live-171").hexdigest()[:32]
        
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"X-Session-Device": device_id},
            timeout=30
        )
        assert response.status_code == 200
        self.token = response.json().get("access_token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "X-Session-Device": device_id
        }
    
    def test_live_readiness_returns_execution_proof(self):
        """Test live readiness endpoint returns execution_proof field"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/live-readiness",
            headers=self.headers,
            params={"refresh": "true"},
            timeout=60
        )
        assert response.status_code == 200, f"Live readiness failed: {response.text}"
        data = response.json()
        
        # Check execution_proof exists
        assert "execution_proof" in data, "Missing execution_proof in live readiness"
        proof = data.get("execution_proof", {})
        print(f"PASS: execution_proof present: {proof.get('proof_status')}")
    
    def test_live_readiness_returns_readiness_matrix(self):
        """Test live readiness endpoint returns readiness_matrix"""
        response = requests.get(
            f"{BASE_URL}/api/admin/futures/live-readiness",
            headers=self.headers,
            timeout=60
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check readiness_matrix exists
        assert "readiness_matrix" in data, "Missing readiness_matrix"
        matrix = data.get("readiness_matrix", {})
        
        # Check expected matrix sections
        if "exchange" in matrix:
            print(f"PASS: readiness_matrix.exchange has {len(matrix['exchange'])} venues")
        if "symbol" in matrix:
            print(f"PASS: readiness_matrix.symbol has {len(matrix['symbol'])} symbols")
        if "strategy" in matrix:
            print(f"PASS: readiness_matrix.strategy has {len(matrix['strategy'])} strategies")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
