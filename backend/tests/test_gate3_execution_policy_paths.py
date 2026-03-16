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
    assert response.status_code == 200, f"admin login failed: {response.text}"
    token = response.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


def _new_user_headers() -> dict:
    email = f"gate3_exec_{uuid.uuid4().hex[:8]}@example.com"
    password = "Gate3Exec123!"
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
    return {"Authorization": f"Bearer {login.json().get('access_token')}"}


def _base_payload() -> dict:
    return {
        "source_type": "scanner",
        "source_ref_id": "gate3-signal",
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
        "score": 81,
        "confidence": 0.72,
        "timestamp": "2026-03-16T00:00:00Z",
        "scanner_signal_snapshot": {
            "symbol": "ETHUSDT",
            "signal": "long",
            "score": 81,
            "strategy": "spot_pullback_v1",
            "confidence": 0.72,
            "timestamp": "2026-03-16T00:00:00Z",
        },
    }


@pytest.fixture(scope="module")
def user_headers():
    return _new_user_headers()


def test_trading_preview_rejects_invalid_quote_asset(user_headers):
    payload = _base_payload()
    payload["symbol"] = "ETHBTC"
    payload["scanner_signal_snapshot"]["symbol"] = "ETHBTC"
    response = requests.post(f"{BASE_URL}/api/v1/user/trading/preview", headers=user_headers, json=payload, timeout=30)
    assert response.status_code == 400, response.text
    assert "invalid_quote_asset" in response.text


def test_execution_preview_rejects_invalid_quote_asset(user_headers):
    payload = _base_payload()
    payload["symbol"] = "ETHBTC"
    payload["scanner_signal_snapshot"]["symbol"] = "ETHBTC"
    response = requests.post(f"{BASE_URL}/api/user/execution/intent/preview", headers=user_headers, json=payload, timeout=30)
    assert response.status_code == 400, response.text
    assert "invalid_quote_asset" in response.text


def test_both_preview_paths_reject_missing_symbol(user_headers):
    payload = _base_payload()
    payload["symbol"] = ""
    payload["scanner_signal_snapshot"]["symbol"] = ""

    trading_response = requests.post(f"{BASE_URL}/api/v1/user/trading/preview", headers=user_headers, json=payload, timeout=30)
    execution_response = requests.post(f"{BASE_URL}/api/user/execution/intent/preview", headers=user_headers, json=payload, timeout=30)

    assert trading_response.status_code == 400, trading_response.text
    assert execution_response.status_code == 400, execution_response.text
    assert "symbol_required_for_execution_intent" in trading_response.text
    assert "symbol_required_for_execution_intent" in execution_response.text


def test_normalized_payload_has_quote_asset(user_headers):
    """Test that /api/v1/user/trading/preview includes quote_asset in normalized payload."""
    payload = _base_payload()
    response = requests.post(f"{BASE_URL}/api/v1/user/trading/preview", headers=user_headers, json=payload, timeout=30)
    assert response.status_code == 200, response.text
    preview = response.json().get("preview") or {}
    normalized = preview.get("normalized_order_payload") or {}
    assert normalized.get("symbol") == "ETHUSDT"
    assert normalized.get("quote_asset") == "USDT"


def test_execution_preview_normalized_payload_has_quote_asset(user_headers):
    """Test that /api/user/execution/intent/preview includes quote_asset in normalized payload."""
    payload = _base_payload()
    response = requests.post(f"{BASE_URL}/api/user/execution/intent/preview", headers=user_headers, json=payload, timeout=30)
    assert response.status_code == 200, response.text
    normalized = response.json().get("normalized_order_payload") or {}
    assert normalized.get("symbol") == "ETHUSDT"
    assert normalized.get("quote_asset") == "USDT"


def test_scanner_snapshot_symbol_mismatch_rejected(user_headers):
    """Test that scanner_execution_symbol_mismatch is triggered when snapshot.symbol != payload.symbol."""
    payload = _base_payload()
    payload["symbol"] = "BTCUSDT"
    payload["scanner_signal_snapshot"]["symbol"] = "ETHUSDT"  # Mismatch!
    
    # Test on /api/v1/user/trading/preview
    response = requests.post(f"{BASE_URL}/api/v1/user/trading/preview", headers=user_headers, json=payload, timeout=30)
    assert response.status_code == 400, response.text
    assert "scanner_execution_symbol_mismatch" in response.text


def test_execution_intent_scanner_snapshot_mismatch(user_headers):
    """Test that scanner_execution_symbol_mismatch is triggered on /api/user/execution/intent/preview."""
    payload = _base_payload()
    payload["symbol"] = "BTCUSDT"
    payload["scanner_signal_snapshot"]["symbol"] = "ETHUSDT"  # Mismatch!
    
    response = requests.post(f"{BASE_URL}/api/user/execution/intent/preview", headers=user_headers, json=payload, timeout=30)
    assert response.status_code == 400, response.text
    assert "scanner_execution_symbol_mismatch" in response.text


def test_execution_precheck_quote_policy_enforced_without_allowlist(user_headers):
    """Test that quote policy is enforced by execution_precheck_service even without enforce_symbols_allowlist."""
    # Use a non-allowlisted but invalid quote asset symbol
    # This tests that quote policy is primary gate regardless of allowlist
    payload = _base_payload()
    payload["symbol"] = "DOGEBTC"  # Invalid quote asset
    payload["scanner_signal_snapshot"]["symbol"] = "DOGEBTC"
    
    response = requests.post(f"{BASE_URL}/api/v1/user/trading/preview", headers=user_headers, json=payload, timeout=30)
    assert response.status_code == 400, response.text
    assert "invalid_quote_asset" in response.text


def test_usdc_symbol_accepted_trading_preview(user_headers):
    """Test that USDC symbols are accepted by trading preview."""
    payload = _base_payload()
    payload["symbol"] = "ETHUSDC"
    payload["scanner_signal_snapshot"]["symbol"] = "ETHUSDC"
    
    response = requests.post(f"{BASE_URL}/api/v1/user/trading/preview", headers=user_headers, json=payload, timeout=30)
    assert response.status_code == 200, response.text
    preview = response.json().get("preview") or {}
    normalized = preview.get("normalized_order_payload") or {}
    assert normalized.get("quote_asset") == "USDC"


def test_usdc_symbol_accepted_execution_preview(user_headers):
    """Test that USDC symbols are accepted by execution intent preview."""
    payload = _base_payload()
    payload["symbol"] = "BTCUSDC"
    payload["scanner_signal_snapshot"]["symbol"] = "BTCUSDC"
    
    response = requests.post(f"{BASE_URL}/api/user/execution/intent/preview", headers=user_headers, json=payload, timeout=30)
    assert response.status_code == 200, response.text
    normalized = response.json().get("normalized_order_payload") or {}
    assert normalized.get("quote_asset") == "USDC"


def test_busd_symbol_rejected_as_invalid_quote(user_headers):
    """Test that BUSD symbols are rejected as invalid quote asset."""
    payload = _base_payload()
    payload["symbol"] = "ETHBUSD"
    payload["scanner_signal_snapshot"]["symbol"] = "ETHBUSD"
    
    # Both endpoints should reject
    trading_resp = requests.post(f"{BASE_URL}/api/v1/user/trading/preview", headers=user_headers, json=payload, timeout=30)
    assert trading_resp.status_code == 400, trading_resp.text
    assert "invalid_quote_asset" in trading_resp.text
    
    exec_resp = requests.post(f"{BASE_URL}/api/user/execution/intent/preview", headers=user_headers, json=payload, timeout=30)
    assert exec_resp.status_code == 400, exec_resp.text
    assert "invalid_quote_asset" in exec_resp.text


def test_scanner_snapshot_missing_symbol_rejected(user_headers):
    """Test that empty symbol in scanner_signal_snapshot is rejected."""
    payload = _base_payload()
    payload["scanner_signal_snapshot"]["symbol"] = ""
    
    response = requests.post(f"{BASE_URL}/api/v1/user/trading/preview", headers=user_headers, json=payload, timeout=30)
    assert response.status_code == 400, response.text
    assert "scanner_signal_snapshot_missing_symbol" in response.text