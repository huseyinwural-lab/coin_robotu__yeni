from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import PaperPosition, PositionLedgerEvent, StrategyObservabilityEvent, StrategyTemplate


def _global_strategy_stats(db: Session) -> dict:
    open_events = db.query(PositionLedgerEvent).filter(PositionLedgerEvent.event_type == "trade_open").all()
    strategy_map = {event.position_id: str((event.payload or {}).get("strategy_id") or "spot_pullback_v1") for event in open_events}

    closed_rows = db.query(PaperPosition).filter(PaperPosition.closed_at.is_not(None)).all()
    pnl_by_strategy: dict[str, list[float]] = {}
    for row in closed_rows:
        strategy_id = strategy_map.get(row.id, "spot_pullback_v1")
        pnl_by_strategy.setdefault(strategy_id, []).append(float(row.realized_pnl or 0.0))

    result: dict[str, dict] = {}
    for strategy_id, pnls in pnl_by_strategy.items():
        positive = sum(item for item in pnls if item > 0)
        negative = sum(abs(item) for item in pnls if item < 0)
        pf = (positive / negative) if negative > 0 else (2.0 if positive > 0 else 1.0)

        cumulative = 0.0
        peak = 0.0
        drawdown = 0.0
        for item in pnls:
            cumulative += item
            peak = max(peak, cumulative)
            drawdown = max(drawdown, peak - cumulative)
        drawdown_pct = (drawdown / 10000.0) * 100

        result[strategy_id] = {
            "profit_factor": round(pf, 4),
            "drawdown_pct": round(drawdown_pct, 4),
            "trades": len(pnls),
        }
    return result


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
                strategy_id=str(candidate.get("strategy_id") or strategy_id),
                strategy_name=str(candidate.get("strategy_name") or strategy_name),
                event_type=event_type,
                market_regime=str(candidate.get("market_regime") or market_regime),
                multiplier_version=str(candidate.get("multiplier_version") or multiplier_version),
                multiplier_set=candidate.get("multiplier_set") or multiplier_set,
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
    rejected_market_bias = base_query.filter(
        StrategyObservabilityEvent.rejection_reason.in_(["market_bias_hostile", "btc_regime_hostile"])
    ).count()
    rejected_market_stress = base_query.filter(
        StrategyObservabilityEvent.rejection_reason.in_(["market_stress_guard_active", "freeze_guard_active"])
    ).count()
    rejected_threshold = base_query.filter(StrategyObservabilityEvent.rejection_reason == "adjusted_score_below_threshold").count()

    return {
        "window": normalized,
        "signals_total": total,
        "signals_after_hard_gate": after_hard_gate,
        "signals_rejected_trend_strength": rejected_trend,
        "signals_rejected_market_bias": rejected_market_bias,
        "signals_rejected_market_stress": rejected_market_stress,
        "signals_rejected_btc_regime": rejected_market_bias,
        "signals_rejected_freeze_guard": rejected_market_stress,
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
            "signals_per_strategy": {},
            "selected_signals_per_strategy": {},
        }

    regime_counts: dict[str, int] = {}
    selected_per_regime: dict[str, int] = {}
    signals_per_strategy: dict[str, int] = {}
    selected_signals_per_strategy: dict[str, int] = {}
    base_scores: list[float] = []
    adjusted_scores: list[float] = []
    deltas: list[float] = []

    for row in rows:
        regime_counts[row.market_regime] = regime_counts.get(row.market_regime, 0) + 1
        signals_per_strategy[row.strategy_id] = signals_per_strategy.get(row.strategy_id, 0) + 1
        if row.event_type == "selected_for_execution":
            selected_per_regime[row.market_regime] = selected_per_regime.get(row.market_regime, 0) + 1
            selected_signals_per_strategy[row.strategy_id] = selected_signals_per_strategy.get(row.strategy_id, 0) + 1
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
        "signals_per_strategy": signals_per_strategy,
        "selected_signals_per_strategy": selected_signals_per_strategy,
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
    if not active_spot_strategies:
        observed = list((score_metrics.get("signals_per_strategy") or {}).keys())
        active_spot_strategies = sorted(observed)

    strategy_stats = _global_strategy_stats(db)
    strategy_profit_factor = {key: value.get("profit_factor", 0) for key, value in strategy_stats.items()}
    strategy_drawdown = {key: value.get("drawdown_pct", 0) for key, value in strategy_stats.items()}
    return {
        "window": rejection["window"],
        "active_spot_strategies": active_spot_strategies,
        "market_regime_distribution": score_metrics.get("market_regime_distribution", {}),
        "signals_per_strategy": score_metrics.get("signals_per_strategy", {}),
        "selected_signals_per_strategy": score_metrics.get("selected_signals_per_strategy", {}),
        "signals_total": rejection.get("signals_total", 0),
        "signals_selected": rejection.get("signals_selected", 0),
        "signals_rejected_breakdown": {
            "trend_strength": rejection.get("signals_rejected_trend_strength", 0),
            "market_bias": rejection.get("signals_rejected_market_bias", 0),
            "market_stress": rejection.get("signals_rejected_market_stress", 0),
            "btc_regime": rejection.get("signals_rejected_btc_regime", 0),
            "freeze_guard": rejection.get("signals_rejected_freeze_guard", 0),
            "threshold": rejection.get("signals_rejected_threshold", 0),
        },
        "strategy_profit_factor": strategy_profit_factor,
        "strategy_drawdown": strategy_drawdown,
        "avg_adjusted_score": score_metrics.get("avg_adjusted_score", 0),
        "avg_base_score": score_metrics.get("avg_base_score", 0),
        "score_delta_avg": score_metrics.get("avg_score_delta", 0),
    }


def log_risk_outcome_event(
    db: Session,
    *,
    selection_cycle_id: str,
    audit_log_id: str | None,
    bot_profile_id: str | None,
    user_id: str | None,
    symbol: str,
    strategy_id: str,
    strategy_name: str,
    market_regime: str,
    multiplier_version: str,
    multiplier_set: dict,
    base_score: float,
    adjusted_score: float,
    score_delta: float,
    selection_rank: int | None,
    trend_strength: str | None,
    relative_volume: float | None,
    risk_check_result: str,
    capital_allocation: dict,
    reason_codes: list[str],
):
    row = StrategyObservabilityEvent(
        selection_cycle_id=selection_cycle_id,
        audit_log_id=audit_log_id,
        bot_profile_id=bot_profile_id,
        user_id=user_id,
        symbol=symbol,
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        event_type="risk_result",
        market_regime=market_regime,
        multiplier_version=multiplier_version,
        multiplier_set=multiplier_set,
        base_score=float(base_score or 0),
        adjusted_score=float(adjusted_score or 0),
        score_delta=float(score_delta or 0),
        selection_rank=selection_rank,
        trend_strength=trend_strength,
        relative_volume=float(relative_volume or 0),
        hard_gate_pass=True,
        threshold_pass=True,
        rejection_reason=None if risk_check_result == "approved" else (reason_codes[0] if reason_codes else "risk_rejected"),
        event_metadata={
            "risk_check_result": risk_check_result,
            "capital_allocation": capital_allocation,
            "reason_codes": reason_codes,
        },
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
