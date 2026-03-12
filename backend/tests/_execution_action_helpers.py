import os
import random
import string
from pathlib import Path

import requests

ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"


def resolve_base_url() -> str:
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if direct:
        return direct

    env_file = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        if raw_line.startswith("REACT_APP_BACKEND_URL="):
            return raw_line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


def random_email(prefix: str = "posaction") -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{prefix}_{suffix}@example.com"


def provision_user() -> tuple[str, dict, dict]:
    base = resolve_base_url()
    email = random_email()
    password = "PositionAction123!"

    register = requests.post(f"{base}/api/auth/register", json={"email": email, "password": password}, timeout=20)
    register.raise_for_status()
    user_id = register.json()["id"]

    admin_login = requests.post(
        f"{base}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    admin_login.raise_for_status()
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    approve_user = requests.post(
        f"{base}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers=admin_headers,
        timeout=20,
    )
    approve_user.raise_for_status()

    user_login = requests.post(
        f"{base}/api/auth/login/user",
        json={"email": email, "password": password},
        timeout=20,
    )
    user_login.raise_for_status()
    user_headers = {"Authorization": f"Bearer {user_login.json()['access_token']}"}
    return base, user_headers, admin_headers


def create_and_release_open_position(base: str, user_headers: dict, admin_headers: dict) -> dict:
    preview_payload = {
        "source_type": "manual",
        "market_type": "spot",
        "symbol": "BTCUSDT",
        "side": "buy",
        "order_type": "market",
        "position_size_mode": "fixed_notional",
        "position_size_value": 80,
        "take_profit_mode": "percent",
        "take_profit_value": 2,
        "stop_loss_mode": "percent",
        "stop_loss_value": 1,
        "execution_mode": "manual",
        "strategy_binding": "spot_pullback_v1",
    }
    preview = requests.post(f"{base}/api/user/execution/intent/preview", headers=user_headers, json=preview_payload, timeout=20)
    preview.raise_for_status()
    preview_data = preview.json()
    assert preview_data["validation_status"] == "valid"

    submit = requests.post(
        f"{base}/api/user/execution/intent/submit",
        headers=user_headers,
        json={"intent_token": preview_data["intent_token"], "preview_hash": preview_data["preview_hash"]},
        timeout=20,
    )
    submit.raise_for_status()

    queue = requests.get(f"{base}/api/admin/execution-queue", headers=admin_headers, params={"status_filter": "QUEUED", "limit": 200}, timeout=20)
    queue.raise_for_status()
    queued = [row for row in queue.json() if row.get("intent_token") == preview_data["intent_token"]]
    assert queued
    intent_id = queued[0]["id"]

    approve = requests.post(
        f"{base}/api/admin/execution-queue/{intent_id}/approve",
        headers=admin_headers,
        json={"note": "test_open_position"},
        timeout=20,
    )
    approve.raise_for_status()

    positions = requests.get(f"{base}/api/user/execution/positions", headers=user_headers, timeout=20)
    positions.raise_for_status()
    rows = positions.json()
    assert rows
    return rows[0]


def preview_submit_approve_position_action(
    base: str,
    user_headers: dict,
    admin_headers: dict,
    *,
    intent_type: str,
    position_id: str,
    symbol: str,
    size: float,
    price: float | None = None,
    stop_price: float | None = None,
    take_profit_price: float | None = None,
) -> dict:
    preview = requests.post(
        f"{base}/api/user/execution/position-actions/preview",
        headers=user_headers,
        json={
            "intent_type": intent_type,
            "position_id": position_id,
            "symbol": symbol,
            "size": size,
            "reduce_only": intent_type in {"CLOSE_POSITION", "PARTIAL_CLOSE", "MOVE_STOP", "MOVE_TAKE_PROFIT"},
            "price": price,
            "stop_price": stop_price,
            "take_profit_price": take_profit_price,
        },
        timeout=20,
    )
    preview.raise_for_status()
    preview_data = preview.json()
    assert preview_data["validation_status"] == "valid"

    submit = requests.post(
        f"{base}/api/user/execution/position-actions/submit",
        headers=user_headers,
        json={"intent_token": preview_data["intent_token"], "preview_hash": preview_data["preview_hash"]},
        timeout=20,
    )
    submit.raise_for_status()

    queue = requests.get(f"{base}/api/admin/execution-queue", headers=admin_headers, params={"status_filter": "QUEUED", "limit": 200}, timeout=20)
    queue.raise_for_status()
    queued = [row for row in queue.json() if row.get("intent_token") == preview_data["intent_token"]]
    assert queued
    intent_id = queued[0]["id"]

    approve = requests.post(
        f"{base}/api/admin/execution-queue/{intent_id}/approve",
        headers=admin_headers,
        json={"note": f"test_{intent_type.lower()}"},
        timeout=20,
    )
    approve.raise_for_status()
    return preview_data
