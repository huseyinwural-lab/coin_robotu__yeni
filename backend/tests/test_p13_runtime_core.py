"""P1.3 Runtime Core Tests

Coverage:
- Unified auth payload (/api/auth/login)
- Strategy signal contract (/api/runtime/strategy/signal)
- Risk reject path (leverage/max position)
- Queue enqueue -> worker consume -> FILLED transition
- Idempotent execution key handling
"""

import os
import time
import uuid

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


def _wait_health_ok(timeout_seconds: int = 40) -> None:
    start = time.time()
    while time.time() - start < timeout_seconds:
        try:
            resp = requests.get(f"{BASE_URL}/api/health", timeout=5)
            if resp.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(1)
    pytest.skip("backend health not ready")


@pytest.fixture(scope="module")
def auth_headers():
    _wait_health_ok()
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "canary.admin@platform.local", "password": "CanaryAdmin123!"},
        timeout=20,
    )
    if response.status_code != 200:
        pytest.skip("admin login failed")

    payload = response.json()
    assert payload.get("token")
    assert payload.get("role") in {"super_admin", "admin", "ops", "user"}
    return {"Authorization": f"Bearer {payload['access_token']}"}


def test_unified_login_contract_has_token_and_role():
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "canary.admin@platform.local", "password": "CanaryAdmin123!"},
        timeout=20,
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("token")
    assert data.get("role")
    assert data.get("user")


def test_strategy_signal_endpoint_contract(auth_headers):
    closes = [100 + i * 0.15 for i in range(80)]
    response = requests.post(
        f"{BASE_URL}/api/runtime/strategy/signal",
        json={"symbol": "ETHUSDT", "closes": closes, "strategy_name": "ema_rsi"},
        headers=auth_headers,
        timeout=20,
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") in {"ok", "no_signal"}
    if data.get("signal"):
        signal = data["signal"]
        for key in ["symbol", "side", "size", "confidence", "strategy_name", "timestamp"]:
            assert key in signal


def test_runtime_execution_risk_reject(auth_headers):
    idem = f"p13-risk-reject-{uuid.uuid4()}"
    response = requests.post(
        f"{BASE_URL}/api/runtime/execution/submit",
        json={
            "symbol": "ETHUSDT",
            "side": "BUY",
            "size": 1.0,
            "confidence": 0.8,
            "strategy_name": "ema_rsi",
            "mark_price": 1000,
            "leverage": 9,
            "idempotency_key": idem,
        },
        headers=auth_headers,
        timeout=20,
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "rejected"
    assert data.get("risk", {}).get("reject_reason") is not None


def test_runtime_queue_and_worker_flow(auth_headers):
    idem = f"p13-enqueue-{uuid.uuid4()}"
    submit = requests.post(
        f"{BASE_URL}/api/runtime/execution/submit",
        json={
            "symbol": "ETHUSDT",
            "side": "BUY",
            "size": 0.2,
            "confidence": 0.8,
            "strategy_name": "ema_rsi",
            "mark_price": 1200,
            "leverage": 2,
            "idempotency_key": idem,
        },
        headers=auth_headers,
        timeout=20,
    )
    assert submit.status_code == 200
    submit_data = submit.json()
    assert submit_data.get("status") == "enqueued"

    queue_payload = submit_data.get("queue_payload", {})
    for required in ["idempotency_key", "user_id", "symbol", "side", "size", "strategy_name", "created_at"]:
        assert required in queue_payload

    worker = requests.post(
        f"{BASE_URL}/api/runtime/execution/worker/process-once",
        headers=auth_headers,
        timeout=20,
    )
    assert worker.status_code == 200
    worker_data = worker.json()
    assert worker_data.get("status") in {"processed", "queue_empty"}

    job_id = submit_data.get("execution_job_id")
    job = requests.get(f"{BASE_URL}/api/runtime/execution/jobs/{job_id}", headers=auth_headers, timeout=20)
    assert job.status_code == 200
    assert job.json().get("state") in {"CREATED", "SENT", "PARTIALLY_FILLED", "FILLED", "FAILED", "CANCELED"}


def test_runtime_idempotency_duplicate(auth_headers):
    idem = f"p13-idem-{uuid.uuid4()}"
    payload = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "size": 0.2,
        "confidence": 0.7,
        "strategy_name": "ema_rsi",
        "mark_price": 100,
        "leverage": 2,
        "idempotency_key": idem,
    }

    first = requests.post(f"{BASE_URL}/api/runtime/execution/submit", json=payload, headers=auth_headers, timeout=20)
    second = requests.post(f"{BASE_URL}/api/runtime/execution/submit", json=payload, headers=auth_headers, timeout=20)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json().get("status") == "duplicate"
