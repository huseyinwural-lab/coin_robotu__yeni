from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from services.audit_service import create_audit_log
from services.readiness_history_maintenance_service import run_readiness_history_maintenance


APP_ROOT = Path(os.getenv("APP_ROOT") or Path(__file__).resolve().parents[2])
ARTIFACT_DIR = APP_ROOT / "artifacts"
STATUS_PATH = ARTIFACT_DIR / "readiness_maintenance_status.json"
LOG_PATH = ARTIFACT_DIR / "readiness_maintenance_cron.log"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_log(message: str) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"[{_utcnow_iso()}] {message}\n")


def _write_status(payload: dict) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_readiness_maintenance_status() -> dict:
    try:
        if STATUS_PATH.exists():
            data = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        return {}
    return {}


def _run_once(session_factory, *, retry_seconds: int, trigger: str = "scheduler") -> tuple[bool, dict]:
    db = session_factory()
    started_at = _utcnow_iso()
    try:
        result = run_readiness_history_maintenance(db, dry_run=False)
        status_payload = {
            "status": "success",
            "trigger": trigger,
            "started_at": started_at,
            "finished_at": _utcnow_iso(),
            "last_success_at": _utcnow_iso(),
            "retry_in_seconds": None,
            "reason_code": None,
            "result": result,
        }
        _write_status(status_payload)
        _append_log(
            "READINESS_MAINTENANCE_RUN_OK "
            f"deleted_detail_rows={result.get('deleted_detail_rows')} "
            f"deleted_aggregate_rows={result.get('deleted_aggregate_rows')} "
            f"daily_summary_rows_upserted={result.get('daily_summary_rows_upserted')}"
        )
        create_audit_log(
            db,
            action="READINESS_HISTORY_MAINTENANCE_SCHEDULED_RUN",
            entity_type="readiness_history",
            entity_id="scheduled",
            actor_role="system",
            severity="info",
            details={"trigger": trigger, **result},
            commit=True,
        )
        return True, status_payload
    except Exception as exc:  # noqa: BLE001
        reason_code = "READINESS_MAINTENANCE_JOB_FAILED"
        status_payload = {
            "status": "failed",
            "trigger": trigger,
            "started_at": started_at,
            "finished_at": _utcnow_iso(),
            "last_success_at": read_readiness_maintenance_status().get("last_success_at"),
            "retry_in_seconds": int(retry_seconds),
            "reason_code": reason_code,
            "error": str(exc)[:400],
        }
        _write_status(status_payload)
        _append_log(
            f"READINESS_MAINTENANCE_RUN_FAIL reason_code={reason_code} retry_in_seconds={retry_seconds} error={str(exc)[:220]}"
        )
        try:
            create_audit_log(
                db,
                action="READINESS_HISTORY_MAINTENANCE_SCHEDULED_FAIL",
                entity_type="readiness_history",
                entity_id="scheduled",
                actor_role="system",
                severity="critical",
                details=status_payload,
                commit=True,
            )
        except Exception:
            pass
        return False, status_payload
    finally:
        db.close()


async def run_readiness_maintenance_scheduler_loop(session_factory) -> None:
    enabled = str(os.getenv("READINESS_MAINTENANCE_SCHEDULER_ENABLED", "1") or "1").strip().lower() in {"1", "true", "yes"}
    interval_seconds = max(300, int(float(os.getenv("READINESS_MAINTENANCE_INTERVAL_SECONDS", "86400") or "86400")))
    retry_seconds = max(120, int(float(os.getenv("READINESS_MAINTENANCE_RETRY_SECONDS", "900") or "900")))
    initial_delay_seconds = max(0, int(float(os.getenv("READINESS_MAINTENANCE_INITIAL_DELAY_SECONDS", "10") or "10")))

    _append_log(
        "READINESS_MAINTENANCE_SCHEDULER_INIT "
        f"enabled={int(enabled)} interval_seconds={interval_seconds} retry_seconds={retry_seconds} initial_delay_seconds={initial_delay_seconds}"
    )

    if not enabled:
        _write_status(
            {
                "status": "disabled",
                "updated_at": _utcnow_iso(),
                "reason_code": "READINESS_MAINTENANCE_SCHEDULER_DISABLED",
            }
        )
        _append_log("READINESS_MAINTENANCE_SCHEDULER_DISABLED")
        return

    if initial_delay_seconds > 0:
        await asyncio.sleep(initial_delay_seconds)

    while True:
        success, _ = await asyncio.to_thread(_run_once, session_factory, retry_seconds=retry_seconds, trigger="scheduler")
        await asyncio.sleep(interval_seconds if success else retry_seconds)
