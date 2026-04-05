import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from db import redis_client
from models import PaperPosition, Position, RiskCluster

_POSITION_SYNC_CACHE: dict[str, datetime] = {}
_POSITION_SYNC_TTL_SECONDS = 20
_POSITION_PRICE_FROM_REDIS = str(os.getenv("POSITION_PRICE_FROM_REDIS", "false") or "false").strip().lower() in {"1", "true", "yes"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_price(symbol: str) -> float:
    if not _POSITION_PRICE_FROM_REDIS:
        return 0.0

    payload = redis_client.get(f"market:ticker:{symbol}")
    if payload and isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    try:
        import json

        parsed = json.loads(payload) if isinstance(payload, str) else {}
        return float(parsed.get("last_price") or parsed.get("mid_price") or 100)
    except Exception:
        return 0.0


def _cluster_map(db: Session) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in db.query(RiskCluster).all():
        for symbol in row.symbols or []:
            mapping[str(symbol).upper()] = row.cluster_id
    return mapping


def sync_position_state(
    db: Session,
    *,
    paper_position: PaperPosition,
    strategy_id: str | None = None,
    cluster_id: str | None = None,
) -> Position:
    row = db.query(Position).filter(Position.position_id == paper_position.id).first()
    if row is None:
        row = Position(
            position_id=paper_position.id,
            user_id=paper_position.user_id,
            created_at=paper_position.opened_at or _now(),
        )
        db.add(row)

    market_price = _safe_price(str(paper_position.symbol).upper())
    if market_price <= 0:
        entry = float(paper_position.entry_price or 0)
        qty = float(paper_position.quantity or 0)
        unrealized = float(paper_position.unrealized_pnl or 0)
        if qty > 0:
            market_price = entry + (unrealized / qty)
        else:
            market_price = entry

    if market_price <= 0:
        market_price = float(paper_position.entry_price or 0)
    row.symbol = str(paper_position.symbol).upper()
    row.size = float(paper_position.quantity or 0)
    row.entry_price = float(paper_position.entry_price or 0)
    row.current_price = market_price
    row.unrealized_pnl = float(paper_position.unrealized_pnl or 0)
    row.leverage = int(paper_position.leverage or 1)
    row.strategy_id = strategy_id if strategy_id is not None else row.strategy_id
    row.cluster_id = cluster_id if cluster_id is not None else row.cluster_id
    row.status = "open" if paper_position.status == "open" else "closed"
    row.updated_at = _now()
    db.flush()
    return row


def sync_all_positions_for_user(db: Session, user_id: str, *, include_closed: bool = True) -> list[Position]:
    cluster_mapping = _cluster_map(db)
    query = db.query(PaperPosition).filter(PaperPosition.user_id == user_id)
    if not include_closed:
        query = query.filter(PaperPosition.status == "open")
    rows = query.all()
    for paper in rows:
        sync_position_state(
            db,
            paper_position=paper,
            strategy_id=None,
            cluster_id=cluster_mapping.get(str(paper.symbol).upper(), "UNCLUSTERED"),
        )
    db.flush()
    return db.query(Position).filter(Position.user_id == user_id).order_by(Position.updated_at.desc()).all()


def _should_sync_positions(user_id: str) -> bool:
    now = _now()
    last = _POSITION_SYNC_CACHE.get(user_id)
    if last is None:
        _POSITION_SYNC_CACHE[user_id] = now
        return True
    elapsed = (now - last).total_seconds()
    if elapsed >= _POSITION_SYNC_TTL_SECONDS:
        _POSITION_SYNC_CACHE[user_id] = now
        return True
    return False


def list_user_positions(db: Session, user_id: str, include_closed: bool = False) -> list[Position]:
    latest_position_row = (
        db.query(Position.updated_at)
        .filter(Position.user_id == user_id)
        .order_by(Position.updated_at.desc())
        .first()
    )
    latest_updated_at = latest_position_row[0] if latest_position_row else None
    latest_is_fresh = bool(latest_updated_at and ((_now() - latest_updated_at).total_seconds() <= 300))

    if (not latest_is_fresh) and _should_sync_positions(user_id):
        sync_all_positions_for_user(db, user_id, include_closed=include_closed)
    query = db.query(Position).filter(Position.user_id == user_id)
    if not include_closed:
        query = query.filter(Position.status == "open")
    return query.order_by(Position.updated_at.desc()).all()


def list_all_open_positions(db: Session) -> list[Position]:
    cluster_mapping = _cluster_map(db)
    papers = db.query(PaperPosition).all()
    for paper in papers:
        sync_position_state(
            db,
            paper_position=paper,
            strategy_id=None,
            cluster_id=cluster_mapping.get(str(paper.symbol).upper(), "UNCLUSTERED"),
        )
    db.flush()
    return db.query(Position).filter(Position.status == "open").order_by(Position.updated_at.desc()).all()


def calculate_forced_liquidation_risk(position: Position) -> float:
    entry = float(position.entry_price or 0)
    current = float(position.current_price or 0)
    leverage = max(int(position.leverage or 1), 1)
    if entry <= 0:
        return 0.0
    distance_pct = abs((current - entry) / entry) * 100
    threshold = max(100 / leverage, 1)
    return round(min(100.0, (distance_pct / threshold) * 100), 4)
