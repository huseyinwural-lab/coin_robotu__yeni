from datetime import datetime, timedelta, timezone
import uuid

from fastapi.testclient import TestClient
import pytest

from db import SessionLocal
from models import AuditLog, CommercialAlertEvent, CommercialExportSchedule
from server import fastapi_app
from services.commercial_export_scheduler_service import run_commercial_export_scheduler_cycle
from services.commercial_controls_enforcement_service import (
    CommercialControlViolation,
    enforce_commercial_control_or_raise,
)


ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


def _login(client: TestClient):
    response = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert response.status_code == 200
    data = response.json()
    token = data.get("access_token") or data.get("token")
    user_id = (data.get("user") or {}).get("id")
    assert token
    assert user_id
    return token, user_id


def _admin_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def _set_controls(client: TestClient, token: str, user_id: str, **kwargs):
    payload = {
        "trading_enabled": kwargs.get("trading_enabled", True),
        "capital_frozen": kwargs.get("capital_frozen", False),
        "withdraw_locked": kwargs.get("withdraw_locked", False),
        "emergency_stop": kwargs.get("emergency_stop", False),
        "reason_note": kwargs.get("reason_note", "test control update"),
    }
    response = client.post(f"/api/admin/commercial/controls/{user_id}", headers=_admin_headers(token), json=payload)
    assert response.status_code == 200


def _execution_submit_payload():
    return {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "size": 1.0,
        "confidence": 0.7,
        "strategy_name": "ema_rsi",
        "mark_price": 100.0,
        "leverage": 1,
    }


def _intent_preview_payload():
    return {
        "intent_type": "OPEN_POSITION",
        "market_type": "spot",
        "symbol": "BTCUSDT",
        "side": "buy",
        "order_type": "market",
        "position_size_mode": "fixed_notional",
        "position_size_value": 10,
    }


def test_operational_control_enforcement_reason_codes_and_audit_trail():
    client = TestClient(fastapi_app)
    token, user_id = _login(client)

    try:
        _set_controls(client, token, user_id, trading_enabled=False, reason_note="disable trading")
        runtime_resp = client.post("/api/runtime/execution/submit", headers=_admin_headers(token), json=_execution_submit_payload())
        assert runtime_resp.status_code == 423
        assert runtime_resp.json().get("detail", {}).get("reason_code") == "COMMERCIAL_TRADING_DISABLED"

        _set_controls(client, token, user_id, trading_enabled=True, emergency_stop=True, reason_note="emergency")
        runtime_resp = client.post("/api/runtime/execution/submit", headers=_admin_headers(token), json=_execution_submit_payload())
        assert runtime_resp.status_code == 423
        assert runtime_resp.json().get("detail", {}).get("reason_code") == "COMMERCIAL_EMERGENCY_STOP"

        _set_controls(client, token, user_id, trading_enabled=True, emergency_stop=False, capital_frozen=True, reason_note="freeze capital")
        runtime_resp = client.post("/api/runtime/execution/submit", headers=_admin_headers(token), json=_execution_submit_payload())
        assert runtime_resp.status_code == 423
        assert runtime_resp.json().get("detail", {}).get("reason_code") == "COMMERCIAL_CAPITAL_FROZEN"

        _set_controls(client, token, user_id, trading_enabled=True, capital_frozen=False, withdraw_locked=True, reason_note="lock withdraw")
        db = SessionLocal()
        try:
            with pytest.raises(CommercialControlViolation) as exc_info:
                enforce_commercial_control_or_raise(
                    db,
                    user_id=user_id,
                    operation="withdraw",
                    actor_user_id=user_id,
                    actor_role="USER",
                    entity_type="fund_withdraw_request",
                    entity_id="req-1",
                    source="test_withdraw_path",
                    metadata={"amount_usd": 10},
                )
            assert exc_info.value.reason_code == "COMMERCIAL_WITHDRAW_LOCKED"
        finally:
            db.close()

        db = SessionLocal()
        try:
            blocked_logs = (
                db.query(AuditLog)
                .filter(AuditLog.action == "COMMERCIAL_OPERATION_BLOCKED", AuditLog.actor_user_id == user_id)
                .order_by(AuditLog.created_at.desc())
                .limit(10)
                .all()
            )
            assert blocked_logs
        finally:
            db.close()
    finally:
        _set_controls(
            client,
            token,
            user_id,
            trading_enabled=True,
            capital_frozen=False,
            withdraw_locked=False,
            emergency_stop=False,
            reason_note="reset controls",
        )


def test_transition_diff_snapshot_visible_in_overview():
    client = TestClient(fastapi_app)
    token, user_id = _login(client)
    _set_controls(client, token, user_id, trading_enabled=False, emergency_stop=True, reason_note="diff test")

    response = client.get("/api/admin/commercial/overview", headers=_admin_headers(token))
    assert response.status_code == 200
    actions = response.json().get("operational_controls", {}).get("recent_actions", [])
    assert actions
    action = actions[0]
    assert "changed_fields" in action
    assert "previous_state_snapshot" in action
    assert "new_state_snapshot" in action

    _set_controls(
        client,
        token,
        user_id,
        trading_enabled=True,
        capital_frozen=False,
        withdraw_locked=False,
        emergency_stop=False,
        reason_note="reset after diff",
    )


def test_monthly_export_governance_and_artifact_linkage():
    client = TestClient(fastapi_app)
    token, _ = _login(client)

    response = client.get("/api/admin/commercial/monthly-pnl/export", headers=_admin_headers(token))
    assert response.status_code == 200
    assert response.headers.get("x-export-id")
    assert response.headers.get("x-export-file-hash")
    assert response.headers.get("x-export-artifact-ref")

    overview = client.get("/api/admin/commercial/overview", headers=_admin_headers(token))
    assert overview.status_code == 200
    manifests = overview.json().get("export_ops", {}).get("recent_manifests", [])
    assert manifests
    assert any(item.get("delivery_status") == "success" and item.get("artifact_ref") for item in manifests)


def test_scheduler_runner_executes_due_jobs_and_updates_lifecycle():
    client = TestClient(fastapi_app)
    token, _ = _login(client)

    create_resp = client.post(
        "/api/admin/commercial/exports/schedules",
        headers=_admin_headers(token),
        json={"export_type": "pnl", "schedule_period": "daily", "output_format": "csv", "filters_snapshot": {}},
    )
    assert create_resp.status_code == 200
    schedule_id = create_resp.json().get("schedule_id")
    assert schedule_id

    db = SessionLocal()
    try:
        schedule = db.query(CommercialExportSchedule).filter(CommercialExportSchedule.id == schedule_id).first()
        assert schedule is not None
        schedule.last_run_at = datetime.now(timezone.utc) - timedelta(days=2)
        schedule.last_status = "pending"
        db.commit()
    finally:
        db.close()

    run_commercial_export_scheduler_cycle()

    db = SessionLocal()
    try:
        schedule = db.query(CommercialExportSchedule).filter(CommercialExportSchedule.id == schedule_id).first()
        assert schedule is not None
        assert schedule.last_status in {"success", "failed", "pending", "running", "due"}
    finally:
        db.close()


def test_alert_lifecycle_ack_and_triage_normalization():
    client = TestClient(fastapi_app)
    token, user_id = _login(client)

    db = SessionLocal()
    try:
        alert = CommercialAlertEvent(
            alert_type="duplicate_trade_alert",
            severity="warning",
            source="commercial.alerts",
            entity_type="trade",
            entity_id="trade-1",
            title="Duplicate trade",
            message="Duplicate trade detected",
            suggested_action="",
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        alert_id = alert.id
    finally:
        db.close()

    lifecycle = client.post(
        f"/api/admin/commercial/alerts/{alert_id}/lifecycle",
        headers=_admin_headers(token),
        json={
            "triage_status": "acknowledged",
            "escalation_level": "medium",
            "resolution_note": "investigating",
            "acknowledge": True,
        },
    )
    assert lifecycle.status_code == 200
    assert lifecycle.json().get("triage_status") == "acknowledged"
    assert lifecycle.json().get("acknowledged_by") == user_id

    overview = client.get("/api/admin/commercial/overview", headers=_admin_headers(token))
    assert overview.status_code == 200
    alerts = overview.json().get("alert_rail", [])
    assert any(item.get("triage_status") in {"new", "acknowledged", "resolved"} for item in alerts)
    assert any(item.get("suggested_action") for item in alerts)
