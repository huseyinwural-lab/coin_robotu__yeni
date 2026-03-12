import os
import random
import string
from pathlib import Path

import pytest
import requests

ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"


def _resolve_base_url() -> str:
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if direct:
        return direct

    env_file = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        if raw_line.strip().startswith("REACT_APP_BACKEND_URL="):
            return raw_line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


BASE_URL = _resolve_base_url()


def _random_email(prefix: str = "phase8") -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{prefix}_{suffix}@example.com"


@pytest.fixture(scope="module")
def auth_context():
    email = _random_email()
    password = "Phase8Explain123!"

    register = requests.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": password}, timeout=20)
    assert register.status_code == 200
    user_id = register.json()["id"]

    admin_login = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["access_token"]

    approve = requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=20,
    )
    assert approve.status_code == 200

    user_login = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert user_login.status_code == 200
    user_token = user_login.json()["access_token"]

    return {
        "user_headers": {"Authorization": f"Bearer {user_token}"},
        "admin_headers": {"Authorization": f"Bearer {admin_token}"},
    }


def _run_scanner(user_headers: dict) -> None:
    response = requests.post(
        f"{BASE_URL}/api/user/scanner/run",
        headers=user_headers,
        json={"mode": "ASSISTED", "max_results": 20},
        timeout=20,
    )
    assert response.status_code == 200


def _latest_signal(user_headers: dict) -> dict:
    response = requests.get(
        f"{BASE_URL}/api/user/signals",
        headers=user_headers,
        params={"limit": 100},
        timeout=20,
    )
    assert response.status_code == 200
    rows = response.json()
    assert isinstance(rows, list)
    assert rows
    return rows[0]


def test_phase8_signal_decision_trace_endpoint(auth_context):
    _run_scanner(auth_context["user_headers"])
    signal = _latest_signal(auth_context["user_headers"])

    trace_response = requests.get(
        f"{BASE_URL}/api/user/signals/{signal['id']}/decision-trace",
        headers=auth_context["user_headers"],
        timeout=20,
    )
    assert trace_response.status_code == 200
    payload = trace_response.json()
    assert payload["entity_scope"] == "signal"
    assert payload["trace_count"] >= 1
    assert payload["latest_trace"]["trace_scope"] == "signal"
    assert isinstance(payload["latest_trace"]["reason_details"], list)


def test_phase8_trade_trace_after_signal_approval(auth_context):
    _run_scanner(auth_context["user_headers"])
    response = requests.get(
        f"{BASE_URL}/api/user/signals",
        headers=auth_context["user_headers"],
        params={"limit": 100},
        timeout=20,
    )
    assert response.status_code == 200
    pending = [row for row in response.json() if row.get("status") == "pending"]
    if not pending:
        pytest.skip("Pending signal bulunamadı")

    approve = requests.post(
        f"{BASE_URL}/api/user/signal/{pending[0]['id']}/approve",
        headers=auth_context["user_headers"],
        json={"note": "phase8_test_approve"},
        timeout=20,
    )
    assert approve.status_code == 200
    trade_id = approve.json().get("order_position_id")
    assert trade_id

    trade_trace = requests.get(
        f"{BASE_URL}/api/user/trades/{trade_id}/decision-trace",
        headers=auth_context["user_headers"],
        timeout=20,
    )
    assert trade_trace.status_code == 200
    payload = trade_trace.json()
    assert payload["entity_scope"] == "trade"
    assert payload["trace_count"] >= 1
    assert payload["latest_trace"]["trace_scope"] == "trade"


def test_phase8_execution_trace_strategy_explain_and_coverage(auth_context):
    preview_payload = {
        "source_type": "manual",
        "source_ref_id": "",
        "market_type": "spot",
        "symbol": "BTCUSDT",
        "side": "buy",
        "order_type": "market",
        "position_size_mode": "fixed_notional",
        "position_size_value": 30,
        "take_profit_mode": "percent",
        "take_profit_value": 2,
        "stop_loss_mode": "percent",
        "stop_loss_value": 1,
        "execution_mode": "manual",
        "strategy_binding": "spot_pullback_v1",
        "holding_profile": "intraday",
    }
    preview = requests.post(
        f"{BASE_URL}/api/user/execution/intent/preview",
        headers=auth_context["user_headers"],
        json=preview_payload,
        timeout=20,
    )
    assert preview.status_code == 200
    intent_id = preview.json()["intent_id"]

    execution_trace = requests.get(
        f"{BASE_URL}/api/user/execution/intents/{intent_id}/decision-trace",
        headers=auth_context["user_headers"],
        timeout=20,
    )
    assert execution_trace.status_code == 200
    execution_trace_payload = execution_trace.json()
    assert execution_trace_payload["entity_scope"] == "execution"
    assert execution_trace_payload["trace_count"] >= 1

    strategy_explain = requests.get(
        f"{BASE_URL}/api/user/strategies/spot_pullback_v1/explain",
        headers=auth_context["user_headers"],
        params={"lookback_days": 30},
        timeout=20,
    )
    assert strategy_explain.status_code == 200
    strategy_payload = strategy_explain.json()
    assert strategy_payload["strategy_code"] == "spot_pullback_v1"
    assert "decision_distribution" in strategy_payload
    assert "top_reason_codes" in strategy_payload

    coverage = requests.get(
        f"{BASE_URL}/api/user/explainability/coverage",
        headers=auth_context["user_headers"],
        params={"days": 7},
        timeout=20,
    )
    assert coverage.status_code == 200
    coverage_payload = coverage.json()
    assert coverage_payload["window_days"] == 7
    scopes = {item["scope"] for item in coverage_payload["scopes"]}
    assert {"signal", "trade", "execution"}.issubset(scopes)
