"""
Phase 6 User Platform Backend Tests - Comprehensive
Tests: exchange_connect, portfolio_map, risk_settings, portfolio/performance/trades APIs
Validates: user-only scope, admin 403, user isolation, AES encrypted masked keys, invalid range 400
"""
import os
import random
import string
from pathlib import Path

import pytest
import requests


def _resolve_base_url() -> str:
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if direct:
        return direct

    env_file = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    if env_file.exists():
        for raw_line in env_file.read_text().splitlines():
            line = raw_line.strip()
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE_URL = _resolve_base_url()
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")


def _unique_email(prefix: str = "phase6test") -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    return f"TEST_{prefix}_{suffix}@example.com"


def _register(email: str, password: str) -> dict:
    response = requests.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": password})
    assert response.status_code == 200, f"Registration failed: {response.text}"
    return response.json()


def _admin_token() -> str:
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["access_token"]


def _approve_user(user_id: str, admin_token: str):
    response = requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200, f"Approval failed: {response.text}"


def _login_user(email: str, password: str) -> str:
    response = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, f"User login failed: {response.text}"
    return response.json()["access_token"]


def _create_approved_user() -> tuple[str, dict]:
    """Create, approve and login a user, returns (token, user_data)"""
    email = _unique_email()
    password = "TestUser123!"
    user = _register(email, password)
    admin_token = _admin_token()
    _approve_user(user["id"], admin_token)
    user_token = _login_user(email, password)
    return user_token, {"id": user["id"], "email": email, "password": password}


class TestUserExchangeConnect:
    """POST /api/user/exchange/connect - user-only, masked keys, AES encrypted"""

    def test_exchange_connect_returns_200_and_masked_keys(self):
        """Exchange connect should return 200 with has_api_key/has_api_secret true, masked_api_key not plaintext"""
        user_token, _ = _create_approved_user()
        headers = {"Authorization": f"Bearer {user_token}"}

        raw_api_key = "FAKE_BINANCE_KEY_XYZ123456789"
        raw_api_secret = "FAKE_BINANCE_SECRET_ABC987654321"

        response = requests.post(
            f"{BASE_URL}/api/user/exchange/connect",
            headers=headers,
            json={
                "exchange": "binance",
                "mode": "live",
                "api_key": raw_api_key,
                "api_secret": raw_api_secret,
            },
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        # Verify has_api_key and has_api_secret are True
        assert data["has_api_key"] is True, "has_api_key should be True"
        assert data["has_api_secret"] is True, "has_api_secret should be True"

        # Verify masked_api_key is NOT the plaintext key
        assert data["masked_api_key"] != raw_api_key, "masked_api_key should NOT be plaintext"

        # Verify masked_api_key contains masking pattern (***) 
        assert "***" in data["masked_api_key"], "masked_api_key should contain masking (***)"

        # Verify credential_fingerprint is present (SHA256 hash)
        assert "credential_fingerprint" in data, "credential_fingerprint should be present"
        assert len(data["credential_fingerprint"]) == 12, "credential_fingerprint should be 12 chars"

    def test_exchange_connect_admin_gets_403(self):
        """Admin token should get 403 on user-only endpoint"""
        admin_token = _admin_token()
        headers = {"Authorization": f"Bearer {admin_token}"}

        response = requests.post(
            f"{BASE_URL}/api/user/exchange/connect",
            headers=headers,
            json={
                "exchange": "binance",
                "mode": "live",
                "api_key": "ADMIN_KEY",
                "api_secret": "ADMIN_SECRET",
            },
        )

        assert response.status_code == 403, f"Expected 403 for admin, got {response.status_code}: {response.text}"


class TestUserPortfolioMap:
    """POST /api/user/portfolio/map - portfolio mapping"""

    def test_portfolio_map_returns_expected_fields(self):
        """Portfolio map should return market_type, current_capital, allocation_capital etc."""
        user_token, _ = _create_approved_user()
        headers = {"Authorization": f"Bearer {user_token}"}

        response = requests.post(
            f"{BASE_URL}/api/user/portfolio/map",
            headers=headers,
            json={
                "market_type": "futures",
                "leverage": 5,
                "margin_mode": "cross",
                "position_side": "BOTH",
            },
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        # Verify required fields
        assert data["market_type"] == "futures", "market_type should be futures"
        assert "current_capital" in data, "current_capital should be present"
        assert "available_balance" in data, "available_balance should be present"
        assert "allocation_capital" in data, "allocation_capital should be present"
        assert "max_trade_loss" in data, "max_trade_loss should be present"
        assert "recommended_order_notional" in data, "recommended_order_notional should be present"
        assert data["leverage"] == 5, "leverage should be 5 for futures"

    def test_portfolio_map_spot_no_leverage(self):
        """Spot market should not return leverage"""
        user_token, _ = _create_approved_user()
        headers = {"Authorization": f"Bearer {user_token}"}

        response = requests.post(
            f"{BASE_URL}/api/user/portfolio/map",
            headers=headers,
            json={
                "market_type": "spot",
                "leverage": 1,
                "margin_mode": "cross",
                "position_side": "BOTH",
            },
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data["market_type"] == "spot"
        assert data["leverage"] is None, "leverage should be None for spot"


class TestUserRiskSettings:
    """PUT /api/user/risk-settings - valid/invalid range handling"""

    def test_risk_settings_valid_update(self):
        """Valid risk settings should return 200"""
        user_token, _ = _create_approved_user()
        headers = {"Authorization": f"Bearer {user_token}"}

        response = requests.put(
            f"{BASE_URL}/api/user/risk-settings",
            headers=headers,
            json={
                "allocation_pct": 30,
                "trade_risk_pct": 15,
                "daily_loss_limit_pct": 5,
                "compounding_enabled": True,
            },
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["allocation_pct"] == 30
        assert data["trade_risk_pct"] == 15
        assert data["daily_loss_limit_pct"] == 5
        assert data["compounding_enabled"] is True

    def test_risk_settings_invalid_allocation_pct_low(self):
        """allocation_pct < 1 should return 400"""
        user_token, _ = _create_approved_user()
        headers = {"Authorization": f"Bearer {user_token}"}

        response = requests.put(
            f"{BASE_URL}/api/user/risk-settings",
            headers=headers,
            json={
                "allocation_pct": 0.5,  # Below 1
                "trade_risk_pct": 10,
                "daily_loss_limit_pct": 3,
                "compounding_enabled": False,
            },
        )

        assert response.status_code == 400, f"Expected 400 for allocation_pct < 1, got {response.status_code}"

    def test_risk_settings_invalid_allocation_pct_high(self):
        """allocation_pct > 50 should return 400"""
        user_token, _ = _create_approved_user()
        headers = {"Authorization": f"Bearer {user_token}"}

        response = requests.put(
            f"{BASE_URL}/api/user/risk-settings",
            headers=headers,
            json={
                "allocation_pct": 55,  # Above 50
                "trade_risk_pct": 10,
                "daily_loss_limit_pct": 3,
                "compounding_enabled": False,
            },
        )

        assert response.status_code == 400, f"Expected 400 for allocation_pct > 50, got {response.status_code}"

    def test_risk_settings_invalid_trade_risk_pct_high(self):
        """trade_risk_pct > 25 should return 400"""
        user_token, _ = _create_approved_user()
        headers = {"Authorization": f"Bearer {user_token}"}

        response = requests.put(
            f"{BASE_URL}/api/user/risk-settings",
            headers=headers,
            json={
                "allocation_pct": 20,
                "trade_risk_pct": 30,  # Above 25
                "daily_loss_limit_pct": 3,
                "compounding_enabled": False,
            },
        )

        assert response.status_code == 400, f"Expected 400 for trade_risk_pct > 25, got {response.status_code}"

    def test_risk_settings_invalid_daily_loss_limit_high(self):
        """daily_loss_limit_pct > 10 should return 400"""
        user_token, _ = _create_approved_user()
        headers = {"Authorization": f"Bearer {user_token}"}

        response = requests.put(
            f"{BASE_URL}/api/user/risk-settings",
            headers=headers,
            json={
                "allocation_pct": 20,
                "trade_risk_pct": 10,
                "daily_loss_limit_pct": 15,  # Above 10
                "compounding_enabled": False,
            },
        )

        assert response.status_code == 400, f"Expected 400 for daily_loss_limit_pct > 10, got {response.status_code}"


class TestUserPortfolioPerformanceTrades:
    """GET /api/user/portfolio, /api/user/performance, /api/user/trades"""

    def test_user_portfolio_returns_200(self):
        """GET /api/user/portfolio should return 200 with expected fields"""
        user_token, _ = _create_approved_user()
        headers = {"Authorization": f"Bearer {user_token}"}

        response = requests.get(f"{BASE_URL}/api/user/portfolio", headers=headers)

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "current_capital" in data
        assert "available_balance" in data
        assert "open_notional" in data
        assert "compounding_enabled" in data

    def test_user_performance_returns_200(self):
        """GET /api/user/performance should return 200 with expected fields"""
        user_token, _ = _create_approved_user()
        headers = {"Authorization": f"Bearer {user_token}"}

        response = requests.get(f"{BASE_URL}/api/user/performance", headers=headers)

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "win_rate" in data
        assert "realized_pnl_total" in data
        assert "total_closed_trades" in data
        assert "profit_factor" in data

    def test_user_trades_returns_200_list(self):
        """GET /api/user/trades should return 200 with a list"""
        user_token, _ = _create_approved_user()
        headers = {"Authorization": f"Bearer {user_token}"}

        response = requests.get(f"{BASE_URL}/api/user/trades", headers=headers)

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "trades should return a list"


class TestAdminAccessDenied:
    """Admin token should get 403 on all /api/user/* endpoints"""

    def test_admin_denied_portfolio(self):
        """Admin token should get 403 on GET /api/user/portfolio"""
        admin_token = _admin_token()
        headers = {"Authorization": f"Bearer {admin_token}"}

        response = requests.get(f"{BASE_URL}/api/user/portfolio", headers=headers)
        assert response.status_code == 403, f"Expected 403 for admin on portfolio, got {response.status_code}"

    def test_admin_denied_performance(self):
        """Admin token should get 403 on GET /api/user/performance"""
        admin_token = _admin_token()
        headers = {"Authorization": f"Bearer {admin_token}"}

        response = requests.get(f"{BASE_URL}/api/user/performance", headers=headers)
        assert response.status_code == 403, f"Expected 403 for admin on performance, got {response.status_code}"

    def test_admin_denied_trades(self):
        """Admin token should get 403 on GET /api/user/trades"""
        admin_token = _admin_token()
        headers = {"Authorization": f"Bearer {admin_token}"}

        response = requests.get(f"{BASE_URL}/api/user/trades", headers=headers)
        assert response.status_code == 403, f"Expected 403 for admin on trades, got {response.status_code}"

    def test_admin_denied_risk_settings_get(self):
        """Admin token should get 403 on GET /api/user/risk-settings"""
        admin_token = _admin_token()
        headers = {"Authorization": f"Bearer {admin_token}"}

        response = requests.get(f"{BASE_URL}/api/user/risk-settings", headers=headers)
        assert response.status_code == 403, f"Expected 403 for admin on risk-settings GET, got {response.status_code}"

    def test_admin_denied_risk_settings_put(self):
        """Admin token should get 403 on PUT /api/user/risk-settings"""
        admin_token = _admin_token()
        headers = {"Authorization": f"Bearer {admin_token}"}

        response = requests.put(
            f"{BASE_URL}/api/user/risk-settings",
            headers=headers,
            json={
                "allocation_pct": 20,
                "trade_risk_pct": 10,
                "daily_loss_limit_pct": 3,
                "compounding_enabled": True,
            },
        )
        assert response.status_code == 403, f"Expected 403 for admin on risk-settings PUT, got {response.status_code}"

    def test_admin_denied_portfolio_map(self):
        """Admin token should get 403 on POST /api/user/portfolio/map"""
        admin_token = _admin_token()
        headers = {"Authorization": f"Bearer {admin_token}"}

        response = requests.post(
            f"{BASE_URL}/api/user/portfolio/map",
            headers=headers,
            json={
                "market_type": "futures",
                "leverage": 1,
                "margin_mode": "cross",
                "position_side": "BOTH",
            },
        )
        assert response.status_code == 403, f"Expected 403 for admin on portfolio/map, got {response.status_code}"


class TestUserIsolation:
    """User1 risk-settings change should NOT reflect on User2"""

    def test_user_isolation_risk_settings(self):
        """User1 changes should not affect User2's settings"""
        # Create two users
        user1_token, _ = _create_approved_user()
        user2_token, _ = _create_approved_user()

        user1_headers = {"Authorization": f"Bearer {user1_token}"}
        user2_headers = {"Authorization": f"Bearer {user2_token}"}

        # Get User2's default settings
        user2_initial = requests.get(f"{BASE_URL}/api/user/risk-settings", headers=user2_headers)
        assert user2_initial.status_code == 200
        assert 1 <= user2_initial.json()["allocation_pct"] <= 50

        # Update User1's settings with specific value
        user1_new_allocation = 45  # Unique value
        requests.put(
            f"{BASE_URL}/api/user/risk-settings",
            headers=user1_headers,
            json={
                "allocation_pct": user1_new_allocation,
                "trade_risk_pct": 20,
                "daily_loss_limit_pct": 8,
                "compounding_enabled": False,
            },
        )

        # Verify User2's settings are NOT affected
        user2_after = requests.get(f"{BASE_URL}/api/user/risk-settings", headers=user2_headers)
        assert user2_after.status_code == 200
        user2_after_allocation = user2_after.json()["allocation_pct"]

        # User2's allocation should NOT be 45 (User1's value)
        assert user2_after_allocation != user1_new_allocation, \
            f"User isolation failed: User2 has User1's allocation_pct={user1_new_allocation}"

        # Confirm User1's value was actually set
        user1_verify = requests.get(f"{BASE_URL}/api/user/risk-settings", headers=user1_headers)
        assert user1_verify.status_code == 200
        assert user1_verify.json()["allocation_pct"] == user1_new_allocation


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
