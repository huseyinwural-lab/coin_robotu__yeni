from datetime import datetime

from sqlalchemy import and_, func, not_, or_
from sqlalchemy.orm import Session

from models import AuditLog


def _critical_action_filter():
    upper_action = func.upper(AuditLog.action)
    return or_(
        upper_action.like("AUTH%"),
        upper_action.like("%LOGIN%"),
        upper_action.like("%PASSWORD_RESET%"),
        upper_action.like("EXECUTION%"),
        upper_action.like("TRADING%"),
        upper_action.like("%ORDER%"),
        upper_action.like("ADMIN_ACTION%"),
    )


def prune_audit_logs_with_policy(db: Session, *, cutoff: datetime, dry_run: bool = False) -> dict:
    critical_filter = _critical_action_filter()
    base_filter = AuditLog.created_at < cutoff

    protected_count = db.query(AuditLog.id).filter(and_(base_filter, critical_filter)).count()
    delete_ids = [
        row[0]
        for row in db.query(AuditLog.id)
        .filter(and_(base_filter, not_(critical_filter)))
        .all()
    ]

    deleted_count = len(delete_ids)
    if not dry_run and delete_ids:
        db.query(AuditLog).filter(AuditLog.id.in_(delete_ids)).delete(synchronize_session=False)
        db.commit()

    return {
        "deleted_count": int(deleted_count),
        "protected_count": int(protected_count),
        "retention_policy_applied": True,
        "preserved_categories": ["AUTH", "EXECUTION", "ADMIN_ACTION"],
        "dry_run": bool(dry_run),
    }
