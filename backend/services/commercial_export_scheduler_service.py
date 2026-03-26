from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from db import SessionLocal, redis_client
from models import CommercialExportManifest, CommercialExportSchedule, User
from services.admin_commercial_service import (
    create_commercial_export_manifest,
    export_monthly_pnl_excel,
    finalize_export_delivery,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_due(schedule: CommercialExportSchedule, now: datetime) -> bool:
    if not bool(getattr(schedule, "is_active", False)):
        return False
    period = str(getattr(schedule, "schedule_period", "daily") or "daily").lower()
    last_run = getattr(schedule, "last_run_at", None)
    if last_run is None:
        return True
    delta = now - last_run
    if period == "daily":
        return delta >= timedelta(days=1)
    if period == "weekly":
        return delta >= timedelta(days=7)
    if period == "monthly":
        return delta >= timedelta(days=30)
    return False


def _build_export_payload(db, export_type: str) -> tuple[bytes, str]:
    export_code = str(export_type or "").lower()
    if export_code in {"monthly_pnl", "pnl"}:
        return export_monthly_pnl_excel(db, month=None)

    content = "generated_at,export_type\n{},{}\n".format(_now().isoformat(), export_code)
    filename = f"commercial_{export_code}_{_now().strftime('%Y%m%d%H%M%S')}.csv"
    return content.encode("utf-8"), filename


def run_commercial_export_scheduler_cycle() -> dict:
    db = SessionLocal()
    processed = 0
    try:
        now = _now()
        schedules = (
            db.query(CommercialExportSchedule)
            .filter(CommercialExportSchedule.is_active.is_(True))
            .order_by(CommercialExportSchedule.updated_at.asc())
            .limit(50)
            .all()
        )
        for schedule in schedules:
            if not _is_due(schedule, now):
                continue

            schedule.last_status = "due"
            db.commit()

            actor = db.query(User).filter(User.id == schedule.requested_by).first()
            if actor is None:
                schedule.last_status = "failed"
                schedule.filters_snapshot = {
                    **(schedule.filters_snapshot or {}),
                    "failure_reason": "scheduler_actor_not_found",
                }
                db.commit()
                continue

            schedule.last_status = "running"
            db.commit()

            try:
                manifest = create_commercial_export_manifest(
                    db,
                    actor_user=actor,
                    export_type=schedule.export_type,
                    schema_version="v1",
                    filters_snapshot=schedule.filters_snapshot or {},
                    column_mapping={},
                    output_format=schedule.output_format,
                    row_count=0,
                    reason_note="scheduled_export_runner",
                )
                payload_bytes, filename = _build_export_payload(db, schedule.export_type)
                delivery = finalize_export_delivery(
                    db,
                    export_id=manifest["export_id"],
                    content_bytes=payload_bytes,
                    output_format=schedule.output_format,
                )
                schedule.last_run_at = now
                schedule.last_status = "success"
                schedule.last_output_ref = str(delivery.get("artifact_ref") or filename)
                processed += 1
            except Exception as exc:  # noqa: BLE001
                schedule.last_run_at = now
                schedule.last_status = "failed"
                schedule.filters_snapshot = {
                    **(schedule.filters_snapshot or {}),
                    "failure_reason": str(exc)[:300],
                }
            db.commit()
        return {"processed": processed}
    finally:
        db.close()


async def run_commercial_export_scheduler_loop(interval_seconds: int = 60):
    while True:
        lock_key = "commercial:export:scheduler:lock"
        lock_existing = redis_client.get(lock_key)
        if not lock_existing:
            redis_client.set(lock_key, "1")
            redis_client.expire(lock_key, max(30, interval_seconds - 5))
            try:
                run_commercial_export_scheduler_cycle()
            finally:
                redis_client.delete(lock_key)
        await asyncio.sleep(interval_seconds)
