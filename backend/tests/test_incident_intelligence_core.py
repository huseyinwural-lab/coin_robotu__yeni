# ruff: noqa: E402
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.security import hash_password
from db import SessionLocal
from models import AuditLog, FailedEvent, SystemAlert, User, UserRole
from services.incident_intelligence_service import (
    build_correlation_graph,
    build_incident_kpis,
    build_incident_predictions,
    build_incident_timeline,
    build_weekly_incident_summary,
    list_intelligence_incidents,
    run_incident_intelligence_cycle,
    update_incident_intelligence_state,
)


def _create_admin(db) -> User:
    user = User(
        email=f"incident-admin-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("Pass1234!Aa"),
        role=UserRole.ADMIN,
        is_active=True,
        approval_status="approved",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _seed_events(db, actor_id: str):
    now = datetime.now(timezone.utc)
    for idx in range(3):
        db.add(
            AuditLog(
                actor_user_id=actor_id,
                actor_role="admin",
                action="risk_guard_triggered",
                entity_type="risk_engine",
                entity_id=f"risk-{idx}",
                severity="warning",
                details={"reason_code": "risk_limit", "correlation_id": f"risk-chain-{idx}"},
                created_at=now - timedelta(minutes=5 - idx),
            )
        )
    db.add(
        AuditLog(
            actor_user_id=actor_id,
            actor_role="admin",
            action="execution_submit_failed",
            entity_type="execution_job",
            entity_id="exec-1",
            severity="error",
            details={"reason_code": "precheck_failed", "intent_id": "intent-1", "correlation_id": "exec-chain-1"},
            created_at=now - timedelta(minutes=2),
        )
    )
    db.add(
        FailedEvent(
            event_type="worker_loop_failed",
            entity_type="worker",
            entity_id="worker-1",
            payload={"worker": "runtime", "artifact_id": "artifact-1"},
            error_message="worker timeout",
            failure_class="worker_timeout",
            correlation_id="sys-chain-1",
            retry_reason="worker_timeout",
            status="pending",
            created_at=now - timedelta(minutes=3),
        )
    )
    db.add(
        SystemAlert(
            alert_type="exchange_connectivity_fail",
            severity="CRITICAL",
            message="Bybit 403",
            fingerprint=str(uuid.uuid4()),
            entity_key="bybit",
            root_cause_code="exchange_403",
            details={"exchange": "bybit", "reason_code": "exchange_403", "artifact_id": "artifact-2"},
            status="open",
            created_at=now - timedelta(minutes=1),
            updated_at=now - timedelta(minutes=1),
            last_triggered_at=now - timedelta(minutes=1),
        )
    )
    db.commit()


def test_incident_engine_creates_cross_domain_anomalies_and_incidents():
    db = SessionLocal()
    try:
        admin = _create_admin(db)
        _seed_events(db, admin.id)
        payload = run_incident_intelligence_cycle(db, window_minutes=60)
        domains = {item["domain"] for item in payload["anomalies"]}
        assert {"execution", "risk", "system", "exchange"}.issubset(domains)
        assert payload["incidents"]
    finally:
        db.close()


def test_incident_timeline_kpis_and_false_positive_flow():
    db = SessionLocal()
    try:
        admin = _create_admin(db)
        _seed_events(db, admin.id)
        run_incident_intelligence_cycle(db, window_minutes=60)
        incident = list_intelligence_incidents(db, limit=10)[0]
        timeline = build_incident_timeline(db, incident["incident_id"])
        kinds = {item["kind"] for item in timeline["chain"]}
        assert {"raw_event", "anomaly", "incident"}.issubset(kinds)
        updated = update_incident_intelligence_state(db, incident_id=incident["incident_id"], state="FALSE_POSITIVE", owner="ops", note="validated")
        assert updated["state"] == "FALSE_POSITIVE"
        kpis = build_incident_kpis(db, days=1)
        assert kpis["incident_count"] >= 1
    finally:
        db.close()


def test_auto_remediation_weekly_summary_graph_and_predictions():
    db = SessionLocal()
    try:
        admin = _create_admin(db)
        _seed_events(db, admin.id)
        first = run_incident_intelligence_cycle(db, window_minutes=60)
        incidents = list_intelligence_incidents(db, limit=20)
        assert any(item.get("state") == "MITIGATED" for item in incidents)
        for item in incidents:
            update_incident_intelligence_state(db, incident_id=item["incident_id"], state="RESOLVED")
        second = run_incident_intelligence_cycle(db, window_minutes=60)
        summary = build_weekly_incident_summary(db)
        graph = build_correlation_graph(db, limit=40)
        predictions = build_incident_predictions(db, days=30)
        assert summary["kpis"]["incident_count"] >= 1
        assert graph["nodes"]
        assert first["anomalies"] and second["anomalies"]
        assert isinstance(predictions["items"], list)
    finally:
        db.close()
