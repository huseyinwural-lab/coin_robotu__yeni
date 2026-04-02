"""
Iteration 128: P0 Chain Testing - Spot Live + Futures Test Flows
Tests:
1. GET /api/admin/commercial/p0/pnl/latest with market_types query (spot-only/futures-only)
2. GET /api/admin/commercial/p0/data-quality with required_market_types support
3. GET /api/admin/commercial/p0/live-gate with required_market_types=spot (credential_not_found regression fix)
4. Spot live chain calls should not return 500 (ingest/pnl/recon/data-quality/live-gate)
5. Futures test chain calls should not return 500 and live-gate should return calculation
6. Frontend trace drawer history: /audit-logs/timeline with last 10 traces
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")
    data = response.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip("No token in login response")
    return token


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers with admin auth token"""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }


@pytest.fixture(scope="module")
def test_user_id(admin_headers):
    """Get a test user ID for P0 chain testing"""
    # First try to get users list
    response = requests.get(
        f"{BASE_URL}/api/admin/users",
        headers=admin_headers,
        timeout=15
    )
    if response.status_code == 200:
        users = response.json()
        if isinstance(users, list) and len(users) > 0:
            # Return first user ID
            return users[0].get("id")
    
    # Fallback: use admin user's own ID from /me endpoint
    me_response = requests.get(
        f"{BASE_URL}/api/auth/me",
        headers=admin_headers,
        timeout=15
    )
    if me_response.status_code == 200:
        return me_response.json().get("id")
    
    pytest.skip("Could not get test user ID")


class TestP0PnlLatestMarketTypes:
    """Test GET /api/admin/commercial/p0/pnl/latest with market_types query"""
    
    def test_pnl_latest_spot_only(self, admin_headers, test_user_id):
        """Test PnL endpoint with spot-only market type"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/p0/pnl/latest",
            params={
                "target_user_id": test_user_id,
                "environment": "live",
                "market_types": ["spot"]
            },
            headers=admin_headers,
            timeout=30
        )
        # Should not return 500 - may return 400/404 if no credentials
        assert response.status_code != 500, f"Unexpected 500 error: {response.text}"
        print(f"PnL spot-only response: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            assert "status" in data
            print(f"PnL spot-only data: {data}")
    
    def test_pnl_latest_futures_only(self, admin_headers, test_user_id):
        """Test PnL endpoint with futures-only market type"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/p0/pnl/latest",
            params={
                "target_user_id": test_user_id,
                "environment": "live",
                "market_types": ["futures"]
            },
            headers=admin_headers,
            timeout=30
        )
        # Should not return 500
        assert response.status_code != 500, f"Unexpected 500 error: {response.text}"
        print(f"PnL futures-only response: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            assert "status" in data
            print(f"PnL futures-only data: {data}")
    
    def test_pnl_latest_both_markets(self, admin_headers, test_user_id):
        """Test PnL endpoint with both market types"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/p0/pnl/latest",
            params={
                "target_user_id": test_user_id,
                "environment": "live",
                "market_types": ["spot", "futures"]
            },
            headers=admin_headers,
            timeout=30
        )
        # Should not return 500
        assert response.status_code != 500, f"Unexpected 500 error: {response.text}"
        print(f"PnL both markets response: {response.status_code}")


class TestP0DataQualityMarketTypes:
    """Test GET /api/admin/commercial/p0/data-quality with required_market_types"""
    
    def test_data_quality_spot_only(self, admin_headers, test_user_id):
        """Test data-quality endpoint with spot-only"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/p0/data-quality",
            params={
                "target_user_id": test_user_id,
                "environment": "live",
                "required_market_types": ["spot"]
            },
            headers=admin_headers,
            timeout=30
        )
        # Should not return 500
        assert response.status_code != 500, f"Unexpected 500 error: {response.text}"
        print(f"Data quality spot-only response: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            assert "status" in data
            # Check freshness_seconds structure
            if "freshness_seconds" in data:
                print(f"Freshness seconds: {data['freshness_seconds']}")
    
    def test_data_quality_futures_only(self, admin_headers, test_user_id):
        """Test data-quality endpoint with futures-only"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/p0/data-quality",
            params={
                "target_user_id": test_user_id,
                "environment": "live",
                "required_market_types": ["futures"]
            },
            headers=admin_headers,
            timeout=30
        )
        # Should not return 500
        assert response.status_code != 500, f"Unexpected 500 error: {response.text}"
        print(f"Data quality futures-only response: {response.status_code}")


class TestP0LiveGateRegressionFix:
    """Test GET /api/admin/commercial/p0/live-gate credential_not_found regression fix"""
    
    def test_live_gate_spot_only_no_500(self, admin_headers, test_user_id):
        """Test live-gate with required_market_types=spot should not return 500"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/p0/live-gate",
            params={
                "target_user_id": test_user_id,
                "environment": "live",
                "required_market_types": ["spot"]
            },
            headers=admin_headers,
            timeout=30
        )
        # Critical: Should NOT return 500 (regression fix)
        assert response.status_code != 500, f"REGRESSION: live-gate spot-only returned 500: {response.text}"
        print(f"Live-gate spot-only response: {response.status_code}")
        
        # If 404, it's expected for credential_not_found
        if response.status_code == 404:
            data = response.json()
            detail = data.get("detail", "")
            print(f"Live-gate 404 detail: {detail}")
            # This is acceptable - credential not found is a valid response
        elif response.status_code == 200:
            data = response.json()
            assert "status" in data
            assert "live_transition_ready" in data
            print(f"Live-gate spot-only data: {data}")
    
    def test_live_gate_futures_live(self, admin_headers, test_user_id):
        """Test live-gate with futures live should return calculation"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/p0/live-gate",
            params={
                "target_user_id": test_user_id,
                "environment": "live",
                "required_market_types": ["futures"]
            },
            headers=admin_headers,
            timeout=30
        )
        # Should not return 500
        assert response.status_code != 500, f"Unexpected 500 error: {response.text}"
        print(f"Live-gate futures live response: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            assert "status" in data
            assert "live_transition_ready" in data
            assert "controls" in data
            print(f"Live-gate futures live controls: {data.get('controls')}")


class TestP0SpotLiveChain:
    """Test spot live chain calls should not return 500"""
    
    def test_spot_live_ingest_no_500(self, admin_headers, test_user_id):
        """Test spot live ingestion endpoint"""
        response = requests.post(
            f"{BASE_URL}/api/admin/commercial/p0/ingestion/rest-run",
            json={
                "target_user_id": test_user_id,
                "environment": "live",
                "market_types": ["spot"],
                "symbols": ["BTCUSDT"],
                "limit_per_symbol": 10
            },
            headers=admin_headers,
            timeout=60
        )
        # Should not return 500
        assert response.status_code != 500, f"Spot live ingest returned 500: {response.text}"
        print(f"Spot live ingest response: {response.status_code}")
    
    def test_spot_live_pnl_no_500(self, admin_headers, test_user_id):
        """Test spot live PnL endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/p0/pnl/latest",
            params={
                "target_user_id": test_user_id,
                "environment": "live",
                "market_types": ["spot"]
            },
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code != 500, f"Spot live PnL returned 500: {response.text}"
        print(f"Spot live PnL response: {response.status_code}")
    
    def test_spot_live_data_quality_no_500(self, admin_headers, test_user_id):
        """Test spot live data-quality endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/p0/data-quality",
            params={
                "target_user_id": test_user_id,
                "environment": "live",
                "required_market_types": ["spot"]
            },
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code != 500, f"Spot live data-quality returned 500: {response.text}"
        print(f"Spot live data-quality response: {response.status_code}")
    
    def test_spot_live_live_gate_no_500(self, admin_headers, test_user_id):
        """Test spot live live-gate endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/p0/live-gate",
            params={
                "target_user_id": test_user_id,
                "environment": "live",
                "required_market_types": ["spot"]
            },
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code != 500, f"Spot live live-gate returned 500: {response.text}"
        print(f"Spot live live-gate response: {response.status_code}")


class TestP0FuturesTestChain:
    """Test futures test chain calls should not return 500"""
    
    def test_futures_test_ingest_no_500(self, admin_headers, test_user_id):
        """Test futures live ingestion endpoint"""
        response = requests.post(
            f"{BASE_URL}/api/admin/commercial/p0/ingestion/rest-run",
            json={
                "target_user_id": test_user_id,
                "environment": "live",
                "market_types": ["futures"],
                "symbols": [],  # Futures can work without symbols
                "limit_per_symbol": 10
            },
            headers=admin_headers,
            timeout=60
        )
        # Should not return 500
        assert response.status_code != 500, f"Futures test ingest returned 500: {response.text}"
        print(f"Futures test ingest response: {response.status_code}")
    
    def test_futures_test_pnl_no_500(self, admin_headers, test_user_id):
        """Test futures live PnL endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/p0/pnl/latest",
            params={
                "target_user_id": test_user_id,
                "environment": "live",
                "market_types": ["futures"]
            },
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code != 500, f"Futures test PnL returned 500: {response.text}"
        print(f"Futures test PnL response: {response.status_code}")
    
    def test_futures_test_recon_no_500(self, admin_headers, test_user_id):
        """Test futures live reconciliation endpoint"""
        response = requests.post(
            f"{BASE_URL}/api/admin/commercial/p0/reconciliation/run",
            json={
                "target_user_id": test_user_id,
                "environment": "live",
                "market_types": ["futures"],
                "symbols": [],
                "limit_per_symbol": 10
            },
            headers=admin_headers,
            timeout=60
        )
        assert response.status_code != 500, f"Futures test recon returned 500: {response.text}"
        print(f"Futures test recon response: {response.status_code}")
    
    def test_futures_test_data_quality_no_500(self, admin_headers, test_user_id):
        """Test futures live data-quality endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/p0/data-quality",
            params={
                "target_user_id": test_user_id,
                "environment": "live",
                "required_market_types": ["futures"]
            },
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code != 500, f"Futures test data-quality returned 500: {response.text}"
        print(f"Futures test data-quality response: {response.status_code}")
    
    def test_futures_test_live_gate_returns_calculation(self, admin_headers, test_user_id):
        """Test futures live live-gate returns calculation"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/p0/live-gate",
            params={
                "target_user_id": test_user_id,
                "environment": "live",
                "required_market_types": ["futures"]
            },
            headers=admin_headers,
            timeout=30
        )
        assert response.status_code != 500, f"Futures test live-gate returned 500: {response.text}"
        print(f"Futures test live-gate response: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            # Verify live-gate calculation fields
            assert "live_transition_ready" in data, "Missing live_transition_ready field"
            assert "controls" in data, "Missing controls field"
            controls = data.get("controls", {})
            print(f"Live-gate controls: {controls}")
            # trade_ingest_ok may be false if no trades, but field should exist
            assert "trade_ingest_ok" in controls or "pnl_ok" in controls


class TestAuditLogsTimeline:
    """Test /audit-logs/timeline for trace history"""
    
    def test_audit_logs_timeline_endpoint(self, admin_headers):
        """Test audit-logs timeline endpoint returns data"""
        response = requests.get(
            f"{BASE_URL}/api/audit-logs/timeline",
            params={
                "action": "admin_credential_resolution_preview",
                "entity_type": "credential_resolution_trace",
                "limit": 10
            },
            headers=admin_headers,
            timeout=15
        )
        # Should not return 500
        assert response.status_code != 500, f"Audit logs timeline returned 500: {response.text}"
        print(f"Audit logs timeline response: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            # Check structure
            if "items" in data:
                items = data["items"]
                print(f"Audit logs timeline items count: {len(items)}")
                if items:
                    first_item = items[0]
                    print(f"First item keys: {list(first_item.keys())}")
    
    def test_audit_logs_timeline_with_query(self, admin_headers, test_user_id):
        """Test audit-logs timeline with user_id query"""
        response = requests.get(
            f"{BASE_URL}/api/audit-logs/timeline",
            params={
                "action": "admin_credential_resolution_preview",
                "entity_type": "credential_resolution_trace",
                "q": test_user_id,
                "limit": 10
            },
            headers=admin_headers,
            timeout=15
        )
        assert response.status_code != 500, f"Audit logs timeline with query returned 500: {response.text}"
        print(f"Audit logs timeline with query response: {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
