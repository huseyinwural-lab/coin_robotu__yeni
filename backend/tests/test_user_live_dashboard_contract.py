import os
import uuid
from pathlib import Path

import pytest
import requests


def _resolve_base_url() -> str:
    env_base = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if env_base:
        return env_base
    frontend_env = Path("/app/frontend/.env")
    if frontend_env.exists():
        for line in frontend_env.read_text(encoding="utf-8").splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL bulunamadı")


BASE_URL = _resolve_base_url()
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@platform.local")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin12345!")


def _admin_headers() -> dict:
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _prepare_user() -> dict:
    admin_headers = _admin_headers()
    password = "UserLiveContract123!"
    email = f"contract_{uuid.uuid4().hex[:8]}@example.com"

    register = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert register.status_code == 200, register.text
    user_id = register.json()["id"]

    approve = requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers=admin_headers,
        timeout=20,
    )
    assert approve.status_code == 200, approve.text

    login = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    create_bot = requests.post(
        f"{BASE_URL}/api/bot-profiles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "contract-bot",
            "exchange": "binance",
            "market_type": "spot",
            "symbols": ["CONTRACTUSDT"],
            "strategy_type": "contract_strategy",
            "timeframe": "15m",
            "trend_timeframe": "1h",
            "leverage": 1,
            "is_enabled": True,
        },
        timeout=20,
    )
    assert create_bot.status_code == 200, create_bot.text

    return {"user_id": user_id, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture(scope="module")
def contract_context():
    return _prepare_user()


def test_user_live_contract_endpoints(contract_context):
    headers = contract_context["headers"]
    endpoint_expectations = [
        ("/api/user/live/summary", {"window": "1h"}, ["bots", "open_positions", "performance", "risk", "execution", "strategies", "trades", "alerts"]),
        ("/api/user/live/positions", None, ["positions_count", "total_unrealized_pnl", "positions"]),
        ("/api/user/live/performance", {"window": "24h"}, ["trades_today", "win_rate", "pnl_today", "avg_hold_time_minutes"]),
        ("/api/user/live/risk", {"window": "24h"}, ["risk_per_trade_used", "own_portfolio_exposure", "own_daily_loss_pct"]),
        ("/api/user/live/execution-quality", {"window": "24h"}, ["own_execution_quality_score", "avg_slippage", "avg_latency", "reject_rate"]),
        ("/api/user/live/strategies", {"window": "24h"}, ["strategy_count", "items"]),
        ("/api/user/live/trades", {"window": "24h"}, ["trades_count", "items"]),
        ("/api/user/live/daily-report", {"window": "24h"}, ["date", "trades_today", "top_strategies", "recent_trades", "alerts"]),
    ]

    for endpoint, params, required_keys in endpoint_expectations:
        response = requests.get(
            f"{BASE_URL}{endpoint}",
            params=params,
            headers=headers,
            timeout=30,
        )
        assert response.status_code == 200, f"{endpoint} failed: {response.text}"
        payload = response.json()
        for key in required_keys:
            assert key in payload, f"{endpoint} missing key: {key}"


def test_user_response_excludes_admin_scope_fields(contract_context):
    headers = contract_context["headers"]
    response = requests.get(
        f"{BASE_URL}/api/user/live/summary",
        params={"window": "6h"},
        headers=headers,
        timeout=30,
    )
    assert response.status_code == 200, response.text
    payload_text = str(response.json()).lower()

    forbidden_tokens = [
        "queue_depth",
        "fallback_state",
        "global",
        "cluster_exposure",
        "admin_risk_config",
        "kill_switch",
        "raw_diagnostics",
        "risk_veto_distribution",
    ]
    for token in forbidden_tokens:
        assert token not in payload_text, f"forbidden token leaked: {token}"