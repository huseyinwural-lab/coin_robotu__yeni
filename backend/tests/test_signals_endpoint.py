"""
Test suite for GET /api/user/signals endpoint
Tests:
- Response contains rich fields: signal, signal_direction, execution_intent_status, proposed_notional, linked_trade_id, linked_open_trade_count, has_open_position_link
- Endpoint responds within 15s timeout
- Response structure matches UserSignalResponse schema
"""
import os
import time
import pytest
import requests

# Use local backend for testing (external URL may timeout)
BASE_URL = os.environ.get("TEST_BACKEND_URL", "http://127.0.0.1:8001").rstrip("/")
TEST_EMAIL = "review.user@platform.local"
TEST_PASSWORD = "ReviewUser123!"


@pytest.fixture(scope="module")
def auth_token():
    """Authenticate and get token for test user"""
    if not BASE_URL:
        pytest.skip("TEST_BACKEND_URL not set")
    
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=60
    )
    
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")
    
    data = response.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip("No token in auth response")
    
    return token


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Create authenticated session"""
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    })
    return session


class TestSignalsEndpointPerformance:
    """Test signals endpoint performance - must respond within 15s"""
    
    def test_signals_endpoint_responds_within_timeout(self, api_client):
        """GET /api/user/signals should respond within 15 seconds"""
        start_time = time.time()
        response = api_client.get(f"{BASE_URL}/api/user/signals", params={"limit": 80}, timeout=15)
        elapsed = time.time() - start_time
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        assert elapsed < 15, f"Response took {elapsed:.2f}s, expected < 15s"
        print(f"✓ Signals endpoint responded in {elapsed:.2f}s")


class TestSignalsResponseSchema:
    """Test signals response contains required rich fields"""
    
    def test_signals_returns_list(self, api_client):
        """GET /api/user/signals should return a list"""
        response = api_client.get(f"{BASE_URL}/api/user/signals", params={"limit": 80}, timeout=15)
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"✓ Signals endpoint returned list with {len(data)} items")
    
    def test_signal_has_signal_field(self, api_client):
        """Each signal should have 'signal' field (long/short/none)"""
        response = api_client.get(f"{BASE_URL}/api/user/signals", params={"limit": 80}, timeout=15)
        assert response.status_code == 200
        
        data = response.json()
        if len(data) == 0:
            pytest.skip("No signals to test - empty list is valid")
        
        for signal in data[:5]:  # Check first 5
            assert "signal" in signal, f"Signal missing 'signal' field: {signal.get('id')}"
        print(f"✓ All checked signals have 'signal' field")
    
    def test_signal_has_signal_direction_field(self, api_client):
        """Each signal should have 'signal_direction' field"""
        response = api_client.get(f"{BASE_URL}/api/user/signals", params={"limit": 80}, timeout=15)
        assert response.status_code == 200
        
        data = response.json()
        if len(data) == 0:
            pytest.skip("No signals to test")
        
        for signal in data[:5]:
            assert "signal_direction" in signal, f"Signal missing 'signal_direction' field: {signal.get('id')}"
        print(f"✓ All checked signals have 'signal_direction' field")
    
    def test_signal_has_execution_intent_status_field(self, api_client):
        """Each signal should have 'execution_intent_status' field"""
        response = api_client.get(f"{BASE_URL}/api/user/signals", params={"limit": 80}, timeout=15)
        assert response.status_code == 200
        
        data = response.json()
        if len(data) == 0:
            pytest.skip("No signals to test")
        
        for signal in data[:5]:
            assert "execution_intent_status" in signal, f"Signal missing 'execution_intent_status' field: {signal.get('id')}"
        print(f"✓ All checked signals have 'execution_intent_status' field")
    
    def test_signal_has_proposed_notional_field(self, api_client):
        """Each signal should have 'proposed_notional' field"""
        response = api_client.get(f"{BASE_URL}/api/user/signals", params={"limit": 80}, timeout=15)
        assert response.status_code == 200
        
        data = response.json()
        if len(data) == 0:
            pytest.skip("No signals to test")
        
        for signal in data[:5]:
            assert "proposed_notional" in signal, f"Signal missing 'proposed_notional' field: {signal.get('id')}"
        print(f"✓ All checked signals have 'proposed_notional' field")
    
    def test_signal_has_linked_trade_id_field(self, api_client):
        """Each signal should have 'linked_trade_id' field"""
        response = api_client.get(f"{BASE_URL}/api/user/signals", params={"limit": 80}, timeout=15)
        assert response.status_code == 200
        
        data = response.json()
        if len(data) == 0:
            pytest.skip("No signals to test")
        
        for signal in data[:5]:
            assert "linked_trade_id" in signal, f"Signal missing 'linked_trade_id' field: {signal.get('id')}"
        print(f"✓ All checked signals have 'linked_trade_id' field")
    
    def test_signal_has_linked_open_trade_count_field(self, api_client):
        """Each signal should have 'linked_open_trade_count' field"""
        response = api_client.get(f"{BASE_URL}/api/user/signals", params={"limit": 80}, timeout=15)
        assert response.status_code == 200
        
        data = response.json()
        if len(data) == 0:
            pytest.skip("No signals to test")
        
        for signal in data[:5]:
            assert "linked_open_trade_count" in signal, f"Signal missing 'linked_open_trade_count' field: {signal.get('id')}"
            assert isinstance(signal["linked_open_trade_count"], int), f"linked_open_trade_count should be int"
        print(f"✓ All checked signals have 'linked_open_trade_count' field (int)")
    
    def test_signal_has_has_open_position_link_field(self, api_client):
        """Each signal should have 'has_open_position_link' field"""
        response = api_client.get(f"{BASE_URL}/api/user/signals", params={"limit": 80}, timeout=15)
        assert response.status_code == 200
        
        data = response.json()
        if len(data) == 0:
            pytest.skip("No signals to test")
        
        for signal in data[:5]:
            assert "has_open_position_link" in signal, f"Signal missing 'has_open_position_link' field: {signal.get('id')}"
            assert isinstance(signal["has_open_position_link"], bool), f"has_open_position_link should be bool"
        print(f"✓ All checked signals have 'has_open_position_link' field (bool)")


class TestSignalsDataIntegrity:
    """Test signals data integrity and consistency"""
    
    def test_signal_core_fields_present(self, api_client):
        """Each signal should have core required fields"""
        response = api_client.get(f"{BASE_URL}/api/user/signals", params={"limit": 80}, timeout=15)
        assert response.status_code == 200
        
        data = response.json()
        if len(data) == 0:
            pytest.skip("No signals to test")
        
        required_fields = [
            "id", "signal_id", "user_id", "symbol", "strategy_code",
            "confidence", "mode", "status", "created_at"
        ]
        
        for signal in data[:5]:
            for field in required_fields:
                assert field in signal, f"Signal missing required field '{field}': {signal.get('id')}"
        print(f"✓ All checked signals have core required fields")
    
    def test_signal_status_values_valid(self, api_client):
        """Signal status should be one of valid values"""
        response = api_client.get(f"{BASE_URL}/api/user/signals", params={"limit": 80}, timeout=15)
        assert response.status_code == 200
        
        data = response.json()
        if len(data) == 0:
            pytest.skip("No signals to test")
        
        valid_statuses = {"pending", "ready", "approved", "blocked", "rejected", "expired", "submitted", "filled", "queued"}
        
        for signal in data[:10]:
            status = str(signal.get("status", "")).lower()
            assert status in valid_statuses, f"Invalid status '{status}' for signal {signal.get('id')}"
        print(f"✓ All checked signals have valid status values")
    
    def test_open_position_link_consistency(self, api_client):
        """has_open_position_link should be consistent with linked_open_trade_count"""
        response = api_client.get(f"{BASE_URL}/api/user/signals", params={"limit": 80}, timeout=15)
        assert response.status_code == 200
        
        data = response.json()
        if len(data) == 0:
            pytest.skip("No signals to test")
        
        for signal in data[:10]:
            has_link = signal.get("has_open_position_link", False)
            count = signal.get("linked_open_trade_count", 0)
            
            # If has_open_position_link is True, count should be > 0
            if has_link:
                assert count > 0, f"has_open_position_link=True but linked_open_trade_count={count} for signal {signal.get('id')}"
            # If count > 0, has_link should be True
            if count > 0:
                assert has_link, f"linked_open_trade_count={count} but has_open_position_link=False for signal {signal.get('id')}"
        print(f"✓ Open position link fields are consistent")


class TestSignalModeEndpoint:
    """Test signal-mode endpoint"""
    
    def test_get_signal_mode(self, api_client):
        """GET /api/user/signal-mode should return mode"""
        response = api_client.get(f"{BASE_URL}/api/user/signal-mode", timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        assert "mode" in data, "Response missing 'mode' field"
        assert data["mode"] in {"MANUAL", "ASSISTED", "AUTO"}, f"Invalid mode: {data['mode']}"
        print(f"✓ Signal mode endpoint returned mode: {data['mode']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
