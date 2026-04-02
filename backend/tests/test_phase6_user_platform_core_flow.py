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


def _unique_email(prefix: str = "phase6core") -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    return f"{prefix}_{suffix}@example.com"


def _register(email: str, password: str) -> dict:
    response = requests.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()


def _admin_token() -> str:
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _approve_user(user_id: str, admin_token: str):
    response = requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200


def _login_user(email: str, password: str) -> str:
    response = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


class TestPhase6UserPlatformCoreFlow:
    def test_user_platform_core_sequence(self):
        email = _unique_email("userflow")
        password = "UserFlow123!"
        user = _register(email, password)

        admin_token = _admin_token()
        _approve_user(user["id"], admin_token)
        user_token = _login_user(email, password)
        headers = {"Authorization": f"Bearer {user_token}"}

        connect_response = requests.post(
            f"{BASE_URL}/api/user/exchange/connect",
            headers=headers,
            json={
                "exchange": "binance",
                "mode": "live",
                "api_key": "FAKE_API_KEY_123456",
                "api_secret": "FAKE_API_SECRET_654321",
            },
        )
        assert connect_response.status_code == 200, connect_response.text
        connect_data = connect_response.json()
        assert connect_data["has_api_key"] is True
        assert connect_data["has_api_secret"] is True
        assert connect_data["masked_api_key"] != "FAKE_API_KEY_123456"
        assert "***" in connect_data["masked_api_key"]

        map_response = requests.post(
            f"{BASE_URL}/api/user/portfolio/map",
            headers=headers,
            json={"market_type": "futures", "leverage": 3, "margin_mode": "cross", "position_side": "BOTH"},
        )
        assert map_response.status_code == 200, map_response.text
        map_data = map_response.json()
        assert map_data["market_type"] == "futures"
        assert map_data["current_capital"] >= 0
        assert "allocation_capital" in map_data

        risk_response = requests.put(
            f"{BASE_URL}/api/user/risk-settings",
            headers=headers,
            json={
                "allocation_pct": 25,
                "trade_risk_pct": 12,
                "daily_loss_limit_pct": 4,
                "compounding_enabled": True,
            },
        )
        assert risk_response.status_code == 200, risk_response.text
        risk_data = risk_response.json()
        assert risk_data["allocation_pct"] == 25
        assert risk_data["trade_risk_pct"] == 12

        portfolio_response = requests.get(f"{BASE_URL}/api/user/portfolio", headers=headers)
        assert portfolio_response.status_code == 200
        assert "current_capital" in portfolio_response.json()

        performance_response = requests.get(f"{BASE_URL}/api/user/performance", headers=headers)
        assert performance_response.status_code == 200
        assert "win_rate" in performance_response.json()

        trades_response = requests.get(f"{BASE_URL}/api/user/trades", headers=headers)
        assert trades_response.status_code == 200
        assert isinstance(trades_response.json(), list)

    def test_user_only_and_isolated_scope(self):
        password = "Isolation123!"
        user1 = _register(_unique_email("iso_a"), password)
        user2 = _register(_unique_email("iso_b"), password)

        admin_token = _admin_token()
        _approve_user(user1["id"], admin_token)
        _approve_user(user2["id"], admin_token)

        user1_token = _login_user(user1["email"], password)
        user2_token = _login_user(user2["email"], password)

        user1_headers = {"Authorization": f"Bearer {user1_token}"}
        user2_headers = {"Authorization": f"Bearer {user2_token}"}

        update_user1 = requests.put(
            f"{BASE_URL}/api/user/risk-settings",
            headers=user1_headers,
            json={
                "allocation_pct": 33,
                "trade_risk_pct": 11,
                "daily_loss_limit_pct": 4,
                "compounding_enabled": False,
            },
        )
        assert update_user1.status_code == 200

        user2_settings = requests.get(f"{BASE_URL}/api/user/risk-settings", headers=user2_headers)
        assert user2_settings.status_code == 200
        assert user2_settings.json()["allocation_pct"] != 33

        admin_access = requests.get(
            f"{BASE_URL}/api/user/portfolio",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert admin_access.status_code == 403


if __name__ == "__main__":
    pytest.main([__file__, "-v"])