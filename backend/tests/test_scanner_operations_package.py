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
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _new_user_headers(prefix: str, admin_headers: dict) -> dict:
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    password = "ScannerOps123!"

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
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.fixture(scope="module")
def scanner_user_headers():
    return _new_user_headers("scanner_ops", _admin_headers())


def test_scanner_runtime_live_readiness_and_daily_report(scanner_user_headers):
    readiness = requests.get(
        f"{BASE_URL}/api/user/scanner/runtime/live-readiness",
        params={"window": "24h"},
        headers=scanner_user_headers,
        timeout=30,
    )
    assert readiness.status_code == 200, readiness.text
    readiness_payload = readiness.json()
    for key in ["symbol_integrity", "max_risk_guard", "execution_quality", "scanner_activity", "strategy_diversity", "emergency_stop"]:
        assert key in readiness_payload

    report = requests.get(
        f"{BASE_URL}/api/user/scanner/runtime/daily-report",
        params={"window": "24h"},
        headers=scanner_user_headers,
        timeout=30,
    )
    assert report.status_code == 200, report.text
    report_payload = report.json()
    for key in ["date", "scan", "execution", "risk", "strategies"]:
        assert key in report_payload

    export_csv = requests.get(
        f"{BASE_URL}/api/user/scanner/runtime/daily-report/export",
        params={"window": "24h", "format": "csv"},
        headers=scanner_user_headers,
        timeout=30,
    )
    assert export_csv.status_code == 200, export_csv.text
    assert "text/csv" in export_csv.headers.get("content-type", "")


def test_scanner_execution_symbol_integrity_rejects_mismatch(scanner_user_headers):
    payload = {
        "source_type": "scanner",
        "source_ref_id": "scanner-row-1",
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
        "timestamp": "2026-03-15T00:00:00Z",
        "scanner_signal_snapshot": {
            "symbol": "BTCUSDT",
            "signal": "long",
            "score": 82,
            "strategy": "spot_pullback_v1",
            "confidence": 0.73,
            "timestamp": "2026-03-15T00:00:00Z",
        },
    }
    response = requests.post(
        f"{BASE_URL}/api/v1/user/trading/preview",
        headers=scanner_user_headers,
        json=payload,
        timeout=30,
    )
    assert response.status_code == 400, response.text
    assert "scanner_execution_symbol_mismatch" in response.text


def test_scanner_execution_requires_symbol(scanner_user_headers):
    payload = {
        "source_type": "scanner",
        "source_ref_id": "scanner-row-2",
        "market_type": "spot",
        "symbol": " ",
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
        "scanner_signal_snapshot": {
            "symbol": "ETHUSDT",
            "signal": "long",
            "score": 75,
            "strategy": "spot_pullback_v1",
            "confidence": 0.6,
            "timestamp": "2026-03-15T00:00:00Z",
        },
    }
    response = requests.post(
        f"{BASE_URL}/api/v1/user/trading/preview",
        headers=scanner_user_headers,
        json=payload,
        timeout=30,
    )
    assert response.status_code == 400, response.text
    assert "symbol_required_for_execution_intent" in response.text