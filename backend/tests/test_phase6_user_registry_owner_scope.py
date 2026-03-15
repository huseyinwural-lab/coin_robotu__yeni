import os
import random
import string

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")


def _unique_email(prefix: str = "phase6") -> str:
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


class TestPhase6RegistryAndIsolation:
    def test_register_defaults(self):
        email = _unique_email("registry")
        password = "RegistryPass123!"
        payload = _register(email, password)

        assert payload["role"] == "user"
        assert payload["approval_status"] == "pending"
        assert payload["is_active"] is False

    def test_pending_user_blocked_from_login(self):
        email = _unique_email("pending")
        password = "PendingPass123!"
        _register(email, password)

        response = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": email, "password": password},
        )
        assert response.status_code == 403
        assert "onayı" in response.json().get("detail", "").lower()

    def test_owner_scope_enforced_between_users(self):
        user1_email = _unique_email("owner_a")
        user2_email = _unique_email("owner_b")
        password = "OwnerScope123!"

        user1 = _register(user1_email, password)
        user2 = _register(user2_email, password)

        admin_token = _admin_token()
        _approve_user(user1["id"], admin_token)
        _approve_user(user2["id"], admin_token)

        user1_token = _login_user(user1_email, password)
        user2_token = _login_user(user2_email, password)

        create_bot = requests.post(
            f"{BASE_URL}/api/bot-profiles",
            headers={"Authorization": f"Bearer {user1_token}"},
            json={
                "name": "Owner Scoped Bot",
                "exchange": "binance",
                "market_type": "spot",
                "symbols": ["BTCUSDT"],
                "strategy_type": "trend_following",
                "timeframe": "15m",
                "trend_timeframe": "1h",
                "leverage": 2,
                "is_enabled": True,
            },
        )
        assert create_bot.status_code == 200
        bot_id = create_bot.json()["id"]

        list_for_user2 = requests.get(
            f"{BASE_URL}/api/bot-profiles",
            headers={"Authorization": f"Bearer {user2_token}"},
        )
        assert list_for_user2.status_code == 200
        assert all(row["id"] != bot_id for row in list_for_user2.json())

        update_by_user2 = requests.put(
            f"{BASE_URL}/api/bot-profiles/{bot_id}",
            headers={"Authorization": f"Bearer {user2_token}"},
            json={
                "name": "Hijack Attempt",
                "exchange": "binance",
                "market_type": "spot",
                "symbols": ["ETHUSDT"],
                "strategy_type": "trend_following",
                "timeframe": "15m",
                "trend_timeframe": "1h",
                "leverage": 2,
                "is_enabled": True,
            },
        )
        assert update_by_user2.status_code == 404

        start_by_user2 = requests.post(
            f"{BASE_URL}/api/pipeline/bots/{bot_id}/start",
            headers={"Authorization": f"Bearer {user2_token}"},
        )
        assert start_by_user2.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])