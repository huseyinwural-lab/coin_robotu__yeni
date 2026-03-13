import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import UserIndicatorSavedQuery, UserIndicatorWatchlist


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def list_saved_queries(db: Session, user_id: str) -> list[UserIndicatorSavedQuery]:
    return (
        db.query(UserIndicatorSavedQuery)
        .filter(UserIndicatorSavedQuery.user_id == user_id)
        .order_by(UserIndicatorSavedQuery.updated_at.desc())
        .all()
    )


def create_saved_query(
    db: Session,
    *,
    user_id: str,
    name: str,
    exchange: str,
    market_type: str,
    timeframe: str,
    query_expression: str,
    symbol_universe,
    filter_snapshot: dict,
    schema_version: int,
    result_limit: int,
) -> UserIndicatorSavedQuery:
    normalized_name = name.strip() if name else ""
    if not normalized_name:
        normalized_name = f"Query {datetime.now(timezone.utc).strftime('%H:%M:%S')}"

    existing = (
        db.query(UserIndicatorSavedQuery)
        .filter(
            UserIndicatorSavedQuery.user_id == user_id,
            UserIndicatorSavedQuery.name == normalized_name,
        )
        .first()
    )

    if existing:
        existing.exchange = exchange
        existing.market_type = market_type
        existing.timeframe = timeframe
        existing.query_expression = query_expression
        existing.symbol_universe = symbol_universe if isinstance(symbol_universe, list) else []
        existing.filter_snapshot = filter_snapshot if isinstance(filter_snapshot, dict) else {}
        existing.schema_version = int(schema_version or 1)
        existing.result_limit = result_limit
        existing.updated_at = _utc_now()
        db.commit()
        db.refresh(existing)
        return existing

    row = UserIndicatorSavedQuery(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name=normalized_name,
        exchange=exchange,
        market_type=market_type,
        timeframe=timeframe,
        query_expression=query_expression,
        symbol_universe=symbol_universe if isinstance(symbol_universe, list) else [],
        filter_snapshot=filter_snapshot if isinstance(filter_snapshot, dict) else {},
        schema_version=int(schema_version or 1),
        result_limit=result_limit,
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_saved_query(db: Session, *, user_id: str, query_id: str) -> bool:
    row = (
        db.query(UserIndicatorSavedQuery)
        .filter(UserIndicatorSavedQuery.id == query_id, UserIndicatorSavedQuery.user_id == user_id)
        .first()
    )
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def list_watchlist(db: Session, user_id: str) -> list[UserIndicatorWatchlist]:
    return (
        db.query(UserIndicatorWatchlist)
        .filter(UserIndicatorWatchlist.user_id == user_id)
        .order_by(UserIndicatorWatchlist.created_at.desc())
        .all()
    )


def add_watchlist_symbol(
    db: Session,
    *,
    user_id: str,
    exchange: str,
    market_type: str,
    symbol: str,
    note: str,
    context_snapshot: dict,
) -> UserIndicatorWatchlist:
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("Sembol boş olamaz")

    existing = (
        db.query(UserIndicatorWatchlist)
        .filter(
            UserIndicatorWatchlist.user_id == user_id,
            UserIndicatorWatchlist.exchange == exchange,
            UserIndicatorWatchlist.market_type == market_type,
            UserIndicatorWatchlist.symbol == normalized_symbol,
        )
        .first()
    )
    if existing:
        existing.note = note or existing.note
        existing.context_snapshot = context_snapshot if isinstance(context_snapshot, dict) else existing.context_snapshot
        db.commit()
        db.refresh(existing)
        return existing

    row = UserIndicatorWatchlist(
        id=str(uuid.uuid4()),
        user_id=user_id,
        exchange=exchange,
        market_type=market_type,
        symbol=normalized_symbol,
        note=note or "",
        context_snapshot=context_snapshot if isinstance(context_snapshot, dict) else {},
        created_at=_utc_now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_watchlist_symbol(db: Session, *, user_id: str, watch_id: str) -> bool:
    row = (
        db.query(UserIndicatorWatchlist)
        .filter(UserIndicatorWatchlist.id == watch_id, UserIndicatorWatchlist.user_id == user_id)
        .first()
    )
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
