from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import BotProfile, ExecutionEvent, PaperPosition, PositionLedgerEvent, User


def open_paper_position(
    db: Session,
    *,
    user: User,
    bot: BotProfile,
    symbol: str,
    direction: str,
    market_price: float,
    quantity: float,
    leverage: int,
    stop_loss: float,
    take_profit: float,
    response_payload: dict,
) -> PaperPosition:
    execution_event = ExecutionEvent(
        bot_profile_id=bot.id,
        exchange=bot.exchange,
        symbol=symbol,
        side=direction,
        quantity=quantity,
        mock_price=market_price,
        execution_status="filled",
        response_payload=response_payload,
        note="Paper trading execution",
    )
    db.add(execution_event)
    db.flush()

    position = PaperPosition(
        user_id=user.id,
        bot_profile_id=bot.id,
        symbol=symbol,
        market_type=bot.market_type,
        side=direction,
        quantity=quantity,
        leverage=leverage,
        entry_price=market_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        status="open",
        unrealized_pnl=0,
        realized_pnl=0,
    )
    db.add(position)
    db.flush()

    db.add(
        PositionLedgerEvent(
            position_id=position.id,
            event_type="trade_open",
            payload={
                "entry_price": market_price,
                "quantity": quantity,
                "direction": direction,
                "execution_event_id": execution_event.id,
            },
        )
    )
    db.commit()
    db.refresh(position)
    return position


def refresh_open_positions(db: Session, latest_prices: dict[str, float]):
    open_positions = db.query(PaperPosition).filter(PaperPosition.status == "open").all()
    closed: list[PaperPosition] = []
    for position in open_positions:
        last_price = latest_prices.get(position.symbol)
        if last_price is None:
            continue

        pnl_factor = 1 if position.side == "long" else -1
        unrealized = (last_price - position.entry_price) * pnl_factor * position.quantity * position.leverage
        position.unrealized_pnl = round(unrealized, 6)

        close_reason = None
        if position.side == "long" and last_price <= position.stop_loss:
            close_reason = "stop_hit"
        elif position.side == "long" and last_price >= position.take_profit:
            close_reason = "tp_hit"
        elif position.side == "short" and last_price >= position.stop_loss:
            close_reason = "stop_hit"
        elif position.side == "short" and last_price <= position.take_profit:
            close_reason = "tp_hit"

        if close_reason:
            position.status = close_reason
            position.realized_pnl = round(unrealized, 6)
            position.closed_at = datetime.now(timezone.utc)
            db.add(
                PositionLedgerEvent(
                    position_id=position.id,
                    event_type="trade_close",
                    payload={"reason": close_reason, "exit_price": last_price, "realized_pnl": position.realized_pnl},
                )
            )
            closed.append(position)

    db.commit()
    return closed


def manual_close_position(db: Session, position: PaperPosition, reason: str):
    position.status = reason
    position.realized_pnl = position.unrealized_pnl
    position.closed_at = datetime.now(timezone.utc)
    db.add(
        PositionLedgerEvent(
            position_id=position.id,
            event_type="trade_close",
            payload={"reason": reason, "realized_pnl": position.realized_pnl},
        )
    )
    db.commit()
    db.refresh(position)
    return position