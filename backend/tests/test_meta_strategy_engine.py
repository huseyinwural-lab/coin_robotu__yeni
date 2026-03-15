import os
import random
import string
from pathlib import Path

import requests

ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")


def _base_url() -> str:
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if direct:
        return direct
    env_file = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        if raw_line.startswith("REACT_APP_BACKEND_URL="):
            return raw_line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


def _random_email(prefix: str = "meta") -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{prefix}_{suffix}@example.com"


def test_meta_strategy_disable_blocks_preview():
    base = _base_url()

    admin_login = requests.post(
        f"{base}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert admin_login.status_code == 200
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    disable = requests.put(
        f"{base}/api/admin/strategy-allocation/meta_disabled_v1",
        headers=admin_headers,
        json={"state": "DISABLED", "capital_weight": 1.0, "max_capital": 1000, "current_capital": 0},
        timeout=20,
    )
    assert disable.status_code == 200
    assert disable.json()["state"] == "DISABLED"

    email = _random_email()
    password = "MetaEngine123!"
    register = requests.post(f"{base}/api/auth/register", json={"email": email, "password": password}, timeout=20)
    assert register.status_code == 200
    user_id = register.json()["id"]

    approve = requests.post(
        f"{base}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers=admin_headers,
        timeout=20,
    )
    assert approve.status_code == 200

    user_login = requests.post(
        f"{base}/api/auth/login/user",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert user_login.status_code == 200
    user_headers = {"Authorization": f"Bearer {user_login.json()['access_token']}"}

    preview = requests.post(
        f"{base}/api/user/execution/intent/preview",
        headers=user_headers,
        json={
            "source_type": "manual",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50,
            "take_profit_mode": "percent",
            "take_profit_value": 2,
            "stop_loss_mode": "percent",
            "stop_loss_value": 1,
            "execution_mode": "manual",
            "strategy_binding": "meta_disabled_v1",
        },
        timeout=20,
    )
    assert preview.status_code == 200
    payload = preview.json()
    assert payload["meta_engine_decision"] == "DISABLED"
    assert payload["validation_status"] == "rejected"
    assert "strategy_disabled_by_meta_engine" in payload["reject_reason_codes"]
