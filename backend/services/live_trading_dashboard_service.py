import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from models import (
    AlertPolicy,
    AuditLog,
    ExecutionMetric,
    LearningRecommendation,
    LiveActivationConfig,
    PaperPosition,
    RiskOrchestratorPolicy,
    ScannerPerformanceSnapshot,
    StrategyOutcomeMemory,
    TestnetExecutionLog,
)
from services.risk_engine_service import build_admin_risk_status
from services.scanner_observability_service import FALLBACK_TRIGGER_THRESHOLDS
from services.scanner_runtime import get_latest_global_runtime_snapshot

WINDOW_MAP = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
}

REJECT_STATUSES = {"REJECTED", "FAILED", "CANCELLED", "EXPIRED"}
PARTIAL_FILL_STATUSES = {"PARTIALLY_FILLED", "PARTIAL", "PARTIAL_FILL"}


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 6)


def _window_bounds(window: str) -> tuple[str, datetime, datetime]:
    normalized = str(window or "1h").strip().lower()
    if normalized not in WINDOW_MAP:
        raise ValueError("window must be one of 1h, 6h, 24h")
    now = datetime.now(timezone.utc)
    since = now - WINDOW_MAP[normalized]
    return normalized, since, now


def _extract_metric(metrics: dict, keys: list[str], *, as_ms: bool = False) -> float | None:
    for key in keys:
        if key not in metrics:
            continue
        raw = metrics.get(key)
        if raw is None:
            continue
        value = _safe_float(raw, 0.0)
        return value * 1000.0 if as_ms else value
    return None


def _extract_bool(metrics: dict, keys: list[str]) -> bool | None:
    for key in keys:
        if key in metrics:
            return bool(metrics.get(key))
    return None


def _today_bounds_utc() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    return day_start, now


def _risk_policy(db: Session) -> RiskOrchestratorPolicy | None:
    return db.query(RiskOrchestratorPolicy).filter(RiskOrchestratorPolicy.id == "global").first()


def _alert_policy(db: Session) -> AlertPolicy | None:
    return db.query(AlertPolicy).filter(AlertPolicy.id == "global").first()


def _live_config(db: Session) -> LiveActivationConfig | None:
    return db.query(LiveActivationConfig).filter(LiveActivationConfig.id == "global").first()


def _scanner_rows(db: Session, since: datetime) -> list[ScannerPerformanceSnapshot]:
    return (
        db.query(ScannerPerformanceSnapshot)
        .filter(ScannerPerformanceSnapshot.created_at >= since)
        .order_by(ScannerPerformanceSnapshot.created_at.desc())
        .limit(2500)
        .all()
    )


def _execution_rows(db: Session, since: datetime) -> list[ExecutionMetric]:
    return (
        db.query(ExecutionMetric)
        .filter(ExecutionMetric.created_at >= since)
        .order_by(ExecutionMetric.created_at.desc())
        .limit(2500)
        .all()
    )


def build_scanner_health(db: Session, cache, *, window: str = "1h") -> dict:
    normalized_window, since, now = _window_bounds(window)
    rows = _scanner_rows(db, since)
    runtime = get_latest_global_runtime_snapshot(cache) or {}
    runtime_metrics = runtime.get("runtime_metrics") or {}
    tiered_scan = runtime.get("tiered_scan") or {}
    discovery = tiered_scan.get("discovery") or {}
    qualification = tiered_scan.get("qualification") or {}
    freshness = runtime.get("freshness") or {}
    risk_engine = runtime.get("risk_engine") or {}
    reason_distribution = risk_engine.get("reason_distribution") or {}

    scan_latencies: list[float] = []
    decision_latencies: list[float] = []
    snapshot_ages: list[float] = []
    queue_depth_values: list[float] = []
    fallback_hits = 0

    for row in rows:
        metrics = row.metrics or {}
        scan_latency = _extract_metric(metrics, ["scan_latency_ms", "cycle_duration_ms"])
        decision_latency = _extract_metric(metrics, ["decision_latency_ms"])
        snapshot_age = _extract_metric(metrics, ["snapshot_age_ms"]) or _extract_metric(metrics, ["snapshot_age_avg_sec"], as_ms=True)
        queue_depth = _extract_metric(metrics, ["queue_depth", "queue_backlog"])
        fallback_flag = _extract_bool(metrics, ["fallback_active", "overload_fallback_applied"])

        if scan_latency is not None:
            scan_latencies.append(scan_latency)
        if decision_latency is not None:
            decision_latencies.append(decision_latency)
        if snapshot_age is not None:
            snapshot_ages.append(snapshot_age)
        if queue_depth is not None:
            queue_depth_values.append(queue_depth)
        if fallback_flag:
            fallback_hits += 1

    fallback_rate = round(fallback_hits / max(len(rows), 1), 6) if rows else 0.0
    spread_reject_count = sum(
        _safe_int(value)
        for key, value in reason_distribution.items()
        if "spread" in str(key or "").lower()
    )

    symbols_scanned = _safe_int(
        (runtime.get("scanner_perf") or {}).get("total_active_symbols")
        or runtime.get("universe_size")
        or runtime_metrics.get("candidate_count")
    )

    return {
        "window": normalized_window,
        "generated_at": now,
        "sample_count": len(rows),
        "symbols_scanned": symbols_scanned,
        "discovery_candidates": _safe_int(discovery.get("candidate_count") or runtime_metrics.get("candidate_count")),
        "qualified_candidates": _safe_int(qualification.get("qualified_count")),
        "decisions_generated": _safe_int(runtime.get("decision_count")),
        "fallback_active": bool(runtime.get("fallback_active", False)),
        "fallback_rate": fallback_rate,
        "stale_skip_count": _safe_int(freshness.get("stale_skip_count") or runtime_metrics.get("stale_skip_count")),
        "spread_reject_count": spread_reject_count,
        "queue_depth": _safe_int(runtime_metrics.get("queue_depth") if runtime_metrics.get("queue_depth") is not None else _avg(queue_depth_values)),
        "scan_latency_avg_ms": round(_avg(scan_latencies), 4),
        "decision_latency_avg_ms": round(_avg(decision_latencies), 4),
        "snapshot_age_avg_ms": round(_avg(snapshot_ages), 4),
    }


def build_execution_quality_summary(db: Session, *, window: str = "1h") -> dict:
    normalized_window, since, now = _window_bounds(window)
    metrics = _execution_rows(db, since)

    if not metrics:
        fallback_rows = (
            db.query(TestnetExecutionLog)
            .filter(TestnetExecutionLog.created_at >= since)
            .order_by(TestnetExecutionLog.created_at.desc())
            .limit(1200)
            .all()
        )
        latencies = [_safe_float(row.execution_latency) for row in fallback_rows if row.execution_latency is not None]
        slippages = [abs(_safe_float(row.slippage)) for row in fallback_rows if row.slippage is not None]
        quality_scores = [_safe_float(row.execution_quality_score) for row in fallback_rows]
        reject_count = sum(1 for row in fallback_rows if str(row.status or "").upper() in REJECT_STATUSES)
        return {
            "window": normalized_window,
            "generated_at": now,
            "sample_count": len(fallback_rows),
            "execution_latency_avg_ms": round(_avg(latencies), 4),
            "slippage_avg_pct": round(_avg(slippages), 6),
            "reject_rate": round(reject_count / max(len(fallback_rows), 1), 6) if fallback_rows else 0.0,
            "partial_fill_rate": 0.0,
            "precision_error_count": 0,
            "retry_count": 0,
            "execution_quality_score": round(_avg(quality_scores), 4),
            "strategy_stats": [],
            "symbol_stats": [],
            "recent_items": [
                {
                    "created_at": _as_aware(row.created_at),
                    "symbol": row.symbol,
                    "status": row.status,
                    "execution_quality_score": _safe_float(row.execution_quality_score),
                }
                for row in fallback_rows[:20]
            ],
        }

    latencies: list[float] = []
    slippages: list[float] = []
    quality_scores: list[float] = []
    reject_count = 0
    partial_fill_count = 0
    precision_error_count = 0
    retry_count = 0

    strategy_acc: dict[str, dict] = defaultdict(lambda: {"trades": 0, "quality_total": 0.0, "reject": 0})
    symbol_acc: dict[str, dict] = defaultdict(lambda: {"trades": 0, "quality_total": 0.0, "reject": 0})

    for row in metrics:
        latency = row.execution_time_ms
        if latency is not None:
            latencies.append(_safe_float(latency))

        slippage = row.slippage_pct
        if slippage is not None:
            slippages.append(abs(_safe_float(slippage)))

        quality = _safe_float(row.execution_quality_score)
        quality_scores.append(quality)

        status = str(row.final_status or row.status or "").upper()
        is_reject = status in REJECT_STATUSES
        if is_reject:
            reject_count += 1
        if status in PARTIAL_FILL_STATUSES:
            partial_fill_count += 1

        failure_code = str(row.failure_code or "").lower()
        if "precision" in failure_code:
            precision_error_count += 1

        raw_status = row.raw_exchange_status or {}
        retry_count += _safe_int(raw_status.get("retry_count") or raw_status.get("retries") or 0)

        strategy_key = str(row.strategy_type or "unknown_strategy")
        strategy_acc[strategy_key]["trades"] += 1
        strategy_acc[strategy_key]["quality_total"] += quality
        strategy_acc[strategy_key]["reject"] += 1 if is_reject else 0

        symbol_key = str(row.symbol or "UNKNOWN").upper()
        symbol_acc[symbol_key]["trades"] += 1
        symbol_acc[symbol_key]["quality_total"] += quality
        symbol_acc[symbol_key]["reject"] += 1 if is_reject else 0

    strategy_stats = [
        {
            "strategy": key,
            "trades": value["trades"],
            "avg_quality_score": round(value["quality_total"] / max(value["trades"], 1), 4),
            "reject_rate": round(value["reject"] / max(value["trades"], 1), 6),
        }
        for key, value in strategy_acc.items()
    ]
    strategy_stats.sort(key=lambda item: (item["trades"], item["avg_quality_score"]), reverse=True)

    symbol_stats = [
        {
            "symbol": key,
            "trades": value["trades"],
            "avg_quality_score": round(value["quality_total"] / max(value["trades"], 1), 4),
            "reject_rate": round(value["reject"] / max(value["trades"], 1), 6),
        }
        for key, value in symbol_acc.items()
    ]
    symbol_stats.sort(key=lambda item: (item["trades"], item["avg_quality_score"]), reverse=True)

    return {
        "window": normalized_window,
        "generated_at": now,
        "sample_count": len(metrics),
        "execution_latency_avg_ms": round(_avg(latencies), 4),
        "slippage_avg_pct": round(_avg(slippages), 6),
        "reject_rate": round(reject_count / max(len(metrics), 1), 6),
        "partial_fill_rate": round(partial_fill_count / max(len(metrics), 1), 6),
        "precision_error_count": precision_error_count,
        "retry_count": retry_count,
        "execution_quality_score": round(_avg(quality_scores), 4),
        "strategy_stats": strategy_stats[:10],
        "symbol_stats": symbol_stats[:10],
        "recent_items": [
            {
                "created_at": _as_aware(row.created_at),
                "symbol": row.symbol,
                "status": row.final_status or row.status,
                "execution_quality_score": _safe_float(row.execution_quality_score),
            }
            for row in metrics[:20]
        ],
    }


def build_risk_summary(db: Session, cache, *, window: str = "1h") -> dict:
    normalized_window, _since, now = _window_bounds(window)
    risk_status = build_admin_risk_status(db, cache)
    runtime = get_latest_global_runtime_snapshot(cache) or {}
    runtime_risk = runtime.get("risk_engine") or {}
    distribution_raw = runtime_risk.get("decision_distribution") or {}

    distribution = {str(key or "").lower(): _safe_int(value) for key, value in distribution_raw.items()}
    allow_count = _safe_int(distribution.get("allow"))
    reduce_size_count = _safe_int(distribution.get("reduce_size") or distribution.get("reduce"))
    pass_count = _safe_int(distribution.get("pass"))
    block_count = _safe_int(distribution.get("block") or distribution.get("reject") or distribution.get("rejected"))

    if allow_count + reduce_size_count + pass_count + block_count == 0:
        block_count = _safe_int(risk_status.get("risk_reject_count"))
        reduce_size_count = _safe_int(runtime_risk.get("reduce_size_count"))
        pass_count = _safe_int(risk_status.get("cooldown_pass_count"))

    total_decisions = allow_count + reduce_size_count + pass_count + block_count
    risk_reject_rate = (
        round(block_count / max(total_decisions, 1), 6)
        if total_decisions > 0
        else round(_safe_float(runtime_risk.get("risk_veto_rate"), 0.0), 6)
    )

    daily_loss = risk_status.get("daily_loss") or {}
    symbol_exposure = list(risk_status.get("symbol_exposure") or [])
    cluster_exposure = list(risk_status.get("cluster_exposure") or [])
    symbol_exposure.sort(key=lambda item: _safe_float(item.get("notional_pct")), reverse=True)
    cluster_exposure.sort(key=lambda item: _safe_float(item.get("notional_pct")), reverse=True)

    return {
        "window": normalized_window,
        "generated_at": now,
        "allow_count": allow_count,
        "reduce_size_count": reduce_size_count,
        "pass_count": pass_count,
        "block_count": block_count,
        "risk_reject_rate": risk_reject_rate,
        "daily_loss_pct": round(_safe_float(daily_loss.get("daily_loss_pct")), 6),
        "portfolio_exposure_pct": round(_safe_float(risk_status.get("portfolio_exposure_pct")), 6),
        "symbol_exposure_top": symbol_exposure[:3],
        "cluster_exposure_top": cluster_exposure[:3],
        "kill_switch_active": bool((risk_status.get("kill_switch_state") or {}).get("pipeline_kill_switch_active", False)),
        "spread_reject_count": _safe_int(risk_status.get("spread_reject_count")),
        "stale_reject_count": _safe_int(risk_status.get("stale_reject_count")),
        "config": risk_status.get("risk_config_snapshot") or {},
    }


def build_trading_performance_today(db: Session) -> dict:
    day_start, now = _today_bounds_utc()
    closed_rows = (
        db.query(PaperPosition)
        .filter(PaperPosition.closed_at.isnot(None), PaperPosition.closed_at >= day_start)
        .order_by(PaperPosition.closed_at.asc())
        .all()
    )
    open_count = db.query(PaperPosition).filter(PaperPosition.status == "open").count()

    trades_count_today = len(closed_rows)
    wins = sum(1 for row in closed_rows if _safe_float(row.realized_pnl) > 0)
    pnl_today_usdt = round(sum(_safe_float(row.realized_pnl) for row in closed_rows), 6)
    win_rate_today = round(wins / max(trades_count_today, 1), 6) if trades_count_today else 0.0

    hold_times = []
    for row in closed_rows:
        opened_at = _as_aware(row.opened_at)
        closed_at = _as_aware(row.closed_at)
        if opened_at and closed_at and closed_at >= opened_at:
            hold_times.append((closed_at - opened_at).total_seconds() / 60)
    avg_hold_time_min = round(_avg(hold_times), 4)

    policy = _risk_policy(db)
    baseline_equity = _safe_float(policy.reference_equity_usd if policy else 10000.0, 10000.0)
    running_equity = baseline_equity
    peak_equity = baseline_equity
    max_drawdown_pct = 0.0
    for row in closed_rows:
        running_equity += _safe_float(row.realized_pnl)
        if running_equity > peak_equity:
            peak_equity = running_equity
        drawdown_pct = ((peak_equity - running_equity) / max(abs(peak_equity), 1.0)) * 100
        if drawdown_pct > max_drawdown_pct:
            max_drawdown_pct = drawdown_pct

    symbol_acc: dict[str, dict] = defaultdict(lambda: {"trades": 0, "pnl_usdt": 0.0})
    for row in closed_rows:
        symbol_key = str(row.symbol or "UNKNOWN").upper()
        symbol_acc[symbol_key]["trades"] += 1
        symbol_acc[symbol_key]["pnl_usdt"] += _safe_float(row.realized_pnl)

    symbol_stats = [
        {
            "symbol": key,
            "trades": value["trades"],
            "pnl_usdt": round(value["pnl_usdt"], 6),
        }
        for key, value in symbol_acc.items()
    ]
    symbol_stats.sort(key=lambda item: (item["trades"], item["pnl_usdt"]), reverse=True)

    return {
        "generated_at": now,
        "day_start": day_start,
        "trades_count_today": trades_count_today,
        "win_rate_today": win_rate_today,
        "pnl_today_usdt": pnl_today_usdt,
        "max_drawdown_today_pct": round(max_drawdown_pct, 6),
        "avg_hold_time_min": avg_hold_time_min,
        "open_positions_count": open_count,
        "top_3_symbol_stats": symbol_stats[:3],
    }


def build_learning_summary(db: Session, *, window: str = "24h") -> dict:
    normalized_window, since, now = _window_bounds(window)
    rows = db.query(StrategyOutcomeMemory).order_by(StrategyOutcomeMemory.updated_at.desc()).limit(1200).all()

    if not rows:
        new_reco_count = (
            db.query(LearningRecommendation)
            .filter(LearningRecommendation.created_at >= since, LearningRecommendation.is_applied.is_(False))
            .count()
        )
        return {
            "window": normalized_window,
            "generated_at": now,
            "strategy_top_win_rate": None,
            "strategy_top_loss_rate": None,
            "false_allow_rate": 0.0,
            "false_reject_rate": 0.0,
            "quality_score_by_strategy": [],
            "new_recommendations_count": new_reco_count,
        }

    top_win = max(rows, key=lambda row: _safe_float(row.hit_rate))
    top_loss = min(rows, key=lambda row: _safe_float(row.hit_rate))

    weighted_false_allow = 0.0
    weighted_false_reject = 0.0
    total_samples = 0.0
    quality_items = []
    for row in rows:
        samples = max(_safe_float(row.sample_count), 1.0)
        total_samples += samples
        weighted_false_allow += _safe_float(row.false_allow_rate) * samples
        weighted_false_reject += _safe_float(row.false_reject_rate) * samples
        quality_items.append(
            {
                "strategy": row.strategy_id,
                "quality_score": round(_safe_float(row.decay_adjusted_quality_score), 6),
                "hit_rate": round(_safe_float(row.hit_rate), 6),
                "sample_count": _safe_int(row.sample_count),
            }
        )

    quality_items.sort(key=lambda item: (item["quality_score"], item["sample_count"]), reverse=True)
    new_reco_count = (
        db.query(LearningRecommendation)
        .filter(LearningRecommendation.created_at >= since, LearningRecommendation.is_applied.is_(False))
        .count()
    )

    return {
        "window": normalized_window,
        "generated_at": now,
        "strategy_top_win_rate": {
            "strategy": top_win.strategy_id,
            "hit_rate": round(_safe_float(top_win.hit_rate), 6),
            "sample_count": _safe_int(top_win.sample_count),
        },
        "strategy_top_loss_rate": {
            "strategy": top_loss.strategy_id,
            "hit_rate": round(_safe_float(top_loss.hit_rate), 6),
            "sample_count": _safe_int(top_loss.sample_count),
        },
        "false_allow_rate": round(weighted_false_allow / max(total_samples, 1.0), 6),
        "false_reject_rate": round(weighted_false_reject / max(total_samples, 1.0), 6),
        "quality_score_by_strategy": quality_items[:10],
        "new_recommendations_count": new_reco_count,
    }


def _derive_thresholds(db: Session, *, risk_summary: dict) -> dict:
    alert_policy = _alert_policy(db)
    risk_policy = _risk_policy(db)
    risk_config = risk_summary.get("config") or {}

    execution_quality_warning = _safe_float(alert_policy.execution_quality_warning_threshold if alert_policy else 60.0, 60.0)
    execution_quality_critical = _safe_float(alert_policy.execution_quality_critical_threshold if alert_policy else 40.0, 40.0)
    daily_loss_threshold = _safe_float(risk_policy.daily_loss_limit_pct if risk_policy else 5.0, 5.0)
    queue_depth_threshold = _safe_float(FALLBACK_TRIGGER_THRESHOLDS.get("queue_backlog"), 20.0)
    fallback_rate_threshold = _safe_float(FALLBACK_TRIGGER_THRESHOLDS.get("stale_rate"), 0.05)
    snapshot_age_threshold_ms = _safe_float(risk_config.get("stale_snapshot_threshold_sec"), 120.0) * 1000.0

    # policy'den türetilmiş reject-rate limiti
    reject_rate_threshold = round(max(0.03, min(0.4, daily_loss_threshold / 20.0)), 6)

    return {
        "execution_quality_warning_threshold": execution_quality_warning,
        "execution_quality_critical_threshold": execution_quality_critical,
        "daily_loss_pct_threshold": daily_loss_threshold,
        "queue_depth_threshold": queue_depth_threshold,
        "fallback_rate_threshold": fallback_rate_threshold,
        "snapshot_age_avg_ms_threshold": snapshot_age_threshold_ms,
        "reject_rate_threshold": reject_rate_threshold,
    }


def _critical_alerts(*, system_health: dict, scanner_health: dict, execution_quality: dict, risk_summary: dict, thresholds: dict) -> dict:
    alerts: list[dict] = []

    def _push(code: str, value, warning_threshold, critical_threshold, warning_hit: bool, critical_hit: bool):
        if not warning_hit and not critical_hit:
            return
        alerts.append(
            {
                "code": code,
                "status": "critical" if critical_hit else "warning",
                "value": value,
                "threshold_warning": warning_threshold,
                "threshold_critical": critical_threshold,
            }
        )

    kill_switch_active = bool(system_health.get("kill_switch_active", False))
    if kill_switch_active:
        alerts.append(
            {
                "code": "kill_switch_active",
                "status": "critical",
                "value": True,
                "threshold_warning": False,
                "threshold_critical": True,
            }
        )

    fallback_rate = _safe_float(scanner_health.get("fallback_rate"), 0.0)
    fallback_threshold = _safe_float(thresholds.get("fallback_rate_threshold"), 0.05)
    _push(
        "fallback_rate_high",
        round(fallback_rate, 6),
        fallback_threshold,
        round(fallback_threshold * 2, 6),
        fallback_rate > fallback_threshold,
        fallback_rate > (fallback_threshold * 2),
    )

    execution_quality_score = _safe_float(system_health.get("execution_quality_score"), 0.0)
    eq_warning = _safe_float(thresholds.get("execution_quality_warning_threshold"), 60.0)
    eq_critical = _safe_float(thresholds.get("execution_quality_critical_threshold"), 40.0)
    _push(
        "execution_quality_low",
        round(execution_quality_score, 4),
        eq_warning,
        eq_critical,
        execution_quality_score < eq_warning,
        execution_quality_score < eq_critical,
    )

    daily_loss_pct = _safe_float(risk_summary.get("daily_loss_pct"), 0.0)
    daily_loss_threshold = _safe_float(thresholds.get("daily_loss_pct_threshold"), 5.0)
    _push(
        "daily_loss_high",
        round(daily_loss_pct, 6),
        daily_loss_threshold,
        round(daily_loss_threshold * 1.25, 6),
        daily_loss_pct > daily_loss_threshold,
        daily_loss_pct > (daily_loss_threshold * 1.25),
    )

    reject_rate = _safe_float(execution_quality.get("reject_rate"), 0.0)
    reject_rate_threshold = _safe_float(thresholds.get("reject_rate_threshold"), 0.1)
    _push(
        "reject_rate_high",
        round(reject_rate, 6),
        reject_rate_threshold,
        round(reject_rate_threshold * 1.5, 6),
        reject_rate > reject_rate_threshold,
        reject_rate > (reject_rate_threshold * 1.5),
    )

    snapshot_age_avg_ms = _safe_float(system_health.get("snapshot_age_avg_ms"), 0.0)
    snapshot_age_threshold = _safe_float(thresholds.get("snapshot_age_avg_ms_threshold"), 120000.0)
    _push(
        "snapshot_age_high",
        round(snapshot_age_avg_ms, 4),
        snapshot_age_threshold,
        round(snapshot_age_threshold * 1.5, 4),
        snapshot_age_avg_ms > snapshot_age_threshold,
        snapshot_age_avg_ms > (snapshot_age_threshold * 1.5),
    )

    queue_depth = _safe_float(system_health.get("queue_depth"), 0.0)
    queue_depth_threshold = _safe_float(thresholds.get("queue_depth_threshold"), 20.0)
    _push(
        "queue_depth_high",
        round(queue_depth, 4),
        queue_depth_threshold,
        round(queue_depth_threshold * 1.5, 4),
        queue_depth > queue_depth_threshold,
        queue_depth > (queue_depth_threshold * 1.5),
    )

    overall_status = "normal"
    if any(item["status"] == "critical" for item in alerts):
        overall_status = "critical"
    elif any(item["status"] == "warning" for item in alerts):
        overall_status = "warning"

    return {
        "status": overall_status,
        "items": alerts,
    }


def build_live_trading_summary(db: Session, cache, *, window: str = "1h") -> dict:
    normalized_window, _since, now = _window_bounds(window)
    component_errors: list[dict] = []

    def _safe_component(name: str, builder, fallback: dict):
        try:
            return builder()
        except (SQLAlchemyError, ValueError, RuntimeError) as exc:
            component_errors.append({"component": name, "error": str(exc)})
            return fallback

    scanner_health = _safe_component(
        "scanner_health",
        lambda: build_scanner_health(db, cache, window=normalized_window),
        {
            "window": normalized_window,
            "generated_at": now,
            "sample_count": 0,
            "symbols_scanned": 0,
            "fallback_active": False,
            "fallback_rate": 0.0,
            "queue_depth": 0,
            "scan_latency_avg_ms": 0.0,
            "decision_latency_avg_ms": 0.0,
            "snapshot_age_avg_ms": 0.0,
        },
    )
    execution_quality = _safe_component(
        "execution_quality",
        lambda: build_execution_quality_summary(db, window=normalized_window),
        {
            "window": normalized_window,
            "generated_at": now,
            "sample_count": 0,
            "execution_latency_avg_ms": 0.0,
            "slippage_avg_pct": 0.0,
            "reject_rate": 0.0,
            "partial_fill_rate": 0.0,
            "precision_error_count": 0,
            "retry_count": 0,
            "execution_quality_score": 0.0,
            "strategy_stats": [],
            "symbol_stats": [],
            "recent_items": [],
        },
    )
    risk_summary = _safe_component(
        "risk_summary",
        lambda: build_risk_summary(db, cache, window=normalized_window),
        {
            "window": normalized_window,
            "generated_at": now,
            "kill_switch_active": False,
            "risk_reject_rate": 0.0,
            "allow_count": 0,
            "reduce_size_count": 0,
            "pass_count": 0,
            "block_count": 0,
            "cluster_exposure": [],
            "symbol_exposure": [],
        },
    )
    trading_performance = _safe_component(
        "trading_performance",
        lambda: build_trading_performance_today(db),
        {
            "date": now.date().isoformat(),
            "generated_at": now,
            "trades_count_today": 0,
            "win_rate_today": 0.0,
            "pnl_today_usdt": 0.0,
            "max_drawdown_today_pct": 0.0,
            "open_positions_count": 0,
            "top_3_symbol_stats": [],
        },
    )
    learning_summary = _safe_component(
        "learning_summary",
        lambda: build_learning_summary(db, window=normalized_window),
        {
            "window": normalized_window,
            "generated_at": now,
            "memory_sample_count": 0,
            "realized_avg": 0.0,
            "suggestions_sample_count": 0,
            "suggestion_mix": {},
        },
    )

    config = _safe_component("live_config", lambda: _live_config(db), {})
    config_obj = None if isinstance(config, dict) else config
    execution_mode = "MOCK"
    if config_obj:
        market_type = str(config_obj.market_type or "").lower()
        if bool(config_obj.live_mode_enabled) and "testnet" not in market_type:
            execution_mode = "LIVE" if not bool(config_obj.safe_mode_enabled) else "GUARDED_LIVE"
        elif bool(config_obj.live_mode_enabled):
            execution_mode = "PAPER_LIVE"

    system_health = {
        "execution_mode": execution_mode,
        "kill_switch_active": bool(risk_summary.get("kill_switch_active", False) or (config_obj.kill_switch_enabled if config_obj else False)),
        "fallback_active": bool(scanner_health.get("fallback_active", False)),
        "queue_depth": _safe_int(scanner_health.get("queue_depth")),
        "scan_latency_avg_ms": round(_safe_float(scanner_health.get("scan_latency_avg_ms")), 4),
        "decision_latency_avg_ms": round(_safe_float(scanner_health.get("decision_latency_avg_ms")), 4),
        "snapshot_age_avg_ms": round(_safe_float(scanner_health.get("snapshot_age_avg_ms")), 4),
        "execution_quality_score": round(_safe_float(execution_quality.get("execution_quality_score")), 4),
    }

    thresholds = _safe_component(
        "thresholds",
        lambda: _derive_thresholds(db, risk_summary=risk_summary),
        {
            "execution_quality_warning": 0.0,
            "execution_quality_critical": 0.0,
            "risk_reject_rate_warning": 0.0,
            "risk_reject_rate_critical": 0.0,
            "fallback_rate_warning": 0.0,
            "fallback_rate_critical": 0.0,
            "queue_depth_threshold": 0.0,
            "scan_latency_threshold_ms": 0.0,
            "decision_latency_threshold_ms": 0.0,
            "snapshot_age_threshold_ms": 0.0,
        },
    )
    critical_alerts = _safe_component(
        "critical_alerts",
        lambda: _critical_alerts(
            system_health=system_health,
            scanner_health=scanner_health,
            execution_quality=execution_quality,
            risk_summary=risk_summary,
            thresholds=thresholds,
        ),
        {"status": "normal", "items": []},
    )

    return {
        "window": normalized_window,
        "generated_at": now,
        "system_health": system_health,
        "trading_performance": trading_performance,
        "risk_engine": risk_summary,
        "scanner_health": scanner_health,
        "execution_quality": execution_quality,
        "learning_snapshot": learning_summary,
        "critical_alerts": critical_alerts,
        "thresholds": thresholds,
        "component_errors": component_errors,
    }


def build_daily_report(db: Session, cache) -> dict:
    day_start, now = _today_bounds_utc()
    summary = build_live_trading_summary(db, cache, window="24h")
    execution_quality = summary.get("execution_quality") or {}
    risk_engine = summary.get("risk_engine") or {}
    scanner_health = summary.get("scanner_health") or {}
    trading_performance = summary.get("trading_performance") or {}

    strategy_stats = list(execution_quality.get("strategy_stats") or [])[:3]
    symbol_stats = list(trading_performance.get("top_3_symbol_stats") or [])[:3]

    critical_alert_codes = [item.get("code") for item in (summary.get("critical_alerts") or {}).get("items", []) if item.get("status") == "critical"]
    audit_errors = (
        db.query(AuditLog)
        .filter(AuditLog.created_at >= day_start, AuditLog.severity == "error")
        .order_by(AuditLog.created_at.desc())
        .limit(10)
        .all()
    )
    critical_errors = critical_alert_codes + [str(row.action or "unknown_error") for row in audit_errors]

    return {
        "date": day_start.date().isoformat(),
        "generated_at": now,
        "execution_mode": (summary.get("system_health") or {}).get("execution_mode"),
        "trades_count": _safe_int(trading_performance.get("trades_count_today")),
        "win_rate": round(_safe_float(trading_performance.get("win_rate_today")), 6),
        "pnl_usdt": round(_safe_float(trading_performance.get("pnl_today_usdt")), 6),
        "max_drawdown_pct": round(_safe_float(trading_performance.get("max_drawdown_today_pct")), 6),
        "open_positions": _safe_int(trading_performance.get("open_positions_count")),
        "execution_quality_score": round(_safe_float((summary.get("system_health") or {}).get("execution_quality_score")), 4),
        "fallback_rate": round(_safe_float(scanner_health.get("fallback_rate")), 6),
        "scan_latency_avg_ms": round(_safe_float(scanner_health.get("scan_latency_avg_ms")), 4),
        "decision_latency_avg_ms": round(_safe_float(scanner_health.get("decision_latency_avg_ms")), 4),
        "risk_reject_rate": round(_safe_float(risk_engine.get("risk_reject_rate")), 6),
        "allow_count": _safe_int(risk_engine.get("allow_count")),
        "reduce_size_count": _safe_int(risk_engine.get("reduce_size_count")),
        "pass_count": _safe_int(risk_engine.get("pass_count")),
        "block_count": _safe_int(risk_engine.get("block_count")),
        "top_3_strategy_stats": strategy_stats,
        "top_3_symbol_stats": symbol_stats,
        "critical_errors": critical_errors,
    }


def export_daily_report_csv(report: dict) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "date",
            "execution_mode",
            "trades_count",
            "win_rate",
            "pnl_usdt",
            "max_drawdown_pct",
            "open_positions",
            "execution_quality_score",
            "fallback_rate",
            "scan_latency_avg_ms",
            "decision_latency_avg_ms",
            "risk_reject_rate",
            "allow_count",
            "reduce_size_count",
            "pass_count",
            "block_count",
            "top_3_strategy_stats",
            "top_3_symbol_stats",
            "critical_errors",
        ]
    )
    writer.writerow(
        [
            report.get("date"),
            report.get("execution_mode"),
            report.get("trades_count"),
            report.get("win_rate"),
            report.get("pnl_usdt"),
            report.get("max_drawdown_pct"),
            report.get("open_positions"),
            report.get("execution_quality_score"),
            report.get("fallback_rate"),
            report.get("scan_latency_avg_ms"),
            report.get("decision_latency_avg_ms"),
            report.get("risk_reject_rate"),
            report.get("allow_count"),
            report.get("reduce_size_count"),
            report.get("pass_count"),
            report.get("block_count"),
            json.dumps(report.get("top_3_strategy_stats") or [], ensure_ascii=False),
            json.dumps(report.get("top_3_symbol_stats") or [], ensure_ascii=False),
            json.dumps(report.get("critical_errors") or [], ensure_ascii=False),
        ]
    )
    return output.getvalue()
