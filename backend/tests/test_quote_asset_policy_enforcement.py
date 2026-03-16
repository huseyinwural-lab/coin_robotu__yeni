import os
import sys
import uuid
from pathlib import Path

import pytest
import requests

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.quote_asset_policy import is_allowed_quote_symbol


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
    assert response.status_code == 200, f"admin login failed: {response.text}"
    token = response.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


def _new_user_headers() -> dict:
    email = f"quote_policy_{uuid.uuid4().hex[:8]}@example.com"
    password = "QuotePolicy123!"
    register = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert register.status_code == 200, register.text
    user_id = register.json().get("id")
    approve = requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers=_admin_headers(),
        timeout=20,
    )
    assert approve.status_code == 200, approve.text
    login = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert login.status_code == 200, login.text
    token = login.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def user_headers():
    return _new_user_headers()


def _base_preview_payload() -> dict:
    return {
        "source_type": "scanner",
        "source_ref_id": "scanner-row-policy",
        "market_type": "spot",
        "symbol": "ETHUSDT",
        "side": "buy",
        "order_type": "market",
        "position_size_mode": "fixed_notional",
        "position_size_value": 20,
        "take_profit_mode": "percent",
        "take_profit_value": 2,
        "stop_loss_mode": "percent",
        "stop_loss_value": 1,
        "execution_mode": "signal_follow",
        "strategy_binding": "spot_pullback_v1",
        "signal": "long",
        "score": 82,
        "confidence": 0.73,
        "timestamp": "2026-03-16T00:00:00Z",
        "scanner_signal_snapshot": {
            "symbol": "ETHUSDT",
            "signal": "long",
            "score": 82,
            "strategy": "spot_pullback_v1",
            "confidence": 0.73,
            "timestamp": "2026-03-16T00:00:00Z",
        },
    }


def test_only_usdt_usdc_pairs_allowed():
    assert is_allowed_quote_symbol("ETHUSDT") is True
    assert is_allowed_quote_symbol("SOLUSDC") is True
    assert is_allowed_quote_symbol("ETHBTC") is False
    assert is_allowed_quote_symbol("BTCBUSD") is False


def test_btc_fallback_rejected(user_headers):
    payload = _base_preview_payload()
    payload["symbol"] = ""
    response = requests.post(f"{BASE_URL}/api/v1/user/trading/preview", headers=user_headers, json=payload, timeout=30)
    assert response.status_code == 400, response.text
    assert "symbol_required_for_execution_intent" in response.text


def test_scanner_execution_symbol_integrity(user_headers):
    payload = _base_preview_payload()
    payload["symbol"] = "ETHUSDT"
    payload["scanner_signal_snapshot"]["symbol"] = "SOLUSDT"
    response = requests.post(f"{BASE_URL}/api/v1/user/trading/preview", headers=user_headers, json=payload, timeout=30)
    assert response.status_code == 400, response.text
    assert "scanner_execution_symbol_mismatch" in response.text


def test_invalid_quote_asset_rejected(user_headers):
    payload = _base_preview_payload()
    payload["symbol"] = "ETHBTC"
    payload["scanner_signal_snapshot"]["symbol"] = "ETHBTC"
    response = requests.post(f"{BASE_URL}/api/v1/user/trading/preview", headers=user_headers, json=payload, timeout=30)
    assert response.status_code == 400, response.text
    assert "invalid_quote_asset" in response.text