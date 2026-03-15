import os
import random
import string
from pathlib import Path

import pytest
import requests

ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")


def _resolve_base_url() -> str:
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if direct:
        return direct
    env_file = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        if raw_line.strip().startswith("REACT_APP_BACKEND_URL="):
            return raw_line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


BASE_URL = _resolve_base_url()


def _random_email(prefix: str = "iter50") -> str:
    return f"{prefix}_{''.join(random.choices(string.ascii_lowercase + string.digits, k=8))}@example.com"


@pytest.fixture(scope="module")
def auth_context():
    email = _random_email()
    password = "Iteration50123!"

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

    user_login = requests.post(f"{BASE_URL}/api/auth/login/user", json={"email": email, "password": password}, timeout=20)
    assert user_login.status_code == 200
    user_token = user_login.json()["access_token"]

    return {
        "user_headers": {"Authorization": f"Bearer {user_token}"},
        "admin_headers": {"Authorization": f"Bearer {admin_token}"},
    }


def test_pg01_reports_live_and_artifacts(auth_context):
    response = requests.get(
        f"{BASE_URL}/api/user/reports/weekly",
        headers=auth_context["user_headers"],
        params={"include_artifacts": True},
        timeout=20,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["report_id"]
    assert "weekly_performance_report.pdf" in data["download_links"]

    pdf_url = data["download_links"]["weekly_performance_report.pdf"]
    pdf_response = requests.get(f"{BASE_URL}{pdf_url}", headers=auth_context["user_headers"], timeout=20)
    assert pdf_response.status_code == 200


def test_execution_preview_submit_admin_release_flow(auth_context):
    payload = {
        "source_type": "manual",
        "market_type": "spot",
        "symbol": "BTCUSDT",
        "side": "buy",
        "order_type": "market",
        "position_size_mode": "fixed_notional",
        "position_size_value": 35,
        "take_profit_mode": "percent",
        "take_profit_value": 2,
        "stop_loss_mode": "percent",
        "stop_loss_value": 1,
        "execution_mode": "manual",
    }

    preview = requests.post(
        f"{BASE_URL}/api/user/execution/intent/preview",
        headers=auth_context["user_headers"],
        json=payload,
        timeout=20,
    )
    assert preview.status_code == 200
    preview_data = preview.json()
    assert preview_data["validation_status"] == "valid"

    no_preview_submit = requests.post(
        f"{BASE_URL}/api/user/execution/intent/submit",
        headers=auth_context["user_headers"],
        json={"intent_token": "missing-token"},
        timeout=20,
    )
    assert no_preview_submit.status_code == 400

    submit = requests.post(
        f"{BASE_URL}/api/user/execution/intent/submit",
        headers=auth_context["user_headers"],
        json={"intent_token": preview_data["intent_token"], "preview_hash": preview_data["preview_hash"]},
        timeout=20,
    )
    assert submit.status_code == 200
    assert submit.json()["intent_status"] == "QUEUED_FOR_APPROVAL"

    queue = requests.get(
        f"{BASE_URL}/api/admin/execution-queue",
        headers=auth_context["admin_headers"],
        params={"status_filter": "QUEUED"},
        timeout=20,
    )
    assert queue.status_code == 200
    queue_rows = queue.json()
    queue_row = next(item for item in queue_rows if item["id"] == submit.json()["intent_id"])

    approve = requests.post(
        f"{BASE_URL}/api/admin/execution-queue/{queue_row['id']}/approve",
        headers=auth_context["admin_headers"],
        json={"note": "approved_in_test"},
        timeout=20,
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "RELEASED"
