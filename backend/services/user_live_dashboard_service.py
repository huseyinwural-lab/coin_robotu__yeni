import csv
import io
import json
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models import (
    BotProfile,
    ExecutionMetric,
    PendingSignal,
    PaperPosition,
    PositionLedgerEvent,
    RiskPolicy,
    TestnetExecutionLog,
    UserRiskSetting,
)
from services.decision_card_service import list_user_decision_cards
from services.execution_intent_service import list_user_execution_intents

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
    return sum(values) / len(values)


def _pagination(limit: int | None, offset: int | None, *, default_limit: int = 50, max_limit: int = 500) -> tuple[int, int]:
    safe_limit = _safe_int(limit, default_limit)
    safe_offset = _safe_int(offset, 0)
    safe_limit = max(1, min(max_limit, safe_limit))
    safe_offset = max(0, safe_offset)
    return safe_limit, safe_offset


def _window_bounds(window: str) -> tuple[str, datetime, datetime]:
    normalized = str(window or "1h").strip().lower()
    if normalized not in WINDOW_MAP:
        raise ValueError("window must be one of 1h, 6h, 24h")
    now = datetime.now(timezone.utc)
    since = now - WINDOW_MAP[normalized]
    return normalized, since, now


def _today_bounds_utc() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    return day_start, now


def _latest_user_risk_setting(db: Session, user_id: str) -> UserRiskSetting | None:
    return db.query(UserRiskSetting).filter(UserRiskSetting.user_id == user_id).first()


def _latest_risk_policy(db: Session, user_id: str) -> RiskPolicy | None:
    return (
        db.query(RiskPolicy)
        .filter(RiskPolicy.user_id == user_id)
        .order_by(RiskPolicy.updated_at.desc())
        .first()
    )


def _bot_summary(db: Session, user_id: str) -> dict:
    bots = db.query(BotProfile).filter(BotProfile.user_id == user_id, BotProfile.is_deleted.is_(False)).all()
    running = sum(1 for bot in bots if bool(bot.is_running) and bool(bot.is_enabled))
    paused = sum(1 for bot in bots if not bool(bot.is_running) and bool(bot.is_enabled))
    failed = sum(1 for bot in bots if not bool(bot.is_enabled))
    latest = max((bot.updated_at for bot in bots if bot.updated_at), default=None)

    return {
        "total_bots": len(bots),
        "running_bots": running,
        "paused_bots": paused,
        "failed_bots": failed,
        "bot_names": [str(bot.name or "") for bot in bots[:10]],
        "last_bot_action_at": _as_aware(latest),
    }


def build_user_live_positions(db: Session, user_id: str, *, limit: int = 50, offset: int = 0) -> dict:
    safe_limit, safe_offset = _pagination(limit, offset, default_limit=50, max_limit=500)
    rows = (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id == user_id, PaperPosition.status == "open")
        .order_by(PaperPosition.opened_at.desc())
        .all()
    )

    items: list[dict] = []
    total_unrealized = 0.0
    total_notional = 0.0
    for row in rows:
        quantity = _safe_float(row.quantity)
        entry_price = _safe_float(row.entry_price)
        unrealized = _safe_float(row.unrealized_pnl)
        current_price = entry_price + (unrealized / quantity) if quantity else entry_price

        items.append(
            {
                "position_id": row.id,
                "symbol": str(row.symbol or "").upper(),
                "side": str(row.side or "").lower(),
                "entry_price": round(entry_price, 6),
                "current_price": round(_safe_float(current_price), 6),
                "unrealized_pnl": round(unrealized, 6),
                "position_size": round(quantity, 6),
                "opened_at": _as_aware(row.opened_at),
                "bot_profile_id": row.bot_profile_id,
            }
        )
        total_unrealized += unrealized
        total_notional += abs(entry_price * quantity)

    paged_items = items[safe_offset: safe_offset + safe_limit]

    return {
        "generated_at": datetime.now(timezone.utc),
        "positions_count": len(paged_items),
        "total_positions_count": len(items),
        "limit": safe_limit,
        "offset": safe_offset,
        "total_unrealized_pnl": round(total_unrealized, 6),
        "total_position_notional": round(total_notional, 6),
        "positions": paged_items,
    }


def _closed_positions_for_window(db: Session, user_id: str, since: datetime) -> list[PaperPosition]:
    return (
        db.query(PaperPosition)
        .filter(
            PaperPosition.user_id == user_id,
            PaperPosition.closed_at.isnot(None),
            PaperPosition.closed_at >= since,
        )
        .order_by(PaperPosition.closed_at.desc())
        .all()
    )


def build_user_live_performance(db: Session, user_id: str, *, window: str = "24h") -> dict:
    normalized_window, since, now = _window_bounds(window)
    day_start, _ = _today_bounds_utc()

    closed_window = _closed_positions_for_window(db, user_id, since)
    closed_today = _closed_positions_for_window(db, user_id, day_start)

    wins_today = sum(1 for row in closed_today if _safe_float(row.realized_pnl) > 0)
    pnl_today = round(sum(_safe_float(row.realized_pnl) for row in closed_today), 6)
    win_rate_today = round(wins_today / max(len(closed_today), 1), 6) if closed_today else 0.0

    hold_minutes: list[float] = []
    for row in closed_today:
        opened_at = _as_aware(row.opened_at)
        closed_at = _as_aware(row.closed_at)
        if opened_at and closed_at and closed_at >= opened_at:
            hold_minutes.append((closed_at - opened_at).total_seconds() / 60)

    return {
        "window": normalized_window,
        "generated_at": now,
        "trades_today": len(closed_today),
        "win_rate": win_rate_today,
        "pnl_today": pnl_today,
        "avg_hold_time_minutes": round(_avg(hold_minutes), 4),
        "trades_in_window": len(closed_window),
        "pnl_in_window": round(sum(_safe_float(row.realized_pnl) for row in closed_window), 6),
    }


def build_user_live_risk(db: Session, user_id: str, *, window: str = "24h") -> dict:
    normalized_window, _since, now = _window_bounds(window)
    day_start, _ = _today_bounds_utc()

    user_risk_setting = _latest_user_risk_setting(db, user_id)
    risk_policy = _latest_risk_policy(db, user_id)
    open_positions = db.query(PaperPosition).filter(PaperPosition.user_id == user_id, PaperPosition.status == "open").all()
    closed_today = _closed_positions_for_window(db, user_id, day_start)

    base_capital = _safe_float(user_risk_setting.base_capital if user_risk_setting else 10000.0, 10000.0)
    risk_per_trade_used = _safe_float(
        (user_risk_setting.trade_risk_pct if user_risk_setting else None)
        or (risk_policy.position_size_pct if risk_policy else 0.0)
    )
    total_notional = sum(abs(_safe_float(row.entry_price) * _safe_float(row.quantity)) for row in open_positions)
    own_portfolio_exposure = round((total_notional / max(base_capital, 1.0)) * 100.0, 6)

    pnl_today = sum(_safe_float(row.realized_pnl) for row in closed_today)
    own_daily_loss_pct = round(max(0.0, (-pnl_today / max(base_capital, 1.0)) * 100.0), 6)
    daily_loss_limit_pct = _safe_float(
        (user_risk_setting.daily_loss_limit_pct if user_risk_setting else None)
        or (risk_policy.daily_loss_cutoff_pct if risk_policy else 5.0),
        5.0,
    )

    return {
        "window": normalized_window,
        "generated_at": now,
        "risk_per_trade_used": round(risk_per_trade_used, 6),
        "own_portfolio_exposure": own_portfolio_exposure,
        "own_daily_loss_pct": own_daily_loss_pct,
        "daily_loss_limit_pct": round(daily_loss_limit_pct, 6),
        "open_positions_count": len(open_positions),
        "base_capital": round(base_capital, 6),
    }


def _execution_rows(db: Session, user_id: str, since: datetime) -> list[ExecutionMetric]:
    return (
        db.query(ExecutionMetric)
        .filter(ExecutionMetric.user_id == user_id, ExecutionMetric.created_at >= since)
        .order_by(ExecutionMetric.created_at.desc())
        .limit(1000)
        .all()
    )


def _testnet_rows(db: Session, user_id: str, since: datetime) -> list[TestnetExecutionLog]:
    return (
        db.query(TestnetExecutionLog)
        .filter(TestnetExecutionLog.user_id == user_id, TestnetExecutionLog.created_at >= since)
        .order_by(TestnetExecutionLog.created_at.desc())
        .limit(1000)
        .all()
    )


def build_user_live_execution_quality(db: Session, user_id: str, *, window: str = "24h") -> dict:
    normalized_window, since, now = _window_bounds(window)
    metrics = _execution_rows(db, user_id, since)

    if metrics:
        latencies = [_safe_float(row.execution_time_ms) for row in metrics if row.execution_time_ms is not None]
        slippages = [abs(_safe_float(row.slippage_pct)) for row in metrics if row.slippage_pct is not None]
        quality_scores = [_safe_float(row.execution_quality_score) for row in metrics]
        reject_count = sum(1 for row in metrics if str(row.final_status or row.status or "").upper() in REJECT_STATUSES)
        return {
            "window": normalized_window,
            "generated_at": now,
            "sample_count": len(metrics),
            "own_execution_quality_score": round(_avg(quality_scores), 4),
            "avg_slippage": round(_avg(slippages), 6),
            "avg_latency": round(_avg(latencies), 4),
            "reject_rate": round(reject_count / max(len(metrics), 1), 6),
        }

    fallback = _testnet_rows(db, user_id, since)
    latencies = [_safe_float(row.execution_latency) for row in fallback if row.execution_latency is not None]
    slippages = [abs(_safe_float(row.slippage)) for row in fallback if row.slippage is not None]
    quality_scores = [_safe_float(row.execution_quality_score) for row in fallback]
    reject_count = sum(1 for row in fallback if str(row.status or "").upper() in REJECT_STATUSES)
    return {
        "window": normalized_window,
        "generated_at": now,
        "sample_count": len(fallback),
        "own_execution_quality_score": round(_avg(quality_scores), 4),
        "avg_slippage": round(_avg(slippages), 6),
        "avg_latency": round(_avg(latencies), 4),
        "reject_rate": round(reject_count / max(len(fallback), 1), 6) if fallback else 0.0,
    }


def _position_strategy_map(db: Session, user_id: str, positions: list[PaperPosition]) -> dict[str, str]:
    if not positions:
        return {}

    position_ids = [row.id for row in positions]
    bot_ids = {row.bot_profile_id for row in positions if row.bot_profile_id}
    bot_map = {
        row.id: row
        for row in db.query(BotProfile).filter(BotProfile.user_id == user_id, BotProfile.is_deleted.is_(False), BotProfile.id.in_(bot_ids)).all()
    }

    strategy_map: dict[str, str] = {}
    ledger_rows = (
        db.query(PositionLedgerEvent)
        .filter(PositionLedgerEvent.position_id.in_(position_ids))
        .order_by(PositionLedgerEvent.created_at.asc())
        .all()
    )
    for row in ledger_rows:
        payload = row.payload or {}
        strategy_id = str(
            payload.get("strategy_id")
            or payload.get("strategy_type")
            or payload.get("strategy")
            or ""
        ).strip()
        if strategy_id and row.position_id not in strategy_map:
            strategy_map[row.position_id] = strategy_id

    for row in positions:
        if row.id in strategy_map:
            continue
        bot = bot_map.get(row.bot_profile_id)
        strategy_map[row.id] = str((bot.strategy_type if bot else "manual_trade") or "manual_trade")

    return strategy_map


def build_user_live_strategies(
    db: Session,
    user_id: str,
    *,
    window: str = "24h",
    limit: int = 20,
    offset: int = 0,
) -> dict:
    safe_limit, safe_offset = _pagination(limit, offset, default_limit=20, max_limit=500)
    normalized_window, since, now = _window_bounds(window)
    closed_rows = _closed_positions_for_window(db, user_id, since)
    strategy_map = _position_strategy_map(db, user_id, closed_rows)

    acc: dict[str, dict] = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": 0.0, "returns": []})
    for row in closed_rows:
        key = strategy_map.get(row.id, "manual_trade")
        pnl = _safe_float(row.realized_pnl)
        notional = abs(_safe_float(row.entry_price) * _safe_float(row.quantity))
        ret = (pnl / max(notional, 1.0)) * 100.0
        acc[key]["trades"] += 1
        acc[key]["wins"] += 1 if pnl > 0 else 0
        acc[key]["pnl"] += pnl
        acc[key]["returns"].append(ret)

    items = []
    for strategy_name, value in acc.items():
        trades = value["trades"]
        win_rate = value["wins"] / max(trades, 1)
        avg_return = _avg(value["returns"])
        quality_score = max(0.0, min(100.0, (win_rate * 100.0 * 0.7) + (max(avg_return, 0.0) * 0.3)))
        items.append(
            {
                "strategy_name": strategy_name,
                "trades": trades,
                "win_rate": round(win_rate, 6),
                "avg_return": round(avg_return, 6),
                "quality_score": round(quality_score, 4),
                "pnl": round(_safe_float(value["pnl"]), 6),
            }
        )

    items.sort(key=lambda item: (item["trades"], item["quality_score"]), reverse=True)
    paged_items = items[safe_offset: safe_offset + safe_limit]
    return {
        "window": normalized_window,
        "generated_at": now,
        "strategy_count": len(paged_items),
        "total_strategy_count": len(items),
        "limit": safe_limit,
        "offset": safe_offset,
        "items": paged_items,
    }


def build_user_live_trades(
    db: Session,
    user_id: str,
    *,
    window: str = "24h",
    limit: int = 120,
    offset: int = 0,
) -> dict:
    safe_limit, safe_offset = _pagination(limit, offset, default_limit=120, max_limit=1000)
    normalized_window, since, now = _window_bounds(window)
    rows = _closed_positions_for_window(db, user_id, since)

    items = [
        {
            "trade_id": row.id,
            "timestamp": _as_aware(row.closed_at),
            "symbol": str(row.symbol or "").upper(),
            "side": str(row.side or "").lower(),
            "size": round(_safe_float(row.quantity), 6),
            "pnl": round(_safe_float(row.realized_pnl), 6),
            "entry_price": round(_safe_float(row.entry_price), 6),
            "exit_price": None,
        }
        for row in rows[:120]
    ]

    paged_items = items[safe_offset: safe_offset + safe_limit]

    return {
        "window": normalized_window,
        "generated_at": now,
        "trades_count": len(paged_items),
        "total_trades_count": len(items),
        "limit": safe_limit,
        "offset": safe_offset,
        "items": paged_items,
    }


def _build_user_alerts(db: Session, user_id: str, *, risk: dict, execution: dict, bots: dict) -> dict:
    alerts: list[dict] = []

    cooldown_count = (
        db.query(PendingSignal)
        .filter(
            PendingSignal.user_id == user_id,
            PendingSignal.status.in_(["pending", "blocked"]),
            PendingSignal.blocked_reason_code.ilike("%cooldown%"),
        )
        .count()
    )
    if cooldown_count > 0:
        alerts.append(
            {
                "code": "cooldown_active",
                "status": "warning",
                "message": "Cooldown aktif sinyal(ler) mevcut",
                "value": cooldown_count,
            }
        )

    if _safe_int(bots.get("paused_bots")) > 0:
        alerts.append(
            {
                "code": "bot_paused",
                "status": "warning",
                "message": "Duraklatılmış bot var",
                "value": _safe_int(bots.get("paused_bots")),
            }
        )

    execution_quality_score = _safe_float(execution.get("own_execution_quality_score"), 0.0)
    reject_rate = _safe_float(execution.get("reject_rate"), 0.0)
    if execution_quality_score < 55 or reject_rate > 0.2:
        alerts.append(
            {
                "code": "execution_warning",
                "status": "warning",
                "message": "Execution kalitesi eşik altına indi",
                "value": {
                    "quality_score": round(execution_quality_score, 4),
                    "reject_rate": round(reject_rate, 6),
                },
            }
        )

    exposure = _safe_float(risk.get("own_portfolio_exposure"), 0.0)
    daily_loss_pct = _safe_float(risk.get("own_daily_loss_pct"), 0.0)
    daily_loss_limit_pct = _safe_float(risk.get("daily_loss_limit_pct"), 5.0)
    if exposure >= 75.0 or daily_loss_pct >= (daily_loss_limit_pct * 0.8):
        alerts.append(
            {
                "code": "risk_limit_near",
                "status": "warning",
                "message": "Risk limitine yaklaşılıyor",
                "value": {
                    "exposure_pct": round(exposure, 6),
                    "daily_loss_pct": round(daily_loss_pct, 6),
                    "daily_loss_limit_pct": round(daily_loss_limit_pct, 6),
                },
            }
        )

    overall_status = "normal" if not alerts else "warning"
    return {
        "status": overall_status,
        "items": alerts,
    }


def build_user_live_summary(db: Session, user_id: str, *, window: str = "1h") -> dict:
    normalized_window, _since, now = _window_bounds(window)
    bots = _bot_summary(db, user_id)
    positions = build_user_live_positions(db, user_id)
    performance = build_user_live_performance(db, user_id, window="24h")
    risk = build_user_live_risk(db, user_id, window="24h")
    execution = build_user_live_execution_quality(db, user_id, window=normalized_window)
    strategies = build_user_live_strategies(db, user_id, window=normalized_window)
    trades = build_user_live_trades(db, user_id, window=normalized_window)
    alerts = _build_user_alerts(db, user_id, risk=risk, execution=execution, bots=bots)

    return {
        "window": normalized_window,
        "generated_at": now,
        "bots": bots,
        "open_positions": {
            "positions_count": positions.get("positions_count", 0),
            "total_unrealized_pnl": positions.get("total_unrealized_pnl", 0.0),
            "total_position_notional": positions.get("total_position_notional", 0.0),
        },
        "performance": performance,
        "risk": risk,
        "execution": execution,
        "strategies": {
            "strategy_count": strategies.get("strategy_count", 0),
            "top": list(strategies.get("items") or [])[:5],
        },
        "trades": {
            "trades_count": trades.get("trades_count", 0),
            "recent": list(trades.get("items") or [])[:10],
        },
        "alerts": alerts,
    }


def build_user_live_queue(db: Session, user_id: str, *, limit: int = 20) -> dict:
    intents = list_user_execution_intents(db, user_id, limit=limit)
    signal_rows = (
        db.query(PendingSignal)
        .filter(PendingSignal.user_id == user_id)
        .order_by(PendingSignal.created_at.desc())
        .limit(limit)
        .all()
    )
    pending_orders = []
    for row in intents:
      pending_orders.append(
            {
                "intent_id": row.intent_id,
                "symbol": str(row.symbol or "").upper(),
                "intent_type": row.intent_type,
                "status": row.status,
                "gate_decision": row.gate_decision,
                "meta_engine_decision": row.meta_engine_decision,
                "risk_score": round(_safe_float(row.risk_score), 6),
                "created_at": _as_aware(row.created_at),
            }
        )
    pending_decisions = []
    for row in signal_rows:
        pending_decisions.append(
            {
                "signal_id": row.signal_id,
                "symbol": str(row.symbol or "").upper(),
                "status": row.status,
                "blocked_reason_code": row.blocked_reason_code,
                "strategy_code": row.strategy_code,
                "confidence": round(_safe_float(row.confidence), 6),
                "created_at": _as_aware(row.created_at),
            }
        )
    return {
        "generated_at": datetime.now(timezone.utc),
        "pending_orders": pending_orders,
        "pending_decisions": pending_decisions,
        "queue_depth": len(pending_orders),
    }


def build_user_live_runtime_snapshot(db: Session, user_id: str, *, window: str = "1h") -> dict:
    summary = build_user_live_summary(db, user_id, window=window)
    positions = build_user_live_positions(db, user_id, limit=8, offset=0)
    strategies = build_user_live_strategies(db, user_id, window=window, limit=8, offset=0)
    trades = build_user_live_trades(db, user_id, window=window, limit=8, offset=0)
    queue = build_user_live_queue(db, user_id, limit=12)
    decisions = list_user_decision_cards(db, user_id, limit=8)
    return {
        "generated_at": datetime.now(timezone.utc),
        "summary": summary,
        "positions": positions,
        "strategies": strategies,
        "trades": trades,
        "queue": queue,
        "decision_cards": decisions,
        "alerts": (summary.get("alerts") or {}).get("items") or [],
    }


def build_user_live_daily_report(db: Session, user_id: str, *, window: str = "24h") -> dict:
    normalized_window, _since, now = _window_bounds(window)
    day_start, _ = _today_bounds_utc()

    summary = build_user_live_summary(db, user_id, window=normalized_window)
    performance = summary.get("performance") or {}
    risk = summary.get("risk") or {}
    execution = summary.get("execution") or {}
    strategies = (summary.get("strategies") or {}).get("top") or []
    trades = (summary.get("trades") or {}).get("recent") or []
    alerts = (summary.get("alerts") or {}).get("items") or []

    return {
        "report_id": str(uuid.uuid4()),
        "date": day_start.date().isoformat(),
        "window": normalized_window,
        "generated_at": now,
        "trades_today": _safe_int(performance.get("trades_today")),
        "win_rate": round(_safe_float(performance.get("win_rate")), 6),
        "pnl_today": round(_safe_float(performance.get("pnl_today")), 6),
        "avg_hold_time_minutes": round(_safe_float(performance.get("avg_hold_time_minutes")), 4),
        "risk_per_trade_used": round(_safe_float(risk.get("risk_per_trade_used")), 6),
        "own_portfolio_exposure": round(_safe_float(risk.get("own_portfolio_exposure")), 6),
        "own_daily_loss_pct": round(_safe_float(risk.get("own_daily_loss_pct")), 6),
        "own_execution_quality_score": round(_safe_float(execution.get("own_execution_quality_score")), 4),
        "avg_slippage": round(_safe_float(execution.get("avg_slippage")), 6),
        "avg_latency": round(_safe_float(execution.get("avg_latency")), 4),
        "reject_rate": round(_safe_float(execution.get("reject_rate")), 6),
        "open_positions_count": _safe_int((summary.get("open_positions") or {}).get("positions_count")),
        "top_strategies": strategies,
        "recent_trades": trades,
        "alerts": alerts,
    }


def export_user_live_daily_report_csv(report: dict) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "date",
            "window",
            "trades_today",
            "win_rate",
            "pnl_today",
            "avg_hold_time_minutes",
            "risk_per_trade_used",
            "own_portfolio_exposure",
            "own_daily_loss_pct",
            "own_execution_quality_score",
            "avg_slippage",
            "avg_latency",
            "reject_rate",
            "open_positions_count",
            "top_strategies",
            "recent_trades",
            "alerts",
        ]
    )
    writer.writerow(
        [
            report.get("date"),
            report.get("window"),
            report.get("trades_today"),
            report.get("win_rate"),
            report.get("pnl_today"),
            report.get("avg_hold_time_minutes"),
            report.get("risk_per_trade_used"),
            report.get("own_portfolio_exposure"),
            report.get("own_daily_loss_pct"),
            report.get("own_execution_quality_score"),
            report.get("avg_slippage"),
            report.get("avg_latency"),
            report.get("reject_rate"),
            report.get("open_positions_count"),
            json.dumps(report.get("top_strategies") or [], ensure_ascii=False),
            json.dumps(report.get("recent_trades") or [], ensure_ascii=False),
            json.dumps(report.get("alerts") or [], ensure_ascii=False),
        ]
    )
    return output.getvalue()