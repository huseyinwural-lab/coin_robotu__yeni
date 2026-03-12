from sqlalchemy.orm import Session

from core.users.user_risk_settings import get_or_create_user_risk_settings
from models import PaperPosition


def _safe_float(value: float | None) -> float:
    return float(value or 0)


def map_user_portfolio(
    db: Session,
    *,
    user_id: str,
    market_type: str = "spot",
    leverage: int = 1,
    margin_mode: str = "cross",
    position_side: str = "BOTH",
) -> dict:
    risk_row = get_or_create_user_risk_settings(db, user_id)
    safe_market_type = (market_type or "spot").strip().lower()
    safe_leverage = max(1, min(int(leverage or 1), 20))

    open_positions = (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id == user_id, PaperPosition.status == "open")
        .all()
    )
    closed_positions = (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id == user_id, PaperPosition.status != "open")
        .all()
    )

    open_notional = round(sum(_safe_float(row.quantity) * _safe_float(row.entry_price) for row in open_positions), 2)
    open_unrealized = round(sum(_safe_float(row.unrealized_pnl) for row in open_positions), 2)
    closed_pnl = round(sum(_safe_float(row.realized_pnl) for row in closed_positions), 2)

    current_capital = round(float(risk_row.base_capital) + closed_pnl, 2)
    available_balance = round(max(current_capital - open_notional, 0), 2)
    allocation_capital = round(current_capital * (float(risk_row.allocation_pct) / 100), 2)
    max_trade_loss = round(allocation_capital * (float(risk_row.trade_risk_pct) / 100), 2)
    daily_loss_limit_amount = round(current_capital * (float(risk_row.daily_loss_limit_pct) / 100), 2)
    recommended_order_notional = round(allocation_capital * (safe_leverage if safe_market_type == "futures" else 1), 2)
    utilization_pct = round((open_notional / max(current_capital, 1)) * 100, 2)

    warnings: list[str] = []
    if float(risk_row.allocation_pct) > 30:
        warnings.append("high_allocation")
    if float(risk_row.trade_risk_pct) > 15:
        warnings.append("high_trade_risk")
    if float(risk_row.daily_loss_limit_pct) > 5:
        warnings.append("high_daily_loss")
    if utilization_pct > 85:
        warnings.append("portfolio_high_utilization")

    return {
        "market_type": safe_market_type,
        "margin_mode": margin_mode,
        "position_side": position_side,
        "leverage": safe_leverage if safe_market_type == "futures" else None,
        "current_capital": current_capital,
        "available_balance": available_balance,
        "open_notional": open_notional,
        "open_unrealized_pnl": open_unrealized,
        "closed_pnl": closed_pnl,
        "allocation_pct": float(risk_row.allocation_pct),
        "trade_risk_pct": float(risk_row.trade_risk_pct),
        "daily_loss_limit_pct": float(risk_row.daily_loss_limit_pct),
        "allocation_capital": allocation_capital,
        "max_trade_loss": max_trade_loss,
        "daily_loss_limit_amount": daily_loss_limit_amount,
        "recommended_order_notional": recommended_order_notional,
        "compounding_enabled": bool(risk_row.compounding_enabled),
        "next_trade_base_capital": current_capital if risk_row.compounding_enabled else float(risk_row.base_capital),
        "open_positions_count": len(open_positions),
        "warnings": warnings,
    }