from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import RuntimeSmokeRun


def record_runtime_smoke_run(
    db: Session,
    *,
    status: str,
    summary: str,
    steps: dict,
    trigger_source: str,
    report_path: str | None,
    started_at: datetime,
) -> RuntimeSmokeRun:
    row = RuntimeSmokeRun(
        status=status,
        summary=summary,
        steps=steps,
        trigger_source=trigger_source,
        report_path=report_path,
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_latest_runtime_smoke_run(db: Session) -> RuntimeSmokeRun | None:
    return db.query(RuntimeSmokeRun).order_by(RuntimeSmokeRun.created_at.desc()).first()
