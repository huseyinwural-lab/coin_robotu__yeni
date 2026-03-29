import os

import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://dry-run-shadow.preview.emergentagent.com").rstrip("/")


def _admin_headers():
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "canary.admin@platform.local", "password": "CanaryAdmin123!"},
        timeout=20,
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _latest_runtime_alert_id(headers):
    response = requests.get(f"{BASE_URL}/api/runtime/alerts", headers=headers, timeout=20)
    assert response.status_code == 200
    items = response.json().get("items", [])
    assert len(items) > 0
    return items[0]["id"]


def test_runtime_alert_triage_actions_flow():
    headers = _admin_headers()
    alert_id = _latest_runtime_alert_id(headers)

    ack = requests.post(f"{BASE_URL}/api/runtime/alerts/{alert_id}/ack", headers=headers, timeout=20)
    assert ack.status_code == 200
    assert ack.json().get("alert_status") == "acknowledged"

    mute = requests.post(
        f"{BASE_URL}/api/runtime/alerts/{alert_id}/mute",
        json={"minutes": 15, "note": "triage mute"},
        headers=headers,
        timeout=20,
    )
    assert mute.status_code == 200
    assert mute.json().get("alert_status") == "muted"

    note = requests.post(
        f"{BASE_URL}/api/runtime/alerts/{alert_id}/note",
        json={"note": "operator note test"},
        headers=headers,
        timeout=20,
    )
    assert note.status_code == 200

    escalate = requests.post(
        f"{BASE_URL}/api/runtime/alerts/{alert_id}/escalate",
        json={"note": "escalate test"},
        headers=headers,
        timeout=20,
    )
    assert escalate.status_code == 200
    assert escalate.json().get("alert_status") == "escalated"

    resolve = requests.post(
        f"{BASE_URL}/api/runtime/alerts/{alert_id}/resolve",
        json={"note": "resolved"},
        headers=headers,
        timeout=20,
    )
    assert resolve.status_code == 200
    assert resolve.json().get("alert_status") == "resolved"
