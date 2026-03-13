from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from services.strategy_observability_service import (
    get_rejection_analytics,
    get_score_metrics,
    get_strategy_observability_report,
    get_top_signals,
)

router = APIRouter(prefix="/admin/strategy", tags=["admin_strategy_observability"])


@router.get("/top-signals")
def top_signals(
    window: str = Query(default="24h"),
    top_n: int = Query(default=10, ge=1, le=50),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_top_signals(db, window=window, top_n=top_n)


@router.get("/rejection-analytics")
def rejection_analytics(
    window: str = Query(default="24h"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_rejection_analytics(db, window=window)


@router.get("/score-metrics")
def score_metrics(
    window: str = Query(default="24h"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_score_metrics(db, window=window)


@router.get("/report")
def strategy_observability_report(
    window: str = Query(default="24h"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_strategy_observability_report(db, window=window)


@router.get("/observability-report")
def strategy_observability_report_alias(
    window: str = Query(default="24h"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_strategy_observability_report(db, window=window)
