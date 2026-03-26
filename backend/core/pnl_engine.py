from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.alerts.runtime_alert_triggers import check_pnl_drop_trigger
from models import CommercialTrade, Order, Position


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _compute_realized_pnl(orders: list[Order]) -> float:
    buy_notional = sum(_safe_float(row.size) * _safe_float(row.avg_fill_price) for row in orders if str(row.side).upper() == "BUY")
    sell_notional = sum(_safe_float(row.size) * _safe_float(row.avg_fill_price) for row in orders if str(row.side).upper() == "SELL")
    return sell_notional - buy_notional


def _compute_fees(orders: list[Order], fee_rate: float = 0.001) -> float:
    traded_notional = sum(_safe_float(row.size) * _safe_float(row.avg_fill_price) for row in orders)
    return traded_notional * fee_rate


def _compute_funding(db: Session, *, user_id: str, symbol: str, since_hours: int = 24) -> float:
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    total = (
        db.query(func.coalesce(func.sum(CommercialTrade.funding_fee_usd), 0.0))
        .filter(
            CommercialTrade.user_id == user_id,
            CommercialTrade.symbol == symbol,
            CommercialTrade.trade_time >= since,
        )
        .scalar()
        or 0.0
    )
    return _safe_float(total)


def compute_runtime_pnl_positions(db: Session, *, user_id: str | None = None, symbol: str | None = None) -> list[dict]:
    query = db.query(Position)
    if user_id:
        query = query.filter(Position.user_id == user_id)
    if symbol:
        query = query.filter(Position.symbol == str(symbol).upper())

    rows = query.order_by(Position.updated_at.desc()).all()
    output: list[dict] = []

    for pos in rows:
        order_rows = (
            db.query(Order)
            .filter(
                Order.user_id == pos.user_id,
                Order.symbol == pos.symbol,
                Order.state.in_(["FILLED", "PARTIALLY_FILLED"]),
            )
            .order_by(Order.updated_at.desc())
            .all()
        )

        realized_pnl = _compute_realized_pnl(order_rows)
        fees = _compute_fees(order_rows)
        funding = _compute_funding(db, user_id=pos.user_id, symbol=pos.symbol)
        position_qty = _safe_float(pos.size)
        avg_entry_price = _safe_float(pos.entry_price)
        mark_price = _safe_float(pos.current_price)
        unrealized_pnl = (mark_price - avg_entry_price) * position_qty
        net_pnl = realized_pnl + unrealized_pnl - fees + funding

        output.append(
            {
                "user_id": pos.user_id,
                "symbol": pos.symbol,
                "position_qty": round(position_qty, 8),
                "avg_entry_price": round(avg_entry_price, 8),
                "mark_price": round(mark_price, 8),
                "realized_pnl": round(realized_pnl, 8),
                "unrealized_pnl": round(unrealized_pnl, 8),
                "fees": round(fees, 8),
                "funding": round(funding, 8),
                "net_pnl": round(net_pnl, 8),
                "updated_at": (pos.updated_at or datetime.now(timezone.utc)).isoformat(),
            }
        )

    return output


def compute_runtime_pnl_summary(db: Session, *, requester_role: str, requester_user_id: str) -> dict:
    is_admin = str(requester_role).lower() in {"super_admin", "admin", "ops"}
    pnl_rows = compute_runtime_pnl_positions(db, user_id=None if is_admin else requester_user_id)

    total_realized = sum(_safe_float(row["realized_pnl"]) for row in pnl_rows)
    total_unrealized = sum(_safe_float(row["unrealized_pnl"]) for row in pnl_rows)
    total_fees = sum(_safe_float(row["fees"]) for row in pnl_rows)
    total_funding = sum(_safe_float(row["funding"]) for row in pnl_rows)
    total_net = sum(_safe_float(row["net_pnl"]) for row in pnl_rows)

    by_symbol: dict[str, float] = {}
    by_user: dict[str, float] = {}
    for row in pnl_rows:
        by_symbol[row["symbol"]] = by_symbol.get(row["symbol"], 0.0) + _safe_float(row["net_pnl"])
        by_user[row["user_id"]] = by_user.get(row["user_id"], 0.0) + _safe_float(row["net_pnl"])

    for row in pnl_rows:
        previous_net = _safe_float(row["realized_pnl"])
        check_pnl_drop_trigger(
            db,
            user_id=row["user_id"],
            symbol=row["symbol"],
            previous_net_pnl=previous_net,
            current_net_pnl=_safe_float(row["net_pnl"]),
            threshold_pct=5.0,
        )

    return {
        "scope": "admin_all" if is_admin else "user_self",
        "requester_user_id": requester_user_id,
        "open_positions": len(pnl_rows),
        "realized_pnl": round(total_realized, 8),
        "unrealized_pnl": round(total_unrealized, 8),
        "fees": round(total_fees, 8),
        "funding": round(total_funding, 8),
        "net_pnl": round(total_net, 8),
        "by_symbol": {k: round(v, 8) for k, v in by_symbol.items()},
        "by_user": {k: round(v, 8) for k, v in by_user.items()} if is_admin else {requester_user_id: round(total_net, 8)},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
