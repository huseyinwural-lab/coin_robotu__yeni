"""Phase 3 admin APIs + execution policy integration regression tests."""

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
    payload = response.json()
    return {"token": payload["access_token"], "user": payload["user"]}


@pytest.fixture(scope="session")
def user_auth(api_client):
    email = f"phase3_user_{uuid.uuid4().hex[:8]}@platform.dev"
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


def _wait_until(assertion_callback, timeout_sec=90, interval_sec=5):
    deadline = time.time() + timeout_sec
    last_value = None
    while time.time() < deadline:
        last_value = assertion_callback()
        if last_value:
            return last_value
        time.sleep(interval_sec)
    return last_value


def test_phase3_admin_endpoints_and_schema_reachable(api_client, admin_auth):
    # module: alembic startup path + phase3 table reachability via admin endpoints
    headers = _auth_headers(admin_auth["token"])

    root_response = api_client.get(f"{API_BASE}/", timeout=25)
    assert root_response.status_code == 200
    assert root_response.json()["phase"] == "3-iter1"

    for endpoint in [
        "/admin-phase3/execution-policies",
        "/admin-phase3/exposure-groups",
        "/admin-phase3/failed-events",
        "/admin-phase3/state-rebuild-logs",
        "/admin-phase3/backtest-cards",
    ]:
        response = api_client.get(f"{API_BASE}{endpoint}", headers=headers, timeout=25)
        assert response.status_code == 200
        assert isinstance(response.json(), list)


def test_execution_policy_create_update_and_list(api_client, admin_auth):
    # module: admin phase3 execution policy list/create/update
    headers = _auth_headers(admin_auth["token"])
    strategy = f"TEST_phase3_exec_{uuid.uuid4().hex[:6]}"
    create_payload = {
        "strategy_type": strategy,
        "execution_style": "balanced",
        "order_preference": "limit_first",
        "timeout_seconds": 9,
        "fallback_behavior": "market_fallback",
        "partial_fill_tolerance_pct": 55,
        "execution_urgency": "medium",
        "retry_limit": 2,
        "is_active": True,
    }
    create_response = api_client.post(
        f"{API_BASE}/admin-phase3/execution-policies",
        headers=headers,
        json=create_payload,
        timeout=25,
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["strategy_type"] == strategy
    assert created["execution_style"] == "balanced"

    update_payload = {**create_payload, "execution_style": "aggressive", "timeout_seconds": 6, "retry_limit": 1}
    update_response = api_client.put(
        f"{API_BASE}/admin-phase3/execution-policies/{created['id']}",
        headers=headers,
        json=update_payload,
        timeout=25,
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["execution_style"] == "aggressive"
    assert updated["timeout_seconds"] == 6

    list_response = api_client.get(f"{API_BASE}/admin-phase3/execution-policies", headers=headers, timeout=25)
    assert list_response.status_code == 200
    matches = [row for row in list_response.json() if row["id"] == created["id"]]
    assert len(matches) == 1
    assert matches[0]["retry_limit"] == 1


def test_exposure_group_create_update_and_list(api_client, admin_auth):
    # module: admin phase3 exposure groups list/create/update (single-group baseline)
    headers = _auth_headers(admin_auth["token"])
    name = f"test_group_{uuid.uuid4().hex[:6]}"
    create_payload = {
        "name": name,
        "label": "TEST single pool",
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "max_group_open_positions": 12,
        "max_group_directional_positions": 7,
        "max_group_risk_pct": 32,
    }
    create_response = api_client.post(
        f"{API_BASE}/admin-phase3/exposure-groups",
        headers=headers,
        json=create_payload,
        timeout=25,
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["name"] == name
    assert created["symbols"] == ["BTCUSDT", "ETHUSDT"]

    update_payload = {**create_payload, "symbols": ["BTCUSDT"], "max_group_risk_pct": 28}
    update_response = api_client.put(
        f"{API_BASE}/admin-phase3/exposure-groups/{created['id']}",
        headers=headers,
        json=update_payload,
        timeout=25,
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["symbols"] == ["BTCUSDT"]
    assert updated["max_group_risk_pct"] == 28

    list_response = api_client.get(f"{API_BASE}/admin-phase3/exposure-groups", headers=headers, timeout=25)
    assert list_response.status_code == 200
    matches = [row for row in list_response.json() if row["id"] == created["id"]]
    assert len(matches) == 1
    assert matches[0]["label"] == "TEST single pool"


def test_failed_events_list_retry_resolve(api_client, admin_auth):
    # module: admin phase3 failed events list + retry + resolve
    headers = _auth_headers(admin_auth["token"])
    list_response = api_client.get(f"{API_BASE}/admin-phase3/failed-events", headers=headers, timeout=25)
    assert list_response.status_code == 200
    rows = list_response.json()
    assert isinstance(rows, list)
    if not rows:
        pytest.skip("No failed events available in runtime for retry/resolve assertions")

    target = next((item for item in rows if item["status"] != "resolved"), rows[0])
    retry_response = api_client.post(
        f"{API_BASE}/admin-phase3/failed-events/{target['id']}/retry",
        headers=headers,
        timeout=25,
    )
    assert retry_response.status_code == 200
    retry_data = retry_response.json()
    assert retry_data["id"] == target["id"]
    assert retry_data["retry_count"] >= target["retry_count"]

    resolve_response = api_client.post(
        f"{API_BASE}/admin-phase3/failed-events/{target['id']}/resolve",
        headers=headers,
        timeout=25,
    )
    assert resolve_response.status_code == 200
    resolved = resolve_response.json()
    assert resolved["status"] == "resolved"


def test_state_rebuild_logs_and_manual_trigger(api_client, admin_auth):
    # module: admin phase3 state rebuild list + manual trigger
    headers = _auth_headers(admin_auth["token"])
    before_response = api_client.get(f"{API_BASE}/admin-phase3/state-rebuild-logs", headers=headers, timeout=25)
    assert before_response.status_code == 200
    before_count = len(before_response.json())

    trigger_response = api_client.post(f"{API_BASE}/admin-phase3/state-rebuild/run", headers=headers, timeout=25)
    assert trigger_response.status_code == 200
    triggered = trigger_response.json()
    assert triggered["trigger_source"] == "manual_admin"
    assert triggered["status"] == "completed"

    after_response = api_client.get(f"{API_BASE}/admin-phase3/state-rebuild-logs", headers=headers, timeout=25)
    assert after_response.status_code == 200
    rows = after_response.json()
    assert len(rows) >= before_count
    assert any(log["id"] == triggered["id"] for log in rows)


def test_backtest_cards_create_update_and_list(api_client, admin_auth):
    # module: admin phase3 backtest cards list/create/update
    headers = _auth_headers(admin_auth["token"])
    strategy = f"TEST_bt_{uuid.uuid4().hex[:6]}"
    create_payload = {
        "strategy_type": strategy,
        "market_type": "spot",
        "timeframe": "15m",
        "sample_size": 140,
        "win_rate": 57.4,
        "max_drawdown": 11.0,
        "profit_factor": 1.35,
        "sharpe_like_score": 0.92,
        "performance_summary": "TEST card baseline",
        "risk_label": "medium",
        "period_start": "2025-01-01",
        "period_end": "2025-12-31",
    }
    create_response = api_client.post(
        f"{API_BASE}/admin-phase3/backtest-cards",
        headers=headers,
        json=create_payload,
        timeout=25,
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["strategy_type"] == strategy
    assert created["win_rate"] == 57.4

    update_payload = {**create_payload, "win_rate": 61.2, "risk_label": "low"}
    update_response = api_client.put(
        f"{API_BASE}/admin-phase3/backtest-cards/{created['id']}",
        headers=headers,
        json=update_payload,
        timeout=25,
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["win_rate"] == 61.2
    assert updated["risk_label"] == "low"

    list_response = api_client.get(f"{API_BASE}/admin-phase3/backtest-cards", headers=headers, timeout=25)
    assert list_response.status_code == 200
    matches = [row for row in list_response.json() if row["id"] == created["id"]]
    assert len(matches) == 1
    assert matches[0]["profit_factor"] == 1.35


def test_execution_policy_payload_reflected_in_paper_execution_events(api_client, admin_auth, user_auth):
    # module: risk/execution policy integration reflected in paper execution payload
    admin_headers = _auth_headers(admin_auth["token"])
    user_headers = _auth_headers(user_auth["token"])

    policy_target = {
        "strategy_type": "trend_following",
        "execution_style": "passive",
        "order_preference": "limit_first",
        "timeout_seconds": 19,
        "fallback_behavior": "limit_retry_then_market",
        "partial_fill_tolerance_pct": 42,
        "execution_urgency": "low",
        "retry_limit": 4,
        "is_active": True,
    }

    policies_response = api_client.get(f"{API_BASE}/admin-phase3/execution-policies", headers=admin_headers, timeout=25)
    assert policies_response.status_code == 200
    existing = next((row for row in policies_response.json() if row["strategy_type"] == "trend_following"), None)

    if existing:
        upsert_response = api_client.put(
            f"{API_BASE}/admin-phase3/execution-policies/{existing['id']}",
            headers=admin_headers,
            json=policy_target,
            timeout=25,
        )
    else:
        upsert_response = api_client.post(
            f"{API_BASE}/admin-phase3/execution-policies",
            headers=admin_headers,
            json=policy_target,
            timeout=25,
        )
    assert upsert_response.status_code == 200

    risk_policy_payload = {
        "name": f"TEST_phase3_risk_{uuid.uuid4().hex[:6]}",
        "position_size_pct": 2,
        "atr_stop_multiplier": 1.4,
        "risk_reward_ratio": 2.0,
        "daily_loss_cutoff_pct": 6,
        "max_open_positions": 3,
        "max_leverage": 3,
        "spread_limit_bps": 80,
        "slippage_limit_bps": 50,
        "min_liquidity_usdt": 100000,
    }
    risk_response = api_client.post(
        f"{API_BASE}/risk-policies",
        headers=user_headers,
        json=risk_policy_payload,
        timeout=25,
    )
    assert risk_response.status_code == 200

    bot_payload = {
        "name": f"TEST_phase3_bot_{uuid.uuid4().hex[:6]}",
        "exchange": "binance",
        "market_type": "spot",
        "symbols": ["BTCUSDT"],
        "strategy_type": "trend_following",
        "timeframe": "15m",
        "trend_timeframe": "1h",
        "leverage": 2,
        "is_enabled": True,
    }
    bot_response = api_client.post(f"{API_BASE}/bot-profiles", headers=user_headers, json=bot_payload, timeout=25)
    assert bot_response.status_code == 200
    bot = bot_response.json()

    start_response = api_client.post(f"{API_BASE}/pipeline/bots/{bot['id']}/start", headers=user_headers, timeout=25)
    assert start_response.status_code == 200
    assert start_response.json()["is_running"] is True

    def _find_matching_execution_event():
        events_response = api_client.get(f"{API_BASE}/exchange/mock/events", headers=user_headers, timeout=25)
        if events_response.status_code != 200:
            return None
        events = events_response.json()
        for event in events:
            if event["bot_profile_id"] != bot["id"]:
                continue
            policy = event.get("response_payload", {}).get("execution_policy", {})
            if policy.get("timeout_seconds") == 19 and policy.get("retry_limit") == 4:
                return event
        return None

    matched_event = _wait_until(_find_matching_execution_event, timeout_sec=120, interval_sec=5)
    assert matched_event is not None
    policy_payload = matched_event["response_payload"]["execution_policy"]
    assert policy_payload["style"] == "passive"
    assert policy_payload["fallback_behavior"] == "limit_retry_then_market"
    assert policy_payload["partial_fill_tolerance_pct"] == 42
