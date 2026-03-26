from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import uuid

from sqlalchemy import or_, text, update

from db import SessionLocal, redis_client
from models import CommercialExportManifest, CommercialExportSchedule, User
from services.admin_commercial_service import (
    cleanup_expired_export_artifacts,
    create_commercial_export_manifest,
    export_monthly_pnl_excel,
    finalize_export_delivery,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_due(schedule: CommercialExportSchedule, now: datetime) -> bool:
    if not bool(getattr(schedule, "is_active", False)):
        return False
    if getattr(schedule, "next_retry_at", None) and now < schedule.next_retry_at:
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


def _execution_window_key(schedule: CommercialExportSchedule, now: datetime) -> str:
    period = str(getattr(schedule, "schedule_period", "daily") or "daily").lower()
    if period == "daily":
        return now.strftime("%Y-%m-%d")
    if period == "weekly":
        week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        return f"week:{week_start}"
    if period == "monthly":
        return now.strftime("%Y-%m")
    return now.strftime("%Y-%m-%d")


def _recover_stale_running_schedules(db, now: datetime, stale_minutes: int = 10):
    rows = (
        db.query(CommercialExportSchedule)
        .filter(CommercialExportSchedule.last_status == "running")
        .limit(50)
        .all()
    )
    for row in rows:
        started_at = getattr(row, "running_started_at", None)
        claim_expired = bool(getattr(row, "claim_expires_at", None) and now >= row.claim_expires_at)
        runtime_stale = bool(started_at is not None and now - started_at >= timedelta(minutes=stale_minutes))
        if runtime_stale or claim_expired:
            row.last_status = "failed"
            row.stale_run_flag = True
            row.last_failure_reason = "stale_run_recovered" if runtime_stale else "stale_claim_recovered"
            row.claim_token = None
            row.claim_expires_at = None
            row.running_started_at = None
            row.retry_count = int(getattr(row, "retry_count", 0) or 0) + 1
            row.next_retry_at = now + timedelta(minutes=min(30, 2 ** max(1, row.retry_count)))
    db.commit()


def _build_export_payload(db, export_type: str) -> tuple[bytes, str]:
    export_code = str(export_type or "").lower()
    if export_code in {"monthly_pnl", "pnl"}:
        return export_monthly_pnl_excel(db, month=None)

    content = "generated_at,export_type\n{},{}\n".format(_now().isoformat(), export_code)
    filename = f"commercial_{export_code}_{_now().strftime('%Y%m%d%H%M%S')}.csv"
    return content.encode("utf-8"), filename


def _build_schedule_window_lock_key(schedule_id: str, execution_window: str) -> int:
    key_seed = f"commercial_export_schedule:{schedule_id}:{execution_window}"
    digest = hashlib.sha256(key_seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False) % (2**63 - 1)


def _try_acquire_window_advisory_lock(db, lock_key: int) -> bool:
    try:
        acquired = db.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": int(lock_key)}).scalar()
        return bool(acquired)
    except Exception as exc:
        db.rollback()
        message = str(exc).lower()
        if "pg_try_advisory_lock" in message or "no such function" in message or "does not exist" in message:
            return True
        return False


def _release_window_advisory_lock(db, lock_key: int) -> None:
    try:
        db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": int(lock_key)})
    except Exception:
        db.rollback()


def _try_claim_schedule(db, *, schedule_id: str, claim_token: str, now: datetime, claim_expires_at: datetime) -> bool:
    claim_stmt = (
        update(CommercialExportSchedule)
        .where(
            CommercialExportSchedule.id == schedule_id,
            CommercialExportSchedule.is_active.is_(True),
            or_(
                CommercialExportSchedule.claim_token.is_(None),
                CommercialExportSchedule.claim_expires_at.is_(None),
                CommercialExportSchedule.claim_expires_at <= now,
            ),
        )
        .values(
            claim_token=claim_token,
            claim_expires_at=claim_expires_at,
            last_status="due",
            stale_run_flag=False,
        )
    )
    result = db.execute(claim_stmt)
    db.commit()
    return int(result.rowcount or 0) == 1


def run_commercial_export_scheduler_cycle() -> dict:
    db = SessionLocal()
    processed = 0
    try:
        now = _now()
        _recover_stale_running_schedules(db, now)
        schedules = (
            db.query(CommercialExportSchedule)
            .filter(CommercialExportSchedule.is_active.is_(True))
            .order_by(CommercialExportSchedule.updated_at.asc())
            .limit(50)
            .all()
        )
        for schedule in schedules:
            if schedule.claim_token and schedule.claim_expires_at and schedule.claim_expires_at > now:
                continue
            if not _is_due(schedule, now):
                continue

            execution_window = _execution_window_key(schedule, now)
            if (
                str(getattr(schedule, "last_execution_window", "") or "") == execution_window
                and str(getattr(schedule, "last_status", "") or "").lower() in {"success", "running", "due"}
            ):
                continue

            window_lock_key = _build_schedule_window_lock_key(str(schedule.id), execution_window)
            if not _try_acquire_window_advisory_lock(db, window_lock_key):
                continue

            try:
                if int(getattr(schedule, "retry_count", 0) or 0) > int(getattr(schedule, "max_retry", 3) or 3):
                    schedule.last_status = "disabled"
                    schedule.is_active = False
                    db.commit()
                    continue

                claim_token = str(uuid.uuid4())
                claim_ok = _try_claim_schedule(
                    db,
                    schedule_id=str(schedule.id),
                    claim_token=claim_token,
                    now=now,
                    claim_expires_at=now + timedelta(minutes=2),
                )
                if not claim_ok:
                    continue
                db.refresh(schedule)

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
                schedule.running_started_at = now
                schedule.stale_run_flag = False
                db.commit()

                manifest_id: str | None = None
                idempotency_key = f"{schedule.id}:{execution_window}:{schedule.export_type}"
                existing = (
                    db.query(CommercialExportManifest)
                    .filter(CommercialExportManifest.idempotency_key == idempotency_key)
                    .order_by(CommercialExportManifest.requested_at.desc())
                    .first()
                )
                if existing and str(getattr(existing, "delivery_status", "")).lower() in {"success", "running", "pending"}:
                    schedule.last_run_at = now
                    schedule.last_status = "success"
                    schedule.last_output_ref = getattr(existing, "artifact_ref", None)
                    schedule.last_execution_window = execution_window
                    schedule.claim_token = None
                    schedule.claim_expires_at = None
                    schedule.running_started_at = None
                    db.commit()
                    processed += 1
                    continue

                if existing is not None:
                    manifest_id = str(existing.id)
                    manifest_row = existing
                else:
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
                    manifest_id = str(manifest["export_id"])
                    manifest_row = db.query(CommercialExportManifest).filter(CommercialExportManifest.id == manifest["export_id"]).first()
                if manifest_row is not None:
                    manifest_row.idempotency_key = idempotency_key
                    manifest_row.status = "running"
                    manifest_row.delivery_status = "running"
                    manifest_row.failure_reason = None
                db.commit()

                if not manifest_id:
                    raise RuntimeError("scheduler_manifest_id_missing")

                payload_bytes, filename = _build_export_payload(db, schedule.export_type)
                delivery = finalize_export_delivery(
                    db,
                    export_id=manifest_id,
                    content_bytes=payload_bytes,
                    output_format=schedule.output_format,
                )
                schedule.last_run_at = now
                schedule.last_status = "success"
                schedule.last_output_ref = str(delivery.get("artifact_ref") or filename)
                schedule.last_failure_reason = None
                schedule.retry_count = 0
                schedule.next_retry_at = None
                schedule.last_execution_window = execution_window
                schedule.claim_token = None
                schedule.claim_expires_at = None
                schedule.running_started_at = None
                processed += 1
            except Exception as exc:  # noqa: BLE001
                if manifest_id:
                    try:
                        finalize_export_delivery(
                            db,
                            export_id=manifest_id,
                            content_bytes=b"",
                            output_format=schedule.output_format,
                            failure_reason=str(exc)[:300],
                        )
                    except Exception:
                        pass
                schedule.last_run_at = now
                schedule.last_status = "failed"
                schedule.last_failure_reason = str(exc)[:300]
                schedule.retry_count = int(getattr(schedule, "retry_count", 0) or 0) + 1
                max_retry = int(getattr(schedule, "max_retry", 3) or 3)
                if schedule.retry_count > max_retry:
                    schedule.last_status = "disabled"
                    schedule.is_active = False
                else:
                    backoff_minutes = min(60, 2 ** max(1, schedule.retry_count))
                    schedule.next_retry_at = now + timedelta(minutes=backoff_minutes)
                schedule.claim_token = None
                schedule.claim_expires_at = None
                schedule.running_started_at = None
                db.commit()
            finally:
                _release_window_advisory_lock(db, window_lock_key)
        cleanup_stats = cleanup_expired_export_artifacts(db, limit=50)
        return {"processed": processed, "cleanup": cleanup_stats}
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
                await asyncio.to_thread(run_commercial_export_scheduler_cycle)
            finally:
                redis_client.delete(lock_key)
        await asyncio.sleep(interval_seconds)
