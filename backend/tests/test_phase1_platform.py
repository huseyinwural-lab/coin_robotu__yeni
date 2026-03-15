"""Phase 1 platform API regression tests: auth, role access, CRUD shells, audit, exchange mock."""

import os
import uuid

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    pytest.skip("REACT_APP_BACKEND_URL is required for public endpoint testing", allow_module_level=True)

API_BASE = f"{BASE_URL.rstrip('/')}/api"


@pytest.fixture(scope="session")
def api_client():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="session")
def admin_auth(api_client):
    payload = {"email": os.environ.get("TEST_ADMIN_EMAIL", ""), "password": os.environ.get("TEST_ADMIN_PASSWORD", "")}
    response = api_client.post(f"{API_BASE}/auth/login", json=payload, timeout=20)
    if response.status_code != 200:
        pytest.skip(f"Admin login failed with status {response.status_code}")
    data = response.json()
    return {"token": data["access_token"], "user": data["user"]}


@pytest.fixture(scope="session")
def user_auth(api_client):
    unique = uuid.uuid4().hex[:8]
    email = f"test_user_{unique}@platform.dev"
    password = "Testing123!"

    register_response = api_client.post(
        f"{API_BASE}/auth/register",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert register_response.status_code == 200
    register_data = register_response.json()
    assert register_data["email"] == email
    assert register_data["role"] == "user"

    login_response = api_client.post(
        f"{API_BASE}/auth/login",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert login_response.status_code == 200
    login_data = login_response.json()
    return {"token": login_data["access_token"], "user": login_data["user"], "email": email}


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_auth_me_flow_user(api_client, user_auth):
    response = api_client.get(
        f"{API_BASE}/auth/me",
        headers=_auth_headers(user_auth["token"]),
        timeout=20,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == user_auth["email"]
    assert data["role"] == "user"
    assert isinstance(data["id"], str)


def test_role_access_user_blocked_from_admin_audit(api_client, user_auth):
    response = api_client.get(
        f"{API_BASE}/audit-logs",
        headers=_auth_headers(user_auth["token"]),
        timeout=20,
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Admin role required"


def test_role_access_admin_can_list_audit_logs(api_client, admin_auth):
    response = api_client.get(
        f"{API_BASE}/audit-logs",
        headers=_auth_headers(admin_auth["token"]),
        timeout=20,
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        first = data[0]
        assert "action" in first
        assert "severity" in first


def test_bot_profile_create_update_and_list_verify(api_client, user_auth):
    name = f"TEST_bot_{uuid.uuid4().hex[:6]}"
    create_payload = {
        "name": name,
        "exchange": "binance",
        "market_type": "spot",
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "strategy_type": "trend_following",
        "timeframe": "15m",
        "trend_timeframe": "1h",
        "leverage": 3,
        "is_enabled": True,
    }
    create_response = api_client.post(
        f"{API_BASE}/bot-profiles",
        headers=_auth_headers(user_auth["token"]),
        json=create_payload,
        timeout=20,
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["name"] == name
    assert created["symbols"] == ["BTCUSDT", "ETHUSDT"]

    update_payload = {**create_payload, "name": f"{name}_updated", "leverage": 5}
    update_response = api_client.put(
        f"{API_BASE}/bot-profiles/{created['id']}",
        headers=_auth_headers(user_auth["token"]),
        json=update_payload,
        timeout=20,
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["name"] == f"{name}_updated"
    assert updated["leverage"] == 5

    list_response = api_client.get(
        f"{API_BASE}/bot-profiles",
        headers=_auth_headers(user_auth["token"]),
        timeout=20,
    )
    assert list_response.status_code == 200
    rows = list_response.json()
    matched = [row for row in rows if row["id"] == created["id"]]
    assert len(matched) == 1
    assert matched[0]["name"] == f"{name}_updated"


def test_risk_policy_create_update_and_list_verify(api_client, user_auth):
    name = f"TEST_risk_{uuid.uuid4().hex[:6]}"
    create_payload = {
        "name": name,
        "position_size_pct": 2,
        "atr_stop_multiplier": 1.5,
        "risk_reward_ratio": 2.0,
        "daily_loss_cutoff_pct": 5,
        "max_open_positions": 3,
        "max_leverage": 3,
        "spread_limit_bps": 30,
        "slippage_limit_bps": 40,
        "min_liquidity_usdt": 100000,
    }
    create_response = api_client.post(
        f"{API_BASE}/risk-policies",
        headers=_auth_headers(user_auth["token"]),
        json=create_payload,
        timeout=20,
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["name"] == name

    update_payload = {**create_payload, "name": f"{name}_updated", "max_open_positions": 4}
    update_response = api_client.put(
        f"{API_BASE}/risk-policies/{created['id']}",
        headers=_auth_headers(user_auth["token"]),
        json=update_payload,
        timeout=20,
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["name"] == f"{name}_updated"
    assert updated["max_open_positions"] == 4

    list_response = api_client.get(
        f"{API_BASE}/risk-policies",
        headers=_auth_headers(user_auth["token"]),
        timeout=20,
    )
    assert list_response.status_code == 200
    rows = list_response.json()
    matched = [row for row in rows if row["id"] == created["id"]]
    assert len(matched) == 1
    assert matched[0]["name"] == f"{name}_updated"


def test_strategy_template_admin_create_update_and_user_list(api_client, admin_auth, user_auth):
    template_name = f"TEST_strategy_{uuid.uuid4().hex[:6]}"
    create_payload = {
        "name": template_name,
        "strategy_type": "trend_following",
        "parameters": {"ema_fast": 20, "ema_slow": 50},
        "is_active": True,
    }
    create_response = api_client.post(
        f"{API_BASE}/strategy-templates",
        headers=_auth_headers(admin_auth["token"]),
        json=create_payload,
        timeout=20,
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["name"] == template_name

    update_payload = {
        "name": f"{template_name}_v2",
        "strategy_type": "trend_following",
        "parameters": {"ema_fast": 21, "ema_slow": 55},
        "is_active": True,
    }
    update_response = api_client.put(
        f"{API_BASE}/strategy-templates/{created['id']}",
        headers=_auth_headers(admin_auth["token"]),
        json=update_payload,
        timeout=20,
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["name"] == f"{template_name}_v2"
    assert updated["parameters"]["ema_fast"] == 21

    user_list_response = api_client.get(
        f"{API_BASE}/strategy-templates",
        headers=_auth_headers(user_auth["token"]),
        timeout=20,
    )
    assert user_list_response.status_code == 200
    rows = user_list_response.json()
    matched = [row for row in rows if row["id"] == created["id"]]
    assert len(matched) == 1
    assert matched[0]["name"] == f"{template_name}_v2"


def test_strategy_template_user_create_forbidden(api_client, user_auth):
    payload = {
        "name": f"TEST_user_forbidden_{uuid.uuid4().hex[:6]}",
        "strategy_type": "breakout",
        "parameters": {"atr": 14},
        "is_active": True,
    }
    response = api_client.post(
        f"{API_BASE}/strategy-templates",
        headers=_auth_headers(user_auth["token"]),
        json=payload,
        timeout=20,
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Admin role required"


def test_exchange_mock_execute_and_events_flow(api_client, user_auth):
    bot_payload = {
        "name": f"TEST_exchange_bot_{uuid.uuid4().hex[:6]}",
        "exchange": "binance",
        "market_type": "spot",
        "symbols": ["BTCUSDT"],
        "strategy_type": "trend_following",
        "timeframe": "15m",
        "trend_timeframe": "1h",
        "leverage": 2,
        "is_enabled": True,
    }
    bot_response = api_client.post(
        f"{API_BASE}/bot-profiles",
        headers=_auth_headers(user_auth["token"]),
        json=bot_payload,
        timeout=20,
    )
    assert bot_response.status_code == 200
    bot_id = bot_response.json()["id"]

    execute_response = api_client.post(
        f"{API_BASE}/exchange/mock/execute",
        headers=_auth_headers(user_auth["token"]),
        json={"bot_profile_id": bot_id, "symbol": "BTCUSDT", "side": "buy", "quantity": 0.01},
        timeout=20,
    )
    assert execute_response.status_code == 200
    executed = execute_response.json()
    assert executed["bot_profile_id"] == bot_id
    assert executed["execution_status"] == "filled"
    assert executed["response_payload"]["mode"] == "mock"

    state_response = api_client.get(
        f"{API_BASE}/exchange/mock/state",
        headers=_auth_headers(user_auth["token"]),
        timeout=20,
    )
    assert state_response.status_code == 200
    state = state_response.json()
    assert state["adapter"]["mode"] == "mock"
    assert state["viewer_role"] == "user"

    events_response = api_client.get(
        f"{API_BASE}/exchange/mock/events",
        headers=_auth_headers(user_auth["token"]),
        timeout=20,
    )
    assert events_response.status_code == 200
    events = events_response.json()
    matched = [event for event in events if event["id"] == executed["id"]]
    assert len(matched) == 1
    assert matched[0]["symbol"] == "BTCUSDT"
