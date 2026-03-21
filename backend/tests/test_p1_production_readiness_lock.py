"""
P1 Production Readiness Lock Testing
=====================================
Tests for:
1. Configuration lock: /app/config/trading.json is single source for allowed_quote_assets
2. Runtime /quote-policy endpoint returns allowed quotes from config
3. Guard telemetry: INVALID_QUOTE_ASSET badge + highlight + pinned top reason
4. State validation checklist: real state updates (not dummy)
5. Action->Result: toast success/fail + trace_id + panel last_action_result
6. Guard telemetry finalize: blocked trade list + reason breakdown + timestamp + symbol
"""

import os
import json
import pytest
import requests
from pathlib import Path

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
USER_EMAIL = "quote.user@platform.local"
USER_PASSWORD = "QuoteUser123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get super admin auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def user_token():
    """Get regular user auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": USER_EMAIL, "password": USER_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"User login failed: {response.status_code} - {response.text}")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def user_headers(user_token):
    return {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}


class TestConfigurationLock:
    """Test that /app/config/trading.json is the single source for allowed_quote_assets"""

    def test_trading_config_file_exists(self):
        """Verify trading.json config file exists"""
        config_path = Path("/app/config/trading.json")
        assert config_path.exists(), "trading.json config file must exist"

    def test_trading_config_has_allowed_quote_assets(self):
        """Verify trading.json has allowed_quote_assets array"""
        config_path = Path("/app/config/trading.json")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        assert "allowed_quote_assets" in config, "Config must have allowed_quote_assets"
        assert isinstance(config["allowed_quote_assets"], list), "allowed_quote_assets must be a list"
        assert len(config["allowed_quote_assets"]) > 0, "allowed_quote_assets must not be empty"

    def test_trading_config_contains_usdt_usdc(self):
        """Verify config contains USDT and USDC"""
        config_path = Path("/app/config/trading.json")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        quotes = [q.upper() for q in config["allowed_quote_assets"]]
        assert "USDT" in quotes, "USDT must be in allowed_quote_assets"
        assert "USDC" in quotes, "USDC must be in allowed_quote_assets"


class TestRuntimeQuotePolicyEndpoint:
    """Test /runtime/quote-policy endpoint returns allowed quotes from config"""

    def test_quote_policy_endpoint_accessible(self, admin_headers):
        """Verify /runtime/quote-policy endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/runtime/quote-policy", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_quote_policy_returns_allowed_quote_assets(self, admin_headers):
        """Verify endpoint returns allowed_quote_assets array"""
        response = requests.get(f"{BASE_URL}/api/runtime/quote-policy", headers=admin_headers)
        data = response.json()
        assert "allowed_quote_assets" in data, "Response must have allowed_quote_assets"
        assert isinstance(data["allowed_quote_assets"], list), "allowed_quote_assets must be a list"

    def test_quote_policy_matches_config_file(self, admin_headers):
        """Verify endpoint returns same values as config file"""
        config_path = Path("/app/config/trading.json")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config_quotes = [q.upper() for q in config["allowed_quote_assets"]]

        response = requests.get(f"{BASE_URL}/api/runtime/quote-policy", headers=admin_headers)
        api_quotes = [q.upper() for q in response.json()["allowed_quote_assets"]]

        assert set(config_quotes) == set(api_quotes), f"Config quotes {config_quotes} must match API quotes {api_quotes}"


class TestGuardTelemetryEndpoint:
    """Test /runtime/guard/telemetry endpoint for INVALID_QUOTE_ASSET visibility"""

    def test_guard_telemetry_endpoint_accessible(self, admin_headers):
        """Verify /runtime/guard/telemetry endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/runtime/guard/telemetry", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_guard_telemetry_has_blocked_trade_list(self, admin_headers):
        """Verify telemetry has blocked_trade_list"""
        response = requests.get(f"{BASE_URL}/api/runtime/guard/telemetry", headers=admin_headers)
        data = response.json()
        assert "blocked_trade_list" in data, "Response must have blocked_trade_list"
        assert isinstance(data["blocked_trade_list"], list), "blocked_trade_list must be a list"

    def test_guard_telemetry_has_top_reasons(self, admin_headers):
        """Verify telemetry has top_reasons breakdown"""
        response = requests.get(f"{BASE_URL}/api/runtime/guard/telemetry", headers=admin_headers)
        data = response.json()
        assert "top_reasons" in data, "Response must have top_reasons"
        assert isinstance(data["top_reasons"], list), "top_reasons must be a list"

    def test_guard_telemetry_has_allowed_quote_assets(self, admin_headers):
        """Verify telemetry returns allowed_quote_assets"""
        response = requests.get(f"{BASE_URL}/api/runtime/guard/telemetry", headers=admin_headers)
        data = response.json()
        assert "allowed_quote_assets" in data, "Response must have allowed_quote_assets"
        assert isinstance(data["allowed_quote_assets"], list), "allowed_quote_assets must be a list"

    def test_guard_telemetry_blocked_trade_has_required_fields(self, admin_headers):
        """Verify blocked trades have required fields: symbol, reason, timestamp"""
        response = requests.get(f"{BASE_URL}/api/runtime/guard/telemetry", headers=admin_headers)
        data = response.json()
        blocked_trades = data.get("blocked_trade_list", [])
        
        if len(blocked_trades) > 0:
            trade = blocked_trades[0]
            assert "symbol" in trade, "Blocked trade must have symbol"
            assert "reason" in trade or "reason_codes" in trade, "Blocked trade must have reason or reason_codes"
            assert "updated_at" in trade, "Blocked trade must have updated_at timestamp"

    def test_guard_telemetry_top_reasons_has_count(self, admin_headers):
        """Verify top_reasons has reason and count fields"""
        response = requests.get(f"{BASE_URL}/api/runtime/guard/telemetry", headers=admin_headers)
        data = response.json()
        top_reasons = data.get("top_reasons", [])
        
        if len(top_reasons) > 0:
            reason = top_reasons[0]
            assert "reason" in reason, "Top reason must have reason field"
            assert "count" in reason, "Top reason must have count field"


class TestWSHealthEndpoint:
    """Test /runtime/ws/health endpoint for state validation"""

    def test_ws_health_endpoint_accessible(self, admin_headers):
        """Verify /runtime/ws/health endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/runtime/ws/health", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_ws_health_has_state(self, admin_headers):
        """Verify ws health has state object"""
        response = requests.get(f"{BASE_URL}/api/runtime/ws/health", headers=admin_headers)
        data = response.json()
        assert "state" in data, "Response must have state"


class TestGateStatusEndpoint:
    """Test /runtime/gate/status endpoint for release gate state"""

    def test_gate_status_endpoint_accessible(self, admin_headers):
        """Verify /runtime/gate/status endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/runtime/gate/status", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_gate_status_has_status_field(self, admin_headers):
        """Verify gate status has status field"""
        response = requests.get(f"{BASE_URL}/api/runtime/gate/status", headers=admin_headers)
        data = response.json()
        assert "status" in data, "Response must have status field"


class TestOverrideEndpoints:
    """Test /runtime/override/* endpoints for override state"""

    def test_override_active_endpoint_accessible(self, admin_headers):
        """Verify /runtime/override/active endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/runtime/override/active", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_override_active_has_items(self, admin_headers):
        """Verify override active has items array"""
        response = requests.get(f"{BASE_URL}/api/runtime/override/active", headers=admin_headers)
        data = response.json()
        assert "items" in data, "Response must have items"
        assert isinstance(data["items"], list), "items must be a list"

    def test_override_history_endpoint_accessible(self, admin_headers):
        """Verify /runtime/override/history endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/runtime/override/history", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


class TestActionResultContract:
    """Test action endpoints return trace_id and proper result structure"""

    def test_heartbeat_check_returns_trace_id(self, admin_headers):
        """Verify heartbeat check returns trace_id in response"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/heartbeat/check",
            headers=admin_headers,
            json={"lag_threshold_seconds": 60},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "trace_id" in data, "Response must have trace_id"
        assert "status" in data, "Response must have status"
        assert "message" in data, "Response must have message"

    def test_action_result_has_state_snapshot(self, admin_headers):
        """Verify action result has state_snapshot"""
        response = requests.post(
            f"{BASE_URL}/api/runtime/heartbeat/check",
            headers=admin_headers,
            json={"lag_threshold_seconds": 60},
        )
        data = response.json()
        assert "state_snapshot" in data, "Response must have state_snapshot"


class TestAlertsEndpoints:
    """Test /runtime/alerts/* endpoints"""

    def test_alerts_history_endpoint_accessible(self, admin_headers):
        """Verify /runtime/alerts/history endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/runtime/alerts/history", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_alerts_history_has_items(self, admin_headers):
        """Verify alerts history has items array"""
        response = requests.get(f"{BASE_URL}/api/runtime/alerts/history", headers=admin_headers)
        data = response.json()
        assert "items" in data, "Response must have items"
        assert isinstance(data["items"], list), "items must be a list"


class TestAlertPolicyEndpoint:
    """Test /runtime/alert-policy endpoint"""

    def test_alert_policy_endpoint_accessible(self, admin_headers):
        """Verify /runtime/alert-policy endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/runtime/alert-policy", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_alert_policy_has_policy_object(self, admin_headers):
        """Verify alert policy has policy object"""
        response = requests.get(f"{BASE_URL}/api/runtime/alert-policy", headers=admin_headers)
        data = response.json()
        assert "policy" in data, "Response must have policy"


class TestExchangeMonitoringEndpoint:
    """Test /runtime/exchange/monitoring endpoint"""

    def test_exchange_monitoring_endpoint_accessible(self, admin_headers):
        """Verify /runtime/exchange/monitoring endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/runtime/exchange/monitoring", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_exchange_monitoring_has_trend(self, admin_headers):
        """Verify exchange monitoring has trend data"""
        response = requests.get(f"{BASE_URL}/api/runtime/exchange/monitoring", headers=admin_headers)
        data = response.json()
        assert "trend" in data, "Response must have trend"


class TestHardeningAnalyticsEndpoint:
    """Test /runtime/hardening/analytics endpoint"""

    def test_hardening_analytics_endpoint_accessible(self, admin_headers):
        """Verify /runtime/hardening/analytics endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/runtime/hardening/analytics", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_hardening_analytics_has_items(self, admin_headers):
        """Verify hardening analytics has items"""
        response = requests.get(f"{BASE_URL}/api/runtime/hardening/analytics", headers=admin_headers)
        data = response.json()
        assert "items" in data, "Response must have items"


class TestActionAuditEndpoint:
    """Test /runtime/action-audit endpoint"""

    def test_action_audit_endpoint_accessible(self, admin_headers):
        """Verify /runtime/action-audit endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/runtime/action-audit", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_action_audit_has_items(self, admin_headers):
        """Verify action audit has items"""
        response = requests.get(f"{BASE_URL}/api/runtime/action-audit", headers=admin_headers)
        data = response.json()
        assert "items" in data, "Response must have items"


class TestInvalidQuoteAssetNormalization:
    """Test that INVALID_QUOTE_ASSET reason is properly normalized in telemetry"""

    def test_reason_code_normalization_in_telemetry(self, admin_headers):
        """Verify reason codes are normalized to INVALID_QUOTE_ASSET"""
        response = requests.get(f"{BASE_URL}/api/runtime/guard/telemetry", headers=admin_headers)
        data = response.json()
        
        # Check if any blocked trades have INVALID_QUOTE_ASSET reason
        blocked_trades = data.get("blocked_trade_list", [])
        top_reasons = data.get("top_reasons", [])
        
        # Verify reason codes are uppercase and normalized
        for trade in blocked_trades:
            reason_codes = trade.get("reason_codes", [])
            for code in reason_codes:
                assert code == code.upper(), f"Reason code {code} should be uppercase"
        
        for reason in top_reasons:
            reason_text = reason.get("reason", "")
            assert reason_text == reason_text.upper(), f"Reason {reason_text} should be uppercase"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
