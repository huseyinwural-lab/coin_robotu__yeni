from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from services.audit_service import create_audit_log
from services.futures_strategy_service import get_futures_leverage_status
from services.pipeline.runtime import pipeline_runtime

router = APIRouter(prefix="/admin/futures/leverage", tags=["admin_futures_leverage"])


@router.get("/status")
def futures_leverage_status(
    refresh: bool = False,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    status = get_futures_leverage_status(db, pipeline_runtime.cache, current_admin.id, refresh=refresh)
    create_audit_log(
        db,
        action="FUTURES_LEVERAGE_STATUS_VIEWED",
        entity_type="futures_leverage_status",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={
            "symbol": status.get("symbol"),
            "final_leverage": status.get("final_leverage"),
            "size_ratio": status.get("size_ratio"),
        },
    )
    return status
