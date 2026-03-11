from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import StrategyObservabilityEvent, StrategyTemplate


def parse_window_to_since(window: str) -> tuple[str, datetime]:
    normalized = (window or "24h").lower()
    now = datetime.now(timezone.utc)
    mapping = {
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
    }
    if normalized not in mapping:
        normalized = "24h"
    return normalized, now - mapping[normalized]


def log_strategy_observability_events(
    db: Session,
    *,
    selection_cycle_id: str,
    audit_log_id: str | None,
    bot_profile_id: str | None,
    user_id: str | None,
    strategy_id: str,
    strategy_name: str,
    market_regime: str,
    multiplier_version: str,
    multiplier_set: dict,
    ranked: list[dict],
    selected: list[dict],
):
    selected_rank_map = {item.get("symbol", "").upper(): item.get("selection_rank") for item in selected}
    rows: list[StrategyObservabilityEvent] = []

    for candidate in ranked:
        symbol = str(candidate.get("symbol", "")).upper()
        if not symbol:
            continue
        reason_codes = candidate.get("reason_codes") or []
        event_type = "selected_for_execution" if symbol in selected_rank_map else "rejected"
        rejection_reason = None if event_type == "selected_for_execution" else (reason_codes[0] if reason_codes else "not_selected")

        rows.append(
            StrategyObservabilityEvent(
                selection_cycle_id=selection_cycle_id,
                audit_log_id=audit_log_id,
                bot_profile_id=bot_profile_id,
                user_id=user_id,
                symbol=symbol,
                strategy_id=strategy_id,
                strategy_name=strategy_name,
                event_type=event_type,
                market_regime=market_regime,
                multiplier_version=multiplier_version,
                multiplier_set=multiplier_set,
                base_score=float(candidate.get("base_score", 0.0)),
                adjusted_score=float(candidate.get("adjusted_score", 0.0)),
                score_delta=float(candidate.get("score_delta", 0.0)),
                selection_rank=selected_rank_map.get(symbol),
                trend_strength=candidate.get("trend_strength"),
                relative_volume=float(candidate.get("relative_volume", 0.0) or 0.0),
                hard_gate_pass=bool(candidate.get("hard_gate_pass", False)),
                threshold_pass=bool(candidate.get("threshold_pass", False)),
                rejection_reason=rejection_reason,
                event_metadata={
                    "reason_codes": reason_codes,
                    "component_scores": candidate.get("component_scores", {}),
                    "metadata": candidate.get("metadata", {}),
                },
            )
        )

    if rows:
        db.add_all(rows)
        db.commit()


def get_top_signals(db: Session, *, window: str, top_n: int):
    normalized, since = parse_window_to_since(window)
    top_n = min(max(int(top_n), 1), 50)

    latest_cycle = (
        db.query(StrategyObservabilityEvent.selection_cycle_id)
        .filter(
            StrategyObservabilityEvent.created_at >= since,
            StrategyObservabilityEvent.event_type == "selected_for_execution",
        )
        .order_by(StrategyObservabilityEvent.created_at.desc())
        .first()
    )

    query = db.query(StrategyObservabilityEvent).filter(
        StrategyObservabilityEvent.created_at >= since,
        StrategyObservabilityEvent.event_type == "selected_for_execution",
    )
    if latest_cycle and latest_cycle[0]:
        query = query.filter(StrategyObservabilityEvent.selection_cycle_id == latest_cycle[0])

    rows = (
        query.order_by(
            StrategyObservabilityEvent.selection_rank.asc().nullslast(),
            StrategyObservabilityEvent.adjusted_score.desc(),
            StrategyObservabilityEvent.symbol.asc(),
        )
        .limit(top_n)
        .all()
    )

    return {
        "window": normalized,
        "top_n": top_n,
        "selection_cycle_id": latest_cycle[0] if latest_cycle else None,
        "items": [
            {
                "symbol": row.symbol,
                "strategy_id": row.strategy_id,
                "market_regime": row.market_regime,
                "base_score": row.base_score,
                "adjusted_score": row.adjusted_score,
                "score_delta": row.score_delta,
                "selection_rank": row.selection_rank,
                "trend_strength": row.trend_strength,
                "relative_volume": row.relative_volume,
                "timestamp": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
    }


def get_rejection_analytics(db: Session, *, window: str):
    normalized, since = parse_window_to_since(window)
    base_query = db.query(StrategyObservabilityEvent).filter(StrategyObservabilityEvent.created_at >= since)

    total = base_query.count()
    after_hard_gate = base_query.filter(StrategyObservabilityEvent.hard_gate_pass.is_(True)).count()
    selected = base_query.filter(StrategyObservabilityEvent.event_type == "selected_for_execution").count()
    rejected_trend = base_query.filter(StrategyObservabilityEvent.rejection_reason == "trend_strength_weak").count()
    rejected_btc = base_query.filter(StrategyObservabilityEvent.rejection_reason == "btc_regime_hostile").count()
    rejected_freeze = base_query.filter(StrategyObservabilityEvent.rejection_reason == "freeze_guard_active").count()
    rejected_threshold = base_query.filter(StrategyObservabilityEvent.rejection_reason == "adjusted_score_below_threshold").count()

    return {
        "window": normalized,
        "signals_total": total,
        "signals_after_hard_gate": after_hard_gate,
        "signals_rejected_trend_strength": rejected_trend,
        "signals_rejected_btc_regime": rejected_btc,
        "signals_rejected_freeze_guard": rejected_freeze,
        "signals_rejected_threshold": rejected_threshold,
        "signals_selected": selected,
    }


def get_score_metrics(db: Session, *, window: str):
    normalized, since = parse_window_to_since(window)
    rows = db.query(StrategyObservabilityEvent).filter(StrategyObservabilityEvent.created_at >= since).all()

    if not rows:
        return {
            "window": normalized,
            "market_regime_distribution": {},
            "avg_base_score": 0,
            "avg_adjusted_score": 0,
            "avg_score_delta": 0,
            "signals_per_regime": {},
            "selected_signals_per_regime": {},
        }

    regime_counts: dict[str, int] = {}
    selected_per_regime: dict[str, int] = {}
    base_scores: list[float] = []
    adjusted_scores: list[float] = []
    deltas: list[float] = []

    for row in rows:
        regime_counts[row.market_regime] = regime_counts.get(row.market_regime, 0) + 1
        if row.event_type == "selected_for_execution":
            selected_per_regime[row.market_regime] = selected_per_regime.get(row.market_regime, 0) + 1
        if row.base_score is not None:
            base_scores.append(float(row.base_score))
        if row.adjusted_score is not None:
            adjusted_scores.append(float(row.adjusted_score))
        if row.score_delta is not None:
            deltas.append(float(row.score_delta))

    avg_base = sum(base_scores) / len(base_scores) if base_scores else 0
    avg_adjusted = sum(adjusted_scores) / len(adjusted_scores) if adjusted_scores else 0
    avg_delta = sum(deltas) / len(deltas) if deltas else 0

    return {
        "window": normalized,
        "market_regime_distribution": regime_counts,
        "avg_base_score": round(avg_base, 4),
        "avg_adjusted_score": round(avg_adjusted, 4),
        "avg_score_delta": round(avg_delta, 4),
        "signals_per_regime": regime_counts,
        "selected_signals_per_regime": selected_per_regime,
    }


def get_strategy_observability_report(db: Session, *, window: str):
    rejection = get_rejection_analytics(db, window=window)
    score_metrics = get_score_metrics(db, window=window)
    active_spot_strategies = [
        item[0]
        for item in db.query(StrategyTemplate.strategy_type)
        .filter(StrategyTemplate.is_active.is_(True), StrategyTemplate.strategy_type.like("spot_%"))
        .all()
    ]
    return {
        "window": rejection["window"],
        "active_spot_strategies": active_spot_strategies,
        "market_regime_distribution": score_metrics.get("market_regime_distribution", {}),
        "signals_total": rejection.get("signals_total", 0),
        "signals_selected": rejection.get("signals_selected", 0),
        "signals_rejected_breakdown": {
            "trend_strength": rejection.get("signals_rejected_trend_strength", 0),
            "btc_regime": rejection.get("signals_rejected_btc_regime", 0),
            "freeze_guard": rejection.get("signals_rejected_freeze_guard", 0),
            "threshold": rejection.get("signals_rejected_threshold", 0),
        },
        "avg_adjusted_score": score_metrics.get("avg_adjusted_score", 0),
        "avg_base_score": score_metrics.get("avg_base_score", 0),
        "score_delta_avg": score_metrics.get("avg_score_delta", 0),
    }
