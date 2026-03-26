import os
import uuid

import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://revenue-snapshot.preview.emergentagent.com").rstrip("/")


def _admin_headers():
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "canary.admin@platform.local", "password": "CanaryAdmin123!"},
        timeout=20,
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_runtime_stream_receives_execution_state_events():
    headers = _admin_headers()
    idem = f"ws-stream-{uuid.uuid4()}"

    submit = requests.post(
        f"{BASE_URL}/api/runtime/execution/submit",
        json={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "size": 0.2,
            "confidence": 0.9,
            "strategy_name": "ema_rsi",
            "mark_price": 100,
            "leverage": 2,
            "idempotency_key": idem,
        },
        headers=headers,
        timeout=20,
    )
    assert submit.status_code == 200

    worker = requests.post(f"{BASE_URL}/api/runtime/execution/worker/process-once", headers=headers, timeout=20)
    assert worker.status_code == 200

    timeline = requests.get(f"{BASE_URL}/api/runtime/timeline/events", headers=headers, timeout=20)
    assert timeline.status_code == 200
    events = timeline.json().get("items", [])
    assert len(events) > 0
    assert any(event.get("event_type") == "execution_state_changed" for event in events)
