"""Phase 2-b pipeline spine API tests: admin universe, pipeline lifecycle, monitoring, signals, paper positions, audit chain."""

import os
import time
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


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def admin_auth(api_client):
    response = api_client.post(
        f"{API_BASE}/auth/login",
        json={"email": "admin@platform.dev", "password": "Admin12345!"},
        timeout=25,
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code}")
    data = response.json()
    return {"token": data["access_token"], "user": data["user"]}


@pytest.fixture(scope="session")
def user_auth(api_client):
    unique = uuid.uuid4().hex[:8]
    email = f"phase2_user_{unique}@platform.dev"
    password = "Testing123!"

    register = api_client.post(
        f"{API_BASE}/auth/register",
        json={"email": email, "password": password},
        timeout=25,
    )
    assert register.status_code == 200
    assert register.json()["email"] == email

    login = api_client.post(
        f"{API_BASE}/auth/login",
        json={"email": email, "password": password},
        timeout=25,
    )
    assert login.status_code == 200
    payload = login.json()
    return {"token": payload["access_token"], "user": payload["user"], "email": email}


@pytest.fixture(scope="session")
def user_risk_policy(api_client, user_auth):
    # module: risk policy prerequisite for pipeline risk engine
    payload = {
        "name": f"TEST_phase2_policy_{uuid.uuid4().hex[:6]}",
        "position_size_pct": 2,
        "atr_stop_multiplier": 1.4,
        "risk_reward_ratio": 2.0,
        "daily_loss_cutoff_pct": 5,
        "max_open_positions": 2,
        "max_leverage": 3,
        "spread_limit_bps": 45,
        "slippage_limit_bps": 50,
        "min_liquidity_usdt": 100000,
    }
    response = api_client.post(
        f"{API_BASE}/risk-policies",
        headers=_auth_headers(user_auth["token"]),
        json=payload,
        timeout=25,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == payload["name"]
    return data


@pytest.fixture(scope="session")
def user_bot(api_client, user_auth):
    # module: bot profile prerequisite for start/stop and pipeline routing
    payload = {
        "name": f"TEST_phase2_bot_{uuid.uuid4().hex[:6]}",
        "exchange": "binance",
        "market_type": "spot",
        "symbols": ["BTCUSDT"],
        "strategy_type": "mean_reversion",
        "timeframe": "15m",
        "trend_timeframe": "1h",
        "leverage": 2,
        "is_enabled": True,
    }
    response = api_client.post(
        f"{API_BASE}/bot-profiles",
        headers=_auth_headers(user_auth["token"]),
        json=payload,
        timeout=25,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == payload["name"]
    assert data["symbols"] == ["BTCUSDT"]
    return data


def _wait_until(assertion_callback, timeout_sec=70, interval_sec=5):
    deadline = time.time() + timeout_sec
    last_value = None
    while time.time() < deadline:
        last_value = assertion_callback()
        if last_value:
            return last_value
        time.sleep(interval_sec)
    return last_value


def test_admin_control_get_put_and_universe_preview(api_client, admin_auth):
    # module: admin control universe management
    headers = _auth_headers(admin_auth["token"])
    original_response = api_client.get(f"{API_BASE}/admin-control", headers=headers, timeout=25)
    assert original_response.status_code == 200
    original = original_response.json()
    assert original["id"] == "global"

    update_payload = {
        "max_leverage_cap": 4,
        "max_open_positions_cap": 8,
        "minimum_volume_usd": 500000,
        "max_spread_bps": 55,
        "spot_universe": ["BTCUSDT", "ETHUSDT", "BNBUSDT"],
        "futures_universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        "whitelist": ["BTCUSDT", "ETHUSDT"],
        "blacklist": ["ETHUSDT"],
        "emergency_mode": False,
        "disable_futures": False,
    }
    put_response = api_client.put(f"{API_BASE}/admin-control", headers=headers, json=update_payload, timeout=25)
    assert put_response.status_code == 200
    updated = put_response.json()
    assert updated["max_leverage_cap"] == 4
    assert updated["whitelist"] == ["BTCUSDT", "ETHUSDT"]
    assert updated["blacklist"] == ["ETHUSDT"]

    preview_response = api_client.get(f"{API_BASE}/admin-control/universe/preview", headers=headers, timeout=25)
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["filters"]["max_spread_bps"] == 55
    assert isinstance(preview["spot_symbols"], list)
    assert "ETHUSDT" not in preview["spot_symbols"]


def test_pipeline_bot_start_stop_lifecycle(api_client, user_auth, user_bot):
    # module: pipeline bot lifecycle controls
    headers = _auth_headers(user_auth["token"])
    start_response = api_client.post(f"{API_BASE}/pipeline/bots/{user_bot['id']}/start", headers=headers, timeout=25)
    assert start_response.status_code == 200
    started = start_response.json()
    assert started["id"] == user_bot["id"]
    assert started["is_running"] is True

    list_response = api_client.get(f"{API_BASE}/bot-profiles", headers=headers, timeout=25)
    assert list_response.status_code == 200
    listed = [item for item in list_response.json() if item["id"] == user_bot["id"]][0]
    assert listed["is_running"] is True

    stop_response = api_client.post(f"{API_BASE}/pipeline/bots/{user_bot['id']}/stop", headers=headers, timeout=25)
    assert stop_response.status_code == 200
    stopped = stop_response.json()
    assert stopped["is_running"] is False


def test_pipeline_monitoring_admin_only(api_client, admin_auth, user_auth):
    # module: pipeline monitoring endpoint
    admin_response = api_client.get(
        f"{API_BASE}/pipeline/monitoring",
        headers=_auth_headers(admin_auth["token"]),
        timeout=25,
    )
    assert admin_response.status_code == 200
    metrics = admin_response.json()
    assert "websocket_status" in metrics
    assert isinstance(metrics["signal_rate_last_5m"], int)
    assert isinstance(metrics["active_bots_running"], int)

    user_response = api_client.get(
        f"{API_BASE}/pipeline/monitoring",
        headers=_auth_headers(user_auth["token"]),
        timeout=25,
    )
    assert user_response.status_code == 403
    assert user_response.json()["detail"] == "Admin role required"


def test_signals_risk_rejection_and_paper_position_chain(api_client, admin_auth, user_auth, user_risk_policy, user_bot):
    # module: market -> signal -> risk -> paper execution -> position chain + audit
    admin_headers = _auth_headers(admin_auth["token"])
    user_headers = _auth_headers(user_auth["token"])

    api_client.post(f"{API_BASE}/pipeline/bots/{user_bot['id']}/start", headers=user_headers, timeout=25)

    emergency_payload = {
        "max_leverage_cap": 5,
        "max_open_positions_cap": 10,
        "minimum_volume_usd": 100000,
        "max_spread_bps": 80,
        "spot_universe": ["BTCUSDT", "ETHUSDT", "BNBUSDT"],
        "futures_universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        "whitelist": [],
        "blacklist": [],
        "emergency_mode": True,
        "disable_futures": False,
    }
    emergency_set = api_client.put(f"{API_BASE}/admin-control", headers=admin_headers, json=emergency_payload, timeout=25)
    assert emergency_set.status_code == 200
    assert emergency_set.json()["emergency_mode"] is True

    def _fetch_signals_for_bot():
        response = api_client.get(f"{API_BASE}/pipeline/signals?limit=100", headers=user_headers, timeout=25)
        if response.status_code != 200:
            return []
        rows = response.json()
        return [row for row in rows if row["bot_profile_id"] == user_bot["id"]]

    signals_for_bot = _wait_until(_fetch_signals_for_bot, timeout_sec=80, interval_sec=5)
    assert signals_for_bot and len(signals_for_bot) > 0
    first_signal = signals_for_bot[0]
    assert first_signal["signal"] in ["long", "short", "none"]
    assert isinstance(first_signal["reason_codes"], list)

    logs_after_emergency = api_client.get(f"{API_BASE}/audit-logs?limit=300", headers=admin_headers, timeout=25)
    assert logs_after_emergency.status_code == 200
    emergency_actions = [log["action"] for log in logs_after_emergency.json()]
    assert "risk_rejection" in emergency_actions

    normal_payload = {**emergency_payload, "emergency_mode": False}
    normal_set = api_client.put(f"{API_BASE}/admin-control", headers=admin_headers, json=normal_payload, timeout=25)
    assert normal_set.status_code == 200
    assert normal_set.json()["emergency_mode"] is False

    def _fetch_open_positions_for_user():
        response = api_client.get(f"{API_BASE}/paper-positions", headers=user_headers, timeout=25)
        if response.status_code != 200:
            return []
        return [pos for pos in response.json() if pos["user_id"] == user_auth["user"]["id"] and pos["status"] == "open"]

    open_positions = _wait_until(_fetch_open_positions_for_user, timeout_sec=90, interval_sec=5)
    assert open_positions and len(open_positions) > 0

    position_id = open_positions[0]["id"]
    manual_close = api_client.post(
        f"{API_BASE}/paper-positions/{position_id}/manual-close",
        headers=user_headers,
        json={"reason": "manual_close"},
        timeout=25,
    )
    assert manual_close.status_code == 200
    closed = manual_close.json()
    assert closed["id"] == position_id
    assert closed["status"] == "manual_close"

    logs_after_close = api_client.get(f"{API_BASE}/audit-logs?limit=300", headers=admin_headers, timeout=25)
    assert logs_after_close.status_code == 200
    actions = [log["action"] for log in logs_after_close.json()]
    assert "trade_open" in actions
    assert "trade_close" in actions
