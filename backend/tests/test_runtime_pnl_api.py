import os
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


def _admin_headers():
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "canary.admin@platform.local", "password": "CanaryAdmin123!"},
        timeout=20,
    )
    assert response.status_code == 200
    token = response.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


def test_runtime_pnl_summary_and_positions_api():
    headers = _admin_headers()

    summary = requests.get(f"{BASE_URL}/api/runtime/pnl/summary", headers=headers, timeout=20)
    assert summary.status_code == 200
    summary_payload = summary.json()
    for key in ["scope", "realized_pnl", "unrealized_pnl", "net_pnl", "updated_at"]:
        assert key in summary_payload

    positions = requests.get(f"{BASE_URL}/api/runtime/pnl/positions", headers=headers, timeout=20)
    assert positions.status_code == 200
    pos_payload = positions.json()
    assert "rows" in pos_payload
