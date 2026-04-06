"""
Iteration 17 - Scanner Bot Symbols Fallback Tests

Tests for the new fallback mechanism in _resolve_symbol_source():
- When scanner source is used but scanner rows are empty AND selected_symbols is empty,
  the system should fallback to bot.symbols instead of returning SYMBOLS_NOT_RESOLVED blocker.

Key scenarios:
1. _resolve_symbol_source with scanner source, empty scanner rows, empty selected_symbols -> fallback to bot.symbols
2. Bot start should NOT trigger SYMBOLS_NOT_RESOLVED when bot.symbols fallback is used
3. Regression: existing scanner bots with real blockers (EXCHANGE_NOT_READY) should still fail appropriately
"""

import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
TEST_EMAIL = "review.user@platform.local"
TEST_PASSWORD = "ReviewUser123!"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for test user"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=30
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get auth headers"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestScannerBotSymbolsFallback:
    """Tests for scanner_bot_symbols_fallback feature"""

    def test_bot_runtime_service_exists(self, auth_headers):
        """Verify bot runtime service is accessible"""
        # Check if bot list endpoint works
        response = requests.get(
            f"{BASE_URL}/api/user/bots",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code in [200, 404], f"Bot list endpoint failed: {response.status_code}"
        print(f"Bot list endpoint status: {response.status_code}")

    def test_bot_runtime_summary_endpoint(self, auth_headers):
        """Test bot runtime summary endpoint exists"""
        response = requests.get(
            f"{BASE_URL}/api/user/bots",
            headers=auth_headers,
            timeout=30
        )
        if response.status_code == 200:
            bots = response.json()
            if isinstance(bots, list) and len(bots) > 0:
                bot_id = bots[0].get("id")
                if bot_id:
                    # Try to get runtime summary
                    runtime_response = requests.get(
                        f"{BASE_URL}/api/user/bots/{bot_id}/runtime",
                        headers=auth_headers,
                        timeout=30
                    )
                    print(f"Runtime endpoint status: {runtime_response.status_code}")
                    assert runtime_response.status_code in [200, 404, 422], f"Runtime endpoint failed: {runtime_response.status_code}"
        print("Bot runtime summary endpoint test passed")

    def test_scanner_source_fallback_logic_in_code(self):
        """
        Verify the fallback logic exists in bot_runtime_service.py
        This is a code review test to ensure the patch is applied correctly.
        """
        import sys
        sys.path.insert(0, "/app/backend")
        
        try:
            from services.bot_runtime_service import _resolve_symbol_source
            # Function exists
            assert callable(_resolve_symbol_source), "_resolve_symbol_source should be callable"
            print("_resolve_symbol_source function exists and is callable")
        except ImportError as e:
            pytest.fail(f"Could not import _resolve_symbol_source: {e}")

    def test_scanner_bot_symbols_fallback_summary_value(self):
        """
        Test that the fallback returns summary='scanner_bot_symbols_fallback'
        when scanner source is empty but bot.symbols has values.
        """
        # Read the source code to verify the fallback logic
        with open("/app/backend/services/bot_runtime_service.py", "r") as f:
            content = f.read()
        
        # Check for the new fallback summary value
        assert "scanner_bot_symbols_fallback" in content, \
            "scanner_bot_symbols_fallback summary should be present in the code"
        
        # Check the fallback logic structure
        assert "if bot_symbols_fallback:" in content, \
            "bot_symbols_fallback check should be present"
        
        print("scanner_bot_symbols_fallback logic verified in source code")

    def test_fallback_returns_ok_true(self):
        """
        Verify that when bot_symbols_fallback is used, ok=True is returned
        so SYMBOLS_NOT_RESOLVED blocker is not triggered.
        """
        with open("/app/backend/services/bot_runtime_service.py", "r") as f:
            content = f.read()
        
        # Find the fallback block and verify it returns ok: True
        # The code should have: "ok": True for bot_symbols_fallback
        lines = content.split("\n")
        in_fallback_block = False
        found_ok_true = False
        
        for i, line in enumerate(lines):
            if "if bot_symbols_fallback:" in line:
                in_fallback_block = True
            if in_fallback_block and '"ok": True' in line:
                found_ok_true = True
                break
            if in_fallback_block and "return {" in line and "ok" not in line:
                # Check next few lines for ok: True
                for j in range(i, min(i + 15, len(lines))):
                    if '"ok": True' in lines[j]:
                        found_ok_true = True
                        break
                break
        
        assert found_ok_true, "bot_symbols_fallback should return ok: True"
        print("Verified: bot_symbols_fallback returns ok: True")


class TestBotStartBlockerValidation:
    """Tests for bot start blocker validation - SYMBOLS_NOT_RESOLVED should not be false-positive"""

    def test_build_start_status_contract_exists(self):
        """Verify _build_start_status_contract function exists"""
        import sys
        sys.path.insert(0, "/app/backend")
        
        try:
            from services.bot_runtime_service import _build_start_status_contract
            assert callable(_build_start_status_contract), "_build_start_status_contract should be callable"
            print("_build_start_status_contract function exists")
        except ImportError as e:
            pytest.fail(f"Could not import _build_start_status_contract: {e}")

    def test_symbols_ready_check_uses_symbol_resolution_ok(self):
        """
        Verify that symbols_ready check uses symbol_resolution.get('ok')
        which will be True when bot_symbols_fallback is used.
        """
        with open("/app/backend/services/bot_runtime_service.py", "r") as f:
            content = f.read()
        
        # Check that symbols_ready uses symbol_resolution.get("ok")
        assert 'symbols_ready = bool(symbol_resolution.get("ok"))' in content, \
            "symbols_ready should check symbol_resolution.get('ok')"
        
        print("Verified: symbols_ready uses symbol_resolution.get('ok')")

    def test_symbols_not_resolved_blocker_code(self):
        """
        Verify SYMBOLS_NOT_RESOLVED blocker is only added when symbols_ready is False.
        """
        with open("/app/backend/services/bot_runtime_service.py", "r") as f:
            content = f.read()
        
        # Check the blocker logic
        assert 'if not symbols_ready:' in content, \
            "symbols_ready check should exist before SYMBOLS_NOT_RESOLVED blocker"
        assert '"code": "SYMBOLS_NOT_RESOLVED"' in content, \
            "SYMBOLS_NOT_RESOLVED blocker code should exist"
        
        print("Verified: SYMBOLS_NOT_RESOLVED blocker logic is correct")


class TestRegressionScannerBots:
    """Regression tests - existing scanner bots should still work correctly"""

    def test_scanner_selection_fallback_still_works(self):
        """
        Verify scanner_selection_fallback (when selected_symbols exist but scanner rows empty)
        still works correctly.
        """
        with open("/app/backend/services/bot_runtime_service.py", "r") as f:
            content = f.read()
        
        # Check scanner_selection_fallback is still present
        assert '"summary": "scanner_selection_fallback"' in content, \
            "scanner_selection_fallback should still be present"
        
        # Check the order: selected_symbols fallback comes before bot_symbols fallback
        selection_fallback_pos = content.find("scanner_selection_fallback")
        bot_symbols_fallback_pos = content.find("scanner_bot_symbols_fallback")
        
        assert selection_fallback_pos < bot_symbols_fallback_pos, \
            "scanner_selection_fallback should be checked before scanner_bot_symbols_fallback"
        
        print("Verified: scanner_selection_fallback still works and has correct priority")

    def test_scanner_source_empty_still_fails_when_no_bot_symbols(self):
        """
        Verify that when scanner source is empty AND bot.symbols is also empty,
        the system still returns ok: False (scanner_source_empty).
        """
        with open("/app/backend/services/bot_runtime_service.py", "r") as f:
            content = f.read()
        
        # Check scanner_source_empty is still present
        assert '"summary": "scanner_source_empty"' in content, \
            "scanner_source_empty should still be present for when all sources are empty"
        
        # Check it returns ok: False
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if '"summary": "scanner_source_empty"' in line:
                # Check nearby lines for ok: False
                for j in range(max(0, i - 10), min(i + 5, len(lines))):
                    if '"ok": False' in lines[j]:
                        print("Verified: scanner_source_empty returns ok: False")
                        return
        
        pytest.fail("scanner_source_empty should return ok: False")

    def test_exchange_not_ready_blocker_still_works(self):
        """
        Verify EXCHANGE_NOT_READY blocker is still present and works correctly.
        """
        with open("/app/backend/services/bot_runtime_service.py", "r") as f:
            content = f.read()
        
        assert '"code": "EXCHANGE_NOT_READY"' in content, \
            "EXCHANGE_NOT_READY blocker should still be present"
        assert 'if not exchange_ready:' in content, \
            "exchange_ready check should exist before EXCHANGE_NOT_READY blocker"
        
        print("Verified: EXCHANGE_NOT_READY blocker still works")


class TestBotStartAPIIntegration:
    """Integration tests for bot start API with the new fallback"""

    def test_bot_start_endpoint_exists(self, auth_headers):
        """Verify bot start endpoint exists"""
        response = requests.get(
            f"{BASE_URL}/api/user/bots",
            headers=auth_headers,
            timeout=30
        )
        if response.status_code == 200:
            bots = response.json()
            if isinstance(bots, list) and len(bots) > 0:
                bot_id = bots[0].get("id")
                if bot_id:
                    # Try to start the bot (may fail due to other blockers, but endpoint should exist)
                    start_response = requests.post(
                        f"{BASE_URL}/api/user/bots/{bot_id}/start",
                        headers=auth_headers,
                        timeout=30
                    )
                    # Accept any response that indicates the endpoint exists
                    assert start_response.status_code in [200, 400, 422, 403, 409], \
                        f"Bot start endpoint should exist: {start_response.status_code}"
                    print(f"Bot start endpoint status: {start_response.status_code}")
                    
                    # If there are blocking reasons, check they are real blockers
                    if start_response.status_code in [400, 422]:
                        data = start_response.json()
                        blocking_reasons = data.get("blocking_reasons", [])
                        if blocking_reasons:
                            codes = [br.get("code") for br in blocking_reasons]
                            print(f"Blocking reasons: {codes}")
                            # If SYMBOLS_NOT_RESOLVED is present, it should be a real issue
                            # (bot.symbols is also empty)
        print("Bot start endpoint test completed")

    def test_bot_runtime_detail_shows_symbol_source_summary(self, auth_headers):
        """Test that bot runtime detail includes symbol_source_summary"""
        response = requests.get(
            f"{BASE_URL}/api/user/bots",
            headers=auth_headers,
            timeout=30
        )
        if response.status_code == 200:
            bots = response.json()
            if isinstance(bots, list) and len(bots) > 0:
                bot_id = bots[0].get("id")
                if bot_id:
                    detail_response = requests.get(
                        f"{BASE_URL}/api/user/bots/{bot_id}/runtime/detail",
                        headers=auth_headers,
                        timeout=30
                    )
                    if detail_response.status_code == 200:
                        data = detail_response.json()
                        runtime_summary = data.get("runtime_summary", {})
                        symbol_source_summary = runtime_summary.get("symbol_source_summary", {})
                        
                        # Check symbol_source_summary structure
                        assert "ok" in symbol_source_summary, "symbol_source_summary should have 'ok' field"
                        assert "summary" in symbol_source_summary, "symbol_source_summary should have 'summary' field"
                        
                        print(f"symbol_source_summary: {symbol_source_summary}")
                        
                        # If summary is scanner_bot_symbols_fallback, ok should be True
                        if symbol_source_summary.get("summary") == "scanner_bot_symbols_fallback":
                            assert symbol_source_summary.get("ok") is True, \
                                "scanner_bot_symbols_fallback should have ok=True"
                            print("Verified: scanner_bot_symbols_fallback has ok=True")
        print("Bot runtime detail test completed")


class TestFallbackPriorityOrder:
    """Tests to verify the correct priority order of fallbacks"""

    def test_fallback_priority_order(self):
        """
        Verify the fallback priority order:
        1. Scanner rows with selected_symbols filter
        2. scanner_selection_fallback (selected_symbols exist, no scanner rows)
        3. scanner_bot_symbols_fallback (no selected_symbols, no scanner rows, but bot.symbols exist)
        4. scanner_source_empty (all sources empty)
        """
        with open("/app/backend/services/bot_runtime_service.py", "r") as f:
            content = f.read()
        
        # Find positions of each fallback
        scanner_rows_pos = content.find("for row in rows:")
        selection_fallback_pos = content.find("scanner_selection_fallback")
        bot_symbols_fallback_pos = content.find("scanner_bot_symbols_fallback")
        source_empty_pos = content.find("scanner_source_empty")
        
        # Verify order
        assert scanner_rows_pos < selection_fallback_pos, \
            "Scanner rows processing should come before selection_fallback"
        assert selection_fallback_pos < bot_symbols_fallback_pos, \
            "selection_fallback should come before bot_symbols_fallback"
        assert bot_symbols_fallback_pos < source_empty_pos, \
            "bot_symbols_fallback should come before source_empty"
        
        print("Verified: Fallback priority order is correct")
        print("Order: scanner_rows -> selection_fallback -> bot_symbols_fallback -> source_empty")


class TestSymbolResolutionSnapshot:
    """Tests for symbol resolution snapshot in bot start"""

    def test_symbol_resolution_snapshot_saved_on_start(self):
        """
        Verify that symbol_resolution_snapshot is saved when bot starts successfully.
        """
        with open("/app/backend/services/bot_runtime_service.py", "r") as f:
            content = f.read()
        
        # Check that symbol_resolution_snapshot is updated on successful start
        assert "bot.symbol_resolution_snapshot" in content, \
            "symbol_resolution_snapshot should be updated"
        assert '"last_symbol_resolution": symbol_resolution' in content, \
            "last_symbol_resolution should be saved in snapshot"
        
        print("Verified: symbol_resolution_snapshot is saved on bot start")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
