import os
import random
import string
from pathlib import Path

import requests

ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")


def _base_url() -> str:
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if direct:
        return direct
    env_file = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        if raw_line.startswith("REACT_APP_BACKEND_URL="):
            return raw_line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


def _random_email(prefix: str = "riskgate") -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{prefix}_{suffix}@example.com"


def _provision_user(base: str) -> dict:
    admin_login = requests.post(
        f"{base}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert admin_login.status_code == 200
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    email = _random_email()
    password = "RiskGate123!"
    register = requests.post(f"{base}/api/auth/register", json={"email": email, "password": password}, timeout=20)
    assert register.status_code == 200
    user_id = register.json()["id"]

    approve = requests.post(
        f"{base}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers=admin_headers,
        timeout=20,
    )
    assert approve.status_code == 200

    user_login = requests.post(
        f"{base}/api/auth/login/user",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert user_login.status_code == 200
    return {"Authorization": f"Bearer {user_login.json()['access_token']}"}


def test_execution_risk_gate_and_trace_fields():
    base = _base_url()
    user_headers = _provision_user(base)

    high_risk_preview = requests.post(
        f"{base}/api/user/execution/intent/preview",
        headers=user_headers,
        json={
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 150000,
            "take_profit_mode": "percent",
            "take_profit_value": 2,
            "stop_loss_mode": "percent",
            "stop_loss_value": 1,
            "execution_mode": "manual",
            "strategy_binding": "spot_pullback_v1",
        },
        timeout=20,
    )
    assert high_risk_preview.status_code == 200
    payload = high_risk_preview.json()
    assert payload["gate_decision"] in {"ALLOW", "ADJUST_POSITION", "REQUIRE_APPROVAL", "REJECT"}
    assert "portfolio_risk_impact" in payload
    assert payload["portfolio_risk_impact"]["risk_score"] >= 0
    assert payload["portfolio_risk_impact"]["current_portfolio_leverage"] >= 0

    trace = requests.get(
        f"{base}/api/user/execution/intents/{payload['intent_id']}/decision-trace",
        headers=user_headers,
        timeout=20,
    )
    assert trace.status_code == 200
    latest = trace.json()["latest_trace"]
    assert latest["portfolio_risk_score"] is not None
    assert "strategy_allocation_reason" in latest
    assert "meta_engine_decision" in latest
