from __future__ import annotations

import asyncio
import csv
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from db import redis_client
from models import FailedEvent, SystemAlert
from services.artifact_service import verify_manifest_chain
from services.risk_orchestrator_analytics_service import compute_risk_analytics
from services.runtime_ops_service import list_stuck_intents
from services.system_alert_service import create_system_alert

REPORT_DIR = Path("/app/backend/exports")
LAST_REPORT_KEY = "weekly_report:last_path"


def _date_range(days: int) -> datetime:
    return datetime.now(tz=ZoneInfo("UTC")) - timedelta(days=days)


def generate_weekly_report(db: Session, *, days: int = 7) -> dict:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
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

    filename = f"weekly_ops_report_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.csv"
    path = REPORT_DIR / filename

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        writer.writerow(["generated_at", datetime.utcnow().isoformat()])
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

    redis_client.set(LAST_REPORT_KEY, str(path))

    alert = create_system_alert(
        db,
        alert_type="weekly_ops_report_generated",
        severity="INFO",
        message="Weekly CSV report generated",
        details={"path": str(path), "days": days},
        entity_key="weekly_report",
        root_cause_code="weekly_report_generated",
        state_key=path.name,
    )

    return {"path": str(path), "alert_id": alert.id, "analytics": analytics}


def get_latest_report_path() -> str | None:
    raw = redis_client.get(LAST_REPORT_KEY)
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return raw


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
            generate_weekly_report(db)
        finally:
            db.close()
