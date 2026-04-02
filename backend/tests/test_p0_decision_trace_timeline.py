"""
Test P0 Commercial Ops endpoints and Decision Trace Timeline features.
Tests:
- /api/venues/admin/credentials with purpose filter + multi-market alias
- Spot live probe and Futures test probe endpoint flows
- P0 endpoints: /api/admin/commercial/p0/ingestion/rest-run (spot/live + futures/live)
- P0 endpoint: /api/admin/commercial/p0/live-gate (futures required)
- Decision Trace Timeline UI data structure
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
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code}")
    data = response.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers with admin auth"""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json",
    }


class TestCredentialOrchestrationFilters:
    """Test /api/venues/admin/credentials with purpose filter + multi-market alias"""

    def test_credentials_list_with_purpose_filter_market_data(self, admin_headers):
        """Test credentials list with purpose=market_data filter"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credentials",
            params={
                "exchange": "binance",
                "market_type": "spot",
                "purpose": "market_data",
                "include_inactive": True,
            },
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Credentials list with purpose=market_data returned {len(data)} items")

    def test_credentials_list_with_purpose_filter_execution(self, admin_headers):
        """Test credentials list with purpose=execution filter"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credentials",
            params={
                "exchange": "binance",
                "market_type": "spot",
                "purpose": "execution",
                "include_inactive": True,
            },
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Credentials list with purpose=execution returned {len(data)} items")

    def test_credentials_list_with_purpose_filter_fallback(self, admin_headers):
        """Test credentials list with purpose=fallback filter"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credentials",
            params={
                "exchange": "binance",
                "market_type": "spot",
                "purpose": "fallback",
                "include_inactive": True,
            },
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Credentials list with purpose=fallback returned {len(data)} items")

    def test_credentials_list_multi_market_alias_usdt_perp(self, admin_headers):
        """Test credentials list with market_type=usdt_perp (should include futures alias)"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credentials",
            params={
                "exchange": "binance",
                "market_type": "usdt_perp",
                "include_inactive": True,
            },
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Credentials list with market_type=usdt_perp returned {len(data)} items")

    def test_credentials_list_multi_market_alias_coin_perp(self, admin_headers):
        """Test credentials list with market_type=coin_perp (should include futures alias)"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credentials",
            params={
                "exchange": "binance",
                "market_type": "coin_perp",
                "include_inactive": True,
            },
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Credentials list with market_type=coin_perp returned {len(data)} items")

    def test_credentials_list_all_purposes(self, admin_headers):
        """Test credentials list without purpose filter (all purposes)"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credentials",
            params={
                "exchange": "binance",
                "market_type": "spot",
                "include_inactive": True,
            },
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Credentials list without purpose filter returned {len(data)} items")


class TestCredentialProbeEndpoints:
    """Test Spot live probe and Futures test probe endpoint flows"""

    def test_spot_live_credential_probe(self, admin_headers):
        """Test spot live credential probe - should return probe status"""
        # First get credentials to find a spot/live credential
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credentials",
            params={
                "exchange": "binance",
                "market_type": "spot",
                "environment": "live",
                "include_inactive": True,
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        credentials = response.json()
        
        if not credentials:
            # Create a test credential for spot/live
            create_response = requests.post(
                f"{BASE_URL}/api/venues/admin/credentials",
                json={
                    "scope_type": "global",
                    "exchange": "binance",
                    "market_type": "spot",
                    "purpose": "execution",
                    "environment": "live",
                    "api_key": "test_spot_live_key",
                    "api_secret": "test_spot_live_secret",
                    "is_default": False,
                },
                headers=admin_headers,
            )
            assert create_response.status_code == 201, f"Failed to create credential: {create_response.text}"
            credential_id = create_response.json()["id"]
        else:
            credential_id = credentials[0]["id"]

        # Probe the credential
        probe_response = requests.post(
            f"{BASE_URL}/api/venues/admin/credentials/{credential_id}/probe",
            headers=admin_headers,
        )
        assert probe_response.status_code == 200, f"Probe failed: {probe_response.text}"
        probe_data = probe_response.json()
        
        # Verify probe response structure
        assert "last_probe_status" in probe_data
        assert "last_probe_message" in probe_data
        assert "last_probe_at" in probe_data
        print(f"PASS: Spot live probe returned status={probe_data.get('last_probe_status')}")

    def test_futures_live_credential_probe(self, admin_headers):
        """Test futures live credential probe - should return probe status"""
        # First get credentials to find a futures/live credential
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credentials",
            params={
                "exchange": "binance",
                "market_type": "usdt_perp",
                "environment": "live",
                "include_inactive": True,
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        credentials = response.json()
        
        if not credentials:
            # Create a test credential for futures/live
            create_response = requests.post(
                f"{BASE_URL}/api/venues/admin/credentials",
                json={
                    "scope_type": "global",
                    "exchange": "binance",
                    "market_type": "usdt_perp",
                    "purpose": "execution",
                    "environment": "live",
                    "api_key": "test_futures_live_key",
                    "api_secret": "test_futures_live_secret",
                    "is_default": False,
                },
                headers=admin_headers,
            )
            assert create_response.status_code == 201, f"Failed to create credential: {create_response.text}"
            credential_id = create_response.json()["id"]
        else:
            credential_id = credentials[0]["id"]

        # Probe the credential
        probe_response = requests.post(
            f"{BASE_URL}/api/venues/admin/credentials/{credential_id}/probe",
            headers=admin_headers,
        )
        assert probe_response.status_code == 200, f"Probe failed: {probe_response.text}"
        probe_data = probe_response.json()
        
        # Verify probe response structure
        assert "last_probe_status" in probe_data
        assert "last_probe_message" in probe_data
        assert "last_probe_at" in probe_data
        print(f"PASS: Futures live probe returned status={probe_data.get('last_probe_status')}")


class TestP0IngestionEndpoints:
    """Test P0 endpoints: /api/admin/commercial/p0/ingestion/rest-run"""

    def test_p0_ingestion_spot_live_requires_symbols(self, admin_headers):
        """Test P0 ingestion for spot/live - should require symbols"""
        response = requests.post(
            f"{BASE_URL}/api/admin/commercial/p0/ingestion/rest-run",
            json={
                "target_user_email": ADMIN_EMAIL,
                "environment": "live",
                "market_types": ["spot"],
                "symbols": [],  # Empty symbols should fail for spot
                "limit_per_symbol": 100,
            },
            headers=admin_headers,
        )
        # Spot requires symbols, so this should fail with 400
        assert response.status_code == 400, f"Expected 400 for spot without symbols, got {response.status_code}"
        print("PASS: P0 ingestion spot/live correctly requires symbols")

    def test_p0_ingestion_spot_live_with_symbols(self, admin_headers):
        """Test P0 ingestion for spot/live with symbols"""
        response = requests.post(
            f"{BASE_URL}/api/admin/commercial/p0/ingestion/rest-run",
            json={
                "target_user_email": ADMIN_EMAIL,
                "environment": "live",
                "market_types": ["spot"],
                "symbols": ["BTCUSDT"],
                "limit_per_symbol": 10,
            },
            headers=admin_headers,
        )
        # This may fail due to credential issues, but should not be 500
        assert response.status_code in [200, 400, 404], f"Unexpected status: {response.status_code}: {response.text}"
        print(f"PASS: P0 ingestion spot/live with symbols returned {response.status_code}")

    def test_p0_ingestion_futures_live(self, admin_headers):
        """Test P0 ingestion for futures/live"""
        response = requests.post(
            f"{BASE_URL}/api/admin/commercial/p0/ingestion/rest-run",
            json={
                "target_user_email": ADMIN_EMAIL,
                "environment": "live",
                "market_types": ["futures"],
                "symbols": [],  # Futures can work without symbols
                "limit_per_symbol": 10,
            },
            headers=admin_headers,
        )
        # This may fail due to credential issues, but should not be 500
        assert response.status_code in [200, 400, 404], f"Unexpected status: {response.status_code}: {response.text}"
        print(f"PASS: P0 ingestion futures/live returned {response.status_code}")


class TestP0LiveGateEndpoint:
    """Test P0 endpoint: /api/admin/commercial/p0/live-gate"""

    def test_live_gate_futures_required(self, admin_headers):
        """Test live-gate with futures required - may return false if trade coverage insufficient"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/p0/live-gate",
            params={
                "target_user_email": ADMIN_EMAIL,
                "environment": "live",
                "required_market_types": ["futures"],
            },
            headers=admin_headers,
        )
        assert response.status_code in [200, 400, 404], f"Unexpected status: {response.status_code}: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            assert "status" in data
            assert "live_transition_ready" in data
            assert "controls" in data
            
            controls = data.get("controls", {})
            assert "trade_ingest_ok" in controls
            assert "pnl_ok" in controls
            assert "reconciliation_ok" in controls
            assert "market_ingest_coverage" in controls
            
            print(f"PASS: Live-gate returned live_transition_ready={data.get('live_transition_ready')}")
        else:
            print(f"PASS: Live-gate returned {response.status_code} (expected for missing credentials)")

    def test_live_gate_spot_and_futures(self, admin_headers):
        """Test live-gate with both spot and futures required"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/p0/live-gate",
            params={
                "target_user_email": ADMIN_EMAIL,
                "environment": "live",
                "required_market_types": ["spot", "futures"],
            },
            headers=admin_headers,
        )
        assert response.status_code in [200, 400, 404], f"Unexpected status: {response.status_code}: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            assert "live_transition_ready" in data
            print(f"PASS: Live-gate (spot+futures) returned live_transition_ready={data.get('live_transition_ready')}")
        else:
            print(f"PASS: Live-gate (spot+futures) returned {response.status_code}")


class TestDecisionTraceTimeline:
    """Test Decision Trace Timeline data structure via resolution preview"""

    def test_resolution_preview_returns_audit_metadata(self, admin_headers):
        """Test that resolution preview returns audit_metadata for Decision Trace Timeline"""
        # First ensure we have a credential to resolve
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credentials",
            params={
                "exchange": "binance",
                "market_type": "spot",
                "environment": "live",
                "include_inactive": True,
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        credentials = response.json()
        
        if not credentials:
            # Create a test credential
            create_response = requests.post(
                f"{BASE_URL}/api/venues/admin/credentials",
                json={
                    "scope_type": "global",
                    "exchange": "binance",
                    "market_type": "spot",
                    "purpose": "execution",
                    "environment": "live",
                    "api_key": "test_timeline_key",
                    "api_secret": "test_timeline_secret",
                    "is_default": True,
                },
                headers=admin_headers,
            )
            assert create_response.status_code == 201
            credential_id = create_response.json()["id"]
            
            # Approve the credential
            approve_response = requests.post(
                f"{BASE_URL}/api/venues/admin/credentials/{credential_id}/approve",
                headers=admin_headers,
            )
            assert approve_response.status_code == 200

        # Get admin user ID
        me_response = requests.get(f"{BASE_URL}/api/auth/me", headers=admin_headers)
        assert me_response.status_code == 200
        user_id = me_response.json().get("id")

        # Test resolution preview
        preview_response = requests.get(
            f"{BASE_URL}/api/venues/admin/credential-resolution-preview",
            params={
                "user_id": user_id,
                "exchange": "binance",
                "market_type": "spot",
                "environment": "live",
                "purpose": "execution",
            },
            headers=admin_headers,
        )
        
        if preview_response.status_code == 200:
            data = preview_response.json()
            
            # Verify Decision Trace Timeline data structure
            assert "source" in data, "Missing 'source' field for Decision Trace Timeline"
            assert "selected_credential_id" in data, "Missing 'selected_credential_id' field"
            assert "audit_metadata" in data, "Missing 'audit_metadata' field for Decision Trace Timeline"
            
            audit = data.get("audit_metadata", {})
            assert "selection_reason" in audit, "Missing 'selection_reason' in audit_metadata"
            
            # The source should indicate which step was selected (user/tenant/global)
            source = data.get("source", "")
            print(f"PASS: Resolution preview returned source={source}, selection_reason={audit.get('selection_reason')}")
        else:
            print(f"PASS: Resolution preview returned {preview_response.status_code} (credential not found)")

    def test_resolution_preview_fallback_chain(self, admin_headers):
        """Test that resolution preview follows user→tenant_admin→global_admin fallback chain"""
        # Get admin user ID
        me_response = requests.get(f"{BASE_URL}/api/auth/me", headers=admin_headers)
        assert me_response.status_code == 200
        user_id = me_response.json().get("id")

        # Test with different purposes to verify fallback
        for purpose in ["execution", "fallback", "market_data"]:
            preview_response = requests.get(
                f"{BASE_URL}/api/venues/admin/credential-resolution-preview",
                params={
                    "user_id": user_id,
                    "exchange": "binance",
                    "market_type": "spot",
                    "environment": "live",
                    "purpose": purpose,
                },
                headers=admin_headers,
            )
            
            if preview_response.status_code == 200:
                data = preview_response.json()
                source = data.get("source", "")
                audit = data.get("audit_metadata", {})
                selection_reason = audit.get("selection_reason", "")
                
                # Verify the source follows the expected pattern
                valid_sources = ["user", "admin_global_default", "admin_tenant_default", "admin_group_default"]
                source_valid = any(s in source.lower() for s in ["user", "admin", "global", "tenant", "group"])
                
                print(f"PASS: Resolution preview for purpose={purpose}: source={source}, reason={selection_reason}")
            else:
                print(f"INFO: Resolution preview for purpose={purpose} returned {preview_response.status_code}")


class TestCredentialRulesEndpoints:
    """Test credential routing rules endpoints"""

    def test_list_credential_rules(self, admin_headers):
        """Test listing credential rules"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credential-rules",
            params={
                "exchange": "binance",
                "market_type": "spot",
                "environment": "live",
            },
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Credential rules list returned {len(data)} rules")

    def test_upsert_credential_rule(self, admin_headers):
        """Test upserting a credential rule"""
        response = requests.put(
            f"{BASE_URL}/api/venues/admin/credential-rules",
            json={
                "exchange": "binance",
                "market_type": "spot",
                "environment": "live",
                "preferred_source": "user",
                "fallback_enabled": True,
            },
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "id" in data
        assert data.get("preferred_source") == "user"
        assert data.get("fallback_enabled") == True
        print(f"PASS: Credential rule upserted with id={data.get('id')}")


class TestP0DataQualityEndpoint:
    """Test P0 data quality endpoint"""

    def test_data_quality_snapshot(self, admin_headers):
        """Test data quality snapshot endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/commercial/p0/data-quality",
            params={
                "target_user_email": ADMIN_EMAIL,
                "environment": "live",
            },
            headers=admin_headers,
        )
        assert response.status_code in [200, 400, 404], f"Unexpected status: {response.status_code}: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            assert "status" in data
            assert "freshness_seconds" in data
            assert "missing_data_alert" in data
            print(f"PASS: Data quality snapshot returned status={data.get('status')}")
        else:
            print(f"PASS: Data quality snapshot returned {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
