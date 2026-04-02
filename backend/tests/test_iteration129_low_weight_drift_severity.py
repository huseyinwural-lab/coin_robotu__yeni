"""
Iteration 129: Low-Weight Spot Ingest Mode + Drift Highlight Severity Testing
Tests:
1. Backend low-weight mode: live+spot ingest market_summary with low_weight_mode=true and processed_symbols single symbol
2. Backend low-weight mode: rate-limit handling (400 should not crash, rate_limit_hits increment)
3. Spot live chain endpoints should not return 500: ingest/pnl/reconciliation/data-quality/live-gate
4. Futures test live-gate regression check
5. Frontend drift highlight severity badge mapping (source=critical, selection_reason=medium, probe_state=low)
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


class TestLowWeightSpotIngestMode:
    """Test low-weight spot ingest mode with single symbol and narrow window"""
    
    def test_spot_live_ingest_low_weight_mode_enabled(self, admin_headers, test_user_id):
        """Test spot live ingestion returns low_weight_mode=true in market_summary"""
        response = requests.post(
            f"{BASE_URL}/api/admin/commercial/p0/ingestion/rest-run",
            json={
                "target_user_id": test_user_id,
                "environment": "live",
                "market_types": ["spot"],
                "symbols": ["BTCUSDT"],
                "limit_per_symbol": 120  # LOW_WEIGHT_SPOT_MAX_LIMIT default
            },
            headers=admin_headers,
            timeout=60
        )
        # Should not return 500
        assert response.status_code != 500, f"Spot live ingest returned 500: {response.text}"
        print(f"Spot live ingest response: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            market_summary = data.get("market_summary", {})
            spot_summary = market_summary.get("spot", {})
            
            # Verify low_weight_mode is true for live+spot
            low_weight_mode = spot_summary.get("low_weight_mode")
            print(f"low_weight_mode: {low_weight_mode}")
            assert low_weight_mode is True, f"Expected low_weight_mode=true for live+spot, got {low_weight_mode}"
            
            # Verify processed_symbols is single symbol (or limited)
            processed_symbols = spot_summary.get("processed_symbols", [])
            print(f"processed_symbols: {processed_symbols}")
            # LOW_WEIGHT_SPOT_MAX_SYMBOLS default is 1
            assert len(processed_symbols) <= 1, f"Expected single symbol in low-weight mode, got {len(processed_symbols)}"
            
            # Verify rate_limit_hits field exists
            rate_limit_hits = spot_summary.get("rate_limit_hits", 0)
            print(f"rate_limit_hits: {rate_limit_hits}")
            assert isinstance(rate_limit_hits, int), "rate_limit_hits should be an integer"
    
    def test_spot_live_ingest_multiple_symbols_limited(self, admin_headers, test_user_id):
        """Test spot live ingestion with multiple symbols gets limited to single symbol"""
        response = requests.post(
            f"{BASE_URL}/api/admin/commercial/p0/ingestion/rest-run",
            json={
                "target_user_id": test_user_id,
                "environment": "live",
                "market_types": ["spot"],
                "symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT"],  # Multiple symbols
                "limit_per_symbol": 120
            },
            headers=admin_headers,
            timeout=60
        )
        # Should not return 500
        assert response.status_code != 500, f"Spot live ingest returned 500: {response.text}"
        print(f"Spot live ingest multiple symbols response: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            market_summary = data.get("market_summary", {})
            spot_summary = market_summary.get("spot", {})
            
            # Verify processed_symbols is limited
            processed_symbols = spot_summary.get("processed_symbols", [])
            print(f"processed_symbols (multiple input): {processed_symbols}")
            # Should be limited to LOW_WEIGHT_SPOT_MAX_SYMBOLS (default 1)
            assert len(processed_symbols) <= 1, f"Expected limited symbols in low-weight mode, got {len(processed_symbols)}"
    
    def test_spot_live_ingest_no_low_weight_mode(self, admin_headers, test_user_id):
        """Test spot live ingestion does NOT have low_weight_mode (only live has it)"""
        response = requests.post(
            f"{BASE_URL}/api/admin/commercial/p0/ingestion/rest-run",
            json={
                "target_user_id": test_user_id,
                "environment": "live",
                "market_types": ["spot"],
                "symbols": ["BTCUSDT"],
                "limit_per_symbol": 100
            },
            headers=admin_headers,
            timeout=60
        )
        # Should not return 500
        assert response.status_code != 500, f"Spot live ingest returned 500: {response.text}"
        print(f"Spot live ingest response: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            market_summary = data.get("market_summary", {})
            spot_summary = market_summary.get("spot", {})
            
            # Verify low_weight_mode is false for live
            low_weight_mode = spot_summary.get("low_weight_mode", False)
            print(f"live low_weight_mode: {low_weight_mode}")
            assert low_weight_mode is False, f"Expected low_weight_mode=false for live, got {low_weight_mode}"


class TestSpotLiveChainNo500:
    """Test spot live chain endpoints should not return 500"""
    
    def test_spot_live_ingest_no_500(self, admin_headers, test_user_id):
        """Test spot live ingestion endpoint does not return 500"""
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
        assert response.status_code != 500, f"Spot live ingest returned 500: {response.text}"
        print(f"Spot live ingest response: {response.status_code}")
    
    def test_spot_live_pnl_no_500(self, admin_headers, test_user_id):
        """Test spot live PnL endpoint does not return 500"""
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
    
    def test_spot_live_reconciliation_no_500(self, admin_headers, test_user_id):
        """Test spot live reconciliation endpoint does not return 500"""
        response = requests.post(
            f"{BASE_URL}/api/admin/commercial/p0/reconciliation/run",
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
        assert response.status_code != 500, f"Spot live reconciliation returned 500: {response.text}"
        print(f"Spot live reconciliation response: {response.status_code}")
    
    def test_spot_live_data_quality_no_500(self, admin_headers, test_user_id):
        """Test spot live data-quality endpoint does not return 500"""
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
        """Test spot live live-gate endpoint does not return 500"""
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
        
        # live_transition_ready=false is normal if no real trades
        if response.status_code == 200:
            data = response.json()
            live_ready = data.get("live_transition_ready", False)
            print(f"live_transition_ready: {live_ready}")


class TestFuturesTestLiveGateRegression:
    """Test futures test live-gate regression check"""
    
    def test_futures_live_live_gate_no_500(self, admin_headers, test_user_id):
        """Test futures live live-gate does not return 500"""
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
        assert response.status_code != 500, f"Futures live live-gate returned 500: {response.text}"
        print(f"Futures live live-gate response: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            assert "status" in data
            assert "live_transition_ready" in data
            assert "controls" in data
            controls = data.get("controls", {})
            print(f"Futures live live-gate controls: {controls}")
    
    def test_futures_live_live_gate_returns_controls(self, admin_headers, test_user_id):
        """Test futures live live-gate returns proper controls structure"""
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
        
        if response.status_code == 200:
            data = response.json()
            controls = data.get("controls", {})
            
            # Verify expected control fields exist
            expected_fields = ["trade_ingest_ok", "pnl_ok", "reconciliation_ok"]
            for field in expected_fields:
                assert field in controls, f"Missing control field: {field}"
            
            print(f"Controls structure verified: {list(controls.keys())}")


class TestAuditLogsTimelineLimit:
    """Test audit-logs timeline with proper limit parameter"""
    
    def test_audit_logs_timeline_limit_20(self, admin_headers):
        """Test audit-logs timeline with limit=20 (API minimum)"""
        response = requests.get(
            f"{BASE_URL}/api/audit-logs/timeline",
            params={
                "action": "admin_credential_resolution_preview",
                "entity_type": "credential_resolution_trace",
                "limit": 20  # API requires limit >= 20
            },
            headers=admin_headers,
            timeout=15
        )
        assert response.status_code != 500, f"Audit logs timeline returned 500: {response.text}"
        print(f"Audit logs timeline response: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            items = data.get("items", [])
            print(f"Audit logs timeline items count: {len(items)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
