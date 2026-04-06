"""
Iteration 11 - Observability & Status Contract Testing
Tests for:
- GET /api/user/scanner/status-contract (required fields)
- POST /api/user/scanner/run-async-both + GET /api/user/scanner/run-async/{job_id}
- GET /api/user/signals (blocked_reason_code, blocked_reason_message, blocked_solution_hint)
- POST /api/bot-profiles/{id}/start (fail-fast 422 + status_contract + blocking_reasons)
- GET /api/admin/strategy/status-contract (required fields)
- GET /api/admin/strategy/top-signals (blocked fields)
- POST /api/admin/strategy/signals/{signal_id}/diagnose?auto_fix=true
"""

import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://trade-trace-engine.preview.emergentagent.com").rstrip("/")

# Test credentials
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def user_auth_token(api_client):
    """Get user authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": USER_EMAIL,
        "password": USER_PASSWORD
    })
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    pytest.skip(f"User authentication failed: {response.status_code}")


@pytest.fixture(scope="module")
def admin_auth_token(api_client):
    """Get admin authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    pytest.skip(f"Admin authentication failed: {response.status_code}")


@pytest.fixture(scope="module")
def user_client(api_client, user_auth_token):
    """Session with user auth header"""
    api_client.headers.update({"Authorization": f"Bearer {user_auth_token}"})
    return api_client


@pytest.fixture(scope="function")
def admin_client():
    """Fresh session with admin auth for each test"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login fresh for each admin test
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    
    if response.status_code == 200:
        data = response.json()
        token = data.get("access_token") or data.get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    pytest.skip(f"Admin authentication failed: {response.status_code}")


class TestUserScannerStatusContract:
    """Tests for GET /api/user/scanner/status-contract"""
    
    def test_status_contract_returns_required_fields(self, user_client):
        """Verify status-contract returns all required fields"""
        response = user_client.get(f"{BASE_URL}/api/user/scanner/status-contract")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Required fields per spec
        required_fields = [
            "scanner_ready",
            "strategy_ready",
            "risk_ready",
            "execution_ready",
            "symbols_ready",
            "exchange_ready",
            "bot_status",
            "health",
            "blocking_reasons"
        ]
        
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        # Validate types
        assert isinstance(data["scanner_ready"], bool), "scanner_ready should be boolean"
        assert isinstance(data["strategy_ready"], bool), "strategy_ready should be boolean"
        assert isinstance(data["risk_ready"], bool), "risk_ready should be boolean"
        assert isinstance(data["execution_ready"], bool), "execution_ready should be boolean"
        assert isinstance(data["symbols_ready"], bool), "symbols_ready should be boolean"
        assert isinstance(data["exchange_ready"], bool), "exchange_ready should be boolean"
        assert isinstance(data["bot_status"], str), "bot_status should be string"
        assert isinstance(data["health"], str), "health should be string"
        assert isinstance(data["blocking_reasons"], list), "blocking_reasons should be list"
        
        print(f"✓ Status contract returned all required fields: {list(data.keys())}")
    
    def test_blocking_reasons_structure(self, user_client):
        """Verify blocking_reasons items have correct structure"""
        response = user_client.get(f"{BASE_URL}/api/user/scanner/status-contract")
        
        assert response.status_code == 200
        data = response.json()
        
        blocking_reasons = data.get("blocking_reasons", [])
        
        # If there are blocking reasons, verify structure
        for reason in blocking_reasons:
            assert "code" in reason, "blocking_reason should have 'code'"
            assert "message" in reason, "blocking_reason should have 'message'"
            # hint is optional but should be present if code exists
            if reason.get("code"):
                assert "hint" in reason, "blocking_reason should have 'hint'"
        
        print(f"✓ Blocking reasons structure valid, count: {len(blocking_reasons)}")


class TestUserScannerRunAsyncBoth:
    """Tests for POST /api/user/scanner/run-async-both + GET /api/user/scanner/run-async/{job_id}"""
    
    def test_run_async_both_creates_job(self, user_client):
        """Verify run-async-both creates a job and returns job_id"""
        payload = {
            "mode": "ASSISTED",
            "max_results": 10,
            "symbol_source": "crypto",
            "market_type": "both",
            "symbol_selection_mode": "all_market_symbols",
            "selected_symbols": []
        }
        
        response = user_client.post(f"{BASE_URL}/api/user/scanner/run-async-both", json=payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        assert "job_id" in data, "Response should contain job_id"
        assert "status" in data, "Response should contain status"
        assert data["status"] == "queued", f"Initial status should be 'queued', got {data['status']}"
        assert data.get("market_type") == "both", "market_type should be 'both'"
        
        print(f"✓ run-async-both created job: {data['job_id']}")
        return data["job_id"]
    
    def test_run_async_job_status_polling(self, user_client):
        """Verify job status can be polled and completes"""
        # First create a job
        payload = {
            "mode": "ASSISTED",
            "max_results": 5,
            "symbol_source": "crypto",
            "market_type": "both",
            "symbol_selection_mode": "all_market_symbols",
            "selected_symbols": []
        }
        
        create_response = user_client.post(f"{BASE_URL}/api/user/scanner/run-async-both", json=payload)
        assert create_response.status_code == 200
        
        job_id = create_response.json()["job_id"]
        
        # Poll for completion (max 60 seconds)
        max_attempts = 30
        final_status = None
        
        for attempt in range(max_attempts):
            status_response = user_client.get(f"{BASE_URL}/api/user/scanner/run-async/{job_id}")
            
            assert status_response.status_code == 200, f"Status check failed: {status_response.status_code}"
            
            status_data = status_response.json()
            final_status = status_data.get("status", "").lower()
            
            if final_status in ["completed", "failed"]:
                break
            
            time.sleep(2)
        
        assert final_status in ["completed", "failed"], f"Job did not complete, final status: {final_status}"
        
        # If completed, verify result structure
        if final_status == "completed":
            result = status_data.get("result", {})
            assert "market_type" in result or "runs" in result, "Completed job should have result with market_type or runs"
            print(f"✓ Job completed successfully with status: {final_status}")
        else:
            print(f"⚠ Job failed: {status_data.get('error', 'unknown error')}")


class TestUserSignalsBlockedFields:
    """Tests for GET /api/user/signals blocked fields"""
    
    def test_signals_contain_blocked_fields(self, user_client):
        """Verify signals response contains blocked_reason_code, blocked_reason_message, blocked_solution_hint"""
        response = user_client.get(f"{BASE_URL}/api/user/signals", params={"limit": 50})
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        signals = data if isinstance(data, list) else data.get("items", [])
        
        # Check that blocked fields exist in schema (even if empty)
        blocked_fields = ["blocked_reason_code", "blocked_reason_message", "blocked_solution_hint"]
        
        for signal in signals[:10]:  # Check first 10 signals
            for field in blocked_fields:
                assert field in signal, f"Signal missing field: {field}"
            
            # If status is blocked, verify fields are populated
            if signal.get("status") == "blocked":
                code = signal.get("blocked_reason_code", "")
                message = signal.get("blocked_reason_message", "")
                hint = signal.get("blocked_solution_hint", "")
                
                # At least code should be non-empty for blocked signals
                assert code, f"Blocked signal should have blocked_reason_code, got: {code}"
                print(f"  Blocked signal: code={code}, message={message[:50] if message else 'N/A'}...")
        
        print(f"✓ Signals contain blocked fields, total signals: {len(signals)}")


class TestBotProfileStartFailFast:
    """Tests for POST /api/bot-profiles/{id}/start fail-fast behavior"""
    
    def test_bot_start_returns_status_contract_on_failure(self, user_client):
        """Verify bot start returns 422 with status_contract and blocking_reasons on binding failure"""
        # First get list of bot profiles
        list_response = user_client.get(f"{BASE_URL}/api/bot-profiles")
        
        assert list_response.status_code == 200, f"Failed to list bot profiles: {list_response.status_code}"
        
        bots = list_response.json()
        
        if not bots:
            pytest.skip("No bot profiles available for testing")
        
        # Try to start a bot
        bot_id = bots[0]["id"]
        start_response = user_client.post(f"{BASE_URL}/api/bot-profiles/{bot_id}/start")
        
        # Either 200 (success) or 422 (binding failed)
        assert start_response.status_code in [200, 422], f"Unexpected status: {start_response.status_code}"
        
        data = start_response.json()
        
        if start_response.status_code == 422:
            # Verify fail-fast contract
            detail = data.get("detail", {})
            
            assert "status_contract" in detail, "422 response should contain status_contract in detail"
            assert "blocking_reasons" in detail, "422 response should contain blocking_reasons in detail"
            
            status_contract = detail["status_contract"]
            blocking_reasons = detail["blocking_reasons"]
            
            # Verify status_contract fields
            contract_fields = ["scanner_ready", "strategy_ready", "risk_ready", "execution_ready", "symbols_ready", "exchange_ready"]
            for field in contract_fields:
                assert field in status_contract, f"status_contract missing field: {field}"
            
            print(f"✓ Bot start returned 422 with status_contract and {len(blocking_reasons)} blocking_reasons")
        else:
            # Success case
            assert "status" in data, "Success response should contain status"
            print(f"✓ Bot started successfully with status: {data.get('status')}")


class TestAdminStrategyStatusContract:
    """Tests for GET /api/admin/strategy/status-contract"""
    
    def test_admin_status_contract_returns_required_fields(self, admin_client):
        """Verify admin status-contract returns all required fields"""
        response = admin_client.get(f"{BASE_URL}/api/admin/strategy/status-contract")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Required fields per spec
        required_fields = [
            "scanner_ready",
            "strategy_ready",
            "risk_ready",
            "execution_ready",
            "symbols_ready",
            "exchange_ready",
            "bot_status",
            "health",
            "blocking_reasons"
        ]
        
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        # Validate types
        assert isinstance(data["scanner_ready"], bool), "scanner_ready should be boolean"
        assert isinstance(data["strategy_ready"], bool), "strategy_ready should be boolean"
        assert isinstance(data["risk_ready"], bool), "risk_ready should be boolean"
        assert isinstance(data["execution_ready"], bool), "execution_ready should be boolean"
        assert isinstance(data["symbols_ready"], bool), "symbols_ready should be boolean"
        assert isinstance(data["exchange_ready"], bool), "exchange_ready should be boolean"
        assert isinstance(data["bot_status"], str), "bot_status should be string"
        assert isinstance(data["health"], str), "health should be string"
        assert isinstance(data["blocking_reasons"], list), "blocking_reasons should be list"
        
        print(f"✓ Admin status contract returned all required fields: {list(data.keys())}")


class TestAdminTopSignalsBlockedFields:
    """Tests for GET /api/admin/strategy/top-signals blocked fields"""
    
    def test_top_signals_contain_blocked_fields(self, admin_client):
        """Verify top-signals items contain blocked_reason_code, blocked_reason_message, blocked_solution_hint"""
        response = admin_client.get(f"{BASE_URL}/api/admin/strategy/top-signals", params={"window": "24h", "top_n": 10})
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        items = data.get("items", [])
        
        blocked_fields = ["blocked_reason_code", "blocked_reason_message", "blocked_solution_hint"]
        
        for item in items[:5]:  # Check first 5 items
            for field in blocked_fields:
                assert field in item, f"Top signal item missing field: {field}"
        
        print(f"✓ Top signals contain blocked fields, total items: {len(items)}")


class TestAdminSignalDiagnose:
    """Tests for POST /api/admin/strategy/signals/{signal_id}/diagnose?auto_fix=true"""
    
    def test_diagnose_endpoint_works(self, admin_client):
        """Verify diagnose endpoint with auto_fix=true works"""
        # First get top signals to find a signal_id
        top_response = admin_client.get(f"{BASE_URL}/api/admin/strategy/top-signals", params={"window": "24h", "top_n": 10})
        
        if top_response.status_code != 200:
            pytest.skip(f"Could not get top signals: {top_response.status_code}")
        
        items = top_response.json().get("items", [])
        
        if not items:
            pytest.skip("No signals available for diagnose testing")
        
        # Find a signal with pending_signal_id
        signal_id = None
        for item in items:
            if item.get("pending_signal_id") or item.get("signal_id"):
                signal_id = item.get("signal_id")
                break
        
        if not signal_id:
            pytest.skip("No signal with valid ID found for diagnose testing")
        
        # Call diagnose with auto_fix=true
        diagnose_response = admin_client.post(
            f"{BASE_URL}/api/admin/strategy/signals/{signal_id}/diagnose",
            params={"auto_fix": True}
        )
        
        # Either 200 (success) or 404 (signal not found in pending_signals)
        assert diagnose_response.status_code in [200, 404], f"Unexpected status: {diagnose_response.status_code}: {diagnose_response.text}"
        
        if diagnose_response.status_code == 200:
            data = diagnose_response.json()
            
            # Verify response structure
            assert "status" in data, "Diagnose response should contain status"
            assert "signal_id" in data, "Diagnose response should contain signal_id"
            
            # Check for blocked fields in response
            blocked_fields = ["blocked_reason_code", "blocked_reason_message", "blocked_solution_hint"]
            for field in blocked_fields:
                assert field in data, f"Diagnose response missing field: {field}"
            
            print(f"✓ Diagnose completed: status={data.get('status')}, actions={data.get('actions_applied', [])}")
        else:
            print(f"⚠ Signal {signal_id} not found in pending_signals (404)")


class TestPipelineBotStartFailFast:
    """Tests for POST /api/pipeline/bots/{bot_id}/start fail-fast behavior"""
    
    def test_pipeline_bot_start_fail_fast(self, user_client):
        """Verify pipeline bot start returns 422 with status_contract on binding failure"""
        # First get list of bot profiles
        list_response = user_client.get(f"{BASE_URL}/api/bot-profiles")
        
        assert list_response.status_code == 200, f"Failed to list bot profiles: {list_response.status_code}"
        
        bots = list_response.json()
        
        if not bots:
            pytest.skip("No bot profiles available for testing")
        
        bot_id = bots[0]["id"]
        
        # Try pipeline start endpoint
        start_response = user_client.post(f"{BASE_URL}/api/pipeline/bots/{bot_id}/start")
        
        # Either 200 (success) or 422 (binding failed)
        assert start_response.status_code in [200, 422], f"Unexpected status: {start_response.status_code}"
        
        data = start_response.json()
        
        if start_response.status_code == 422:
            detail = data.get("detail", {})
            
            assert "status_contract" in detail, "422 response should contain status_contract"
            assert "blocking_reasons" in detail, "422 response should contain blocking_reasons"
            
            print(f"✓ Pipeline bot start returned 422 with fail-fast contract")
        else:
            print(f"✓ Pipeline bot started successfully")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
