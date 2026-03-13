from collections import defaultdict
from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from models import (
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
        no_trade = [e for e in events if e.decision in {"NO_TRADE", "BLOCKED"}]

        hit_rate = (len(wins) / len(closed) * 100) if closed else 0.0
        avg_return = (sum(e.pnl_normalized for e in closed) / len(closed)) if closed else 0.0
        avg_mfe = (sum(e.max_favorable_excursion for e in events) / sample) if sample else 0.0
        avg_mae = (sum(e.max_adverse_excursion for e in events) / sample) if sample else 0.0
        false_allow_rate = (len([e for e in actionable if e.outcome_label in {"LOSS", "REJECTED"}]) / len(actionable) * 100) if actionable else 0.0
        false_reject_rate = (len(no_trade) / sample * 100) if sample else 0.0
        rolling = (hit_rate * 0.7) + ((avg_return * 100) * 0.3)
        decay_quality = (rolling * 0.8) - (false_allow_rate * 0.2)

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
                recommendations.append(
                    LearningRecommendation(
                        id=str(uuid.uuid4()),
                        strategy_id=strategy_id,
                        family=None,
                        recommendation_type="disable_recommendation",
                        recommendation_value={"suggested_is_enabled": False},
                        note="quality score critically low, disable önerisi",
                        severity="high",
                    )
                )
            elif false_allow_rate > 45:
                recommendations.append(
                    LearningRecommendation(
                        id=str(uuid.uuid4()),
                        strategy_id=strategy_id,
                        family=None,
                        recommendation_type="decrease_weight_recommendation",
                        recommendation_value={"suggested_weight_multiplier": 0.7},
                        note="false allow trend yüksek, throttle önerisi",
                        severity="medium",
                    )
                )
            elif decay_quality > 70:
                recommendations.append(
                    LearningRecommendation(
                        id=str(uuid.uuid4()),
                        strategy_id=strategy_id,
                        family=None,
                        recommendation_type="increase_weight_recommendation",
                        recommendation_value={"suggested_weight_multiplier": 1.1},
                        note="son dönem kalite yüksek, sınırlı weight artırımı önerisi",
                        severity="low",
                    )
                )

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
        db.add(recommendation)
    db.commit()

    return {
        "schema_version": LEARNING_SCHEMA_VERSION,
        "engine_version": LEARNING_ENGINE_VERSION,
        "generated_at": datetime.now(timezone.utc),
        "window_days": window_days,
        "events_count": len(recent_events),
        "strategy_memory_count": len(strategy_buckets),
        "family_memory_count": len(family_buckets),
        "recommendation_count": len(recommendations),
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
        if key:
            recommendation_lookup[key].append(
                {
                    "recommendation_type": row.recommendation_type,
                    "severity": row.severity,
                    "note": row.note,
                    "created_at": row.created_at,
                }
            )

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
                "created_at": row.created_at,
                "applied_at": row.applied_at,
                "admin_approval_required": True,
            }
            for row in recommendation_rows
        ],
        "events": list_learning_events(db, limit=200),
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
        events.append(
            {
                "event_id": row.id,
                "symbol": row.symbol,
                "decision": row.decision,
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
