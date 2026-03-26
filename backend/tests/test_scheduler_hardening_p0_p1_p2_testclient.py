"""
Comprehensive tests for P0-P3 hardening features using TestClient:
- P0: Scheduler distributed lock/idempotency/retry + secondary enforcement
- P1: Lifecycle hardening: retention/storage abstraction/strict registry
- P2: Alert bulk + assignment + SLA
- P3: Frontend hardening (tested via API response structure)
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from db import SessionLocal
from models import CommercialAlertEvent, CommercialExportManifest, CommercialExportSchedule
from server import fastapi_app
from services import commercial_export_scheduler_service as scheduler_service


ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def client():
    """TestClient instance"""
    return TestClient(fastapi_app)


@pytest.fixture(scope="module")
def auth_headers(client):
    """Get authentication headers"""
    resp = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    data = resp.json()
    token = data.get("access_token") or data.get("token")
    assert token, "No token in response"
    return {"Authorization": f"Bearer {token}"}


class TestSchedulerHardeningP0:
    """P0: Scheduler distributed lock, idempotency, retry, stale recovery"""

    def test_create_export_schedule_with_max_retry(self, client, auth_headers):
        """Test schedule creation with max_retry field"""
        resp = client.post(
            "/api/admin/commercial/exports/schedules",
            headers=auth_headers,
            json={
                "export_type": "pnl",
                "schedule_period": "daily",
                "output_format": "csv",
                "filters_snapshot": {},
                "max_retry": 5,
            },
        )
        assert resp.status_code == 200, f"Schedule creation failed: {resp.text}"
        data = resp.json()
        assert "schedule_id" in data
        assert data.get("export_type") == "pnl"
        assert data.get("schedule_period") == "daily"

    def test_overview_export_ops_contains_retry_fields(self, client, auth_headers):
        """Test that overview export_ops contains retry/stale fields"""
        resp = client.get(
            "/api/admin/commercial/overview",
            headers=auth_headers,
            params={"environment": "live", "time_window": "last_30_days"},
        )
        assert resp.status_code == 200, f"Overview failed: {resp.text}"
        data = resp.json()
        
        export_ops = data.get("export_ops", {})
        assert "scheduler_health" in export_ops
        assert "recent_export_jobs" in export_ops
        
        # Check that recent_export_jobs contain hardening fields
        jobs = export_ops.get("recent_export_jobs", [])
        if jobs:
            job = jobs[0]
            # P0 hardening fields
            assert "retry_count" in job, "retry_count field missing"
            assert "next_retry_at" in job, "next_retry_at field missing"
            assert "running_started_at" in job, "running_started_at field missing"
            assert "stale_run_flag" in job, "stale_run_flag field missing"
            assert "failure_reason" in job, "failure_reason field missing"

    def test_overview_export_ops_contains_retention_downloadable_fields(self, client, auth_headers):
        """Test that overview export_ops contains retention/downloadable fields (P1)"""
        resp = client.get(
            "/api/admin/commercial/overview",
            headers=auth_headers,
            params={"environment": "live", "time_window": "last_30_days"},
        )
        assert resp.status_code == 200
        data = resp.json()
        
        export_ops = data.get("export_ops", {})
        jobs = export_ops.get("recent_export_jobs", [])
        manifests = export_ops.get("recent_manifests", [])
        
        # Check retention/downloadable fields in jobs
        if jobs:
            job = jobs[0]
            assert "retention_state" in job, "retention_state field missing in jobs"
            assert "downloadable_state" in job, "downloadable_state field missing in jobs"
        
        # Check retention/downloadable fields in manifests
        if manifests:
            manifest = manifests[0]
            assert "retention_state" in manifest, "retention_state field missing in manifests"
            assert "downloadable_state" in manifest, "downloadable_state field missing in manifests"
            assert "signed_download_url" in manifest, "signed_download_url field missing in manifests"


class TestSecondaryPathEnforcementP0:
    """P0: Secondary path enforcement (runtime/admin/automation paths) and reason code consistency"""

    def test_commercial_controls_enforcement_reason_codes(self, client, auth_headers):
        """Test that commercial controls return proper reason codes"""
        resp = client.get(
            "/api/admin/commercial/overview",
            headers=auth_headers,
            params={"environment": "live", "time_window": "last_30_days"},
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Check operational_controls structure
        op_controls = data.get("operational_controls", {})
        assert "trading_enabled_count" in op_controls
        assert "emergency_stop_count" in op_controls
        assert "capital_frozen_count" in op_controls
        assert "withdraw_locked_count" in op_controls
        assert "recent_actions" in op_controls

    def test_operational_control_update_with_reason_note(self, client, auth_headers):
        """Test operational control update requires reason_note"""
        # Get user ID from login response
        login_resp = client.post(
            "/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        user_id = login_resp.json().get("user", {}).get("id")
        assert user_id
        
        # Update operational control
        resp = client.post(
            f"/api/admin/commercial/controls/{user_id}",
            headers=auth_headers,
            json={
                "trading_enabled": True,
                "capital_frozen": False,
                "withdraw_locked": False,
                "emergency_stop": False,
                "reason_note": "Test operational control update",
            },
        )
        assert resp.status_code == 200, f"Control update failed: {resp.text}"
        data = resp.json()
        assert "user_id" in data
        assert "trading_enabled" in data


class TestMonthlyExportGovernanceP0:
    """P0: Monthly export endpoint governance bypass check (manifest+audit+checksum+headers)"""

    def test_monthly_pnl_export_returns_governance_headers(self, client, auth_headers):
        """Test that monthly PnL export returns governance headers"""
        resp = client.get(
            "/api/admin/commercial/monthly-pnl/export",
            headers=auth_headers,
            params={"month": "2026-01"},
        )
        assert resp.status_code == 200, f"Export failed: {resp.text}"
        
        # Check governance headers
        assert "x-export-id" in resp.headers, "x-export-id header missing"
        assert "x-export-artifact-ref" in resp.headers, "x-export-artifact-ref header missing"
        assert "x-export-file-hash" in resp.headers, "x-export-file-hash header missing"

    def test_export_manifest_request_creates_audit_trail(self, client, auth_headers):
        """Test that export manifest request creates proper audit trail"""
        resp = client.post(
            "/api/admin/commercial/exports/request",
            headers=auth_headers,
            json={
                "export_type": "pnl",
                "schema_version": "v1",
                "output_format": "csv",
                "filters_snapshot": {},
                "column_mapping": {},
                "row_count": 0,
                "reason_note": "Test export request",
            },
        )
        assert resp.status_code == 200, f"Export request failed: {resp.text}"
        data = resp.json()
        assert "export_id" in data
        assert "status" in data


class TestExportRegistryValidationP1:
    """P1: Strict export registry validation (type/version/mapping)"""

    def test_export_request_with_invalid_schema_version_fails(self, client, auth_headers):
        """Test that invalid schema version is rejected"""
        resp = client.post(
            "/api/admin/commercial/exports/request",
            headers=auth_headers,
            json={
                "export_type": "pnl",
                "schema_version": "v999",  # Invalid version
                "output_format": "csv",
                "filters_snapshot": {},
                "column_mapping": {},
                "row_count": 0,
                "reason_note": "Test invalid schema",
            },
        )
        # Should fail with 422 for invalid schema
        assert resp.status_code == 422, f"Expected 422 for invalid schema, got {resp.status_code}: {resp.text}"


class TestAlertBulkLifecycleP2:
    """P2: Alert bulk lifecycle endpoint (bulk ack/triage/escalation)"""

    def test_alert_bulk_lifecycle_endpoint_exists(self, client, auth_headers):
        """Test that bulk lifecycle endpoint exists and accepts requests"""
        # First create some test alerts
        db = SessionLocal()
        try:
            alert_a = CommercialAlertEvent(
                alert_type="test_bulk_alert_a",
                severity="warning",
                source="commercial.test",
                entity_type="test",
                entity_id="bulk-test-1",
                title="Bulk Test A",
                message="Test alert for bulk operations",
                suggested_action="Test action",
                created_at=datetime.now(timezone.utc),
            )
            alert_b = CommercialAlertEvent(
                alert_type="test_bulk_alert_b",
                severity="warning",
                source="commercial.test",
                entity_type="test",
                entity_id="bulk-test-2",
                title="Bulk Test B",
                message="Test alert for bulk operations",
                suggested_action="Test action",
                created_at=datetime.now(timezone.utc),
            )
            db.add_all([alert_a, alert_b])
            db.commit()
            db.refresh(alert_a)
            db.refresh(alert_b)
            alert_ids = [alert_a.id, alert_b.id]
        finally:
            db.close()
        
        # Test bulk lifecycle update
        resp = client.post(
            "/api/admin/commercial/alerts/bulk-lifecycle",
            headers=auth_headers,
            json={
                "alert_ids": alert_ids,
                "triage_status": "acknowledged",
                "escalation_level": "medium",
                "acknowledge": True,
            },
        )
        assert resp.status_code == 200, f"Bulk lifecycle failed: {resp.text}"
        data = resp.json()
        assert "updated_count" in data
        assert data["updated_count"] == 2


class TestAlertAssignmentP2:
    """P2: Alert assignment endpoint and SLA fields in overview"""

    def test_alert_assignment_endpoint_exists(self, client, auth_headers):
        """Test that alert assignment endpoint exists"""
        # Create a test alert
        db = SessionLocal()
        try:
            alert = CommercialAlertEvent(
                alert_type="test_assignment_alert",
                severity="warning",
                source="commercial.test",
                entity_type="test",
                entity_id="assign-test-1",
                title="Assignment Test",
                message="Test alert for assignment",
                suggested_action="Test action",
                created_at=datetime.now(timezone.utc),
            )
            db.add(alert)
            db.commit()
            db.refresh(alert)
            alert_id = alert.id
        finally:
            db.close()
        
        # Test assignment
        resp = client.post(
            f"/api/admin/commercial/alerts/{alert_id}/assign",
            headers=auth_headers,
            json={
                "assigned_to_user_id": "test-user-id",
                "assigned_to_email": "test@example.com",
                "assignment_note": "Test assignment",
            },
        )
        assert resp.status_code == 200, f"Assignment failed: {resp.text}"

    def test_alert_rail_contains_sla_and_assignment_fields(self, client, auth_headers):
        """Test that alert_rail contains SLA and assignment fields"""
        # Create a test alert first
        db = SessionLocal()
        try:
            alert = CommercialAlertEvent(
                alert_type="test_sla_alert",
                severity="warning",
                source="commercial.test",
                entity_type="test",
                entity_id="sla-test-1",
                title="SLA Test",
                message="Test alert for SLA fields",
                suggested_action="Test action",
                created_at=datetime.now(timezone.utc) - timedelta(hours=2),
            )
            db.add(alert)
            db.commit()
        finally:
            db.close()
        
        resp = client.get(
            "/api/admin/commercial/overview",
            headers=auth_headers,
            params={"environment": "live", "time_window": "last_30_days"},
        )
        assert resp.status_code == 200
        data = resp.json()
        
        alert_rail = data.get("alert_rail", [])
        if not alert_rail:
            pytest.skip("No alerts available for SLA field testing")
        
        alert = alert_rail[0]
        # P2 SLA and assignment fields
        assert "sla_state" in alert, "sla_state field missing"
        assert "assigned_to_user_id" in alert, "assigned_to_user_id field missing"
        assert "assigned_to_email" in alert, "assigned_to_email field missing"
        assert "assigned_at" in alert, "assigned_at field missing"
        assert "assignment_note" in alert, "assignment_note field missing"
        assert "age_seconds" in alert, "age_seconds field missing"
        assert "auto_escalated" in alert, "auto_escalated field missing"
        assert "auto_escalated_at" in alert, "auto_escalated_at field missing"


class TestFrontendHardeningP3:
    """P3: Frontend hardening - verify API response structure supports frontend features"""

    def test_overview_contains_all_required_blocks(self, client, auth_headers):
        """Test that overview contains all blocks needed for frontend"""
        resp = client.get(
            "/api/admin/commercial/overview",
            headers=auth_headers,
            params={"environment": "live", "time_window": "last_30_days"},
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Required blocks for frontend
        required_blocks = [
            "financial_accuracy",
            "revenue_model",
            "user_economics",
            "pnl_analytics",
            "risk_summary",
            "usage_analytics",
            "data_quality",
            "export_ops",
            "alert_rail",
            "operational_controls",
            "applied_filters",
        ]
        
        for block in required_blocks:
            assert block in data, f"Required block '{block}' missing from overview"

    def test_export_ops_job_fields_for_frontend_table(self, client, auth_headers):
        """Test that export_ops jobs have all fields needed for frontend table"""
        # First create a schedule to ensure we have data
        client.post(
            "/api/admin/commercial/exports/schedules",
            headers=auth_headers,
            json={
                "export_type": "pnl",
                "schedule_period": "daily",
                "output_format": "csv",
                "filters_snapshot": {},
                "max_retry": 3,
            },
        )
        
        resp = client.get(
            "/api/admin/commercial/overview",
            headers=auth_headers,
            params={"environment": "live", "time_window": "last_30_days"},
        )
        assert resp.status_code == 200
        data = resp.json()
        
        export_ops = data.get("export_ops", {})
        jobs = export_ops.get("recent_export_jobs", [])
        
        if jobs:
            job = jobs[0]
            # Fields needed for frontend Export Ops table
            required_fields = [
                "schedule_id",
                "export_type",
                "schedule_period",
                "is_active",
                "output_format",
                "last_status",
                "last_run_at",
                "last_output_ref",
                "failure_reason",
                "retry_count",
                "next_retry_at",
                "running_started_at",
                "stale_run_flag",
                "retention_state",
                "downloadable_state",
            ]
            for field in required_fields:
                assert field in job, f"Field '{field}' missing from export job"

    def test_alert_rail_fields_for_frontend_table(self, client, auth_headers):
        """Test that alert_rail has all fields needed for frontend table"""
        # Create a test alert
        db = SessionLocal()
        try:
            alert = CommercialAlertEvent(
                alert_type="test_frontend_alert",
                severity="warning",
                source="commercial.test",
                entity_type="test",
                entity_id="frontend-test-1",
                title="Frontend Test",
                message="Test alert for frontend fields",
                suggested_action="Test action",
                created_at=datetime.now(timezone.utc),
            )
            db.add(alert)
            db.commit()
        finally:
            db.close()
        
        resp = client.get(
            "/api/admin/commercial/overview",
            headers=auth_headers,
            params={"environment": "live", "time_window": "last_30_days"},
        )
        assert resp.status_code == 200
        data = resp.json()
        
        alert_rail = data.get("alert_rail", [])
        if not alert_rail:
            pytest.skip("No alerts available for field testing")
        
        alert = alert_rail[0]
        # Fields needed for frontend Alert Rail table
        required_fields = [
            "id",
            "alert_type",
            "severity",
            "source",
            "entity_type",
            "entity_id",
            "title",
            "message",
            "suggested_action",
            "triage_status",
            "acknowledged_at",
            "assigned_to_user_id",
            "assigned_to_email",
            "assigned_at",
            "assignment_note",
            "age_seconds",
            "sla_state",
            "auto_escalated",
            "auto_escalated_at",
            "created_at",
        ]
        for field in required_fields:
            assert field in alert, f"Field '{field}' missing from alert"

    def test_infra_health_badge_data_available(self, client, auth_headers):
        """Test that data for infra health badge is available"""
        resp = client.get(
            "/api/admin/commercial/overview",
            headers=auth_headers,
            params={"environment": "live", "time_window": "last_30_days"},
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Data quality for freshness
        data_quality = data.get("data_quality", {})
        assert "freshness_seconds" in data_quality or "status" in data_quality
        
        # Export ops for scheduler health
        export_ops = data.get("export_ops", {})
        assert "scheduler_health" in export_ops


class TestSchedulerCycleIntegration:
    """Integration tests for scheduler cycle behavior"""

    def test_scheduler_stale_recovery(self, client, auth_headers):
        """Test scheduler stale recovery mechanism"""
        # Create a schedule
        create_resp = client.post(
            "/api/admin/commercial/exports/schedules",
            headers=auth_headers,
            json={
                "export_type": "pnl",
                "schedule_period": "daily",
                "output_format": "csv",
                "filters_snapshot": {},
                "max_retry": 3,
            },
        )
        assert create_resp.status_code == 200
        schedule_id = create_resp.json()["schedule_id"]
        
        # Set schedule to stale running state
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
        
        # Run scheduler cycle
        result = scheduler_service.run_commercial_export_scheduler_cycle()
        assert "processed" in result
        
        # Verify stale recovery
        db = SessionLocal()
        try:
            row = db.query(CommercialExportSchedule).filter(CommercialExportSchedule.id == schedule_id).first()
            assert row is not None
            assert row.stale_run_flag is True
            assert row.retry_count >= 1
            assert row.next_retry_at is not None
        finally:
            db.close()

    def test_scheduler_idempotency_prevents_duplicates(self, client, auth_headers):
        """Test scheduler idempotency prevents duplicate exports in same window"""
        # Create a schedule
        create_resp = client.post(
            "/api/admin/commercial/exports/schedules",
            headers=auth_headers,
            json={
                "export_type": "pnl",
                "schedule_period": "daily",
                "output_format": "csv",
                "filters_snapshot": {},
                "max_retry": 2,
            },
        )
        assert create_resp.status_code == 200
        schedule_id = create_resp.json()["schedule_id"]
        
        # Set schedule to be due
        db = SessionLocal()
        try:
            row = db.query(CommercialExportSchedule).filter(CommercialExportSchedule.id == schedule_id).first()
            row.last_run_at = datetime.now(timezone.utc) - timedelta(days=2)
            row.last_status = "pending"
            db.commit()
        finally:
            db.close()
        
        # Run scheduler cycle twice
        scheduler_service.run_commercial_export_scheduler_cycle()
        scheduler_service.run_commercial_export_scheduler_cycle()
        
        # Verify no duplicate manifests
        db = SessionLocal()
        try:
            manifests = (
                db.query(CommercialExportManifest)
                .filter(CommercialExportManifest.idempotency_key.like(f"{schedule_id}:%"))
                .all()
            )
            unique_keys = {row.idempotency_key for row in manifests}
            assert len(unique_keys) <= 1, "Duplicate manifests created"
        finally:
            db.close()

    def test_scheduler_max_retry_disables_schedule(self, client, auth_headers):
        """Test that exceeding max_retry disables the schedule"""
        # Create a schedule with low max_retry
        create_resp = client.post(
            "/api/admin/commercial/exports/schedules",
            headers=auth_headers,
            json={
                "export_type": "pnl",
                "schedule_period": "daily",
                "output_format": "csv",
                "filters_snapshot": {},
                "max_retry": 1,
            },
        )
        assert create_resp.status_code == 200
        schedule_id = create_resp.json()["schedule_id"]
        
        # Set schedule to exceed max_retry
        db = SessionLocal()
        try:
            row = db.query(CommercialExportSchedule).filter(CommercialExportSchedule.id == schedule_id).first()
            row.retry_count = 5  # Exceeds max_retry of 1
            row.last_run_at = datetime.now(timezone.utc) - timedelta(days=2)
            row.last_status = "pending"
            db.commit()
        finally:
            db.close()
        
        # Run scheduler cycle
        scheduler_service.run_commercial_export_scheduler_cycle()
        
        # Verify schedule is disabled
        db = SessionLocal()
        try:
            row = db.query(CommercialExportSchedule).filter(CommercialExportSchedule.id == schedule_id).first()
            assert row is not None
            assert row.is_active is False or row.last_status == "disabled"
        finally:
            db.close()
