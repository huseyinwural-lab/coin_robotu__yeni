import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from db import redis_client
from models import BotProfile, PaperPosition, PositionLedgerEvent, UserExecutionIntent
from services.explainability_service import record_decision_trace
from services.execution_precheck_service import list_execution_presets, validate_execution_payload
from services.meta_strategy_engine_service import run_meta_strategy_engine
from services.portfolio_risk_service import portfolio_risk_check

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


def _extract_notional(normalized_payload: dict) -> float:
    position_value = float(normalized_payload.get("position_size_value") or 0)
    if normalized_payload.get("position_size_mode") == "fixed_notional":
        return max(position_value, 0)
    return max(position_value * 100, 0)


def preview_execution_intent(db: Session, user_id: str, payload: dict) -> tuple[UserExecutionIntent, dict]:
    validation = validate_execution_payload(payload)
    token = str(uuid.uuid4())

    normalized = validation.get("normalized_order_payload") or {}
    notional = _extract_notional(normalized)

    strategy_binding = str(normalized.get("strategy_binding") or "manual_execution")
    symbol = str(normalized.get("symbol") or "BTCUSDT")
    signal_confidence = float(payload.get("signal_confidence") or normalized.get("signal_confidence") or 0.65)

    meta_summary = run_meta_strategy_engine(
        db,
        user_id=user_id,
        strategy_id=strategy_binding,
        symbol=symbol,
        signal_confidence=signal_confidence,
        requested_notional=notional,
    )

    meta_decision = str(meta_summary.get("meta_engine_decision") or "ALLOW")
    allocation_reason = str(meta_summary.get("strategy_allocation_reason") or "normal_allocation")
    strategy_weight = float(meta_summary.get("strategy_weight") or 1.0)
    adjusted_notional = float(meta_summary.get("adjusted_notional") or notional)

    if normalized.get("position_size_mode") == "fixed_notional":
        normalized["position_size_value"] = round(adjusted_notional, 4)

    precheck_reasons = list(validation.get("reject_reason_codes") or [])
    precheck_flags = list(validation.get("risk_flags") or [])

    if meta_decision == "DISABLED":
        validation["validation_status"] = "rejected"
        precheck_reasons.append("strategy_disabled_by_meta_engine")
        adjusted_notional = 0
        if normalized.get("position_size_mode") == "fixed_notional":
            normalized["position_size_value"] = 0

    risk_impact = {
        "risk_score": 0.0,
        "risk_flags": [],
        "approval_required": True,
        "position_adjustment": {
            "applied": False,
            "requested_notional": round(adjusted_notional, 4),
            "adjusted_notional": round(adjusted_notional, 4),
            "adjustment_factor": 1.0,
        },
        "decision": "ALLOW",
        "cluster_id": "UNCLUSTERED",
        "current_portfolio_leverage": 0,
        "symbol_exposure_pct": 0,
        "cluster_exposure_pct": 0,
        "strategy_exposure_pct": 0,
        "single_trade_risk_pct": 0,
        "portfolio_state": {},
        "limits": {},
    }

    if validation.get("validation_status") == "valid" and adjusted_notional > 0:
        risk_impact = portfolio_risk_check(
            db,
            user_id=user_id,
            execution_intent={
                "symbol": symbol,
                "notional": adjusted_notional,
                "position_size": normalized.get("position_size_value"),
            },
            strategy_context={"strategy_id": strategy_binding},
            market_state={"volatility_pct": payload.get("volatility_pct", 0)},
        )

        risk_decision = str(risk_impact.get("decision") or "ALLOW")
        if risk_decision == "REJECT":
            validation["validation_status"] = "rejected"
            precheck_reasons.extend(risk_impact.get("risk_flags") or ["portfolio_risk_rejected"])
        elif risk_decision == "ADJUST_POSITION":
            position_adjustment = risk_impact.get("position_adjustment") or {}
            adjusted_from_risk = float(position_adjustment.get("adjusted_notional") or adjusted_notional)
            adjusted_notional = adjusted_from_risk
            if normalized.get("position_size_mode") == "fixed_notional":
                normalized["position_size_value"] = round(adjusted_from_risk, 4)
            precheck_flags.append("portfolio_risk_adjusted")
        elif risk_decision == "REQUIRE_APPROVAL":
            precheck_flags.append("portfolio_risk_manual_approval_required")

    final_reject_codes = sorted(set(precheck_reasons))
    final_risk_flags = sorted(set(precheck_flags + (risk_impact.get("risk_flags") or [])))
    gate_decision = str(risk_impact.get("decision") or "ALLOW")

    normalized["meta_strategy_summary"] = meta_summary
    normalized["portfolio_risk_impact"] = {
        "risk_score": risk_impact.get("risk_score"),
        "risk_flags": risk_impact.get("risk_flags") or [],
        "decision": risk_impact.get("decision"),
        "cluster_id": risk_impact.get("cluster_id"),
        "current_portfolio_leverage": risk_impact.get("current_portfolio_leverage"),
        "symbol_exposure_pct": risk_impact.get("symbol_exposure_pct"),
        "cluster_exposure_pct": risk_impact.get("cluster_exposure_pct"),
        "strategy_exposure_pct": risk_impact.get("strategy_exposure_pct"),
        "single_trade_risk_pct": risk_impact.get("single_trade_risk_pct"),
        "portfolio_state": risk_impact.get("portfolio_state") or {},
    }

    final_status = "PREVIEWED" if validation.get("validation_status") == "valid" else "REJECTED"
    intent = UserExecutionIntent(
        id=str(uuid.uuid4()),
        user_id=user_id,
        source_type=str(normalized.get("source_type") or "manual"),
        source_ref_id=str(normalized.get("source_ref_id") or "") or None,
        status=final_status,
        intent_token=token,
        preview_hash=validation.get("preview_hash"),
        queue_mode=validation.get("queue_mode", "ASSISTED"),
        approval_required=bool(risk_impact.get("approval_required", True)),
        symbol=symbol,
        market_type=str(normalized.get("market_type") or "spot"),
        side=str(normalized.get("side") or "buy"),
        notional=max(adjusted_notional, 0),
        normalized_order_payload=normalized,
        reject_reason_codes=final_reject_codes,
        risk_flags=final_risk_flags,
        risk_score=float(risk_impact.get("risk_score") or 0),
        gate_decision=gate_decision,
        meta_engine_decision=meta_decision,
        cluster_id=risk_impact.get("cluster_id"),
    )
    db.add(intent)

    preview_reason_codes = final_reject_codes or ["execution_preview_valid"]
    cluster_flag = next((item for item in final_risk_flags if "cluster" in item), None)
    record_decision_trace(
        db,
        user_id=user_id,
        trace_scope="execution",
        trace_type="execution_preview",
        entity_id=intent.id,
        strategy_code=strategy_binding,
        decision_status="VALID" if validation.get("validation_status") == "valid" else "REJECTED",
        reason_codes=preview_reason_codes,
        portfolio_risk_score=float(risk_impact.get("risk_score") or 0),
        strategy_allocation_reason=allocation_reason,
        cluster_risk_flag=cluster_flag,
        meta_engine_decision=meta_decision,
        feature_snapshot={
            "symbol": symbol,
            "market_type": str(normalized.get("market_type") or "spot"),
            "side": str(normalized.get("side") or "buy"),
            "notional": max(adjusted_notional, 0),
            "risk_flags": final_risk_flags,
            "strategy_weight": strategy_weight,
        },
        context_payload={
            "queue_mode": validation.get("queue_mode", "ASSISTED"),
            "normalized_order_payload": normalized,
            "preview_hash": validation.get("preview_hash"),
            "meta_strategy_summary": meta_summary,
            "portfolio_risk_impact": risk_impact,
        },
    )

    validation["reject_reason_codes"] = final_reject_codes
    validation["risk_flags"] = final_risk_flags
    validation["normalized_order_payload"] = normalized
    validation["meta_strategy_summary"] = meta_summary
    validation["portfolio_risk_impact"] = risk_impact
    validation["gate_decision"] = gate_decision
    validation["meta_engine_decision"] = meta_decision

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
        portfolio_risk_score=float(intent.risk_score or 0),
        strategy_allocation_reason=(intent.normalized_order_payload or {}).get("meta_strategy_summary", {}).get(
            "strategy_allocation_reason"
        ),
        cluster_risk_flag=next((item for item in (intent.risk_flags or []) if "cluster" in str(item)), None),
        meta_engine_decision=intent.meta_engine_decision,
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
        portfolio_risk_score=float(intent.risk_score or 0),
        meta_engine_decision=intent.meta_engine_decision,
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
        portfolio_risk_score=float(intent.risk_score or 0),
        strategy_allocation_reason=(intent.normalized_order_payload or {}).get("meta_strategy_summary", {}).get(
            "strategy_allocation_reason"
        ),
        cluster_risk_flag=next((item for item in (intent.risk_flags or []) if "cluster" in str(item)), None),
        meta_engine_decision=intent.meta_engine_decision,
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
        portfolio_risk_score=float(intent.risk_score or 0),
        strategy_allocation_reason=(intent.normalized_order_payload or {}).get("meta_strategy_summary", {}).get(
            "strategy_allocation_reason"
        ),
        cluster_risk_flag=next((item for item in (intent.risk_flags or []) if "cluster" in str(item)), None),
        meta_engine_decision=intent.meta_engine_decision,
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
            "strategy_weight": (intent.normalized_order_payload or {}).get("meta_strategy_summary", {}).get(
                "strategy_weight"
            ),
            "allocation_source": (intent.normalized_order_payload or {}).get("meta_strategy_summary", {}).get(
                "allocation_source"
            ),
            "meta_engine_decision": intent.meta_engine_decision,
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
        portfolio_risk_score=float(intent.risk_score or 0),
        strategy_allocation_reason=(intent.normalized_order_payload or {}).get("meta_strategy_summary", {}).get(
            "strategy_allocation_reason"
        ),
        cluster_risk_flag=next((item for item in (intent.risk_flags or []) if "cluster" in str(item)), None),
        meta_engine_decision=intent.meta_engine_decision,
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