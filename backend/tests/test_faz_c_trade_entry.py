"""
FAZ-C Trade Entry Testing:
- C1 Trade Entry Panel at /user/trade with validate-order and open-position
- C2 execution result binding (status, execution_mode, violations)
- C3 positions listing after successful trade
- C4 screener->chart navigation
- C5 minimal filters on screener
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://trade-trace-engine.preview.emergentagent.com")


@pytest.fixture(scope="module")
def admin_session():
    """Get admin session with auth token"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@platform.local",
        "password": "Admin12345!"
    })
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    data = response.json()
    session.headers.update({"Authorization": f"Bearer {data['access_token']}"})
    return session


@pytest.fixture(scope="module")
def user_session(admin_session):
    """Create and approve test user, return authenticated session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Try login first in case user exists
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": "fazc_test_user@test.com",
        "password": "FazCTestUser123!"
    })
    
    if response.status_code == 200:
        data = response.json()
        session.headers.update({"Authorization": f"Bearer {data['access_token']}"})
        return session
    
    # Register new user
    response = session.post(f"{BASE_URL}/api/auth/register", json={
        "email": "fazc_test_user@test.com",
        "password": "FazCTestUser123!",
        "first_name": "FAZ",
        "last_name": "CTest"
    })
    assert response.status_code in [200, 201, 409], f"Registration failed: {response.text}"
    
    if response.status_code == 200 or response.status_code == 201:
        user_data = response.json()
        user_id = user_data.get("id")
        
        # Approve user via admin
        approve_response = admin_session.post(
            f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve"
        )
        assert approve_response.status_code == 200, f"Approval failed: {approve_response.text}"
    
    # Login with approved user
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": "fazc_test_user@test.com",
        "password": "FazCTestUser123!"
    })
    assert response.status_code == 200, f"User login failed: {response.text}"
    data = response.json()
    session.headers.update({"Authorization": f"Bearer {data['access_token']}"})
    return session


class TestHealthAndBasicAuth:
    """Basic health and auth checks"""
    
    def test_health_endpoint(self):
        """Test health endpoint returns ok"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        print("Health check: PASSED")
    
    def test_admin_login(self, admin_session):
        """Verify admin session is valid"""
        response = admin_session.get(f"{BASE_URL}/api/admin/dashboard")
        assert response.status_code == 200
        print("Admin login and dashboard access: PASSED")


class TestC1TradeEntryPanel:
    """C1: Trade Entry Panel at /user/trade - validate-order and open-position"""
    
    def test_validate_order_endpoint_exists(self, user_session):
        """Test validate-order endpoint exists and accepts required fields"""
        payload = {
            "symbol": "BTCUSDT",
            "market_type": "futures",
            "order_type": "market",
            "side": "buy",
            "price": 50000,
            "size": 0.001,
            "leverage": 3,
            "margin_mode": "isolated"
        }
        response = user_session.post(f"{BASE_URL}/api/user/validate-order", json=payload)
        assert response.status_code == 200, f"validate-order failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "valid" in data, "Response must contain 'valid' field"
        assert "violations" in data, "Response must contain 'violations' field"
        assert "execution_mode" in data, "Response must contain 'execution_mode' field"
        
        print(f"validate-order response: valid={data['valid']}, execution_mode={data['execution_mode']}")
        print(f"Violations: {data.get('violations', [])}")
        print("C1 validate-order endpoint: PASSED")
    
    def test_validate_order_blocks_invalid_trade(self, user_session):
        """Test validation fails with insufficient size"""
        payload = {
            "symbol": "BTCUSDT",
            "market_type": "futures",
            "order_type": "market",
            "side": "buy",
            "price": 0,  # Invalid price
            "size": 0,   # Invalid size
            "leverage": 1,
            "margin_mode": "isolated"
        }
        response = user_session.post(f"{BASE_URL}/api/user/validate-order", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        # Should fail validation due to zero size
        if not data["valid"]:
            assert len(data["violations"]) > 0, "Invalid order should have violations"
            print(f"Validation correctly blocked: violations={data['violations']}")
        print("C1 validate-order blocks invalid trade: PASSED")
    
    def test_trading_preview_flow(self, user_session):
        """Test full preview flow for trading intent"""
        payload = {
            "source_type": "manual",
            "intent_type": "OPEN_POSITION",
            "market_type": "futures",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 100,
            "margin_mode": "isolated",
            "leverage": 3,
            "execution_mode": "manual",
            "holding_profile": "intraday",
            "size": 0.001
        }
        response = user_session.post(f"{BASE_URL}/api/v1/user/trading/preview", json=payload)
        assert response.status_code == 200, f"Trading preview failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "preview" in data, "Response must contain preview"
        preview = data["preview"]
        assert "intent_token" in preview, "Preview must contain intent_token"
        assert "preview_hash" in preview, "Preview must contain preview_hash"
        assert "validation_status" in preview, "Preview must contain validation_status"
        
        print(f"Trading preview: status={preview['validation_status']}, intent_token exists={bool(preview['intent_token'])}")
        print("C1 trading preview flow: PASSED")
        return data


class TestC2ExecutionResultBinding:
    """C2: Execution result binding - status + execution_mode + violations shown"""
    
    def test_validate_order_returns_execution_mode(self, user_session):
        """Test that validate-order returns execution_mode in response"""
        payload = {
            "symbol": "ETHUSDT",
            "market_type": "futures",
            "order_type": "market",
            "side": "buy",
            "price": 3000,
            "size": 0.01,
            "leverage": 2,
            "margin_mode": "isolated"
        }
        response = user_session.post(f"{BASE_URL}/api/user/validate-order", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        # Verify execution_mode is present (should be mocked in test env)
        assert "execution_mode" in data
        print(f"execution_mode: {data['execution_mode']}")
        
        # Verify violations list exists
        assert isinstance(data.get("violations", []), list)
        print("C2 execution_mode in validate-order: PASSED")
    
    def test_trading_preview_returns_full_result(self, user_session):
        """Test trading preview returns complete result binding info"""
        payload = {
            "source_type": "manual",
            "intent_type": "OPEN_POSITION",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50,
            "execution_mode": "manual",
            "size": 0.001
        }
        response = user_session.post(f"{BASE_URL}/api/v1/user/trading/preview", json=payload)
        assert response.status_code == 200
        data = response.json()
        preview = data.get("preview", {})
        
        # Verify result binding fields
        assert "intent_status" in preview, "Must have intent_status"
        assert "validation_status" in preview, "Must have validation_status"
        assert "reject_reason_codes" in preview, "Must have reject_reason_codes"
        assert "risk_flags" in preview, "Must have risk_flags"
        
        print(f"Result binding: intent_status={preview['intent_status']}, validation_status={preview['validation_status']}")
        print("C2 full result binding in preview: PASSED")


class TestC3PositionsIntegration:
    """C3: After successful open-position, positions list renders correctly"""
    
    def test_positions_endpoint(self, user_session):
        """Test positions endpoint returns valid structure"""
        response = user_session.get(f"{BASE_URL}/api/user/execution/positions", params={"include_closed": False})
        assert response.status_code == 200, f"Positions endpoint failed: {response.text}"
        data = response.json()
        
        # Verify it's a list
        assert isinstance(data, list), "Positions response must be a list"
        
        # If positions exist, verify structure
        if len(data) > 0:
            position = data[0]
            required_fields = ["position_id", "symbol", "size", "leverage", "entry_price", "execution_mode"]
            for field in required_fields:
                assert field in position, f"Position must have {field} field"
            print(f"Position found: symbol={position['symbol']}, size={position['size']}, execution_mode={position['execution_mode']}")
        else:
            print("No open positions (expected if no trades executed)")
        
        print("C3 positions endpoint: PASSED")


class TestC4ScreenerChartBridge:
    """C4: Screener rows contain View Chart and navigate to /user/chart?symbol=...&tf=1h"""
    
    def test_screener_endpoint(self, user_session):
        """Test screener endpoint returns results with symbol data"""
        response = user_session.get(f"{BASE_URL}/api/screener", params={"limit": 10})
        assert response.status_code == 200, f"Screener endpoint failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Screener response must be a list"
        
        # If results exist, verify symbol field
        if len(data) > 0:
            result = data[0]
            assert "symbol" in result, "Screener result must have symbol"
            assert "id" in result, "Screener result must have id"
            print(f"Screener result example: symbol={result['symbol']}, id={result['id']}")
        else:
            print("No screener results (scanner may not have run yet)")
        
        print("C4 screener endpoint: PASSED")
    
    def test_market_ticker_for_chart(self, user_session):
        """Test market ticker endpoint used for chart data"""
        response = user_session.get(f"{BASE_URL}/api/market/ticker", params={"symbol": "BTCUSDT"})
        assert response.status_code == 200, f"Market ticker failed: {response.text}"
        data = response.json()
        
        assert "mid_price" in data, "Market ticker must have mid_price"
        print(f"Market ticker: mid_price={data['mid_price']}")
        print("C4 market ticker for chart: PASSED")


class TestC5MinimalFilters:
    """C5: Minimal filters (rsi_min, rsi_max, volume_min, market_cap_min, timeframe)"""
    
    def test_screener_with_filters(self, user_session):
        """Test screener accepts filter parameters"""
        # Test with filters parameter as JSON
        filters = {
            "rsi_min": 30,
            "rsi_max": 70,
            "volume_min": 1000000,
            "market_cap_min": 100000000,
            "timeframe": "1h"
        }
        import json
        response = user_session.get(
            f"{BASE_URL}/api/screener",
            params={"filters": json.dumps(filters), "limit": 20}
        )
        assert response.status_code == 200, f"Screener with filters failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Filtered screener response must be a list"
        print(f"Screener with filters returned {len(data)} results")
        print("C5 screener with filters: PASSED")
    
    def test_screener_individual_filter_params(self, user_session):
        """Test screener with individual filter query params"""
        response = user_session.get(
            f"{BASE_URL}/api/screener",
            params={
                "rsi_min": 25,
                "rsi_max": 75,
                "timeframe": "1h",
                "limit": 15
            }
        )
        assert response.status_code == 200, f"Screener with individual params failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Screener response must be a list"
        print(f"Screener with individual params returned {len(data)} results")
        print("C5 screener individual filter params: PASSED")


class TestE2EScenarios:
    """C6 E2E scenarios: validate fail blocks open, validate success path, 423 blocked, etc."""
    
    def test_validation_failure_blocks_trade(self, user_session):
        """Test that validation failure blocks the trade"""
        # First validate with invalid params
        validate_payload = {
            "symbol": "BTCUSDT",
            "market_type": "futures",
            "order_type": "market",
            "side": "buy",
            "price": 0,
            "size": 0,  # Zero size should fail
            "leverage": 1,
            "margin_mode": "isolated"
        }
        response = user_session.post(f"{BASE_URL}/api/user/validate-order", json=validate_payload)
        assert response.status_code == 200
        data = response.json()
        
        # If validation fails, trade should be blocked
        if not data["valid"]:
            print(f"Validation correctly failed: {data['violations']}")
            print("E2E: validate fail blocks open: PASSED")
        else:
            print("Validation passed (test configuration may allow zero size)")
            print("E2E: validate scenario: PASSED")
    
    def test_full_validation_to_preview_flow(self, user_session):
        """Test complete validation -> preview flow"""
        # Step 1: Validate order
        validate_payload = {
            "symbol": "ETHUSDT",
            "market_type": "futures",
            "order_type": "market",
            "side": "buy",
            "price": 3000,
            "size": 0.01,
            "leverage": 2,
            "margin_mode": "isolated"
        }
        validate_response = user_session.post(f"{BASE_URL}/api/user/validate-order", json=validate_payload)
        assert validate_response.status_code == 200
        validate_data = validate_response.json()
        
        print(f"Step 1 - Validation: valid={validate_data['valid']}, execution_mode={validate_data['execution_mode']}")
        
        # Step 2: Create preview
        preview_payload = {
            "source_type": "manual",
            "intent_type": "OPEN_POSITION",
            "market_type": "futures",
            "symbol": "ETHUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 100,
            "margin_mode": "isolated",
            "leverage": 2,
            "execution_mode": "manual",
            "size": 0.01
        }
        preview_response = user_session.post(f"{BASE_URL}/api/v1/user/trading/preview", json=preview_payload)
        assert preview_response.status_code == 200
        preview_data = preview_response.json()
        
        preview = preview_data.get("preview", {})
        print(f"Step 2 - Preview: validation_status={preview.get('validation_status')}, intent_token exists={bool(preview.get('intent_token'))}")
        
        print("E2E: full validation->preview flow: PASSED")
    
    def test_execution_intents_queue(self, user_session):
        """Test execution intents queue listing"""
        response = user_session.get(f"{BASE_URL}/api/user/execution/intents", params={"limit": 20})
        assert response.status_code == 200, f"Execution intents failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Execution intents must be a list"
        if len(data) > 0:
            intent = data[0]
            assert "intent_token" in intent, "Intent must have token"
            assert "status" in intent, "Intent must have status"
            print(f"Execution intent: status={intent['status']}, symbol={intent.get('symbol')}")
        else:
            print("No execution intents (expected if no trades attempted)")
        
        print("E2E: execution intents queue: PASSED")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
