from sqlalchemy.orm import Session

from models import AuditLog, ExecutionStateTransition, HardeningChecklistRun
from services.pipeline.runtime import pipeline_runtime


def _item(key: str, label: str, critical: bool, passed: bool, value, threshold, note: str) -> dict:
    return {
        "key": key,
        "label": label,
        "critical": critical,
        "status": "pass" if passed else "fail",
        "value": value,
        "threshold": threshold,
        "note": note,
    }


def run_hardening_checklist(db: Session) -> HardeningChecklistRun:
    monitoring = pipeline_runtime.monitoring_snapshot(db)
    transitions_count = db.query(ExecutionStateTransition).count()
    audit_count = db.query(AuditLog).count()
    activity_window = (
        monitoring["signal_rate_last_5m"]
        + monitoring["paper_trades_last_5m"]
        + monitoring["execution_transitions_5m"]
    )

    idempotency_ok = monitoring["idempotency_keys_5m"] > 0 if activity_window > 0 else True
    duplicate_ok = (
        0 <= monitoring["duplicate_signals_blocked_5m"] <= max(monitoring["idempotency_keys_5m"], 0)
        if activity_window > 0
        else True
    )

    items = [
        _item(
            "idempotency_protection",
            "Idempotency protection active",
            True,
            idempotency_ok,
            monitoring["idempotency_keys_5m"],
            "> 0 when activity > 0",
            "Aktif pencerede idempotency key üretimi zorunlu.",
        ),
        _item(
            "duplicate_blocking",
            "Duplicate signal blocking active",
            True,
            duplicate_ok,
            monitoring["duplicate_signals_blocked_5m"],
            "0 <= blocked <= idempotency_keys when activity > 0",
            "Duplicate bloklama idempotency üretimiyle tutarlı olmalı.",
        ),
        _item(
            "websocket_resilience",
            "Websocket reconnect bounded",
            True,
            monitoring["websocket_reconnects_5m"] <= 20,
            monitoring["websocket_reconnects_5m"],
            "<= 20 / 5m",
            "Reconnection oranı kontrol sınırında olmalı.",
        ),
        _item(
            "failed_event_health",
            "Failed event queue health",
            True,
            monitoring["failed_events_dead"] == 0 and monitoring["failed_events_pending"] < 15,
            {
                "pending": monitoring["failed_events_pending"],
                "dead": monitoring["failed_events_dead"],
            },
            "dead=0 and pending<15",
            "Dead event olmamalı, pending kuyruk sınırlı kalmalı.",
        ),
        _item(
            "execution_state_visibility",
            "Execution transition visibility",
            True,
            transitions_count > 0,
            transitions_count,
            "> 0",
            "State machine görünürlüğü için transition kaydı olmalı.",
        ),
        _item(
            "queue_depth_guard",
            "Queue depth guard",
            False,
            monitoring["queue_depth"] < 1000,
            monitoring["queue_depth"],
            "< 1000",
            "Queue derinliği güvenli sınırda olmalı.",
        ),
        _item(
            "audit_trail_presence",
            "Audit trail presence",
            False,
            audit_count > 0,
            audit_count,
            "> 0",
            "Sistem aksiyonları için audit trail bulunmalı.",
        ),
    ]

    critical_items = [item for item in items if item["critical"]]
    non_critical_items = [item for item in items if not item["critical"]]
    critical_weight = 14
    non_critical_weight = 15

    score = sum(critical_weight for item in critical_items if item["status"] == "pass")
    score += sum(non_critical_weight for item in non_critical_items if item["status"] == "pass")
    score = min(float(score), 100.0)

    critical_blocked = any(item["status"] == "fail" for item in critical_items)
    if critical_blocked:
        score = min(score, 59.0)

    readiness_status = "ready" if (not critical_blocked and score >= 75) else "blocked"

    run = HardeningChecklistRun(
        score=round(score, 2),
        critical_blocked=critical_blocked,
        readiness_status=readiness_status,
        checklist_items=items,
        summary={
            "critical_passed": len([item for item in critical_items if item["status"] == "pass"]),
            "critical_total": len(critical_items),
            "non_critical_passed": len([item for item in non_critical_items if item["status"] == "pass"]),
            "non_critical_total": len(non_critical_items),
        },
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def get_latest_hardening_checklist_run(db: Session) -> HardeningChecklistRun | None:
    return db.query(HardeningChecklistRun).order_by(HardeningChecklistRun.created_at.desc()).first()