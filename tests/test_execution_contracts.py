import json
import os
import random
import string
from pathlib import Path

import pytest
import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT_DIR / "contracts" / "execution_intent_contract.json"
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")


def _resolve_base_url() -> str:
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if direct:
        return direct
    env_path = ROOT_DIR / "frontend" / ".env"
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE_URL = _resolve_base_url()


def _random_email(prefix: str = "exec") -> str:
    return f"{prefix}_{''.join(random.choices(string.ascii_lowercase + string.digits, k=9))}@example.com"


@pytest.fixture(scope="module")
def contract_payload():
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def auth_tokens():
    email = _random_email()
    password = "Exec12345!"

    register = requests.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": password}, timeout=20)
    assert register.status_code == 200
    user_id = register.json()["id"]

    admin_login = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["access_token"]

    approve = requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=20,
    )
    assert approve.status_code == 200

    login = requests.post(f"{BASE_URL}/api/auth/login/user", json={"email": email, "password": password}, timeout=20)
    assert login.status_code == 200
    return {
        "user": login.json()["access_token"],
        "admin": admin_token,
    }


def _valid_preview_payload():
    return {
        "source_type": "manual",
        "market_type": "spot",
        "symbol": "BTCUSDT",
        "side": "buy",
        "order_type": "market",
        "position_size_mode": "fixed_notional",
        "position_size_value": 30,
        "take_profit_mode": "percent",
        "take_profit_value": 2,
        "stop_loss_mode": "percent",
        "stop_loss_value": 1,
        "execution_mode": "manual",
    }


def test_execution_contract_endpoints_exist(contract_payload):
    for item in contract_payload.get("endpoints", []):
        endpoint = item["endpoint"]
        method = item["method"].upper()
        response = requests.request(method, f"{BASE_URL}{endpoint}", timeout=20)
        assert response.status_code != 404, f"missing endpoint: {method} {endpoint}"


def test_preview_required_before_submit(auth_tokens):
    user_headers = {"Authorization": f"Bearer {auth_tokens['user']}"}
    no_preview_submit = requests.post(
        f"{BASE_URL}/api/user/execution/intent/submit",
        headers=user_headers,
        json={"intent_token": "non-existent-token"},
        timeout=20,
    )
    assert no_preview_submit.status_code == 400


def test_preview_then_submit_queue_flow(auth_tokens):
    user_headers = {"Authorization": f"Bearer {auth_tokens['user']}"}
    admin_headers = {"Authorization": f"Bearer {auth_tokens['admin']}"}

    preview = requests.post(
        f"{BASE_URL}/api/user/execution/intent/preview",
        headers=user_headers,
        json=_valid_preview_payload(),
        timeout=20,
    )
    assert preview.status_code == 200
    preview_data = preview.json()
    assert preview_data["validation_status"] == "valid"

    submit = requests.post(
        f"{BASE_URL}/api/user/execution/intent/submit",
        headers=user_headers,
        json={"intent_token": preview_data["intent_token"], "preview_hash": preview_data["preview_hash"]},
        timeout=20,
    )
    assert submit.status_code == 200
    assert submit.json()["intent_status"] == "QUEUED_FOR_APPROVAL"

    queue = requests.get(f"{BASE_URL}/api/admin/execution-queue", headers=admin_headers, timeout=20)
    assert queue.status_code == 200
    rows = queue.json()
    row = next((item for item in rows if item["id"] == submit.json()["intent_id"]), None)
    assert row is not None
    assert row["status"] == "QUEUED"


def test_preview_hash_mismatch_rejected(auth_tokens):
    user_headers = {"Authorization": f"Bearer {auth_tokens['user']}"}
    preview = requests.post(
        f"{BASE_URL}/api/user/execution/intent/preview",
        headers=user_headers,
        json=_valid_preview_payload(),
        timeout=20,
    )
    assert preview.status_code == 200
    data = preview.json()

    submit = requests.post(
        f"{BASE_URL}/api/user/execution/intent/submit",
        headers=user_headers,
        json={"intent_token": data["intent_token"], "preview_hash": "mismatch"},
        timeout=20,
    )
    assert submit.status_code == 400


def test_admin_approve_creates_required_audit_events(auth_tokens):
    user_headers = {"Authorization": f"Bearer {auth_tokens['user']}"}
    admin_headers = {"Authorization": f"Bearer {auth_tokens['admin']}"}

    preview = requests.post(
        f"{BASE_URL}/api/user/execution/intent/preview",
        headers=user_headers,
        json=_valid_preview_payload(),
        timeout=20,
    )
    assert preview.status_code == 200
    preview_data = preview.json()

    submit = requests.post(
        f"{BASE_URL}/api/user/execution/intent/submit",
        headers=user_headers,
        json={"intent_token": preview_data["intent_token"], "preview_hash": preview_data["preview_hash"]},
        timeout=20,
    )
    assert submit.status_code == 200
    intent_id = submit.json()["intent_id"]

    approve = requests.post(
        f"{BASE_URL}/api/admin/execution-queue/{intent_id}/approve",
        headers=admin_headers,
        json={"note": "approve_for_audit_check"},
        timeout=20,
    )
    assert approve.status_code == 200

    audit_logs = requests.get(f"{BASE_URL}/api/audit-logs", headers=admin_headers, timeout=20)
    assert audit_logs.status_code == 200
    actions = [row["action"] for row in audit_logs.json() if row.get("entity_id") == intent_id]
    for action in [
        "EXECUTION_INTENT_PREVIEWED",
        "EXECUTION_INTENT_SUBMITTED",
        "EXECUTION_INTENT_QUEUED",
        "EXECUTION_INTENT_APPROVED",
        "EXECUTION_ORDER_RELEASED",
    ]:
        assert action in actions
