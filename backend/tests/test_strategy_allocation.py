import os
from pathlib import Path

import requests

ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"


def _base_url() -> str:
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if direct:
        return direct
    env_file = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        if raw_line.startswith("REACT_APP_BACKEND_URL="):
            return raw_line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


def _admin_headers() -> dict:
    base = _base_url()
    login = requests.post(
        f"{base}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_strategy_allocation_dashboard_and_update():
    base = _base_url()
    headers = _admin_headers()

    listing = requests.get(f"{base}/api/admin/strategy-allocation", headers=headers, timeout=20)
    assert listing.status_code == 200
    assert isinstance(listing.json(), list)

    update = requests.put(
        f"{base}/api/admin/strategy-allocation/meta_test_v1",
        headers=headers,
        json={
            "capital_weight": 0.6,
            "max_capital": 12000,
            "current_capital": 1500,
            "state": "ACTIVE",
        },
        timeout=20,
    )
    assert update.status_code == 200
    payload = update.json()
    assert payload["strategy_id"] == "meta_test_v1"
    assert payload["capital_weight"] == 0.6
    assert payload["state"] == "ACTIVE"
