from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from models import (
    CanonicalStrategyRegistry,
    FamilyOutcomeMemory,
    LearningDecisionEvent,
    LearningRecommendation,
    PaperPosition,
    PendingSignal,
    StrategyOutcomeMemory,
    UserScannerResult,
)


LEARNING_SCHEMA_VERSION = "learning.v1"
LEARNING_ENGINE_VERSION = "learning-engine.v1"
LEARNING_ENGINE_VERSION_V15 = "learning-engine.v1.5"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_safe(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _ensure_learning_tables(db: Session):
    inspector = inspect(db.bind)
    existing = set(inspector.get_table_names())
    for model in [LearningDecisionEvent, StrategyOutcomeMemory, FamilyOutcomeMemory, LearningRecommendation]:
        table_name = model.__table__.name
        if table_name not in existing:
            model.__table__.create(bind=db.bind, checkfirst=True)
            existing.add(table_name)


def _classify_outcome(position: PaperPosition | None, pending: PendingSignal | None, decision: str) -> tuple[str, float, float, float, bool, bool]:
    if position is not None and position.status == "closed":
        pnl = _safe_float(position.realized_pnl)
        denom = abs(_safe_float(position.entry_price) * _safe_float(position.quantity)) or 1.0
        pnl_norm = pnl / denom
        if pnl > 0:
            label = "WIN"
        elif pnl < 0:
            label = "LOSS"
        else:
            label = "BREAKEVEN"
        mfe = max(pnl_norm, 0.0)
        mae = min(pnl_norm, 0.0)
        return label, pnl_norm, mfe, mae, pnl <= 0, pnl > 0

    if pending is not None and pending.status in {"blocked", "risk_blocked", "rejected"}:
        return "REJECTED", 0.0, 0.0, 0.0, False, False

    if decision in {"NO_TRADE", "BLOCKED"}:
        return "REJECTED", 0.0, 0.0, 0.0, False, False

    return "OPEN", 0.0, 0.0, 0.0, False, False


def _canonical_signal(row: UserScannerResult | None, payload: dict | None) -> dict:
    source_payload = payload or {}
    return {
        "signal_strength": _safe_float(source_payload.get("signal_strength") or source_payload.get("score") or 0.0),
        "signal_type": str(source_payload.get("signal_type") or source_payload.get("final_decision") or "none").lower(),
        "scanner_result_id": str(getattr(row, "id", None) or getattr(row, "scanner_result_id", None) or "") or None,
    }


def _canonical_regime(payload: dict | None) -> str:
    source_payload = payload or {}
    regime_payload = source_payload.get("regime_state") or source_payload.get("regime_snapshot") or {}
    return str(regime_payload.get("market_regime") or source_payload.get("market_regime") or "unknown")


def _decision_quality_breakdown(events: list[LearningDecisionEvent]) -> dict:
    decisions = defaultdict(int)
    for event in events:
        decisions[str(event.outcome_label or "OPEN")] += 1
    total = max(len(events), 1)
    return {
        "win_rate": round(decisions.get("WIN", 0) / total, 6),
        "loss_rate": round(decisions.get("LOSS", 0) / total, 6),
        "blocked_rate": round(decisions.get("RISK_BLOCKED", 0) / total, 6),
        "rejected_rate": round(decisions.get("REJECTED", 0) / total, 6),
        "manual_cancel_rate": round(decisions.get("MANUAL_CANCELLED", 0) / total, 6),
        "no_trade_rate": round(decisions.get("NO_TRADE", 0) / total, 6),
    }


def _rolling_window_summary(rows: list[LearningDecisionEvent]) -> dict:
    now = _utcnow()
    windows = {}
    for label, days in [("7d", 7), ("30d", 30), ("90d", 90)]:
        scoped = [row for row in rows if row.created_at and row.created_at >= now - timedelta(days=days)]
        windows[label] = _window_metrics(scoped)
    return windows


def _decay_and_drift(rows: list[LearningDecisionEvent]) -> dict:
    rolling = _rolling_window_summary(rows)
    short_term = rolling.get("7d") or {}
    medium_term = rolling.get("30d") or {}
    long_term = rolling.get("90d") or medium_term
    decay_score = max(0.0, round((_safe_float(long_term.get("avg_return"), 0.0) - _safe_float(short_term.get("avg_return"), 0.0)) * 1000, 6))
    regimes_short = Counter(_canonical_regime(row.regime_snapshot) for row in rows if row.created_at and row.created_at >= _utcnow() - timedelta(days=7))
    regimes_long = Counter(_canonical_regime(row.regime_snapshot) for row in rows if row.created_at and row.created_at >= _utcnow() - timedelta(days=90))
    top_short = regimes_short.most_common(1)[0][0] if regimes_short else "unknown"
    top_long = regimes_long.most_common(1)[0][0] if regimes_long else "unknown"
    regime_drift_flag = top_short != top_long and top_short != "unknown" and top_long != "unknown"
    confidence_degradation = round(max(0.0, (_safe_float(long_term.get("hit_rate"), 0.0) - _safe_float(short_term.get("hit_rate"), 0.0)) / 100.0), 6)
    return {
        "rolling_windows": rolling,
        "window_comparison": {
            "7d_vs_30d": {
                "pnl_norm_delta": round(_safe_float(short_term.get("avg_return"), 0.0) - _safe_float(medium_term.get("avg_return"), 0.0), 8),
                "hit_rate_delta": round(_safe_float(short_term.get("hit_rate"), 0.0) - _safe_float(medium_term.get("hit_rate"), 0.0), 6),
                "drawdown_delta": round(_safe_float(short_term.get("drawdown"), 0.0) - _safe_float(medium_term.get("drawdown"), 0.0), 6),
                "false_allow_delta": round(_safe_float(short_term.get("false_allow_rate"), 0.0) - _safe_float(medium_term.get("false_allow_rate"), 0.0), 6),
                "false_reject_delta": round(_safe_float(short_term.get("false_reject_rate"), 0.0) - _safe_float(medium_term.get("false_reject_rate"), 0.0), 6),
            },
            "30d_vs_90d": {
                "pnl_norm_delta": round(_safe_float(medium_term.get("avg_return"), 0.0) - _safe_float(long_term.get("avg_return"), 0.0), 8),
                "hit_rate_delta": round(_safe_float(medium_term.get("hit_rate"), 0.0) - _safe_float(long_term.get("hit_rate"), 0.0), 6),
                "drawdown_delta": round(_safe_float(medium_term.get("drawdown"), 0.0) - _safe_float(long_term.get("drawdown"), 0.0), 6),
                "false_allow_delta": round(_safe_float(medium_term.get("false_allow_rate"), 0.0) - _safe_float(long_term.get("false_allow_rate"), 0.0), 6),
                "false_reject_delta": round(_safe_float(medium_term.get("false_reject_rate"), 0.0) - _safe_float(long_term.get("false_reject_rate"), 0.0), 6),
            },
        },
        "stability_score": round(max(0.0, 1.0 - abs(_safe_float(short_term.get("avg_return"), 0.0) - _safe_float(long_term.get("avg_return"), 0.0)) * 10 - confidence_degradation), 6),
        "decay_score": decay_score,
        "regime_drift_flag": regime_drift_flag,
        "drift_confidence": round(min(0.95, 0.45 + (0.2 if regime_drift_flag else 0.0) + confidence_degradation), 6),
        "confidence_degradation": confidence_degradation,
        "actionability_flag": bool(decay_score > 0.01 or regime_drift_flag),
    }


def _cross_strategy_correlation(events: list[LearningDecisionEvent]) -> dict:
    strategies = [str(event.strategy_id or "unknown") for event in events]
    symbols = [str(event.symbol or "unknown") for event in events]
    strategy_diversity = len(set(strategies))
    symbol_overlap = 1.0 - (len(set(symbols)) / max(len(symbols), 1))
    correlation_score = round(min(1.0, (symbol_overlap * 0.6) + (max(strategy_diversity - 1, 0) / max(len(events), 1)) * 4), 6)
    return {
        "cross_strategy_correlation": correlation_score,
        "strategy_count": strategy_diversity,
        "symbol_cluster": sorted(set(symbols))[:10],
    }


def _recommendation_control_state(*, recommendation_type: str, confidence: float, risk_impact: dict, sample_count: int, scope: str, stability_score: float = 0.0) -> dict:
    tail = abs(_safe_float((risk_impact or {}).get("tail_impact"), 0.0))
    cluster = abs(_safe_float((risk_impact or {}).get("cluster_impact"), 0.0))
    capital = abs(_safe_float((risk_impact or {}).get("capital_impact"), 0.0))
    risk_total = tail + cluster + capital
    actionable_state = "actionable"
    if sample_count < 8:
        actionable_state = "ignore"
    elif risk_total > 1.25 or confidence < 0.5:
        actionable_state = "monitor_only"
    elif stability_score < 0.35:
        actionable_state = "monitor_only"

    recommendation_score = round(max(0.0, min(100.0, confidence * 55 + max(stability_score, 0.0) * 20 + max(sample_count, 0) * 0.15 - risk_total * 18)), 6)
    auto_apply_eligible = bool(
        actionable_state == "actionable"
        and scope == "strategy"
        and recommendation_type in {"threshold_tune", "strategy_weight_down", "strategy_weight_up"}
        and confidence >= 0.72
        and risk_total <= 0.7
    )
    return {
        "actionable_state": actionable_state,
        "recommendation_score": recommendation_score,
        "decision_candidate": actionable_state in {"actionable", "monitor_only"},
        "auto_apply_eligible": auto_apply_eligible,
    }


def _enrich_recommendation_payload(row: LearningRecommendation) -> dict:
    payload = _ensure_recommendation_defaults(row)
    evidence = dict(payload.get("evidence_summary") or {})
    rolling = dict(evidence.get("rolling_windows") or {})
    drift = dict(evidence.get("drift") or {})
    sample_count = int(evidence.get("sample_count") or evidence.get("sample") or rolling.get("30d", {}).get("sample_count") or 0)
    confidence = _safe_float(payload.get("confidence"), 0.55)
    scope = str(payload.get("scope") or "strategy")
    risk_impact = dict(payload.get("risk_impact") or {})
    stability_score = _safe_float(drift.get("stability_score"), 0.0)
    control = _recommendation_control_state(
        recommendation_type=str(row.recommendation_type or ""),
        confidence=confidence,
        risk_impact=risk_impact,
        sample_count=sample_count,
        scope=scope,
        stability_score=stability_score,
    )
    payload.update(control)
    payload.setdefault("scope_reason", f"scope={scope} çünkü evidence bu katmanda yoğunlaşıyor")
    payload.setdefault("cross_strategy_correlation", _safe_float((evidence.get("cross_strategy") or {}).get("cross_strategy_correlation"), 0.0))
    payload.setdefault("monitoring_feedback", {})
    row.recommendation_value = payload
    return payload


def _false_flags(outcome_label: str, decision: str) -> tuple[bool, bool]:
    normalized_outcome = str(outcome_label or "OPEN").upper()
    normalized_decision = str(decision or "NO_TRADE").upper()
    false_allow = normalized_decision in {"LONG", "SHORT"} and normalized_outcome in {"LOSS", "REJECTED", "RISK_BLOCKED", "MANUAL_CANCELLED"}
    false_reject = normalized_decision in {"NO_TRADE", "BLOCKED"} and normalized_outcome in {"MISSED_TRADE", "FALSE_REJECT"}
    return false_allow, false_reject


def _ensure_recommendation_defaults(row: LearningRecommendation) -> dict:
    payload = dict(row.recommendation_value or {})
    payload.setdefault("scope", "strategy" if row.strategy_id else "family" if row.family else "portfolio")
    payload.setdefault("reason", row.note or "learning recommendation")
    payload.setdefault("confidence", 0.55)
    payload.setdefault("evidence_summary", {})
    payload.setdefault("risk_impact", {"tail_impact": 0.0, "cluster_impact": 0.0, "capital_impact": 0.0})
    payload.setdefault("lifecycle", "recommendation_created")
    payload.setdefault("status_history", [{"state": "recommendation_created", "at": _utcnow().isoformat()}])
    payload.setdefault("version", {"previous_version": None, "current_version": f"learning-rec-{row.id[:8]}", "changed_by": None, "changed_reason": row.note or "created", "rollback_target": None})
    row.recommendation_value = payload
    return payload


def _quality_degradation_flag(decay_quality: float) -> bool:
    return float(decay_quality) < 25.0


def refresh_learning_memory(db: Session, *, window_days: int = 30) -> dict:
    _ensure_learning_tables(db)
    window_start = datetime.now(timezone.utc) - timedelta(days=window_days)

    scanner_rows = (
        db.query(UserScannerResult)
        .filter(UserScannerResult.generated_at >= window_start)
        .order_by(UserScannerResult.generated_at.desc())
        .all()
    )
    events_by_scanner = {
        row.scanner_result_id: row
        for row in db.query(LearningDecisionEvent)
        .filter(LearningDecisionEvent.created_at >= window_start, LearningDecisionEvent.scanner_result_id.isnot(None))
        .all()
    }
    # Track already-used pending signal IDs to avoid unique constraint violations
    used_pending_signal_ids = set(
        row.pending_signal_id
        for row in db.query(LearningDecisionEvent)
        .filter(LearningDecisionEvent.pending_signal_id.isnot(None))
        .all()
    )

    for row in scanner_rows:
        payload = row.payload or {}
        decision = str(payload.get("final_decision") or "NO_TRADE").upper()
        strategy_id = str(payload.get("strategy_code") or row.strategy_code or "unknown")
        source_strategies = payload.get("source_strategies") or []
        family_scores = payload.get("family_scores") or {}
        dominant_family = payload.get("dominant_family") or (
            source_strategies[0].get("family") if source_strategies else "unknown"
        )

        pending = (
            db.query(PendingSignal)
            .filter(
                PendingSignal.user_id == row.user_id,
                PendingSignal.symbol == row.symbol,
                PendingSignal.strategy_code == strategy_id,
                PendingSignal.created_at >= row.generated_at - timedelta(minutes=30),
                PendingSignal.created_at <= row.generated_at + timedelta(minutes=30),
            )
            .order_by(PendingSignal.created_at.asc())
            .first()
        )
        position = None
        if pending is not None and pending.order_position_id:
            position = db.query(PaperPosition).filter(PaperPosition.id == pending.order_position_id).first()

        outcome_label, pnl_norm, mfe, mae, stop_hit, tp_hit = _classify_outcome(position, pending, decision)
        if pending is not None:
            pending_status = str(pending.status or "").lower()
            if pending_status in {"risk_blocked", "blocked"}:
                outcome_label = "RISK_BLOCKED"
            elif pending_status in {"rejected"}:
                outcome_label = "REJECTED"
            elif pending_status in {"cancelled", "canceled"}:
                outcome_label = "MANUAL_CANCELLED"
        elif decision in {"NO_TRADE", "BLOCKED"}:
            outcome_label = "NO_TRADE"
        hold_minutes = 0.0
        closed_at = None
        if position is not None and position.closed_at is not None:
            closed_at = position.closed_at
            open_at = position.opened_at or row.generated_at
            hold_minutes = max((closed_at - open_at).total_seconds() / 60, 0)

        event = events_by_scanner.get(row.id)
        if event is None:
            event = LearningDecisionEvent(
                id=str(uuid.uuid4()),
                user_id=row.user_id,
                symbol=row.symbol,
                scanner_result_id=row.id,
            )
            db.add(event)
            events_by_scanner[row.id] = event

        event.decision = decision
        event.source_strategies = source_strategies
        event.family_scores = family_scores
        event.regime_snapshot = payload.get("regime_state") or {"market_regime": payload.get("market_regime")}
        event.risk_snapshot = payload.get("risk_state") or {}
        event.entry_price = _safe_float(payload.get("entry"), None)
        event.exit_price = _safe_float(position.entry_price, None) if position is not None and position.status == "closed" else None
        event.max_favorable_excursion = float(mfe)
        event.max_adverse_excursion = float(mae)
        event.hold_duration_minutes = float(hold_minutes)
        event.outcome_label = outcome_label
        event.pnl_normalized = float(pnl_norm)
        event.stop_hit = bool(stop_hit)
        event.tp_hit = bool(tp_hit)
        event.timed_exit = False
        event.invalidated = decision in {"BLOCKED", "NO_TRADE"}
        event.strategy_id = strategy_id
        event.strategy_family = str(dominant_family or "unknown")
        # Only set pending_signal_id if not already used (unique constraint)
        if pending is not None and pending.id not in used_pending_signal_ids:
            event.pending_signal_id = pending.id
            used_pending_signal_ids.add(pending.id)
        else:
            event.pending_signal_id = None
        event.position_id = position.id if position is not None else None
        event.created_at = row.generated_at
        event.closed_at = closed_at

    db.commit()

    recent_events = (
        db.query(LearningDecisionEvent)
        .filter(LearningDecisionEvent.created_at >= window_start)
        .all()
    )

    db.query(StrategyOutcomeMemory).delete()
    db.query(FamilyOutcomeMemory).delete()
    db.query(LearningRecommendation).filter(LearningRecommendation.is_applied.is_(False)).delete()

    strategy_buckets: dict[tuple[str, str, str], list[LearningDecisionEvent]] = defaultdict(list)
    family_buckets: dict[tuple[str, str], list[LearningDecisionEvent]] = defaultdict(list)
    for event in recent_events:
        regime = str((event.regime_snapshot or {}).get("market_regime") or "any")
        decision = str(event.decision or "NO_TRADE").upper()
        direction = "long" if decision == "LONG" else "short" if decision == "SHORT" else "both"
        strategy_key = (str(event.strategy_id or "unknown"), direction, regime)
        family_key = (str(event.strategy_family or "unknown"), regime)
        strategy_buckets[strategy_key].append(event)
        family_buckets[family_key].append(event)

    recommendations: list[LearningRecommendation] = []

    for (strategy_id, direction, regime), events in strategy_buckets.items():
        sample = len(events)
        closed = [e for e in events if e.outcome_label in {"WIN", "LOSS", "BREAKEVEN"}]
        wins = [e for e in closed if e.outcome_label == "WIN"]
        actionable = [e for e in events if e.decision in {"LONG", "SHORT"}]
        false_allow_count = len([e for e in actionable if _false_flags(e.outcome_label, e.decision)[0]])
        false_reject_count = len([e for e in events if _false_flags(e.outcome_label, e.decision)[1]])

        hit_rate = (len(wins) / len(closed) * 100) if closed else 0.0
        avg_return = (sum(e.pnl_normalized for e in closed) / len(closed)) if closed else 0.0
        avg_mfe = (sum(e.max_favorable_excursion for e in events) / sample) if sample else 0.0
        avg_mae = (sum(e.max_adverse_excursion for e in events) / sample) if sample else 0.0
        false_allow_rate = (false_allow_count / len(actionable) * 100) if actionable else 0.0
        false_reject_rate = (false_reject_count / sample * 100) if sample else 0.0
        rolling = (hit_rate * 0.7) + ((avg_return * 100) * 0.3)
        decay_quality = (rolling * 0.8) - (false_allow_rate * 0.2)
        closed_returns = [e.pnl_normalized for e in closed]
        cumulative = 0.0
        peak = 0.0
        drawdown = 0.0
        for value in closed_returns:
            cumulative += value
            peak = max(peak, cumulative)
            drawdown = min(drawdown, cumulative - peak)

        pnl_by_regime = defaultdict(float)
        for event in closed:
            pnl_by_regime[str((event.regime_snapshot or {}).get("market_regime") or "unknown")] += float(event.pnl_normalized or 0.0)
        decision_quality = _decision_quality_breakdown(events)
        perf_payload = {
            "drawdown": round(drawdown, 6),
            "pnl_by_regime": {key: round(value, 6) for key, value in pnl_by_regime.items()},
            "decision_quality_breakdown": decision_quality,
            "false_allow_trend": {"count": false_allow_count, "rate": round(false_allow_rate, 4)},
            "false_reject_trend": {"count": false_reject_count, "rate": round(false_reject_rate, 4)},
            "rolling_windows": _rolling_window_summary(events),
            "drift": _decay_and_drift(events),
            "sample_count": sample,
            "cross_strategy": _cross_strategy_correlation(events),
        }

        db.add(
            StrategyOutcomeMemory(
                id=str(uuid.uuid4()),
                strategy_id=strategy_id,
                direction=direction,
                regime=regime,
                sample_count=sample,
                hit_rate=round(hit_rate, 4),
                avg_return=round(avg_return, 6),
                avg_mfe=round(avg_mfe, 6),
                avg_mae=round(avg_mae, 6),
                false_allow_rate=round(false_allow_rate, 4),
                false_reject_rate=round(false_reject_rate, 4),
                recent_rolling_score=round(rolling, 4),
                decay_adjusted_quality_score=round(decay_quality, 4),
            )
        )

        if sample >= 8:
            if decay_quality < 15:
                rec = LearningRecommendation(
                    id=str(uuid.uuid4()),
                    strategy_id=strategy_id,
                    family=None,
                    recommendation_type="strategy_disable",
                    recommendation_value={
                        "suggested_is_enabled": False,
                        "scope": "strategy",
                        "reason": "quality score critically low",
                        "confidence": round(min(0.6 + abs(decay_quality) / 100.0, 0.95), 6),
                        "evidence_summary": perf_payload,
                        "risk_impact": {"tail_impact": round(abs(avg_mae), 6), "cluster_impact": round(false_allow_rate / 100.0, 6), "capital_impact": round(abs(drawdown), 6)},
                    },
                    note="quality score critically low, disable önerisi",
                    severity="high",
                )
                _enrich_recommendation_payload(rec)
                recommendations.append(
                    rec
                )
            elif false_allow_rate > 45:
                rec = LearningRecommendation(
                    id=str(uuid.uuid4()),
                    strategy_id=strategy_id,
                    family=None,
                    recommendation_type="strategy_weight_down",
                    recommendation_value={
                        "suggested_weight_multiplier": 0.7,
                        "scope": "strategy",
                        "reason": "false allow trend yüksek",
                        "confidence": round(min(0.55 + false_allow_rate / 100.0, 0.95), 6),
                        "evidence_summary": perf_payload,
                        "risk_impact": {"tail_impact": round(abs(avg_mae), 6), "cluster_impact": round(false_allow_rate / 100.0, 6), "capital_impact": round(abs(drawdown), 6)},
                    },
                    note="false allow trend yüksek, throttle önerisi",
                    severity="medium",
                )
                _enrich_recommendation_payload(rec)
                recommendations.append(
                    rec
                )
            elif decay_quality > 70:
                rec = LearningRecommendation(
                    id=str(uuid.uuid4()),
                    strategy_id=strategy_id,
                    family=None,
                    recommendation_type="strategy_weight_up",
                    recommendation_value={
                        "suggested_weight_multiplier": 1.1,
                        "scope": "strategy",
                        "reason": "son dönem kalite yüksek",
                        "confidence": round(min(0.55 + decay_quality / 100.0, 0.95), 6),
                        "evidence_summary": perf_payload,
                        "risk_impact": {"tail_impact": round(abs(avg_mae), 6), "cluster_impact": round(false_allow_rate / 100.0, 6), "capital_impact": round(abs(drawdown), 6)},
                    },
                    note="son dönem kalite yüksek, sınırlı weight artırımı önerisi",
                    severity="low",
                )
                _enrich_recommendation_payload(rec)
                recommendations.append(
                    rec
                )
            if sample >= 12 and abs(avg_mae) > 0.01:
                rec = LearningRecommendation(
                    id=str(uuid.uuid4()),
                    strategy_id=strategy_id,
                    family=None,
                    recommendation_type="threshold_tune",
                    recommendation_value={
                        "suggested_threshold_delta": -0.05 if avg_mae < -0.01 else 0.03,
                        "scope": "strategy",
                        "reason": "mae/pnl profilinde threshold tune ihtiyacı",
                        "confidence": round(min(0.5 + sample / 100.0, 0.9), 6),
                        "evidence_summary": perf_payload,
                        "risk_impact": {"tail_impact": round(abs(avg_mae), 6), "cluster_impact": round(false_allow_rate / 100.0, 6), "capital_impact": round(abs(drawdown), 6)},
                    },
                    note="threshold tune recommendation",
                    severity="medium",
                )
                _enrich_recommendation_payload(rec)
                recommendations.append(rec)

    for (family, regime), events in family_buckets.items():
        sample = len(events)
        closed = [e for e in events if e.outcome_label in {"WIN", "LOSS", "BREAKEVEN"}]
        wins = [e for e in closed if e.outcome_label == "WIN"]
        hit_rate = (len(wins) / len(closed) * 100) if closed else 0.0
        avg_return = (sum(e.pnl_normalized for e in closed) / len(closed)) if closed else 0.0
        volatility_success = (len([e for e in events if e.tp_hit]) / sample * 100) if sample else 0.0
        conflict_success = (len([e for e in events if e.decision in {"BLOCKED", "NO_TRADE"}]) / sample * 100) if sample else 0.0
        solo = len([e for e in events if len(e.source_strategies or []) <= 1])
        combo = len([e for e in events if len(e.source_strategies or []) > 1])
        db.add(
            FamilyOutcomeMemory(
                id=str(uuid.uuid4()),
                family=family,
                regime=regime,
                sample_count=sample,
                hit_rate=round(hit_rate, 4),
                avg_return=round(avg_return, 6),
                volatility_success=round(volatility_success, 4),
                conflict_success=round(conflict_success, 4),
                solo_vs_combo_success={"solo_samples": solo, "combo_samples": combo},
            )
        )

    for recommendation in recommendations:
        _ensure_recommendation_defaults(recommendation)
        db.add(recommendation)

    for family, events in family_buckets.items():
        if len(events) < 10:
            continue
        rolling = _rolling_window_summary(events)
        drift = _decay_and_drift(events)
        family_conflict = len([e for e in events if _false_flags(e.outcome_label, e.decision)[0]]) / max(len(events), 1)
        if drift["actionability_flag"] or family_conflict > 0.25:
            rec = LearningRecommendation(
                id=str(uuid.uuid4()),
                strategy_id=None,
                family=family,
                recommendation_type="family_weight_down",
                recommendation_value={
                    "suggested_weight_multiplier": 0.85,
                    "scope": "family",
                    "reason": "family rolling window decay / regime drift tespit edildi",
                    "confidence": round(min(0.55 + family_conflict, 0.92), 6),
                    "evidence_summary": {"rolling_windows": rolling, "drift": drift},
                    "risk_impact": {
                        "tail_impact": round(abs(rolling.get("30d", {}).get("drawdown", 0.0)), 6),
                        "cluster_impact": round(family_conflict, 6),
                        "capital_impact": round(abs(rolling.get("30d", {}).get("avg_return", 0.0)), 6),
                    },
                    "symbol_cluster": sorted({str(e.symbol or "unknown") for e in events[:20]}),
                    "regime": Counter(_canonical_regime(e.regime_snapshot) for e in events).most_common(1)[0][0],
                    "scope_reason": "family/regime performans bozulması çapraz strateji etkisi gösteriyor",
                    "cross_strategy": _cross_strategy_correlation(events),
                },
                note="family/regime drift recommendation",
                severity="medium",
            )
            _enrich_recommendation_payload(rec)
            db.add(rec)
    db.commit()

    trade_linked = len([row for row in recent_events if row.position_id])
    blocked_rejected = len([row for row in recent_events if row.outcome_label in {"REJECTED", "RISK_BLOCKED", "NO_TRADE", "MANUAL_CANCELLED"}])
    strategies_covered = sorted({str(row.strategy_id or "unknown") for row in recent_events})

    return {
        "schema_version": LEARNING_SCHEMA_VERSION,
        "engine_version": LEARNING_ENGINE_VERSION_V15,
        "generated_at": datetime.now(timezone.utc),
        "window_days": window_days,
        "events_count": len(recent_events),
        "strategy_memory_count": len(strategy_buckets),
        "family_memory_count": len(family_buckets),
        "recommendation_count": len(recommendations),
        "backfill": {
            "events_generated": len(recent_events),
            "trade_linked": trade_linked,
            "blocked_or_rejected": blocked_rejected,
            "strategies_covered": strategies_covered,
        },
    }


def get_learning_overview(db: Session) -> dict:
    _ensure_learning_tables(db)
    strategy_rows = db.query(StrategyOutcomeMemory).order_by(StrategyOutcomeMemory.decay_adjusted_quality_score.desc()).limit(300).all()
    family_rows = db.query(FamilyOutcomeMemory).order_by(FamilyOutcomeMemory.sample_count.desc()).limit(120).all()
    recommendation_rows = (
        db.query(LearningRecommendation)
        .order_by(LearningRecommendation.created_at.desc())
        .limit(120)
        .all()
    )

    recommendation_lookup: dict[str, list[dict]] = defaultdict(list)
    for row in recommendation_rows:
        key = str(row.strategy_id or "")
        enriched_payload = _enrich_recommendation_payload(row)
        if key:
            recommendation_lookup[key].append(
                {
                    "recommendation_type": row.recommendation_type,
                    "severity": row.severity,
                    "note": row.note,
                    "created_at": row.created_at,
                    "actionable_state": enriched_payload.get("actionable_state"),
                    "recommendation_score": enriched_payload.get("recommendation_score"),
                }
            )

    event_rows = db.query(LearningDecisionEvent).order_by(LearningDecisionEvent.created_at.desc()).limit(3000).all()
    strategy_perf = defaultdict(lambda: {"drawdown": 0.0, "pnl_by_regime": defaultdict(float), "events": []})
    for event in reversed(event_rows):
        key = str(event.strategy_id or "unknown")
        bucket = strategy_perf[key]
        bucket["events"].append(event)
        regime_key = _canonical_regime(event.regime_snapshot)
        bucket["pnl_by_regime"][regime_key] += float(event.pnl_normalized or 0.0)
    strategy_perf_resolved = {}
    for strategy_id, payload in strategy_perf.items():
        cumulative = 0.0
        peak = 0.0
        drawdown = 0.0
        for event in payload["events"]:
            cumulative += float(event.pnl_normalized or 0.0)
            peak = max(peak, cumulative)
            drawdown = min(drawdown, cumulative - peak)
        strategy_perf_resolved[strategy_id] = {
            "drawdown": round(drawdown, 6),
            "pnl_by_regime": {key: round(value, 6) for key, value in payload["pnl_by_regime"].items()},
            "decision_quality_breakdown": _decision_quality_breakdown(payload["events"]),
            "false_allow_trend": {
                "count": len([e for e in payload["events"] if _false_flags(e.outcome_label, e.decision)[0]]),
            },
            "false_reject_trend": {
                "count": len([e for e in payload["events"] if _false_flags(e.outcome_label, e.decision)[1]]),
            },
            **_decay_and_drift(payload["events"]),
        }

    return {
        "schema_version": LEARNING_SCHEMA_VERSION,
        "engine_version": LEARNING_ENGINE_VERSION,
        "generated_at": datetime.now(timezone.utc),
        "guardrails": {
            "auto_change_forbidden": True,
            "admin_approval_required": True,
            "audit_log_enabled": True,
        },
        "strategy_memory": [
            {
                "strategy_id": row.strategy_id,
                "direction": row.direction,
                "regime": row.regime,
                "sample_count": row.sample_count,
                "hit_rate": row.hit_rate,
                "avg_return": row.avg_return,
                "avg_mfe": row.avg_mfe,
                "avg_mae": row.avg_mae,
                "false_allow_rate": row.false_allow_rate,
                "false_reject_rate": row.false_reject_rate,
                "rolling_quality_score": row.recent_rolling_score,
                "decay_adjusted_score": row.decay_adjusted_quality_score,
                "recent_rolling_score": row.recent_rolling_score,
                "decay_adjusted_quality_score": row.decay_adjusted_quality_score,
                "quality_degradation_flag": _quality_degradation_flag(row.decay_adjusted_quality_score),
                "drawdown": _safe_float((strategy_perf_resolved.get(str(row.strategy_id)) or {}).get("drawdown"), 0.0),
                "pnl_by_regime": ((strategy_perf_resolved.get(str(row.strategy_id)) or {}).get("pnl_by_regime")) or {},
                "decision_quality_breakdown": ((strategy_perf_resolved.get(str(row.strategy_id)) or {}).get("decision_quality_breakdown")) or {},
                "false_allow_trend": ((strategy_perf_resolved.get(str(row.strategy_id)) or {}).get("false_allow_trend")) or {},
                "false_reject_trend": ((strategy_perf_resolved.get(str(row.strategy_id)) or {}).get("false_reject_trend")) or {},
                "rolling_windows": ((strategy_perf_resolved.get(str(row.strategy_id)) or {}).get("rolling_windows")) or {},
                "decay_score": _safe_float((strategy_perf_resolved.get(str(row.strategy_id)) or {}).get("decay_score"), 0.0),
                "regime_drift_flag": bool((strategy_perf_resolved.get(str(row.strategy_id)) or {}).get("regime_drift_flag", False)),
                "confidence_degradation": _safe_float((strategy_perf_resolved.get(str(row.strategy_id)) or {}).get("confidence_degradation"), 0.0),
                "actionability_flag": bool((strategy_perf_resolved.get(str(row.strategy_id)) or {}).get("actionability_flag", False)),
                "window_comparison": ((strategy_perf_resolved.get(str(row.strategy_id)) or {}).get("window_comparison")) or {},
                "stability_score": _safe_float((strategy_perf_resolved.get(str(row.strategy_id)) or {}).get("stability_score"), 0.0),
                "drift_confidence": _safe_float((strategy_perf_resolved.get(str(row.strategy_id)) or {}).get("drift_confidence"), 0.0),
                "recent_performance": {
                    "hit_rate": row.hit_rate,
                    "avg_return": row.avg_return,
                },
                "recommendation": (recommendation_lookup.get(str(row.strategy_id)) or [None])[0],
                "updated_at": row.updated_at,
            }
            for row in strategy_rows
        ],
        "family_memory": [
            {
                "family": row.family,
                "regime": row.regime,
                "sample_count": row.sample_count,
                "hit_rate": row.hit_rate,
                "avg_return": row.avg_return,
                "volatility_success": row.volatility_success,
                "conflict_success": row.conflict_success,
                "solo_vs_combo_success": row.solo_vs_combo_success,
                "updated_at": row.updated_at,
            }
            for row in family_rows
        ],
        "recommendations": [
            {
                "id": row.id,
                "strategy_id": row.strategy_id,
                "family": row.family,
                "recommendation_type": row.recommendation_type,
                "recommendation_value": row.recommendation_value,
                "note": row.note,
                "severity": row.severity,
                "is_applied": row.is_applied,
                "reason": _enrich_recommendation_payload(row).get("reason"),
                "confidence": _enrich_recommendation_payload(row).get("confidence"),
                "evidence_summary": _enrich_recommendation_payload(row).get("evidence_summary"),
                "recommendation_scope": _enrich_recommendation_payload(row).get("scope"),
                "risk_impact": _enrich_recommendation_payload(row).get("risk_impact"),
                "lifecycle": _enrich_recommendation_payload(row).get("lifecycle"),
                "status_history": _enrich_recommendation_payload(row).get("status_history"),
                "version": _enrich_recommendation_payload(row).get("version"),
                "actionable_state": _enrich_recommendation_payload(row).get("actionable_state"),
                "recommendation_score": _enrich_recommendation_payload(row).get("recommendation_score"),
                "decision_candidate": _enrich_recommendation_payload(row).get("decision_candidate"),
                "auto_apply_eligible": _enrich_recommendation_payload(row).get("auto_apply_eligible"),
                "scope_reason": _enrich_recommendation_payload(row).get("scope_reason"),
                "cross_strategy_correlation": _enrich_recommendation_payload(row).get("cross_strategy_correlation"),
                "created_at": row.created_at,
                "applied_at": row.applied_at,
                "admin_approval_required": True,
            }
            for row in recommendation_rows
        ],
        "events": list_learning_events(db, limit=200),
        "adaptive_summary": {
            "affected_strategies": [
                row.strategy_id
                for row in strategy_rows
                if bool((strategy_perf_resolved.get(str(row.strategy_id)) or {}).get("regime_drift_flag", False))
            ],
        },
    }


def list_learning_events(db: Session, *, limit: int = 200) -> list[dict]:
    _ensure_learning_tables(db)
    rows = (
        db.query(LearningDecisionEvent)
        .order_by(LearningDecisionEvent.created_at.desc())
        .limit(max(1, min(limit, 1000)))
        .all()
    )
    events: list[dict] = []
    for row in rows:
        false_allow, false_reject = _false_flags(row.outcome_label, row.decision)
        events.append(
            {
                "event_id": row.id,
                "signal": _canonical_signal(None, {"final_decision": row.decision}),
                "symbol": row.symbol,
                "decision": row.decision,
                "outcome": row.outcome_label,
                "pnl_norm": row.pnl_normalized,
                "mfe": row.max_favorable_excursion,
                "mae": row.max_adverse_excursion,
                "false_allow": false_allow,
                "false_reject": false_reject,
                "regime": _canonical_regime(row.regime_snapshot),
                "strategy_id": row.strategy_id,
                "strategies": list(row.source_strategies or []),
                "families": row.family_scores or {},
                "regime_snapshot": row.regime_snapshot or {},
                "risk_snapshot": row.risk_snapshot or {},
                "entry_price": row.entry_price,
                "exit_price": row.exit_price,
                "max_favorable_excursion": row.max_favorable_excursion,
                "max_adverse_excursion": row.max_adverse_excursion,
                "hold_duration": row.hold_duration_minutes,
                "hold_duration_minutes": row.hold_duration_minutes,
                "outcome_label": row.outcome_label,
                "pnl_normalized": row.pnl_normalized,
                "stop_hit": row.stop_hit,
                "tp_hit": row.tp_hit,
                "invalidated": row.invalidated,
                "created_at": row.created_at,
                "closed_at": row.closed_at,
            }
        )
    return events


def strategy_quality_lookup(db: Session) -> dict[str, dict]:
    _ensure_learning_tables(db)
    rows = db.query(StrategyOutcomeMemory).all()
    lookup: dict[str, dict] = {}
    for row in rows:
        current = lookup.get(row.strategy_id)
        if current is None or row.sample_count > current.get("sample_count", -1):
            lookup[row.strategy_id] = {
                "sample_count": row.sample_count,
                "quality_score": row.decay_adjusted_quality_score,
                "false_allow_rate": row.false_allow_rate,
                "recent_rolling_score": row.recent_rolling_score,
            }
    return lookup


def strategy_recommendation_lookup(db: Session) -> dict[str, list[dict]]:
    _ensure_learning_tables(db)
    rows = (
        db.query(LearningRecommendation)
        .filter(LearningRecommendation.strategy_id.isnot(None), LearningRecommendation.is_applied.is_(False))
        .order_by(LearningRecommendation.created_at.desc())
        .all()
    )
    lookup: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        lookup[str(row.strategy_id)].append(
            {
                "recommendation_type": row.recommendation_type,
                "recommendation_value": row.recommendation_value,
                "severity": row.severity,
                "note": row.note,
            }
        )
    return dict(lookup)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))


def _gate_decision_from_risk(risk_score: float) -> str:
    if risk_score < 0.35:
        return "ALLOW"
    if risk_score < 0.55:
        return "ADJUST_POSITION"
    if risk_score < 0.75:
        return "REQUIRE_APPROVAL"
    return "REJECT"


def _find_strategy_memory(db: Session, strategy_id: str) -> StrategyOutcomeMemory | None:
    return (
        db.query(StrategyOutcomeMemory)
        .filter(StrategyOutcomeMemory.strategy_id == strategy_id)
        .order_by(StrategyOutcomeMemory.sample_count.desc(), StrategyOutcomeMemory.updated_at.desc())
        .first()
    )


def _find_family_memory(db: Session, family: str) -> FamilyOutcomeMemory | None:
    return (
        db.query(FamilyOutcomeMemory)
        .filter(FamilyOutcomeMemory.family == family)
        .order_by(FamilyOutcomeMemory.sample_count.desc(), FamilyOutcomeMemory.updated_at.desc())
        .first()
    )


def simulate_learning_recommendation_impact(
    db: Session,
    *,
    strategy_id: str | None,
    strategy_ids: list[str] | None = None,
    family: str | None,
    symbol_cluster: list[str] | None = None,
    scenario: str = "base",
    recommendation_type: str,
    suggested_weight_multiplier: float | None = None,
) -> dict:
    _ensure_learning_tables(db)
    normalized_strategy = str(strategy_id or "").strip() or None
    normalized_strategy_ids = [str(item).strip() for item in (strategy_ids or []) if str(item).strip()]
    normalized_family = str(family or "").strip() or None
    normalized_cluster = [str(item).upper().strip() for item in (symbol_cluster or []) if str(item).strip()]
    normalized_scenario = str(scenario or "base").strip().lower()
    rec_type = str(recommendation_type or "decrease_weight_recommendation")

    strategy_row = _find_strategy_memory(db, normalized_strategy) if normalized_strategy else None
    family_row = _find_family_memory(db, normalized_family) if normalized_family else None
    scope = "portfolio" if len(normalized_strategy_ids) > 1 else "symbol_cluster" if normalized_cluster else "strategy" if strategy_row else "family" if family_row else "global"

    baseline_hit_rate = float(strategy_row.hit_rate if strategy_row else family_row.hit_rate if family_row else 52.0)
    baseline_avg_return = float(strategy_row.avg_return if strategy_row else family_row.avg_return if family_row else 0.001)
    baseline_false_allow = float(strategy_row.false_allow_rate if strategy_row else 25.0)
    baseline_quality = float(strategy_row.decay_adjusted_quality_score if strategy_row else 45.0)
    baseline_conflict = float(family_row.conflict_success if family_row else 20.0)

    base_risk_score = _clamp((baseline_false_allow / 100.0) * 0.55 + ((100.0 - _clamp(baseline_quality, 0, 100)) / 100.0) * 0.45, 0.0, 1.0)
    if family_row and not strategy_row:
        base_risk_score = _clamp((100.0 - baseline_hit_rate) / 100.0 * 0.6 + (baseline_conflict / 100.0) * 0.4, 0.0, 1.0)

    weight_multiplier = float(suggested_weight_multiplier or 1.0)
    risk_delta = 0.0
    expected_hit_rate_delta = 0.0
    expected_avg_return_delta = 0.0
    allocation_drift_delta = 0.0
    hedge_effect_score = 0.5

    if rec_type == "disable_recommendation":
        expected_hit_rate_delta = 0.7 if baseline_quality < 25 else -0.2
        expected_avg_return_delta = 0.001 if baseline_avg_return < 0 else -0.0003
        risk_delta = -0.18
        allocation_drift_delta = -0.24
        hedge_effect_score = 0.74
    elif rec_type in {"decrease_weight_recommendation", "auto_throttle_recommendation"}:
        intensity = _clamp(1.0 - weight_multiplier, 0.0, 0.9)
        expected_hit_rate_delta = 0.5 + (intensity * 2.1)
        expected_avg_return_delta = 0.0004 + (intensity * 0.0014)
        risk_delta = -(0.05 + (intensity * 0.2))
        allocation_drift_delta = -(0.03 + (intensity * 0.17))
        hedge_effect_score = 0.56 + (intensity * 0.25)
    elif rec_type in {"increase_weight_recommendation", "weight_boost_recommendation"}:
        intensity = _clamp(weight_multiplier - 1.0, 0.0, 1.0)
        expected_hit_rate_delta = 0.3 + (intensity * 1.4)
        expected_avg_return_delta = 0.0006 + (intensity * 0.0019)
        risk_delta = 0.05 + (intensity * 0.15)
        allocation_drift_delta = 0.04 + (intensity * 0.11)
        hedge_effect_score = 0.46 - (intensity * 0.08)

    if scope == "family":
        expected_hit_rate_delta += _clamp((50.0 - baseline_conflict) / 100.0, -0.4, 0.6)
        expected_avg_return_delta += _clamp((float(family_row.volatility_success if family_row else 40.0) - 40.0) / 100000.0, -0.0005, 0.0008)

    scenario_multiplier = {
        "base": {"risk": 1.0, "return": 1.0, "capital": 1.0},
        "stressed": {"risk": 1.35, "return": 0.72, "capital": 1.2},
        "high_volatility": {"risk": 1.25, "return": 0.82, "capital": 1.12},
        "low_liquidity": {"risk": 1.15, "return": 0.88, "capital": 1.18},
    }.get(normalized_scenario, {"risk": 1.0, "return": 1.0, "capital": 1.0})

    projected_risk_score = _clamp(base_risk_score + risk_delta, 0.0, 1.0)

    query = db.query(LearningDecisionEvent)
    if normalized_strategy_ids:
        query = query.filter(LearningDecisionEvent.strategy_id.in_(normalized_strategy_ids))
    elif normalized_strategy:
        query = query.filter(LearningDecisionEvent.strategy_id == normalized_strategy)
    if normalized_family:
        query = query.filter(LearningDecisionEvent.strategy_family == normalized_family)
    if normalized_cluster:
        query = query.filter(LearningDecisionEvent.symbol.in_(normalized_cluster))
    sample_rows = query.order_by(LearningDecisionEvent.created_at.desc()).limit(400).all()
    replay_sample = [row for row in sample_rows if row.outcome_label in {"WIN", "LOSS", "BREAKEVEN"}]
    coverage = max(len(sample_rows), 1)
    per_strategy = defaultdict(list)
    for row in replay_sample:
        per_strategy[str(row.strategy_id or "unknown")].append(row)
    interaction_effects = {
        "correlation_impact": round(_cross_strategy_correlation(replay_sample).get("cross_strategy_correlation"), 6),
        "conflict_detection": round(len([row for row in sample_rows if str(row.decision or "") in {"BLOCKED", "NO_TRADE"}]) / coverage, 6),
        "capital_contention": round(max(len(per_strategy) - 1, 0) / max(len(sample_rows), 1) * 10, 6),
        "strategy_count": len(per_strategy),
    }
    projected_hit_rate = (baseline_hit_rate + expected_hit_rate_delta) * scenario_multiplier["return"]
    projected_avg_return = (baseline_avg_return + expected_avg_return_delta) * scenario_multiplier["return"]
    projected_drawdown = max(0.0, abs(base_risk_score + risk_delta) * 0.12 * scenario_multiplier["risk"])
    projected_capital_usage_delta = _clamp(allocation_drift_delta * 0.8 * scenario_multiplier["capital"], -1.0, 1.0)
    concentration_delta = _clamp(((weight_multiplier - 1.0) * 0.4) + interaction_effects["correlation_impact"] * 0.3, -1.0, 1.0)
    exposure_delta = round((len(normalized_strategy_ids) or (1 if normalized_strategy else 0) or 1) * 0.04 * scenario_multiplier["capital"], 6)
    tail_impact = round(abs(projected_drawdown) * 0.8, 6)
    cluster_impact = round(abs(concentration_delta) * 0.7 + interaction_effects["correlation_impact"] * 0.2, 6)
    capital_impact = round(abs(projected_capital_usage_delta) * 0.6, 6)
    baseline_metrics = {
        "hit_rate": round(baseline_hit_rate, 6),
        "avg_return": round(baseline_avg_return, 8),
        "drawdown": round(abs(base_risk_score) * 0.1, 6),
        "risk_score": round(base_risk_score, 6),
    }
    projected_metrics = {
        "hit_rate": round(projected_hit_rate, 6),
        "avg_return": round(projected_avg_return, 8),
        "drawdown": round(projected_drawdown, 6),
        "risk_score": round(projected_risk_score, 6),
    }
    delta_metrics = {
        "hit_rate_delta": round(projected_metrics["hit_rate"] - baseline_metrics["hit_rate"], 6),
        "avg_return_delta": round(projected_metrics["avg_return"] - baseline_metrics["avg_return"], 8),
        "drawdown_delta": round(projected_metrics["drawdown"] - baseline_metrics["drawdown"], 6),
        "risk_delta": round(projected_metrics["risk_score"] - baseline_metrics["risk_score"], 6),
    }
    sample_coverage = {
        "sample_size": len(sample_rows),
        "trade_linked": len(replay_sample),
        "coverage_ratio": round(len(replay_sample) / coverage, 6),
        "reliability_score": round(max(0.0, min(1.0, (len(replay_sample) / max(25, coverage)) + 0.35 - interaction_effects["conflict_detection"])), 6),
    }

    return {
        "schema_version": LEARNING_SCHEMA_VERSION,
        "engine_version": "learning-impact-simulator.v1.5",
        "simulated_at": datetime.now(timezone.utc),
        "scope": scope,
        "strategy_id": normalized_strategy,
        "strategy_ids": normalized_strategy_ids,
        "family": normalized_family,
        "symbol_cluster": normalized_cluster,
        "scenario": normalized_scenario,
        "recommendation_type": rec_type,
        "read_only": True,
        "projected_risk_score": round(projected_risk_score, 6),
        "projected_gate_decision": _gate_decision_from_risk(projected_risk_score),
        "expected_hit_rate_delta": round(expected_hit_rate_delta, 6),
        "expected_avg_return_delta": round(expected_avg_return_delta, 8),
        "allocation_drift_delta": round(allocation_drift_delta, 6),
        "hedge_effect_score": round(_clamp(hedge_effect_score, 0.0, 1.0), 6),
        "baseline_metrics": baseline_metrics,
        "projected_metrics": projected_metrics,
        "delta_metrics": delta_metrics,
        "sample_coverage": sample_coverage,
        "counterfactual_replay": {
            "baseline_vs_projected": {
                "hit_rate": {"baseline": baseline_metrics["hit_rate"], "projected": projected_metrics["hit_rate"]},
                "avg_return": {"baseline": baseline_metrics["avg_return"], "projected": projected_metrics["avg_return"]},
                "drawdown": {"baseline": baseline_metrics["drawdown"], "projected": projected_metrics["drawdown"]},
            },
            "sample_coverage": sample_coverage,
        },
        "portfolio_impact": {
            "net_pnl_delta": round(expected_avg_return_delta * max(len(replay_sample), 1), 8),
            "drawdown_delta": round(projected_drawdown - abs(base_risk_score) * 0.1, 6),
            "capital_usage_delta": round(projected_capital_usage_delta, 6),
            "exposure_delta": exposure_delta,
            "concentration_delta": round(concentration_delta, 6),
        },
        "risk_aware_view": {
            "tail_impact": tail_impact,
            "cluster_impact": cluster_impact,
            "capital_impact": capital_impact,
            "actionability_flag": bool(projected_risk_score < 0.75),
        },
        "interaction_effects": interaction_effects,
        "baseline": {
            "hit_rate": round(baseline_hit_rate, 6),
            "avg_return": round(baseline_avg_return, 8),
            "false_allow_rate": round(baseline_false_allow, 6),
            "quality_score": round(baseline_quality, 6),
            "conflict_success": round(baseline_conflict, 6),
            "base_risk_score": round(base_risk_score, 6),
            "weight_multiplier": round(weight_multiplier, 6),
        },
        "assumptions": [
            "read-only simulation: no production rule changed",
            "allocation and hedge impact are replay-assisted model estimates",
            "apply action requires explicit admin approval",
        ],
    }


def simulate_recommendation_row_impact(db: Session, *, recommendation: LearningRecommendation) -> dict:
    rec_value = recommendation.recommendation_value or {}
    return simulate_learning_recommendation_impact(
        db,
        strategy_id=recommendation.strategy_id,
        family=recommendation.family,
        recommendation_type=recommendation.recommendation_type,
        suggested_weight_multiplier=rec_value.get("suggested_weight_multiplier"),
    )


def _append_status_history(payload: dict, *, state: str, actor: str, reason: str, version_ref: str | None, before_payload: dict | None = None, after_payload: dict | None = None) -> dict:
    next_payload = dict(payload or {})
    history = list(next_payload.get("status_history") or [])
    history.append(
        {
            "state": state,
            "actor": actor,
            "timestamp": _utcnow().isoformat(),
            "reason": reason,
            "version_ref": version_ref,
            "before_payload": before_payload or {},
            "after_payload": after_payload or {},
        }
    )
    next_payload["status_history"] = history
    next_payload["lifecycle"] = state
    return next_payload


def _recommendation_by_id(db: Session, recommendation_id: str) -> LearningRecommendation | None:
    return db.query(LearningRecommendation).filter(LearningRecommendation.id == recommendation_id).first()


def _monitoring_windows() -> list[tuple[str, timedelta]]:
    return [("1h", timedelta(hours=1)), ("24h", timedelta(hours=24)), ("7d", timedelta(days=7))]


def _event_scope_filter(rows: list[LearningDecisionEvent], recommendation: LearningRecommendation) -> list[LearningDecisionEvent]:
    if recommendation.strategy_id:
        return [row for row in rows if str(row.strategy_id or "") == str(recommendation.strategy_id)]
    if recommendation.family:
        return [row for row in rows if str(row.strategy_family or "") == str(recommendation.family)]
    return rows


def _window_metrics(rows: list[LearningDecisionEvent]) -> dict:
    sample = len(rows)
    closed = [row for row in rows if str(row.outcome_label or "") in {"WIN", "LOSS", "BREAKEVEN"}]
    wins = [row for row in closed if str(row.outcome_label or "") == "WIN"]
    avg_return = sum(float(row.pnl_normalized or 0.0) for row in closed) / len(closed) if closed else 0.0
    cumulative = 0.0
    peak = 0.0
    drawdown = 0.0
    for row in closed:
        cumulative += float(row.pnl_normalized or 0.0)
        peak = max(peak, cumulative)
        drawdown = min(drawdown, cumulative - peak)
    return {
        "sample_count": sample,
        "hit_rate": round((len(wins) / len(closed) * 100) if closed else 0.0, 6),
        "avg_return": round(avg_return, 8),
        "drawdown": round(drawdown, 6),
        "false_allow_rate": round((len([row for row in rows if _false_flags(row.outcome_label, row.decision)[0]]) / max(sample, 1) * 100), 6),
        "false_reject_rate": round((len([row for row in rows if _false_flags(row.outcome_label, row.decision)[1]]) / max(sample, 1) * 100), 6),
    }


def _current_version_ref(payload: dict, recommendation_id: str) -> str:
    version = dict((payload or {}).get("version") or {})
    return str(version.get("current_version") or f"learning-rec-{recommendation_id[:8]}")


def approve_learning_recommendation(db: Session, *, recommendation_id: str, actor: str, reason: str) -> dict:
    recommendation = _recommendation_by_id(db, recommendation_id)
    if recommendation is None:
        raise ValueError("learning_recommendation_not_found")
    payload = _ensure_recommendation_defaults(recommendation)
    version_ref = _current_version_ref(payload, recommendation.id)
    before_payload = dict(payload)
    payload = _append_status_history(payload, state="approved", actor=actor, reason=reason, version_ref=version_ref, before_payload=before_payload, after_payload={"approved": True})
    recommendation.recommendation_value = payload
    db.commit()
    db.refresh(recommendation)
    return serialize_learning_recommendation(recommendation)


def reject_learning_recommendation(db: Session, *, recommendation_id: str, actor: str, reason: str) -> dict:
    recommendation = _recommendation_by_id(db, recommendation_id)
    if recommendation is None:
        raise ValueError("learning_recommendation_not_found")
    payload = _ensure_recommendation_defaults(recommendation)
    version_ref = _current_version_ref(payload, recommendation.id)
    before_payload = dict(payload)
    payload = _append_status_history(payload, state="rejected", actor=actor, reason=reason, version_ref=version_ref, before_payload=before_payload, after_payload={"rejected": True})
    recommendation.recommendation_value = payload
    db.commit()
    db.refresh(recommendation)
    return serialize_learning_recommendation(recommendation)


def _apply_recommendation_change(db: Session, recommendation: LearningRecommendation) -> tuple[dict, dict, str | None]:
    before_payload = {}
    after_payload = {}
    version_ref = None
    rec_value = dict(recommendation.recommendation_value or {})
    rec_type = str(recommendation.recommendation_type or "")
    if recommendation.strategy_id:
        strategy = db.query(CanonicalStrategyRegistry).filter(CanonicalStrategyRegistry.strategy_id == recommendation.strategy_id).first()
        if strategy is None:
            raise ValueError("strategy_not_found_for_recommendation")
        before_payload = {
            "strategy_id": strategy.strategy_id,
            "is_enabled": bool(strategy.is_enabled),
            "weight": float(strategy.weight or 0.0),
            "entry_long": dict(strategy.entry_long or {}),
            "entry_short": dict(strategy.entry_short or {}),
        }
        if rec_type in {"strategy_disable", "strategy_disable_suggestion", "disable_recommendation"}:
            strategy.is_enabled = bool(rec_value.get("suggested_is_enabled", False))
        elif rec_type in {"strategy_weight_down", "strategy_weight_decrease_recommendation", "decrease_weight_recommendation", "auto_throttle_recommendation"}:
            strategy.weight = max(0.0, round(float(strategy.weight or 1.0) * float(rec_value.get("suggested_weight_multiplier", 1.0)), 4))
        elif rec_type in {"strategy_weight_up", "strategy_weight_increase_recommendation", "increase_weight_recommendation", "weight_boost_recommendation"}:
            strategy.weight = max(0.0, round(float(strategy.weight or 1.0) * float(rec_value.get("suggested_weight_multiplier", 1.0)), 4))
        elif rec_type in {"threshold_tune", "threshold_tune_recommendation"}:
            threshold_delta = float(rec_value.get("suggested_threshold_delta") or 0.0)
            entry_long = dict(strategy.entry_long or {})
            entry_short = dict(strategy.entry_short or {})
            entry_long["adaptive_threshold_delta"] = round(float(entry_long.get("adaptive_threshold_delta") or 0.0) + threshold_delta, 6)
            entry_short["adaptive_threshold_delta"] = round(float(entry_short.get("adaptive_threshold_delta") or 0.0) + threshold_delta, 6)
            strategy.entry_long = entry_long
            strategy.entry_short = entry_short
        after_payload = {
            "strategy_id": strategy.strategy_id,
            "is_enabled": bool(strategy.is_enabled),
            "weight": float(strategy.weight or 0.0),
            "entry_long": dict(strategy.entry_long or {}),
            "entry_short": dict(strategy.entry_short or {}),
        }
        version_ref = f"strategy:{strategy.strategy_id}:{_utcnow().strftime('%Y%m%d%H%M%S')}"
    return before_payload, after_payload, version_ref


def _build_post_change_monitoring(db: Session, *, recommendation: LearningRecommendation, since_at: datetime) -> dict:
    rows = db.query(LearningDecisionEvent).filter(LearningDecisionEvent.created_at >= since_at - timedelta(days=7)).all()
    scoped = _event_scope_filter(rows, recommendation)
    baseline_rows = [row for row in scoped if row.created_at < since_at]
    baseline_metrics = _window_metrics(baseline_rows)
    windows = {}
    for label, delta in _monitoring_windows():
        current_rows = [row for row in scoped if row.created_at >= since_at and row.created_at <= since_at + delta]
        current_metrics = _window_metrics(current_rows)
        deterioration = current_metrics["avg_return"] < baseline_metrics["avg_return"] or current_metrics["drawdown"] < baseline_metrics["drawdown"]
        windows[label] = {
            "baseline": baseline_metrics,
            "current": current_metrics,
            "deterioration_flag": bool(deterioration),
            "rollback_recommendation": bool(deterioration and current_metrics["sample_count"] >= 3),
        }
    return {"generated_at": _utcnow().isoformat(), "windows": windows}


def apply_learning_recommendation(db: Session, *, recommendation_id: str, actor: str, reason: str) -> dict:
    recommendation = _recommendation_by_id(db, recommendation_id)
    if recommendation is None:
        raise ValueError("learning_recommendation_not_found")
    payload = _ensure_recommendation_defaults(recommendation)
    lifecycle = str(payload.get("lifecycle") or "recommendation_created")
    if lifecycle not in {"approved", "simulated", "recommendation_created"}:
        raise ValueError("learning_recommendation_not_approvable")
    before_change, after_change, version_ref = _apply_recommendation_change(db, recommendation)
    version = dict(payload.get("version") or {})
    current_version = str(version.get("current_version") or f"learning-rec-{recommendation.id[:8]}")
    next_version = f"{current_version}-applied-{_utcnow().strftime('%H%M%S')}"
    version_history = list(payload.get("version_history") or [])
    version_history.append({
        "previous_version": current_version,
        "current_version": next_version,
        "changed_by": actor,
        "changed_reason": reason,
        "rollback_target": current_version,
        "changed_at": _utcnow().isoformat(),
        "version_ref": version_ref,
    })
    payload["version"] = {
        "previous_version": current_version,
        "current_version": next_version,
        "changed_by": actor,
        "changed_reason": reason,
        "rollback_target": current_version,
    }
    payload["version_history"] = version_history
    payload = _append_status_history(payload, state="applied", actor=actor, reason=reason, version_ref=version_ref or next_version, before_payload=before_change, after_payload=after_change)
    recommendation.recommendation_value = payload
    recommendation.is_applied = True
    recommendation.applied_at = _utcnow()
    payload["post_change_monitoring"] = _build_post_change_monitoring(db, recommendation=recommendation, since_at=recommendation.applied_at)
    recommendation.recommendation_value = payload
    db.commit()
    db.refresh(recommendation)
    return serialize_learning_recommendation(recommendation)


def rollback_learning_recommendation(db: Session, *, recommendation_id: str, actor: str, reason: str) -> dict:
    recommendation = _recommendation_by_id(db, recommendation_id)
    if recommendation is None:
        raise ValueError("learning_recommendation_not_found")
    payload = _ensure_recommendation_defaults(recommendation)
    history = list(payload.get("status_history") or [])
    applied_entry = next((item for item in reversed(history) if item.get("state") == "applied"), None)
    if applied_entry is None:
        raise ValueError("learning_recommendation_not_applied")
    before_payload = dict(applied_entry.get("before_payload") or {})
    after_payload = dict(applied_entry.get("after_payload") or {})
    if recommendation.strategy_id:
        strategy = db.query(CanonicalStrategyRegistry).filter(CanonicalStrategyRegistry.strategy_id == recommendation.strategy_id).first()
        if strategy is None:
            raise ValueError("strategy_not_found_for_recommendation")
        strategy.is_enabled = bool(before_payload.get("is_enabled", strategy.is_enabled))
        strategy.weight = float(before_payload.get("weight", strategy.weight or 1.0))
        if before_payload.get("entry_long") is not None:
            strategy.entry_long = dict(before_payload.get("entry_long") or {})
        if before_payload.get("entry_short") is not None:
            strategy.entry_short = dict(before_payload.get("entry_short") or {})
    payload = _append_status_history(payload, state="rolled_back", actor=actor, reason=reason, version_ref=str((payload.get("version") or {}).get("rollback_target") or recommendation.id), before_payload=after_payload, after_payload=before_payload)
    recommendation.recommendation_value = payload
    recommendation.is_applied = False
    db.commit()
    db.refresh(recommendation)
    return serialize_learning_recommendation(recommendation)


def get_learning_version_history(db: Session, *, recommendation_id: str) -> dict:
    recommendation = _recommendation_by_id(db, recommendation_id)
    if recommendation is None:
        raise ValueError("learning_recommendation_not_found")
    payload = _ensure_recommendation_defaults(recommendation)
    return {
        "recommendation_id": recommendation.id,
        "current_version": (payload.get("version") or {}).get("current_version"),
        "items": list(payload.get("version_history") or []),
    }


def get_learning_post_change_monitoring(db: Session, *, recommendation_id: str) -> dict:
    recommendation = _recommendation_by_id(db, recommendation_id)
    if recommendation is None:
        raise ValueError("learning_recommendation_not_found")
    payload = _ensure_recommendation_defaults(recommendation)
    monitoring = payload.get("post_change_monitoring") or {}
    if recommendation.applied_at:
        monitoring = _build_post_change_monitoring(db, recommendation=recommendation, since_at=recommendation.applied_at)
        payload["post_change_monitoring"] = monitoring
        recommendation.recommendation_value = payload
        db.commit()
        db.refresh(recommendation)
    return {"recommendation_id": recommendation.id, **(monitoring or {"windows": {}})}


def mark_learning_recommendation_simulated(db: Session, *, recommendation_id: str, actor: str, reason: str, simulation_payload: dict) -> dict:
    recommendation = _recommendation_by_id(db, recommendation_id)
    if recommendation is None:
        raise ValueError("learning_recommendation_not_found")
    payload = _ensure_recommendation_defaults(recommendation)
    version_ref = _current_version_ref(payload, recommendation.id)
    safe_simulation_payload = _json_safe(simulation_payload)
    payload["last_simulation"] = safe_simulation_payload
    payload = _append_status_history(payload, state="simulated", actor=actor, reason=reason, version_ref=version_ref, before_payload={}, after_payload={"simulation_scope": safe_simulation_payload.get("scope")})
    recommendation.recommendation_value = payload
    db.commit()
    db.refresh(recommendation)
    return serialize_learning_recommendation(recommendation)


def serialize_learning_recommendation(row: LearningRecommendation) -> dict:
    payload = _ensure_recommendation_defaults(row)
    return {
        "id": row.id,
        "strategy_id": row.strategy_id,
        "family": row.family,
        "recommendation_type": row.recommendation_type,
        "recommendation_value": payload,
        "note": row.note,
        "severity": row.severity,
        "is_applied": row.is_applied,
        "reason": payload.get("reason"),
        "confidence": payload.get("confidence"),
        "evidence_summary": payload.get("evidence_summary"),
        "recommendation_scope": payload.get("scope"),
        "risk_impact": payload.get("risk_impact"),
        "lifecycle": payload.get("lifecycle"),
        "status_history": payload.get("status_history") or [],
        "version": payload.get("version") or {},
        "version_history": payload.get("version_history") or [],
        "post_change_monitoring": payload.get("post_change_monitoring") or {},
        "created_at": row.created_at,
        "applied_at": row.applied_at,
    }
