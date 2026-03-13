from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import get_current_user, require_admin
from models import User
from schemas import (
    SymbolProviderConfigResponse,
    SymbolProviderConfigUpdateRequest,
    SymbolUniverseResponse,
    SymbolWatchlistCreateRequest,
    SymbolWatchlistResponse,
    SymbolWatchlistUpdateRequest,
)
from services.audit_service import create_audit_log
from services.symbol_selector_service import (
    create_symbol_watchlist,
    delete_symbol_watchlist,
    list_symbol_watchlists,
    provider_config_summary,
    resolve_symbol_universe,
    update_symbol_watchlist,
    upsert_alpha_vantage_key,
)

router = APIRouter(prefix="/symbol-selector", tags=["symbol_selector"])


@router.get("/universe", response_model=SymbolUniverseResponse)
def symbol_universe(
    source: str = Query(default="crypto"),
    exchange: str = Query(default="binance"),
    market_type: str = Query(default="spot"),
    mode: str = Query(default="all_exchange"),
    selected_symbols: str = Query(default=""),
    query: str = Query(default=""),
    quote_asset_filter: str = Query(default="ALL"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    payload = resolve_symbol_universe(
        db,
        source=source,
        exchange=exchange,
        market_type=market_type,
        mode=mode,
        selected_symbols=selected_symbols,
        query=query,
        quote_asset_filter=quote_asset_filter,
    )
    return SymbolUniverseResponse(**payload)


@router.get("/watchlists", response_model=list[SymbolWatchlistResponse])
def symbol_watchlists(
    source: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_symbol_watchlists(db, current_user.id, source=source)


@router.post("/watchlists", response_model=SymbolWatchlistResponse)
def create_watchlist(
    payload: SymbolWatchlistCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = create_symbol_watchlist(
        db,
        user_id=current_user.id,
        name=payload.name,
        source=payload.source,
        exchange=payload.exchange,
        market_type=payload.market_type,
        symbols=payload.symbols,
    )
    create_audit_log(
        db,
        action="SYMBOL_WATCHLIST_CREATED",
        entity_type="symbol_watchlist",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"source": row.source, "symbol_count": len(row.symbols or [])},
    )
    return row


@router.put("/watchlists/{watchlist_id}", response_model=SymbolWatchlistResponse)
def update_watchlist(
    watchlist_id: str,
    payload: SymbolWatchlistUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        row = update_symbol_watchlist(
            db,
            watchlist_id=watchlist_id,
            user_id=current_user.id,
            name=payload.name,
            symbols=payload.symbols,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    create_audit_log(
        db,
        action="SYMBOL_WATCHLIST_UPDATED",
        entity_type="symbol_watchlist",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"symbol_count": len(row.symbols or [])},
    )
    return row


@router.delete("/watchlists/{watchlist_id}")
def delete_watchlist(
    watchlist_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    deleted = delete_symbol_watchlist(db, watchlist_id=watchlist_id, user_id=current_user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="watchlist_not_found")

    create_audit_log(
        db,
        action="SYMBOL_WATCHLIST_DELETED",
        entity_type="symbol_watchlist",
        entity_id=watchlist_id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={},
    )
    return {"status": "ok", "deleted": True, "watchlist_id": watchlist_id}


@router.get("/provider-config", response_model=SymbolProviderConfigResponse)
def get_provider_config(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    return provider_config_summary(db)


@router.put("/provider-config/alpha-vantage", response_model=SymbolProviderConfigResponse)
def put_alpha_vantage_key(
    payload: SymbolProviderConfigUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    upsert_alpha_vantage_key(db, payload.api_key)
    create_audit_log(
        db,
        action="SYMBOL_PROVIDER_ALPHA_KEY_UPDATED",
        entity_type="symbol_provider",
        entity_id="alpha_vantage",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"has_key": True},
    )
    return provider_config_summary(db)
