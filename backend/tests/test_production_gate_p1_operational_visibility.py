"""
Production Gate P1 Operational Visibility Tests

Kapsam:
- API key test endpoint ve payload alanları
- Permission breakdown (exchange bazlı)
- Exchange health (exchange bazlı)
- Mode history görünümü
- Order scenario matrix (PASS + FAIL)
- Export filtreleri (scope/date)
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "https://dry-run-shadow.preview.emergentagent.com"
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture()
def authed_session() -> requests.Session:
    session = requests.Session()
    login = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
        timeout=30,
    )
    assert login.status_code == 200, f"Login failed: {login.status_code} {login.text}"
    token = login.json().get("access_token")
    assert token, "Missing access token"
    session.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return session


def test_ops_overview_shape(authed_session: requests.Session):
    response = authed_session.get(f"{BASE_URL}/api/phase4/admin/production-gate/ops-overview", timeout=30)
    assert response.status_code == 200, response.text
    data = response.json()

    required = [
        "active_fail_count",
        "active_fail_codes",
        "api_key_tests",
        "permission_breakdown",
        "exchange_health",
        "mode_history",
        "order_scenarios",
    ]
    for key in required:
        assert key in data, f"Missing key: {key}"

    assert isinstance(data["active_fail_count"], int)
    assert isinstance(data["active_fail_codes"], list)
    assert isinstance(data["api_key_tests"], list)
    assert isinstance(data["permission_breakdown"], list)
    assert isinstance(data["exchange_health"], list)
    assert isinstance(data["mode_history"], list)
    assert isinstance(data["order_scenarios"], list)


def test_api_key_test_run_payload(authed_session: requests.Session):
    response = authed_session.post(
        f"{BASE_URL}/api/phase4/admin/production-gate/api-key-tests/run",
        json={},
        timeout=60,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    rows = data.get("api_key_tests") or []
    assert len(rows) >= 1, "Expected at least one api_key_tests row"

    row = rows[0]
    for key in ["exchange", "market_type", "environment", "connection_id", "status", "success", "response_summary", "last_tested_at"]:
        assert key in row, f"Missing API key test field: {key}"
    assert row["status"] in {"PASS", "FAIL"}
    assert isinstance(row["success"], bool)


def test_permission_breakdown_shape(authed_session: requests.Session):
    response = authed_session.get(f"{BASE_URL}/api/phase4/admin/production-gate/ops-overview", timeout=30)
    assert response.status_code == 200
    rows = response.json().get("permission_breakdown") or []
    assert len(rows) >= 1, "Expected at least one permission row"

    row = rows[0]
    for key in ["exchange", "read_status", "write_status", "trade_status"]:
        assert key in row, f"Missing permission field: {key}"
    assert row["read_status"] in {"PASS", "FAIL", "UNKNOWN"}
    assert row["write_status"] in {"PASS", "FAIL", "UNKNOWN"}
    assert row["trade_status"] in {"PASS", "FAIL", "UNKNOWN"}


def test_exchange_health_shape(authed_session: requests.Session):
    response = authed_session.get(f"{BASE_URL}/api/phase4/admin/production-gate/ops-overview", timeout=30)
    assert response.status_code == 200
    rows = response.json().get("exchange_health") or []
    assert len(rows) >= 1, "Expected at least one exchange health row"

    row = rows[0]
    for key in ["exchange", "connection_status", "auth_status", "permission_status", "last_checked_at"]:
        assert key in row, f"Missing health field: {key}"
    assert row["connection_status"] in {"PASS", "FAIL", "UNKNOWN"}
    assert row["auth_status"] in {"PASS", "FAIL", "UNKNOWN"}
    assert row["permission_status"] in {"PASS", "FAIL", "UNKNOWN"}


def test_mode_history_endpoint(authed_session: requests.Session):
    response = authed_session.get(f"{BASE_URL}/api/phase4/admin/production-gate/mode-history?limit=20", timeout=30)
    assert response.status_code == 200, response.text
    rows = response.json()
    assert isinstance(rows, list)
    if len(rows) > 0:
        row = rows[0]
        for key in ["changed_at", "actor_role", "from_mode", "to_mode", "request_id"]:
            assert key in row, f"Missing mode history field: {key}"


def test_order_scenario_matrix_contains_pass_and_fail(authed_session: requests.Session):
    response = authed_session.post(
        f"{BASE_URL}/api/phase4/admin/production-gate/order-scenarios/rerun",
        json={},
        timeout=60,
    )
    assert response.status_code == 200, response.text
    rows = response.json().get("order_scenarios") or []
    assert len(rows) >= 5, "Expected full scenario matrix"

    statuses = {str(item.get("status") or "") for item in rows}
    assert "PASS" in statuses, "Expected at least one PASS scenario"
    assert "FAIL" in statuses, "Expected at least one FAIL scenario"


def test_export_filters_scope_and_date_range(authed_session: requests.Session):
    date_from = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    date_to = datetime.now(timezone.utc).isoformat()

    response = authed_session.get(
        f"{BASE_URL}/api/phase4/admin/production-gate/export/raw",
        params={"scope": "summary", "date_from": date_from, "date_to": date_to},
        timeout=30,
    )
    assert response.status_code == 200, response.text
    data = response.json()

    assert data.get("scope") == "summary"
    assert "filters" in data
    assert "export_payload" in data
    assert "ops_summary" in data
    assert "active_state_summary" in (data.get("export_payload") or {})
