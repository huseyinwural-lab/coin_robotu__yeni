from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from db import get_db, redis_client
from deps import require_admin
from models import User
from services.scanner_runtime import get_latest_global_runtime_snapshot
from services.top_volume_fallback import evaluate_top_volume_fallback
from services.universe_service import get_exchange_universe_snapshot, get_full_market_universe


router = APIRouter(prefix="/admin/universe", tags=["admin_universe_runtime"])


@router.get("/runtime-summary")
def admin_runtime_universe_summary(
    scanner_mode: str = Query(default="all_market_symbols"),
    top_n: int = Query(default=50, ge=10, le=200),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    fallback_state = evaluate_top_volume_fallback(redis_client)
    effective_mode = "top_volume" if bool(fallback_state.get("active", False)) else scanner_mode
    universe = get_full_market_universe(db, redis_client, scanner_mode=effective_mode, selected_symbols=[], top_n=top_n)
    exchange_snapshot = get_exchange_universe_snapshot(scanner_mode=effective_mode, top_n=top_n)
    return {
        "scanner_mode_requested": scanner_mode,
        "scanner_mode_effective": effective_mode,
        "fallback_state": fallback_state,
        "universe": universe,
        "exchange_snapshot": exchange_snapshot,
    }


@router.get("/runtime-latest-scan")
def admin_runtime_latest_scan(
    current_admin: User = Depends(require_admin),
):
    _ = current_admin
    return get_latest_global_runtime_snapshot(redis_client)
