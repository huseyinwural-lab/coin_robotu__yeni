from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from db import get_db, redis_client
from deps import require_user
from models import User
from services.scanner_runtime import get_runtime_snapshot, run_scanner_runtime


router = APIRouter(prefix="/user/scanner/runtime", tags=["user_scanner_runtime"])


@router.post("/run")
def run_runtime_scan(
    symbol_selection_mode: str = Query(default="all_market_symbols"),
    max_results: int = Query(default=120, ge=10, le=500),
    selected_symbols: str = Query(default=""),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    selected_list = [item.strip().upper() for item in selected_symbols.split(",") if item.strip()]
    return run_scanner_runtime(
        db,
        redis_client,
        user_id=current_user.id,
        symbol_selection_mode=symbol_selection_mode,
        selected_symbols=selected_list,
        symbol_source="crypto",
        max_results=max_results,
    )


@router.get("/snapshot")
def get_runtime_scan_snapshot(
    current_user: User = Depends(require_user),
):
    return get_runtime_snapshot(redis_client, user_id=current_user.id)
