from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from db import get_db
from deps import require_super_admin
from models import User
from schemas import AdminCommercialTotalPnlResponse, CommercialUsageLogsResponse
from services.admin_commercial_service import build_total_pnl_bundle, build_usage_logs, export_monthly_pnl_excel

router = APIRouter(prefix="/admin/commercial", tags=["admin_commercial"])


@router.get("/usage-logs", response_model=CommercialUsageLogsResponse)
def admin_usage_logs(
    user_id: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    status_filter: str = Query(default="all", alias="status"),
    from_ts: str | None = Query(default=None),
    to_ts: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    _: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    return build_usage_logs(
        db,
        user_id=user_id,
        symbol=symbol,
        status_filter=status_filter,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=limit,
    )


@router.get("/total-pnl", response_model=AdminCommercialTotalPnlResponse)
def admin_total_pnl(
    _: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    return build_total_pnl_bundle(db)


@router.get("/monthly-pnl/export")
def admin_monthly_pnl_export(
    month: str | None = Query(default=None, description="YYYY-MM"),
    _: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    payload, filename = export_monthly_pnl_excel(db, month=month)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        iter([payload]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )