from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import require_super_admin
from models import User
from schemas import AdminRevenueSummaryResponse
from services.revenue_engine_service import get_revenue_summary


router = APIRouter(prefix="/admin/revenue", tags=["admin_revenue"])


def _to_http_error(exc: Exception) -> HTTPException:
    message = str(exc)
    mapping = {
        "target_user_not_found": (status.HTTP_404_NOT_FOUND, "target_user_not_found"),
        "missing_revenue_pnl_share_rate": (status.HTTP_500_INTERNAL_SERVER_ERROR, "missing_revenue_pnl_share_rate"),
        "invalid_revenue_pnl_share_rate": (status.HTTP_500_INTERNAL_SERVER_ERROR, "invalid_revenue_pnl_share_rate"),
    }
    status_code, detail = mapping.get(message, (status.HTTP_400_BAD_REQUEST, message))
    return HTTPException(status_code=status_code, detail=detail)


@router.get("/summary", response_model=AdminRevenueSummaryResponse)
def admin_revenue_summary(
    environment: str = Query(default="live"),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    user_email: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    top_limit: int = Query(default=10, ge=1, le=50),
    _: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        return AdminRevenueSummaryResponse(
            **get_revenue_summary(
                db,
                environment=environment,
                start_date=start_date,
                end_date=end_date,
                user_id=user_id,
                user_email=user_email,
                symbol=symbol,
                top_limit=top_limit,
            )
        )
    except Exception as exc:
        raise _to_http_error(exc) from exc
