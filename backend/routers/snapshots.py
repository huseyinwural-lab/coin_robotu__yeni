from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import require_super_admin
from models import User
from services.analytics_snapshot_service import compare_analytics_snapshots, list_analytics_snapshots, run_analytics_snapshot


router = APIRouter(prefix="/admin/snapshots", tags=["admin_snapshots"])


def _to_http_error(exc: Exception) -> HTTPException:
    detail = str(exc)
    mapping = {
        "invalid_snapshot_type": (status.HTTP_400_BAD_REQUEST, detail),
        "snapshot_not_found": (status.HTTP_404_NOT_FOUND, detail),
        "snapshot_environment_mismatch": (status.HTTP_400_BAD_REQUEST, detail),
        "snapshot_type_mismatch": (status.HTTP_400_BAD_REQUEST, detail),
        "missing_revenue_pnl_share_rate": (status.HTTP_500_INTERNAL_SERVER_ERROR, detail),
        "invalid_revenue_pnl_share_rate": (status.HTTP_500_INTERNAL_SERVER_ERROR, detail),
    }
    status_code, final_detail = mapping.get(detail, (status.HTTP_400_BAD_REQUEST, detail))
    return HTTPException(status_code=status_code, detail=final_detail)


@router.get("")
def get_snapshots(
    environment: str = Query(default="live"),
    snapshot_type: str = Query(default="daily"),
    limit: int = Query(default=50, ge=1, le=200),
    _: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        return list_analytics_snapshots(
            db,
            environment=environment,
            snapshot_type=snapshot_type,
            limit=limit,
        )
    except Exception as exc:
        raise _to_http_error(exc) from exc


@router.post("/run")
def run_snapshot(
    environment: str = Query(default="live"),
    snapshot_type: str = Query(default="daily"),
    as_of_date: str | None = Query(default=None),
    churn_inactive_days: int = Query(default=30, ge=1, le=365),
    top_limit: int = Query(default=20, ge=1, le=200),
    _: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        return run_analytics_snapshot(
            db,
            environment=environment,
            snapshot_type=snapshot_type,
            as_of_date=as_of_date,
            churn_inactive_days=churn_inactive_days,
            top_limit=top_limit,
        )
    except Exception as exc:
        raise _to_http_error(exc) from exc


@router.get("/compare")
def compare_snapshots(
    base_snapshot_id: str = Query(...),
    target_snapshot_id: str = Query(...),
    _: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        return compare_analytics_snapshots(
            db,
            base_snapshot_id=base_snapshot_id,
            target_snapshot_id=target_snapshot_id,
        )
    except Exception as exc:
        raise _to_http_error(exc) from exc
