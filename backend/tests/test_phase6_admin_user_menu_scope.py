import os
import random
import string

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"


def _unique_email(prefix: str) -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    return f"{prefix}_{suffix}@example.com"


def _admin_token() -> str:
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _register(email: str, password: str) -> dict:
    response = requests.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()


class TestPhase6AdminUserScopes:
    def test_admin_scope_lists_only_admin_roles(self):
        token = _admin_token()
        create_email = _unique_email("newadmin")
        create_payload = {"email": create_email, "password": "AdminCreate123!", "role": "admin"}

        create_response = requests.post(
            f"{BASE_URL}/api/admin/users/admin-create",
            headers={"Authorization": f"Bearer {token}"},
            json=create_payload,
        )
        assert create_response.status_code == 201
        assert create_response.json()["role"] == "admin"

        list_response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers={"Authorization": f"Bearer {token}"},
            params={"scope": "admin"},
        )
        assert list_response.status_code == 200
        rows = list_response.json()
        roles = {row["role"] for row in rows}
        assert roles.issubset({"super_admin", "admin", "ops"})
        assert any(row["email"] == create_email for row in rows)

    def test_user_scope_lists_approved_users(self):
        token = _admin_token()

        pending_email = _unique_email("pendinguser")
        approved_email = _unique_email("approveduser")
        password = "UserScope123!"

        _register(pending_email, password)
        approved_user = _register(approved_email, password)

        approve_response = requests.post(
            f"{BASE_URL}/api/auth/admin/user-approval-requests/{approved_user['id']}/approve",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert approve_response.status_code == 200

        list_response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers={"Authorization": f"Bearer {token}"},
            params={"scope": "user"},
        )
        assert list_response.status_code == 200
        rows = list_response.json()

        emails = {row["email"] for row in rows}
        assert approved_email in emails
        assert pending_email not in emails
        assert all(row["role"] == "user" for row in rows)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])