from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from db import get_db
from deps import require_super_admin
from models import User
from services.analytics_snapshot_service import export_revenue_ledger, export_user_economics_aggregates


router = APIRouter(prefix="/admin/export", tags=["admin_export"])


def _to_http_error(exc: Exception) -> HTTPException:
    detail = str(exc)
    if detail == "target_user_not_found":
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    if detail in {"invalid_export_format", "invalid_snapshot_type"}:
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


@router.get("/revenue")
def export_revenue(
    environment: str = Query(default="live"),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    user_email: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    output: str = Query(default="csv"),
    _: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        payload_iter, media_type, filename = export_revenue_ledger(
            db,
            environment=environment,
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
            user_email=user_email,
            symbol=symbol,
            output=output,
        )
    except Exception as exc:
        raise _to_http_error(exc) from exc

    return StreamingResponse(
        payload_iter,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/user-economics")
def export_user_economics(
    environment: str = Query(default="live"),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    user_email: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    churn_inactive_days: int = Query(default=30, ge=1, le=365),
    cohort_month: str | None = Query(default=None),
    top_limit: int = Query(default=200, ge=1, le=500),
    output: str = Query(default="csv"),
    _: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        payload_iter, media_type, filename = export_user_economics_aggregates(
            db,
            environment=environment,
            start_date=start_date,
            end_date=end_date,
            user_email=user_email,
            symbol=symbol,
            churn_inactive_days=churn_inactive_days,
            cohort_month=cohort_month,
            top_limit=top_limit,
            output=output,
        )
    except Exception as exc:
        raise _to_http_error(exc) from exc

    return StreamingResponse(
        payload_iter,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
