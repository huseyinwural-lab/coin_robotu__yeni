"""Phase-3 Iteration-2: risk multi-exposure logic + execution state/hardening admin API coverage."""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

sys.path.append(str(Path(__file__).resolve().parents[1]))

from services.pipeline.events import SignalDecision
from services.pipeline.execution_engine import _build_state_path
from services.pipeline.risk_engine import evaluate_risk


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    pytest.skip("REACT_APP_BACKEND_URL is required for public endpoint testing", allow_module_level=True)

API_BASE = f"{BASE_URL.rstrip('/')}/api"


class _FakeQuery:
    def __init__(self, payload):
        self.payload = payload

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        if isinstance(self.payload, list):
            return self.payload[0] if self.payload else None
        return self.payload

    def all(self):
        if isinstance(self.payload, list):
            return self.payload
        return []


class _FakeDB:
    def __init__(self, mapping):
        self.mapping = mapping

    def query(self, model):
        return _FakeQuery(self.mapping.get(model.__name__))


@pytest.fixture(scope="module")
def api_client():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def admin_headers(api_client):
    # module: admin auth fixture for phase3 hardening/state endpoints
    login = api_client.post(
        f"{API_BASE}/auth/login",
        json={"email": os.environ.get("TEST_ADMIN_EMAIL", ""), "password": os.environ.get("TEST_ADMIN_PASSWORD", "")},
        timeout=25,
    )
    if login.status_code != 200:
        pytest.skip(f"Admin login failed: {login.status_code}")
    token = login.json().get("access_token")
    assert isinstance(token, str) and token
    return {"Authorization": f"Bearer {token}"}


def _sample_signal(symbol: str = "BTCUSDT", direction: str = "long"):
    return SignalDecision(
        signal="long" if direction == "long" else "short",
        symbol=symbol,
        direction=direction,
        confidence=0.81,
        strategy_id="test_strategy",
        reason_codes=["test"],
        proposed_entry=100.0,
        proposed_stop=98.0 if direction == "long" else 102.0,
        proposed_take_profit=104.0 if direction == "long" else 96.0,
        timestamp=datetime.now(timezone.utc),
    )


def test_risk_engine_fallback_to_mid_cap_group_for_unmapped_symbol():
    # module: risk engine exposure group fallback (majors/high_beta -> mid_cap)
    control = SimpleNamespace(max_leverage_cap=5, max_open_positions_cap=10, max_spread_bps=80, emergency_mode=False)
    policy = SimpleNamespace(
        user_id="u1",
        updated_at=datetime.now(timezone.utc),
        spread_limit_bps=60,
        max_open_positions=6,
        max_leverage=3,
        position_size_pct=1.5,
    )
    groups = [
        SimpleNamespace(
            name="majors",
            symbols=["BTCUSDT", "ETHUSDT"],
            max_group_open_positions=8,
            max_group_directional_positions=6,
            max_group_risk_pct=50,
        ),
        SimpleNamespace(
            name="high_beta",
            symbols=["SOLUSDT", "DOGEUSDT"],
            max_group_open_positions=8,
            max_group_directional_positions=6,
            max_group_risk_pct=50,
        ),
        SimpleNamespace(
            name="mid_cap",
            symbols=[],
            max_group_open_positions=8,
            max_group_directional_positions=6,
            max_group_risk_pct=50,
        ),
    ]

    fake_db = _FakeDB(
        {
            "AdminControl": control,
            "RiskPolicy": [policy],
            "PaperPosition": [],
            "RiskExposureGroup": groups,
        }
    )

    result = evaluate_risk(
        fake_db,
        current_user=SimpleNamespace(id="u1"),
        signal=_sample_signal(symbol="XRPUSDT", direction="long"),
        market_type="spot",
        market_price=100.0,
        spread_bps=10.0,
        atr_pct=0.02,
    )

    assert result.approved is True
    assert "approved" in result.risk_tags


def test_risk_engine_blocks_directional_cluster_limit():
    # module: risk engine directional/cluster limit tagging
    control = SimpleNamespace(max_leverage_cap=5, max_open_positions_cap=10, max_spread_bps=80, emergency_mode=False)
    policy = SimpleNamespace(
        user_id="u1",
        updated_at=datetime.now(timezone.utc),
        spread_limit_bps=60,
        max_open_positions=8,
        max_leverage=3,
        position_size_pct=1.5,
    )
    groups = [
        SimpleNamespace(
            name="majors",
            symbols=["BTCUSDT", "ETHUSDT"],
            max_group_open_positions=8,
            max_group_directional_positions=2,
            max_group_risk_pct=50,
        )
    ]
    open_positions = [
        SimpleNamespace(symbol="BTCUSDT", side="long", entry_price=100.0, stop_loss=98.0, quantity=0.1, leverage=2, status="open"),
        SimpleNamespace(symbol="ETHUSDT", side="long", entry_price=100.0, stop_loss=98.0, quantity=0.1, leverage=2, status="open"),
    ]
    fake_db = _FakeDB(
        {
            "AdminControl": control,
            "RiskPolicy": [policy],
            "PaperPosition": open_positions,
            "RiskExposureGroup": groups,
        }
    )

    result = evaluate_risk(
        fake_db,
        current_user=SimpleNamespace(id="u1"),
        signal=_sample_signal(symbol="BTCUSDT", direction="long"),
        market_type="spot",
        market_price=100.0,
        spread_bps=10.0,
        atr_pct=0.02,
    )

    assert result.approved is False
    assert "directional_cluster_limit" in result.risk_tags


def test_execution_state_path_limit_fallback_then_market_flow():
    # module: execution state machine path (created->...->filled)
    states = _build_state_path(
        {
            "order_preference": "limit_first",
            "fallback_behavior": "limit_retry_then_market",
            "partial_fill_tolerance_pct": 40,
        }
    )
    assert states == ["created", "submitted", "acknowledged", "partially_filled", "fallback_submitted", "filled"]


def test_execution_state_path_cancel_flow():
    # module: execution state machine cancel terminal flow
    states = _build_state_path(
        {
            "order_preference": "limit_first",
            "fallback_behavior": "cancel_no_fill",
            "partial_fill_tolerance_pct": 80,
        }
    )
    assert states == ["created", "submitted", "acknowledged", "partially_filled", "cancel_requested", "cancelled"]


def test_admin_hardening_summary_contract(api_client, admin_headers):
    # module: admin endpoint hardening-summary
    response = api_client.get(f"{API_BASE}/admin-phase3/hardening-summary", headers=admin_headers, timeout=25)
    assert response.status_code == 200
    data = response.json()
    for key in [
        "websocket_reconnects_5m",
        "idempotency_keys_5m",
        "duplicate_signals_blocked_5m",
        "execution_transitions_5m",
        "failed_events_pending",
        "failed_events_dead",
        "last_state_rebuild_status",
    ]:
        assert key in data
    assert isinstance(data["execution_transitions_5m"], int)


def test_admin_execution_state_simulate_and_visibility(api_client, admin_headers):
    # module: admin endpoint execution-state-transitions + simulate
    simulate = api_client.post(
        f"{API_BASE}/admin-phase3/execution-state-transitions/simulate",
        params={"strategy_type": "breakout", "symbol": "BTCUSDT", "side": "long"},
        headers=admin_headers,
        timeout=25,
    )
    assert simulate.status_code == 200
    sim_data = simulate.json()

    assert isinstance(sim_data["execution_event_id"], str) and sim_data["execution_event_id"]
    assert sim_data["state_path"][0:3] == ["created", "submitted", "acknowledged"]
    assert sim_data["state_path"][-1] == sim_data["final_state"]

    transitions = api_client.get(
        f"{API_BASE}/admin-phase3/execution-state-transitions",
        params={"limit": 200},
        headers=admin_headers,
        timeout=25,
    )
    assert transitions.status_code == 200
    rows = transitions.json()
    assert isinstance(rows, list)

    same_event = [row for row in rows if row["execution_event_id"] == sim_data["execution_event_id"]]
    assert len(same_event) >= 3
    states = {row["state"] for row in same_event}
    assert "created" in states and "submitted" in states and "acknowledged" in states
