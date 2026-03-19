# ruff: noqa: E402
"""
Gate-2 Scanner Policy Hardening Verification Tests

Features tested:
- Scanner run manual selection: ETHBTC/BNBBUSD gibi policy dışı semboller 400 ile bloklanmalı
- Scanner run valid sembollerle çalışmalı (ETHUSDT/SOLUSDT vb.)
- GET /api/user/scanner/results contract: quote_asset alanı dönmeli ve USDT/USDC olmalı
- Watchlist create/update sonrası policy dışı pairler backendde filtrelenmeli
- User_scanner_signals run guard mesajı policy metniyle dönmeli
- Execution preview invalid quote asset reject (invalid_quote_asset)
"""

import os
import sys
import uuid
from pathlib import Path

import pytest
import requests

# Add backend to path for direct module imports
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.quote_asset_policy import (
    ALLOWED_QUOTE_ASSETS,
    extract_quote_asset,
    is_allowed_quote_symbol,
    filter_allowed_quote_symbols,
)


def _resolve_base_url() -> str:
    """Resolve the backend URL from environment or frontend .env file."""
    env_base = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if env_base:
        return env_base
    frontend_env = Path("/app/frontend/.env")
    if frontend_env.exists():
        for line in frontend_env.read_text(encoding="utf-8").splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE_URL = _resolve_base_url()
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@platform.local")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin12345!")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _admin_headers() -> dict:
    """Get admin auth headers."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    token = response.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


def _create_test_user() -> dict:
    """Create a new test user and return auth headers."""
    email = f"gate2_test_{uuid.uuid4().hex[:8]}@example.com"
    password = "Gate2Test123!"
    
    # Register
    register = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert register.status_code == 200, f"Register failed: {register.text}"
    user_id = register.json().get("id")
    
    # Approve
    admin_headers = _admin_headers()
    approve = requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers=admin_headers,
        timeout=20,
    )
    assert approve.status_code == 200, f"Approve failed: {approve.text}"
    
    # Login
    login = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert login.status_code == 200, f"Login failed: {login.text}"
    token = login.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def user_headers():
    """Module-scoped user auth headers fixture."""
    return _create_test_user()


@pytest.fixture(scope="module")
def admin_headers():
    """Module-scoped admin auth headers fixture."""
    return _admin_headers()


# ============================================================================
# TEST CLASS: Scanner Run Manual Selection Policy Blocking
# ============================================================================

class TestScannerRunManualSelectionPolicyBlocking:
    """
    Test: scanner run manual selection: ETHBTC/BNBBUSD gibi policy dışı semboller 400 ile bloklanmalı
    """
    
    def test_scanner_run_ethbtc_blocked(self, user_headers):
        """ETHBTC (BTC quote) should be blocked with 400."""
        payload = {
            "mode": "ASSISTED",
            "max_results": 20,
            "symbol_source": "crypto",
            "symbol_selection_mode": "manual_selection",
            "selected_symbols": ["ETHBTC"],
        }
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=user_headers,
            json=payload,
            timeout=30,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        # Should mention USDT/USDC policy
        assert "USDT" in response.text or "USDC" in response.text

    def test_scanner_run_bnbbusd_blocked(self, user_headers):
        """BNBBUSD (BUSD quote) should be blocked with 400."""
        payload = {
            "mode": "ASSISTED",
            "max_results": 20,
            "symbol_source": "crypto",
            "symbol_selection_mode": "manual_selection",
            "selected_symbols": ["BNBBUSD"],
        }
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=user_headers,
            json=payload,
            timeout=30,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        assert "USDT" in response.text or "USDC" in response.text

    def test_scanner_run_mixed_invalid_symbols_blocked(self, user_headers):
        """Mix of ETHBTC and BNBBUSD (both invalid) should be blocked."""
        payload = {
            "mode": "ASSISTED",
            "max_results": 20,
            "symbol_source": "crypto",
            "symbol_selection_mode": "manual_selection",
            "selected_symbols": ["ETHBTC", "BNBBUSD"],
        }
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=user_headers,
            json=payload,
            timeout=30,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        assert "USDT" in response.text or "USDC" in response.text

    def test_scanner_run_btcbnb_blocked(self, user_headers):
        """BTCBNB (BNB quote) should be blocked."""
        payload = {
            "mode": "ASSISTED",
            "max_results": 20,
            "symbol_source": "crypto",
            "symbol_selection_mode": "manual_selection",
            "selected_symbols": ["BTCBNB"],
        }
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=user_headers,
            json=payload,
            timeout=30,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"


# ============================================================================
# TEST CLASS: Scanner Run Valid Symbols
# ============================================================================

class TestScannerRunValidSymbols:
    """
    Test: Scanner run valid sembollerle çalışmalı (ETHUSDT/SOLUSDT vb.)
    """
    
    def test_scanner_run_ethusdt_works(self, user_headers):
        """ETHUSDT (valid USDT pair) should work."""
        payload = {
            "mode": "ASSISTED",
            "max_results": 20,
            "symbol_source": "crypto",
            "symbol_selection_mode": "manual_selection",
            "selected_symbols": ["ETHUSDT"],
        }
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=user_headers,
            json=payload,
            timeout=60,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "run_id" in data
        assert "mode" in data
        # Check that the response structure is valid - scanner may select different symbols internally
        selected = data.get("selected_symbols", [])
        # All selected symbols should be USDT/USDC pairs
        for sym in selected:
            assert sym.endswith("USDT") or sym.endswith("USDC"), f"Invalid symbol in selection: {sym}"

    def test_scanner_run_solusdt_works(self, user_headers):
        """SOLUSDT (valid USDT pair) should work."""
        payload = {
            "mode": "ASSISTED",
            "max_results": 20,
            "symbol_source": "crypto",
            "symbol_selection_mode": "manual_selection",
            "selected_symbols": ["SOLUSDT"],
        }
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=user_headers,
            json=payload,
            timeout=60,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_scanner_run_multiple_valid_usdt_symbols(self, user_headers):
        """Multiple valid USDT symbols should work."""
        payload = {
            "mode": "ASSISTED",
            "max_results": 20,
            "symbol_source": "crypto",
            "symbol_selection_mode": "manual_selection",
            "selected_symbols": ["ETHUSDT", "SOLUSDT", "XRPUSDT"],
        }
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=user_headers,
            json=payload,
            timeout=60,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_scanner_run_usdc_symbols_work(self, user_headers):
        """USDC symbols should work."""
        payload = {
            "mode": "ASSISTED",
            "max_results": 20,
            "symbol_source": "crypto",
            "symbol_selection_mode": "manual_selection",
            "selected_symbols": ["ETHUSDC", "BTCUSDC"],
        }
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=user_headers,
            json=payload,
            timeout=60,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


# ============================================================================
# TEST CLASS: Scanner Results Contract - quote_asset Field
# ============================================================================

class TestScannerResultsContractQuoteAsset:
    """
    Test: GET /api/user/scanner/results contract: quote_asset alanı dönmeli ve USDT/USDC olmalı
    """
    
    def test_scanner_results_has_quote_asset_field(self, user_headers):
        """Scanner results should have quote_asset field."""
        # First run a scan to generate results
        run_payload = {
            "mode": "ASSISTED",
            "max_results": 20,
            "symbol_source": "crypto",
            "symbol_selection_mode": "manual_selection",
            "selected_symbols": ["ETHUSDT", "SOLUSDT", "BTCUSDT"],
        }
        run_response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=user_headers,
            json=run_payload,
            timeout=60,
        )
        assert run_response.status_code == 200, f"Scanner run failed: {run_response.text}"
        
        # Get scanner results
        results_response = requests.get(
            f"{BASE_URL}/api/user/scanner/results",
            headers=user_headers,
            params={"limit": 30},
            timeout=30,
        )
        assert results_response.status_code == 200, f"Results fetch failed: {results_response.text}"
        
        rows = results_response.json()
        if rows:
            for row in rows:
                # Verify quote_asset field exists
                assert "quote_asset" in row, f"Missing quote_asset field in row: {row}"
                # Verify quote_asset is USDT or USDC
                quote_asset = row["quote_asset"]
                assert quote_asset in ["USDT", "USDC", "UNKNOWN"], f"Invalid quote_asset: {quote_asset}"

    def test_scanner_results_quote_asset_matches_symbol(self, user_headers):
        """Scanner results quote_asset should match the symbol suffix."""
        # Get scanner results
        results_response = requests.get(
            f"{BASE_URL}/api/user/scanner/results",
            headers=user_headers,
            params={"limit": 50},
            timeout=30,
        )
        assert results_response.status_code == 200, f"Results fetch failed: {results_response.text}"
        
        rows = results_response.json()
        for row in rows:
            symbol = row.get("symbol", "")
            quote_asset = row.get("quote_asset", "UNKNOWN")
            
            # If symbol ends with USDT, quote_asset should be USDT
            if symbol.endswith("USDT"):
                assert quote_asset == "USDT", f"Mismatch: {symbol} has quote_asset={quote_asset}"
            elif symbol.endswith("USDC"):
                assert quote_asset == "USDC", f"Mismatch: {symbol} has quote_asset={quote_asset}"


# ============================================================================
# TEST CLASS: Watchlist Create/Update Policy Filtering
# ============================================================================

class TestWatchlistPolicyFiltering:
    """
    Test: Watchlist create/update sonrası policy dışı pairler backendde filtrelenmeli
    """
    
    def test_watchlist_create_filters_invalid_pairs(self, user_headers):
        """Watchlist create should filter out policy-invalid pairs."""
        watchlist_name = f"test_watchlist_{uuid.uuid4().hex[:6]}"
        payload = {
            "name": watchlist_name,
            "source": "crypto",
            "exchange": "binance",
            "market_type": "spot",
            "symbols": ["ETHUSDT", "ETHBTC", "SOLUSDC", "BNBBUSD", "BTCUSDT"],
        }
        response = requests.post(
            f"{BASE_URL}/api/symbol-selector/watchlists",
            headers=user_headers,
            json=payload,
            timeout=20,
        )
        assert response.status_code in [200, 201], f"Create failed: {response.text}"
        
        data = response.json()
        symbols = data.get("symbols", [])
        
        # Valid symbols should be present
        assert "ETHUSDT" in symbols, "ETHUSDT should be in watchlist"
        assert "SOLUSDC" in symbols, "SOLUSDC should be in watchlist"
        assert "BTCUSDT" in symbols, "BTCUSDT should be in watchlist"
        
        # Invalid symbols should be filtered out
        assert "ETHBTC" not in symbols, "ETHBTC should be filtered from watchlist"
        assert "BNBBUSD" not in symbols, "BNBBUSD should be filtered from watchlist"

    def test_watchlist_update_filters_invalid_pairs(self, user_headers):
        """Watchlist update should filter out policy-invalid pairs."""
        # First create a watchlist
        watchlist_name = f"update_test_{uuid.uuid4().hex[:6]}"
        create_payload = {
            "name": watchlist_name,
            "source": "crypto",
            "exchange": "binance",
            "market_type": "spot",
            "symbols": ["ETHUSDT"],
        }
        create_response = requests.post(
            f"{BASE_URL}/api/symbol-selector/watchlists",
            headers=user_headers,
            json=create_payload,
            timeout=20,
        )
        assert create_response.status_code in [200, 201], f"Create failed: {create_response.text}"
        watchlist_id = create_response.json().get("id")
        
        # Update with mix of valid and invalid symbols
        update_payload = {
            "name": watchlist_name,
            "symbols": ["XRPUSDT", "LINKBTC", "DOTUSDC", "ADABUSD"],
        }
        update_response = requests.put(
            f"{BASE_URL}/api/symbol-selector/watchlists/{watchlist_id}",
            headers=user_headers,
            json=update_payload,
            timeout=20,
        )
        assert update_response.status_code == 200, f"Update failed: {update_response.text}"
        
        data = update_response.json()
        symbols = data.get("symbols", [])
        
        # Valid symbols should be present
        assert "XRPUSDT" in symbols, "XRPUSDT should be in updated watchlist"
        assert "DOTUSDC" in symbols, "DOTUSDC should be in updated watchlist"
        
        # Invalid symbols should be filtered
        assert "LINKBTC" not in symbols, "LINKBTC should be filtered"
        assert "ADABUSD" not in symbols, "ADABUSD should be filtered"


# ============================================================================
# TEST CLASS: User Scanner Signals Run Guard Message
# ============================================================================

class TestUserScannerSignalsRunGuardMessage:
    """
    Test: user_scanner_signals run guard mesajı policy metniyle dönmeli
    """
    
    def test_scanner_run_guard_returns_policy_message(self, user_headers):
        """Scanner run with invalid symbols should return policy-related message."""
        payload = {
            "mode": "ASSISTED",
            "max_results": 20,
            "symbol_source": "crypto",
            "symbol_selection_mode": "manual_selection",
            "selected_symbols": ["ETHBTC", "BNBBUSD"],
        }
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=user_headers,
            json=payload,
            timeout=30,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        
        # Verify the error message contains policy text
        error_text = response.text.lower()
        assert "usdt" in error_text or "usdc" in error_text, \
            f"Error message should mention USDT/USDC policy: {response.text}"

    def test_scanner_run_empty_symbols_guard_message(self, user_headers):
        """Scanner run with empty symbols should return appropriate message."""
        payload = {
            "mode": "ASSISTED",
            "max_results": 20,
            "symbol_source": "crypto",
            "symbol_selection_mode": "manual_selection",
            "selected_symbols": [],
        }
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=user_headers,
            json=payload,
            timeout=30,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"


# ============================================================================
# TEST CLASS: Execution Preview Invalid Quote Asset Rejection
# ============================================================================

class TestExecutionPreviewInvalidQuoteAssetRejection:
    """
    Test: Execution preview invalid quote asset reject (invalid_quote_asset)
    """
    
    def test_execution_preview_ethbtc_rejected(self, user_headers):
        """Execution preview with ETHBTC should be rejected with invalid_quote_asset."""
        payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "ETHBTC",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 20,
            "execution_mode": "manual",
        }
        response = requests.post(
            f"{BASE_URL}/api/v1/user/trading/preview",
            headers=user_headers,
            json=payload,
            timeout=30,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        assert "invalid_quote_asset" in response.text.lower(), \
            f"Expected invalid_quote_asset in response: {response.text}"

    def test_execution_preview_bnbbusd_rejected(self, user_headers):
        """Execution preview with BNBBUSD should be rejected with invalid_quote_asset."""
        payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "BNBBUSD",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 20,
            "execution_mode": "manual",
        }
        response = requests.post(
            f"{BASE_URL}/api/v1/user/trading/preview",
            headers=user_headers,
            json=payload,
            timeout=30,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        assert "invalid_quote_asset" in response.text.lower()

    def test_execution_preview_btcbnb_rejected(self, user_headers):
        """Execution preview with BTCBNB should be rejected."""
        payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "BTCBNB",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 20,
            "execution_mode": "manual",
        }
        response = requests.post(
            f"{BASE_URL}/api/v1/user/trading/preview",
            headers=user_headers,
            json=payload,
            timeout=30,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        assert "invalid_quote_asset" in response.text.lower()

    def test_execution_preview_valid_usdt_symbol_accepted(self, user_headers):
        """Execution preview with valid USDT symbol should be accepted."""
        payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "ETHUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 20,
            "execution_mode": "manual",
        }
        response = requests.post(
            f"{BASE_URL}/api/v1/user/trading/preview",
            headers=user_headers,
            json=payload,
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "preview" in data

    def test_execution_preview_valid_usdc_symbol_accepted(self, user_headers):
        """Execution preview with valid USDC symbol should be accepted."""
        payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "SOLUSDC",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 15,
            "execution_mode": "manual",
        }
        response = requests.post(
            f"{BASE_URL}/api/v1/user/trading/preview",
            headers=user_headers,
            json=payload,
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


# ============================================================================
# TEST CLASS: Scanner Signal Snapshot Validation
# ============================================================================

class TestScannerSignalSnapshotValidation:
    """
    Additional tests for scanner signal snapshot validation during execution.
    """
    
    def test_scanner_execution_snapshot_symbol_mismatch_rejected(self, user_headers):
        """Scanner execution with mismatched symbol in snapshot should be rejected."""
        payload = {
            "source_type": "scanner",
            "market_type": "spot",
            "symbol": "ETHUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 20,
            "execution_mode": "signal_follow",
            "scanner_signal_snapshot": {
                "symbol": "BTCUSDT",  # Mismatch!
                "signal": "long",
                "confidence": 0.75,
            },
        }
        response = requests.post(
            f"{BASE_URL}/api/v1/user/trading/preview",
            headers=user_headers,
            json=payload,
            timeout=30,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        assert "mismatch" in response.text.lower()

    def test_scanner_execution_snapshot_with_invalid_quote_rejected(self, user_headers):
        """Scanner execution with invalid quote in both symbol and snapshot should be rejected."""
        payload = {
            "source_type": "scanner",
            "market_type": "spot",
            "symbol": "ETHBTC",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 20,
            "execution_mode": "signal_follow",
            "scanner_signal_snapshot": {
                "symbol": "ETHBTC",
                "signal": "long",
                "confidence": 0.75,
            },
        }
        response = requests.post(
            f"{BASE_URL}/api/v1/user/trading/preview",
            headers=user_headers,
            json=payload,
            timeout=30,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        assert "invalid_quote_asset" in response.text.lower()


# ============================================================================
# TEST CLASS: Unit Tests for Quote Asset Policy Module
# ============================================================================

class TestQuoteAssetPolicyUnit:
    """Unit tests to verify the quote asset policy module functions."""
    
    def test_allowed_quote_assets_are_only_usdt_usdc(self):
        """Verify ALLOWED_QUOTE_ASSETS only contains USDT and USDC."""
        assert ALLOWED_QUOTE_ASSETS == {"USDT", "USDC"}
        assert "BTC" not in ALLOWED_QUOTE_ASSETS
        assert "BUSD" not in ALLOWED_QUOTE_ASSETS
        assert "BNB" not in ALLOWED_QUOTE_ASSETS
    
    def test_extract_quote_asset_usdt(self):
        """Test extract_quote_asset for USDT pairs."""
        assert extract_quote_asset("ETHUSDT") == "USDT"
        assert extract_quote_asset("BTCUSDT") == "USDT"
        assert extract_quote_asset("XRPUSDT") == "USDT"
    
    def test_extract_quote_asset_usdc(self):
        """Test extract_quote_asset for USDC pairs."""
        assert extract_quote_asset("ETHUSDC") == "USDC"
        assert extract_quote_asset("SOLUSDC") == "USDC"
    
    def test_extract_quote_asset_invalid(self):
        """Test extract_quote_asset returns None for invalid pairs."""
        assert extract_quote_asset("ETHBTC") is None
        assert extract_quote_asset("BNBBUSD") is None
        assert extract_quote_asset("BTCBNB") is None
    
    def test_is_allowed_quote_symbol(self):
        """Test is_allowed_quote_symbol function."""
        assert is_allowed_quote_symbol("ETHUSDT") is True
        assert is_allowed_quote_symbol("SOLUSDC") is True
        assert is_allowed_quote_symbol("ETHBTC") is False
        assert is_allowed_quote_symbol("BNBBUSD") is False
    
    def test_filter_allowed_quote_symbols(self):
        """Test filter_allowed_quote_symbols function."""
        input_list = ["ETHUSDT", "ETHBTC", "SOLUSDC", "BNBBUSD", "BTCUSDT"]
        result = filter_allowed_quote_symbols(input_list)
        assert "ETHUSDT" in result
        assert "SOLUSDC" in result
        assert "BTCUSDT" in result
        assert "ETHBTC" not in result
        assert "BNBBUSD" not in result
