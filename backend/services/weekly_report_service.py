from __future__ import annotations

import asyncio
import csv
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from db import redis_client
from models import FailedEvent, SystemAlert, WeeklyReportArchive
from services.artifact_service import verify_manifest_chain
from services.audit_service import create_audit_log
from services.risk_orchestrator_analytics_service import compute_risk_analytics
from services.runtime_ops_service import list_stuck_intents
from services.system_alert_service import create_system_alert

REPORT_DIR = Path("/app/backend/exports")
LAST_REPORT_KEY = "weekly_report:last_id"
RETENTION_MONTHS = 12


def _date_range(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record_latest_report(report_id: str) -> None:
    redis_client.set(LAST_REPORT_KEY, report_id)


def _get_latest_report_id() -> str | None:
    raw = redis_client.get(LAST_REPORT_KEY)
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return raw


def cleanup_report_retention(db: Session, retention_months: int = RETENTION_MONTHS) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_months * 30)
    reports = (
        db.query(WeeklyReportArchive)
        .filter(WeeklyReportArchive.generated_at < cutoff, WeeklyReportArchive.status != "purged")
        .all()
    )
    purged = 0
    for report in reports:
        if report.storage_path:
            try:
                path = Path(report.storage_path)
                if path.exists():
                    path.unlink()
            except Exception:
                pass
        report.status = "purged"
        report.updated_at = datetime.now(timezone.utc)
        db.commit()
        create_audit_log(
            db,
            action="weekly_report_purged",
            entity_type="weekly_report",
            entity_id=report.report_id,
            actor_user_id="system",
            actor_role="system",
            severity="info",
            details={"report_id": report.report_id, "filename": report.filename, "status": report.status},
        )
        purged += 1
    return purged


def generate_weekly_report(
    db: Session,
    *,
    days: int = 7,
    trigger_source: str = "scheduled",
    generated_by: str = "system",
) -> dict:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc)
    period_end = generated_at
    period_start = generated_at - timedelta(days=days)

    try:
        analytics = compute_risk_analytics(db, days=days)
        stuck_intents = list_stuck_intents(db)
        chain_status = verify_manifest_chain()

        since = _date_range(days)
        quarantine_events = (
            db.query(FailedEvent)
            .filter(FailedEvent.created_at >= since, FailedEvent.status.in_(["quarantined", "dead"]))
            .all()
        )
        quarantine_by_day = {}
        for event in quarantine_events:
            day_key = event.created_at.date().isoformat()
            quarantine_by_day[day_key] = quarantine_by_day.get(day_key, 0) + 1

        release_gate_blocked = (
            db.query(SystemAlert)
            .filter(SystemAlert.alert_type == "release_gate_blocked", SystemAlert.created_at >= since)
            .count()
        )
        release_gate_warning = (
            db.query(SystemAlert)
            .filter(SystemAlert.alert_type == "release_gate_warning", SystemAlert.created_at >= since)
            .count()
        )

        filename = f"weekly_ops_report_{generated_at.strftime('%Y%m%d%H%M%S')}.csv"
        path = REPORT_DIR / filename

        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["metric", "value"])
            writer.writerow(["generated_at", generated_at.isoformat()])
            writer.writerow(["window_days", days])
            writer.writerow(["risk_policy_hits", analytics.get("risk_policy_hits")])
            writer.writerow(["kill_switch_events", analytics.get("kill_switch_events")])
            writer.writerow(["duplicate_intent_attempts", analytics.get("duplicate_intent_attempts")])
            writer.writerow(["stale_intent_count", len(stuck_intents)])
            writer.writerow(["chain_integrity_failure", chain_status.get("chain_broken")])
            writer.writerow(["release_gate_blocked", release_gate_blocked])
            writer.writerow(["release_gate_warning", release_gate_warning])
            writer.writerow([])
            writer.writerow(["section", "reject_reason_distribution"])
            for item in analytics.get("reject_reason_distribution", []):
                writer.writerow([item.get("label"), item.get("value")])
            writer.writerow([])
            writer.writerow(["section", "breach_by_day"])
            for item in analytics.get("breach_by_day", []):
                writer.writerow([item.get("date"), item.get("value")])
            writer.writerow([])
            writer.writerow(["section", "quarantine_backlog_trend"])
            for day, count in sorted(quarantine_by_day.items()):
                writer.writerow([day, count])

        sha256 = _compute_sha256(path)
        size_bytes = path.stat().st_size

        report = WeeklyReportArchive(
            report_type="weekly_ops",
            period_start=period_start,
            period_end=period_end,
            generated_at=generated_at,
            timezone="Europe/Berlin",
            filename=filename,
            storage_path=str(path),
            size_bytes=size_bytes,
            sha256=sha256,
            status="generated",
            trigger_source=trigger_source,
            generated_by=generated_by,
        )
        db.add(report)
        db.commit()
        db.refresh(report)

        _record_latest_report(report.report_id)

        alert = create_system_alert(
            db,
            alert_type="weekly_ops_report_generated",
            severity="INFO",
            message="Weekly CSV report generated",
            details={"path": str(path), "days": days, "report_id": report.report_id},
            entity_key="weekly_report",
            root_cause_code="weekly_report_generated",
            state_key=report.report_id,
        )

        cleanup_report_retention(db)

        return {"report": report, "alert_id": alert.id, "analytics": analytics}
    except Exception as exc:
        report = WeeklyReportArchive(
            report_type="weekly_ops",
            period_start=period_start,
            period_end=period_end,
            generated_at=generated_at,
            timezone="Europe/Berlin",
            filename=f"failed_{generated_at.strftime('%Y%m%d%H%M%S')}.csv",
            storage_path="",
            size_bytes=0,
            sha256="",
            status="failed",
            trigger_source=trigger_source,
            generated_by=generated_by,
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        create_audit_log(
            db,
            action="weekly_report_failed",
            entity_type="weekly_report",
            entity_id=report.report_id,
            actor_user_id=generated_by,
            actor_role="system",
            severity="warning",
            details={"error": str(exc), "report_id": report.report_id},
        )
        return {"report": report, "error": str(exc)}


def get_latest_report(db: Session) -> WeeklyReportArchive | None:
    report_id = _get_latest_report_id()
    if report_id:
        report = db.query(WeeklyReportArchive).filter(WeeklyReportArchive.report_id == report_id).first()
        if report:
            return report
    return (
        db.query(WeeklyReportArchive)
        .filter(WeeklyReportArchive.status == "generated")
        .order_by(WeeklyReportArchive.generated_at.desc())
        .first()
    )


def compute_next_run(*, tz_name: str = "Europe/Berlin", weekday: int = 0, hour: int = 9) -> datetime:
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    candidate = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    days_ahead = (weekday - candidate.weekday()) % 7
    if days_ahead == 0 and candidate <= now:
        days_ahead = 7
    next_run = candidate + timedelta(days=days_ahead)
    return next_run


async def run_weekly_report_loop(db_factory, tz_name: str = "Europe/Berlin") -> None:
    while True:
        next_run = compute_next_run(tz_name=tz_name)
        now = datetime.now(ZoneInfo(tz_name))
        sleep_seconds = max((next_run - now).total_seconds(), 1)
        await asyncio.sleep(sleep_seconds)
        db = db_factory()
        try:
            generate_weekly_report(db, trigger_source="scheduled", generated_by="system")
        finally:
            db.close()
