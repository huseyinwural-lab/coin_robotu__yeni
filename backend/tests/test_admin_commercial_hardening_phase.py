from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from db import SessionLocal
from models import CommercialAlertEvent, CommercialExportManifest, CommercialExportSchedule
from server import fastapi_app
from services import commercial_export_scheduler_service as scheduler_service


ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


def _login(client: TestClient):
    resp = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert resp.status_code == 200
    data = resp.json()
    token = data.get("access_token") or data.get("token")
    assert token
    return token


def test_scheduler_stale_recovery_and_retry_fields():
    client = TestClient(fastapi_app)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = client.post(
        "/api/admin/commercial/exports/schedules",
        headers=headers,
        json={"export_type": "pnl", "schedule_period": "daily", "output_format": "csv", "filters_snapshot": {}, "max_retry": 3},
    )
    assert create_resp.status_code == 200
    schedule_id = create_resp.json()["schedule_id"]

    db = SessionLocal()
    try:
        row = db.query(CommercialExportSchedule).filter(CommercialExportSchedule.id == schedule_id).first()
        row.last_status = "running"
        row.running_started_at = datetime.now(timezone.utc) - timedelta(minutes=20)
        row.claim_token = "stale-token"
        row.claim_expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        db.commit()
    finally:
        db.close()

    scheduler_service.run_commercial_export_scheduler_cycle()

    db = SessionLocal()
    try:
        row = db.query(CommercialExportSchedule).filter(CommercialExportSchedule.id == schedule_id).first()
        assert row is not None
        assert row.stale_run_flag is True
        assert row.retry_count >= 1
        assert row.next_retry_at is not None
    finally:
        db.close()


def test_scheduler_idempotency_prevents_duplicate_same_window_exports():
    client = TestClient(fastapi_app)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = client.post(
        "/api/admin/commercial/exports/schedules",
        headers=headers,
        json={"export_type": "pnl", "schedule_period": "daily", "output_format": "csv", "filters_snapshot": {}, "max_retry": 2},
    )
    assert create_resp.status_code == 200
    schedule_id = create_resp.json()["schedule_id"]

    db = SessionLocal()
    try:
        row = db.query(CommercialExportSchedule).filter(CommercialExportSchedule.id == schedule_id).first()
        row.last_run_at = datetime.now(timezone.utc) - timedelta(days=2)
        row.last_status = "pending"
        db.commit()
    finally:
        db.close()

    scheduler_service.run_commercial_export_scheduler_cycle()
    scheduler_service.run_commercial_export_scheduler_cycle()

    db = SessionLocal()
    try:
        manifests = (
            db.query(CommercialExportManifest)
            .filter(CommercialExportManifest.idempotency_key.like(f"{schedule_id}:%"))
            .all()
        )
        unique_keys = {row.idempotency_key for row in manifests}
        assert len(unique_keys) <= 1
    finally:
        db.close()


def test_alert_bulk_assignment_and_sla_surface():
    client = TestClient(fastapi_app)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    db = SessionLocal()
    try:
        alert_a = CommercialAlertEvent(
            alert_type="pnl_threshold_breach",
            severity="warning",
            source="commercial.alerts",
            entity_type="user",
            entity_id="u-1",
            title="A",
            message="A",
            suggested_action="Investigate",
            created_at=datetime.now(timezone.utc) - timedelta(hours=5),
        )
        alert_b = CommercialAlertEvent(
            alert_type="data_freshness_alert",
            severity="warning",
            source="commercial.alerts",
            entity_type="system",
            entity_id="s-1",
            title="B",
            message="B",
            suggested_action="Investigate",
            created_at=datetime.now(timezone.utc) - timedelta(minutes=30),
        )
        db.add_all([alert_a, alert_b])
        db.commit()
        db.refresh(alert_a)
        db.refresh(alert_b)
        ids = [alert_a.id, alert_b.id]
    finally:
        db.close()

    bulk_resp = client.post(
        "/api/admin/commercial/alerts/bulk-lifecycle",
        headers=headers,
        json={"alert_ids": ids, "triage_status": "acknowledged", "escalation_level": "medium", "acknowledge": True},
    )
    assert bulk_resp.status_code == 200
    assert bulk_resp.json()["updated_count"] == 2

    assign_resp = client.post(
        f"/api/admin/commercial/alerts/{ids[0]}/assign",
        headers=headers,
        json={"assigned_to_user_id": "owner-1", "assigned_to_email": "owner@example.com", "assignment_note": "take ownership"},
    )
    assert assign_resp.status_code == 200

    overview = client.get("/api/admin/commercial/overview", headers=headers)
    assert overview.status_code == 200
    alerts = overview.json().get("alert_rail", [])
    assert any(item.get("triage_status") == "acknowledged" for item in alerts)
    assert any(item.get("assigned_to_email") == "owner@example.com" for item in alerts)
    assert any(item.get("sla_state") in {"within_sla", "warning_overdue", "critical_overdue"} for item in alerts)
