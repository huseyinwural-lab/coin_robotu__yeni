"""
Test suite for Admin Credential Orchestration API endpoints.
Tests multi-exchange credential management with binance/bybit/okx,
market types (spot/usdt_perp/coin_perp), purposes (market_data/execution/fallback),
and routing matrix with user → tenant_admin → global_admin fallback chain.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://dry-run-shadow.preview.emergentagent.com"


class TestCredentialOrchestrationAPI:
    """Test Admin Credential Orchestration endpoints"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test fixtures - login and get token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "canary.admin@platform.local",
                "password": "CanaryAdmin123!"
            }
        )
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        
        token = login_response.json().get("access_token")
        assert token, "No access token received"
        
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        self.created_credential_ids = []
        self.created_rule_ids = []
        
        yield
        
        # Cleanup - disable created credentials
        for cred_id in self.created_credential_ids:
            try:
                self.session.post(f"{BASE_URL}/api/venues/admin/credentials/{cred_id}/disable")
            except Exception:
                pass

    # ==================== Credential List Tests ====================
    
    def test_list_credentials_binance_spot(self):
        """Test listing credentials for binance/spot"""
        response = self.session.get(
            f"{BASE_URL}/api/venues/admin/credentials",
            params={
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
                "include_inactive": True
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} binance/spot credentials")

    def test_list_credentials_bybit_usdt_perp(self):
        """Test listing credentials for bybit/usdt_perp"""
        response = self.session.get(
            f"{BASE_URL}/api/venues/admin/credentials",
            params={
                "exchange": "bybit",
                "market_type": "usdt_perp",
                "environment": "testnet",
                "include_inactive": True
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} bybit/usdt_perp credentials")

    def test_list_credentials_okx_coin_perp(self):
        """Test listing credentials for okx/coin_perp"""
        response = self.session.get(
            f"{BASE_URL}/api/venues/admin/credentials",
            params={
                "exchange": "okx",
                "market_type": "coin_perp",
                "environment": "live",
                "include_inactive": True
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} okx/coin_perp credentials")

    def test_list_credentials_with_purpose_filter(self):
        """Test listing credentials with purpose filter"""
        for purpose in ["market_data", "execution", "fallback"]:
            response = self.session.get(
                f"{BASE_URL}/api/venues/admin/credentials",
                params={
                    "exchange": "binance",
                    "market_type": "spot",
                    "purpose": purpose,
                    "include_inactive": True
                }
            )
            assert response.status_code == 200, f"Failed for purpose={purpose}"
            print(f"Purpose filter '{purpose}' returned {len(response.json())} credentials")

    # ==================== Credential Create Tests ====================

    def test_create_credential_binance_spot_market_data(self):
        """Test creating binance/spot/market_data credential"""
        response = self.session.post(
            f"{BASE_URL}/api/venues/admin/credentials",
            json={
                "scope_type": "global",
                "exchange": "binance",
                "market_type": "spot",
                "purpose": "market_data",
                "environment": "testnet",
                "api_key": "TEST_BINANCE_SPOT_KEY",
                "api_secret": "TEST_BINANCE_SPOT_SECRET"
            }
        )
        assert response.status_code == 201
        data = response.json()
        
        # Verify response structure
        assert data["exchange"] == "binance"
        assert data["market_type"] == "spot"
        assert data["purpose"] == "market_data"
        assert data["environment"] == "testnet"
        assert data["scope_type"] == "global"
        assert data["approval_status"] == "pending"
        assert data["is_active"] == False
        assert data["has_api_key"] == True
        assert data["has_api_secret"] == True
        assert "credential_fingerprint" in data
        
        self.created_credential_ids.append(data["id"])
        print(f"Created credential: {data['id']}")

    def test_create_credential_bybit_usdt_perp_execution(self):
        """Test creating bybit/usdt_perp/execution credential"""
        response = self.session.post(
            f"{BASE_URL}/api/venues/admin/credentials",
            json={
                "scope_type": "global",
                "exchange": "bybit",
                "market_type": "usdt_perp",
                "purpose": "execution",
                "environment": "testnet",
                "api_key": "TEST_BYBIT_PERP_KEY",
                "api_secret": "TEST_BYBIT_PERP_SECRET"
            }
        )
        assert response.status_code == 201
        data = response.json()
        
        assert data["exchange"] == "bybit"
        assert data["market_type"] == "usdt_perp"
        assert data["purpose"] == "execution"
        
        self.created_credential_ids.append(data["id"])
        print(f"Created bybit credential: {data['id']}")

    def test_create_credential_okx_coin_perp_fallback(self):
        """Test creating okx/coin_perp/fallback credential with passphrase"""
        response = self.session.post(
            f"{BASE_URL}/api/venues/admin/credentials",
            json={
                "scope_type": "global",
                "exchange": "okx",
                "market_type": "coin_perp",
                "purpose": "fallback",
                "environment": "live",
                "api_key": "TEST_OKX_KEY",
                "api_secret": "TEST_OKX_SECRET",
                "passphrase": "TEST_OKX_PASSPHRASE"
            }
        )
        assert response.status_code == 201
        data = response.json()
        
        assert data["exchange"] == "okx"
        assert data["market_type"] == "coin_perp"
        assert data["purpose"] == "fallback"
        assert data["environment"] == "live"
        
        self.created_credential_ids.append(data["id"])
        print(f"Created okx credential: {data['id']}")

    def test_create_credential_invalid_exchange(self):
        """Test creating credential with invalid exchange returns 400"""
        response = self.session.post(
            f"{BASE_URL}/api/venues/admin/credentials",
            json={
                "scope_type": "global",
                "exchange": "invalid_exchange",
                "market_type": "spot",
                "purpose": "market_data",
                "environment": "testnet",
                "api_key": "TEST_KEY",
                "api_secret": "TEST_SECRET"
            }
        )
        assert response.status_code == 400
        assert "unsupported_exchange" in response.json().get("detail", "")

    def test_create_credential_invalid_market_type(self):
        """Test creating credential with invalid market type returns 400"""
        response = self.session.post(
            f"{BASE_URL}/api/venues/admin/credentials",
            json={
                "scope_type": "global",
                "exchange": "binance",
                "market_type": "invalid_market",
                "purpose": "market_data",
                "environment": "testnet",
                "api_key": "TEST_KEY",
                "api_secret": "TEST_SECRET"
            }
        )
        assert response.status_code == 400
        assert "invalid_market_type" in response.json().get("detail", "")

    def test_create_credential_invalid_purpose(self):
        """Test creating credential with invalid purpose returns 400"""
        response = self.session.post(
            f"{BASE_URL}/api/venues/admin/credentials",
            json={
                "scope_type": "global",
                "exchange": "binance",
                "market_type": "spot",
                "purpose": "invalid_purpose",
                "environment": "testnet",
                "api_key": "TEST_KEY",
                "api_secret": "TEST_SECRET"
            }
        )
        assert response.status_code == 400
        assert "invalid_purpose" in response.json().get("detail", "")

    # ==================== Credential Actions Tests ====================

    def test_approve_credential(self):
        """Test approving a credential"""
        # First create a credential
        create_response = self.session.post(
            f"{BASE_URL}/api/venues/admin/credentials",
            json={
                "scope_type": "global",
                "exchange": "binance",
                "market_type": "spot",
                "purpose": "execution",
                "environment": "testnet",
                "api_key": "TEST_APPROVE_KEY",
                "api_secret": "TEST_APPROVE_SECRET"
            }
        )
        assert create_response.status_code == 201
        cred_id = create_response.json()["id"]
        self.created_credential_ids.append(cred_id)
        
        # Approve the credential
        approve_response = self.session.post(
            f"{BASE_URL}/api/venues/admin/credentials/{cred_id}/approve"
        )
        assert approve_response.status_code == 200
        data = approve_response.json()
        
        assert data["approval_status"] == "approved"
        assert data["is_active"] == True
        assert data["approved_by"] is not None
        assert data["approved_at"] is not None
        print(f"Approved credential: {cred_id}")

    def test_disable_credential(self):
        """Test disabling a credential"""
        # First create and approve a credential
        create_response = self.session.post(
            f"{BASE_URL}/api/venues/admin/credentials",
            json={
                "scope_type": "global",
                "exchange": "binance",
                "market_type": "spot",
                "purpose": "market_data",
                "environment": "testnet",
                "api_key": "TEST_DISABLE_KEY",
                "api_secret": "TEST_DISABLE_SECRET"
            }
        )
        assert create_response.status_code == 201
        cred_id = create_response.json()["id"]
        self.created_credential_ids.append(cred_id)
        
        # Approve first
        self.session.post(f"{BASE_URL}/api/venues/admin/credentials/{cred_id}/approve")
        
        # Disable the credential
        disable_response = self.session.post(
            f"{BASE_URL}/api/venues/admin/credentials/{cred_id}/disable"
        )
        assert disable_response.status_code == 200
        data = disable_response.json()
        
        assert data["is_active"] == False
        print(f"Disabled credential: {cred_id}")

    def test_probe_credential(self):
        """Test probing a credential"""
        # First create a credential
        create_response = self.session.post(
            f"{BASE_URL}/api/venues/admin/credentials",
            json={
                "scope_type": "global",
                "exchange": "binance",
                "market_type": "spot",
                "purpose": "market_data",
                "environment": "testnet",
                "api_key": "TEST_PROBE_KEY",
                "api_secret": "TEST_PROBE_SECRET"
            }
        )
        assert create_response.status_code == 201
        cred_id = create_response.json()["id"]
        self.created_credential_ids.append(cred_id)
        
        # Probe the credential
        probe_response = self.session.post(
            f"{BASE_URL}/api/venues/admin/credentials/{cred_id}/probe"
        )
        assert probe_response.status_code == 200
        data = probe_response.json()
        
        # Probe should update status
        assert data["last_probe_status"] is not None
        assert data["last_probe_message"] is not None
        assert data["last_probe_at"] is not None
        assert "last_probe_meta" in data
        print(f"Probed credential: {cred_id}, status: {data['last_probe_status']}")

    # ==================== Routing Rules Tests ====================

    def test_list_credential_rules(self):
        """Test listing credential assignment rules"""
        response = self.session.get(
            f"{BASE_URL}/api/venues/admin/credential-rules",
            params={
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} routing rules")

    def test_upsert_credential_rule(self):
        """Test creating/updating a credential assignment rule"""
        response = self.session.put(
            f"{BASE_URL}/api/venues/admin/credential-rules",
            json={
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
                "tenant_id": None,
                "user_id": None,
                "preferred_source": "user",
                "fallback_enabled": True
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["exchange"] == "binance"
        assert data["market_type"] == "spot"
        assert data["environment"] == "testnet"
        assert data["preferred_source"] == "user"
        assert data["fallback_enabled"] == True
        
        self.created_rule_ids.append(data["id"])
        print(f"Created/updated rule: {data['id']}")

    def test_upsert_credential_rule_admin_source(self):
        """Test creating rule with admin preferred source"""
        response = self.session.put(
            f"{BASE_URL}/api/venues/admin/credential-rules",
            json={
                "exchange": "bybit",
                "market_type": "usdt_perp",
                "environment": "testnet",
                "preferred_source": "admin",
                "fallback_enabled": True
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["preferred_source"] == "admin"
        self.created_rule_ids.append(data["id"])

    def test_upsert_credential_rule_admin_fallback_source(self):
        """Test creating rule with admin_fallback preferred source"""
        response = self.session.put(
            f"{BASE_URL}/api/venues/admin/credential-rules",
            json={
                "exchange": "okx",
                "market_type": "coin_perp",
                "environment": "live",
                "preferred_source": "admin_fallback",
                "fallback_enabled": False
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["preferred_source"] == "admin_fallback"
        assert data["fallback_enabled"] == False
        self.created_rule_ids.append(data["id"])

    def test_upsert_credential_rule_invalid_source(self):
        """Test creating rule with invalid preferred source returns 400"""
        response = self.session.put(
            f"{BASE_URL}/api/venues/admin/credential-rules",
            json={
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
                "preferred_source": "invalid_source",
                "fallback_enabled": True
            }
        )
        assert response.status_code == 400
        assert "invalid_preferred_source" in response.json().get("detail", "")

    # ==================== Resolution Preview Tests ====================

    def test_resolution_preview_with_approved_credential(self):
        """Test resolution preview returns correct data when credential exists"""
        # First create and approve a credential
        create_response = self.session.post(
            f"{BASE_URL}/api/venues/admin/credentials",
            json={
                "scope_type": "global",
                "exchange": "binance",
                "market_type": "spot",
                "purpose": "execution",
                "environment": "testnet",
                "api_key": "TEST_PREVIEW_KEY",
                "api_secret": "TEST_PREVIEW_SECRET"
            }
        )
        assert create_response.status_code == 201
        cred_id = create_response.json()["id"]
        self.created_credential_ids.append(cred_id)
        
        # Approve the credential
        self.session.post(f"{BASE_URL}/api/venues/admin/credentials/{cred_id}/approve")
        
        # Create a routing rule
        self.session.put(
            f"{BASE_URL}/api/venues/admin/credential-rules",
            json={
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
                "preferred_source": "user",
                "fallback_enabled": True
            }
        )
        
        # Test resolution preview
        response = self.session.get(
            f"{BASE_URL}/api/venues/admin/credential-resolution-preview",
            params={
                "user_id": "test-user-123",
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
                "purpose": "execution"
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "selected_credential_id" in data
        assert "source" in data
        assert "masked_api_key" in data
        assert "masked_fingerprint" in data
        assert "effective_base_url" in data
        assert "audit_metadata" in data
        
        # Verify audit metadata
        audit = data["audit_metadata"]
        assert "selection_reason" in audit
        assert "preferred_source" in audit
        assert "fallback_enabled" in audit
        
        print(f"Resolution preview: source={data['source']}, reason={audit['selection_reason']}")

    def test_resolution_preview_no_credential(self):
        """Test resolution preview returns 404 when no credential exists"""
        response = self.session.get(
            f"{BASE_URL}/api/venues/admin/credential-resolution-preview",
            params={
                "user_id": "nonexistent-user",
                "exchange": "nonexistent",
                "market_type": "spot",
                "environment": "testnet",
                "purpose": "execution"
            }
        )
        # Should return 400 for unsupported exchange or 404 for no credential
        assert response.status_code in [400, 404]

    def test_resolution_preview_execution_purpose(self):
        """Test resolution preview with execution purpose"""
        response = self.session.get(
            f"{BASE_URL}/api/venues/admin/credential-resolution-preview",
            params={
                "user_id": "test-user",
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
                "purpose": "execution"
            }
        )
        # May return 200 or 404 depending on existing credentials
        assert response.status_code in [200, 404]

    def test_resolution_preview_fallback_purpose(self):
        """Test resolution preview with fallback purpose"""
        response = self.session.get(
            f"{BASE_URL}/api/venues/admin/credential-resolution-preview",
            params={
                "user_id": "test-user",
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
                "purpose": "fallback"
            }
        )
        # May return 200 or 404 depending on existing credentials
        assert response.status_code in [200, 404]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
