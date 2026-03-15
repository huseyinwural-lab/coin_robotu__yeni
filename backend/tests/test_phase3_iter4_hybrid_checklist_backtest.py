"""Phase-3 Iteration-4 regression: hybrid risk/correlation, execution branches, checklist trend, and backtest insights."""

import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import requests

sys.path.append("/app/backend")

from models import AdminControl, PaperPosition, RiskExposureGroup, RiskPolicy
from services.pipeline.events import SignalDecision
from services.pipeline.execution_engine import _build_state_path
from services.pipeline.risk_engine import evaluate_risk


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    pytest.skip("REACT_APP_BACKEND_URL is required for public endpoint testing", allow_module_level=True)

API_BASE = f"{BASE_URL.rstrip('/')}/api"


@pytest.fixture(scope="session")
def api_client():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="session")
def admin_token(api_client):
    response = api_client.post(
        f"{API_BASE}/auth/login",
        json={"email": os.environ.get("TEST_ADMIN_EMAIL", ""), "password": os.environ.get("TEST_ADMIN_PASSWORD", "")},
        timeout=30,
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code}")
    return response.json()["access_token"]


@pytest.fixture(scope="session")
def viewer_token(api_client):
    response = api_client.post(
        f"{API_BASE}/auth/login",
        json={"email": "viewer01@demo.dev", "password": "Test12345!"},
        timeout=30,
    )
    if response.status_code != 200:
        pytest.skip(f"Viewer login failed: {response.status_code}")
    return response.json()["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_correlation_matrix_endpoint_window_and_schema(api_client, admin_token):
    # module: admin correlation matrix endpoint response contract
    response = api_client.get(
        f"{API_BASE}/admin-phase3/correlation-matrix?window=120",
        headers=_headers(admin_token),
        timeout=30,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["window"] == 120
    assert isinstance(payload["symbols"], list)
    assert isinstance(payload["matrix"], dict)
    if payload["symbols"]:
        first = payload["symbols"][0]
        assert payload["matrix"][first][first] == 1.0


def test_correlation_matrix_window_validation(api_client, admin_token):
    # module: correlation matrix query guard (window min/max)
    response = api_client.get(
        f"{API_BASE}/admin-phase3/correlation-matrix?window=10",
        headers=_headers(admin_token),
        timeout=30,
    )
    assert response.status_code == 422


def test_simulate_endpoint_allow_list_validation(api_client, admin_token):
    # module: simulate endpoint allow-list for outcome + side
    bad_outcome = api_client.post(
        f"{API_BASE}/admin-phase3/execution-state-transitions/simulate?outcome=unknown&side=long",
        headers=_headers(admin_token),
        timeout=30,
    )
    assert bad_outcome.status_code == 422
    assert "Invalid outcome" in bad_outcome.json()["detail"]

    bad_side = api_client.post(
        f"{API_BASE}/admin-phase3/execution-state-transitions/simulate?outcome=filled&side=up",
        headers=_headers(admin_token),
        timeout=30,
    )
    assert bad_side.status_code == 422
    assert "Invalid side" in bad_side.json()["detail"]


@pytest.mark.parametrize(
    "outcome,retry_budget,expected_final,expected_min_retry_used",
    [
        ("filled", 3, "filled", 0),
        ("partial", 2, "filled", 1),
        ("timeout", 3, "filled", 3),
        ("rejected", 2, "rejected", 0),
        ("failed", 2, "failed", 0),
    ],
)
def test_simulate_endpoint_execution_branches(api_client, admin_token, outcome, retry_budget, expected_final, expected_min_retry_used):
    # module: execution state machine branches + retry budget usage through admin simulate
    response = api_client.post(
        (
            f"{API_BASE}/admin-phase3/execution-state-transitions/simulate"
            f"?strategy_type=breakout&symbol=BTCUSDT&side=long&outcome={outcome}&retry_budget={retry_budget}"
        ),
        headers=_headers(admin_token),
        timeout=30,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["final_state"] == expected_final
    assert payload["state_path"][-1] == expected_final
    assert payload["retry_budget_used"] >= expected_min_retry_used
    if outcome == "partial":
        assert payload["partial_fill_ratio"] > 0


def test_hardening_checklist_run_latest_trend(api_client, admin_token):
    # module: hardening checklist run + latest + trend alarm schema and consistency
    run_response = api_client.post(
        f"{API_BASE}/admin-phase3/hardening-checklist/run",
        headers=_headers(admin_token),
        timeout=30,
    )
    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert "score" in run_payload
    assert "critical_blocked" in run_payload

    latest_response = api_client.get(
        f"{API_BASE}/admin-phase3/hardening-checklist/latest",
        headers=_headers(admin_token),
        timeout=30,
    )
    assert latest_response.status_code == 200
    latest = latest_response.json()
    assert latest["id"] == run_payload["id"]

    trend_response = api_client.get(
        f"{API_BASE}/admin-phase3/hardening-checklist/trend",
        headers=_headers(admin_token),
        timeout=30,
    )
    assert trend_response.status_code == 200
    trend = trend_response.json()
    assert isinstance(trend["average_score_last_5"], (int, float))
    assert isinstance(trend["critical_alarm"], bool)
    assert isinstance(trend["trend_alarm"], bool)
    assert isinstance(trend["active_alerts"], list)
    assert trend["critical_alarm"] == latest["critical_blocked"]


def test_backtest_cards_read_only_visibility_for_user(api_client, admin_token, viewer_token):
    # module: user read-only backtest insights visibility via /backtest/cards
    create_payload = {
        "strategy_type": "TEST_iter4_breakout",
        "market_type": "spot",
        "timeframe": "15m",
        "sample_size": 111,
        "win_rate": 52.1,
        "max_drawdown": 14.2,
        "profit_factor": 1.21,
        "sharpe_like_score": 0.81,
        "performance_summary": "TEST iter4 read-only card",
        "risk_label": "medium",
        "period_start": "2025-01-01",
        "period_end": "2025-12-31",
    }
    create_response = api_client.post(
        f"{API_BASE}/admin-phase3/backtest-cards",
        headers=_headers(admin_token),
        json=create_payload,
        timeout=30,
    )
    assert create_response.status_code == 200
    created = create_response.json()

    viewer_list_response = api_client.get(
        f"{API_BASE}/backtest/cards",
        headers=_headers(viewer_token),
        timeout=30,
    )
    assert viewer_list_response.status_code == 200
    cards = viewer_list_response.json()
    assert any(card["id"] == created["id"] for card in cards)


def test_monitoring_contains_correlation_rejections_metric(api_client, admin_token):
    # module: monitoring metric contract for correlation rejection visibility
    response = api_client.get(
        f"{API_BASE}/pipeline/monitoring",
        headers=_headers(admin_token),
        timeout=30,
    )
    assert response.status_code == 200
    payload = response.json()
    assert "correlation_rejections_5m" in payload
    assert isinstance(payload["correlation_rejections_5m"], int)


def test_execution_engine_state_path_retry_budget_unit():
    # module: execution engine branch logic for partial + timeout retry budget
    timeout_path = _build_state_path(
        {"fallback_behavior": "market_fallback", "retry_limit": 3},
        {"forced_outcome": "timeout"},
    )
    assert timeout_path["path"][-1] == "filled"
    assert timeout_path["retry_budget_used"] == 3

    partial_path = _build_state_path(
        {"fallback_behavior": "market_fallback", "retry_limit": 2},
        {"forced_outcome": "partial", "partial_fill_ratio": 0.42},
    )
    assert "partially_filled" in partial_path["path"]
    assert partial_path["retry_budget_used"] == 2
    assert partial_path["partial_fill_ratio"] == 0.42


class _FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return list(self.rows)


class _FakeDB:
    def __init__(self, mapping):
        self.mapping = mapping

    def query(self, model):
        return _FakeQuery(self.mapping.get(model, []))


def test_hybrid_exposure_static_group_plus_correlation_rejects(monkeypatch):
    # module: risk engine hybrid exposure (static group + rolling-correlation cluster tag)
    control = SimpleNamespace(
        id="global",
        emergency_mode=False,
        max_spread_bps=80,
        max_open_positions_cap=10,
        max_leverage_cap=5,
    )
    policy = SimpleNamespace(
        user_id="u1",
        spread_limit_bps=70,
        max_open_positions=8,
        max_leverage=3,
        position_size_pct=1.5,
    )
    group = SimpleNamespace(
        name="majors",
        symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        max_group_open_positions=2,
        max_group_directional_positions=1,
        max_group_risk_pct=100,
    )
    open_positions = [
        SimpleNamespace(
            user_id="u1",
            status="open",
            symbol="ETHUSDT",
            side="long",
            entry_price=100.0,
            stop_loss=95.0,
            quantity=1.0,
            leverage=1,
        ),
        SimpleNamespace(
            user_id="u1",
            status="open",
            symbol="SOLUSDT",
            side="long",
            entry_price=50.0,
            stop_loss=47.5,
            quantity=2.0,
            leverage=1,
        ),
    ]
    fake_db = _FakeDB(
        {
            AdminControl: [control],
            RiskPolicy: [policy],
            PaperPosition: open_positions,
            RiskExposureGroup: [group],
        }
    )

    monkeypatch.setattr("services.pipeline.risk_engine.pair_correlation", lambda *_args, **_kwargs: 0.92)

    signal = SignalDecision(
        signal="long",
        symbol="BTCUSDT",
        direction="long",
        confidence=0.8,
        strategy_id="breakout",
        reason_codes=["unit"],
        proposed_entry=100.0,
        proposed_stop=96.0,
        proposed_take_profit=108.0,
        timestamp=datetime.now(timezone.utc),
    )

    result = evaluate_risk(
        fake_db,
        current_user=SimpleNamespace(id="u1"),
        cache=None,
        signal=signal,
        market_type="spot",
        market_price=100.0,
        spread_bps=10.0,
        atr_pct=0.02,
    )

    assert result.approved is False
    assert "directional_cluster_limit" in result.risk_tags
    assert "correlated_cluster_overload" in result.risk_tags
