from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import BotProfile, ExecutionEvent, ExecutionStateTransition, PaperPosition, PositionLedgerEvent, User


def _build_state_path(execution_policy: dict, execution_context: dict | None = None) -> dict:
    context = execution_context or {}
    path = ["created", "submitted", "acknowledged"]
    order_preference = execution_policy.get("order_preference", "limit_first")
    fallback_behavior = execution_policy.get("fallback_behavior", "market_fallback")
    partial_fill_tolerance = float(execution_policy.get("partial_fill_tolerance_pct", 50))
    timeout_seconds = int(execution_policy.get("timeout_seconds", 8))
    execution_style = execution_policy.get("style", execution_policy.get("execution_style", "balanced"))
    retry_limit = int(execution_policy.get("retry_limit", 1))
    spread_bps = float(context.get("spread_bps", 0))
    latency_ms = float(context.get("latency_ms", 0))
    forced_outcome = context.get("forced_outcome")

    retry_budget_used = 0
    partial_fill_ratio = 0.0

    def _result():
        return {
            "path": path,
            "retry_budget_used": retry_budget_used,
            "partial_fill_ratio": round(partial_fill_ratio, 2),
        }

    if forced_outcome == "rejected":
        path.append("rejected")
        return _result()
    if forced_outcome == "failed":
        path.append("failed")
        return _result()
    if forced_outcome == "timeout":
        path.append("timeout")
        for retry_index in range(retry_limit):
            path.append(f"retry_{retry_index + 1}_submitted")
            retry_budget_used += 1
        if fallback_behavior in {"market_fallback", "limit_retry_then_market"} and retry_limit > 0:
            path.extend(["fallback_submitted", "filled"])
        else:
            path.extend(["cancel_requested", "cancelled", "failed"])
        return _result()
    if forced_outcome == "partial":
        partial_fill_ratio = float(context.get("partial_fill_ratio", 0.45))
        path.append("partially_filled")
        for retry_index in range(min(retry_limit, 2)):
            path.append(f"retry_{retry_index + 1}_submitted")
            retry_budget_used += 1
        path.extend(["fallback_submitted", "filled"])
        return _result()

    if execution_style == "aggressive" and spread_bps > 70:
        path.append("rejected")
        return _result()

    if latency_ms > 1200:
        path.append("timeout")
        for retry_index in range(retry_limit):
            path.append(f"retry_{retry_index + 1}_submitted")
            retry_budget_used += 1
        if fallback_behavior in {"market_fallback", "limit_retry_then_market"} and retry_limit > 0:
            path.extend(["fallback_submitted", "filled"])
        else:
            path.extend(["cancel_requested", "cancelled", "failed"])
        return _result()

    if order_preference == "market_first":
        path.append("filled")
        return _result()

    if partial_fill_tolerance < 95:
        path.append("partially_filled")
        partial_fill_ratio = 0.6

    if timeout_seconds <= 3:
        path.append("timeout")
        for retry_index in range(retry_limit):
            path.append(f"retry_{retry_index + 1}_submitted")
            retry_budget_used += 1
        if fallback_behavior in {"market_fallback", "limit_retry_then_market"} and retry_limit > 0:
            path.extend(["fallback_submitted", "filled"])
        else:
            path.extend(["cancel_requested", "cancelled", "failed"])
        return _result()

    if fallback_behavior == "cancel_no_fill":
        path.extend(["cancel_requested", "cancelled", "failed"])
        return _result()

    if fallback_behavior in {"market_fallback", "limit_retry_then_market"}:
        for retry_index in range(min(retry_limit, 1)):
            path.append(f"retry_{retry_index + 1}_submitted")
            retry_budget_used += 1
        path.extend(["fallback_submitted", "filled"])
        return _result()

    path.append("filled")
    return _result()


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
    execution_context: dict | None = None,
) -> dict:
    state_machine = _build_state_path(execution_policy, execution_context)
    state_path = state_machine["path"]
    final_state = state_path[-1]
    enriched_payload = {
        **response_payload,
        "execution_policy": execution_policy,
        "state_machine": {
            "previous": "created",
            "current": final_state,
            "path": state_path,
            "retry_budget_used": state_machine["retry_budget_used"],
            "partial_fill_ratio": state_machine["partial_fill_ratio"],
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
                    "retry_budget_used": state_machine["retry_budget_used"],
                    "partial_fill_ratio": state_machine["partial_fill_ratio"],
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
            "retry_budget_used": state_machine["retry_budget_used"],
            "partial_fill_ratio": state_machine["partial_fill_ratio"],
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
                "strategy_id": response_payload.get("strategy_id"),
                "lifecycle_state": "OPEN",
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
        "retry_budget_used": state_machine["retry_budget_used"],
        "partial_fill_ratio": state_machine["partial_fill_ratio"],
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
            lifecycle_state = "TAKE_PROFIT" if close_reason == "tp_hit" else "STOPPED"
            db.add(
                PositionLedgerEvent(
                    position_id=position.id,
                    event_type="trade_close",
                    payload={
                        "reason": close_reason,
                        "exit_price": last_price,
                        "realized_pnl": position.realized_pnl,
                        "lifecycle_state": lifecycle_state,
                    },
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