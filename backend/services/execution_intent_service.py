import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from db import redis_client
from models import BotProfile, PaperPosition, PositionLedgerEvent, UserExecutionIntent
from services.explainability_service import record_decision_trace
from services.execution_precheck_service import list_execution_presets, validate_execution_payload

ALLOWED_SUBMIT_SOURCE_STATES = {"PREVIEWED"}


def _safe_price(symbol: str) -> float:
    payload = redis_client.get(f"market:ticker:{symbol}")
    if payload and isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    try:
        import json

        parsed = json.loads(payload) if isinstance(payload, str) else {}
        return float(parsed.get("last_price") or parsed.get("mid_price") or 100)
    except Exception:
        return 100.0


def _default_bot(db: Session, user_id: str, market_type: str) -> BotProfile:
    row = db.query(BotProfile).filter(BotProfile.user_id == user_id).order_by(BotProfile.created_at.asc()).first()
    if row:
        return row

    row = BotProfile(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name="Execution Intent Bot",
        exchange="binance",
        market_type=market_type,
        symbols=["BTCUSDT"],
        strategy_type="manual_execution",
        timeframe="15m",
        trend_timeframe="1h",
        leverage=1,
        is_enabled=True,
        is_running=False,
    )
    db.add(row)
    db.flush()
    return row


def preview_execution_intent(db: Session, user_id: str, payload: dict) -> tuple[UserExecutionIntent, dict]:
    validation = validate_execution_payload(payload)
    token = str(uuid.uuid4())

    normalized = validation.get("normalized_order_payload") or {}
    position_value = float(normalized.get("position_size_value") or 0)
    notional = position_value if normalized.get("position_size_mode") == "fixed_notional" else position_value * 100
    intent = UserExecutionIntent(
        id=str(uuid.uuid4()),
        user_id=user_id,
        source_type=str(normalized.get("source_type") or "manual"),
        source_ref_id=str(normalized.get("source_ref_id") or "") or None,
        status="PREVIEWED" if validation.get("validation_status") == "valid" else "REJECTED",
        intent_token=token,
        preview_hash=validation.get("preview_hash"),
        queue_mode=validation.get("queue_mode", "ASSISTED"),
        approval_required=True,
        symbol=str(normalized.get("symbol") or "BTCUSDT"),
        market_type=str(normalized.get("market_type") or "spot"),
        side=str(normalized.get("side") or "buy"),
        notional=max(notional, 0),
        normalized_order_payload=normalized,
        reject_reason_codes=validation.get("reject_reason_codes") or [],
        risk_flags=validation.get("risk_flags") or [],
    )
    db.add(intent)

    preview_reason_codes = validation.get("reject_reason_codes") or ["execution_preview_valid"]
    record_decision_trace(
        db,
        user_id=user_id,
        trace_scope="execution",
        trace_type="execution_preview",
        entity_id=intent.id,
        strategy_code=str(normalized.get("strategy_binding") or "") or None,
        decision_status="VALID" if validation.get("validation_status") == "valid" else "REJECTED",
        reason_codes=preview_reason_codes,
        feature_snapshot={
            "symbol": str(normalized.get("symbol") or "BTCUSDT"),
            "market_type": str(normalized.get("market_type") or "spot"),
            "side": str(normalized.get("side") or "buy"),
            "notional": max(notional, 0),
            "risk_flags": validation.get("risk_flags") or [],
        },
        context_payload={
            "queue_mode": validation.get("queue_mode", "ASSISTED"),
            "normalized_order_payload": normalized,
            "preview_hash": validation.get("preview_hash"),
        },
    )

    db.commit()
    db.refresh(intent)
    return intent, validation


def submit_execution_intent(db: Session, user_id: str, intent_token: str, preview_hash: str | None = None) -> UserExecutionIntent:
    intent = (
        db.query(UserExecutionIntent)
        .filter(UserExecutionIntent.user_id == user_id, UserExecutionIntent.intent_token == intent_token)
        .first()
    )
    if intent is None:
        raise ValueError("intent_not_found")
    if intent.status not in ALLOWED_SUBMIT_SOURCE_STATES:
        raise ValueError("preview_required")
    if preview_hash and preview_hash != intent.preview_hash:
        raise ValueError("preview_hash_mismatch")

    intent.status = "SUBMITTED"
    intent.submitted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(intent)

    intent.status = "QUEUED"
    record_decision_trace(
        db,
        user_id=user_id,
        trace_scope="execution",
        trace_type="execution_submit",
        entity_id=intent.id,
        strategy_code=(intent.normalized_order_payload or {}).get("strategy_binding") or None,
        decision_status="QUEUED_FOR_APPROVAL",
        reason_codes=["execution_intent_submitted"],
        feature_snapshot={
            "symbol": intent.symbol,
            "market_type": intent.market_type,
            "side": intent.side,
            "notional": float(intent.notional or 0),
        },
        context_payload={
            "intent_token": intent.intent_token,
            "preview_hash": intent.preview_hash,
            "queue_mode": intent.queue_mode,
        },
    )
    db.commit()
    db.refresh(intent)
    return intent


def cancel_execution_intent(db: Session, user_id: str, intent_token: str) -> UserExecutionIntent:
    intent = (
        db.query(UserExecutionIntent)
        .filter(UserExecutionIntent.user_id == user_id, UserExecutionIntent.intent_token == intent_token)
        .first()
    )
    if intent is None:
        raise ValueError("intent_not_found")
    if intent.status in {"RELEASED", "REJECTED", "CANCELLED"}:
        raise ValueError("intent_not_cancellable")

    intent.status = "CANCELLED"
    intent.cancelled_at = datetime.now(timezone.utc)
    record_decision_trace(
        db,
        user_id=user_id,
        trace_scope="execution",
        trace_type="execution_cancel",
        entity_id=intent.id,
        strategy_code=(intent.normalized_order_payload or {}).get("strategy_binding") or None,
        decision_status="CANCELLED",
        reason_codes=["execution_intent_cancelled"],
        feature_snapshot={
            "symbol": intent.symbol,
            "market_type": intent.market_type,
            "side": intent.side,
            "notional": float(intent.notional or 0),
        },
        context_payload={"intent_token": intent.intent_token},
    )
    db.commit()
    db.refresh(intent)
    return intent


def approve_execution_intent(db: Session, intent_id: str, admin_user_id: str, admin_note: str = "") -> UserExecutionIntent:
    intent = db.query(UserExecutionIntent).filter(UserExecutionIntent.id == intent_id).first()
    if intent is None:
        raise ValueError("intent_not_found")
    if intent.status != "QUEUED":
        raise ValueError("intent_not_in_queue")

    intent.status = "APPROVED"
    intent.admin_user_id = admin_user_id
    intent.admin_note = admin_note
    intent.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(intent)

    normalized = intent.normalized_order_payload or {}
    bot = _default_bot(db, intent.user_id, str(normalized.get("market_type") or "spot"))
    symbol = str(normalized.get("symbol") or intent.symbol or "BTCUSDT")
    entry_price = _safe_price(symbol)
    quantity = round(max(float(intent.notional or 0) / max(entry_price, 1), 0.001), 6)
    side = str(normalized.get("side") or "buy").lower()
    position_side = "long" if side in {"buy", "long"} else "short"

    position = PaperPosition(
        id=str(uuid.uuid4()),
        user_id=intent.user_id,
        bot_profile_id=bot.id,
        symbol=symbol,
        market_type=str(normalized.get("market_type") or "spot"),
        side=position_side,
        quantity=quantity,
        leverage=int(normalized.get("leverage") or 1),
        entry_price=entry_price,
        stop_loss=round(entry_price * 0.99, 6),
        take_profit=round(entry_price * 1.02, 6),
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
            event_type="execution_order_released",
            payload={"intent_id": intent.id, "intent_token": intent.intent_token, "symbol": symbol},
            created_at=datetime.now(timezone.utc),
        )
    )

    intent.status = "RELEASED"
    intent.released_at = datetime.now(timezone.utc)

    strategy_code = str(normalized.get("strategy_binding") or "") or None
    record_decision_trace(
        db,
        user_id=intent.user_id,
        trace_scope="execution",
        trace_type="execution_admin_approval",
        entity_id=intent.id,
        strategy_code=strategy_code,
        decision_status="RELEASED",
        reason_codes=["execution_intent_released"],
        feature_snapshot={
            "symbol": symbol,
            "market_type": str(normalized.get("market_type") or "spot"),
            "side": position_side,
            "quantity": float(quantity),
        },
        context_payload={
            "admin_user_id": admin_user_id,
            "admin_note": admin_note,
            "intent_token": intent.intent_token,
        },
    )
    record_decision_trace(
        db,
        user_id=intent.user_id,
        trace_scope="trade",
        trace_type="trade_opened_from_execution",
        entity_id=position.id,
        strategy_code=strategy_code,
        decision_status="OPENED",
        reason_codes=["trade_opened_from_execution"],
        feature_snapshot={
            "entry_price": float(position.entry_price or 0),
            "quantity": float(position.quantity or 0),
            "side": position.side,
            "leverage": int(position.leverage or 1),
        },
        context_payload={
            "intent_id": intent.id,
            "intent_token": intent.intent_token,
            "symbol": symbol,
        },
    )

    db.commit()
    db.refresh(intent)
    return intent


def reject_execution_intent(db: Session, intent_id: str, admin_user_id: str, admin_note: str = "") -> UserExecutionIntent:
    intent = db.query(UserExecutionIntent).filter(UserExecutionIntent.id == intent_id).first()
    if intent is None:
        raise ValueError("intent_not_found")
    if intent.status not in {"QUEUED", "SUBMITTED", "PREVIEWED"}:
        raise ValueError("intent_not_rejectable")

    intent.status = "REJECTED"
    intent.admin_user_id = admin_user_id
    intent.admin_note = admin_note
    record_decision_trace(
        db,
        user_id=intent.user_id,
        trace_scope="execution",
        trace_type="execution_admin_rejection",
        entity_id=intent.id,
        strategy_code=(intent.normalized_order_payload or {}).get("strategy_binding") or None,
        decision_status="REJECTED",
        reason_codes=(intent.reject_reason_codes or ["execution_intent_rejected"]),
        feature_snapshot={
            "symbol": intent.symbol,
            "market_type": intent.market_type,
            "side": intent.side,
            "notional": float(intent.notional or 0),
        },
        context_payload={
            "admin_user_id": admin_user_id,
            "admin_note": admin_note,
            "intent_token": intent.intent_token,
        },
    )
    db.commit()
    db.refresh(intent)
    return intent


def list_execution_queue(db: Session, *, status_filter: str = "QUEUED", limit: int = 100) -> list[UserExecutionIntent]:
    query = db.query(UserExecutionIntent)
    if status_filter != "all":
        query = query.filter(UserExecutionIntent.status == status_filter)
    return query.order_by(UserExecutionIntent.created_at.desc()).limit(limit).all()


def list_user_execution_intents(db: Session, user_id: str, limit: int = 50) -> list[UserExecutionIntent]:
    return (
        db.query(UserExecutionIntent)
        .filter(UserExecutionIntent.user_id == user_id)
        .order_by(UserExecutionIntent.created_at.desc())
        .limit(limit)
        .all()
    )


def get_execution_presets() -> list[dict]:
    return list_execution_presets()