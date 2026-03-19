import asyncio
import os
from datetime import datetime
from pathlib import Path


BACKUP_SCRIPT_PATH = "/app/scripts/db_backup.sh"
BACKUP_CRON_LOG_PATH = Path("/app/artifacts/backup_cron.log")


def _log(message: str) -> None:
    BACKUP_CRON_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with BACKUP_CRON_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")


async def _run_backup_once() -> None:
    process = await asyncio.create_subprocess_exec(
        "/bin/bash",
        BACKUP_SCRIPT_PATH,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    stdout_text = stdout.decode("utf-8", errors="ignore").strip()
    stderr_text = stderr.decode("utf-8", errors="ignore").strip()

    if process.returncode == 0:
        _log(f"SCHEDULED_BACKUP_OK rc=0 output={stdout_text}")
    else:
        _log(f"SCHEDULED_BACKUP_FAIL rc={process.returncode} stdout={stdout_text} stderr={stderr_text}")


async def run_backup_scheduler_loop() -> None:
    enabled = str(os.getenv("BACKUP_SCHEDULER_ENABLED", "1") or "1").strip() == "1"
    interval_seconds = int(str(os.getenv("BACKUP_SCHEDULER_INTERVAL_SECONDS", "3600") or "3600"))
    interval_seconds = max(interval_seconds, 60)

    if not enabled:
        _log("SCHEDULED_BACKUP_DISABLED")
        return

    _log(f"SCHEDULED_BACKUP_LOOP_STARTED interval_seconds={interval_seconds}")
    while True:
        await _run_backup_once()
        await asyncio.sleep(interval_seconds)
