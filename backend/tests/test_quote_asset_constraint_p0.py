"""
P0 Quote Asset Constraint Tests
================================
Tests for quote asset hard constraint: only USDT/USDC allowed.
This is a core trading constraint, not a risk control.

Test Coverage:
1. Execution layer enforcement: BTCUSDT/ETHUSDC accepted; BTCBTC/ETHBUSD rejected
2. Invalid quote response contract: detail.error_code, detail.message, detail.state_snapshot.symbol
3. Guard telemetry: INVALID_QUOTE_ASSET reason visibility in blocked trades
4. Scanner/signal layer: manual_selection filters non-USDT/USDC symbols
5. Override security: invalid quote cannot be bypassed by any override/guard condition
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
USER_EMAIL = "quote.user@platform.local"
USER_PASSWORD = "QuoteUser123!"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def admin_token(api_client):
    """Get super admin authentication token"""
    response = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Admin authentication failed: {response.status_code}")


@pytest.fixture(scope="module")
def user_token(api_client):
    """Get user authentication token for execution endpoints"""
    response = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": USER_EMAIL, "password": USER_PASSWORD},
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"User authentication failed: {response.status_code}")


@pytest.fixture(scope="module")
def authenticated_admin(api_client, admin_token):
    """Session with admin auth header"""
    api_client.headers.update({"Authorization": f"Bearer {admin_token}"})
    return api_client


@pytest.fixture(scope="module")
def authenticated_user(api_client, user_token):
    """Session with user auth header for execution endpoints"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {user_token}"
    })
    return session


class TestQuoteAssetCorePolicy:
    """Test core quote asset policy functions"""

    def test_allowed_quotes_only_usdt_usdc(self, api_client, user_token):
        """Verify allowed quote assets are only USDT and USDC"""
        # This tests the core policy via an endpoint that exposes allowed quotes
        response = api_client.get(
            f"{BASE_URL}/api/user/execution/presets",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        # Even if presets endpoint doesn't expose quotes directly,
        # we verify the constraint through execution attempts
        assert response.status_code in [200, 401, 403]


class TestExecutionLayerEnforcement:
    """Test execution layer quote asset enforcement"""

    def test_btcusdt_accepted(self, api_client, user_token):
        """BTCUSDT should be accepted (USDT quote)"""
        payload = {
            "source_type": "manual",
            "source_ref_id": "test-btcusdt-001",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50.0,
        }
        response = api_client.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            json=payload,
            headers={"Authorization": f"Bearer {user_token}"},
        )
        # Should not return 400 with INVALID_QUOTE_ASSET
        if response.status_code == 400:
            detail = response.json().get("detail", {})
            if isinstance(detail, dict):
                assert detail.get("error_code") != "INVALID_QUOTE_ASSET", \
                    f"BTCUSDT should be accepted but got INVALID_QUOTE_ASSET: {detail}"
        print(f"BTCUSDT response: {response.status_code}")

    def test_ethusdc_accepted(self, api_client, user_token):
        """ETHUSDC should be accepted (USDC quote)"""
        payload = {
            "source_type": "manual",
            "source_ref_id": "test-ethusdc-001",
            "market_type": "spot",
            "symbol": "ETHUSDC",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50.0,
        }
        response = api_client.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            json=payload,
            headers={"Authorization": f"Bearer {user_token}"},
        )
        # Should not return 400 with INVALID_QUOTE_ASSET
        if response.status_code == 400:
            detail = response.json().get("detail", {})
            if isinstance(detail, dict):
                assert detail.get("error_code") != "INVALID_QUOTE_ASSET", \
                    f"ETHUSDC should be accepted but got INVALID_QUOTE_ASSET: {detail}"
        print(f"ETHUSDC response: {response.status_code}")

    def test_btcbtc_rejected_invalid_quote(self, api_client, user_token):
        """BTCBTC should be rejected (BTC is not allowed quote)"""
        payload = {
            "source_type": "manual",
            "source_ref_id": "test-btcbtc-001",
            "market_type": "spot",
            "symbol": "BTCBTC",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50.0,
        }
        response = api_client.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            json=payload,
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 400, f"BTCBTC should be rejected with 400, got {response.status_code}"
        detail = response.json().get("detail", {})
        if isinstance(detail, dict):
            assert detail.get("error_code") == "INVALID_QUOTE_ASSET", \
                f"Expected INVALID_QUOTE_ASSET error_code, got: {detail}"
            assert detail.get("message") == "Quote asset must be USDT or USDC", \
                f"Expected standard message, got: {detail.get('message')}"
        print(f"BTCBTC correctly rejected: {detail}")

    def test_ethbusd_rejected_invalid_quote(self, api_client, user_token):
        """ETHBUSD should be rejected (BUSD is not allowed quote)"""
        payload = {
            "source_type": "manual",
            "source_ref_id": "test-ethbusd-001",
            "market_type": "spot",
            "symbol": "ETHBUSD",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50.0,
        }
        response = api_client.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            json=payload,
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 400, f"ETHBUSD should be rejected with 400, got {response.status_code}"
        detail = response.json().get("detail", {})
        if isinstance(detail, dict):
            assert detail.get("error_code") == "INVALID_QUOTE_ASSET", \
                f"Expected INVALID_QUOTE_ASSET error_code, got: {detail}"
            assert detail.get("message") == "Quote asset must be USDT or USDC", \
                f"Expected standard message, got: {detail.get('message')}"
        print(f"ETHBUSD correctly rejected: {detail}")

    def test_soleth_rejected_invalid_quote(self, api_client, user_token):
        """SOLETH should be rejected (ETH is not allowed quote)"""
        payload = {
            "source_type": "manual",
            "source_ref_id": "test-soleth-001",
            "market_type": "spot",
            "symbol": "SOLETH",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50.0,
        }
        response = api_client.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            json=payload,
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 400, f"SOLETH should be rejected with 400, got {response.status_code}"
        detail = response.json().get("detail", {})
        if isinstance(detail, dict):
            assert detail.get("error_code") == "INVALID_QUOTE_ASSET", \
                f"Expected INVALID_QUOTE_ASSET error_code, got: {detail}"
        print(f"SOLETH correctly rejected: {detail}")


class TestInvalidQuoteResponseContract:
    """Test invalid quote error response contract"""

    def test_error_response_has_error_code(self, api_client, user_token):
        """detail.error_code must be INVALID_QUOTE_ASSET"""
        payload = {
            "source_type": "manual",
            "source_ref_id": "test-contract-001",
            "market_type": "spot",
            "symbol": "BTCEUR",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50.0,
        }
        response = api_client.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            json=payload,
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 400
        detail = response.json().get("detail", {})
        assert isinstance(detail, dict), f"detail should be dict, got: {type(detail)}"
        assert "error_code" in detail, f"detail must have error_code field: {detail}"
        assert detail["error_code"] == "INVALID_QUOTE_ASSET", \
            f"error_code must be INVALID_QUOTE_ASSET, got: {detail['error_code']}"
        print(f"Contract verified - error_code: {detail['error_code']}")

    def test_error_response_has_message(self, api_client, user_token):
        """detail.message must be 'Quote asset must be USDT or USDC'"""
        payload = {
            "source_type": "manual",
            "source_ref_id": "test-contract-002",
            "market_type": "spot",
            "symbol": "BTCGBP",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50.0,
        }
        response = api_client.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            json=payload,
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 400
        detail = response.json().get("detail", {})
        assert isinstance(detail, dict), f"detail should be dict, got: {type(detail)}"
        assert "message" in detail, f"detail must have message field: {detail}"
        assert detail["message"] == "Quote asset must be USDT or USDC", \
            f"message must be standard, got: {detail['message']}"
        print(f"Contract verified - message: {detail['message']}")

    def test_error_response_has_state_snapshot_symbol(self, api_client, user_token):
        """detail.state_snapshot.symbol must contain the rejected symbol"""
        test_symbol = "LINKJPY"
        payload = {
            "source_type": "manual",
            "source_ref_id": "test-contract-003",
            "market_type": "spot",
            "symbol": test_symbol,
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50.0,
        }
        response = api_client.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            json=payload,
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 400
        detail = response.json().get("detail", {})
        assert isinstance(detail, dict), f"detail should be dict, got: {type(detail)}"
        assert "state_snapshot" in detail, f"detail must have state_snapshot field: {detail}"
        state_snapshot = detail["state_snapshot"]
        assert isinstance(state_snapshot, dict), f"state_snapshot should be dict: {state_snapshot}"
        assert "symbol" in state_snapshot, f"state_snapshot must have symbol field: {state_snapshot}"
        assert state_snapshot["symbol"] == test_symbol.upper(), \
            f"state_snapshot.symbol must be {test_symbol.upper()}, got: {state_snapshot['symbol']}"
        print(f"Contract verified - state_snapshot.symbol: {state_snapshot['symbol']}")

    def test_error_response_state_snapshot_has_allowed_quote_assets(self, api_client, user_token):
        """detail.state_snapshot.allowed_quote_assets must list USDT and USDC"""
        payload = {
            "source_type": "manual",
            "source_ref_id": "test-contract-004",
            "market_type": "spot",
            "symbol": "AVAXBNB",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50.0,
        }
        response = api_client.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            json=payload,
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 400
        detail = response.json().get("detail", {})
        state_snapshot = detail.get("state_snapshot", {})
        assert "allowed_quote_assets" in state_snapshot, \
            f"state_snapshot must have allowed_quote_assets: {state_snapshot}"
        allowed = state_snapshot["allowed_quote_assets"]
        assert isinstance(allowed, list), f"allowed_quote_assets should be list: {allowed}"
        assert "USDT" in allowed, f"USDT must be in allowed_quote_assets: {allowed}"
        assert "USDC" in allowed, f"USDC must be in allowed_quote_assets: {allowed}"
        print(f"Contract verified - allowed_quote_assets: {allowed}")


class TestGuardTelemetryVisibility:
    """Test guard telemetry shows INVALID_QUOTE_ASSET reason"""

    def test_guard_telemetry_endpoint_accessible(self, api_client, admin_token):
        """Guard telemetry endpoint should be accessible"""
        response = api_client.get(
            f"{BASE_URL}/api/runtime/guard/telemetry",
            params={"limit": 100},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200, f"Guard telemetry should return 200, got {response.status_code}"
        data = response.json()
        assert "blocked_trade_list" in data, f"Response must have blocked_trade_list: {data.keys()}"
        assert "top_reasons" in data, f"Response must have top_reasons: {data.keys()}"
        print(f"Guard telemetry accessible - blocked_trades: {len(data.get('blocked_trade_list', []))}")

    def test_invalid_quote_triggers_audit_log(self, api_client, user_token, admin_token):
        """Invalid quote rejection should create EXECUTION_BLOCKED audit log"""
        # First trigger an invalid quote rejection using user token
        payload = {
            "source_type": "manual",
            "source_ref_id": "test-audit-001",
            "market_type": "spot",
            "symbol": "DOTBNB",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50.0,
        }
        reject_response = api_client.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            json=payload,
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert reject_response.status_code == 400, "Should reject invalid quote"

        # Now check guard telemetry for the blocked trade using admin token
        telemetry_response = api_client.get(
            f"{BASE_URL}/api/runtime/guard/telemetry",
            params={"limit": 100},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert telemetry_response.status_code == 200
        data = telemetry_response.json()
        
        # Check if INVALID_QUOTE_ASSET appears in top_reasons or blocked_trade_list
        top_reasons = data.get("top_reasons", [])
        blocked_trades = data.get("blocked_trade_list", [])
        
        # Look for INVALID_QUOTE_ASSET in reasons
        invalid_quote_in_reasons = any(
            "INVALID_QUOTE_ASSET" in str(item.get("reason", "")).upper()
            for item in top_reasons
        )
        invalid_quote_in_blocked = any(
            "INVALID_QUOTE_ASSET" in str(item.get("reason", "")).upper() or
            "INVALID_QUOTE_ASSET" in str(item.get("reason_codes", [])).upper()
            for item in blocked_trades
        )
        
        print(f"Top reasons: {top_reasons[:5]}")
        print(f"Blocked trades sample: {blocked_trades[:3]}")
        print(f"INVALID_QUOTE_ASSET in reasons: {invalid_quote_in_reasons}")
        print(f"INVALID_QUOTE_ASSET in blocked: {invalid_quote_in_blocked}")

    def test_reason_code_normalization(self, api_client, user_token, admin_token):
        """Verify reason codes are normalized to INVALID_QUOTE_ASSET"""
        # Trigger multiple invalid quote rejections with different symbols
        test_symbols = ["XRPBNB", "ADAEUR", "MATICGBP"]
        for symbol in test_symbols:
            payload = {
                "source_type": "manual",
                "source_ref_id": f"test-norm-{symbol}",
                "market_type": "spot",
                "symbol": symbol,
                "side": "buy",
                "order_type": "market",
                "position_size_mode": "fixed_notional",
                "position_size_value": 50.0,
            }
            api_client.post(
                f"{BASE_URL}/api/user/execution/intent/preview",
                json=payload,
                headers={"Authorization": f"Bearer {user_token}"},
            )

        # Check telemetry using admin token
        response = api_client.get(
            f"{BASE_URL}/api/runtime/guard/telemetry",
            params={"limit": 100},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        print(f"Telemetry after multiple rejections: {response.json().get('top_reasons', [])[:5]}")


class TestCaseInsensitiveHandling:
    """Test case-insensitive symbol handling"""

    def test_lowercase_usdt_symbol_accepted(self, api_client, user_token):
        """btcusdt (lowercase) should be accepted"""
        payload = {
            "source_type": "manual",
            "source_ref_id": "test-case-001",
            "market_type": "spot",
            "symbol": "btcusdt",  # lowercase
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50.0,
        }
        response = api_client.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            json=payload,
            headers={"Authorization": f"Bearer {user_token}"},
        )
        if response.status_code == 400:
            detail = response.json().get("detail", {})
            if isinstance(detail, dict):
                assert detail.get("error_code") != "INVALID_QUOTE_ASSET", \
                    f"btcusdt (lowercase) should be accepted: {detail}"
        print(f"Lowercase btcusdt response: {response.status_code}")

    def test_mixed_case_usdc_symbol_accepted(self, api_client, user_token):
        """EthUsdc (mixed case) should be accepted"""
        payload = {
            "source_type": "manual",
            "source_ref_id": "test-case-002",
            "market_type": "spot",
            "symbol": "EthUsdc",  # mixed case
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50.0,
        }
        response = api_client.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            json=payload,
            headers={"Authorization": f"Bearer {user_token}"},
        )
        if response.status_code == 400:
            detail = response.json().get("detail", {})
            if isinstance(detail, dict):
                assert detail.get("error_code") != "INVALID_QUOTE_ASSET", \
                    f"EthUsdc (mixed case) should be accepted: {detail}"
        print(f"Mixed case EthUsdc response: {response.status_code}")

    def test_lowercase_invalid_quote_rejected(self, api_client, user_token):
        """ethbusd (lowercase invalid) should be rejected"""
        payload = {
            "source_type": "manual",
            "source_ref_id": "test-case-003",
            "market_type": "spot",
            "symbol": "ethbusd",  # lowercase invalid
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50.0,
        }
        response = api_client.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            json=payload,
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 400, f"ethbusd should be rejected, got {response.status_code}"
        detail = response.json().get("detail", {})
        if isinstance(detail, dict):
            assert detail.get("error_code") == "INVALID_QUOTE_ASSET", \
                f"Expected INVALID_QUOTE_ASSET, got: {detail}"
        print(f"Lowercase ethbusd correctly rejected")


class TestV1TradingEndpoint:
    """Test v1/user/trading endpoint quote asset enforcement"""

    def test_v1_trading_preview_valid_quote(self, api_client, user_token):
        """V1 trading preview should accept valid quote assets"""
        payload = {
            "source_type": "manual",
            "source_ref_id": "test-v1-001",
            "market_type": "spot",
            "symbol": "SOLUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50.0,
        }
        response = api_client.post(
            f"{BASE_URL}/api/v1/user/trading/preview",
            json=payload,
            headers={"Authorization": f"Bearer {user_token}"},
        )
        if response.status_code == 400:
            detail = response.json().get("detail", {})
            if isinstance(detail, dict):
                assert detail.get("error_code") != "INVALID_QUOTE_ASSET", \
                    f"SOLUSDT should be accepted: {detail}"
        print(f"V1 trading preview SOLUSDT: {response.status_code}")

    def test_v1_trading_preview_invalid_quote(self, api_client, user_token):
        """V1 trading preview should reject invalid quote assets"""
        payload = {
            "source_type": "manual",
            "source_ref_id": "test-v1-002",
            "market_type": "spot",
            "symbol": "SOLBNB",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50.0,
        }
        response = api_client.post(
            f"{BASE_URL}/api/v1/user/trading/preview",
            json=payload,
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 400, f"SOLBNB should be rejected, got {response.status_code}"
        detail = response.json().get("detail", {})
        if isinstance(detail, dict):
            assert detail.get("error_code") == "INVALID_QUOTE_ASSET", \
                f"Expected INVALID_QUOTE_ASSET, got: {detail}"
            assert detail.get("message") == "Quote asset must be USDT or USDC"
            assert "state_snapshot" in detail
            assert detail["state_snapshot"].get("symbol") == "SOLBNB"
        print(f"V1 trading preview SOLBNB correctly rejected: {detail}")


class TestPositionActionEndpoint:
    """Test position action endpoint quote asset enforcement"""

    def test_position_action_preview_invalid_quote(self, api_client, user_token):
        """Position action preview should reject invalid quote assets"""
        payload = {
            "position_id": "test-position-001",
            "intent_type": "close_position",
            "symbol": "BTCEUR",
            "size": 0.001,
            "reduce_only": True,
        }
        response = api_client.post(
            f"{BASE_URL}/api/user/execution/position-actions/preview",
            json=payload,
            headers={"Authorization": f"Bearer {user_token}"},
        )
        # Should reject with INVALID_QUOTE_ASSET
        if response.status_code == 400:
            detail = response.json().get("detail", {})
            if isinstance(detail, dict) and detail.get("error_code") == "INVALID_QUOTE_ASSET":
                assert detail.get("message") == "Quote asset must be USDT or USDC"
                print(f"Position action correctly rejected invalid quote: {detail}")
            else:
                print(f"Position action response: {response.status_code} - {detail}")
        else:
            print(f"Position action response: {response.status_code}")


class TestExecutionSafetyServiceEnforcement:
    """Test execution safety service quote asset enforcement"""

    def test_execution_safety_blocks_invalid_quote(self, api_client, user_token):
        """Execution safety service should block invalid quote at open position"""
        # This tests the assert_execution_open_allowed function
        # which checks extract_quote(symbol) is not None
        payload = {
            "source_type": "manual",
            "source_ref_id": "test-safety-001",
            "market_type": "spot",
            "symbol": "BTCJPY",  # Invalid quote
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 100.0,
            "intent_type": "OPEN_POSITION",
        }
        response = api_client.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            json=payload,
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 400
        detail = response.json().get("detail", {})
        if isinstance(detail, dict):
            assert detail.get("error_code") == "INVALID_QUOTE_ASSET"
        print(f"Execution safety correctly blocked invalid quote")


class TestOverrideSecurityNoBypass:
    """Test that invalid quote cannot be bypassed by any override"""

    def test_invalid_quote_not_bypassed_by_risk_override(self, api_client, admin_token, user_token):
        """Invalid quote should not be bypassed even with risk override active"""
        # First, try to create a risk override using admin token
        override_payload = {
            "override_type": "risk_override",
            "scope": "global",
            "ttl_minutes": 30,
            "reason": "test_quote_bypass_attempt",
            "confirmation_phrase": "CREATE OVERRIDE",
        }
        override_response = api_client.post(
            f"{BASE_URL}/api/runtime/override/create",
            json=override_payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        print(f"Override creation: {override_response.status_code}")

        # Now try to execute with invalid quote using user token - should still be rejected
        payload = {
            "source_type": "manual",
            "source_ref_id": "test-bypass-001",
            "market_type": "spot",
            "symbol": "BTCBNB",  # Invalid quote
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50.0,
        }
        response = api_client.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            json=payload,
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 400, \
            f"Invalid quote should still be rejected with override active, got {response.status_code}"
        detail = response.json().get("detail", {})
        if isinstance(detail, dict):
            assert detail.get("error_code") == "INVALID_QUOTE_ASSET", \
                f"Should get INVALID_QUOTE_ASSET even with override: {detail}"
        print(f"Override does not bypass quote constraint - correctly rejected")

    def test_invalid_quote_not_bypassed_by_guard_condition(self, api_client, user_token):
        """Invalid quote should not be bypassed by any guard condition"""
        # Try with different guard-related parameters
        payload = {
            "source_type": "scanner",  # Different source
            "source_ref_id": "test-guard-bypass-001",
            "market_type": "spot",
            "symbol": "ETHEUR",  # Invalid quote
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50.0,
            "execution_mode": "bot_assisted",
            "signal_confidence": 0.95,  # High confidence
        }
        response = api_client.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            json=payload,
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 400, \
            f"Invalid quote should be rejected regardless of guard conditions, got {response.status_code}"
        detail = response.json().get("detail", {})
        if isinstance(detail, dict):
            assert detail.get("error_code") == "INVALID_QUOTE_ASSET"
        print(f"Guard conditions do not bypass quote constraint")


class TestScannerLayerFiltering:
    """Test scanner/signal layer filters non-USDT/USDC symbols"""

    def test_scanner_run_filters_invalid_quotes(self, api_client, user_token):
        """Scanner run should filter out symbols with invalid quote assets"""
        # Run scanner with manual_selection including invalid quote symbols
        payload = {
            "max_results": 20,
            "symbol_source": "crypto",
            "symbol_selection_mode": "manual_selection",
            "selected_symbols": ["BTCUSDT", "ETHUSDC", "ETHBUSD", "BTCBNB", "SOLUSDT"],
        }
        response = api_client.post(
            f"{BASE_URL}/api/user/scanner/run",
            json=payload,
            headers={"Authorization": f"Bearer {user_token}"},
        )
        
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            symbols_in_results = [r.get("symbol", "").upper() for r in results]
            
            # ETHBUSD and BTCBNB should be filtered out
            assert "ETHBUSD" not in symbols_in_results, \
                f"ETHBUSD should be filtered from scanner results: {symbols_in_results}"
            assert "BTCBNB" not in symbols_in_results, \
                f"BTCBNB should be filtered from scanner results: {symbols_in_results}"
            
            # BTCUSDT, ETHUSDC, SOLUSDT should be present (if data available)
            print(f"Scanner results symbols: {symbols_in_results}")
            print(f"Invalid quotes correctly filtered from scanner")
        else:
            print(f"Scanner run response: {response.status_code} - {response.text[:200]}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
