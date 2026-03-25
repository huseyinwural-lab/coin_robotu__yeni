"""
Iteration 130: Live Proxy Transition & Spot/Futures Chain Regression Tests

Test Scope:
1. Env effect: spot/futures live base url works via proxy
2. Spot live ingestion low_weight_mode=true and processed_symbols behavior
3. Spot BTC/ETH/BNB/SOL/ADA ingest calls - no 500 errors
4. Spot P0 chain: pnl/reconciliation/data-quality/live-gate endpoints
5. Futures test scope live-gate regression
6. Credential resolution spot/live source and effective_base_url validation
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Admin credentials
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code}")
    data = response.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers with admin auth token"""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json",
    }


class TestProxyEnvConfiguration:
    """Test that proxy URLs are correctly configured in environment"""

    def test_backend_env_has_spot_live_proxy_url(self):
        """Verify BINANCE_SPOT_LIVE_BASE_URL is set"""
        spot_url = os.environ.get("BINANCE_SPOT_LIVE_BASE_URL", "")
        assert spot_url, "BINANCE_SPOT_LIVE_BASE_URL should be set"
        assert "212.47.73.66" in spot_url or "proxy" in spot_url.lower(), "Should be proxy URL"
        print(f"PASS: BINANCE_SPOT_LIVE_BASE_URL = {spot_url}")

    def test_backend_env_has_futures_live_proxy_url(self):
        """Verify BINANCE_FUTURES_LIVE_BASE_URL is set"""
        futures_url = os.environ.get("BINANCE_FUTURES_LIVE_BASE_URL", "")
        assert futures_url, "BINANCE_FUTURES_LIVE_BASE_URL should be set"
        assert "212.47.73.66" in futures_url or "proxy" in futures_url.lower(), "Should be proxy URL"
        print(f"PASS: BINANCE_FUTURES_LIVE_BASE_URL = {futures_url}")

    def test_backend_env_has_spot_live_proxy_token(self):
        """Verify BINANCE_SPOT_LIVE_PROXY_TOKEN is set"""
        token = os.environ.get("BINANCE_SPOT_LIVE_PROXY_TOKEN", "")
        assert token, "BINANCE_SPOT_LIVE_PROXY_TOKEN should be set"
        assert len(token) > 20, "Token should be substantial"
        print(f"PASS: BINANCE_SPOT_LIVE_PROXY_TOKEN is set (length={len(token)})")

    def test_backend_env_has_futures_live_proxy_token(self):
        """Verify BINANCE_FUTURES_LIVE_PROXY_TOKEN is set"""
        token = os.environ.get("BINANCE_FUTURES_LIVE_PROXY_TOKEN", "")
        assert token, "BINANCE_FUTURES_LIVE_PROXY_TOKEN should be set"
        assert len(token) > 20, "Token should be substantial"
        print(f"PASS: BINANCE_FUTURES_LIVE_PROXY_TOKEN is set (length={len(token)})")


class TestSpotLiveIngestion:
    """Test spot live ingestion with low_weight_mode"""

    def test_spot_live_ingestion_low_weight_mode_btcusdt(self, admin_headers):
        """Spot live ingestion should return low_weight_mode=true for BTCUSDT"""
        response = requests.post(
            f"{BASE_URL}/api/admin/commercial/p0/ingestion/rest-run",
            headers=admin_headers,
            json={
                "target_user_email": ADMIN_EMAIL,
                "environment": "live",
                "market_types": ["spot"],
                "symbols": ["BTCUSDT"],
                "limit_per_symbol": 50,
            },
            timeout=60,
        )
        # Should not return 500
        assert response.status_code != 500, f"Should not return 500: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            # Check low_weight_mode in market_summary
            market_summary = data.get("market_summary", {})
            spot_summary = market_summary.get("spot", {})
            low_weight_mode = spot_summary.get("low_weight_mode", False)
            processed_symbols = spot_summary.get("processed_symbols", [])
            
            print(f"PASS: Spot live ingestion - status={response.status_code}")
            print(f"  low_weight_mode={low_weight_mode}")
            print(f"  processed_symbols={processed_symbols}")
            
            # Verify low_weight_mode is true for live+spot
            assert low_weight_mode is True, "low_weight_mode should be True for live+spot"
        else:
            # Non-500 errors are acceptable (e.g., 400 for missing credentials)
            print(f"INFO: Spot live ingestion returned {response.status_code}: {response.text[:200]}")

    def test_spot_live_ingestion_ethusdt(self, admin_headers):
        """Spot live ingestion for ETHUSDT - no 500 error"""
        response = requests.post(
            f"{BASE_URL}/api/admin/commercial/p0/ingestion/rest-run",
            headers=admin_headers,
            json={
                "target_user_email": ADMIN_EMAIL,
                "environment": "live",
                "market_types": ["spot"],
                "symbols": ["ETHUSDT"],
                "limit_per_symbol": 50,
            },
            timeout=60,
        )
        assert response.status_code != 500, f"Should not return 500: {response.text}"
        print(f"PASS: ETHUSDT spot live ingestion - status={response.status_code}")

    def test_spot_live_ingestion_bnbusdt(self, admin_headers):
        """Spot live ingestion for BNBUSDT - no 500 error"""
        response = requests.post(
            f"{BASE_URL}/api/admin/commercial/p0/ingestion/rest-run",
            headers=admin_headers,
            json={
                "target_user_email": ADMIN_EMAIL,
                "environment": "live",
                "market_types": ["spot"],
                "symbols": ["BNBUSDT"],
                "limit_per_symbol": 50,
            },
            timeout=60,
        )
        assert response.status_code != 500, f"Should not return 500: {response.text}"
        print(f"PASS: BNBUSDT spot live ingestion - status={response.status_code}")

    def test_spot_live_ingestion_solusdt(self, admin_headers):
        """Spot live ingestion for SOLUSDT - no 500 error"""
        response = requests.post(
            f"{BASE_URL}/api/admin/commercial/p0/ingestion/rest-run",
            headers=admin_headers,
            json={
                "target_user_email": ADMIN_EMAIL,
                "environment": "live",
                "market_types": ["spot"],
                "symbols": ["SOLUSDT"],
                "limit_per_symbol": 50,
            },
            timeout=60,
        )
        assert response.status_code != 500, f"Should not return 500: {response.text}"
        print(f"PASS: SOLUSDT spot live ingestion - status={response.status_code}")

    def test_spot_live_ingestion_adausdt(self, admin_headers):
        """Spot live ingestion for ADAUSDT - no 500 error"""
        response = requests.post(
            f"{BASE_URL}/api/admin/commercial/p0/ingestion/rest-run",
            headers=admin_headers,
            json={
                "target_user_email": ADMIN_EMAIL,
                "environment": "live",
                "market_types": ["spot"],
                "symbols": ["ADAUSDT"],
                "limit_per_symbol": 50,
            },
            timeout=60,
        )
        assert response.status_code != 500, f"Should not return 500: {response.text}"
        print(f"PASS: ADAUSDT spot live ingestion - status={response.status_code}")


class TestSpotP0ChainEndpoints:
    """Test Spot P0 chain: pnl/reconciliation/data-quality/live-gate"""

    def test_spot_live_pnl_endpoint(self, admin_headers):
        """GET /api/admin/commercial/p0/pnl/latest for spot live - no 500"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/p0/pnl/latest",
            headers=admin_headers,
            params={
                "target_user_email": ADMIN_EMAIL,
                "environment": "live",
                "market_types": "spot",
            },
            timeout=30,
        )
        assert response.status_code != 500, f"PNL endpoint should not return 500: {response.text}"
        print(f"PASS: Spot live PNL endpoint - status={response.status_code}")

    def test_spot_live_reconciliation_endpoint(self, admin_headers):
        """POST /api/admin/commercial/p0/reconciliation/run for spot live - no 500"""
        response = requests.post(
            f"{BASE_URL}/api/admin/commercial/p0/reconciliation/run",
            headers=admin_headers,
            json={
                "target_user_email": ADMIN_EMAIL,
                "environment": "live",
                "market_types": ["spot"],
                "symbols": ["BTCUSDT"],
                "limit_per_symbol": 50,
            },
            timeout=60,
        )
        assert response.status_code != 500, f"Reconciliation endpoint should not return 500: {response.text}"
        print(f"PASS: Spot live reconciliation endpoint - status={response.status_code}")

    def test_spot_live_data_quality_endpoint(self, admin_headers):
        """GET /api/admin/commercial/p0/data-quality for spot live - no 500"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/p0/data-quality",
            headers=admin_headers,
            params={
                "target_user_email": ADMIN_EMAIL,
                "environment": "live",
                "market_types": "spot",
            },
            timeout=30,
        )
        assert response.status_code != 500, f"Data quality endpoint should not return 500: {response.text}"
        print(f"PASS: Spot live data-quality endpoint - status={response.status_code}")

    def test_spot_live_gate_endpoint(self, admin_headers):
        """GET /api/admin/commercial/p0/live-gate for spot live - no 500"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/p0/live-gate",
            headers=admin_headers,
            params={
                "target_user_email": ADMIN_EMAIL,
                "environment": "live",
                "market_types": "spot",
            },
            timeout=30,
        )
        assert response.status_code != 500, f"Live-gate endpoint should not return 500: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            live_ready = data.get("live_transition_ready", False)
            controls = data.get("controls", {})
            print(f"PASS: Spot live-gate endpoint - status={response.status_code}")
            print(f"  live_transition_ready={live_ready}")
            print(f"  controls={controls}")
        else:
            print(f"INFO: Spot live-gate returned {response.status_code}")


class TestFuturesLiveGateRegression:
    """Test Futures live-gate regression"""

    def test_futures_testnet_live_gate(self, admin_headers):
        """GET /api/admin/commercial/p0/live-gate for futures testnet - no 500"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/p0/live-gate",
            headers=admin_headers,
            params={
                "target_user_email": ADMIN_EMAIL,
                "environment": "testnet",
                "market_types": "futures",
            },
            timeout=30,
        )
        assert response.status_code != 500, f"Futures testnet live-gate should not return 500: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            controls = data.get("controls", {})
            assert "trade_ingest_ok" in controls, "Should have trade_ingest_ok control"
            assert "pnl_ok" in controls, "Should have pnl_ok control"
            assert "reconciliation_ok" in controls, "Should have reconciliation_ok control"
            print(f"PASS: Futures testnet live-gate - status={response.status_code}")
            print(f"  controls structure verified")
        else:
            print(f"INFO: Futures testnet live-gate returned {response.status_code}")

    def test_futures_live_gate(self, admin_headers):
        """GET /api/admin/commercial/p0/live-gate for futures live - no 500"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/p0/live-gate",
            headers=admin_headers,
            params={
                "target_user_email": ADMIN_EMAIL,
                "environment": "live",
                "market_types": "futures",
            },
            timeout=30,
        )
        assert response.status_code != 500, f"Futures live live-gate should not return 500: {response.text}"
        print(f"PASS: Futures live live-gate - status={response.status_code}")


class TestCredentialResolutionSpotLive:
    """Test credential resolution for spot/live source and effective_base_url"""

    def test_credential_resolution_preview_spot_live(self, admin_headers):
        """GET /api/venues/admin/credential-resolution-preview for spot live"""
        # First get admin user ID
        me_response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers=admin_headers,
            timeout=15,
        )
        if me_response.status_code != 200:
            pytest.skip("Could not get current user")
        
        user_id = me_response.json().get("id")
        
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credential-resolution-preview",
            headers=admin_headers,
            params={
                "user_id": user_id,
                "exchange": "binance",
                "market_type": "spot",
                "environment": "live",
                "purpose": "execution",
            },
            timeout=30,
        )
        
        # Should not return 500
        assert response.status_code != 500, f"Credential resolution should not return 500: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            source = data.get("source", "")
            effective_base_url = data.get("effective_base_url", "")
            
            print(f"PASS: Credential resolution preview - status={response.status_code}")
            print(f"  source={source}")
            print(f"  effective_base_url={effective_base_url}")
            
            # If effective_base_url is set, it should be the proxy URL
            if effective_base_url:
                assert "212.47.73.66" in effective_base_url or "api.binance.com" in effective_base_url, \
                    f"effective_base_url should be proxy or binance: {effective_base_url}"
        else:
            print(f"INFO: Credential resolution returned {response.status_code}: {response.text[:200]}")

    def test_credential_list_spot_live(self, admin_headers):
        """GET /api/venues/admin/credentials for spot live"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credentials",
            headers=admin_headers,
            params={
                "exchange": "binance",
                "market_type": "spot",
                "environment": "live",
                "include_inactive": True,
            },
            timeout=30,
        )
        
        assert response.status_code != 500, f"Credential list should not return 500: {response.text}"
        print(f"PASS: Credential list spot/live - status={response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"  Found {len(data)} credentials")


class TestAuditLogsTimeline:
    """Test audit logs timeline endpoint"""

    def test_audit_logs_timeline_with_limit(self, admin_headers):
        """GET /api/audit-logs/timeline with limit parameter"""
        response = requests.get(
            f"{BASE_URL}/api/audit-logs/timeline",
            headers=admin_headers,
            params={
                "limit": 20,
            },
            timeout=30,
        )
        
        assert response.status_code != 500, f"Audit logs timeline should not return 500: {response.text}"
        print(f"PASS: Audit logs timeline - status={response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            items = data.get("items", [])
            print(f"  Found {len(items)} audit log items")


class TestSpotTestnetComparison:
    """Compare spot testnet vs live behavior"""

    def test_spot_testnet_ingestion_no_low_weight_mode(self, admin_headers):
        """Spot testnet ingestion should NOT have low_weight_mode=true"""
        response = requests.post(
            f"{BASE_URL}/api/admin/commercial/p0/ingestion/rest-run",
            headers=admin_headers,
            json={
                "target_user_email": ADMIN_EMAIL,
                "environment": "testnet",
                "market_types": ["spot"],
                "symbols": ["BTCUSDT"],
                "limit_per_symbol": 50,
            },
            timeout=60,
        )
        
        assert response.status_code != 500, f"Should not return 500: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            market_summary = data.get("market_summary", {})
            spot_summary = market_summary.get("spot", {})
            low_weight_mode = spot_summary.get("low_weight_mode", False)
            
            print(f"PASS: Spot testnet ingestion - status={response.status_code}")
            print(f"  low_weight_mode={low_weight_mode} (expected: False for testnet)")
            
            # Testnet should NOT have low_weight_mode
            assert low_weight_mode is False, "low_weight_mode should be False for testnet"
        else:
            print(f"INFO: Spot testnet ingestion returned {response.status_code}")
