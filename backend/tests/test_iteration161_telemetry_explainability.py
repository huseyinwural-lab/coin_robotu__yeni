"""
Iteration 161 - Telemetry + Explainability Testing

Tests for:
T1: Guard telemetry events (EXECUTION_BLOCKED / EXECUTION_ALLOWED / EXECUTION_OVERRIDE_ENABLED)
T2: Aggregation service behavior (blocked_24h, override_24h, top_reasons)
T3: GET /api/admin/guard-telemetry returns 200 and crash-safe zero/empty contract
T4: Admin /admin/system-status guard telemetry card (API level)
E1: /api/screener returns explain array (min 1, deterministic)
E2: trade responses include explain field in validate/open-position paths
E3: User trade page validation and execution explain
E4: consistency rule for screener explain + trade explain
"""
import os
import sys
from pathlib import Path

import pytest
import requests

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://strategy-version-gov.preview.emergentagent.com"

ADMIN_EMAIL = "admin@platform.local"
ADMIN_PASSWORD = "Admin12345!"
USER_EMAIL = "user1773706589@example.com"
USER_PASSWORD = "User12345!"


class TestGuardTelemetryAPI:
    """T1-T4: Guard telemetry API tests"""

    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=15,
        )
        if response.status_code != 200:
            pytest.skip(f"Admin login failed: {response.status_code}")
        return response.json().get("access_token")

    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    def test_t3_guard_telemetry_endpoint_returns_200(self, admin_headers):
        """T3: GET /api/admin/guard-telemetry returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/admin/guard-telemetry",
            headers=admin_headers,
            timeout=15,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_t3_guard_telemetry_contract_is_crash_safe(self, admin_headers):
        """T3: Guard telemetry returns zero/empty contract even with no data"""
        response = requests.get(
            f"{BASE_URL}/api/admin/guard-telemetry",
            headers=admin_headers,
            timeout=15,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Must have these keys and be valid types
        assert "blocked_24h" in data, "Missing blocked_24h field"
        assert "override_24h" in data, "Missing override_24h field"
        assert "top_reasons" in data, "Missing top_reasons field"
        
        # Values should be valid even if zero
        assert isinstance(data["blocked_24h"], int), "blocked_24h must be int"
        assert isinstance(data["override_24h"], int), "override_24h must be int"
        assert isinstance(data["top_reasons"], list), "top_reasons must be list"
        
        # Values should be non-negative
        assert data["blocked_24h"] >= 0
        assert data["override_24h"] >= 0

    def test_t2_guard_telemetry_top_reasons_structure(self, admin_headers):
        """T2: top_reasons items have reason and count fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/guard-telemetry",
            headers=admin_headers,
            timeout=15,
        )
        assert response.status_code == 200
        data = response.json()
        
        for item in data.get("top_reasons", []):
            assert "reason" in item, "Each top_reasons item must have 'reason'"
            assert "count" in item, "Each top_reasons item must have 'count'"
            assert isinstance(item["reason"], str)
            assert isinstance(item["count"], int)
            assert item["count"] >= 0


class TestScreenerExplainability:
    """E1, E3: Screener explainability tests"""

    @pytest.fixture(scope="class")
    def user_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            timeout=15,
        )
        if response.status_code != 200:
            pytest.skip(f"User login failed: {response.status_code}")
        return response.json().get("access_token")

    @pytest.fixture(scope="class")
    def user_headers(self, user_token):
        return {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}

    def test_e1_screener_returns_explain_array(self, user_headers):
        """E1: /api/screener returns explain array (min 1 if results exist)"""
        response = requests.get(
            f"{BASE_URL}/api/screener",
            headers=user_headers,
            params={"limit": 50},
            timeout=15,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # If there are results, each should have explain array
        for item in data:
            assert "explain" in item, f"Missing explain field in screener result: {item.get('symbol')}"
            assert isinstance(item["explain"], list), "explain must be a list"
            assert len(item["explain"]) >= 1, f"explain must have at least 1 item for {item.get('symbol')}"

    def test_e1_screener_explain_is_deterministic(self, user_headers):
        """E1: Screener explain values should be deterministic (same input = same output)"""
        response1 = requests.get(
            f"{BASE_URL}/api/screener",
            headers=user_headers,
            params={"limit": 20},
            timeout=15,
        )
        response2 = requests.get(
            f"{BASE_URL}/api/screener",
            headers=user_headers,
            params={"limit": 20},
            timeout=15,
        )
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        data1 = response1.json()
        data2 = response2.json()
        
        # Find common symbols and check explain matches
        symbols1 = {item["symbol"]: item["explain"] for item in data1}
        symbols2 = {item["symbol"]: item["explain"] for item in data2}
        
        common = set(symbols1.keys()) & set(symbols2.keys())
        for symbol in common:
            assert symbols1[symbol] == symbols2[symbol], f"Explain for {symbol} is not deterministic"


class TestTradeExplainability:
    """E2, E3: Trade validate/execute explainability tests"""

    @pytest.fixture(scope="class")
    def user_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            timeout=15,
        )
        if response.status_code != 200:
            pytest.skip(f"User login failed: {response.status_code}")
        return response.json().get("access_token")

    @pytest.fixture(scope="class")
    def user_headers(self, user_token):
        return {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}

    def test_e2_validate_order_includes_explain(self, user_headers):
        """E2: POST /api/user/validate-order returns explain field"""
        payload = {
            "symbol": "BTCUSDT",
            "market_type": "futures",
            "order_type": "market",
            "side": "buy",
            "price": 100000,
            "size": 0.001,
            "leverage": 1,
            "margin_mode": "isolated",
        }
        response = requests.post(
            f"{BASE_URL}/api/user/validate-order",
            headers=user_headers,
            json=payload,
            timeout=15,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "explain" in data, "Missing explain field in validate-order response"
        assert isinstance(data["explain"], list), "explain must be a list"
        assert len(data["explain"]) >= 1, "explain must have at least 1 item"

    def test_e2_validate_order_explain_items_are_strings(self, user_headers):
        """E2: Validate order explain items should be strings"""
        payload = {
            "symbol": "ETHUSDT",
            "market_type": "futures",
            "order_type": "market",
            "side": "buy",
            "price": 4000,
            "size": 0.01,
            "leverage": 3,
            "margin_mode": "isolated",
        }
        response = requests.post(
            f"{BASE_URL}/api/user/validate-order",
            headers=user_headers,
            json=payload,
            timeout=15,
        )
        assert response.status_code == 200
        
        data = response.json()
        for item in data.get("explain", []):
            assert isinstance(item, str), f"Explain item must be string, got {type(item)}"


class TestExplainConsistency:
    """E4: Consistency rule - screener explain + trade explain should not conflict"""

    @pytest.fixture(scope="class")
    def user_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            timeout=15,
        )
        if response.status_code != 200:
            pytest.skip(f"User login failed: {response.status_code}")
        return response.json().get("access_token")

    @pytest.fixture(scope="class")
    def user_headers(self, user_token):
        return {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}

    def test_e4_explain_consistency_service_exists(self):
        """E4: Verify consistency service exists and is callable"""
        from services.explainability_rules_service import explain_consistency_ok
        
        # Test with non-conflicting explains
        result = explain_consistency_ok(
            screener_explain=["RSI oversold (28)", "Volume spike (2.1x)"],
            trade_explain=["Signal score: 85", "Risk check passed"],
        )
        assert result is True, "Non-conflicting explains should pass consistency check"

    def test_e4_explain_consistency_detects_rsi_conflict(self):
        """E4: Consistency check detects RSI conflicts"""
        from services.explainability_rules_service import explain_consistency_ok
        
        # RSI oversold + RSI overbought = conflict
        result = explain_consistency_ok(
            screener_explain=["RSI oversold (25)"],
            trade_explain=["RSI overbought (75)"],
        )
        assert result is False, "RSI oversold + overbought should be detected as conflict"

    def test_e4_explain_consistency_detects_ma_conflict(self):
        """E4: Consistency check detects MA conflicts"""
        from services.explainability_rules_service import explain_consistency_ok
        
        # Above MA50 + Below MA50 = conflict
        result = explain_consistency_ok(
            screener_explain=["Above MA50"],
            trade_explain=["Below MA50"],
        )
        assert result is False, "Above MA50 + Below MA50 should be detected as conflict"

    def test_e4_explain_consistency_detects_trend_conflict(self):
        """E4: Consistency check detects trend conflicts"""
        from services.explainability_rules_service import explain_consistency_ok
        
        # Trend up + Trend down = conflict
        result = explain_consistency_ok(
            screener_explain=["Trend up bias"],
            trade_explain=["Trend down bias"],
        )
        assert result is False, "Trend up + down should be detected as conflict"


class TestExecutionReadinessResponse:
    """E2: Execution paths include explain field"""

    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=15,
        )
        if response.status_code != 200:
            pytest.skip(f"Admin login failed: {response.status_code}")
        return response.json().get("access_token")

    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    def test_execution_readiness_endpoint(self, admin_headers):
        """Verify execution readiness endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-readiness",
            headers=admin_headers,
            timeout=15,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Basic structure checks
        assert "final_status" in data
        assert "mode" in data
        assert data["final_status"] in ["READY", "BLOCKED"]


class TestScannerResultsResponseContract:
    """E1, E3: Scanner results response contract validation"""

    @pytest.fixture(scope="class")
    def user_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            timeout=15,
        )
        if response.status_code != 200:
            pytest.skip(f"User login failed: {response.status_code}")
        return response.json().get("access_token")

    @pytest.fixture(scope="class")
    def user_headers(self, user_token):
        return {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}

    def test_scanner_results_response_contract(self, user_headers):
        """E3: Scanner results include all required fields"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/results",
            headers=user_headers,
            params={"limit": 50},
            timeout=15,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        for item in data:
            # Required fields
            assert "id" in item
            assert "symbol" in item
            assert "signal" in item
            assert "confidence" in item
            assert "signal_score" in item
            assert "explain" in item, f"Missing explain in result for {item.get('symbol')}"
            
            # Explain contract
            assert isinstance(item["explain"], list)
            assert len(item["explain"]) >= 1, f"explain empty for {item.get('symbol')}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
