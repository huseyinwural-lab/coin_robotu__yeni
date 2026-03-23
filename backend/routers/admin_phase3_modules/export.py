from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from routers.admin_phase3_modules.common import shape_response

router = APIRouter(tags=["admin_phase3_export"])


@router.get("/incident-snapshots/export/filter-options")
def incident_snapshot_export_filter_options(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = db
    return shape_response(
        filter_scope_priority=["correlation_id", "execution_event_id", "time_range"],
        allowed_filter_values={
            "state": [
                "created",
                "submitted",
                "acknowledged",
                "partially_filled",
                "timeout",
                "fallback_submitted",
                "filled",
                "rejected",
                "failed",
                "cancelled",
            ],
            "status": ["filled", "timeout", "rejected", "failed", "cancelled", "submitted", "pending"],
            "source_type": ["production", "paper", "simulation", "replay"],
        },
        compare_mode_rules={
            "scope_type_must_match": True,
            "supported_compare_types": ["correlation_id", "execution_event_id", "time_range"],
        },
    )
