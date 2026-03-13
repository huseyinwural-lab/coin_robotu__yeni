from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db import get_db
from deps import require_user
from models import User
from schemas import (
    IndicatorScreenerPresetResponse,
    IndicatorScreenerRunRequest,
    IndicatorScreenerRunResponse,
    UserIndicatorSavedQueryCreateRequest,
    UserIndicatorSavedQueryResponse,
    UserIndicatorWatchlistCreateRequest,
    UserIndicatorWatchlistResponse,
)
from services.audit_service import create_audit_log
from services.indicator_screener.indicator_query_engine_service import indicator_screener_presets, run_indicator_query_engine
from services.indicator_screener.storage_service import (
    add_watchlist_symbol,
    create_saved_query,
    delete_saved_query,
    delete_watchlist_symbol,
    list_saved_queries,
    list_watchlist,
)

router = APIRouter(prefix="/user/indicator-screener", tags=["user_indicator_screener"])


@router.post("/run", response_model=IndicatorScreenerRunResponse)
def run_indicator_screener(
    payload: IndicatorScreenerRunRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    result = run_indicator_query_engine(
        db=db,
        user_id=current_user.id,
        exchange=payload.exchange,
        market_type=payload.market_type,
        timeframe=payload.timeframe,
        query_expression=payload.query_expression,
        symbol_universe=payload.symbol_universe,
        limit=payload.limit,
        filter_payload=payload.filter_payload,
    )

    create_audit_log(
        db,
        action="user_indicator_screener_run",
        entity_type="user_indicator_screener",
        entity_id=current_user.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        severity="warning" if not result.get("query_valid", False) else "info",
        details={
            "query_expression": payload.query_expression,
            "query_valid": result.get("query_valid", False),
            "result_state": result.get("result_state", "unknown"),
            "filter_error": result.get("filter_error"),
            "match_count": result.get("match_count", 0),
            "evaluated_count": result.get("evaluated_count", 0),
            "market_type": payload.market_type,
            "timeframe": payload.timeframe,
            "applied_filters": result.get("applied_filters", {}),
        },
    )
    return IndicatorScreenerRunResponse(**result)


@router.get("/presets", response_model=list[IndicatorScreenerPresetResponse])
def screener_presets(current_user: User = Depends(require_user)):
    _ = current_user
    return indicator_screener_presets()


@router.get("/saved-queries", response_model=list[UserIndicatorSavedQueryResponse])
def screener_saved_queries(current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    return list_saved_queries(db, current_user.id)


@router.post("/saved-queries", response_model=UserIndicatorSavedQueryResponse)
def screener_saved_query_create(
    payload: UserIndicatorSavedQueryCreateRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    row = create_saved_query(
        db,
        user_id=current_user.id,
        name=payload.name,
        exchange=payload.exchange,
        market_type=payload.market_type,
        timeframe=payload.timeframe,
        query_expression=payload.query_expression,
        symbol_universe=payload.symbol_universe,
        filter_snapshot=payload.filter_snapshot,
        schema_version=payload.schema_version,
        result_limit=payload.result_limit,
    )
    create_audit_log(
        db,
        action="user_indicator_saved_query_upsert",
        entity_type="indicator_saved_query",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={
            "name": row.name,
            "exchange": row.exchange,
            "market_type": row.market_type,
            "timeframe": row.timeframe,
            "schema_version": row.schema_version,
        },
    )
    return row


@router.delete("/saved-queries/{query_id}")
def screener_saved_query_delete(query_id: str, current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    deleted = delete_saved_query(db, user_id=current_user.id, query_id=query_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="saved_query_not_found")
    create_audit_log(
        db,
        action="user_indicator_saved_query_deleted",
        entity_type="indicator_saved_query",
        entity_id=query_id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={},
    )
    return {"status": "ok", "deleted": True, "query_id": query_id}


@router.get("/watchlist", response_model=list[UserIndicatorWatchlistResponse])
def screener_watchlist(current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    return list_watchlist(db, current_user.id)


@router.post("/watchlist", response_model=UserIndicatorWatchlistResponse)
def screener_watchlist_add(
    payload: UserIndicatorWatchlistCreateRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        row = add_watchlist_symbol(
            db,
            user_id=current_user.id,
            exchange=payload.exchange,
            market_type=payload.market_type,
            symbol=payload.symbol,
            note=payload.note,
            context_snapshot=payload.context_snapshot,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    create_audit_log(
        db,
        action="user_indicator_watchlist_upsert",
        entity_type="indicator_watchlist",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={
            "symbol": row.symbol,
            "exchange": row.exchange,
            "market_type": row.market_type,
            "context_snapshot": row.context_snapshot,
        },
    )
    return row


@router.delete("/watchlist/{watch_id}")
def screener_watchlist_delete(watch_id: str, current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    deleted = delete_watchlist_symbol(db, user_id=current_user.id, watch_id=watch_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="watchlist_item_not_found")
    create_audit_log(
        db,
        action="user_indicator_watchlist_deleted",
        entity_type="indicator_watchlist",
        entity_id=watch_id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={},
    )
    return {"status": "ok", "deleted": True, "watch_id": watch_id}
