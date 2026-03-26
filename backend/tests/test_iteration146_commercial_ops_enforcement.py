"""
Iteration 146: Commercial Ops Enforcement and Lifecycle Testing

Tests for:
- Operational controls enforcement: trade intent ve runtime submit path reject reason code
- Reason code standards: COMMERCIAL_TRADING_DISABLED / COMMERCIAL_EMERGENCY_STOP / COMMERCIAL_CAPITAL_FROZEN / COMMERCIAL_WITHDRAW_LOCKED
- Transition diff snapshot fields and overview operational_controls.recent_actions visibility
- Monthly export endpoint governance chain: manifest+audit+checksum+headers (x-export-id/x-export-file-hash/x-export-artifact-ref)
- Export scheduler polling/runner lifecycle: pending/due/running/success|failed updates
- Export artifact linkage: manifest/audit/delivered_at/file_hash/artifact_ref
- Alert lifecycle endpoint: ack/triage/resolution fields
- Alert normalization: severity/source/entity/suggested_action not empty
"""

from datetime import datetime, timedelta, timezone
import uuid

from fastapi.testclient import TestClient
import pytest

from db import SessionLocal
from models import (
    AuditLog,
    CommercialAlertEvent,
    CommercialExportAudit,
    CommercialExportManifest,
    CommercialExportSchedule,
    CommercialOperationalControlState,
    CommercialOperationalControlTransition,
    User,
)
from server import fastapi_app
from services.commercial_export_scheduler_service import run_commercial_export_scheduler_cycle
from services.commercial_controls_enforcement_service import (
    COMMERCIAL_CAPITAL_FROZEN,
    COMMERCIAL_EMERGENCY_STOP,
    COMMERCIAL_TRADING_DISABLED,
    COMMERCIAL_WITHDRAW_LOCKED,
    CommercialControlViolation,
    enforce_commercial_control_or_raise,
    get_user_operational_control_state,
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
    return response.json()


def _reset_controls(client: TestClient, token: str, user_id: str):
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


# ============================================================================
# T-01: Operational Controls Enforcement - Reason Code Standards
# ============================================================================

class TestOperationalControlsEnforcementReasonCodes:
    """Test all 4 reason codes: COMMERCIAL_TRADING_DISABLED, COMMERCIAL_EMERGENCY_STOP, COMMERCIAL_CAPITAL_FROZEN, COMMERCIAL_WITHDRAW_LOCKED"""

    def test_trading_disabled_reason_code_on_runtime_submit(self):
        """T-01a: trading_enabled=false should return COMMERCIAL_TRADING_DISABLED on runtime submit"""
        client = TestClient(fastapi_app)
        token, user_id = _login(client)
        try:
            _set_controls(client, token, user_id, trading_enabled=False, reason_note="disable trading test")
            
            payload = {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "size": 1.0,
                "confidence": 0.7,
                "strategy_name": "ema_rsi",
                "mark_price": 100.0,
                "leverage": 1,
            }
            response = client.post("/api/runtime/execution/submit", headers=_admin_headers(token), json=payload)
            assert response.status_code == 423
            detail = response.json().get("detail", {})
            assert detail.get("reason_code") == COMMERCIAL_TRADING_DISABLED
        finally:
            _reset_controls(client, token, user_id)

    def test_emergency_stop_reason_code_on_runtime_submit(self):
        """T-01b: emergency_stop=true should return COMMERCIAL_EMERGENCY_STOP on runtime submit"""
        client = TestClient(fastapi_app)
        token, user_id = _login(client)
        try:
            _set_controls(client, token, user_id, trading_enabled=True, emergency_stop=True, reason_note="emergency stop test")
            
            payload = {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "size": 1.0,
                "confidence": 0.7,
                "strategy_name": "ema_rsi",
                "mark_price": 100.0,
                "leverage": 1,
            }
            response = client.post("/api/runtime/execution/submit", headers=_admin_headers(token), json=payload)
            assert response.status_code == 423
            detail = response.json().get("detail", {})
            assert detail.get("reason_code") == COMMERCIAL_EMERGENCY_STOP
        finally:
            _reset_controls(client, token, user_id)

    def test_capital_frozen_reason_code_on_runtime_submit(self):
        """T-01c: capital_frozen=true should return COMMERCIAL_CAPITAL_FROZEN on runtime submit"""
        client = TestClient(fastapi_app)
        token, user_id = _login(client)
        try:
            _set_controls(client, token, user_id, trading_enabled=True, capital_frozen=True, reason_note="freeze capital test")
            
            payload = {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "size": 1.0,
                "confidence": 0.7,
                "strategy_name": "ema_rsi",
                "mark_price": 100.0,
                "leverage": 1,
            }
            response = client.post("/api/runtime/execution/submit", headers=_admin_headers(token), json=payload)
            assert response.status_code == 423
            detail = response.json().get("detail", {})
            assert detail.get("reason_code") == COMMERCIAL_CAPITAL_FROZEN
        finally:
            _reset_controls(client, token, user_id)

    def test_withdraw_locked_reason_code_on_withdraw_operation(self):
        """T-01d: withdraw_locked=true should return COMMERCIAL_WITHDRAW_LOCKED on withdraw operation"""
        client = TestClient(fastapi_app)
        token, user_id = _login(client)
        try:
            _set_controls(client, token, user_id, trading_enabled=True, withdraw_locked=True, reason_note="lock withdraw test")
            
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
                        entity_id="req-test",
                        source="test_withdraw_path",
                        metadata={"amount_usd": 100},
                    )
                assert exc_info.value.reason_code == COMMERCIAL_WITHDRAW_LOCKED
            finally:
                db.close()
        finally:
            _reset_controls(client, token, user_id)


# ============================================================================
# T-02: Transition Diff Snapshot Fields
# ============================================================================

class TestTransitionDiffSnapshotFields:
    """Test transition diff snapshot fields: changed_fields, previous_state_snapshot, new_state_snapshot"""

    def test_transition_diff_fields_present_in_overview(self):
        """T-02a: Transition diff fields should be visible in overview operational_controls.recent_actions"""
        client = TestClient(fastapi_app)
        token, user_id = _login(client)
        
        # Make a control change to create a transition
        _set_controls(client, token, user_id, trading_enabled=False, emergency_stop=True, reason_note="diff test")
        
        response = client.get("/api/admin/commercial/overview", headers=_admin_headers(token))
        assert response.status_code == 200
        
        actions = response.json().get("operational_controls", {}).get("recent_actions", [])
        assert actions, "recent_actions should not be empty"
        
        action = actions[0]
        assert "changed_fields" in action, "changed_fields should be present"
        assert "previous_state_snapshot" in action, "previous_state_snapshot should be present"
        assert "new_state_snapshot" in action, "new_state_snapshot should be present"
        assert "transition_id" in action, "transition_id should be present"
        assert "user_id" in action, "user_id should be present"
        assert "actor_user_id" in action, "actor_user_id should be present"
        assert "reason_note" in action, "reason_note should be present"
        
        _reset_controls(client, token, user_id)

    def test_transition_diff_fields_in_database(self):
        """T-02b: Transition diff fields should be stored in database"""
        client = TestClient(fastapi_app)
        token, user_id = _login(client)
        
        _set_controls(client, token, user_id, trading_enabled=False, capital_frozen=True, reason_note="db diff test")
        
        db = SessionLocal()
        try:
            transition = (
                db.query(CommercialOperationalControlTransition)
                .filter(CommercialOperationalControlTransition.user_id == user_id)
                .order_by(CommercialOperationalControlTransition.created_at.desc())
                .first()
            )
            assert transition is not None
            assert transition.changed_fields is not None
            assert transition.previous_state_snapshot is not None
            assert transition.new_state_snapshot is not None
        finally:
            db.close()
        
        _reset_controls(client, token, user_id)


# ============================================================================
# T-03: Monthly Export Governance Chain
# ============================================================================

class TestMonthlyExportGovernanceChain:
    """Test monthly export endpoint governance: manifest+audit+checksum+headers"""

    def test_monthly_export_returns_governance_headers(self):
        """T-03a: Monthly export should return x-export-id, x-export-file-hash, x-export-artifact-ref headers"""
        client = TestClient(fastapi_app)
        token, _ = _login(client)
        
        response = client.get("/api/admin/commercial/monthly-pnl/export", headers=_admin_headers(token))
        assert response.status_code == 200
        
        # Check governance headers
        assert response.headers.get("x-export-id"), "x-export-id header should be present"
        assert response.headers.get("x-export-file-hash"), "x-export-file-hash header should be present"
        assert response.headers.get("x-export-artifact-ref"), "x-export-artifact-ref header should be present"
        
        # Check content type
        assert "spreadsheetml" in response.headers.get("content-type", ""), "Content type should be xlsx"

    def test_monthly_export_creates_manifest_and_audit(self):
        """T-03b: Monthly export should create manifest and audit records"""
        client = TestClient(fastapi_app)
        token, _ = _login(client)
        
        response = client.get("/api/admin/commercial/monthly-pnl/export", headers=_admin_headers(token))
        assert response.status_code == 200
        
        export_id = response.headers.get("x-export-id")
        assert export_id
        
        db = SessionLocal()
        try:
            manifest = db.query(CommercialExportManifest).filter(CommercialExportManifest.id == export_id).first()
            assert manifest is not None
            assert manifest.status == "delivered"
            assert manifest.delivery_status == "success"
            assert manifest.file_hash is not None
            assert manifest.artifact_ref is not None
            assert manifest.delivered_at is not None
            
            audit = db.query(CommercialExportAudit).filter(CommercialExportAudit.export_id == export_id).first()
            assert audit is not None
            assert audit.file_hash is not None
            assert audit.artifact_ref is not None
            assert audit.delivery_status == "success"
        finally:
            db.close()


# ============================================================================
# T-04: Export Scheduler Polling/Runner Lifecycle
# ============================================================================

class TestExportSchedulerLifecycle:
    """Test export scheduler lifecycle: pending/due/running/success|failed"""

    def test_scheduler_creates_schedule_and_runs(self):
        """T-04a: Scheduler should create schedule and run due jobs"""
        client = TestClient(fastapi_app)
        token, _ = _login(client)
        
        # Create a schedule
        create_resp = client.post(
            "/api/admin/commercial/exports/schedules",
            headers=_admin_headers(token),
            json={"export_type": "pnl", "schedule_period": "daily", "output_format": "csv", "filters_snapshot": {}},
        )
        assert create_resp.status_code == 200
        schedule_id = create_resp.json().get("schedule_id")
        assert schedule_id
        
        # Make the schedule due by setting last_run_at to past
        db = SessionLocal()
        try:
            schedule = db.query(CommercialExportSchedule).filter(CommercialExportSchedule.id == schedule_id).first()
            assert schedule is not None
            schedule.last_run_at = datetime.now(timezone.utc) - timedelta(days=2)
            schedule.last_status = "pending"
            db.commit()
        finally:
            db.close()
        
        # Run scheduler cycle
        cycle_result = run_commercial_export_scheduler_cycle()
        assert cycle_result.get("processed", 0) >= 1
        
        # Verify schedule status updated
        db = SessionLocal()
        try:
            schedule = db.query(CommercialExportSchedule).filter(CommercialExportSchedule.id == schedule_id).first()
            assert schedule is not None
            assert schedule.last_status in {"success", "failed"}
        finally:
            db.close()

    def test_scheduler_lifecycle_visible_in_overview(self):
        """T-04b: Scheduler lifecycle should be visible in overview export_ops"""
        client = TestClient(fastapi_app)
        token, _ = _login(client)
        
        response = client.get("/api/admin/commercial/overview", headers=_admin_headers(token))
        assert response.status_code == 200
        
        export_ops = response.json().get("export_ops", {})
        assert "scheduler_health" in export_ops
        assert "pending_exports" in export_ops
        assert "delivered_exports" in export_ops
        assert "recent_export_jobs" in export_ops
        assert "recent_manifests" in export_ops
        assert "recent_audits" in export_ops


# ============================================================================
# T-05: Export Artifact Linkage
# ============================================================================

class TestExportArtifactLinkage:
    """Test export artifact linkage: manifest/audit/delivered_at/file_hash/artifact_ref"""

    def test_artifact_linkage_in_manifests(self):
        """T-05a: Artifact linkage fields should be present in recent_manifests"""
        client = TestClient(fastapi_app)
        token, _ = _login(client)
        
        # Create an export to ensure we have manifests
        client.get("/api/admin/commercial/monthly-pnl/export", headers=_admin_headers(token))
        
        response = client.get("/api/admin/commercial/overview", headers=_admin_headers(token))
        assert response.status_code == 200
        
        manifests = response.json().get("export_ops", {}).get("recent_manifests", [])
        assert manifests, "recent_manifests should not be empty"
        
        # Check first manifest has artifact linkage fields
        manifest = manifests[0]
        assert "export_id" in manifest
        assert "status" in manifest
        assert "delivery_status" in manifest
        assert "delivered_at" in manifest
        assert "artifact_ref" in manifest
        assert "file_hash" in manifest

    def test_artifact_linkage_in_audits(self):
        """T-05b: Artifact linkage fields should be present in recent_audits"""
        client = TestClient(fastapi_app)
        token, _ = _login(client)
        
        response = client.get("/api/admin/commercial/overview", headers=_admin_headers(token))
        assert response.status_code == 200
        
        audits = response.json().get("export_ops", {}).get("recent_audits", [])
        if audits:
            audit = audits[0]
            assert "audit_id" in audit
            assert "export_id" in audit
            assert "actor_email" in audit
            assert "delivery_status" in audit
            assert "artifact_ref" in audit
            assert "file_hash" in audit


# ============================================================================
# T-06: Alert Lifecycle Endpoint
# ============================================================================

class TestAlertLifecycleEndpoint:
    """Test alert lifecycle endpoint: ack/triage/resolution fields"""

    def test_alert_lifecycle_ack_and_triage(self):
        """T-06a: Alert lifecycle endpoint should update ack/triage/resolution fields"""
        client = TestClient(fastapi_app)
        token, user_id = _login(client)
        
        # Create a test alert
        db = SessionLocal()
        try:
            alert = CommercialAlertEvent(
                alert_type="test_alert",
                severity="warning",
                source="commercial.test",
                entity_type="test",
                entity_id="test-1",
                title="Test Alert",
                message="Test alert message",
                suggested_action="Test action",
            )
            db.add(alert)
            db.commit()
            db.refresh(alert)
            alert_id = alert.id
        finally:
            db.close()
        
        # Update alert lifecycle
        lifecycle_resp = client.post(
            f"/api/admin/commercial/alerts/{alert_id}/lifecycle",
            headers=_admin_headers(token),
            json={
                "triage_status": "acknowledged",
                "escalation_level": "medium",
                "resolution_note": "investigating",
                "acknowledge": True,
            },
        )
        assert lifecycle_resp.status_code == 200
        
        data = lifecycle_resp.json()
        assert data.get("triage_status") == "acknowledged"
        assert data.get("acknowledged_by") == user_id
        assert data.get("acknowledged_at") is not None

    def test_alert_lifecycle_resolution(self):
        """T-06b: Alert lifecycle endpoint should handle resolution"""
        client = TestClient(fastapi_app)
        token, _ = _login(client)
        
        # Create a test alert
        db = SessionLocal()
        try:
            alert = CommercialAlertEvent(
                alert_type="test_alert_resolve",
                severity="warning",
                source="commercial.test",
                entity_type="test",
                entity_id="test-2",
                title="Test Alert Resolve",
                message="Test alert message",
                suggested_action="Test action",
            )
            db.add(alert)
            db.commit()
            db.refresh(alert)
            alert_id = alert.id
        finally:
            db.close()
        
        # Resolve alert
        lifecycle_resp = client.post(
            f"/api/admin/commercial/alerts/{alert_id}/lifecycle",
            headers=_admin_headers(token),
            json={
                "triage_status": "resolved",
                "escalation_level": "none",
                "resolution_note": "Issue resolved",
                "acknowledge": True,
            },
        )
        assert lifecycle_resp.status_code == 200
        
        data = lifecycle_resp.json()
        assert data.get("triage_status") == "resolved"
        assert data.get("resolution_note") == "Issue resolved"


# ============================================================================
# T-07: Alert Normalization
# ============================================================================

class TestAlertNormalization:
    """Test alert normalization: severity/source/entity/suggested_action not empty"""

    def test_alert_rail_normalization_in_overview(self):
        """T-07a: Alert rail should have normalized fields"""
        client = TestClient(fastapi_app)
        token, _ = _login(client)
        
        response = client.get("/api/admin/commercial/overview", headers=_admin_headers(token))
        assert response.status_code == 200
        
        alerts = response.json().get("alert_rail", [])
        for alert in alerts:
            # All alerts should have these fields
            assert "severity" in alert
            assert "source" in alert
            assert "entity_type" in alert
            assert "entity_id" in alert
            assert "suggested_action" in alert
            assert "triage_status" in alert
            
            # Severity should be normalized
            assert alert.get("severity") in {"critical", "high", "medium", "low", "info"}
            
            # suggested_action should not be empty
            assert alert.get("suggested_action"), "suggested_action should not be empty"

    def test_alert_normalization_fills_empty_suggested_action(self):
        """T-07b: Alert normalization should fill empty suggested_action"""
        client = TestClient(fastapi_app)
        token, _ = _login(client)
        
        # Create alert with empty suggested_action
        db = SessionLocal()
        try:
            alert = CommercialAlertEvent(
                alert_type="test_empty_action",
                severity="warning",
                source="commercial.test",
                entity_type="test",
                entity_id="test-3",
                title="Test Empty Action",
                message="Test message",
                suggested_action="",  # Empty
            )
            db.add(alert)
            db.commit()
        finally:
            db.close()
        
        response = client.get("/api/admin/commercial/overview", headers=_admin_headers(token))
        assert response.status_code == 200
        
        alerts = response.json().get("alert_rail", [])
        for alert in alerts:
            # suggested_action should be filled with default
            assert alert.get("suggested_action"), "suggested_action should not be empty"


# ============================================================================
# T-08: Trade Intent Enforcement Path
# ============================================================================

class TestTradeIntentEnforcementPath:
    """Test trade intent enforcement path via runtime execution submit (admin accessible)"""

    def test_runtime_execution_submit_blocked_by_trading_disabled(self):
        """T-08a: Runtime execution submit should be blocked when trading_enabled=false"""
        client = TestClient(fastapi_app)
        token, user_id = _login(client)
        
        try:
            _set_controls(client, token, user_id, trading_enabled=False, reason_note="block runtime submit")
            
            payload = {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "size": 1.0,
                "confidence": 0.7,
                "strategy_name": "ema_rsi",
                "mark_price": 100.0,
                "leverage": 1,
            }
            response = client.post("/api/runtime/execution/submit", headers=_admin_headers(token), json=payload)
            assert response.status_code == 423
            detail = response.json().get("detail", {})
            assert detail.get("reason_code") == COMMERCIAL_TRADING_DISABLED
        finally:
            _reset_controls(client, token, user_id)


# ============================================================================
# T-09: Audit Trail for Blocked Operations
# ============================================================================

class TestAuditTrailForBlockedOperations:
    """Test audit trail for blocked operations"""

    def test_blocked_operation_creates_audit_log(self):
        """T-09a: Blocked operation should create audit log"""
        client = TestClient(fastapi_app)
        token, user_id = _login(client)
        
        try:
            _set_controls(client, token, user_id, trading_enabled=False, reason_note="audit test")
            
            payload = {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "size": 1.0,
                "confidence": 0.7,
                "strategy_name": "ema_rsi",
                "mark_price": 100.0,
                "leverage": 1,
            }
            client.post("/api/runtime/execution/submit", headers=_admin_headers(token), json=payload)
            
            db = SessionLocal()
            try:
                blocked_logs = (
                    db.query(AuditLog)
                    .filter(AuditLog.action == "COMMERCIAL_OPERATION_BLOCKED", AuditLog.actor_user_id == user_id)
                    .order_by(AuditLog.created_at.desc())
                    .limit(5)
                    .all()
                )
                assert blocked_logs, "Blocked operation should create audit log"
            finally:
                db.close()
        finally:
            _reset_controls(client, token, user_id)


# ============================================================================
# T-10: Overview Operational Controls Summary
# ============================================================================

class TestOverviewOperationalControlsSummary:
    """Test overview operational controls summary"""

    def test_operational_controls_summary_in_overview(self):
        """T-10a: Overview should have operational controls summary"""
        client = TestClient(fastapi_app)
        token, _ = _login(client)
        
        response = client.get("/api/admin/commercial/overview", headers=_admin_headers(token))
        assert response.status_code == 200
        
        controls = response.json().get("operational_controls", {})
        assert "trading_enabled_count" in controls
        assert "emergency_stop_count" in controls
        assert "capital_frozen_count" in controls
        assert "withdraw_locked_count" in controls
        assert "recent_actions" in controls
