from core import go_live_checklist


def test_readiness_score_ready_when_all_components_pass(monkeypatch):
    def _fake_load(file_name: str):
        if file_name == go_live_checklist.CANARY_RUN_ARTIFACT:
            return {"status": "PASS", "pnl_summary": {"status": "ok"}, "artifact_path": "/tmp/canary.json"}
        if file_name == go_live_checklist.TESTNET_LIFECYCLE_ARTIFACT:
            return {"status": "PASS", "artifact_path": "/tmp/lifecycle.json"}
        return {}

    monkeypatch.setattr(go_live_checklist, "_load_artifact", _fake_load)
    monkeypatch.setattr(go_live_checklist, "_latest_smoke_status", lambda _db: {"run_status": "PASS", "summary": "ok", "explained": False})
    monkeypatch.setattr(go_live_checklist, "_recent_open_critical_alert_count", lambda _db, window_minutes=60: 0)

    payload = go_live_checklist.build_canary_readiness_score(db=None)

    assert payload["status"] == "READY"
    assert payload["components"]["execution"] is True
    assert payload["components"]["exchange"] is True
    assert payload["score"] >= 85


def test_go_live_checklist_blocks_when_kill_switch_validation_missing(monkeypatch):
    def _fake_load(file_name: str):
        if file_name == go_live_checklist.CANARY_RUN_ARTIFACT:
            return {"status": "PASS", "pnl_summary": {"status": "ok"}}
        if file_name == go_live_checklist.TESTNET_LIFECYCLE_ARTIFACT:
            return {"status": "PASS"}
        if file_name == go_live_checklist.KILL_SWITCH_VERIFICATION_ARTIFACT:
            return {"status": "FAIL"}
        return {}

    monkeypatch.setattr(go_live_checklist, "_load_artifact", _fake_load)
    monkeypatch.setattr(go_live_checklist, "_latest_smoke_status", lambda _db: {"run_status": "DEGRADED", "summary": "credential missing", "explained": True})
    monkeypatch.setattr(go_live_checklist, "_recent_open_critical_alert_count", lambda _db, window_minutes=60: 0)
    monkeypatch.setattr(go_live_checklist, "_queue_backlog_count", lambda _db, stale_minutes=5: 0)

    payload = go_live_checklist.evaluate_go_live_checklist(db=None)

    assert payload["go_live"] is False
    assert payload["checks"]["smoke_ok"] is True
    assert payload["checks"]["kill_switch_verified"] is False
    assert any("kill-switch" in reason for reason in payload["reasons"])