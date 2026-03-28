from datetime import datetime, timezone
from types import SimpleNamespace

from services.trading_lifecycle_debugger_service import (
    MANDATORY_FIELDS,
    _build_lifecycle_graph,
    _explain_failure,
    normalize_audit_log_event,
    replay_lifecycle,
)


def _row(**kwargs):
    payload = {
        "id": kwargs.get("id", "1"),
        "action": kwargs.get("action", "REQUEST_RECEIVED"),
        "details": kwargs.get("details", {}),
        "created_at": kwargs.get("created_at", datetime.now(timezone.utc)),
        "severity": kwargs.get("severity", "info"),
        "actor_user_id": kwargs.get("actor_user_id", "u1"),
    }
    return SimpleNamespace(**payload)


def test_normalized_event_contains_mandatory_schema_keys():
    row = _row(
        id="evt-1",
        action="decision.signal",
        details={
            "correlation_id": "corr-1",
            "strategy_id": "s1",
            "symbol": "BTCUSDT",
            "environment": "testnet",
        },
    )
    normalized = normalize_audit_log_event(row).envelope
    for key in MANDATORY_FIELDS:
        assert key in normalized
    assert normalized["correlation_id"] == "corr-1"
    assert normalized["is_valid"] is True


def test_missing_correlation_is_visible_validation_error():
    row = _row(id="evt-2", action="risk.check", details={"strategy_id": "s1"})
    normalized = normalize_audit_log_event(row).envelope
    assert "MISSING_CORRELATION_ID" in normalized["validation_errors"]
    assert normalized["is_valid"] is False


def test_graph_marks_orphan_and_trace_incomplete():
    events = [
        {
            "event_id": "1",
            "event_type": "request.received",
            "lifecycle_stage": "request",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "parent_event_id": None,
            "severity": "INFO",
            "validation_errors": [],
        },
        {
            "event_id": "2",
            "event_type": "execution.submit",
            "lifecycle_stage": "execution",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "parent_event_id": "missing",
            "severity": "ERROR",
            "validation_errors": [],
        },
    ]
    graph = _build_lifecycle_graph(events)
    assert graph["trace_incomplete"] is True
    assert graph["broken_chain"] is True
    assert len(graph["orphans"]) == 1
    assert "intent" in graph["missing_critical_stages"]


def test_explain_failure_returns_broken_step_and_missing_context():
    events = [
        {
            "event_id": "1",
            "event_type": "request.received",
            "lifecycle_stage": "request",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": "INFO",
            "validation_errors": [],
            "causal_index": 1,
        },
        {
            "event_id": "2",
            "event_type": "risk.blocked",
            "lifecycle_stage": "risk",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": "CRITICAL",
            "validation_errors": [],
            "decision_reason": "RISK_LIMIT_EXCEEDED",
            "causal_index": 2,
        },
    ]
    graph = {
        "events": events,
        "trace_incomplete": True,
        "missing_critical_stages": ["order", "execution", "fill"],
    }
    explanation = _explain_failure(graph)
    assert explanation["broken_step"]["event_type"] == "risk.blocked"
    assert explanation["root_cause"] == "RISK_LIMIT_EXCEEDED"
    assert "trace_incomplete" in explanation["missing_context"]


def test_replay_is_deterministic_and_side_effect_safe():
    payload = {
        "correlation_id": "corr-1",
        "chain": {
            "events": [
                {
                    "event_id": "1",
                    "event_type": "request.received",
                    "timestamp": "2026-01-01T00:00:00+00:00",
                    "parent_event_id": None,
                    "severity": "INFO",
                    "validation_errors": [],
                },
                {
                    "event_id": "2",
                    "event_type": "execution.submit",
                    "timestamp": "2026-01-01T00:00:01+00:00",
                    "parent_event_id": "1",
                    "severity": "ERROR",
                    "validation_errors": [],
                    "decision_reason": "VENUE_REJECTED",
                },
            ]
        },
    }

    replay_a = replay_lifecycle(payload, snapshot_id="snap-1", run_by="admin")
    replay_b = replay_lifecycle(payload, snapshot_id="snap-1", run_by="admin")
    assert replay_a["replay_mode"] == "isolated"
    assert replay_a["external_calls_disabled"] is True
    assert replay_a["deterministic_order"] is True
    assert replay_a["side_effects_blocked"] is True
    assert replay_a["steps"] == replay_b["steps"]
    assert replay_a["break_step"]["event_id"] == "2"
