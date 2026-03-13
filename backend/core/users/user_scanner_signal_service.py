import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from db import redis_client
from models import (
    BotProfile,
    PaperPosition,
    PendingSignal,
    RiskPolicy,
    SignalEvent,
    UserExchangeConnection,
    UserScannerResult,
    UserSignalMode,
)
from services.execution_intent_service import (
    approve_execution_intent,
    preview_execution_intent,
    submit_execution_intent,
)
from services.explainability_service import record_decision_trace
from services.meta_strategy_engine_service import run_meta_strategy_engine
from services.pipeline.cache_store import get_json
from services.pipeline.spot_strategy_service import scan_spot_universe_for_signals
from services.venue_service import check_user_venue_access, seed_binance_venue_registry

ALLOWED_SIGNAL_MODES = {"ASSISTED", "AUTO", "MANUAL"}
DEFAULT_SIGNAL_MODE = "MANUAL"

SIGNAL_PENDING_REASON_HINTS = {
    "MANUAL_APPROVAL_REQUIRED": ("Sinyal manuel onay bekliyor.", "Sinyal satırından Approve ile devam edin."),
    "BOT_NOT_RUNNING": ("Bot runtime çalışmıyor.", "Bot profilini başlatın (is_running=true)."),
    "RISK_POLICY_MISSING": ("Risk policy tanımlı değil.", "Risk Policy ekranından aktif policy oluşturun."),
    "RISK_LIMIT_BLOCKED": ("Risk limiti engeli oluştu.", "Risk limitlerini veya mevcut pozisyon riskini kontrol edin."),
    "EXCHANGE_NOT_READY": ("Exchange readiness uygun değil.", "Exchange key/venue assignment/readiness durumunu düzeltin."),
    "MARKET_DATA_STALE": ("Piyasa verisi güncel değil.", "Market data akışını ve son candle zamanını doğrulayın."),
    "POSITION_LIMIT_REACHED": ("Pozisyon limiti dolu.", "Açık pozisyon sayısını azaltın veya policy limitini artırın."),
    "SYMBOL_NOT_ALLOWED": ("Sembol bot kapsamı dışında.", "Bot symbols listesine sembolü ekleyin."),
    "ORDER_PRECHECK_FAILED": ("Order precheck başarısız.", "Preview hata kodlarını inceleyip parametreleri düzeltin."),
    "EXECUTION_DISABLED": ("Execution strategy tarafından devre dışı.", "Meta strategy / bot strategy eşleşmesini düzeltin."),
    "SIGNAL_EXPIRED": ("Signal süresi doldu.", "Yeni sinyal üretimi bekleyin veya scanner yeniden çalıştırın."),
}

SIGNAL_REASON_PRIORITY = [
    "SIGNAL_EXPIRED",
    "BOT_NOT_RUNNING",
    "RISK_POLICY_MISSING",
    "POSITION_LIMIT_REACHED",
    "RISK_LIMIT_BLOCKED",
    "EXCHANGE_NOT_READY",
    "MARKET_DATA_STALE",
    "SYMBOL_NOT_ALLOWED",
    "EXECUTION_DISABLED",
    "ORDER_PRECHECK_FAILED",
    "MANUAL_APPROVAL_REQUIRED",
]


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
    normalized_symbols = [symbol.upper() for symbol in symbols if symbol]
    if not normalized_symbols:
        normalized_symbols = ["BTCUSDT", "ETHUSDT"]

    running_row = (
        db.query(BotProfile)
        .filter(BotProfile.user_id == user_id, BotProfile.is_running.is_(True))
        .order_by(BotProfile.created_at.desc())
        .first()
    )
    if running_row:
        merged_symbols = list(dict.fromkeys([*(running_row.symbols or []), *normalized_symbols]))[:40]
        if merged_symbols != (running_row.symbols or []):
            running_row.symbols = merged_symbols
            running_row.updated_at = datetime.now(timezone.utc)
            db.flush()
        return running_row

    row = db.query(BotProfile).filter(BotProfile.user_id == user_id).order_by(BotProfile.created_at.desc()).first()
    if row:
        row.is_running = True
        merged_symbols = list(dict.fromkeys([*(row.symbols or []), *normalized_symbols]))[:40]
        row.symbols = merged_symbols
        row.updated_at = datetime.now(timezone.utc)
        db.flush()
        return row

    row = BotProfile(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name="Assisted Signal Bot",
        exchange="binance",
        market_type="spot",
        symbols=normalized_symbols[:40],
        strategy_type="spot_pullback",
        timeframe="15m",
        trend_timeframe="1h",
        leverage=1,
        is_enabled=True,
        is_running=True,
    )
    db.add(row)
    db.flush()
    return row


def _execution_mode_label(mode: str | None) -> str:
    normalized = _normalize_mode(mode)
    if normalized == "MANUAL":
        return "Manual"
    if normalized == "AUTO":
        return "Full Auto"
    return "Semi-Auto"


def _requires_manual_approval(mode: str | None) -> bool:
    return _normalize_mode(mode) in {"MANUAL", "ASSISTED"}


def _base_strategy_code(strategy_code: str | None) -> str:
    raw = (strategy_code or "").strip().lower()
    if "_v" in raw:
        return raw.split("_v", 1)[0]
    return raw


def _resolve_default_risk_policy(db: Session, user_id: str) -> RiskPolicy | None:
    return (
        db.query(RiskPolicy)
        .filter(RiskPolicy.user_id == user_id)
        .order_by(RiskPolicy.updated_at.desc())
        .first()
    )


def _resolve_default_exchange_connection(db: Session, user_id: str) -> UserExchangeConnection | None:
    return (
        db.query(UserExchangeConnection)
        .filter(UserExchangeConnection.user_id == user_id)
        .order_by(UserExchangeConnection.is_default.desc(), UserExchangeConnection.updated_at.desc())
        .first()
    )


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        candidate = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(candidate)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _is_market_data_stale(symbol: str, stale_minutes: int = 12) -> bool:
    payload = get_json(redis_client, f"market:ticker:{symbol.upper()}") or {}
    timestamp_raw = payload.get("updated_at") or payload.get("timestamp")
    parsed = _parse_iso_datetime(str(timestamp_raw)) if timestamp_raw else None
    if parsed is None:
        return True
    age_seconds = (datetime.now(timezone.utc) - parsed).total_seconds()
    return age_seconds > stale_minutes * 60


def _signal_reason_details(reason_code: str) -> tuple[str, str]:
    return SIGNAL_PENDING_REASON_HINTS.get(
        reason_code,
        ("Sinyal işleme dönüşemedi.", "Decision trace ve execution precheck kayıtlarını inceleyin."),
    )


def _primary_reason_code(reason_codes: list[str]) -> str:
    for code in SIGNAL_REASON_PRIORITY:
        if code in reason_codes:
            return code
    return reason_codes[0] if reason_codes else ""


def _set_state(row: PendingSignal, next_state: str) -> None:
    if row.current_state == next_state:
        return
    row.previous_state = row.current_state or "DETECTED"
    row.current_state = next_state
    row.last_transition_at = datetime.now(timezone.utc)


def _evaluate_signal_blockers(
    db: Session,
    *,
    row: PendingSignal,
    signal: SignalEvent,
    bot: BotProfile | None,
    risk_policy: RiskPolicy | None,
    exchange_connection: UserExchangeConnection | None,
) -> tuple[list[str], bool, bool]:
    reason_codes: list[str] = []
    requires_manual = _requires_manual_approval(row.mode)

    if requires_manual:
        reason_codes.append("MANUAL_APPROVAL_REQUIRED")

    if bot is None or not bool(bot.is_running):
        reason_codes.append("BOT_NOT_RUNNING")

    if bot is not None:
        symbols = {item.upper() for item in (bot.symbols or []) if item}
        if symbols and row.symbol.upper() not in symbols:
            reason_codes.append("SYMBOL_NOT_ALLOWED")

        signal_strategy = _base_strategy_code(signal.strategy_id)
        bot_strategy = _base_strategy_code(bot.strategy_type)
        generic_runtime_strategies = {"spot_pullback", "trend_following", "mean_reversion", "volatility_breakout"}
        if (
            bot_strategy
            and signal_strategy
            and bot_strategy not in generic_runtime_strategies
            and bot_strategy != signal_strategy
        ):
            reason_codes.append("EXECUTION_DISABLED")

        if signal.market_type and bot.market_type and str(signal.market_type).lower() != str(bot.market_type).lower():
            reason_codes.append("EXECUTION_DISABLED")

    if risk_policy is None:
        reason_codes.append("RISK_POLICY_MISSING")
    else:
        open_positions = (
            db.query(PaperPosition)
            .filter(PaperPosition.user_id == row.user_id, PaperPosition.status == "open")
            .count()
        )
        if open_positions >= int(risk_policy.max_open_positions or 0):
            reason_codes.append("POSITION_LIMIT_REACHED")

    if row.meta_engine_decision == "DISABLED":
        reason_codes.append("EXECUTION_DISABLED")

    if _is_market_data_stale(row.symbol):
        reason_codes.append("MARKET_DATA_STALE")

    signal_generated_at = signal.generated_at
    if signal_generated_at.tzinfo is None:
        signal_generated_at = signal_generated_at.replace(tzinfo=timezone.utc)
    signal_age_seconds = (datetime.now(timezone.utc) - signal_generated_at).total_seconds()
    if signal_age_seconds > 60 * 45:
        reason_codes.append("SIGNAL_EXPIRED")

    if exchange_connection is None:
        reason_codes.append("EXCHANGE_NOT_READY")
    elif str(exchange_connection.environment).lower() == "live":
        seed_binance_venue_registry(db)
        allowed, _, _, _ = check_user_venue_access(
            db,
            row.user_id,
            exchange_connection.exchange,
            exchange_connection.market_type,
            exchange_connection.environment,
        )
        if not allowed:
            reason_codes.append("EXCHANGE_NOT_READY")

    deduped = list(dict.fromkeys(reason_codes))
    hard_blockers = [code for code in deduped if code != "MANUAL_APPROVAL_REQUIRED"]
    execution_eligible = len(hard_blockers) == 0 and not requires_manual
    return deduped, requires_manual, execution_eligible


def _refresh_pending_signal_snapshot(db: Session, row: PendingSignal) -> PendingSignal:
    if row.current_state in {"ORDER_SUBMITTED", "FILLED", "REJECTED"}:
        return row
    if row.current_state == "BLOCKED" and row.blocked_reason_code == "ORDER_PRECHECK_FAILED":
        row.status = "blocked"
        row.execution_eligible = False
        row.last_eligibility_check_at = datetime.now(timezone.utc)
        return row

    signal = db.query(SignalEvent).filter(SignalEvent.id == row.signal_id, SignalEvent.user_id == row.user_id).first()
    if signal is None:
        row.blocked_reason_code = "SIGNAL_EXPIRED"
        row.blocked_reason_message, row.blocked_solution_hint = _signal_reason_details("SIGNAL_EXPIRED")
        row.status = "expired"
        row.execution_eligible = False
        _set_state(row, "EXPIRED")
        row.last_eligibility_check_at = datetime.now(timezone.utc)
        return row

    bot = db.query(BotProfile).filter(BotProfile.id == signal.bot_profile_id).first()
    risk_policy = _resolve_default_risk_policy(db, row.user_id)
    exchange_connection = _resolve_default_exchange_connection(db, row.user_id)
    reason_codes, requires_manual, execution_eligible = _evaluate_signal_blockers(
        db,
        row=row,
        signal=signal,
        bot=bot,
        risk_policy=risk_policy,
        exchange_connection=exchange_connection,
    )

    primary_reason = _primary_reason_code(reason_codes)
    message, hint = _signal_reason_details(primary_reason) if primary_reason else ("", "")

    row.bot_profile_id = bot.id if bot else None
    row.risk_policy_id = risk_policy.id if risk_policy else None
    row.exchange_connection_id = exchange_connection.id if exchange_connection else None
    row.runtime_owner = bot.name if bot else ""
    row.requires_manual_approval = requires_manual
    row.execution_eligible = execution_eligible
    row.blocked_reason_code = primary_reason
    row.blocked_reason_message = message
    row.blocked_solution_hint = hint
    row.last_eligibility_check_at = datetime.now(timezone.utc)

    if primary_reason == "SIGNAL_EXPIRED":
        row.status = "expired"
        _set_state(row, "EXPIRED")
    elif execution_eligible:
        row.status = "ready"
        _set_state(row, "EXECUTION_READY")
    elif primary_reason == "MANUAL_APPROVAL_REQUIRED":
        row.status = "pending"
        _set_state(row, "PENDING_APPROVAL")
    else:
        row.status = "blocked"
        _set_state(row, "BLOCKED")

    return row


def _build_signal_intent_payload(
    row: PendingSignal,
    signal: SignalEvent,
    exchange_connection: UserExchangeConnection | None,
) -> dict:
    side = "buy" if signal.direction == "long" else "sell"
    payload = {
        "source_type": "manual",
        "source_ref_id": row.signal_id,
        "market_type": signal.market_type or "spot",
        "symbol": row.symbol,
        "side": side,
        "order_type": "market",
        "position_size_mode": "fixed_notional",
        "position_size_value": max(20.0, round(float(row.confidence or 0.5) * 120.0, 2)),
        "take_profit_mode": "percent",
        "take_profit_value": 2,
        "stop_loss_mode": "percent",
        "stop_loss_value": 1,
        "execution_mode": "manual",
        "strategy_binding": "manual_execution",
        "signal_confidence": float(row.confidence or 0.5),
        "signal_bridge_context": True,
    }
    if exchange_connection is not None:
        payload.update(
            {
                "exchange_connection_id": exchange_connection.id,
                "exchange": exchange_connection.exchange,
                "environment": exchange_connection.environment,
                "account_label": exchange_connection.account_label,
            }
        )
    return payload


def _dispatch_signal_to_execution(
    db: Session,
    *,
    row: PendingSignal,
    signal: SignalEvent,
    exchange_connection: UserExchangeConnection | None,
    actor_user_id: str,
) -> PendingSignal:
    _set_state(row, "APPROVED")
    row.status = "approved"
    row.decided_at = datetime.now(timezone.utc)
    row.decision_note = row.decision_note or "approved"

    payload = _build_signal_intent_payload(row, signal, exchange_connection)
    intent, validation = preview_execution_intent(db, row.user_id, payload)
    row.created_order_intent_id = intent.id
    _set_state(row, "ORDER_INTENT_CREATED")

    if validation.get("validation_status") != "valid":
        row.execution_eligible = False
        row.status = "blocked"
        row.blocked_reason_code = "ORDER_PRECHECK_FAILED"
        row.blocked_reason_message, row.blocked_solution_hint = _signal_reason_details("ORDER_PRECHECK_FAILED")
        row.decision_note = "order_precheck_failed"
        _set_state(row, "BLOCKED")
        return row

    submitted_intent = submit_execution_intent(db, row.user_id, intent.intent_token, preview_hash=intent.preview_hash)
    _set_state(row, "ORDER_SUBMITTED")
    row.status = "submitted"

    released_intent = approve_execution_intent(
        db,
        submitted_intent.id,
        admin_user_id=actor_user_id,
        admin_note="signal_runtime_auto_release",
    )
    row.order_position_id = released_intent.position_id
    row.status = "filled"
    row.execution_eligible = True
    row.blocked_reason_code = ""
    row.blocked_reason_message = ""
    row.blocked_solution_hint = ""
    row.decision_note = "approved_and_filled"
    _set_state(row, "FILLED")
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
    rows = (
        db.query(PendingSignal)
        .filter(PendingSignal.user_id == user_id)
        .order_by(PendingSignal.created_at.desc())
        .limit(limit)
        .all()
    )

    mutated = False
    for row in rows:
        if row.status not in {"rejected", "filled"}:
            before = (
                row.status,
                row.current_state,
                row.blocked_reason_code,
                row.execution_eligible,
                row.requires_manual_approval,
            )
            _refresh_pending_signal_snapshot(db, row)
            after = (
                row.status,
                row.current_state,
                row.blocked_reason_code,
                row.execution_eligible,
                row.requires_manual_approval,
            )
            if before != after:
                mutated = True
        row.execution_mode_label = _execution_mode_label(row.mode)

    if mutated:
        db.commit()
        for row in rows:
            db.refresh(row)
            row.execution_mode_label = _execution_mode_label(row.mode)
    return rows


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
        requested_notional = max(10.0, round(score, 4))

        meta_summary = run_meta_strategy_engine(
            db,
            user_id=user_id,
            strategy_id=strategy_code,
            symbol=symbol,
            signal_confidence=max(confidence, round(score / 100, 4)),
            requested_notional=requested_notional,
        )
        meta_decision = str(meta_summary.get("meta_engine_decision") or "ALLOW")
        allocation_source = str(meta_summary.get("allocation_source") or "weight_based")
        strategy_weight = float(meta_summary.get("strategy_weight") or 1.0)
        allocation_reason = str(meta_summary.get("strategy_allocation_reason") or "normal_allocation")

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

        pending_row = PendingSignal(
            id=str(uuid.uuid4()),
            signal_id=signal_event.id,
            user_id=user_id,
            symbol=symbol,
            strategy_code=strategy_code,
            confidence=signal_event.confidence,
            mode=mode,
            status="pending",
            strategy_weight=strategy_weight,
            allocation_source=allocation_source,
            meta_engine_decision=meta_decision,
            previous_state="DETECTED",
            current_state="DETECTED",
            bot_profile_id=bot.id,
            runtime_owner=bot.name,
            created_at=datetime.now(timezone.utc),
            decision_note=allocation_reason if meta_decision != "ALLOW" else "",
        )
        db.add(pending_row)
        db.flush()

        _refresh_pending_signal_snapshot(db, pending_row)
        pending_row.execution_mode_label = _execution_mode_label(mode)

        if pending_row.status == "pending":
            queued_count += 1

        if mode == "AUTO" and pending_row.execution_eligible:
            try:
                connection = _resolve_default_exchange_connection(db, user_id)
                _dispatch_signal_to_execution(
                    db,
                    row=pending_row,
                    signal=signal_event,
                    exchange_connection=connection,
                    actor_user_id=user_id,
                )
            except Exception:
                pending_row.status = "blocked"
                pending_row.blocked_reason_code = "ORDER_PRECHECK_FAILED"
                (
                    pending_row.blocked_reason_message,
                    pending_row.blocked_solution_hint,
                ) = _signal_reason_details("ORDER_PRECHECK_FAILED")
                _set_state(pending_row, "BLOCKED")

        record_decision_trace(
            db,
            user_id=user_id,
            trace_scope="signal",
            trace_type="scanner_signal_generated",
            entity_id=pending_row.id,
            strategy_code=strategy_code,
            decision_status=pending_row.current_state,
            reason_codes=[pending_row.blocked_reason_code] if pending_row.blocked_reason_code else (reason_codes or ["signal_generated_without_reason_code"]),
            strategy_allocation_reason=allocation_reason,
            meta_engine_decision=meta_decision,
            feature_snapshot={
                "confidence": float(signal_event.confidence or 0),
                "signal_score": score,
                "mode": mode,
                "signal": signal_value,
                "strategy_weight": strategy_weight,
                "execution_eligible": pending_row.execution_eligible,
            },
            context_payload={
                "run_id": run_id,
                "symbol": symbol,
                "signal_event_id": signal_event.id,
                "pending_status": pending_row.status,
                "current_state": pending_row.current_state,
                "allocation_source": allocation_source,
                "meta_strategy_summary": meta_summary,
                "requires_manual_approval": pending_row.requires_manual_approval,
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

        actionable_count += 1
        fallback_pending = PendingSignal(
            id=str(uuid.uuid4()),
            signal_id=fallback_signal.id,
            user_id=user_id,
            symbol=fallback_symbol,
            strategy_code=fallback_strategy,
            confidence=0.55,
            mode=mode,
            status="pending",
            strategy_weight=1.0,
            allocation_source="fallback",
            meta_engine_decision="ALLOW",
            previous_state="DETECTED",
            current_state="DETECTED",
            bot_profile_id=bot.id,
            runtime_owner=bot.name,
            created_at=datetime.now(timezone.utc),
            decision_note="fallback_signal_created",
        )
        db.add(fallback_pending)
        db.flush()
        _refresh_pending_signal_snapshot(db, fallback_pending)

        if fallback_pending.status == "pending":
            queued_count += 1

        if mode == "AUTO" and fallback_pending.execution_eligible:
            try:
                connection = _resolve_default_exchange_connection(db, user_id)
                _dispatch_signal_to_execution(
                    db,
                    row=fallback_pending,
                    signal=fallback_signal,
                    exchange_connection=connection,
                    actor_user_id=user_id,
                )
            except Exception:
                fallback_pending.status = "blocked"
                fallback_pending.blocked_reason_code = "ORDER_PRECHECK_FAILED"
                (
                    fallback_pending.blocked_reason_message,
                    fallback_pending.blocked_solution_hint,
                ) = _signal_reason_details("ORDER_PRECHECK_FAILED")
                _set_state(fallback_pending, "BLOCKED")

        record_decision_trace(
            db,
            user_id=user_id,
            trace_scope="signal",
            trace_type="scanner_fallback_signal",
            entity_id=fallback_pending.id,
            strategy_code=fallback_strategy,
            decision_status=fallback_pending.current_state,
            reason_codes=[fallback_pending.blocked_reason_code] if fallback_pending.blocked_reason_code else ["fallback_signal_low_activity"],
            strategy_allocation_reason="fallback_signal_created",
            meta_engine_decision="ALLOW",
            feature_snapshot={
                "confidence": 0.55,
                "mode": mode,
                "signal": "long",
                "strategy_weight": 1.0,
                "execution_eligible": fallback_pending.execution_eligible,
            },
            context_payload={
                "run_id": run_id,
                "symbol": fallback_symbol,
                "signal_event_id": fallback_signal.id,
                "pending_status": fallback_pending.status,
                "current_state": fallback_pending.current_state,
                "allocation_source": "fallback",
                "requires_manual_approval": fallback_pending.requires_manual_approval,
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


def approve_pending_signal(db: Session, user_id: str, pending_signal_id: str, note: str = "") -> PendingSignal:
    row = (
        db.query(PendingSignal)
        .filter(PendingSignal.id == pending_signal_id, PendingSignal.user_id == user_id)
        .first()
    )
    if row is None:
        raise ValueError("pending_signal_not_found")
    if row.status not in {"pending", "ready", "blocked"}:
        raise ValueError("pending_signal_not_actionable")

    signal = db.query(SignalEvent).filter(SignalEvent.id == row.signal_id, SignalEvent.user_id == user_id).first()
    if signal is None:
        raise ValueError("signal_event_not_found")

    _refresh_pending_signal_snapshot(db, row)
    if row.blocked_reason_code and row.blocked_reason_code not in {"MANUAL_APPROVAL_REQUIRED", ""}:
        raise ValueError(f"signal_blocked:{row.blocked_reason_code}")

    decision_note = note or "approved"
    row.decision_note = decision_note
    row.decided_at = datetime.now(timezone.utc)

    exchange_connection = _resolve_default_exchange_connection(db, user_id)
    _dispatch_signal_to_execution(
        db,
        row=row,
        signal=signal,
        exchange_connection=exchange_connection,
        actor_user_id=user_id,
    )

    record_decision_trace(
        db,
        user_id=user_id,
        trace_scope="signal",
        trace_type="user_signal_decision",
        entity_id=row.id,
        strategy_code=row.strategy_code,
        decision_status="APPROVED",
        reason_codes=["user_signal_approved"],
        strategy_allocation_reason=row.decision_note or "user_signal_approved",
        meta_engine_decision=row.meta_engine_decision,
        feature_snapshot={
            "confidence": float(row.confidence or 0),
            "mode": row.mode,
            "decision_note": decision_note,
            "strategy_weight": float(row.strategy_weight or 1),
            "execution_eligible": row.execution_eligible,
            "current_state": row.current_state,
        },
        context_payload={
            "pending_signal_id": row.id,
            "signal_id": row.signal_id,
            "position_id": row.order_position_id,
            "symbol": row.symbol,
            "allocation_source": row.allocation_source,
            "meta_engine_decision": row.meta_engine_decision,
            "created_order_intent_id": row.created_order_intent_id,
            "blocked_reason_code": row.blocked_reason_code,
        },
    )

    if row.order_position_id:
        position = db.query(PaperPosition).filter(PaperPosition.id == row.order_position_id).first()
        if position is not None:
            record_decision_trace(
                db,
                user_id=user_id,
                trace_scope="trade",
                trace_type="trade_opened_from_signal",
                entity_id=position.id,
                strategy_code=row.strategy_code,
                decision_status="OPENED",
                reason_codes=["trade_opened_from_signal"],
                strategy_allocation_reason=row.decision_note or "trade_opened_from_signal",
                meta_engine_decision=row.meta_engine_decision,
                feature_snapshot={
                    "entry_price": float(position.entry_price or 0),
                    "quantity": float(position.quantity or 0),
                    "side": position.side,
                    "strategy_weight": float(row.strategy_weight or 1),
                },
                context_payload={
                    "pending_signal_id": row.id,
                    "signal_id": row.signal_id,
                    "symbol": row.symbol,
                    "allocation_source": row.allocation_source,
                    "meta_engine_decision": row.meta_engine_decision,
                    "created_order_intent_id": row.created_order_intent_id,
                },
            )

    db.commit()
    db.refresh(row)
    row.execution_mode_label = _execution_mode_label(row.mode)
    return row


def reject_pending_signal(db: Session, user_id: str, pending_signal_id: str, note: str = "") -> PendingSignal:
    row = (
        db.query(PendingSignal)
        .filter(PendingSignal.id == pending_signal_id, PendingSignal.user_id == user_id)
        .first()
    )
    if row is None:
        raise ValueError("pending_signal_not_found")
    if row.status not in {"pending", "ready", "blocked"}:
        raise ValueError("pending_signal_not_actionable")

    _refresh_pending_signal_snapshot(db, row)
    decision_note = note or "rejected"
    row.status = "rejected"
    row.decided_at = datetime.now(timezone.utc)
    row.decision_note = decision_note
    _set_state(row, "REJECTED")

    record_decision_trace(
        db,
        user_id=user_id,
        trace_scope="signal",
        trace_type="user_signal_decision",
        entity_id=row.id,
        strategy_code=row.strategy_code,
        decision_status="REJECTED",
        reason_codes=["user_signal_rejected"],
        strategy_allocation_reason=decision_note,
        meta_engine_decision=row.meta_engine_decision,
        feature_snapshot={
            "confidence": float(row.confidence or 0),
            "mode": row.mode,
            "decision_note": decision_note,
            "strategy_weight": float(row.strategy_weight or 1),
            "blocked_reason_code": row.blocked_reason_code,
        },
        context_payload={
            "pending_signal_id": row.id,
            "signal_id": row.signal_id,
            "symbol": row.symbol,
            "allocation_source": row.allocation_source,
            "meta_engine_decision": row.meta_engine_decision,
            "current_state": row.current_state,
        },
    )

    db.commit()
    db.refresh(row)
    row.execution_mode_label = _execution_mode_label(row.mode)
    return row