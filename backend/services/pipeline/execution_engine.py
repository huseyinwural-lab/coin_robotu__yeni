from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import BotProfile, ExecutionEvent, ExecutionStateTransition, PaperPosition, PositionLedgerEvent, User


def _build_state_path(execution_policy: dict) -> list[str]:
    path = ["created", "submitted", "acknowledged"]
    order_preference = execution_policy.get("order_preference", "limit_first")
    fallback_behavior = execution_policy.get("fallback_behavior", "market_fallback")
    partial_fill_tolerance = float(execution_policy.get("partial_fill_tolerance_pct", 50))

    if order_preference == "market_first":
        path.append("filled")
        return path

    if partial_fill_tolerance < 95:
        path.append("partially_filled")

    if fallback_behavior == "cancel_no_fill":
        path.extend(["cancel_requested", "cancelled"])
        return path

    if fallback_behavior in {"market_fallback", "limit_retry_then_market"}:
        path.extend(["fallback_submitted", "filled"])
        return path

    path.append("filled")
    return path


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
    execution_policy: dict,
    response_payload: dict,
) -> dict:
    state_path = _build_state_path(execution_policy)
    final_state = state_path[-1]
    enriched_payload = {
        **response_payload,
        "execution_policy": execution_policy,
        "state_machine": {
            "previous": "created",
            "current": final_state,
            "path": state_path,
        },
    }

    execution_event = ExecutionEvent(
        bot_profile_id=bot.id,
        exchange=bot.exchange,
        symbol=symbol,
        side=direction,
        quantity=quantity,
        mock_price=market_price,
        execution_status=final_state,
        response_payload=enriched_payload,
        note="Paper trading execution",
    )
    db.add(execution_event)
    db.flush()

    for index, state in enumerate(state_path):
        db.add(
            ExecutionStateTransition(
                execution_event_id=execution_event.id,
                state=state,
                sequence=index,
                details={
                    "symbol": symbol,
                    "side": direction,
                    "execution_style": execution_policy.get("style"),
                },
            )
        )

    if final_state in {"cancelled", "failed", "rejected"}:
        db.commit()
        return {
            "position": None,
            "execution_event": execution_event,
            "final_state": final_state,
            "state_path": state_path,
            "transition_count": len(state_path),
        }

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
                "execution_policy": execution_policy,
            },
        )
    )
    db.commit()
    db.refresh(position)
    return {
        "position": position,
        "execution_event": execution_event,
        "final_state": final_state,
        "state_path": state_path,
        "transition_count": len(state_path),
    }


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