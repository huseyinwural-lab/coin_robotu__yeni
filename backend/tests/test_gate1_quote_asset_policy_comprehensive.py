"""
Gate-1 BTC Hard Dependency Removal + USDT/USDC Quote Policy Hardening
Comprehensive test module for quote asset policy enforcement across all layers.

Features tested:
- Global policy: only USDT/USDC quote pair acceptance
- No fallback to BTCUSDT: missing symbol rejection
- Invalid quote asset (ETHBTC, BTCBUSD, etc.) rejection
- Scanner run guard: selected symbols out of policy returns 400
- Execution preview path: symbol missing/mismatch/invalid quote tests
- Universe endpoints and symbol selector crypto filters policy compliance
- Market ticker endpoint: symbol required + invalid quote rejection
"""

import os
import sys
import uuid
from pathlib import Path

import pytest
import requests

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Quote asset policy module tests
from services.quote_asset_policy import (
    ALLOWED_QUOTE_ASSETS,
    extract_quote_asset,
    is_allowed_quote_symbol,
    normalize_quote_symbol,
    filter_allowed_quote_symbols,
    allowed_quote_assets_list,
)


def _resolve_base_url() -> str:
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
    email = f"gate1_test_{uuid.uuid4().hex[:8]}@example.com"
    password = "Gate1Test123!"
    
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
# UNIT TESTS - Quote Asset Policy Module
# ============================================================================

class TestQuoteAssetPolicyUnit:
    """Unit tests for quote_asset_policy.py functions."""
    
    def test_allowed_quote_assets_constant(self):
        """Verify only USDT and USDC are allowed."""
        assert ALLOWED_QUOTE_ASSETS == {"USDT", "USDC"}
        assert "BTC" not in ALLOWED_QUOTE_ASSETS
        assert "BUSD" not in ALLOWED_QUOTE_ASSETS
    
    def test_allowed_quote_assets_list(self):
        """Verify allowed_quote_assets_list returns sorted list."""
        result = allowed_quote_assets_list()
        assert result == ["USDC", "USDT"]
    
    def test_extract_quote_asset_usdt(self):
        """Extract quote asset from USDT pairs."""
        assert extract_quote_asset("ETHUSDT") == "USDT"
        assert extract_quote_asset("BTCUSDT") == "USDT"
        assert extract_quote_asset("SOLUSDT") == "USDT"
    
    def test_extract_quote_asset_usdc(self):
        """Extract quote asset from USDC pairs."""
        assert extract_quote_asset("ETHUSDC") == "USDC"
        assert extract_quote_asset("BTCUSDC") == "USDC"
        assert extract_quote_asset("SOLUSDC") == "USDC"
    
    def test_extract_quote_asset_invalid(self):
        """Invalid quote assets should return None."""
        assert extract_quote_asset("ETHBTC") is None
        assert extract_quote_asset("BTCBUSD") is None
        assert extract_quote_asset("SOLETH") is None
        assert extract_quote_asset("INVALID") is None
        assert extract_quote_asset("") is None
        assert extract_quote_asset(None) is None
    
    def test_is_allowed_quote_symbol_valid(self):
        """Valid USDT/USDC pairs should be allowed."""
        assert is_allowed_quote_symbol("ETHUSDT") is True
        assert is_allowed_quote_symbol("BTCUSDT") is True
        assert is_allowed_quote_symbol("SOLUSDC") is True
        assert is_allowed_quote_symbol("BTCUSDC") is True
        # Case insensitive
        assert is_allowed_quote_symbol("ethusdt") is True
        assert is_allowed_quote_symbol("ETHUSDT   ") is True
    
    def test_is_allowed_quote_symbol_invalid(self):
        """Invalid quote assets should be rejected."""
        assert is_allowed_quote_symbol("ETHBTC") is False
        assert is_allowed_quote_symbol("BTCBUSD") is False
        assert is_allowed_quote_symbol("SOLETH") is False
        assert is_allowed_quote_symbol("XRPBNB") is False
        assert is_allowed_quote_symbol("") is False
        assert is_allowed_quote_symbol(None) is False
    
    def test_normalize_quote_symbol_success(self):
        """normalize_quote_symbol should normalize and validate."""
        assert normalize_quote_symbol("ethusdt") == "ETHUSDT"
        assert normalize_quote_symbol("  SOLUSDC  ") == "SOLUSDC"
        assert normalize_quote_symbol("btcusdt") == "BTCUSDT"
    
    def test_normalize_quote_symbol_missing(self):
        """Missing symbol should raise ValueError with correct code."""
        with pytest.raises(ValueError) as exc_info:
            normalize_quote_symbol("")
        assert "symbol_required" in str(exc_info.value)
        
        with pytest.raises(ValueError) as exc_info:
            normalize_quote_symbol(None)
        assert "symbol_required" in str(exc_info.value)
        
        # Custom error code
        with pytest.raises(ValueError) as exc_info:
            normalize_quote_symbol("", missing_error_code="custom_missing")
        assert "custom_missing" in str(exc_info.value)
    
    def test_normalize_quote_symbol_invalid_quote(self):
        """Invalid quote asset should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            normalize_quote_symbol("ETHBTC")
        assert "invalid_quote_asset" in str(exc_info.value)
        
        with pytest.raises(ValueError) as exc_info:
            normalize_quote_symbol("BTCBUSD")
        assert "invalid_quote_asset" in str(exc_info.value)
        
        # Custom error code
        with pytest.raises(ValueError) as exc_info:
            normalize_quote_symbol("ETHBTC", invalid_error_code="custom_invalid")
        assert "custom_invalid" in str(exc_info.value)
    
    def test_filter_allowed_quote_symbols(self):
        """filter_allowed_quote_symbols should filter and normalize."""
        input_list = ["ETHUSDT", "ETHBTC", "SOLUSDC", "BTCBUSD", "BTCUSDT", "invalid"]
        result = filter_allowed_quote_symbols(input_list)
        assert "ETHUSDT" in result
        assert "SOLUSDC" in result
        assert "BTCUSDT" in result
        assert "ETHBTC" not in result
        assert "BTCBUSD" not in result
        assert "INVALID" not in result
    
    def test_filter_allowed_quote_symbols_empty(self):
        """Empty input should return empty list."""
        assert filter_allowed_quote_symbols([]) == []
        assert filter_allowed_quote_symbols(None) == []
    
    def test_filter_allowed_quote_symbols_deduplication(self):
        """Duplicates should be removed."""
        input_list = ["ETHUSDT", "ethusdt", "ETHUSDT", "SOLUSDC"]
        result = filter_allowed_quote_symbols(input_list)
        assert result.count("ETHUSDT") == 1
        assert len([s for s in result if s == "ETHUSDT"]) == 1


# ============================================================================
# API INTEGRATION TESTS - Execution Preview Path
# ============================================================================

class TestExecutionPreviewQuotePolicy:
    """Tests for execution preview endpoint quote asset policy enforcement."""
    
    def test_preview_valid_usdt_symbol(self, user_headers):
        """Valid USDT symbol should be accepted."""
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
        # Should return 200 (valid preview)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "preview" in data
        assert data["preview"]["normalized_order_payload"]["symbol"] == "ETHUSDT"
    
    def test_preview_valid_usdc_symbol(self, user_headers):
        """Valid USDC symbol should be accepted."""
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
    
    def test_preview_missing_symbol_no_fallback(self, user_headers):
        """Missing symbol should be rejected, NOT fallback to BTCUSDT."""
        payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "",
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
        assert "symbol_required" in response.text.lower()
    
    def test_preview_invalid_quote_ethbtc(self, user_headers):
        """ETHBTC (BTC quote) should be rejected."""
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
        assert "invalid_quote_asset" in response.text.lower()
    
    def test_preview_invalid_quote_btcbusd(self, user_headers):
        """BTCBUSD (BUSD quote) should be rejected."""
        payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "BTCBUSD",
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
    
    def test_preview_invalid_quote_solbnb(self, user_headers):
        """SOLBNB (BNB quote) should be rejected."""
        payload = {
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "SOLBNB",
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
    
    def test_preview_scanner_symbol_mismatch(self, user_headers):
        """Scanner signal symbol mismatch should be rejected."""
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
                "symbol": "SOLUSDT",  # Mismatch!
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


# ============================================================================
# API INTEGRATION TESTS - Scanner Run Guard
# ============================================================================

class TestScannerRunQuotePolicy:
    """Tests for scanner run endpoint quote asset policy enforcement."""
    
    def test_scanner_run_valid_usdt_symbols(self, user_headers):
        """Scanner run with valid USDT symbols should succeed."""
        payload = {
            "mode": "assisted",
            "max_results": 10,
            "symbol_source": "crypto",
            "symbol_selection_mode": "manual_selection",
            "selected_symbols": ["ETHUSDT", "BTCUSDT", "SOLUSDT"],
        }
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=user_headers,
            json=payload,
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_scanner_run_valid_usdc_symbols(self, user_headers):
        """Scanner run with valid USDC symbols should succeed."""
        payload = {
            "mode": "assisted",
            "max_results": 10,
            "symbol_source": "crypto",
            "symbol_selection_mode": "manual_selection",
            "selected_symbols": ["ETHUSDC", "BTCUSDC"],
        }
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=user_headers,
            json=payload,
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_scanner_run_empty_symbols_rejected(self, user_headers):
        """Scanner run with no symbols should be rejected."""
        payload = {
            "mode": "assisted",
            "max_results": 10,
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
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
    
    def test_scanner_run_all_invalid_symbols_rejected(self, user_headers):
        """Scanner run with only invalid quote symbols should be rejected."""
        payload = {
            "mode": "assisted",
            "max_results": 10,
            "symbol_source": "crypto",
            "symbol_selection_mode": "manual_selection",
            "selected_symbols": ["ETHBTC", "BTCBUSD", "SOLBNB"],
        }
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run",
            headers=user_headers,
            json=payload,
            timeout=30,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        # Should mention policy or invalid symbols
        assert "usdt" in response.text.lower() or "usdc" in response.text.lower()


# ============================================================================
# API INTEGRATION TESTS - Market Ticker Endpoint
# ============================================================================

class TestMarketTickerQuotePolicy:
    """Tests for market ticker endpoint quote asset policy enforcement."""
    
    def test_ticker_valid_symbol(self, user_headers):
        """Market ticker with valid USDT symbol should succeed."""
        response = requests.get(
            f"{BASE_URL}/api/market/ticker",
            headers=user_headers,
            params={"symbol": "ETHUSDT"},
            timeout=20,
        )
        # May return 200 or some other status depending on market data availability
        # But should NOT return 400 for invalid_quote_asset
        if response.status_code == 400:
            assert "invalid_quote_asset" not in response.text.lower()
    
    def test_ticker_missing_symbol_rejected(self, user_headers):
        """Market ticker without symbol should be rejected."""
        response = requests.get(
            f"{BASE_URL}/api/market/ticker",
            headers=user_headers,
            params={},
            timeout=20,
        )
        assert response.status_code in [400, 422], f"Expected 400/422, got {response.status_code}: {response.text}"
    
    def test_ticker_invalid_quote_rejected(self, user_headers):
        """Market ticker with invalid quote asset should be rejected."""
        response = requests.get(
            f"{BASE_URL}/api/market/ticker",
            headers=user_headers,
            params={"symbol": "ETHBTC"},
            timeout=20,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        assert "invalid_quote_asset" in response.text.lower()
    
    def test_ticker_btcbusd_rejected(self, user_headers):
        """Market ticker with BTCBUSD should be rejected."""
        response = requests.get(
            f"{BASE_URL}/api/market/ticker",
            headers=user_headers,
            params={"symbol": "BTCBUSD"},
            timeout=20,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        assert "invalid_quote_asset" in response.text.lower()


# ============================================================================
# API INTEGRATION TESTS - Admin Risk Simulation
# ============================================================================

class TestAdminRiskSimulationQuotePolicy:
    """Tests for admin risk simulation endpoint quote asset policy enforcement."""
    
    def test_risk_simulation_valid_symbol(self, admin_headers, user_headers):
        """Risk simulation with valid symbol should succeed."""
        # First get a user_id from the user_headers
        me_response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers=user_headers,
            timeout=20,
        )
        assert me_response.status_code == 200
        user_id = me_response.json().get("id")
        
        payload = {
            "user_id": user_id,
            "intent_payload": {
                "symbol": "ETHUSDT",
                "side": "buy",
                "notional": 100,
            },
            "apply_override": False,
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation",
            headers=admin_headers,
            json=payload,
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_risk_simulation_missing_symbol_rejected(self, admin_headers, user_headers):
        """Risk simulation without symbol should be rejected."""
        me_response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers=user_headers,
            timeout=20,
        )
        assert me_response.status_code == 200
        user_id = me_response.json().get("id")
        
        payload = {
            "user_id": user_id,
            "intent_payload": {
                "symbol": "",
                "side": "buy",
                "notional": 100,
            },
            "apply_override": False,
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation",
            headers=admin_headers,
            json=payload,
            timeout=30,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        assert "symbol_required" in response.text.lower()
    
    def test_risk_simulation_invalid_quote_rejected(self, admin_headers, user_headers):
        """Risk simulation with invalid quote asset should be rejected."""
        me_response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers=user_headers,
            timeout=20,
        )
        assert me_response.status_code == 200
        user_id = me_response.json().get("id")
        
        payload = {
            "user_id": user_id,
            "intent_payload": {
                "symbol": "ETHBTC",
                "side": "buy",
                "notional": 100,
            },
            "apply_override": False,
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/risk-simulation",
            headers=admin_headers,
            json=payload,
            timeout=30,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        assert "invalid_quote_asset" in response.text.lower()


# ============================================================================
# API INTEGRATION TESTS - Symbol Selector
# ============================================================================

class TestSymbolSelectorQuotePolicy:
    """Tests for symbol selector crypto filters policy compliance."""
    
    def test_symbol_universe_filters_invalid_quotes(self, user_headers):
        """Symbol universe endpoint should only return USDT/USDC pairs for crypto."""
        response = requests.get(
            f"{BASE_URL}/api/symbol-selector/universe",
            headers=user_headers,
            params={
                "source": "crypto",
                "exchange": "binance",
                "market_type": "spot",
                "mode": "top_volume",
            },
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Check selected_symbols - all should be USDT or USDC
        selected = data.get("selected_symbols", [])
        for symbol in selected:
            assert is_allowed_quote_symbol(symbol), f"Invalid symbol in universe: {symbol}"
    
    def test_watchlist_creation_filters_invalid(self, user_headers):
        """Watchlist creation should filter out invalid quote symbols."""
        payload = {
            "name": f"test_watchlist_{uuid.uuid4().hex[:6]}",
            "source": "crypto",
            "exchange": "binance",
            "market_type": "spot",
            "symbols": ["ETHUSDT", "ETHBTC", "SOLUSDC", "BTCBUSD"],
        }
        response = requests.post(
            f"{BASE_URL}/api/symbol-selector/watchlists",
            headers=user_headers,
            json=payload,
            timeout=20,
        )
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Watchlist should only contain valid symbols
        symbols = data.get("symbols", [])
        for symbol in symbols:
            assert is_allowed_quote_symbol(symbol), f"Invalid symbol in watchlist: {symbol}"
        assert "ETHBTC" not in symbols
        assert "BTCBUSD" not in symbols


# ============================================================================
# API INTEGRATION TESTS - Futures Execution Contract
# ============================================================================

class TestFuturesExecutionContractQuotePolicy:
    """Tests for futures execution contract quote asset validation."""
    
    def test_futures_contract_model_validation(self):
        """Test FuturesExecutionRequest model validates quote asset."""
        from core.execution.futures_execution_contract import FuturesExecutionRequest
        from pydantic import ValidationError
        
        # Valid USDT symbol should work
        valid_request = FuturesExecutionRequest(
            symbol="ETHUSDT",
            side="BUY",
            order_type="MARKET",
            quantity=0.1,
            leverage=3,
            client_order_id="test-client-123456",
            decision_trace_id="test-trace-123456",
            strategy="test_strategy",
        )
        assert valid_request.symbol == "ETHUSDT"
        
        # Invalid quote asset should raise
        with pytest.raises(ValidationError):
            FuturesExecutionRequest(
                symbol="ETHBTC",
                side="BUY",
                order_type="MARKET",
                quantity=0.1,
                leverage=3,
                client_order_id="test-client-123456",
                decision_trace_id="test-trace-123456",
                strategy="test_strategy",
            )


# ============================================================================
# API INTEGRATION TESTS - Trading Preview Service
# ============================================================================

class TestTradingPreviewServiceQuotePolicy:
    """Tests for trading preview service quote asset policy."""
    
    def test_preview_metrics_valid_symbol(self, user_headers):
        """Trading preview should work with valid USDT symbol."""
        payload = {
            "source_type": "manual",
            "market_type": "futures",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50,
            "leverage": 3,
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
        metrics = data.get("metrics", {})
        assert metrics.get("symbol") == "BTCUSDT"
        assert metrics.get("quote_asset") == "USDT"


# ============================================================================
# NEGATIVE TESTS - Various Invalid Quote Assets
# ============================================================================

class TestVariousInvalidQuoteAssets:
    """Comprehensive negative tests for various invalid quote assets."""
    
    @pytest.mark.parametrize("invalid_symbol", [
        "ETHBTC",     # BTC quote
        "BTCBUSD",    # BUSD quote
        "SOLBNB",     # BNB quote
        "ETHEUR",     # EUR quote
        "BTCETH",     # ETH quote
        "XRPBETH",    # BETH quote
        "LINKBNB",    # BNB quote
        "DOGEETH",    # ETH quote
        "ADABTC",     # BTC quote
        "MATICBNB",   # BNB quote
    ])
    def test_invalid_quote_symbols_rejected_by_policy(self, invalid_symbol):
        """Various invalid quote symbols should be rejected by policy."""
        assert is_allowed_quote_symbol(invalid_symbol) is False
        assert extract_quote_asset(invalid_symbol) is None
        
        with pytest.raises(ValueError) as exc_info:
            normalize_quote_symbol(invalid_symbol)
        assert "invalid_quote_asset" in str(exc_info.value)
    
    @pytest.mark.parametrize("valid_symbol", [
        "ETHUSDT",
        "BTCUSDT",
        "SOLUSDT",
        "XRPUSDT",
        "LINKUSDT",
        "ETHUSDC",
        "BTCUSDC",
        "SOLUSDC",
        "AVAXUSDT",
        "DOTUSDC",
    ])
    def test_valid_quote_symbols_accepted_by_policy(self, valid_symbol):
        """Various valid USDT/USDC symbols should be accepted."""
        assert is_allowed_quote_symbol(valid_symbol) is True
        quote = extract_quote_asset(valid_symbol)
        assert quote in {"USDT", "USDC"}
        
        normalized = normalize_quote_symbol(valid_symbol)
        assert normalized == valid_symbol.upper()


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

class TestEdgeCases:
    """Edge case tests for quote asset policy."""
    
    def test_whitespace_handling(self):
        """Whitespace should be trimmed properly."""
        assert is_allowed_quote_symbol("  ETHUSDT  ") is True
        assert normalize_quote_symbol("  ethusdt  ") == "ETHUSDT"
    
    def test_case_insensitivity(self):
        """Symbol matching should be case insensitive."""
        assert is_allowed_quote_symbol("ethusdt") is True
        assert is_allowed_quote_symbol("ETHUSDT") is True
        assert is_allowed_quote_symbol("EthUsdt") is True
    
    def test_usdt_at_end_not_beginning(self):
        """USDT must be at the end, not beginning."""
        # USDTETH should not be valid
        assert is_allowed_quote_symbol("USDTETH") is False
        assert is_allowed_quote_symbol("USDCBTC") is False
    
    def test_short_symbols_rejected(self):
        """Too short symbols should be rejected."""
        assert is_allowed_quote_symbol("USDT") is False  # Just quote, no base
        assert is_allowed_quote_symbol("USDC") is False
    
    def test_filter_mixed_list(self):
        """Filter should handle mixed valid/invalid lists correctly."""
        mixed = [
            "ETHUSDT",   # valid
            "ETHBTC",    # invalid
            "",          # empty
            None,        # null
            "SOLUSDC",   # valid
            "BTCBUSD",   # invalid
            "  btcusdt  ", # valid with whitespace
        ]
        result = filter_allowed_quote_symbols(mixed)
        assert "ETHUSDT" in result
        assert "SOLUSDC" in result
        assert "BTCUSDT" in result
        assert len([s for s in result if "BTC" in s and "USDT" not in s and "USDC" not in s]) == 0
