import requests


BASE_URL = "https://trade-platform-s3.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@platform.local"
ADMIN_PASSWORD = "Admin12345!"
USER_EMAIL = "testuser1773706589@example.com"
USER_PASSWORD = "TestPassword123!"


def _ensure_user_login_token() -> str:
    login = requests.post(
        f"{BASE_URL}/auth/login/user",
        json={"email": USER_EMAIL, "password": USER_PASSWORD},
        timeout=20,
    )
    if login.status_code == 200:
        token = login.json().get("access_token")
        assert token
        return token

    requests.post(
        f"{BASE_URL}/auth/register",
        json={"email": USER_EMAIL, "password": USER_PASSWORD, "role": "user"},
        timeout=20,
    )

    admin_login = requests.post(
        f"{BASE_URL}/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert admin_login.status_code == 200
    admin_token = admin_login.json().get("access_token")
    assert admin_token

    pending = requests.get(
        f"{BASE_URL}/auth/admin/user-approval-requests",
        headers={"Authorization": f"Bearer {admin_token}"},
        params={"status": "pending"},
        timeout=20,
    )
    assert pending.status_code == 200
    target_user = next((row for row in pending.json() if row.get("email") == USER_EMAIL), None)
    if target_user:
        approve = requests.post(
            f"{BASE_URL}/auth/admin/user-approval-requests/{target_user['id']}/approve",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=20,
        )
        assert approve.status_code == 200

    retry = requests.post(
        f"{BASE_URL}/auth/login/user",
        json={"email": USER_EMAIL, "password": USER_PASSWORD},
        timeout=20,
    )
    assert retry.status_code == 200
    token = retry.json().get("access_token")
    assert token
    return token


def test_prod_gate_health_ok():
    response = requests.get(f"{BASE_URL}/health", timeout=20)
    assert response.status_code == 200
    assert response.json().get("status") == "ok"


def test_prod_gate_admin_login_ok():
    response = requests.post(
        f"{BASE_URL}/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("access_token")


def test_prod_gate_user_login_and_readiness_checklist_ok():
    token = _ensure_user_login_token()

    response = requests.get(
        f"{BASE_URL}/exchange/readiness-checklist",
        headers={"Authorization": f"Bearer {token}"},
        params={"exchange": "binance", "market_type": "futures", "environment": "testnet"},
        timeout=25,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("exchange") == "binance"
    assert payload.get("market_type") == "futures"
