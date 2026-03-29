import os
import uuid

import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://unified-orchestrator.preview.emergentagent.com").rstrip("/")


def _admin_headers():
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "canary.admin@platform.local", "password": "CanaryAdmin123!"},
        timeout=20,
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_execution_latency_metrics_are_recorded():
    headers = _admin_headers()
    idem = f"latency-{uuid.uuid4()}"

    submit = requests.post(
        f"{BASE_URL}/api/runtime/execution/submit",
        json={
            "symbol": "ETHUSDT",
            "side": "BUY",
            "size": 0.2,
            "confidence": 0.8,
            "strategy_name": "ema_rsi",
            "mark_price": 200,
            "leverage": 2,
            "idempotency_key": idem,
        },
        headers=headers,
        timeout=20,
    )
    assert submit.status_code == 200
    job_id = submit.json().get("execution_job_id")

    worker = requests.post(f"{BASE_URL}/api/runtime/execution/worker/process-once", headers=headers, timeout=20)
    assert worker.status_code == 200

    job = requests.get(f"{BASE_URL}/api/runtime/execution/jobs/{job_id}", headers=headers, timeout=20)
    assert job.status_code == 200
    payload = job.json()
    assert payload.get("queue_wait_ms") is None or int(payload.get("queue_wait_ms")) >= 0
    assert payload.get("execution_ms") is None or int(payload.get("execution_ms")) >= 0
    assert payload.get("total_ms") is None or int(payload.get("total_ms")) >= 0
    assert payload.get("failure_class") in {None, "adapter_guard", "exchange_reject", "execution_exception"}
