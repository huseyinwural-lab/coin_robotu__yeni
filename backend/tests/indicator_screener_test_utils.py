import os
import uuid
from pathlib import Path

import requests


def resolve_base_url() -> str:
    env_base = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if env_base:
        return env_base
    env_file = Path("/app/frontend/.env")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL bulunamadı")


def admin_headers(base_url: str) -> dict:
    response = requests.post(
        f"{base_url}/api/auth/login/admin",
        json={"email": "admin@platform.dev", "password": "Admin12345!"},
        timeout=20,
    )
    assert response.status_code == 200, response.text
    token = response.json().get("access_token")
    assert token
    return {"Authorization": f"Bearer {token}"}


def ensure_user_headers(base_url: str, *, suffix: str) -> dict:
    email = f"indicator.screener.{suffix}@platform.dev"
    password = "User12345!"

    login = requests.post(
        f"{base_url}/api/auth/login/user",
        json={"email": email, "password": password},
        timeout=20,
    )
    if login.status_code == 200:
        token = login.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}

    register = requests.post(
        f"{base_url}/api/auth/register",
        json={"email": email, "password": password},
        timeout=20,
    )
    if register.status_code not in [200, 400]:
        raise AssertionError(register.text)

    admin = admin_headers(base_url)
    pending = requests.get(
        f"{base_url}/api/auth/admin/user-approval-requests",
        params={"status": "pending"},
        headers=admin,
        timeout=20,
    )
    assert pending.status_code == 200, pending.text
    for row in pending.json():
        if row.get("email") == email:
            approve = requests.post(
                f"{base_url}/api/auth/admin/user-approval-requests/{row['id']}/approve",
                headers=admin,
                timeout=20,
            )
            assert approve.status_code == 200, approve.text
            break

    login2 = requests.post(
        f"{base_url}/api/auth/login/user",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert login2.status_code == 200, login2.text
    token = login2.json().get("access_token")
    assert token
    return {"Authorization": f"Bearer {token}"}


def random_suffix() -> str:
    return uuid.uuid4().hex[:8]
