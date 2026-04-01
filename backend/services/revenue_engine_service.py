import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import CommercialTrade, RevenueLedger, User


def _to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    return _to_utc(datetime.fromisoformat(normalized))


def _must_share_rate() -> float:
    raw = os.environ.get("REVENUE_PNL_SHARE_RATE")
    if raw is None:
        raise ValueError("missing_revenue_pnl_share_rate")
    parsed = float(str(raw).strip())
    if parsed > 1:
        parsed = parsed / 100.0
    if parsed < 0 or parsed > 1:
        raise ValueError("invalid_revenue_pnl_share_rate")
    return parsed


def _build_revenue_components(trade: CommercialTrade, *, pnl_share_rate: float) -> list[dict]:
    fee_amount = max(float(trade.commission_usd or 0), 0.0)
    realized_positive = max(float(trade.realized_pnl_usd or 0), 0.0)
    pnl_share_amount = realized_positive * pnl_share_rate
    return [
        {
            "component_type": "fee",
            "source_amount_usd": fee_amount,
            "share_rate": 1.0,
            "revenue_amount_usd": fee_amount,
            "details": {
                "basis": "commission_usd",
                "commission_asset": trade.commission_asset,
            },
        },
        {
            "component_type": "pnl_share",
            "source_amount_usd": realized_positive,
            "share_rate": pnl_share_rate,
            "revenue_amount_usd": pnl_share_amount,
            "details": {
                "basis": "realized_positive_pnl_usd",
                "realized_pnl_usd": float(trade.realized_pnl_usd or 0),
            },
        },
    ]


def upsert_revenue_for_trades(db: Session, *, trades: list[CommercialTrade]) -> dict:
    if not trades:
        return {"processed": 0, "inserted": 0, "duplicate": 0}

    pnl_share_rate = _must_share_rate()
    trade_ids = [item.id for item in trades if item.id]
    existing_rows = (
        db.query(RevenueLedger.trade_id, RevenueLedger.component_type)
        .filter(RevenueLedger.trade_id.in_(trade_ids))
        .all()
    )
    existing_keys = {(row.trade_id, row.component_type) for row in existing_rows}

    inserted = 0
    duplicate = 0
    for trade in trades:
        components = _build_revenue_components(trade, pnl_share_rate=pnl_share_rate)
        for component in components:
            key = (trade.id, component["component_type"])
            if key in existing_keys:
                duplicate += 1
                continue

            db.add(
                RevenueLedger(
                    user_id=trade.user_id,
                    trade_id=trade.id,
                    exchange=trade.exchange,
                    market_type=trade.market_type,
                    environment=trade.environment,
                    symbol=trade.symbol,
                    trade_time=trade.trade_time,
                    component_type=component["component_type"],
                    source_amount_usd=round(component["source_amount_usd"], 10),
                    share_rate=round(component["share_rate"], 10),
                    revenue_amount_usd=round(component["revenue_amount_usd"], 10),
                    details={
                        "exchange_trade_id": trade.exchange_trade_id,
                        "order_id": trade.order_id,
                        **component["details"],
                    },
                )
            )
            existing_keys.add(key)
            inserted += 1

    return {"processed": len(trades), "inserted": inserted, "duplicate": duplicate}


def sync_revenue_ledger_for_scope(
    db: Session,
    *,
    user_id: str,
    environment: str,
    market_types: list[str],
    symbols: list[str],
    start_ts: str | None,
    end_ts: str | None,
) -> dict:
    query = db.query(CommercialTrade).filter(
        CommercialTrade.user_id == user_id,
        CommercialTrade.environment == environment,
        CommercialTrade.exchange == "binance",
    )
    if market_types:
        query = query.filter(CommercialTrade.market_type.in_(market_types))
    if symbols:
        query = query.filter(CommercialTrade.symbol.in_(symbols))

    start_dt = _parse_datetime(start_ts)
    end_dt = _parse_datetime(end_ts)
    if start_dt is not None:
        query = query.filter(CommercialTrade.trade_time >= start_dt)
    if end_dt is not None:
        query = query.filter(CommercialTrade.trade_time <= end_dt)

    trades = query.order_by(CommercialTrade.trade_time.asc(), CommercialTrade.id.asc()).all()
    return upsert_revenue_for_trades(db, trades=trades)


def get_revenue_summary(
    db: Session,
    *,
    environment: str,
    start_date: str | None,
    end_date: str | None,
    user_id: str | None,
    user_email: str | None,
    symbol: str | None,
    top_limit: int,
) -> dict:
    query = db.query(RevenueLedger).filter(RevenueLedger.environment == environment)

    if user_email:
        target_user = db.query(User).filter(User.email == user_email.strip().lower()).first()
        if target_user is None:
            raise ValueError("target_user_not_found")
        query = query.filter(RevenueLedger.user_id == target_user.id)
    elif user_id:
        query = query.filter(RevenueLedger.user_id == user_id)

    if symbol:
        query = query.filter(RevenueLedger.symbol == symbol.strip().upper())

    start_dt = _parse_datetime(start_date)
    end_dt = _parse_datetime(end_date)
    if start_dt is not None:
        query = query.filter(RevenueLedger.trade_time >= start_dt)
    if end_dt is not None:
        query = query.filter(RevenueLedger.trade_time <= end_dt)

    rows = query.all()
    total_revenue = round(sum(float(item.revenue_amount_usd or 0) for item in rows), 8)

    today = datetime.now(timezone.utc).date()
    today_revenue = round(
        sum(float(item.revenue_amount_usd or 0) for item in rows if item.trade_time and item.trade_time.date() == today),
        8,
    )

    by_user: dict[str, float] = {}
    by_symbol: dict[str, float] = {}
    by_day: dict[str, dict] = {}
    user_map = {
        row.id: row.email
        for row in db.query(User.id, User.email)
        .filter(User.id.in_(list({item.user_id for item in rows})))
        .all()
    }

    for item in rows:
        amount = float(item.revenue_amount_usd or 0)
        by_user[item.user_id] = by_user.get(item.user_id, 0.0) + amount
        by_symbol[item.symbol] = by_symbol.get(item.symbol, 0.0) + amount

        day_key = item.trade_time.date().isoformat() if item.trade_time else "unknown"
        day_bucket = by_day.setdefault(day_key, {"date": day_key, "total": 0.0, "fee": 0.0, "pnl_share": 0.0})
        day_bucket["total"] += amount
        if item.component_type == "fee":
            day_bucket["fee"] += amount
        elif item.component_type == "pnl_share":
            day_bucket["pnl_share"] += amount

    top_users = [
        {"user_id": uid, "email": user_map.get(uid, "unknown"), "revenue_usd": round(amount, 8)}
        for uid, amount in sorted(by_user.items(), key=lambda kv: (-kv[1], kv[0]))[:top_limit]
    ]
    top_symbols = [
        {"symbol": sym, "revenue_usd": round(amount, 8)}
        for sym, amount in sorted(by_symbol.items(), key=lambda kv: (-kv[1], kv[0]))[:top_limit]
    ]
    daily = [
        {
            "date": item["date"],
            "total_revenue_usd": round(item["total"], 8),
            "fee_revenue_usd": round(item["fee"], 8),
            "pnl_share_revenue_usd": round(item["pnl_share"], 8),
        }
        for item in sorted(by_day.values(), key=lambda value: value["date"])
    ]

    return {
        "status": "ok",
        "environment": environment,
        "applied_filters": {
            "start_date": start_date,
            "end_date": end_date,
            "user_id": user_id,
            "user_email": user_email,
            "symbol": symbol,
            "top_limit": top_limit,
        },
        "total_revenue_usd": total_revenue,
        "today_revenue_usd": today_revenue,
        "top_users": top_users,
        "top_symbols": top_symbols,
        "daily_revenue": daily,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
