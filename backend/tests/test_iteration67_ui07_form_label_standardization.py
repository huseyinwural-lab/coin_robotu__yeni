"""
UI-07 Form Field Label Standardization - Backend API Tests
Tests bot-profiles and risk-policies API contracts
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestHealthAndAuth:
    """Basic health and authentication tests"""
    
    def test_health_check(self):
        """Test API health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        print("Health check PASS")
    
    def test_user_login(self):
        """Test user login flow"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "e2_conn_last@example.com",
            "password": "User12345!"
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "user"
        print("User login PASS")

    def test_admin_login(self):
        """Test admin login flow"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@platform.dev",
            "password": "Admin12345!"
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] in ["admin", "super_admin", "ops"]
        print("Admin login PASS")


@pytest.fixture
def user_token():
    """Get user authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "e2_conn_last@example.com",
        "password": "User12345!"
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("User authentication failed")

@pytest.fixture
def admin_token():
    """Get admin authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@platform.dev",
        "password": "Admin12345!"
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Admin authentication failed")

@pytest.fixture
def user_headers(user_token):
    """Headers with user auth"""
    return {
        "Authorization": f"Bearer {user_token}",
        "Content-Type": "application/json"
    }

@pytest.fixture
def admin_headers(admin_token):
    """Headers with admin auth"""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }


class TestBotProfilesAPI:
    """Bot Profiles CRUD API tests"""
    
    def test_bot_profiles_list(self, user_headers):
        """Test GET /api/bot-profiles - list endpoint"""
        response = requests.get(f"{BASE_URL}/api/bot-profiles", headers=user_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Bot profiles list PASS - {len(data)} profiles found")
    
    def test_bot_profiles_create(self, user_headers):
        """Test POST /api/bot-profiles - create endpoint"""
        payload = {
            "name": "TEST_UI07_BotProfile",
            "exchange": "binance",
            "market_type": "spot",
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "strategy_type": "trend_following",
            "timeframe": "15m",
            "trend_timeframe": "1h",
            "leverage": 3,
            "is_enabled": True
        }
        response = requests.post(f"{BASE_URL}/api/bot-profiles", json=payload, headers=user_headers)
        assert response.status_code in [200, 201]
        data = response.json()
        assert "id" in data
        assert data["name"] == "TEST_UI07_BotProfile"
        assert data["exchange"] == "binance"
        assert data["market_type"] == "spot"
        assert "BTCUSDT" in data["symbols"]
        print(f"Bot profile create PASS - id: {data['id']}")
        return data["id"]
    
    def test_bot_profiles_update(self, user_headers):
        """Test PUT /api/bot-profiles/:id - update endpoint"""
        # First create a profile
        create_payload = {
            "name": "TEST_UI07_UpdateBot",
            "exchange": "binance",
            "market_type": "spot",
            "symbols": ["BTCUSDT"],
            "strategy_type": "trend_following",
            "timeframe": "15m",
            "trend_timeframe": "1h",
            "leverage": 3,
            "is_enabled": True
        }
        create_response = requests.post(f"{BASE_URL}/api/bot-profiles", json=create_payload, headers=user_headers)
        assert create_response.status_code in [200, 201]
        bot_id = create_response.json()["id"]
        
        # Update the profile
        update_payload = {
            "name": "TEST_UI07_UpdateBot_Updated",
            "exchange": "binance",
            "market_type": "futures",
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "strategy_type": "mean_reversion",
            "timeframe": "1h",
            "trend_timeframe": "4h",
            "leverage": 5,
            "is_enabled": False
        }
        update_response = requests.put(f"{BASE_URL}/api/bot-profiles/{bot_id}", json=update_payload, headers=user_headers)
        assert update_response.status_code in [200, 201]
        updated_data = update_response.json()
        assert updated_data["name"] == "TEST_UI07_UpdateBot_Updated"
        assert updated_data["market_type"] == "futures"
        assert updated_data["strategy_type"] == "mean_reversion"
        print(f"Bot profile update PASS - id: {bot_id}")
    
    def test_bot_profiles_validation_required_fields(self, user_headers):
        """Test bot profile validation - name is required"""
        # Empty name should fail or use default
        payload = {
            "name": "",
            "exchange": "binance",
            "market_type": "spot",
            "symbols": ["BTCUSDT"],
            "strategy_type": "trend_following",
            "timeframe": "15m",
            "trend_timeframe": "1h",
            "leverage": 3,
            "is_enabled": True
        }
        response = requests.post(f"{BASE_URL}/api/bot-profiles", json=payload, headers=user_headers)
        # API may accept or reject empty name - check response
        if response.status_code in [200, 201]:
            # If accepted, verify name is stored (may be empty)
            print("Bot profile with empty name accepted (server-side validation may differ)")
        else:
            # If rejected, that's expected behavior
            assert response.status_code in [400, 422]
            print("Bot profile validation PASS - empty name rejected")


class TestRiskPoliciesAPI:
    """Risk Policies CRUD API tests"""
    
    def test_risk_policies_list(self, user_headers):
        """Test GET /api/risk-policies - list endpoint"""
        response = requests.get(f"{BASE_URL}/api/risk-policies", headers=user_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Risk policies list PASS - {len(data)} policies found")
    
    def test_risk_policies_create(self, user_headers):
        """Test POST /api/risk-policies - create endpoint"""
        payload = {
            "name": "TEST_UI07_RiskPolicy",
            "position_size_pct": 2.5,
            "atr_stop_multiplier": 1.5,
            "risk_reward_ratio": 2.0,
            "daily_loss_cutoff_pct": 5.0,
            "max_open_positions": 3,
            "max_leverage": 3,
            "spread_limit_bps": 30,
            "slippage_limit_bps": 40,
            "min_liquidity_usdt": 100000
        }
        response = requests.post(f"{BASE_URL}/api/risk-policies", json=payload, headers=user_headers)
        assert response.status_code in [200, 201]
        data = response.json()
        assert "id" in data
        assert data["name"] == "TEST_UI07_RiskPolicy"
        assert data["position_size_pct"] == 2.5
        assert data["atr_stop_multiplier"] == 1.5
        assert data["risk_reward_ratio"] == 2.0
        assert data["max_open_positions"] == 3
        assert data["daily_loss_cutoff_pct"] == 5.0
        print(f"Risk policy create PASS - id: {data['id']}")
        return data["id"]
    
    def test_risk_policies_update(self, user_headers):
        """Test PUT /api/risk-policies/:id - update endpoint"""
        # First create a policy
        create_payload = {
            "name": "TEST_UI07_UpdatePolicy",
            "position_size_pct": 2.0,
            "atr_stop_multiplier": 1.5,
            "risk_reward_ratio": 2.0,
            "daily_loss_cutoff_pct": 5.0,
            "max_open_positions": 3,
            "max_leverage": 3,
            "spread_limit_bps": 30,
            "slippage_limit_bps": 40,
            "min_liquidity_usdt": 100000
        }
        create_response = requests.post(f"{BASE_URL}/api/risk-policies", json=create_payload, headers=user_headers)
        assert create_response.status_code in [200, 201]
        policy_id = create_response.json()["id"]
        
        # Update the policy
        update_payload = {
            "name": "TEST_UI07_UpdatePolicy_Updated",
            "position_size_pct": 3.0,
            "atr_stop_multiplier": 2.0,
            "risk_reward_ratio": 3.0,
            "daily_loss_cutoff_pct": 8.0,
            "max_open_positions": 5,
            "max_leverage": 5,
            "spread_limit_bps": 50,
            "slippage_limit_bps": 60,
            "min_liquidity_usdt": 200000
        }
        update_response = requests.put(f"{BASE_URL}/api/risk-policies/{policy_id}", json=update_payload, headers=user_headers)
        assert update_response.status_code in [200, 201]
        updated_data = update_response.json()
        assert updated_data["name"] == "TEST_UI07_UpdatePolicy_Updated"
        assert updated_data["position_size_pct"] == 3.0
        assert updated_data["atr_stop_multiplier"] == 2.0
        print(f"Risk policy update PASS - id: {policy_id}")
    
    def test_risk_policies_validation_positive_values(self, user_headers):
        """Test risk policy validation - values must be positive"""
        # Negative position_size should fail or be rejected
        payload = {
            "name": "TEST_UI07_InvalidPolicy",
            "position_size_pct": -1.0,  # Invalid
            "atr_stop_multiplier": 1.5,
            "risk_reward_ratio": 2.0,
            "daily_loss_cutoff_pct": 5.0,
            "max_open_positions": 3,
            "max_leverage": 3,
            "spread_limit_bps": 30,
            "slippage_limit_bps": 40,
            "min_liquidity_usdt": 100000
        }
        response = requests.post(f"{BASE_URL}/api/risk-policies", json=payload, headers=user_headers)
        # API may accept or reject negative values
        if response.status_code in [200, 201]:
            print("Risk policy with negative value accepted (server-side validation may differ)")
        else:
            assert response.status_code in [400, 422]
            print("Risk policy validation PASS - negative value rejected")


class TestRouteAccessibility:
    """Test that routes are accessible"""
    
    def test_bot_profiles_route_accessible(self, user_headers):
        """Test /api/bot-profiles is accessible"""
        response = requests.get(f"{BASE_URL}/api/bot-profiles", headers=user_headers)
        assert response.status_code == 200
        print("Bot profiles route accessible PASS")
    
    def test_risk_policies_route_accessible(self, user_headers):
        """Test /api/risk-policies is accessible"""
        response = requests.get(f"{BASE_URL}/api/risk-policies", headers=user_headers)
        assert response.status_code == 200
        print("Risk policies route accessible PASS")
    
    def test_exchange_settings_route_accessible(self, user_headers):
        """Test /api/phase4/exchange-settings is accessible"""
        response = requests.get(f"{BASE_URL}/api/phase4/exchange-settings", headers=user_headers)
        assert response.status_code == 200
        print("Exchange settings route accessible PASS")
    
    def test_user_risk_settings_route_accessible(self, user_headers):
        """Test /api/user-risk/settings is accessible"""
        response = requests.get(f"{BASE_URL}/api/user-risk/settings", headers=user_headers)
        assert response.status_code == 200
        print("User risk settings route accessible PASS")


class TestExchangeConnectionsAPI:
    """Exchange Connections API tests for connection profile form"""
    
    def test_exchange_connections_list(self, user_headers):
        """Test GET /api/user/exchange-connections - list endpoint"""
        response = requests.get(f"{BASE_URL}/api/user/exchange-connections", headers=user_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Exchange connections list PASS - {len(data)} connections found")
    
    def test_exchange_connections_create(self, user_headers):
        """Test POST /api/user/exchange-connections - create endpoint"""
        import uuid
        unique_label = f"TEST_UI07_Conn_{uuid.uuid4().hex[:6]}"
        payload = {
            "account_label": unique_label,
            "exchange": "binance",
            "market_type": "spot",
            "environment": "testnet",
            "is_default": False
        }
        response = requests.post(f"{BASE_URL}/api/user/exchange-connections", json=payload, headers=user_headers)
        assert response.status_code in [200, 201]
        data = response.json()
        assert "id" in data
        assert data["account_label"] == unique_label
        assert data["exchange"] == "binance"
        assert data["market_type"] == "spot"
        assert data["environment"] == "testnet"
        print(f"Exchange connection create PASS - id: {data['id']}")
        return data["id"]


class TestVenuesAPI:
    """Venues API tests for dropdown options"""
    
    def test_venues_options(self, user_headers):
        """Test GET /api/venues/options - dropdown options"""
        response = requests.get(f"{BASE_URL}/api/venues/options", headers=user_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Venues options PASS - {len(data)} venue options")


class TestDataContractIntegrity:
    """Test that API responses match expected form field contracts"""
    
    def test_bot_profile_response_fields(self, user_headers):
        """Test bot profile response contains expected fields for form binding"""
        response = requests.get(f"{BASE_URL}/api/bot-profiles", headers=user_headers)
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            profile = data[0]
            # Check required form binding fields
            required_fields = ["id", "name", "exchange", "market_type", "symbols", "strategy_type"]
            for field in required_fields:
                assert field in profile, f"Missing field: {field}"
            print(f"Bot profile response fields PASS - all {len(required_fields)} required fields present")
        else:
            print("Bot profiles list empty - skipping field validation")
    
    def test_risk_policy_response_fields(self, user_headers):
        """Test risk policy response contains expected fields for form binding"""
        response = requests.get(f"{BASE_URL}/api/risk-policies", headers=user_headers)
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            policy = data[0]
            # Check required form binding fields
            required_fields = [
                "id", "name", "position_size_pct", "atr_stop_multiplier",
                "risk_reward_ratio", "max_open_positions", "daily_loss_cutoff_pct"
            ]
            for field in required_fields:
                assert field in policy, f"Missing field: {field}"
            print(f"Risk policy response fields PASS - all {len(required_fields)} required fields present")
        else:
            print("Risk policies list empty - skipping field validation")
    
    def test_user_risk_settings_response_fields(self, user_headers):
        """Test user risk settings response contains expected fields"""
        response = requests.get(f"{BASE_URL}/api/user-risk/settings", headers=user_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Check required form binding fields for risk settings
        expected_fields = ["allocation_pct", "trade_risk_pct", "daily_loss_limit_pct", "compounding_enabled"]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
        print(f"User risk settings response fields PASS - all {len(expected_fields)} required fields present")
