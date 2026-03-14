from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from db import get_db, redis_client
from deps import require_admin
from models import User
from services.pipeline.universe_engine import debug_effective_universe


router = APIRouter(prefix="/debug", tags=["debug_universe"])


@router.get("/effective-universe")
def get_debug_effective_universe(
    market_type: str = Query(default="spot", pattern="^(spot|futures)$"),
    scanner_mode: str = Query(default="ALL_MARKET_SYMBOLS"),
    selected_symbols: str = Query(default=""),
    top_n: int = Query(default=100, ge=1, le=1000),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    selected_list = [item.strip().upper() for item in selected_symbols.split(",") if item.strip()]
    payload = debug_effective_universe(
        db,
        redis_client,
        market_type=market_type,
        scanner_mode=scanner_mode,
        selected_symbols=selected_list,
        top_n=top_n,
    )
    payload["generated_at"] = payload.get("generated_at") or datetime.now(timezone.utc).isoformat()
    return payload
