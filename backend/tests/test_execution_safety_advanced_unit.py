import pytest

import services.execution_safety_advanced_service as adv


class DummyDB:
    pass


def test_normalize_state_cancelled_to_canceled():
    assert adv._normalize_state("CANCELLED") == "CANCELED"
    assert adv._normalize_state("canceled") == "CANCELED"


def test_correlation_enforcement_critical_quarantine(monkeypatch):
    calls = {"upsert": 0, "audit": 0}

    def fake_upsert(*args, **kwargs):
        calls["upsert"] += 1

    def fake_audit(*args, **kwargs):
        calls["audit"] += 1

    monkeypatch.setattr(adv, "upsert_failed_event", fake_upsert)
    monkeypatch.setattr(adv, "create_audit_log", fake_audit)

    ok, result = adv._enforce_correlation_envelope(
        DummyDB(),
        envelope={"intent_id": "x", "correlation_id": "corr-x"},
        stage="order_submit",
        actor_user_id="tester",
        actor_role="admin",
        intent_id="x",
    )
    assert ok is False
    assert result["status"] == "quarantined"
    assert calls["upsert"] == 1
    assert calls["audit"] == 1


def test_correlation_enforcement_noncritical_blocked(monkeypatch):
    calls = {"upsert": 0, "audit": 0}

    def fake_upsert(*args, **kwargs):
        calls["upsert"] += 1

    def fake_audit(*args, **kwargs):
        calls["audit"] += 1

    monkeypatch.setattr(adv, "upsert_failed_event", fake_upsert)
    monkeypatch.setattr(adv, "create_audit_log", fake_audit)

    ok, result = adv._enforce_correlation_envelope(
        DummyDB(),
        envelope={"intent_id": "x", "correlation_id": "corr-x"},
        stage="read_model_update",
        actor_user_id="tester",
        actor_role="admin",
        intent_id="x",
    )
    assert ok is False
    assert result["status"] == "blocked"
    assert calls["upsert"] == 0
    assert calls["audit"] == 1


def test_acceptance_blocked_by_gate(monkeypatch):
    monkeypatch.setattr(
        adv,
        "evaluate_execution_safety_gate",
        lambda *args, **kwargs: {
            "state": "BLOCKED",
            "blockers": ["release_gate_blocked"],
            "score": 1,
            "warnings": [],
            "evaluated_at": "2026-01-01T00:00:00+00:00",
            "correlation_id": "corr-blocked",
        },
    )
    monkeypatch.setattr(adv, "_record_acceptance_artifact", lambda payload: {"artifact_id": "a1", "payload": payload})
    monkeypatch.setattr(adv, "create_audit_log", lambda *args, **kwargs: None)

    payload = adv.run_testnet_acceptance(DummyDB(), symbol="BTCUSDT", qty=0.001, requested_by="tester")
    assert payload["final_verdict"] == "BLOCKED"
    assert payload["reason_code"] == "acceptance_blocked_by_hard_gate"


def test_reconcile_missing_intent_raises():
    class Query:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return None

    class DB:
        def query(self, *args, **kwargs):
            return Query()

    with pytest.raises(ValueError):
        adv.reconcile_intent_with_exchange(DB(), intent_id="missing", actor_type="system", actor_id="x", reason="test")


def test_acceptance_history_empty_when_manifest_missing(monkeypatch):
    monkeypatch.setattr(adv, "_acceptance_manifest_items", lambda limit=50: [])
    payload = adv.get_testnet_acceptance_history(limit=10)
    assert payload["items"] == []
    assert payload["total"] == 0


def test_bulk_recovery_invalid_action_raises():
    with pytest.raises(ValueError):
        adv.run_bulk_recovery(
            DummyDB(),
            action="invalid",
            selection_mode="explicit_ids",
            intent_ids=[],
            quarantine_ids=[],
            filters={},
            reason="test",
            requested_by="tester",
        )
