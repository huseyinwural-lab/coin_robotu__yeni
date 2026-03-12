import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from db import redis_client
from models import (
    BotProfile,
    PaperPosition,
    PendingSignal,
    PositionLedgerEvent,
    SignalEvent,
    UserScannerResult,
    UserSignalMode,
)
from services.explainability_service import record_decision_trace
from services.pipeline.cache_store import get_json
from services.pipeline.spot_strategy_service import scan_spot_universe_for_signals

ALLOWED_SIGNAL_MODES = {"ASSISTED", "AUTO", "MANUAL"}
DEFAULT_SIGNAL_MODE = "ASSISTED"


def _normalize_mode(mode: str | None) -> str:
    candidate = (mode or DEFAULT_SIGNAL_MODE).strip().upper()
    if candidate not in ALLOWED_SIGNAL_MODES:
        return DEFAULT_SIGNAL_MODE
    return candidate


def _user_symbols_scope(db: Session, user_id: str) -> set[str]:
    rows = db.query(BotProfile).filter(BotProfile.user_id == user_id).all()
    symbols: set[str] = set()
    for row in rows:
        symbols.update((row.symbols or []))
    return {symbol.upper() for symbol in symbols if symbol}


def _default_bot_for_user(db: Session, user_id: str, symbols: list[str]) -> BotProfile:
    row = db.query(BotProfile).filter(BotProfile.user_id == user_id).order_by(BotProfile.created_at.asc()).first()
    if row:
        return row

    row = BotProfile(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name="Assisted Signal Bot",
        exchange="binance",
        market_type="spot",
        symbols=symbols[:6] if symbols else ["BTCUSDT"],
        strategy_type="spot_pullback",
        timeframe="15m",
        trend_timeframe="1h",
        leverage=1,
        is_enabled=True,
        is_running=False,
    )
    db.add(row)
    db.flush()
    return row


def get_or_create_signal_mode(db: Session, user_id: str) -> UserSignalMode:
    row = db.query(UserSignalMode).filter(UserSignalMode.user_id == user_id).first()
    if row:
        return row

    row = UserSignalMode(id=str(uuid.uuid4()), user_id=user_id, mode=DEFAULT_SIGNAL_MODE)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_signal_mode(db: Session, user_id: str, mode: str) -> UserSignalMode:
    row = get_or_create_signal_mode(db, user_id)
    row.mode = _normalize_mode(mode)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def list_user_scanner_results(db: Session, user_id: str, limit: int = 100) -> list[UserScannerResult]:
    return (
        db.query(UserScannerResult)
        .filter(UserScannerResult.user_id == user_id)
        .order_by(UserScannerResult.generated_at.desc())
        .limit(limit)
        .all()
    )


def list_user_signals(db: Session, user_id: str, limit: int = 100) -> list[PendingSignal]:
    return (
        db.query(PendingSignal)
        .filter(PendingSignal.user_id == user_id)
        .order_by(PendingSignal.created_at.desc())
        .limit(limit)
        .all()
    )


def run_user_scanner(db: Session, user_id: str, *, requested_mode: str | None = None, max_results: int = 20) -> dict:
    mode_row = get_or_create_signal_mode(db, user_id)
    mode = _normalize_mode(requested_mode or mode_row.mode)
    if mode_row.mode != mode:
        mode_row.mode = mode
        mode_row.updated_at = datetime.now(timezone.utc)

    payload = scan_spot_universe_for_signals(redis_client, max_symbols=max(max_results, 30))
    ranked = payload.get("top_ranked", [])
    scoped_symbols = _user_symbols_scope(db, user_id)

    if scoped_symbols:
        ranked = [item for item in ranked if str(item.get("symbol", "")).upper() in scoped_symbols]
    selected = ranked[:max_results]
    selected_symbols = [str(item.get("symbol", "BTCUSDT")).upper() for item in selected]

    db.query(UserScannerResult).filter(UserScannerResult.user_id == user_id).delete()

    run_id = str(uuid.uuid4())
    bot = _default_bot_for_user(db, user_id, selected_symbols)
    actionable_count = 0
    queued_count = 0

    for item in selected:
        signal_value = str(item.get("signal", "none") or "none").lower()
        reason_codes = item.get("reason_codes") or []
        confidence = float(item.get("signal_strength") or 0)
        score = float(item.get("signal_score") or 0)
        symbol = str(item.get("symbol", "BTCUSDT")).upper()
        strategy_code = str(item.get("strategy_code") or "spot_pullback_v1")

        scanner_row = UserScannerResult(
            id=str(uuid.uuid4()),
            run_id=run_id,
            user_id=user_id,
            symbol=symbol,
            strategy_code=strategy_code,
            signal=signal_value,
            confidence=confidence,
            signal_score=score,
            reason_codes=reason_codes,
            payload=item,
        )
        db.add(scanner_row)

        if signal_value == "none":
            continue

        actionable_count += 1
        signal_event = SignalEvent(
            id=str(uuid.uuid4()),
            bot_profile_id=bot.id,
            user_id=user_id,
            symbol=symbol,
            market_type=bot.market_type,
            timeframe=bot.timeframe,
            strategy_id=strategy_code,
            signal=signal_value,
            direction="long" if signal_value == "long" else "short",
            confidence=max(confidence, round(score / 100, 4)),
            reason_codes=reason_codes,
        )
        db.add(signal_event)
        db.flush()

        pending_status = "pending" if mode in {"ASSISTED", "AUTO"} else "info"
        if pending_status == "pending":
            queued_count += 1

        pending_row = PendingSignal(
            id=str(uuid.uuid4()),
            signal_id=signal_event.id,
            user_id=user_id,
            symbol=symbol,
            strategy_code=strategy_code,
            confidence=signal_event.confidence,
            mode=mode,
            status=pending_status,
            created_at=datetime.now(timezone.utc),
        )
        db.add(pending_row)

        record_decision_trace(
            db,
            user_id=user_id,
            trace_scope="signal",
            trace_type="scanner_signal_generated",
            entity_id=pending_row.id,
            strategy_code=strategy_code,
            decision_status="PENDING_REVIEW" if pending_status == "pending" else "INFO_ONLY",
            reason_codes=reason_codes or ["signal_generated_without_reason_code"],
            feature_snapshot={
                "confidence": float(signal_event.confidence or 0),
                "signal_score": score,
                "mode": mode,
                "signal": signal_value,
            },
            context_payload={
                "run_id": run_id,
                "symbol": symbol,
                "signal_event_id": signal_event.id,
                "pending_status": pending_status,
            },
        )

    if actionable_count == 0 and selected:
        fallback = selected[0]
        fallback_symbol = str(fallback.get("symbol", "BTCUSDT")).upper()
        fallback_strategy = str(fallback.get("strategy_code") or "spot_pullback_v1")
        fallback_signal = SignalEvent(
            id=str(uuid.uuid4()),
            bot_profile_id=bot.id,
            user_id=user_id,
            symbol=fallback_symbol,
            market_type=bot.market_type,
            timeframe=bot.timeframe,
            strategy_id=fallback_strategy,
            signal="long",
            direction="long",
            confidence=0.55,
            reason_codes=["fallback_signal_low_activity"],
        )
        db.add(fallback_signal)
        db.flush()

        pending_status = "pending" if mode in {"ASSISTED", "AUTO"} else "info"
        if pending_status == "pending":
            queued_count += 1
        actionable_count += 1
        fallback_pending = PendingSignal(
            id=str(uuid.uuid4()),
            signal_id=fallback_signal.id,
            user_id=user_id,
            symbol=fallback_symbol,
            strategy_code=fallback_strategy,
            confidence=0.55,
            mode=mode,
            status=pending_status,
            created_at=datetime.now(timezone.utc),
            decision_note="fallback_signal_created",
        )
        db.add(fallback_pending)
        record_decision_trace(
            db,
            user_id=user_id,
            trace_scope="signal",
            trace_type="scanner_fallback_signal",
            entity_id=fallback_pending.id,
            strategy_code=fallback_strategy,
            decision_status="PENDING_REVIEW" if pending_status == "pending" else "INFO_ONLY",
            reason_codes=["fallback_signal_low_activity"],
            feature_snapshot={
                "confidence": 0.55,
                "mode": mode,
                "signal": "long",
            },
            context_payload={
                "run_id": run_id,
                "symbol": fallback_symbol,
                "signal_event_id": fallback_signal.id,
                "pending_status": pending_status,
            },
        )

    db.commit()
    pending_total = (
        db.query(PendingSignal)
        .filter(PendingSignal.user_id == user_id, PendingSignal.status == "pending")
        .count()
    )
    return {
        "run_id": run_id,
        "mode": mode,
        "result_count": len(selected),
        "actionable_count": actionable_count,
        "queued_count": queued_count,
        "pending_total": pending_total,
        "generated_at": datetime.now(timezone.utc),
    }


def _entry_price_for_symbol(symbol: str, fallback: float = 100.0) -> float:
    ticker_payload = get_json(redis_client, f"market:ticker:{symbol.upper()}") or {}
    return float(ticker_payload.get("last_price") or ticker_payload.get("mid_price") or fallback)


def approve_pending_signal(db: Session, user_id: str, pending_signal_id: str, note: str = "") -> PendingSignal:
    row = (
        db.query(PendingSignal)
        .filter(PendingSignal.id == pending_signal_id, PendingSignal.user_id == user_id)
        .first()
    )
    if row is None:
        raise ValueError("pending_signal_not_found")
    if row.status != "pending":
        raise ValueError("pending_signal_not_actionable")

    signal = db.query(SignalEvent).filter(SignalEvent.id == row.signal_id, SignalEvent.user_id == user_id).first()
    if signal is None:
        raise ValueError("signal_event_not_found")

    entry_price = _entry_price_for_symbol(row.symbol)
    notional = 100.0
    quantity = round(max(notional / max(entry_price, 1), 0.001), 6)
    side = "long" if signal.direction == "long" else "short"
    stop_loss = round(entry_price * (0.99 if side == "long" else 1.01), 6)
    take_profit = round(entry_price * (1.02 if side == "long" else 0.98), 6)

    position = PaperPosition(
        id=str(uuid.uuid4()),
        user_id=user_id,
        bot_profile_id=signal.bot_profile_id,
        symbol=row.symbol,
        market_type=signal.market_type,
        side=side,
        quantity=quantity,
        leverage=1,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        status="open",
        unrealized_pnl=0,
        realized_pnl=0,
        opened_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(position)
    db.flush()

    db.add(
        PositionLedgerEvent(
            id=str(uuid.uuid4()),
            position_id=position.id,
            event_type="trade_open",
            payload={
                "source": "assisted_pending_signal",
                "pending_signal_id": row.id,
                "signal_id": row.signal_id,
                "symbol": row.symbol,
                "strategy_code": row.strategy_code,
            },
            created_at=datetime.now(timezone.utc),
        )
    )

    decision_note = note or "approved"
    row.status = "approved"
    row.order_position_id = position.id
    row.decided_at = datetime.now(timezone.utc)
    row.decision_note = decision_note

    record_decision_trace(
        db,
        user_id=user_id,
        trace_scope="signal",
        trace_type="user_signal_decision",
        entity_id=row.id,
        strategy_code=row.strategy_code,
        decision_status="APPROVED",
        reason_codes=["user_signal_approved"],
        feature_snapshot={
            "confidence": float(row.confidence or 0),
            "mode": row.mode,
            "decision_note": decision_note,
        },
        context_payload={
            "pending_signal_id": row.id,
            "signal_id": row.signal_id,
            "position_id": position.id,
            "symbol": row.symbol,
        },
    )
    record_decision_trace(
        db,
        user_id=user_id,
        trace_scope="trade",
        trace_type="trade_opened_from_signal",
        entity_id=position.id,
        strategy_code=row.strategy_code,
        decision_status="OPENED",
        reason_codes=["trade_opened_from_signal"],
        feature_snapshot={
            "entry_price": float(position.entry_price or 0),
            "quantity": float(position.quantity or 0),
            "side": position.side,
        },
        context_payload={
            "pending_signal_id": row.id,
            "signal_id": row.signal_id,
            "symbol": row.symbol,
        },
    )

    db.commit()
    db.refresh(row)
    return row


def reject_pending_signal(db: Session, user_id: str, pending_signal_id: str, note: str = "") -> PendingSignal:
    row = (
        db.query(PendingSignal)
        .filter(PendingSignal.id == pending_signal_id, PendingSignal.user_id == user_id)
        .first()
    )
    if row is None:
        raise ValueError("pending_signal_not_found")
    if row.status != "pending":
        raise ValueError("pending_signal_not_actionable")

    decision_note = note or "rejected"
    row.status = "rejected"
    row.decided_at = datetime.now(timezone.utc)
    row.decision_note = decision_note

    record_decision_trace(
        db,
        user_id=user_id,
        trace_scope="signal",
        trace_type="user_signal_decision",
        entity_id=row.id,
        strategy_code=row.strategy_code,
        decision_status="REJECTED",
        reason_codes=["user_signal_rejected"],
        feature_snapshot={
            "confidence": float(row.confidence or 0),
            "mode": row.mode,
            "decision_note": decision_note,
        },
        context_payload={
            "pending_signal_id": row.id,
            "signal_id": row.signal_id,
            "symbol": row.symbol,
        },
    )

    db.commit()
    db.refresh(row)
    return row