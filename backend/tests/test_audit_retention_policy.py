import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from db import SessionLocal
from models import AuditLog
from services.audit_retention_service import prune_audit_logs_with_policy


def _create_audit_row(db, *, action: str, days_old: int) -> str:
    row = AuditLog(
        id=str(uuid.uuid4()),
        actor_user_id="user-test",
        actor_role="USER",
        action=action,
        entity_type="test",
        entity_id=str(uuid.uuid4()),
        severity="info",
        details={"seed": True},
        created_at=datetime.now(timezone.utc) - timedelta(days=days_old),
    )
    db.add(row)
    db.commit()
    return row.id


def test_prune_retention_keeps_critical_categories_and_sets_policy_flag():
    db = SessionLocal()
    try:
        auth_id = _create_audit_row(db, action="AUTH_LOGIN_SUCCESS", days_old=180)
        non_critical_id = _create_audit_row(db, action="UI_PAGE_VIEWED", days_old=180)

        result = prune_audit_logs_with_policy(
            db,
            cutoff=datetime.now(timezone.utc) - timedelta(days=90),
            dry_run=False,
        )
        assert result["retention_policy_applied"] is True
        assert "AUTH" in result["preserved_categories"]

        auth_row = db.query(AuditLog).filter(AuditLog.id == auth_id).first()
        deleted_row = db.query(AuditLog).filter(AuditLog.id == non_critical_id).first()
        assert auth_row is not None
        assert deleted_row is None
    finally:
        db.close()
