# Bot Runtime API Tests - Testing all bot-profiles endpoints via HTTP
# Tests: GET /api/bot-profiles, GET /api/bot-profiles/{id}/detail, lifecycle endpoints, performance/logs/trades
# ruff: noqa: E402

import os
import sys
import time
import uuid
from pathlib import Path

import pytest
import requests

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://unified-orchestrator.preview.emergentagent.com"

# Test credentials from test_credentials.md
TEST_EMAIL = "review.user@platform.local"
TEST_PASSWORD = "ReviewUser123!"


class TestBotRuntimeAPI:
    """Bot Runtime API endpoint tests via HTTP"""

    @pytest.fixture(scope="class")
    def auth_session(self):
        """Get authenticated session with cookies"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        # Login to get auth token
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=30
        )
        
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.status_code} - {login_response.text}")
        
        login_data = login_response.json()
        token = login_data.get("access_token") or login_data.get("token")
        
        if token:
            session.headers.update({"Authorization": f"Bearer {token}"})
        
        return session

    @pytest.fixture(scope="class")
    def created_bot_id(self, auth_session):
        """Create a test bot and return its ID for subsequent tests"""
        unique_name = f"TEST_Bot_{uuid.uuid4().hex[:8]}"
        payload = {
            "name": unique_name,
            "exchange": "binance",
            "market_type": "spot",
            "symbol_source_type": "manual",
            "scanner_id": None,
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "strategy_type": "trend_following",
            "strategy_template_id": None,
            "timeframe": "15m",
            "trend_timeframe": "1h",
            "leverage": 1,
            "is_enabled": True
        }
        
        response = auth_session.post(f"{BASE_URL}/api/bot-profiles", json=payload, timeout=30)
        
        if response.status_code not in [200, 201]:
            pytest.skip(f"Bot creation failed: {response.status_code} - {response.text}")
        
        bot_data = response.json()
        bot_id = bot_data.get("id")
        
        yield bot_id
        
        # Cleanup: delete the test bot
        try:
            auth_session.delete(f"{BASE_URL}/api/bot-profiles/{bot_id}", timeout=30)
        except Exception:
            pass

    # ==================== GET /api/bot-profiles ====================
    def test_list_bot_profiles_returns_runtime_summary(self, auth_session, created_bot_id):
        """GET /api/bot-profiles returns lightweight runtime summary with required fields"""
        response = auth_session.get(f"{BASE_URL}/api/bot-profiles", timeout=30)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
        # Find our created bot
        test_bot = next((b for b in data if b.get("id") == created_bot_id), None)
        
        if test_bot:
            # Verify required fields in runtime summary
            assert "id" in test_bot, "Missing id field"
            assert "name" in test_bot, "Missing name field"
            assert "status" in test_bot, "Missing status field"
            assert "health" in test_bot, "Missing health field"
            assert "mode" in test_bot, "Missing mode field"
            assert "strategy_id" in test_bot or "strategy_name" in test_bot, "Missing strategy identifier"
            assert "symbol_source" in test_bot or "symbol_source_summary" in test_bot, "Missing symbol_source info"
            assert "last_heartbeat" in test_bot, "Missing last_heartbeat field"
            
            print(f"✓ Bot list contains runtime summary with status={test_bot.get('status')}, health={test_bot.get('health')}, mode={test_bot.get('mode')}")

    # ==================== GET /api/bot-profiles/{id}/detail ====================
    def test_get_bot_detail_returns_full_runtime_detail(self, auth_session, created_bot_id):
        """GET /api/bot-profiles/{id}/detail returns full runtime detail with bindings"""
        response = auth_session.get(f"{BASE_URL}/api/bot-profiles/{created_bot_id}/detail", timeout=30)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify config_summary
        assert "config_summary" in data, "Missing config_summary"
        config = data["config_summary"]
        assert "bot_id" in config, "Missing bot_id in config_summary"
        assert "name" in config, "Missing name in config_summary"
        assert "exchange" in config, "Missing exchange in config_summary"
        assert "market_type" in config, "Missing market_type in config_summary"
        assert "strategy_type" in config, "Missing strategy_type in config_summary"
        assert "symbol_source_type" in config, "Missing symbol_source_type in config_summary"
        assert "symbols" in config, "Missing symbols in config_summary"
        
        # Verify runtime_summary
        assert "runtime_summary" in data, "Missing runtime_summary"
        runtime = data["runtime_summary"]
        assert "status" in runtime, "Missing status in runtime_summary"
        assert "mode" in runtime, "Missing mode in runtime_summary"
        assert "health" in runtime, "Missing health in runtime_summary"
        
        # Verify strategy_binding
        assert "strategy_binding" in data, "Missing strategy_binding"
        strategy_binding = data["strategy_binding"]
        assert "selected_strategy_id" in strategy_binding, "Missing selected_strategy_id"
        assert "effective_runtime_strategy_id" in strategy_binding, "Missing effective_runtime_strategy_id"
        
        # Verify risk_binding
        assert "risk_binding" in data, "Missing risk_binding"
        risk_binding = data["risk_binding"]
        assert "risk_source" in risk_binding, "Missing risk_source"
        assert "validation_result" in risk_binding, "Missing validation_result"
        
        # Verify execution_binding
        assert "execution_binding" in data, "Missing execution_binding"
        execution_binding = data["execution_binding"]
        assert "execution_source" in execution_binding, "Missing execution_source"
        
        # Verify binding_validation
        assert "binding_validation" in data, "Missing binding_validation"
        binding_validation = data["binding_validation"]
        assert "selected" in binding_validation, "Missing selected in binding_validation"
        assert "resolved" in binding_validation, "Missing resolved in binding_validation"
        assert "result" in binding_validation, "Missing result in binding_validation"
        
        # Verify compatibility
        assert "compatibility" in data, "Missing compatibility"
        
        # Verify last_execution_summary
        assert "last_execution_summary" in data, "Missing last_execution_summary"
        
        print(f"✓ Bot detail contains all required sections: config_summary, runtime_summary, strategy_binding, risk_binding, execution_binding, binding_validation, compatibility, last_execution_summary")

    # ==================== Manual Symbol Source Resolution ====================
    def test_manual_symbol_source_resolves_correctly(self, auth_session, created_bot_id):
        """Manual symbol source resolves correctly in detail endpoint"""
        response = auth_session.get(f"{BASE_URL}/api/bot-profiles/{created_bot_id}/detail", timeout=30)
        
        assert response.status_code == 200
        data = response.json()
        
        config = data.get("config_summary", {})
        runtime = data.get("runtime_summary", {})
        
        # Check symbol source type is manual
        assert config.get("symbol_source_type") == "manual", f"Expected manual, got {config.get('symbol_source_type')}"
        
        # Check symbol_source_summary
        symbol_summary = runtime.get("symbol_source_summary", {})
        assert symbol_summary.get("source_type") == "manual", f"Expected manual source_type, got {symbol_summary.get('source_type')}"
        assert symbol_summary.get("ok") is True or symbol_summary.get("resolution_status") == "resolved", "Manual symbols should resolve successfully"
        assert len(symbol_summary.get("symbols", [])) > 0, "Should have resolved symbols"
        
        print(f"✓ Manual symbol source resolved correctly with symbols: {symbol_summary.get('symbols')}")

    # ==================== Bot Lifecycle Endpoints ====================
    def test_bot_start_endpoint(self, auth_session, created_bot_id):
        """POST /api/bot-profiles/{id}/start works correctly"""
        response = auth_session.post(f"{BASE_URL}/api/bot-profiles/{created_bot_id}/start", timeout=30)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "bot_id" in data, "Missing bot_id in response"
        assert "status" in data, "Missing status in response"
        
        # Status should be RUNNING or ERROR (if binding fails)
        assert data["status"] in ["RUNNING", "ERROR"], f"Unexpected status: {data['status']}"
        
        if data["status"] == "RUNNING":
            assert data.get("binding_ok") is True, "binding_ok should be True for RUNNING status"
            print(f"✓ Bot started successfully with status=RUNNING")
        else:
            print(f"✓ Bot start returned ERROR (expected if no execution profile): binding_ok={data.get('binding_ok')}")

    def test_bot_pause_endpoint(self, auth_session, created_bot_id):
        """POST /api/bot-profiles/{id}/pause works correctly"""
        response = auth_session.post(f"{BASE_URL}/api/bot-profiles/{created_bot_id}/pause", timeout=30)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "bot_id" in data, "Missing bot_id in response"
        assert "status" in data, "Missing status in response"
        assert data["status"] == "PAUSED", f"Expected PAUSED, got {data['status']}"
        
        print(f"✓ Bot paused successfully with status=PAUSED")

    def test_bot_stop_endpoint(self, auth_session, created_bot_id):
        """POST /api/bot-profiles/{id}/stop works correctly"""
        response = auth_session.post(f"{BASE_URL}/api/bot-profiles/{created_bot_id}/stop", timeout=30)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "bot_id" in data, "Missing bot_id in response"
        assert "status" in data, "Missing status in response"
        assert data["status"] == "STOPPED", f"Expected STOPPED, got {data['status']}"
        
        print(f"✓ Bot stopped successfully with status=STOPPED")

    def test_bot_status_endpoint(self, auth_session, created_bot_id):
        """GET /api/bot-profiles/{id}/status works correctly"""
        response = auth_session.get(f"{BASE_URL}/api/bot-profiles/{created_bot_id}/status", timeout=30)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "id" in data, "Missing id in response"
        assert "name" in data, "Missing name in response"
        assert "status" in data, "Missing status in response"
        assert "health" in data, "Missing health in response"
        assert "mode" in data, "Missing mode in response"
        
        print(f"✓ Bot status returned: status={data['status']}, health={data['health']}, mode={data['mode']}")

    # ==================== Bot Performance/Logs/Trades Endpoints ====================
    def test_bot_performance_endpoint(self, auth_session, created_bot_id):
        """GET /api/bot-profiles/{id}/performance works correctly"""
        response = auth_session.get(f"{BASE_URL}/api/bot-profiles/{created_bot_id}/performance", timeout=30)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "bot_id" in data, "Missing bot_id in response"
        assert "pnl" in data, "Missing pnl in response"
        assert "win_rate" in data, "Missing win_rate in response"
        assert "drawdown" in data, "Missing drawdown in response"
        assert "trade_count" in data, "Missing trade_count in response"
        
        print(f"✓ Bot performance returned: pnl={data['pnl']}, win_rate={data['win_rate']}, trade_count={data['trade_count']}")

    def test_bot_logs_endpoint(self, auth_session, created_bot_id):
        """GET /api/bot-profiles/{id}/logs works correctly"""
        response = auth_session.get(f"{BASE_URL}/api/bot-profiles/{created_bot_id}/logs", timeout=30)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
        # If there are logs, verify structure
        if len(data) > 0:
            log_entry = data[0]
            assert "signal" in log_entry or "symbol" in log_entry, "Log entry should have signal or symbol"
            assert "queue_trace" in log_entry, "Log entry should have queue_trace"
            print(f"✓ Bot logs returned {len(data)} entries with queue_trace")
        else:
            print(f"✓ Bot logs returned empty list (no signals yet)")

    def test_bot_trades_endpoint(self, auth_session, created_bot_id):
        """GET /api/bot-profiles/{id}/trades works correctly"""
        response = auth_session.get(f"{BASE_URL}/api/bot-profiles/{created_bot_id}/trades", timeout=30)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
        # If there are trades, verify structure
        if len(data) > 0:
            trade_entry = data[0]
            assert "order_id" in trade_entry or "symbol" in trade_entry, "Trade entry should have order_id or symbol"
            assert "queue_trace" in trade_entry, "Trade entry should have queue_trace"
            print(f"✓ Bot trades returned {len(data)} entries with queue_trace")
        else:
            print(f"✓ Bot trades returned empty list (no trades yet)")

    # ==================== No Timeout Test ====================
    def test_no_timeout_on_local_backend_path(self, auth_session, created_bot_id):
        """Verify no timeout on create/list/detail/status local backend path"""
        start_time = time.time()
        
        # Test list endpoint
        list_response = auth_session.get(f"{BASE_URL}/api/bot-profiles", timeout=30)
        list_time = time.time() - start_time
        assert list_response.status_code == 200, f"List failed: {list_response.status_code}"
        assert list_time < 10, f"List took too long: {list_time}s"
        
        # Test detail endpoint
        start_time = time.time()
        detail_response = auth_session.get(f"{BASE_URL}/api/bot-profiles/{created_bot_id}/detail", timeout=30)
        detail_time = time.time() - start_time
        assert detail_response.status_code == 200, f"Detail failed: {detail_response.status_code}"
        assert detail_time < 10, f"Detail took too long: {detail_time}s"
        
        # Test status endpoint
        start_time = time.time()
        status_response = auth_session.get(f"{BASE_URL}/api/bot-profiles/{created_bot_id}/status", timeout=30)
        status_time = time.time() - start_time
        assert status_response.status_code == 200, f"Status failed: {status_response.status_code}"
        assert status_time < 10, f"Status took too long: {status_time}s"
        
        print(f"✓ No timeout: list={list_time:.2f}s, detail={detail_time:.2f}s, status={status_time:.2f}s")


class TestScannerSymbolSourceBehavior:
    """Test scanner symbol source behavior - empty scanner causes ERROR on start"""

    @pytest.fixture(scope="class")
    def auth_session(self):
        """Get authenticated session with cookies"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=30
        )
        
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.status_code}")
        
        login_data = login_response.json()
        token = login_data.get("access_token") or login_data.get("token")
        
        if token:
            session.headers.update({"Authorization": f"Bearer {token}"})
        
        return session

    def test_scanner_symbol_source_empty_causes_error_on_start(self, auth_session):
        """Scanner symbol source with empty results causes start -> ERROR"""
        unique_name = f"TEST_ScannerBot_{uuid.uuid4().hex[:8]}"
        payload = {
            "name": unique_name,
            "exchange": "binance",
            "market_type": "spot",
            "symbol_source_type": "scanner",
            "scanner_id": f"empty-scanner-{uuid.uuid4().hex[:8]}",
            "symbols": [],
            "strategy_type": "trend_following",
            "strategy_template_id": None,
            "timeframe": "15m",
            "trend_timeframe": "1h",
            "leverage": 1,
            "is_enabled": True
        }
        
        # Create bot with scanner source
        create_response = auth_session.post(f"{BASE_URL}/api/bot-profiles", json=payload, timeout=30)
        
        if create_response.status_code not in [200, 201]:
            pytest.skip(f"Bot creation failed: {create_response.status_code}")
        
        bot_data = create_response.json()
        bot_id = bot_data.get("id")
        
        try:
            # Try to start the bot - should fail with ERROR due to empty scanner
            start_response = auth_session.post(f"{BASE_URL}/api/bot-profiles/{bot_id}/start", timeout=30)
            
            assert start_response.status_code == 200, f"Expected 200, got {start_response.status_code}"
            
            start_data = start_response.json()
            
            # Should be ERROR because scanner has no symbols
            assert start_data["status"] == "ERROR", f"Expected ERROR status for empty scanner, got {start_data['status']}"
            assert start_data.get("binding_ok") is False, "binding_ok should be False for empty scanner"
            
            print(f"✓ Scanner with empty results correctly returns ERROR on start")
            
        finally:
            # Cleanup
            try:
                auth_session.delete(f"{BASE_URL}/api/bot-profiles/{bot_id}", timeout=30)
            except Exception:
                pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
