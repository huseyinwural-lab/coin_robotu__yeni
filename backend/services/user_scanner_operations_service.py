import csv
import io
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models import ExecutionMetric, PaperPosition, UserExecutionIntent, UserRiskSetting
from services.pipeline.cache_store import get_json

WINDOW_MAP = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
}

REJECT_STATUSES = {"REJECTED", "FAILED", "CANCELLED", "EXPIRED"}


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _window_bounds(window: str) -> tuple[str, datetime, datetime]:
    normalized = str(window or "24h").strip().lower()
    if normalized not in WINDOW_MAP:
        raise ValueError("window must be one of 1h, 6h, 24h")
    now = datetime.now(timezone.utc)
    since = now - WINDOW_MAP[normalized]
    return normalized, since, now


def _today_start_utc() -> datetime:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc)


def _base_capital(db: Session, user_id: str) -> float:
    row = db.query(UserRiskSetting).filter(UserRiskSetting.user_id == user_id).first()
    return max(_safe_float((row.base_capital if row else None), 10000.0), 1.0)


def _scanner_intents(db: Session, user_id: str, since: datetime) -> list[UserExecutionIntent]:
    return (
        db.query(UserExecutionIntent)
        .filter(
            UserExecutionIntent.user_id == user_id,
            UserExecutionIntent.created_at >= since,
            UserExecutionIntent.source_type.in_(["scanner", "manual"]),
        )
        .order_by(UserExecutionIntent.created_at.desc())
        .limit(1000)
        .all()
    )


def _execution_quality(db: Session, user_id: str, since: datetime) -> dict:
    rows = (
        db.query(ExecutionMetric)
        .filter(ExecutionMetric.user_id == user_id, ExecutionMetric.created_at >= since)
        .order_by(ExecutionMetric.created_at.desc())
        .limit(1000)
        .all()
    )
    latencies = [_safe_float(row.execution_time_ms) for row in rows if row.execution_time_ms is not None]
    slippages = [abs(_safe_float(row.slippage_pct)) for row in rows if row.slippage_pct is not None]
    reject_count = sum(1 for row in rows if str(row.final_status or row.status or "").upper() in REJECT_STATUSES)
    return {
        "trades": len(rows),
        "avg_latency": round(sum(latencies) / len(latencies), 4) if latencies else 0.0,
        "avg_slippage": round(sum(slippages) / len(slippages), 6) if slippages else 0.0,
        "reject_rate": round(reject_count / max(len(rows), 1), 6) if rows else 0.0,
    }


def _risk_metrics(db: Session, user_id: str) -> dict:
    base_capital = _base_capital(db, user_id)
    open_rows = db.query(PaperPosition).filter(PaperPosition.user_id == user_id, PaperPosition.status == "open").all()
    day_start = _today_start_utc()
    closed_today = (
        db.query(PaperPosition)
        .filter(
            PaperPosition.user_id == user_id,
            PaperPosition.status == "closed",
            PaperPosition.closed_at.isnot(None),
            PaperPosition.closed_at >= day_start,
        )
        .all()
    )
    open_notional = sum(abs(_safe_float(row.entry_price) * _safe_float(row.quantity)) for row in open_rows)
    realized_today = sum(_safe_float(row.realized_pnl) for row in closed_today)
    daily_loss_pct = max(0.0, (-realized_today / base_capital) * 100.0)
    return {
        "portfolio_exposure": round((open_notional / base_capital) * 100.0, 6),
        "daily_loss_pct": round(daily_loss_pct, 6),
        "max_positions": 3,
        "daily_loss_limit_pct": 1.0,
    }


def _scanner_activity(cache, user_id: str) -> dict:
    runtime = get_json(cache, f"scanner:runtime:latest:{user_id}") or {}
    perf = runtime.get("scanner_perf") or {}
    tiered = runtime.get("tiered_scan") or {}
    qualification = tiered.get("qualification") or {}
    return {
        "symbols_scanned": int(perf.get("symbols_evaluated") or 0),
        "candidates": int(perf.get("decision_scope_symbols") or 0),
        "qualified": int(qualification.get("qualified_count") or 0),
        "signals": int(runtime.get("result", {}).get("actionable_count") or 0),
    }


def _strategy_distribution(intents: list[UserExecutionIntent]) -> dict:
    counter = Counter(str((row.normalized_order_payload or {}).get("strategy_binding") or "manual_execution") for row in intents)
    return dict(counter)


def _symbol_integrity(intents: list[UserExecutionIntent]) -> dict:
    total = 0
    matched = 0
    mismatches: list[dict] = []
    for row in intents:
        payload = row.normalized_order_payload or {}
        scanner_snapshot = payload.get("scanner_signal_snapshot") or {}
        scanner_symbol = str(scanner_snapshot.get("symbol") or payload.get("symbol") or "").strip().upper()
        order_symbol = str(row.symbol or payload.get("symbol") or "").strip().upper()
        if not scanner_symbol and not order_symbol:
            continue
        total += 1
        if scanner_symbol == order_symbol:
            matched += 1
        else:
            mismatches.append(
                {
                    "intent_id": row.id,
                    "scanner_symbol": scanner_symbol,
                    "order_symbol": order_symbol,
                }
            )
    return {
        "checked": total,
        "matched": matched,
        "mismatch": max(total - matched, 0),
        "ok": (total == matched),
        "examples": mismatches[:10],
    }


def build_user_scanner_live_readiness(db: Session, user_id: str, cache, *, window: str = "24h") -> dict:
    normalized_window, since, now = _window_bounds(window)
    intents = _scanner_intents(db, user_id, since)
    scanner_activity = _scanner_activity(cache, user_id)
    execution = _execution_quality(db, user_id, since)
    risk = _risk_metrics(db, user_id)

    kill_switch_active = str(cache.get("pipeline:kill_switch") or "0") == "1"
    market_payload = get_json(cache, "spot_strategy:latest_selection") or {}
    strategy_distribution = _strategy_distribution(intents)

    return {
        "window": normalized_window,
        "generated_at": now,
        "symbol_integrity": _symbol_integrity(intents),
        "max_risk_guard": {
            "max_positions": 3,
            "daily_loss_limit_pct": 1.0,
            "portfolio_exposure": risk["portfolio_exposure"],
            "daily_loss_pct": risk["daily_loss_pct"],
            "ok": risk["daily_loss_pct"] < 1.0,
        },
        "execution_quality": {
            **execution,
            "latency_threshold_ms": 500,
            "reject_rate_threshold": 0.02,
            "ok": execution["avg_latency"] < 500 and execution["reject_rate"] < 0.02,
        },
        "scanner_activity": scanner_activity,
        "market_regime": {
            "market_regime": market_payload.get("market_regime"),
            "market_bias_regime": market_payload.get("market_bias_regime"),
            "stress_action": "size küçült" if str(market_payload.get("market_bias_regime") or "").lower() == "hostile" else "normal",
            "spread_action": "skip" if execution["reject_rate"] >= 0.02 else "normal",
        },
        "strategy_diversity": {
            "strategy_distribution": strategy_distribution,
            "total_strategies": len(strategy_distribution),
        },
        "emergency_stop": {
            "kill_switch": kill_switch_active,
            "new_trades_blocked": bool(kill_switch_active),
        },
        "first_live_test_params": {
            "symbols": "10-20",
            "max_positions": 3,
            "risk_per_trade": "düşük",
            "auto_mode": "assisted",
        },
    }


def build_user_scanner_daily_report(db: Session, user_id: str, cache, *, window: str = "24h") -> dict:
    normalized_window, _since, now = _window_bounds(window)
    readiness = build_user_scanner_live_readiness(db, user_id, cache, window=normalized_window)

    return {
        "date": now.date().isoformat(),
        "window": normalized_window,
        "generated_at": now,
        "scan": {
            "symbols_scanned": readiness["scanner_activity"]["symbols_scanned"],
            "candidates": readiness["scanner_activity"]["candidates"],
            "qualified": readiness["scanner_activity"]["qualified"],
            "signals": readiness["scanner_activity"]["signals"],
        },
        "execution": {
            "trades": readiness["execution_quality"]["trades"],
            "avg_slippage": readiness["execution_quality"]["avg_slippage"],
            "avg_latency": readiness["execution_quality"]["avg_latency"],
            "reject_rate": readiness["execution_quality"]["reject_rate"],
        },
        "risk": {
            "portfolio_exposure": readiness["max_risk_guard"]["portfolio_exposure"],
            "daily_loss_pct": readiness["max_risk_guard"]["daily_loss_pct"],
        },
        "strategies": {
            "strategy_distribution": readiness["strategy_diversity"]["strategy_distribution"],
        },
    }


def export_user_scanner_daily_report_csv(report: dict) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "date",
            "window",
            "symbols_scanned",
            "candidates",
            "qualified",
            "signals",
            "trades",
            "avg_slippage",
            "avg_latency",
            "reject_rate",
            "portfolio_exposure",
            "daily_loss_pct",
            "strategy_distribution",
        ]
    )
    writer.writerow(
        [
            report.get("date"),
            report.get("window"),
            (report.get("scan") or {}).get("symbols_scanned"),
            (report.get("scan") or {}).get("candidates"),
            (report.get("scan") or {}).get("qualified"),
            (report.get("scan") or {}).get("signals"),
            (report.get("execution") or {}).get("trades"),
            (report.get("execution") or {}).get("avg_slippage"),
            (report.get("execution") or {}).get("avg_latency"),
            (report.get("execution") or {}).get("reject_rate"),
            (report.get("risk") or {}).get("portfolio_exposure"),
            (report.get("risk") or {}).get("daily_loss_pct"),
            (report.get("strategies") or {}).get("strategy_distribution"),
        ]
    )
    return output.getvalue()