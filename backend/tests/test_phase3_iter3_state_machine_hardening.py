"""Phase-3 Iteration-3: execution state branches + hardening gate + monitoring visibility."""

import os
import sys
from pathlib import Path

import pytest
import requests

sys.path.append(str(Path(__file__).resolve().parents[1]))

from services import hardening_checklist_service as hc_service


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    pytest.skip("REACT_APP_BACKEND_URL is required for public endpoint testing", allow_module_level=True)

API_BASE = f"{BASE_URL.rstrip('/')}/api"


@pytest.fixture(scope="module")
def api_client():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def admin_headers(api_client):
    # module: admin auth fixture for phase3 iter3 APIs
    login = api_client.post(
        f"{API_BASE}/auth/login",
        json={"email": os.environ.get("TEST_ADMIN_EMAIL", ""), "password": os.environ.get("TEST_ADMIN_PASSWORD", "")},
        timeout=30,
    )
    if login.status_code != 200:
        pytest.skip(f"Admin login failed: {login.status_code}")
    token = login.json().get("access_token")
    assert isinstance(token, str) and token
    return {"Authorization": f"Bearer {token}"}


def _ensure_breakout_timeout_fallback_policy(api_client, admin_headers):
    list_resp = api_client.get(f"{API_BASE}/admin-phase3/execution-policies", headers=admin_headers, timeout=30)
    assert list_resp.status_code == 200
    policies = list_resp.json()
    breakout = next((row for row in policies if row["strategy_type"] == "breakout"), None)

    payload = {
        "strategy_type": "breakout",
        "execution_style": "balanced",
        "order_preference": "limit_first",
        "timeout_seconds": 8,
        "fallback_behavior": "limit_retry_then_market",
        "partial_fill_tolerance_pct": 60,
        "execution_urgency": "medium",
        "retry_limit": 2,
        "is_active": True,
    }

    if breakout:
        save_resp = api_client.put(
            f"{API_BASE}/admin-phase3/execution-policies/{breakout['id']}",
            headers=admin_headers,
            json=payload,
            timeout=30,
        )
    else:
        save_resp = api_client.post(
            f"{API_BASE}/admin-phase3/execution-policies",
            headers=admin_headers,
            json=payload,
            timeout=30,
        )

    assert save_resp.status_code == 200
    saved = save_resp.json()
    assert saved["fallback_behavior"] == "limit_retry_then_market"


def test_execution_state_branch_filled(api_client, admin_headers):
    # module: execution state machine branch coverage (filled)
    response = api_client.post(
        f"{API_BASE}/admin-phase3/execution-state-transitions/simulate",
        params={"strategy_type": "breakout", "symbol": "BTCUSDT", "side": "long", "outcome": "filled"},
        headers=admin_headers,
        timeout=30,
    )
    assert response.status_code == 200
    data = response.json()

    assert isinstance(data["execution_event_id"], str) and data["execution_event_id"]
    assert data["final_state"] == "filled"
    assert data["state_path"][0:3] == ["created", "submitted", "acknowledged"]
    assert data["state_path"][-1] == "filled"


def test_execution_state_branch_timeout_to_fallback(api_client, admin_headers):
    # module: execution state machine branch coverage (timeout -> fallback -> filled)
    _ensure_breakout_timeout_fallback_policy(api_client, admin_headers)

    response = api_client.post(
        f"{API_BASE}/admin-phase3/execution-state-transitions/simulate",
        params={"strategy_type": "breakout", "symbol": "BTCUSDT", "side": "long", "outcome": "timeout"},
        headers=admin_headers,
        timeout=30,
    )
    assert response.status_code == 200
    data = response.json()

    assert data["state_path"][0:3] == ["created", "submitted", "acknowledged"]
    assert "timeout" in data["state_path"]
    assert "fallback_submitted" in data["state_path"]
    assert data["final_state"] == "filled"


def test_execution_state_branch_rejected(api_client, admin_headers):
    # module: execution state machine branch coverage (rejected)
    response = api_client.post(
        f"{API_BASE}/admin-phase3/execution-state-transitions/simulate",
        params={"strategy_type": "breakout", "symbol": "BTCUSDT", "side": "long", "outcome": "rejected"},
        headers=admin_headers,
        timeout=30,
    )
    assert response.status_code == 200
    data = response.json()

    assert data["final_state"] == "rejected"
    assert data["state_path"][-1] == "rejected"
    assert "fallback_submitted" not in data["state_path"]


def test_execution_transitions_list_contains_simulated_states(api_client, admin_headers):
    # module: admin execution transition visibility endpoint
    response = api_client.get(
        f"{API_BASE}/admin-phase3/execution-state-transitions",
        params={"limit": 200},
        headers=admin_headers,
        timeout=30,
    )
    assert response.status_code == 200
    rows = response.json()

    assert isinstance(rows, list)
    assert len(rows) > 0
    states = {row["state"] for row in rows}
    assert "filled" in states
    assert "rejected" in states
    assert "timeout" in states


def test_hardening_checklist_run_and_latest_endpoints(api_client, admin_headers):
    # module: hardening checklist run/latest API contract
    run_response = api_client.post(f"{API_BASE}/admin-phase3/hardening-checklist/run", headers=admin_headers, timeout=30)
    assert run_response.status_code == 200
    run_data = run_response.json()

    assert isinstance(run_data["id"], str) and run_data["id"]
    assert isinstance(run_data["score"], (int, float))
    assert isinstance(run_data["critical_blocked"], bool)
    assert run_data["readiness_status"] in {"ready", "blocked"}
    assert isinstance(run_data["checklist_items"], list) and len(run_data["checklist_items"]) >= 5

    latest_response = api_client.get(f"{API_BASE}/admin-phase3/hardening-checklist/latest", headers=admin_headers, timeout=30)
    assert latest_response.status_code == 200
    latest = latest_response.json()
    assert latest["id"] == run_data["id"]


def test_pipeline_monitoring_exposes_hardening_metrics(api_client, admin_headers):
    # module: monitoring endpoint hardening metrics visibility
    response = api_client.get(f"{API_BASE}/pipeline/monitoring", headers=admin_headers, timeout=30)
    assert response.status_code == 200
    data = response.json()

    for key in [
        "websocket_reconnects_5m",
        "idempotency_keys_5m",
        "duplicate_signals_blocked_5m",
        "execution_transitions_5m",
        "failed_events_pending",
        "failed_events_dead",
    ]:
        assert key in data
        assert isinstance(data[key], int)


class _FakeQuery:
    def __init__(self, count_value):
        self._count_value = count_value

    def count(self):
        return self._count_value


class _FakeDb:
    def __init__(self):
        self.saved = []

    def query(self, model):
        name = model.__name__
        if name == "ExecutionStateTransition":
            return _FakeQuery(12)
        if name == "AuditLog":
            return _FakeQuery(4)
        return _FakeQuery(0)

    def add(self, obj):
        self.saved.append(obj)

    def commit(self):
        return None

    def refresh(self, _obj):
        return None


def test_hardening_gate_caps_score_when_critical_item_fails(monkeypatch):
    # module: hardening checklist critical gate scoring logic (service-level)
    fake_db = _FakeDb()

    def _fake_monitoring_snapshot(_db):
        return {
            "websocket_reconnects_5m": 25,
            "idempotency_keys_5m": 5,
            "duplicate_signals_blocked_5m": 1,
            "execution_transitions_5m": 8,
            "failed_events_pending": 0,
            "failed_events_dead": 0,
            "queue_depth": 5,
            "websocket_status": "reconnecting",
            "heartbeat": "-",
            "signal_rate_last_5m": 0,
            "paper_trades_last_5m": 0,
            "open_positions": 0,
            "latency_ms": 0,
            "active_bots_running": 0,
        }

    monkeypatch.setattr(hc_service.pipeline_runtime, "monitoring_snapshot", _fake_monitoring_snapshot)
    run = hc_service.run_hardening_checklist(fake_db)

    assert run.critical_blocked is True
    assert run.readiness_status == "blocked"
    assert run.score <= 59.0
    failed_critical = [item for item in run.checklist_items if item["critical"] and item["status"] == "fail"]
    assert len(failed_critical) >= 1
