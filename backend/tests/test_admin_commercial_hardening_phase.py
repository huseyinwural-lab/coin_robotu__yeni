from datetime import datetime, timedelta, timezone
import threading

from fastapi.testclient import TestClient

from db import SessionLocal
from models import CommercialAlertEvent, CommercialExportManifest, CommercialExportSchedule
from server import fastapi_app
from services import commercial_export_scheduler_service as scheduler_service
from services.admin_commercial_service import update_alert_sla_states


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
    assert any(item.get("sla_state") in {"within_sla", "warning_overdue", "critical_overdue"} for item in alerts)

    db = SessionLocal()
    try:
        assigned_row = db.query(CommercialAlertEvent).filter(CommercialAlertEvent.id == ids[0]).first()
        assert assigned_row is not None
        assert assigned_row.assigned_to_email == "owner@example.com"
        assert assigned_row.assigned_at is not None
    finally:
        db.close()


def test_export_registry_strict_validation_rejects_unknown_types_and_versions():
    client = TestClient(fastapi_app)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    bad_schedule = client.post(
        "/api/admin/commercial/exports/schedules",
        headers=headers,
        json={"export_type": "unknown_type", "schedule_period": "daily", "output_format": "csv", "filters_snapshot": {}, "max_retry": 1},
    )
    assert bad_schedule.status_code == 422

    bad_manifest = client.post(
        "/api/admin/commercial/exports/request",
        headers=headers,
        json={
            "export_type": "pnl",
            "schema_version": "v99",
            "filters_snapshot": {},
            "column_mapping": {},
            "output_format": "csv",
            "row_count": 0,
            "reason_note": "strict test",
        },
    )
    assert bad_manifest.status_code == 422


def test_scheduler_multi_runner_race_produces_single_export_manifest_window():
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
        db.query(CommercialExportSchedule).filter(CommercialExportSchedule.id != schedule_id).update(
            {CommercialExportSchedule.updated_at: datetime.now(timezone.utc)},
            synchronize_session=False,
        )
        row = db.query(CommercialExportSchedule).filter(CommercialExportSchedule.id == schedule_id).first()
        row.last_run_at = datetime.now(timezone.utc) - timedelta(days=2)
        row.last_status = "pending"
        row.claim_token = None
        row.claim_expires_at = None
        row.updated_at = datetime.now(timezone.utc) - timedelta(days=3650)
        db.commit()
    finally:
        db.close()

    barrier = threading.Barrier(2)
    failures: list[str] = []

    def _worker():
        try:
            barrier.wait(timeout=8)
            scheduler_service.run_commercial_export_scheduler_cycle()
        except Exception as exc:  # noqa: BLE001
            failures.append(str(exc))

    threads = [threading.Thread(target=_worker, daemon=True) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not failures

    db = SessionLocal()
    try:
        manifests = (
            db.query(CommercialExportManifest)
            .filter(CommercialExportManifest.idempotency_key.like(f"{schedule_id}:%"))
            .all()
        )
        non_null_keys = [row.idempotency_key for row in manifests if row.idempotency_key]
        assert len(set(non_null_keys)) == 1
        assert len(non_null_keys) == 1
    finally:
        db.close()


def test_scheduler_retry_backoff_boundary_and_disable_after_max_retry(monkeypatch):
    client = TestClient(fastapi_app)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = client.post(
        "/api/admin/commercial/exports/schedules",
        headers=headers,
        json={"export_type": "pnl", "schedule_period": "daily", "output_format": "csv", "filters_snapshot": {}, "max_retry": 1},
    )
    assert create_resp.status_code == 200
    schedule_id = create_resp.json()["schedule_id"]

    db = SessionLocal()
    try:
        db.query(CommercialExportSchedule).filter(CommercialExportSchedule.id != schedule_id).update(
            {CommercialExportSchedule.updated_at: datetime.now(timezone.utc)},
            synchronize_session=False,
        )
        row = db.query(CommercialExportSchedule).filter(CommercialExportSchedule.id == schedule_id).first()
        row.last_run_at = datetime.now(timezone.utc) - timedelta(days=2)
        row.next_retry_at = None
        row.updated_at = datetime.now(timezone.utc) - timedelta(days=3650)
        db.commit()
    finally:
        db.close()

    def _boom(*_args, **_kwargs):
        raise RuntimeError("forced_payload_failure")

    monkeypatch.setattr(scheduler_service, "_build_export_payload", _boom)

    scheduler_service.run_commercial_export_scheduler_cycle()
    db = SessionLocal()
    try:
        row = db.query(CommercialExportSchedule).filter(CommercialExportSchedule.id == schedule_id).first()
        assert row.retry_count == 1
        assert row.last_status in {"failed", "disabled"}
        assert row.next_retry_at is not None
    finally:
        db.close()

    db = SessionLocal()
    try:
        db.query(CommercialExportSchedule).filter(CommercialExportSchedule.id != schedule_id).update(
            {CommercialExportSchedule.updated_at: datetime.now(timezone.utc)},
            synchronize_session=False,
        )
        row = db.query(CommercialExportSchedule).filter(CommercialExportSchedule.id == schedule_id).first()
        row.last_run_at = datetime.now(timezone.utc) - timedelta(days=2)
        row.next_retry_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        row.updated_at = datetime.now(timezone.utc) - timedelta(days=3650)
        db.commit()
    finally:
        db.close()

    scheduler_service.run_commercial_export_scheduler_cycle()
    db = SessionLocal()
    try:
        row = db.query(CommercialExportSchedule).filter(CommercialExportSchedule.id == schedule_id).first()
        assert row.retry_count >= 2
        assert row.last_status == "disabled"
        assert row.is_active is False
    finally:
        db.close()


def test_export_registry_strict_override_allowlist_and_canonical_summary():
    client = TestClient(fastapi_app)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    invalid_override = client.post(
        "/api/admin/commercial/exports/request",
        headers=headers,
        json={
            "export_type": "monthly_pnl",
            "schema_version": "v1",
            "filters_snapshot": {"month": "2026-01"},
            "column_mapping": {"summary": ["window", "not_allowed_column"]},
            "output_format": "csv",
            "row_count": 0,
            "reason_note": "strict override invalid",
        },
    )
    assert invalid_override.status_code == 422

    valid_override = client.post(
        "/api/admin/commercial/exports/request",
        headers=headers,
        json={
            "export_type": "monthly_pnl",
            "schema_version": "v1",
            "filters_snapshot": {"month": "2026-01"},
            "column_mapping": {
                "summary": ["window", "total_pnl"],
                "users": ["user_id", "user_email", "total_pnl"],
            },
            "output_format": "csv",
            "row_count": 0,
            "reason_note": "strict override valid",
        },
    )
    assert valid_override.status_code == 200
    payload = valid_override.json()
    assert payload.get("canonical_column_mapping", {}).get("summary") == ["window", "total_pnl"]
    assert payload.get("canonical_mapping_summary", {}).get("section_count") == 2
    assert payload.get("canonical_mapping_summary", {}).get("total_columns") == 5


def test_export_retention_lifecycle_defaults_to_30_days():
    client = TestClient(fastapi_app)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    export_resp = client.get("/api/admin/commercial/monthly-pnl/export", headers=headers)
    assert export_resp.status_code == 200
    export_id = export_resp.headers.get("x-export-id")
    assert export_id

    db = SessionLocal()
    try:
        manifest = db.query(CommercialExportManifest).filter(CommercialExportManifest.id == export_id).first()
        assert manifest is not None
        assert manifest.delivery_status == "success"
        assert bool(manifest.signed_download_url)
        assert manifest.delivered_at is not None
        assert manifest.retention_expires_at is not None
        delta_days = (manifest.retention_expires_at - manifest.delivered_at).days
        assert 29 <= delta_days <= 31
    finally:
        db.close()


def test_alert_bulk_assignment_and_sla_edge_cases_property_style():
    client = TestClient(fastapi_app)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        alerts = [
            CommercialAlertEvent(
                alert_type="sla_case_recent",
                severity="warning",
                source="commercial.alerts",
                entity_type="system",
                entity_id=f"recent-{now.timestamp()}",
                title="recent",
                message="recent",
                suggested_action="check",
                created_at=now - timedelta(seconds=5),
            ),
            CommercialAlertEvent(
                alert_type="sla_case_warning",
                severity="warning",
                source="commercial.alerts",
                entity_type="system",
                entity_id=f"warning-{now.timestamp()}",
                title="warning",
                message="warning",
                suggested_action="check",
                created_at=now - timedelta(seconds=15),
            ),
            CommercialAlertEvent(
                alert_type="sla_case_critical",
                severity="critical",
                source="commercial.alerts",
                entity_type="system",
                entity_id=f"critical-{now.timestamp()}",
                title="critical",
                message="critical",
                suggested_action="check",
                created_at=now - timedelta(seconds=40),
            ),
        ]
        db.add_all(alerts)
        db.commit()
        for row in alerts:
            db.refresh(row)
        alert_ids = [row.id for row in alerts]
        update_alert_sla_states(db, warning_seconds=10, critical_seconds=30)
    finally:
        db.close()

    db = SessionLocal()
    try:
        rows = db.query(CommercialAlertEvent).filter(CommercialAlertEvent.id.in_(alert_ids)).all()
        state_map = {row.alert_type: row.sla_state for row in rows}
        assert state_map.get("sla_case_recent") == "within_sla"
        assert state_map.get("sla_case_warning") == "warning_overdue"
        assert state_map.get("sla_case_critical") == "critical_overdue"
        critical_row = next(row for row in rows if row.alert_type == "sla_case_critical")
        assert critical_row.auto_escalated is True
        assert critical_row.auto_escalated_at is not None
    finally:
        db.close()

    bulk_resp = client.post(
        "/api/admin/commercial/alerts/bulk-lifecycle",
        headers=headers,
        json={"alert_ids": alert_ids, "triage_status": "acknowledged", "escalation_level": "high", "acknowledge": True},
    )
    assert bulk_resp.status_code == 200
    assert bulk_resp.json().get("updated_count") == 3

    assign_resp = client.post(
        f"/api/admin/commercial/alerts/{alert_ids[0]}/assign",
        headers=headers,
        json={"assigned_to_user_id": "owner-pbt", "assigned_to_email": "owner.pbt@example.com", "assignment_note": "property-style assignment"},
    )
    assert assign_resp.status_code == 200
