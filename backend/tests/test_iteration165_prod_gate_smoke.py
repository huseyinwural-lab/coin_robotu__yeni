import requests


BASE_URL = "https://trade-flow-deploy.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@platform.local"
ADMIN_PASSWORD = "Admin12345!"
USER_EMAIL = "testuser1773706589@example.com"
USER_PASSWORD = "TestPassword123!"


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
    login = requests.post(
        f"{BASE_URL}/auth/login/user",
        json={"email": USER_EMAIL, "password": USER_PASSWORD},
        timeout=20,
    )
    assert login.status_code == 200
    token = login.json().get("access_token")
    assert token

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
