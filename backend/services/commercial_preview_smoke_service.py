from __future__ import annotations

from datetime import datetime, timezone

from db import SessionLocal
from models import User, UserRole
from services.admin_commercial_service import build_admin_commercial_overview


def run_commercial_preview_smoke_gate() -> dict:
    db = SessionLocal()
    started_at = datetime.now(timezone.utc)
    try:
        admin_user = db.query(User).filter(User.role == UserRole.SUPER_ADMIN, User.status == "active").first()
        if admin_user is None:
            raise RuntimeError("smoke_admin_missing")

        overview = build_admin_commercial_overview(
            db,
            time_window="last_30_days",
            environment="live",
            from_ts=None,
            to_ts=None,
        )
        required_blocks = [
            "financial_accuracy",
            "revenue_model",
            "user_economics",
            "pnl_analytics",
            "risk_summary",
            "usage_analytics",
            "data_quality",
            "export_ops",
            "alert_rail",
            "operational_controls",
        ]
        missing = [key for key in required_blocks if key not in overview]
        if missing:
            raise RuntimeError(f"smoke_missing_blocks:{','.join(missing)}")

        return {
            "status": "pass",
            "started_at": started_at.isoformat(),
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "checked_blocks": required_blocks,
            "missing_blocks": [],
        }
    finally:
        db.close()
