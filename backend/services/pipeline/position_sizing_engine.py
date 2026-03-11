from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import PaperPosition, UserRiskSetting


def _get_or_create_risk_setting(db: Session, user_id: str) -> UserRiskSetting:
    row = db.query(UserRiskSetting).filter(UserRiskSetting.user_id == user_id).first()
    if row:
        return row

    row = UserRiskSetting(
        user_id=user_id,
        allocation_pct=20,
        trade_risk_pct=10,
        daily_loss_limit_pct=3,
        compounding_enabled=True,
        base_capital=10000,
    )
    db.add(row)
    db.flush()
    return row


def _closed_pnl(db: Session, user_id: str) -> float:
    rows = db.query(PaperPosition).filter(PaperPosition.user_id == user_id, PaperPosition.closed_at.is_not(None)).all()
    return float(sum(float(row.realized_pnl or 0) for row in rows))


def compute_position_sizing(db: Session, user_id: str, market_price: float) -> dict:
    risk_setting = _get_or_create_risk_setting(db, user_id)
    closed_pnl = _closed_pnl(db, user_id)
    equity = risk_setting.base_capital + (closed_pnl if risk_setting.compounding_enabled else 0)
    equity = max(float(equity), 0.01)

    trade_allocation_usdt = equity * (float(risk_setting.allocation_pct) / 100)
    risk_amount_usdt = trade_allocation_usdt * (float(risk_setting.trade_risk_pct) / 100)
    quantity = round(max(trade_allocation_usdt / max(market_price, 0.0001), 0.0001), 6)

    return {
        "equity": round(equity, 4),
        "trade_allocation_usdt": round(trade_allocation_usdt, 4),
        "risk_amount_usdt": round(risk_amount_usdt, 4),
        "daily_loss_limit_pct": float(risk_setting.daily_loss_limit_pct),
        "allocation_pct": float(risk_setting.allocation_pct),
        "trade_risk_pct": float(risk_setting.trade_risk_pct),
        "quantity": quantity,
    }


def daily_loss_usage(db: Session, user_id: str) -> dict:
    risk_setting = _get_or_create_risk_setting(db, user_id)
    start_of_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = (
        db.query(PaperPosition)
        .filter(
            PaperPosition.user_id == user_id,
            PaperPosition.closed_at.is_not(None),
            PaperPosition.closed_at >= start_of_day,
        )
        .all()
    )
    realized_loss = abs(sum(float(row.realized_pnl or 0) for row in rows if float(row.realized_pnl or 0) < 0))

    closed_pnl_total = _closed_pnl(db, user_id)
    equity = risk_setting.base_capital + (closed_pnl_total if risk_setting.compounding_enabled else 0)
    equity = max(float(equity), 0.01)
    loss_limit_amount = equity * (float(risk_setting.daily_loss_limit_pct) / 100)

    return {
        "daily_loss_amount": round(realized_loss, 4),
        "daily_loss_limit_amount": round(loss_limit_amount, 4),
        "daily_loss_limit_pct": float(risk_setting.daily_loss_limit_pct),
        "limit_exceeded": realized_loss >= loss_limit_amount,
    }


def consecutive_losses(db: Session, user_id: str, max_window: int = 10) -> int:
    rows = (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id == user_id, PaperPosition.closed_at.is_not(None))
        .order_by(PaperPosition.closed_at.desc())
        .limit(max_window)
        .all()
    )
    streak = 0
    for row in rows:
        if float(row.realized_pnl or 0) < 0:
            streak += 1
        else:
            break
    return streak