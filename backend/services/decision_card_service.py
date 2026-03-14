from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import UserDecisionTrace, UserScannerResult
from services.learning_memory_service import strategy_quality_lookup, strategy_recommendation_lookup


SCHEMA_VERSION = "decision-card.v1"
ENGINE_VERSION = "canonical-engine.v3"


def _normalize_decision(value: str | None) -> str:
    candidate = str(value or "").upper().strip()
    if candidate in {"LONG", "SHORT", "BLOCKED", "NO_TRADE"}:
        return candidate
    return "NO_TRADE"


def _decision_template(decision: str, family_scores: dict, blocked_reason: str | None, long_score: float, short_score: float) -> list[str]:
    templates: list[str] = []
    if decision == "LONG":
        supporters = [family for family, item in (family_scores or {}).items() if item.get("gate_status") == "ACCEPTED" and float(item.get("long_score") or 0) > 0]
        templates.append(f"{', '.join(supporters) or 'Strategy family'} confirmed long bias")
    elif decision == "SHORT":
        supporters = [family for family, item in (family_scores or {}).items() if item.get("gate_status") == "ACCEPTED" and float(item.get("short_score") or 0) > 0]
        templates.append(f"{', '.join(supporters) or 'Strategy family'} confirmed short bias")
    elif decision == "BLOCKED":
        templates.append(f"Risk/gating blocked decision due to {blocked_reason or 'unknown_reason'}")
    else:
        templates.append("Score threshold not met, no trade opened")

    if short_score >= 2 and decision == "LONG":
        templates.append("Short score rejected because opposite score exceeded reject threshold")
    if long_score >= 2 and decision == "SHORT":
        templates.append("Long score rejected because opposite score exceeded reject threshold")
    return templates


def _trace_timeline(db: Session, user_id: str, symbol: str, limit: int = 20) -> list[dict]:
    normalized = symbol.upper()
    rows = (
        db.query(UserDecisionTrace)
        .filter(UserDecisionTrace.user_id == user_id, UserDecisionTrace.trace_scope == "signal")
        .order_by(UserDecisionTrace.created_at.desc())
        .limit(500)
        .all()
    )
    items: list[dict] = []
    for row in rows:
        ctx = row.context_payload or {}
        if str(ctx.get("symbol") or "").upper() != normalized:
            continue
        reason_codes = row.reason_codes or []
        items.append(
            {
                "event_time": row.created_at,
                "layer": (row.feature_snapshot or {}).get("layer") or "signal",
                "reason_code": reason_codes[0] if reason_codes else "UNKNOWN",
                "reason_detail": (row.reason_details or [{}])[0].get("description") if row.reason_details else "-",
                "previous_state": (row.feature_snapshot or {}).get("previous_state") or "unknown",
                "new_state": (row.feature_snapshot or {}).get("new_state") or row.decision_status,
            }
        )
        if len(items) >= limit:
            break
    return items


def _resolve_block_category(*, payload: dict, blocked_reason: str | None, risk_block: str | None, cooldown_seconds: int) -> str | None:
    reason_codes = {str(item or "").strip().lower() for item in (payload.get("reason_codes") or []) if str(item or "").strip()}
    blocked_key = str(blocked_reason or "").strip().lower()

    permission_codes = {
        "symbol_not_allowed",
        "symbol_permission_block",
        "symbol_not_allowed_by_whitelist",
        "symbol_not_allowed_by_live_config",
    }
    if blocked_key in permission_codes or reason_codes.intersection(permission_codes):
        return "symbol_permission_block"

    data_codes = {"no_data", "data_unavailable", "stale_indicator_snapshot", "stale_data_block"}
    if blocked_key in data_codes or reason_codes.intersection(data_codes):
        return "data_unavailable"

    cooldown_codes = {"symbol_cooldown", "cooldown_active", "symbol_cooldown_active"}
    if cooldown_seconds > 0 or blocked_key in cooldown_codes or reason_codes.intersection(cooldown_codes):
        return "cooldown_block"

    risk_codes = {"risk_limit_blocked", "position_limit_reached", "max_positions_reached"}
    if risk_block or blocked_key in risk_codes or reason_codes.intersection(risk_codes):
        return "risk_block"

    gate_codes = {
        "family_gate_missing",
        "regime_mismatch",
        "long_threshold_not_met",
        "short_threshold_not_met",
        "min_strategy_count_not_met",
        "conflict_score_exceeded",
        "breakout_condition_missing",
        "pullback_trend_unclear",
        "reversal_requires_confirmation",
        "reversal_extra_confirmation_required",
        "threshold_not_met",
    }
    if blocked_key in gate_codes or reason_codes.intersection(gate_codes):
        return "gate_block"

    if blocked_key:
        return "risk_block"
    return None


def _row_to_decision_card(db: Session, row: UserScannerResult, quality_lookup: dict[str, dict], recommendation_lookup: dict[str, list[dict]]) -> dict:
    payload = row.payload or {}
    decision = _normalize_decision(payload.get("final_decision") or ("LONG" if row.signal == "long" else "SHORT" if row.signal == "short" else "NO_TRADE"))
    source_strategies = payload.get("source_strategies") or []
    top_contributors = payload.get("top_contributors") or source_strategies[:3]
    blocked_reason = payload.get("blocked_reason_current")
    dominant_strategy = str(payload.get("strategy_code") or row.strategy_code or "")
    quality = quality_lookup.get(dominant_strategy, {})
    recommendations = recommendation_lookup.get(dominant_strategy, [])
    learning_badges: list[str] = []
    confidence_adjustment = 0.0

    quality_score = float(quality.get("quality_score") or 0)
    if quality_score < 20 and quality.get("sample_count", 0) >= 5:
        learning_badges.append("recent quality degraded")
        confidence_adjustment -= 0.15
    if quality_score > 65 and quality.get("sample_count", 0) >= 5:
        learning_badges.append("decision supported by high-quality recent signals")
        confidence_adjustment += 0.1
    if any(item.get("recommendation_type") in {"auto_throttle_recommendation", "decrease_weight_recommendation"} for item in recommendations):
        learning_badges.append("strategy currently throttled")
        confidence_adjustment -= 0.1
    timeline = _trace_timeline(db, row.user_id, row.symbol, limit=20)
    if decision == "BLOCKED" and not blocked_reason:
        blocked_reason = timeline[0]["reason_code"] if timeline else None

    cooldown_seconds = int((payload.get("cooldown_state") or {}).get("seconds") or 0)
    risk_block = (payload.get("risk_state") or {}).get("reason")
    block_category = _resolve_block_category(
        payload=payload,
        blocked_reason=blocked_reason,
        risk_block=risk_block,
        cooldown_seconds=cooldown_seconds,
    )

    return {
        "schema_version": payload.get("schema_version") or SCHEMA_VERSION,
        "engine_version": payload.get("engine_version") or ENGINE_VERSION,
        "generated_at": row.generated_at,
        "symbol": row.symbol,
        "market_regime": payload.get("market_regime") or "unknown",
        "decision": decision,
        "confidence": float(payload.get("decision_confidence") or 0),
        "long_score": float(payload.get("long_score") or 0),
        "short_score": float(payload.get("short_score") or 0),
        "dominant_family": payload.get("dominant_family"),
        "supporting_families": payload.get("supporting_families") or [],
        "top_contributors": top_contributors,
        "top_strategies": top_contributors,
        "entry_zone": payload.get("entry_zone") or {},
        "stop_loss": payload.get("stop"),
        "take_profit_1": payload.get("take_profit_1"),
        "take_profit_2": payload.get("take_profit_2") or payload.get("take_profit"),
        "invalidation": payload.get("invalidation") or {},
        "blocked_reason": blocked_reason,
        "block_category": block_category,
        "cooldown_remaining": cooldown_seconds,
        "risk_block": risk_block,
        "risk_state": payload.get("risk_state") or {"state": "unknown"},
        "confidence_adjustment": round(confidence_adjustment, 4),
        "learning_badges": learning_badges,
        "learning_quality_score": round(quality_score, 4) if quality else None,
        "updated_at": row.generated_at,
    }


def list_user_decision_cards(db: Session, user_id: str, limit: int = 50) -> list[dict]:
    quality_lookup = strategy_quality_lookup(db)
    recommendation_lookup = strategy_recommendation_lookup(db)
    rows = (
        db.query(UserScannerResult)
        .filter(UserScannerResult.user_id == user_id)
        .order_by(UserScannerResult.generated_at.desc())
        .limit(max(limit * 5, 100))
        .all()
    )
    dedupe: dict[str, UserScannerResult] = {}
    for row in rows:
        if row.symbol in dedupe:
            continue
        dedupe[row.symbol] = row
        if len(dedupe) >= limit:
            break
    return [_row_to_decision_card(db, row, quality_lookup, recommendation_lookup) for row in dedupe.values()]


def get_user_decision_card(db: Session, user_id: str, symbol: str) -> dict | None:
    quality_lookup = strategy_quality_lookup(db)
    recommendation_lookup = strategy_recommendation_lookup(db)
    row = (
        db.query(UserScannerResult)
        .filter(UserScannerResult.user_id == user_id, UserScannerResult.symbol == symbol.upper())
        .order_by(UserScannerResult.generated_at.desc())
        .first()
    )
    if row is None:
        return None
    return _row_to_decision_card(db, row, quality_lookup, recommendation_lookup)


def get_user_symbol_explainability(db: Session, user_id: str, symbol: str) -> dict | None:
    row = (
        db.query(UserScannerResult)
        .filter(UserScannerResult.user_id == user_id, UserScannerResult.symbol == symbol.upper())
        .order_by(UserScannerResult.generated_at.desc())
        .first()
    )
    if row is None:
        return None
    payload = row.payload or {}
    final_decision = _normalize_decision(payload.get("final_decision") or "NO_TRADE")
    long_score = float(payload.get("long_score") or 0)
    short_score = float(payload.get("short_score") or 0)
    winning_side = payload.get("winning_side") or ("long" if long_score > short_score else "short" if short_score > long_score else "none")
    timeline = _trace_timeline(db, user_id, symbol, limit=20)
    blocked_reason = payload.get("blocked_reason_current") or (timeline[0]["reason_code"] if timeline else None)

    return {
        "schema_version": payload.get("schema_version") or SCHEMA_VERSION,
        "engine_version": payload.get("engine_version") or ENGINE_VERSION,
        "generated_at": row.generated_at,
        "symbol": row.symbol,
        "final_decision": final_decision,
        "long_score": long_score,
        "short_score": short_score,
        "winning_side": winning_side,
        "decision_confidence": float(payload.get("decision_confidence") or 0),
        "source_strategies": payload.get("source_strategies") or [],
        "family_scores": payload.get("family_scores") or {},
        "blocked_reason_current": blocked_reason,
        "blocked_reason_timeline": timeline,
        "risk_state": payload.get("risk_state") or {"state": "unknown"},
        "cooldown_state": payload.get("cooldown_state") or {"state": "unknown"},
        "regime_state": payload.get("regime_state") or {"state": "unknown"},
        "explanation_templates": _decision_template(final_decision, payload.get("family_scores") or {}, blocked_reason, long_score, short_score),
    }


def decision_card_envelope(items: list[dict]) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "generated_at": datetime.now(timezone.utc),
        "items": items,
    }


def blocked_timeline_envelope(symbol: str, items: list[dict]) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "generated_at": datetime.now(timezone.utc),
        "symbol": symbol.upper(),
        "items": items,
    }
