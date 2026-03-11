"""
Phase-5 Iteration-2 Test Suite: Venue Expansion CRUD + Validation
Tests:
- Admin Exchanges FULL CRUD endpoints (exchange registry create/update/delete)
- Capabilities CRUD endpoints (create/update/delete)
- Allowed Markets CRUD endpoints (create/toggle/delete)
- User venue assignment upsert/delete
- User venue options endpoint
- GET /api/exchange/validate requires query params exchange, market_type, environment
- Validate response contract includes exchange, market_type, environment, capability_match, reason_codes
- No regression on existing key save and readiness cards
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"
USER_EMAIL = "TEST_phase4iter2_pipeline@example.com"
USER_PASSWORD = "TestPassword123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.text}")
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def user_token():
    """Get user authentication token"""
    # First try to login with existing user
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": USER_EMAIL, "password": USER_PASSWORD},
    )
    if response.status_code == 200:
        return response.json()["access_token"]
    
    # Fallback to another test user
    fallback_email = "TEST_phase4iter4@example.com"
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": fallback_email, "password": USER_PASSWORD},
    )
    if response.status_code == 200:
        return response.json()["access_token"]
    pytest.skip(f"User login failed: {response.text}")


# Admin Exchanges CRUD Tests
class TestAdminExchangesRegistry:
    """Admin Exchanges FULL CRUD endpoints tests"""

    def test_admin_list_exchanges(self, admin_token):
        """Test GET /api/venues/admin/exchanges returns list"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/exchanges",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should have at least binance seeded
        exchange_codes = [item["exchange_code"] for item in data]
        assert "binance" in exchange_codes

    def test_admin_create_exchange_success(self, admin_token):
        """Test POST /api/venues/admin/exchanges creates new exchange"""
        payload = {
            "exchange_code": "TEST_kraken",
            "exchange_name": "Test Kraken Exchange",
            "status": "active",
            "supported_market_types": ["spot", "futures"],
            "supports_testnet": True,
            "supports_live": False,
            "health_status": "healthy",
            "rate_limit_status": "ok",
            "adapter_version": "v1",
        }
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/exchanges",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=payload,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["exchange_code"] == "test_kraken"
        assert data["exchange_name"] == "Test Kraken Exchange"
        assert data["status"] == "active"
        assert "spot" in data["supported_market_types"]

    def test_admin_create_exchange_duplicate_fails(self, admin_token):
        """Test POST /api/venues/admin/exchanges with duplicate fails"""
        payload = {
            "exchange_code": "binance",
            "exchange_name": "Duplicate Binance",
            "status": "active",
            "supported_market_types": ["spot"],
            "supports_testnet": True,
            "supports_live": False,
            "health_status": "healthy",
            "rate_limit_status": "ok",
            "adapter_version": "v1",
        }
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/exchanges",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=payload,
        )
        assert response.status_code == 400
        assert "zaten" in response.json()["detail"].lower()

    def test_admin_update_exchange(self, admin_token):
        """Test PATCH /api/venues/admin/exchanges/{exchange_code} updates exchange"""
        payload = {
            "status": "maintenance",
            "health_status": "degraded",
            "rate_limit_status": "warning",
            "adapter_version": "v2",
        }
        response = requests.patch(
            f"{BASE_URL}/api/venues/admin/exchanges/test_kraken",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "maintenance"
        assert data["health_status"] == "degraded"
        assert data["rate_limit_status"] == "warning"
        assert data["adapter_version"] == "v2"

    def test_admin_delete_exchange(self, admin_token):
        """Test DELETE /api/venues/admin/exchanges/{exchange_code} deletes exchange"""
        response = requests.delete(
            f"{BASE_URL}/api/venues/admin/exchanges/test_kraken",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] is True
        assert data["exchange_code"] == "test_kraken"

    def test_admin_delete_exchange_not_found(self, admin_token):
        """Test DELETE /api/venues/admin/exchanges with non-existent code returns 404"""
        response = requests.delete(
            f"{BASE_URL}/api/venues/admin/exchanges/nonexistent",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404


# Capabilities CRUD Tests
class TestAdminCapabilities:
    """Capabilities CRUD endpoint tests"""

    def test_admin_list_capabilities(self, admin_token):
        """Test GET /api/venues/admin/capabilities returns list"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/capabilities",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should have binance spot and futures capabilities seeded
        binance_caps = [item for item in data if item["exchange_code"] == "binance"]
        assert len(binance_caps) >= 2

    def test_admin_create_capability(self, admin_token):
        """Test POST /api/venues/admin/capabilities creates capability"""
        # First create test exchange
        requests.post(
            f"{BASE_URL}/api/venues/admin/exchanges",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "exchange_code": "TEST_cap_exchange",
                "exchange_name": "Test Cap Exchange",
                "status": "active",
                "supported_market_types": ["spot"],
                "supports_testnet": True,
                "supports_live": False,
                "health_status": "healthy",
                "rate_limit_status": "ok",
                "adapter_version": "v1",
            },
        )

        payload = {
            "exchange_code": "test_cap_exchange",
            "market_type": "spot",
            "supports_spot": True,
            "supports_futures": False,
            "supports_test_order": True,
            "supports_quote_qty": True,
            "supports_reduce_only": False,
            "supports_leverage": False,
            "supports_margin_mode": False,
            "supports_hedge_mode": False,
        }
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/capabilities",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=payload,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["exchange_code"] == "test_cap_exchange"
        assert data["market_type"] == "spot"
        assert data["supports_spot"] is True
        return data["id"]

    def test_admin_update_capability(self, admin_token):
        """Test PUT /api/venues/admin/capabilities/{id} updates capability"""
        # Get capability ID
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/capabilities",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        caps = response.json()
        test_cap = next((c for c in caps if c["exchange_code"] == "test_cap_exchange"), None)
        if not test_cap:
            pytest.skip("Test capability not found")

        payload = {
            "supports_test_order": False,
            "supports_quote_qty": False,
            "supports_reduce_only": True,
            "supports_leverage": True,
            "supports_margin_mode": True,
            "supports_hedge_mode": True,
        }
        response = requests.put(
            f"{BASE_URL}/api/venues/admin/capabilities/{test_cap['id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["supports_test_order"] is False
        assert data["supports_leverage"] is True

    def test_admin_delete_capability(self, admin_token):
        """Test DELETE /api/venues/admin/capabilities/{id} deletes capability"""
        # Get capability ID
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/capabilities",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        caps = response.json()
        test_cap = next((c for c in caps if c["exchange_code"] == "test_cap_exchange"), None)
        if not test_cap:
            pytest.skip("Test capability not found")

        response = requests.delete(
            f"{BASE_URL}/api/venues/admin/capabilities/{test_cap['id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["deleted"] is True

        # Cleanup: delete test exchange
        requests.delete(
            f"{BASE_URL}/api/venues/admin/exchanges/test_cap_exchange",
            headers={"Authorization": f"Bearer {admin_token}"},
        )


# Allowed Markets CRUD Tests
class TestAdminAllowedMarkets:
    """Allowed Markets CRUD endpoint tests"""

    def test_admin_list_allowed_markets(self, admin_token):
        """Test GET /api/venues/admin/allowed-markets returns list"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/allowed-markets",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should have binance allowed markets seeded
        binance_markets = [item for item in data if item["exchange_code"] == "binance"]
        assert len(binance_markets) >= 2

    def test_admin_create_allowed_market(self, admin_token):
        """Test POST /api/venues/admin/allowed-markets creates allowed market"""
        # First create test exchange
        requests.post(
            f"{BASE_URL}/api/venues/admin/exchanges",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "exchange_code": "TEST_market_exchange",
                "exchange_name": "Test Market Exchange",
                "status": "active",
                "supported_market_types": ["spot"],
                "supports_testnet": True,
                "supports_live": False,
                "health_status": "healthy",
                "rate_limit_status": "ok",
                "adapter_version": "v1",
            },
        )

        payload = {
            "exchange_code": "test_market_exchange",
            "market_type": "spot",
            "environment": "testnet",
            "enabled": True,
        }
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/allowed-markets",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=payload,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["exchange_code"] == "test_market_exchange"
        assert data["market_type"] == "spot"
        assert data["environment"] == "testnet"
        assert data["enabled"] is True
        return data["id"]

    def test_admin_toggle_allowed_market(self, admin_token):
        """Test PUT /api/venues/admin/allowed-markets/{id} toggles enabled"""
        # Get allowed market ID
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/allowed-markets",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        markets = response.json()
        test_market = next((m for m in markets if m["exchange_code"] == "test_market_exchange"), None)
        if not test_market:
            pytest.skip("Test allowed market not found")

        # Toggle to disabled
        response = requests.put(
            f"{BASE_URL}/api/venues/admin/allowed-markets/{test_market['id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"enabled": False},
        )
        assert response.status_code == 200
        assert response.json()["enabled"] is False

        # Toggle back to enabled
        response = requests.put(
            f"{BASE_URL}/api/venues/admin/allowed-markets/{test_market['id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"enabled": True},
        )
        assert response.status_code == 200
        assert response.json()["enabled"] is True

    def test_admin_delete_allowed_market(self, admin_token):
        """Test DELETE /api/venues/admin/allowed-markets/{id} deletes allowed market"""
        # Get allowed market ID
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/allowed-markets",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        markets = response.json()
        test_market = next((m for m in markets if m["exchange_code"] == "test_market_exchange"), None)
        if not test_market:
            pytest.skip("Test allowed market not found")

        response = requests.delete(
            f"{BASE_URL}/api/venues/admin/allowed-markets/{test_market['id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["deleted"] is True

        # Cleanup: delete test exchange
        requests.delete(
            f"{BASE_URL}/api/venues/admin/exchanges/test_market_exchange",
            headers={"Authorization": f"Bearer {admin_token}"},
        )


# User Venue Assignment Tests
class TestAdminUserAssignments:
    """User venue assignment upsert/delete endpoint tests"""

    def test_admin_list_user_assignments(self, admin_token):
        """Test GET /api/venues/admin/user-assignments returns list"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/user-assignments",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_admin_upsert_user_assignment(self, admin_token):
        """Test PUT /api/venues/admin/user-assignments upserts assignment"""
        # Get an approved user
        response = requests.get(
            f"{BASE_URL}/api/auth/admin/user-approval-requests?status=approved",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        users = response.json()
        if not users:
            pytest.skip("No approved users found")

        user_id = users[0]["id"]
        payload = {
            "user_id": user_id,
            "exchange_code": "binance",
            "spot_allowed": True,
            "futures_allowed": True,
            "testnet_allowed": True,
            "live_allowed": False,
        }
        response = requests.put(
            f"{BASE_URL}/api/venues/admin/user-assignments",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == user_id
        assert data["exchange_code"] == "binance"
        assert data["spot_allowed"] is True
        assert data["futures_allowed"] is True
        assert data["testnet_allowed"] is True
        assert data["live_allowed"] is False

    def test_admin_list_user_assignments_by_user_id(self, admin_token):
        """Test GET /api/venues/admin/user-assignments?user_id=xxx filters by user"""
        # Get an approved user
        response = requests.get(
            f"{BASE_URL}/api/auth/admin/user-approval-requests?status=approved",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        users = response.json()
        if not users:
            pytest.skip("No approved users found")

        user_id = users[0]["id"]
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/user-assignments?user_id={user_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        for assignment in data:
            assert assignment["user_id"] == user_id


# Exchange Validate Endpoint Tests
class TestExchangeValidateEndpoint:
    """GET /api/exchange/validate tests with required query params"""

    def test_exchange_validate_requires_exchange_param(self, user_token):
        """Test /api/exchange/validate requires exchange query param"""
        response = requests.get(
            f"{BASE_URL}/api/exchange/validate",
            headers={"Authorization": f"Bearer {user_token}"},
            params={"market_type": "futures", "environment": "testnet"},
        )
        # Should return 422 when exchange is missing
        assert response.status_code == 422

    def test_exchange_validate_requires_market_type_param(self, user_token):
        """Test /api/exchange/validate requires market_type query param"""
        response = requests.get(
            f"{BASE_URL}/api/exchange/validate",
            headers={"Authorization": f"Bearer {user_token}"},
            params={"exchange": "binance", "environment": "testnet"},
        )
        # Should return 422 when market_type is missing
        assert response.status_code == 422

    def test_exchange_validate_requires_environment_param(self, user_token):
        """Test /api/exchange/validate requires environment query param"""
        response = requests.get(
            f"{BASE_URL}/api/exchange/validate",
            headers={"Authorization": f"Bearer {user_token}"},
            params={"exchange": "binance", "market_type": "futures"},
        )
        # Should return 422 when environment is missing
        assert response.status_code == 422

    def test_exchange_validate_response_contract(self, user_token):
        """Test /api/exchange/validate response includes required fields"""
        response = requests.get(
            f"{BASE_URL}/api/exchange/validate",
            headers={"Authorization": f"Bearer {user_token}"},
            params={
                "exchange": "binance",
                "market_type": "futures",
                "environment": "testnet",
            },
        )
        # May return 400/403 if no credentials or no assignment, but detail should have expected shape
        data = response.json()
        if response.status_code == 200:
            assert "exchange" in data
            assert "market_type" in data
            assert "environment" in data
            assert "capability_match" in data
            assert "reason_codes" in data
        else:
            # On error, detail should contain the contract fields
            detail = data.get("detail", data)
            if isinstance(detail, dict):
                assert "exchange" in detail or "reason_codes" in detail

    def test_exchange_validate_with_all_params(self, user_token):
        """Test /api/exchange/validate works with all params"""
        response = requests.get(
            f"{BASE_URL}/api/exchange/validate",
            headers={"Authorization": f"Bearer {user_token}"},
            params={
                "exchange": "binance",
                "market_type": "futures",
                "environment": "testnet",
            },
        )
        # Should not be 422 (validation error)
        assert response.status_code != 422
        data = response.json()
        # Response or error detail should be valid
        assert isinstance(data, dict)


# User Venue Options Endpoint Tests
class TestUserVenueOptions:
    """User venue options endpoint tests"""

    def test_user_venue_options_returns_list(self, user_token):
        """Test GET /api/venues/options returns list of venue options"""
        response = requests.get(
            f"{BASE_URL}/api/venues/options",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if data:
            # Check each item has required fields
            for item in data:
                assert "exchange" in item
                assert "market_type" in item
                assert "environment" in item
                assert "venue_state" in item

    def test_user_venue_access_check(self, user_token):
        """Test GET /api/venues/access-check returns access info"""
        response = requests.get(
            f"{BASE_URL}/api/venues/access-check",
            headers={"Authorization": f"Bearer {user_token}"},
            params={
                "exchange": "binance",
                "market_type": "futures",
                "environment": "testnet",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "allowed" in data
        assert "venue_state" in data
        assert "capability_match" in data
        assert "reason_codes" in data


# Health Summary Endpoint Tests
class TestAdminHealthSummary:
    """Admin health summary endpoint tests"""

    def test_admin_health_summary(self, admin_token):
        """Test GET /api/venues/admin/health-summary returns health info"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/health-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "exchange_health" in data
        assert "market_availability" in data
        assert "capability_mismatch" in data
        assert "adapter_error_status" in data


# Regression Tests - Existing Key Save and Readiness
class TestExistingKeyAndReadinessRegression:
    """Regression tests for existing key save and readiness cards"""

    def test_exchange_settings_save_works(self, user_token):
        """Test PUT /api/phase4/exchange-settings still works"""
        payload = {
            "exchange": "binance",
            "mode": "testnet",
            "api_key": "test_key_placeholder",
            "api_secret": "test_secret_placeholder",
        }
        response = requests.put(
            f"{BASE_URL}/api/phase4/exchange-settings",
            headers={"Authorization": f"Bearer {user_token}"},
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["exchange"] == "binance"
        assert data["mode"] == "testnet"
        assert data["has_api_key"] is True
        assert data["has_api_secret"] is True

    def test_readiness_checklist_returns_expected_fields(self, user_token):
        """Test GET /api/exchange/readiness-checklist returns expected fields"""
        response = requests.get(
            f"{BASE_URL}/api/exchange/readiness-checklist",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "readiness_status" in data
        assert "has_api_key" in data
        assert "has_api_secret" in data
        assert "validation_success" in data
        assert "can_trade" in data
        assert "is_testnet_environment" in data
        assert "is_validation_stale" in data

    def test_test_order_blocked_when_key_invalid(self, user_token):
        """Test POST /api/exchange/test-order is blocked when key is invalid"""
        response = requests.post(
            f"{BASE_URL}/api/exchange/test-order",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        # Should be 400 due to invalid/missing credentials
        assert response.status_code == 400
        data = response.json()
        detail = data.get("detail", {})
        if isinstance(detail, dict):
            assert "failure_code" in detail or "status" in detail


# Auth Requirements Tests
class TestVenueEndpointAuthRequirements:
    """Test venue endpoints require proper authentication"""

    def test_admin_exchanges_requires_admin(self, user_token):
        """Test /api/venues/admin/exchanges requires admin role"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/exchanges",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403

    def test_admin_capabilities_requires_admin(self, user_token):
        """Test /api/venues/admin/capabilities requires admin role"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/capabilities",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403

    def test_admin_allowed_markets_requires_admin(self, user_token):
        """Test /api/venues/admin/allowed-markets requires admin role"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/allowed-markets",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403

    def test_admin_user_assignments_requires_admin(self, user_token):
        """Test /api/venues/admin/user-assignments requires admin role"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/user-assignments",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403

    def test_admin_health_summary_requires_admin(self, user_token):
        """Test /api/venues/admin/health-summary requires admin role"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/health-summary",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403


# Health Check
class TestHealthEndpoint:
    """Test health endpoint"""

    def test_health_returns_ok(self):
        """Test /api/health returns ok status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
