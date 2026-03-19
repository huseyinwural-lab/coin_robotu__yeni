import uuid
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from db import redis_client
from models import BotProfile, PaperPosition, Position, PositionLedgerEvent, UserExecutionIntent
from core.policy.quote_policy import InvalidSymbol, extract_quote, normalize_symbol
from services.explainability_service import record_decision_trace
from services.execution_precheck_service import list_execution_presets, validate_execution_payload
from services.execution_readiness_service import enforce_execution_guard_or_raise, validate_order_precheck
from services.execution_safety_service import enforce_execution_open_allowed_or_raise
from services.meta_strategy_engine_service import run_meta_strategy_engine
from services.portfolio_risk_service import portfolio_risk_check
from services.position_management_service import sync_position_state
from services.risk_engine_service import evaluate_risk_decision, resolve_effective_config_for_user
from services.strategy_intelligence_service import (
    evaluate_capital_rebalance,
    evaluate_conflict_warning,
    evaluate_hedge_suggestion,
)
from services.universe_service import resolve_symbol_market_type
from services.venue_service import check_user_venue_access, seed_binance_venue_registry

ALLOWED_SUBMIT_SOURCE_STATES = {"PREVIEWED"}
POSITION_ACTION_TYPES = {
    "CLOSE_POSITION",
    "PARTIAL_CLOSE",
    "REVERSE_POSITION",
    "MOVE_STOP",
    "MOVE_TAKE_PROFIT",
}
RISK_REDUCTION_ACTIONS = {"CLOSE_POSITION", "PARTIAL_CLOSE", "MOVE_STOP", "MOVE_TAKE_PROFIT"}


def _recommended_futures_leverage(*, user_id: str, volatility_pct: float) -> int:
    config = resolve_effective_config_for_user(redis_client, user_id=user_id)
    max_leverage = max(1, min(int(config.get("max_leverage") or 5), 20))
    if volatility_pct >= 0.035:
        return min(2, max_leverage)
    if volatility_pct >= 0.02:
        return min(3, max_leverage)
    return min(5, max_leverage)


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


def _safe_spread_bps(symbol: str) -> float:
    payload = redis_client.get(f"market:spread:{symbol}")
    if payload and isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    try:
        import json

        parsed = json.loads(payload) if isinstance(payload, str) else {}
        return float(parsed.get("spread_bps") or 0.0)
    except Exception:
        return 0.0


def _default_bot(db: Session, user_id: str, market_type: str, symbol: str | None = None) -> BotProfile:
    row = (
        db.query(BotProfile)
        .filter(BotProfile.user_id == user_id, BotProfile.is_deleted.is_(False))
        .order_by(BotProfile.created_at.asc())
        .first()
    )
    if row:
        return row

    row = BotProfile(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name="Execution Intent Bot",
        exchange="binance",
        market_type=market_type,
        symbols=[str(symbol or "").upper()] if str(symbol or "").strip() else [],
        strategy_type="manual_execution",
        timeframe="15m",
        trend_timeframe="1h",
        leverage=3 if str(market_type or "spot").lower() == "futures" else 1,
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


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _side_to_direction(side: str) -> str:
    side_lower = str(side or "buy").lower()
    if side_lower in {"sell", "short"}:
        return "sell"
    return "buy"


def _extract_hedge_context(normalized_payload: dict) -> tuple[str | None, float | None, str | None]:
    hedge = (normalized_payload or {}).get("hedge_suggestion") or {}
    hedge_symbol = hedge.get("hedge_symbol")
    if not hedge_symbol:
        return None, None, None
    recommendation = f"{hedge_symbol}:{hedge.get('hedge_direction')}:{hedge.get('hedge_size')}"
    return recommendation, float(hedge.get("risk_reduction_score") or 0), hedge.get("correlation_basis")


def _resolve_position_for_action(db: Session, user_id: str, position_id: str) -> PaperPosition:
    row = (
        db.query(PaperPosition)
        .filter(PaperPosition.id == position_id, PaperPosition.user_id == user_id, PaperPosition.status == "open")
        .first()
    )
    if row is None:
        raise ValueError("position_not_found")
    return row


def _build_position_action_preview_payload(db: Session, user_id: str, payload: dict) -> tuple[dict, dict, float, str, float, bool, float | None, float | None, float | None]:
    intent_type = str(payload.get("intent_type") or "").upper()
    if intent_type not in POSITION_ACTION_TYPES:
        raise ValueError("unsupported_intent_type")

    position_id = str(payload.get("position_id") or "").strip()
    if not position_id:
        raise ValueError("position_id_required")

    position = _resolve_position_for_action(db, user_id, position_id)
    position_state = db.query(Position).filter(Position.position_id == position.id).first()
    strategy_binding = str(
        payload.get("strategy_binding")
        or (position_state.strategy_id if position_state and position_state.strategy_id else "manual_execution")
    )

    market_price = _safe_price(position.symbol)
    requested_size = _to_float(payload.get("size"), 0)
    if requested_size <= 0:
        requested_size = float(position.quantity or 0)
    if intent_type == "CLOSE_POSITION":
        requested_size = float(position.quantity or 0)
    if intent_type == "PARTIAL_CLOSE":
        requested_size = min(requested_size, float(position.quantity or 0))
    if intent_type == "REVERSE_POSITION" and requested_size <= 0:
        requested_size = float(position.quantity or 0)

    reduce_only = bool(payload.get("reduce_only", intent_type in {"CLOSE_POSITION", "PARTIAL_CLOSE"}))
    price = _to_float(payload.get("price"), market_price) if payload.get("price") is not None else None
    stop_price = _to_float(payload.get("stop_price"), 0) if payload.get("stop_price") is not None else None
    take_profit_price = (
        _to_float(payload.get("take_profit_price"), 0) if payload.get("take_profit_price") is not None else None
    )

    reasons: list[str] = []
    validation_status = "valid"
    if requested_size <= 0:
        validation_status = "rejected"
        reasons.append("position_action_size_invalid")
    if intent_type == "MOVE_STOP" and stop_price is None:
        validation_status = "rejected"
        reasons.append("stop_price_required")
    if intent_type == "MOVE_TAKE_PROFIT" and take_profit_price is None:
        validation_status = "rejected"
        reasons.append("take_profit_price_required")

    action_side = "sell" if position.side == "long" else "buy"
    if intent_type == "REVERSE_POSITION":
        action_side = "sell" if position.side == "long" else "buy"

    notional = max(requested_size * market_price, 0)
    normalized = {
        "source_type": "position_action",
        "source_ref_id": position.id,
        "intent_type": intent_type,
        "position_id": position.id,
        "market_type": position.market_type,
        "symbol": position.symbol,
        "side": action_side,
        "order_type": "market",
        "position_size_mode": "fixed_notional",
        "position_size_value": round(notional, 6),
        "execution_mode": "position_action",
        "strategy_binding": strategy_binding,
        "size": round(requested_size, 6),
        "reduce_only": reduce_only,
        "price": price,
        "stop_price": stop_price,
        "take_profit_price": take_profit_price,
    }

    validation = {
        "preview_hash": str(uuid.uuid4()),
        "validation_status": validation_status,
        "reject_reason_codes": reasons,
        "risk_flags": [],
        "queue_mode": "ASSISTED",
        "normalized_order_payload": normalized,
    }

    return (
        validation,
        normalized,
        notional,
        strategy_binding,
        requested_size,
        reduce_only,
        price,
        stop_price,
        take_profit_price,
    )


def preview_execution_intent(db: Session, user_id: str, payload: dict) -> tuple[UserExecutionIntent, dict]:
    intent_type = str(payload.get("intent_type") or "OPEN_POSITION").upper()
    token = str(uuid.uuid4())

    if intent_type == "OPEN_POSITION":
        validation = validate_execution_payload(payload)
        normalized = validation.get("normalized_order_payload") or {}
        notional = _extract_notional(normalized)
        action_size = _to_float(payload.get("size"), 0)
        reduce_only = bool(payload.get("reduce_only", False))
        price = _to_float(payload.get("price"), 0) if payload.get("price") is not None else None
        stop_price = _to_float(payload.get("stop_price"), 0) if payload.get("stop_price") is not None else None
        take_profit_price = (
            _to_float(payload.get("take_profit_price"), 0) if payload.get("take_profit_price") is not None else None
        )
    else:
        (
            validation,
            normalized,
            notional,
            strategy_binding_from_action,
            action_size,
            reduce_only,
            price,
            stop_price,
            take_profit_price,
        ) = _build_position_action_preview_payload(db, user_id, payload)
        normalized.setdefault("strategy_binding", strategy_binding_from_action)

    strategy_binding = str(normalized.get("strategy_binding") or "manual_execution")
    source_type = str(normalized.get("source_type") or payload.get("source_type") or "manual").strip().lower()
    try:
        symbol = normalize_symbol(
        normalized.get("symbol") or payload.get("symbol"),
        missing_error_code="symbol_required_for_execution_intent",
        invalid_error_code="invalid_quote_asset",
        )
    except InvalidSymbol as exc:
        raise ValueError(str(exc)) from exc
    normalized["symbol"] = symbol
    normalized["quote_asset"] = extract_quote(symbol)

    scanner_snapshot = normalized.get("scanner_signal_snapshot") or payload.get("scanner_signal_snapshot") or {}
    if scanner_snapshot:
        normalized["scanner_signal_snapshot"] = scanner_snapshot
    if source_type == "scanner" or bool(payload.get("signal_bridge_context")):
        scan_symbol = str((scanner_snapshot or {}).get("symbol") or "").strip().upper()
        if not scan_symbol:
            raise ValueError("scanner_signal_snapshot_missing_symbol")
        if scan_symbol != symbol:
            raise ValueError("scanner_execution_symbol_mismatch")
    signal_confidence = float(payload.get("signal_confidence") or normalized.get("signal_confidence") or 0.65)

    requested_exchange = str(payload.get("exchange") or normalized.get("exchange") or "binance").strip().lower()
    requested_market_type = str(normalized.get("market_type") or payload.get("market_type") or "spot").strip().lower()
    requested_environment = str(payload.get("environment") or normalized.get("environment") or "testnet").strip().lower()
    exchange_connection_id = str(payload.get("exchange_connection_id") or "").strip() or None
    account_label = str(payload.get("account_label") or normalized.get("account_label") or "default").strip()

    seed_binance_venue_registry(db)
    venue_allowed, venue_state, capability_match, venue_reason_codes = check_user_venue_access(
        db,
        user_id,
        requested_exchange,
        requested_market_type,
        requested_environment,
    )
    venue_context = {
        "exchange": requested_exchange,
        "market_type": requested_market_type,
        "environment": requested_environment,
        "account_label": account_label,
        "exchange_connection_id": exchange_connection_id,
        "allowed": venue_allowed,
        "venue_state": venue_state,
        "capability_match": capability_match,
        "reason_codes": venue_reason_codes,
    }
    normalized["exchange"] = requested_exchange
    normalized["environment"] = requested_environment
    normalized["account_label"] = account_label
    normalized["exchange_connection_id"] = exchange_connection_id
    normalized["venue_context"] = venue_context

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
    strategy_override_reason = None

    if normalized.get("position_size_mode") == "fixed_notional":
        normalized["position_size_value"] = round(adjusted_notional, 4)

    precheck_reasons = list(validation.get("reject_reason_codes") or [])
    precheck_flags = list(validation.get("risk_flags") or [])

    if meta_decision == "DISABLED":
        if intent_type in RISK_REDUCTION_ACTIONS:
            meta_decision = "ALLOW"
            strategy_override_reason = "strategy_disabled_but_risk_reduction_action_allowed"
            precheck_flags.append("strategy_override_for_risk_reduction")
        else:
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

    risk_adjustment_reason = None
    leverage_requested = int(normalized.get("leverage") or payload.get("leverage") or 1)
    leverage_requested = max(1, min(leverage_requested, 20))
    leverage_recommended = _recommended_futures_leverage(
        user_id=user_id,
        volatility_pct=float(payload.get("volatility_pct") or 0),
    )
    leverage_applied = leverage_requested
    leverage_clamp_reasons: list[str] = []
    risk_engine_result = {
        "risk_decision": "ALLOW",
        "reason_codes": [],
        "warnings": [],
        "size_multiplier": 1.0,
        "adjusted_notional_usdt": float(adjusted_notional),
        "adjusted_leverage": leverage_requested,
        "metrics": {},
    }
    if validation.get("validation_status") == "valid" and adjusted_notional >= 0:
        risk_impact = portfolio_risk_check(
            db,
            user_id=user_id,
            execution_intent={
                "symbol": symbol,
                "notional": adjusted_notional,
                "position_size": normalized.get("size") or normalized.get("position_size_value"),
            },
            strategy_context={"strategy_id": strategy_binding},
            market_state={"volatility_pct": payload.get("volatility_pct", 0)},
        )

        risk_decision = str(risk_impact.get("decision") or "ALLOW")
        if risk_decision == "REJECT":
            if intent_type in RISK_REDUCTION_ACTIONS:
                risk_adjustment_reason = "risk_gate_override_for_risk_reduction"
                precheck_flags.append("risk_gate_override_for_risk_reduction")
                risk_impact["decision"] = "ALLOW"
            else:
                validation["validation_status"] = "rejected"
                precheck_reasons.extend(risk_impact.get("risk_flags") or ["portfolio_risk_rejected"])
        elif risk_decision == "ADJUST_POSITION":
            position_adjustment = risk_impact.get("position_adjustment") or {}
            adjusted_from_risk = float(position_adjustment.get("adjusted_notional") or adjusted_notional)
            adjusted_notional = adjusted_from_risk
            if normalized.get("position_size_mode") == "fixed_notional":
                normalized["position_size_value"] = round(adjusted_from_risk, 4)
            if notional > 0:
                ratio = max(min(adjusted_from_risk / max(notional, 1e-6), 1.0), 0.0)
                if normalized.get("size") is not None:
                    normalized["size"] = round(float(normalized.get("size") or 0) * ratio, 6)
            precheck_flags.append("portfolio_risk_adjusted")
            risk_adjustment_reason = "position_size_adjusted_by_portfolio_risk"
        elif risk_decision == "REQUIRE_APPROVAL":
            precheck_flags.append("portfolio_risk_manual_approval_required")

        direction = _side_to_direction(normalized.get("side") or payload.get("side") or "buy")
        strategy_decision = "SHORT" if direction == "sell" else "LONG"
        risk_engine_result = evaluate_risk_decision(
            db,
            redis_client,
            user_id=user_id,
            symbol=symbol,
            strategy_decision=strategy_decision,
            market_type=str(normalized.get("market_type") or payload.get("market_type") or "spot"),
            proposed_notional_usdt=float(adjusted_notional or 0),
            strategy_code=strategy_binding,
            requested_leverage=int(normalized.get("leverage") or payload.get("leverage") or 1),
            snapshot_age_ms=float((payload.get("signal_bridge_context") or {}).get("snapshot_age_ms") or 0),
            spread_bps=_safe_spread_bps(symbol),
            execution_latency_ms=float((payload.get("signal_bridge_context") or {}).get("execution_latency_ms") or 0),
            slippage_pct=float((payload.get("signal_bridge_context") or {}).get("slippage_pct") or 0),
            orderbook_depth_score=float((payload.get("signal_bridge_context") or {}).get("orderbook_depth_score") or 1.0),
            liquidation_distance_pct=float(payload.get("liquidation_distance_pct") or 999.0),
        )
        risk_engine_decision = str(risk_engine_result.get("risk_decision") or "ALLOW")

        if risk_engine_decision in {"PASS", "BLOCK"}:
            if intent_type in RISK_REDUCTION_ACTIONS:
                precheck_flags.append("risk_engine_override_for_risk_reduction")
                risk_engine_result["risk_decision"] = "ALLOW"
            else:
                validation["validation_status"] = "rejected"
                precheck_reasons.extend(risk_engine_result.get("reason_codes") or ["risk_engine_veto"])
        elif risk_engine_decision == "REDUCE_SIZE":
            adjusted_notional = float(risk_engine_result.get("adjusted_notional_usdt") or adjusted_notional)
            if normalized.get("position_size_mode") == "fixed_notional":
                normalized["position_size_value"] = round(adjusted_notional, 4)
            if normalized.get("size") is not None and notional > 0:
                ratio = max(min(adjusted_notional / max(notional, 1e-6), 1.0), 0.0)
                normalized["size"] = round(float(normalized.get("size") or 0) * ratio, 6)
            precheck_flags.append("risk_engine_reduce_size")

        precheck_flags.extend(risk_engine_result.get("warnings") or [])

    if str(normalized.get("market_type") or payload.get("market_type") or "spot").lower() == "futures":
        leverage_applied = int(risk_engine_result.get("adjusted_leverage") or leverage_requested)
        leverage_applied = max(1, min(leverage_applied, 20))
        if leverage_applied < leverage_requested:
            leverage_clamp_reasons.append("risk_policy_leverage_cap")
        if "leverage_capped" in (risk_engine_result.get("warnings") or []):
            leverage_clamp_reasons.append("risk_engine_leverage_capped")
        normalized["leverage"] = leverage_applied
    else:
        leverage_requested = None
        leverage_recommended = None
        leverage_applied = None

    normalized["leverage_requested"] = leverage_requested
    normalized["leverage_recommended"] = leverage_recommended
    normalized["leverage_applied"] = leverage_applied
    normalized["leverage_policy_mode"] = "hybrid_user_override" if leverage_requested is not None else None
    normalized["leverage_clamp_reasons"] = sorted(set(leverage_clamp_reasons))

    if intent_type == "OPEN_POSITION" and requested_environment == "live" and not venue_allowed:
        validation["validation_status"] = "rejected"
        precheck_reasons.append("venue_access_blocked")
        if venue_state:
            precheck_flags.append(f"venue_state:{venue_state}")
        precheck_reasons.extend(venue_reason_codes or [])

    conflict_result = evaluate_conflict_warning(
        db,
        user_id=user_id,
        strategy_id=strategy_binding,
        symbol=symbol,
        signal_direction=_side_to_direction(normalized.get("side") or payload.get("side") or "buy"),
        confidence_score=signal_confidence,
    )
    if (
        intent_type == "OPEN_POSITION"
        and bool(conflict_result.get("conflict_detected"))
        and str(conflict_result.get("winning_strategy") or "")
        and str(conflict_result.get("winning_strategy")) != strategy_binding
    ):
        validation["validation_status"] = "rejected"
        precheck_reasons.append("strategy_conflict_loser")

    rebalance_result = evaluate_capital_rebalance(db, user_id=user_id, apply_changes=False)
    strategy_rebalance_event = next(
        (
            event
            for event in (rebalance_result.get("events") or [])
            if str(event.get("strategy_id") or "") == strategy_binding
        ),
        None,
    )
    if strategy_rebalance_event and bool(strategy_rebalance_event.get("throttle_signal")) and adjusted_notional > 0:
        adjusted_notional = round(adjusted_notional * 0.75, 6)
        if normalized.get("position_size_mode") == "fixed_notional":
            normalized["position_size_value"] = adjusted_notional
        if normalized.get("size") is not None and notional > 0:
            normalized["size"] = round(float(normalized.get("size") or 0) * 0.75, 6)
        precheck_flags.append("allocation_rebalanced")
        if not risk_adjustment_reason:
            risk_adjustment_reason = "allocation_rebalance_adjustment"

    hedge_suggestion = evaluate_hedge_suggestion(
        db,
        user_id=user_id,
        volatility=float(payload.get("volatility_pct") or 0),
    )
    if hedge_suggestion.get("hedge_symbol"):
        precheck_flags.append("hedge_suggestion_generated")

    final_reject_codes = sorted(set(precheck_reasons))
    final_risk_flags = sorted(
        set(
            [
                *precheck_flags,
                *(risk_impact.get("risk_flags") or []),
                *(risk_engine_result.get("reason_codes") or []),
            ]
        )
    )
    gate_decision = str(risk_engine_result.get("risk_decision") or risk_impact.get("decision") or "ALLOW")

    if bool(payload.get("signal_bridge_context")) and requested_environment == "testnet":
        soft_override_codes = {"strategy_conflict_loser", "symbol_not_allowed", "assignment_required", "venue_access_blocked"}
        hard_codes = [code for code in final_reject_codes if code not in soft_override_codes]
        if not hard_codes:
            validation["validation_status"] = "valid"
            final_reject_codes = []
            final_risk_flags = sorted(set([*final_risk_flags, "testnet_signal_bridge_soft_override"]))

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
    normalized["strategy_conflict"] = conflict_result
    normalized["capital_rebalance"] = rebalance_result
    normalized["hedge_suggestion"] = hedge_suggestion
    normalized["risk_engine"] = risk_engine_result

    if normalized.get("size") is not None:
        action_size = _to_float(normalized.get("size"), action_size)
    else:
        action_size = action_size or 0

    final_status = "PREVIEWED" if validation.get("validation_status") == "valid" else "REJECTED"
    intent = UserExecutionIntent(
        id=str(uuid.uuid4()),
        user_id=user_id,
        source_type=source_type,
        source_ref_id=str(normalized.get("source_ref_id") or payload.get("source_ref_id") or "") or None,
        intent_type=intent_type,
        position_id=str(normalized.get("position_id") or payload.get("position_id") or "") or None,
        status=final_status,
        intent_token=token,
        preview_hash=validation.get("preview_hash"),
        queue_mode=validation.get("queue_mode", "ASSISTED"),
        approval_required=bool(risk_impact.get("approval_required", True)),
        symbol=symbol,
        market_type=str(normalized.get("market_type") or payload.get("market_type") or "spot"),
        side=str(normalized.get("side") or payload.get("side") or "buy"),
        notional=max(adjusted_notional, 0),
        size=max(action_size, 0),
        reduce_only=bool(normalized.get("reduce_only", reduce_only)),
        price=_to_float(normalized.get("price"), 0) if normalized.get("price") is not None else price,
        stop_price=_to_float(normalized.get("stop_price"), 0) if normalized.get("stop_price") is not None else stop_price,
        take_profit_price=(
            _to_float(normalized.get("take_profit_price"), 0)
            if normalized.get("take_profit_price") is not None
            else take_profit_price
        ),
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
    position_action_reason = intent_type if intent_type in POSITION_ACTION_TYPES else None
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
        position_action_reason=position_action_reason,
        risk_adjustment_reason=risk_adjustment_reason,
        strategy_override_reason=strategy_override_reason,
        feature_snapshot={
            "symbol": symbol,
            "market_type": str(normalized.get("market_type") or "spot"),
            "side": str(normalized.get("side") or "buy"),
            "notional": max(adjusted_notional, 0),
            "size": max(action_size, 0),
            "risk_flags": final_risk_flags,
            "strategy_weight": strategy_weight,
        },
        context_payload={
            "intent_type": intent_type,
            "position_id": intent.position_id,
            "queue_mode": validation.get("queue_mode", "ASSISTED"),
            "normalized_order_payload": normalized,
            "preview_hash": validation.get("preview_hash"),
            "meta_strategy_summary": meta_summary,
            "portfolio_risk_impact": risk_impact,
            "strategy_conflict": conflict_result,
            "capital_rebalance": rebalance_result,
            "hedge_suggestion": hedge_suggestion,
        },
        hedge_recommendation=(
            f"{hedge_suggestion.get('hedge_symbol')}:{hedge_suggestion.get('hedge_direction')}:{hedge_suggestion.get('hedge_size')}"
            if hedge_suggestion.get("hedge_symbol")
            else None
        ),
        risk_reduction_score=float(hedge_suggestion.get("risk_reduction_score") or 0),
        correlation_basis=hedge_suggestion.get("correlation_basis"),
    )

    validation["reject_reason_codes"] = final_reject_codes
    validation["risk_flags"] = final_risk_flags
    validation["normalized_order_payload"] = normalized
    validation["meta_strategy_summary"] = meta_summary
    validation["portfolio_risk_impact"] = risk_impact
    validation["risk_engine"] = risk_engine_result
    validation["gate_decision"] = gate_decision
    validation["meta_engine_decision"] = meta_decision
    validation["intent_type"] = intent_type
    validation["position_id"] = intent.position_id
    validation["size"] = intent.size
    validation["reduce_only"] = intent.reduce_only
    validation["price"] = intent.price
    validation["stop_price"] = intent.stop_price
    validation["take_profit_price"] = intent.take_profit_price
    validation["strategy_conflict_warning"] = conflict_result.get("strategy_conflict_warning")
    validation["allocation_adjustment_notice"] = rebalance_result.get("allocation_adjustment_notice")
    validation["hedge_suggestion"] = hedge_suggestion
    validation["risk_reduction_score"] = float(hedge_suggestion.get("risk_reduction_score") or 0)
    validation["venue_context"] = venue_context
    validation["requested_leverage"] = normalized.get("leverage_requested")
    validation["recommended_leverage"] = normalized.get("leverage_recommended")
    validation["applied_leverage"] = normalized.get("leverage_applied")
    validation["leverage_policy_mode"] = normalized.get("leverage_policy_mode")
    validation["leverage_clamp_reasons"] = normalized.get("leverage_clamp_reasons") or []

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

    if intent.intent_type == "OPEN_POSITION":
        enforce_execution_guard_or_raise(
            db,
            user_id=user_id,
            actor_user_id=user_id,
            actor_role="USER",
            source="execution_intent_service_submit",
        )
        enforce_execution_open_allowed_or_raise(
            db,
            proposed_notional=float(intent.notional or 0.0),
            source="execution_intent_service_submit",
            actor_user_id=user_id,
            actor_role="USER",
            entity_type="user_execution_intent",
            entity_id=intent.id,
        )

        precheck_price = float(intent.price or 0)
        precheck_size = float(intent.size or 0)
        precheck_notional = float(intent.notional or 0)
        if precheck_price <= 0 and precheck_notional > 0 and precheck_size > 0:
            precheck_price = precheck_notional / precheck_size

        precheck = validate_order_precheck(
            db,
            user_id=user_id,
            symbol=str(intent.symbol or "").upper(),
            market_type=str(intent.market_type or "spot"),
            order_type=str((intent.normalized_order_payload or {}).get("order_type") or "market"),
            side=str(intent.side or "buy"),
            price=precheck_price,
            size=precheck_size,
            leverage=int((intent.normalized_order_payload or {}).get("leverage") or 1),
            margin_mode=str((intent.normalized_order_payload or {}).get("margin_mode") or "isolated"),
        )
        if not precheck.get("valid"):
            raise ValueError("order_validation_failed")

    intent.status = "SUBMITTED"
    intent.submitted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(intent)

    intent.status = "QUEUED"
    position_action_reason = intent.intent_type if intent.intent_type in POSITION_ACTION_TYPES else None
    rebalance_apply_result = evaluate_capital_rebalance(db, user_id=user_id, apply_changes=True)
    hedge_recommendation, hedge_risk_reduction, correlation_basis = _extract_hedge_context(intent.normalized_order_payload or {})
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
        position_action_reason=position_action_reason,
        risk_adjustment_reason=(
            "position_size_adjusted_by_portfolio_risk" if "portfolio_risk_adjusted" in (intent.risk_flags or []) else None
        ),
        hedge_recommendation=hedge_recommendation,
        risk_reduction_score=hedge_risk_reduction,
        correlation_basis=correlation_basis,
        feature_snapshot={
            "symbol": intent.symbol,
            "market_type": intent.market_type,
            "side": intent.side,
            "notional": float(intent.notional or 0),
            "size": float(intent.size or 0),
        },
        context_payload={
            "intent_type": intent.intent_type,
            "position_id": intent.position_id,
            "intent_token": intent.intent_token,
            "preview_hash": intent.preview_hash,
            "queue_mode": intent.queue_mode,
            "capital_rebalance": rebalance_apply_result,
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
    hedge_recommendation, hedge_risk_reduction, correlation_basis = _extract_hedge_context(intent.normalized_order_payload or {})
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
        position_action_reason=intent.intent_type if intent.intent_type in POSITION_ACTION_TYPES else None,
        hedge_recommendation=hedge_recommendation,
        risk_reduction_score=hedge_risk_reduction,
        correlation_basis=correlation_basis,
        feature_snapshot={
            "symbol": intent.symbol,
            "market_type": intent.market_type,
            "side": intent.side,
            "notional": float(intent.notional or 0),
            "size": float(intent.size or 0),
        },
        context_payload={"intent_type": intent.intent_type, "position_id": intent.position_id, "intent_token": intent.intent_token},
    )
    db.commit()
    db.refresh(intent)
    return intent


def _calc_realized_pnl(position: PaperPosition, exit_price: float, quantity: float) -> float:
    side_multiplier = 1 if position.side == "long" else -1
    return round((exit_price - float(position.entry_price or 0)) * quantity * side_multiplier * max(int(position.leverage or 1), 1), 6)


def _open_position_from_intent(db: Session, intent: UserExecutionIntent, normalized: dict) -> PaperPosition:
    try:
        symbol = normalize_symbol(
        normalized.get("symbol") or intent.symbol,
        missing_error_code="symbol_required_for_execution_order",
        invalid_error_code="invalid_quote_asset",
        )
    except InvalidSymbol as exc:
        raise ValueError(str(exc)) from exc
    requested_market_type = str(normalized.get("market_type") or "").strip().lower()
    market_type = requested_market_type if requested_market_type in {"spot", "futures"} else resolve_symbol_market_type(db, redis_client, symbol)
    bot = _default_bot(db, intent.user_id, market_type, symbol=symbol)
    entry_price = _safe_price(symbol)
    quantity = round(max(float(intent.notional or 0) / max(entry_price, 1), 0.001), 6)
    side = str(normalized.get("side") or "buy").lower()
    position_side = "long" if side in {"buy", "long"} else "short"
    leverage_default = 3 if market_type == "futures" else 1

    position = PaperPosition(
        id=str(uuid.uuid4()),
        user_id=intent.user_id,
        bot_profile_id=bot.id,
        symbol=symbol,
        market_type=market_type,
        side=position_side,
        quantity=quantity,
        leverage=int(normalized.get("leverage") or leverage_default),
        entry_price=entry_price,
        stop_loss=float(intent.stop_price) if intent.stop_price is not None else round(entry_price * 0.99, 6),
        take_profit=float(intent.take_profit_price)
        if intent.take_profit_price is not None
        else round(entry_price * 1.02, 6),
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
    sync_position_state(
        db,
        paper_position=position,
        strategy_id=(intent.normalized_order_payload or {}).get("strategy_binding"),
        cluster_id=intent.cluster_id,
    )
    return position


def _apply_position_action_intent(db: Session, intent: UserExecutionIntent) -> tuple[PaperPosition, str, str]:
    if not intent.position_id:
        raise ValueError("position_id_required")

    position = (
        db.query(PaperPosition)
        .filter(PaperPosition.id == intent.position_id, PaperPosition.user_id == intent.user_id, PaperPosition.status == "open")
        .first()
    )
    if position is None:
        raise ValueError("position_not_found")

    action = intent.intent_type
    event_type = "position_action"
    position_action_reason = action
    now = datetime.now(timezone.utc)

    if action == "CLOSE_POSITION":
        exit_price = float(intent.price) if intent.price is not None else _safe_price(position.symbol)
        close_qty = float(position.quantity or 0)
        pnl_delta = _calc_realized_pnl(position, exit_price, close_qty)
        position.realized_pnl = float(position.realized_pnl or 0) + pnl_delta
        position.unrealized_pnl = 0
        position.quantity = 0
        position.status = "closed"
        position.closed_at = now
        event_type = "position_closed"
    elif action == "PARTIAL_CLOSE":
        exit_price = float(intent.price) if intent.price is not None else _safe_price(position.symbol)
        requested = float(intent.size or 0)
        close_qty = min(requested, float(position.quantity or 0))
        if close_qty <= 0:
            raise ValueError("position_action_size_invalid")
        pnl_delta = _calc_realized_pnl(position, exit_price, close_qty)
        position.realized_pnl = float(position.realized_pnl or 0) + pnl_delta
        remaining = max(float(position.quantity or 0) - close_qty, 0)
        position.quantity = remaining
        if remaining <= 1e-8:
            position.status = "closed"
            position.closed_at = now
            position.unrealized_pnl = 0
        event_type = "position_partial_close"
    elif action == "REVERSE_POSITION":
        exit_price = float(intent.price) if intent.price is not None else _safe_price(position.symbol)
        close_qty = float(position.quantity or 0)
        pnl_delta = _calc_realized_pnl(position, exit_price, close_qty)
        position.realized_pnl = float(position.realized_pnl or 0) + pnl_delta
        position.unrealized_pnl = 0
        position.quantity = 0
        position.status = "closed"
        position.closed_at = now
        db.add(
            PositionLedgerEvent(
                id=str(uuid.uuid4()),
                position_id=position.id,
                event_type="position_reversed_close_leg",
                payload={"intent_id": intent.id, "exit_price": exit_price},
                created_at=now,
            )
        )

        bot = _default_bot(db, intent.user_id, position.market_type, symbol=position.symbol)
        new_side = "short" if position.side == "long" else "long"
        open_qty = float(intent.size or close_qty)
        open_price = _safe_price(position.symbol)
        new_position = PaperPosition(
            id=str(uuid.uuid4()),
            user_id=intent.user_id,
            bot_profile_id=bot.id,
            symbol=position.symbol,
            market_type=position.market_type,
            side=new_side,
            quantity=max(open_qty, 0.001),
            leverage=int(position.leverage or 1),
            entry_price=open_price,
            stop_loss=float(intent.stop_price) if intent.stop_price is not None else round(open_price * (1.01 if new_side == "short" else 0.99), 6),
            take_profit=float(intent.take_profit_price)
            if intent.take_profit_price is not None
            else round(open_price * (0.98 if new_side == "short" else 1.02), 6),
            status="open",
            unrealized_pnl=0,
            realized_pnl=0,
            opened_at=now,
            updated_at=now,
        )
        db.add(new_position)
        db.flush()
        sync_position_state(
            db,
            paper_position=position,
            strategy_id=(intent.normalized_order_payload or {}).get("strategy_binding"),
            cluster_id=intent.cluster_id,
        )
        sync_position_state(
            db,
            paper_position=new_position,
            strategy_id=(intent.normalized_order_payload or {}).get("strategy_binding"),
            cluster_id=intent.cluster_id,
        )
        event_type = "position_reversed"
        return new_position, event_type, position_action_reason
    elif action == "MOVE_STOP":
        if intent.stop_price is None:
            raise ValueError("stop_price_required")
        position.stop_loss = float(intent.stop_price)
        event_type = "position_stop_updated"
    elif action == "MOVE_TAKE_PROFIT":
        if intent.take_profit_price is None:
            raise ValueError("take_profit_price_required")
        position.take_profit = float(intent.take_profit_price)
        event_type = "position_take_profit_updated"
    else:
        raise ValueError("unsupported_intent_type")

    position.updated_at = now
    db.flush()
    sync_position_state(
        db,
        paper_position=position,
        strategy_id=(intent.normalized_order_payload or {}).get("strategy_binding"),
        cluster_id=intent.cluster_id,
    )
    return position, event_type, position_action_reason


def approve_execution_intent(db: Session, intent_id: str, admin_user_id: str, admin_note: str = "") -> UserExecutionIntent:
    intent = db.query(UserExecutionIntent).filter(UserExecutionIntent.id == intent_id).first()
    if intent is None:
        raise ValueError("intent_not_found")
    if intent.status != "QUEUED":
        raise ValueError("intent_not_in_queue")

    if intent.intent_type == "OPEN_POSITION":
        enforce_execution_guard_or_raise(
            db,
            user_id=intent.user_id,
            actor_user_id=admin_user_id,
            actor_role="ADMIN",
            source="admin_execution_approval",
        )
        enforce_execution_open_allowed_or_raise(
            db,
            proposed_notional=float(intent.notional or 0.0),
            source="admin_execution_approval",
            actor_user_id=admin_user_id,
            actor_role="ADMIN",
            entity_type="user_execution_intent",
            entity_id=intent.id,
        )

    intent.status = "APPROVED"
    intent.admin_user_id = admin_user_id
    intent.admin_note = admin_note
    intent.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(intent)

    normalized = intent.normalized_order_payload or {}
    try:
        symbol = normalize_symbol(
        normalized.get("symbol") or intent.symbol,
        missing_error_code="symbol_required_for_execution_order",
        invalid_error_code="invalid_quote_asset",
        )
    except InvalidSymbol as exc:
        raise ValueError(str(exc)) from exc
    strategy_code = str(normalized.get("strategy_binding") or "") or None

    if intent.intent_type == "OPEN_POSITION":
        position = _open_position_from_intent(db, intent, normalized)
        action_event_type = "execution_order_released"
        intent.position_id = position.id
    else:
        position, action_event_type, _ = _apply_position_action_intent(db, intent)
        intent.position_id = position.id
        db.add(
            PositionLedgerEvent(
                id=str(uuid.uuid4()),
                position_id=position.id,
                event_type=action_event_type,
                payload={
                    "intent_id": intent.id,
                    "intent_token": intent.intent_token,
                    "intent_type": intent.intent_type,
                    "position_id": intent.position_id,
                },
                created_at=datetime.now(timezone.utc),
            )
        )

    intent.status = "RELEASED"
    intent.released_at = datetime.now(timezone.utc)

    risk_adjustment_reason = "position_size_adjusted_by_portfolio_risk" if "portfolio_risk_adjusted" in (intent.risk_flags or []) else None
    strategy_override_reason = (
        "strategy_override_for_risk_reduction"
        if "strategy_override_for_risk_reduction" in (intent.risk_flags or [])
        else None
    )
    position_action_reason = intent.intent_type if intent.intent_type in POSITION_ACTION_TYPES else None
    hedge_recommendation, hedge_risk_reduction, correlation_basis = _extract_hedge_context(intent.normalized_order_payload or {})

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
        position_action_reason=position_action_reason,
        risk_adjustment_reason=risk_adjustment_reason,
        strategy_override_reason=strategy_override_reason,
        hedge_recommendation=hedge_recommendation,
        risk_reduction_score=hedge_risk_reduction,
        correlation_basis=correlation_basis,
        feature_snapshot={
            "symbol": symbol,
            "market_type": str(normalized.get("market_type") or "spot"),
            "side": position.side,
            "quantity": float(position.quantity or 0),
            "intent_type": intent.intent_type,
        },
        context_payload={
            "admin_user_id": admin_user_id,
            "admin_note": admin_note,
            "intent_token": intent.intent_token,
            "position_id": intent.position_id,
        },
    )

    trade_trace_type = "trade_opened_from_execution" if intent.intent_type == "OPEN_POSITION" else "trade_action_from_execution"
    trade_status = "OPENED" if position.status == "open" else "CLOSED"
    record_decision_trace(
        db,
        user_id=intent.user_id,
        trace_scope="trade",
        trace_type=trade_trace_type,
        entity_id=position.id,
        strategy_code=strategy_code,
        decision_status=trade_status,
        reason_codes=["trade_opened_from_execution"] if intent.intent_type == "OPEN_POSITION" else ["position_action_released"],
        portfolio_risk_score=float(intent.risk_score or 0),
        strategy_allocation_reason=(intent.normalized_order_payload or {}).get("meta_strategy_summary", {}).get(
            "strategy_allocation_reason"
        ),
        cluster_risk_flag=next((item for item in (intent.risk_flags or []) if "cluster" in str(item)), None),
        meta_engine_decision=intent.meta_engine_decision,
        position_action_reason=position_action_reason,
        risk_adjustment_reason=risk_adjustment_reason,
        strategy_override_reason=strategy_override_reason,
        hedge_recommendation=hedge_recommendation,
        risk_reduction_score=hedge_risk_reduction,
        correlation_basis=correlation_basis,
        feature_snapshot={
            "entry_price": float(position.entry_price or 0),
            "quantity": float(position.quantity or 0),
            "side": position.side,
            "leverage": int(position.leverage or 1),
            "intent_type": intent.intent_type,
        },
        context_payload={
            "intent_id": intent.id,
            "intent_token": intent.intent_token,
            "symbol": symbol,
            "position_id": position.id,
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
    hedge_recommendation, hedge_risk_reduction, correlation_basis = _extract_hedge_context(intent.normalized_order_payload or {})
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
        position_action_reason=intent.intent_type if intent.intent_type in POSITION_ACTION_TYPES else None,
        risk_adjustment_reason=(
            "position_size_adjusted_by_portfolio_risk" if "portfolio_risk_adjusted" in (intent.risk_flags or []) else None
        ),
        hedge_recommendation=hedge_recommendation,
        risk_reduction_score=hedge_risk_reduction,
        correlation_basis=correlation_basis,
        feature_snapshot={
            "symbol": intent.symbol,
            "market_type": intent.market_type,
            "side": intent.side,
            "notional": float(intent.notional or 0),
            "size": float(intent.size or 0),
            "intent_type": intent.intent_type,
        },
        context_payload={
            "admin_user_id": admin_user_id,
            "admin_note": admin_note,
            "intent_token": intent.intent_token,
            "position_id": intent.position_id,
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


def retry_execution_intent(db: Session, intent_id: str, admin_user_id: str, admin_note: str = "") -> UserExecutionIntent:
    intent = db.query(UserExecutionIntent).filter(UserExecutionIntent.id == intent_id).first()
    if intent is None:
        raise ValueError("intent_not_found")
    if intent.status != "REJECTED":
        raise ValueError("intent_not_retryable")

    intent.status = "QUEUED"
    intent.submitted_at = datetime.now(timezone.utc)
    intent.approved_at = None
    intent.released_at = None
    intent.cancelled_at = None
    intent.admin_user_id = admin_user_id
    intent.admin_note = admin_note or "retried_from_admin_queue"
    intent.reject_reason_codes = []
    db.commit()
    db.refresh(intent)
    return intent


def rejection_reason_summary(db: Session, limit: int = 500) -> list[dict]:
    rows = (
        db.query(UserExecutionIntent)
        .filter(UserExecutionIntent.status == "REJECTED")
        .order_by(UserExecutionIntent.updated_at.desc())
        .limit(limit)
        .all()
    )

    buckets: dict[str, int] = {}
    for row in rows:
        reasons = row.reject_reason_codes or ["unspecified"]
        for reason in reasons:
            key = str(reason or "unspecified")
            buckets[key] = buckets.get(key, 0) + 1

    return [
        {"reason_code": reason_code, "count": count}
        for reason_code, count in sorted(buckets.items(), key=lambda item: item[1], reverse=True)
    ]


def queue_status_summary(db: Session) -> dict:
    rows = (
        db.query(UserExecutionIntent.status, func.count(UserExecutionIntent.id))
        .group_by(UserExecutionIntent.status)
        .all()
    )
    by_status = {str(status): int(count) for status, count in rows}
    return {
        "total": int(sum(by_status.values())),
        "queued": int(by_status.get("QUEUED", 0)),
        "rejected": int(by_status.get("REJECTED", 0)),
        "released": int(by_status.get("RELEASED", 0)),
        "by_status": by_status,
    }


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


def summarize_execution_eligibility(intent: UserExecutionIntent) -> dict:
    market_type = str(intent.market_type or "spot").lower()
    contract_type = "perpetual" if market_type == "futures" else "spot"
    eligible_statuses = {"PREVIEWED", "QUEUED", "RELEASED", "APPROVED"}
    return {
        "intent_id": intent.id,
        "symbol": str(intent.symbol or "").upper(),
        "market_type": market_type,
        "contract_type": contract_type,
        "execution_eligible": str(intent.status or "").upper() in eligible_statuses,
        "status": str(intent.status or ""),
    }


def build_intent_explainability(normalized_payload: dict) -> dict:
    payload = dict(normalized_payload or {})
    strategy_name = str(payload.get("strategy_binding") or "manual_execution")
    confidence = float(payload.get("confidence") or 0.0)
    risk_reasons = payload.get("risk_reasons") or []
    risk_filter_reason = str(risk_reasons[0]) if risk_reasons else None
    decision_reason = str(payload.get("decision_reason") or payload.get("intent_type") or "execution_intent")
    return {
        "strategy_name": strategy_name,
        "signal_strength": confidence,
        "risk_filter_reason": risk_filter_reason,
        "decision_reason": decision_reason,
    }
