import csv
import io
import json
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models import (
    BacktestResultCard,
    BotProfile,
    ExecutionMetric,
    PendingSignal,
    PaperPosition,
    PositionLedgerEvent,
    RiskPolicy,
    LiveExecutionLog,
    UserDecisionTrace,
    UserExecutionIntent,
    UserRiskSetting,
    UserTradeProjection,
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


def _live_rows(db: Session, user_id: str, since: datetime) -> list[LiveExecutionLog]:
    return (
        db.query(LiveExecutionLog)
        .filter(LiveExecutionLog.user_id == user_id, LiveExecutionLog.created_at >= since)
        .order_by(LiveExecutionLog.created_at.desc())
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

    fallback = _live_rows(db, user_id, since)
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


def _upsert_trade_projection(db: Session, *, user_id: str, trade_id: str, payload: dict) -> UserTradeProjection:
    row = db.query(UserTradeProjection).filter(UserTradeProjection.trade_id == trade_id).first()
    if row is None:
        row = UserTradeProjection(trade_id=trade_id, user_id=user_id, symbol=str(payload.get("symbol") or "").upper())
        db.add(row)
    for key, value in payload.items():
        setattr(row, key, value)
    return row


def sync_user_trade_projection(db: Session, *, user_id: str) -> dict:
    positions = db.query(PaperPosition).filter(PaperPosition.user_id == user_id).all()
    intents = db.query(UserExecutionIntent).filter(UserExecutionIntent.user_id == user_id).all()
    metrics = db.query(ExecutionMetric).filter(ExecutionMetric.user_id == user_id).all()
    strategy_map = _position_strategy_map(db, user_id, positions)

    synced = 0
    for row in positions:
        metric = next((item for item in metrics if str(item.symbol or "").upper() == str(row.symbol or "").upper()), None)
        payload = {
            "position_id": row.id,
            "status": "CLOSED" if str(row.status or "") == "closed" else "OPEN",
            "symbol": str(row.symbol or "").upper(),
            "side": str(row.side or "buy").lower(),
            "quantity": round(_safe_float(row.quantity), 8),
            "avg_fill_price": round(_safe_float(row.entry_price), 8),
            "fees": 0.0,
            "slippage": round(_safe_float(getattr(metric, "slippage_pct", 0.0) or 0.0), 8) if metric else None,
            "opened_at": _as_aware(row.opened_at or row.created_at),
            "closed_at": _as_aware(row.closed_at),
            "realized_pnl": round(_safe_float(row.realized_pnl), 8),
            "unrealized_pnl": round(_safe_float(row.unrealized_pnl), 8),
            "strategy_name": strategy_map.get(row.id),
            "strategy_template_id": None,
            "strategy_version_id": None,
            "scan_run_id": None,
            "signal_id": None,
            "decision_card_id": None,
            "reconciliation_status": "OK",
            "reconciliation_reason": None,
            "trace_available": "true",
            "explainability_status": "available",
            "meta_json": {
                "trade_source": "position_projection",
                "allocation_source": strategy_map.get(row.id),
                "market_type": str(row.market_type or "spot").lower(),
                "execution_metric_id": metric.id if metric else None,
            },
        }
        _upsert_trade_projection(db, user_id=user_id, trade_id=str(row.id), payload=payload)
        synced += 1

    for row in intents:
        status = str(row.status or "").upper()
        if status not in {"PREVIEWED", "QUEUED", "APPROVED", "SUBMITTED", "REJECTED", "CANCELLED"}:
            continue
        payload = {
            "intent_id": row.intent_id,
            "status": "PENDING" if status in {"PREVIEWED", "QUEUED", "APPROVED", "SUBMITTED"} else status,
            "symbol": str(row.symbol or "").upper(),
            "side": str(row.side or "buy").lower(),
            "quantity": round(_safe_float(row.size), 8),
            "avg_fill_price": round(_safe_float(row.price), 8) if row.price is not None else None,
            "opened_at": _as_aware(row.created_at),
            "closed_at": _as_aware(getattr(row, "updated_at", None)),
            "realized_pnl": None,
            "unrealized_pnl": None,
            "strategy_name": str((row.normalized_order_payload or {}).get("strategy_type") or "manual_trade"),
            "strategy_template_id": (row.normalized_order_payload or {}).get("strategy_template_id"),
            "strategy_version_id": (row.normalized_order_payload or {}).get("strategy_template_version") or (row.normalized_order_payload or {}).get("template_code"),
            "scan_run_id": (row.normalized_order_payload or {}).get("scan_run_id"),
            "signal_id": (row.normalized_order_payload or {}).get("signal_id"),
            "decision_card_id": (row.normalized_order_payload or {}).get("decision_card_id"),
            "reconciliation_status": "PENDING",
            "reconciliation_reason": str(getattr(row, "reject_reason", None) or "pending_execution"),
            "trace_available": "true",
            "explainability_status": "available",
            "meta_json": {
                "trade_source": "intent_projection",
                "intent_token": row.intent_token,
                "market_type": str(row.market_type or "spot").lower(),
                "meta_engine_decision": row.meta_engine_decision,
                "allocation_source": (row.normalized_order_payload or {}).get("strategy_type"),
            },
        }
        _upsert_trade_projection(db, user_id=user_id, trade_id=str(row.position_id or row.id), payload=payload)

    db.commit()
    return {"synced": synced, "intent_rows": len(intents)}


def build_user_trade_projection_list(db: Session, user_id: str, *, limit: int = 120) -> list[dict]:
    sync_user_trade_projection(db, user_id=user_id)
    rows = db.query(UserTradeProjection).filter(UserTradeProjection.user_id == user_id).order_by(UserTradeProjection.updated_at.desc()).limit(limit).all()
    return [
        {
            "source": (row.meta_json or {}).get("trade_source", "projection"),
            "trade_id": row.trade_id,
            "symbol": row.symbol,
            "market_type": (row.meta_json or {}).get("market_type") or "spot",
            "side": row.side,
            "status": row.status,
            "quantity": row.quantity,
            "entry_price": row.avg_fill_price,
            "exit_price": None,
            "realized_pnl": row.realized_pnl,
            "unrealized_pnl": row.unrealized_pnl,
            "opened_at": row.opened_at,
            "closed_at": row.closed_at,
            "strategy_weight": None,
            "allocation_source": (row.meta_json or {}).get("allocation_source"),
            "meta_engine_decision": (row.meta_json or {}).get("meta_engine_decision"),
            "trace_available": str(row.trace_available or "false").lower() == "true",
            "has_explainability": row.explainability_status == "available",
            "reconciliation_status": row.reconciliation_status,
            "strategy": row.strategy_name,
            "strategy_template_id": row.strategy_template_id,
            "strategy_version_id": row.strategy_version_id,
            "scan_run_id": row.scan_run_id,
            "signal_id": row.signal_id,
            "decision_card_id": row.decision_card_id,
            "intent_id": row.intent_id,
            "execution_trace_id": row.execution_trace_id,
        }
        for row in rows
    ]


def build_user_trade_open_orders(db: Session, user_id: str, *, limit: int = 80) -> list[dict]:
    rows = db.query(UserExecutionIntent).filter(UserExecutionIntent.user_id == user_id, UserExecutionIntent.status.in_(["PREVIEWED", "QUEUED", "APPROVED", "SUBMITTED"])) .order_by(UserExecutionIntent.created_at.desc()).limit(limit).all()
    return [
        {
            "symbol": str(row.symbol or "").upper(),
            "side": row.side,
            "market_type": str(row.market_type or "spot").lower(),
            "size": row.size,
            "status": row.status,
            "submitted_at": row.created_at,
            "venue": (row.normalized_order_payload or {}).get("exchange") or "binance",
            "reduce_only": bool((row.normalized_order_payload or {}).get("reduce_only", False)),
            "queue_status": row.status,
            "intent_source": row.intent_type,
            "intent_id": row.intent_id,
        }
        for row in rows
    ]


def build_user_trade_pending_orders(db: Session, user_id: str, *, limit: int = 80) -> list[dict]:
    return build_user_trade_open_orders(db, user_id, limit=limit)


def build_user_trade_detail(db: Session, user_id: str, trade_id: str) -> dict:
    sync_user_trade_projection(db, user_id=user_id)
    row = db.query(UserTradeProjection).filter(UserTradeProjection.user_id == user_id, UserTradeProjection.trade_id == trade_id).first()
    if row is None:
        raise ValueError("trade_not_found")
    traces = db.query(UserDecisionTrace).filter(UserDecisionTrace.user_id == user_id).order_by(UserDecisionTrace.created_at.desc()).limit(10).all()
    lifecycle = []
    for event_name, timestamp in [
        ("created", row.created_at),
        ("reviewed", row.opened_at),
        ("queued", row.opened_at),
        ("filled", row.opened_at if row.status in {"OPEN", "PARTIALLY_FILLED", "FILLED", "CLOSED"} else None),
        ("updated", row.updated_at),
        ("closed", row.closed_at),
    ]:
        if timestamp:
            lifecycle.append({"event": event_name, "at": timestamp})
    internal_pnl = _safe_float(row.realized_pnl, 0.0) + _safe_float(row.unrealized_pnl, 0.0)
    execution_pnl = _safe_float(row.slippage, 0.0)
    return {
        "trade": {
            "trade_id": row.trade_id,
            "symbol": row.symbol,
            "market_type": (row.meta_json or {}).get("market_type") or "spot",
            "side": row.side,
            "status": row.status,
            "quantity": row.quantity,
            "avg_fill_price": row.avg_fill_price,
            "fees": row.fees,
            "slippage": row.slippage,
            "realized_pnl": row.realized_pnl,
            "unrealized_pnl": row.unrealized_pnl,
            "opened_at": row.opened_at,
            "closed_at": row.closed_at,
            "strategy": row.strategy_name,
            "trace_available": str(row.trace_available or "false").lower() == "true",
            "strategy_template_id": row.strategy_template_id,
            "strategy_version_id": row.strategy_version_id,
            "scan_run_id": row.scan_run_id,
            "signal_id": row.signal_id,
            "decision_card_id": row.decision_card_id,
        },
        "fills": [row.meta_json] if row.meta_json else [],
        "timeline": lifecycle,
        "queue_execution_trace": {
            "intent_id": row.intent_id,
            "order_id": row.order_id,
            "execution_trace_id": row.execution_trace_id,
            "scan_run_id": row.scan_run_id,
            "signal_id": row.signal_id,
            "decision_card_id": row.decision_card_id,
        },
        "risk_policy_summary": {
            "gate_decision": (row.meta_json or {}).get("gate_decision"),
            "meta_engine_decision": (row.meta_json or {}).get("meta_engine_decision"),
        },
        "why_this_trade_happened": {
            "signal_source": (row.meta_json or {}).get("trade_source"),
            "strategy_reason": traces[0].strategy_allocation_reason if traces else None,
            "confidence_score": traces[0].portfolio_risk_score if traces else None,
            "policy_result": (row.meta_json or {}).get("gate_decision"),
            "allocation_decision": (row.meta_json or {}).get("allocation_source"),
            "execution_result": row.status,
            "source_template": {
                "strategy_template_id": row.strategy_template_id,
                "strategy_version_id": row.strategy_version_id,
                "scan_run_id": row.scan_run_id,
            },
        },
        "reconciliation": {
            "internal_pnl": round(internal_pnl, 8),
            "execution_metric_pnl": round(execution_pnl, 8),
            "delta": round(internal_pnl - execution_pnl, 8),
            "status": row.reconciliation_status,
            "reason": row.reconciliation_reason,
            "last_reconciled_at": row.updated_at,
        },
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


def build_user_strategy_performance_bridge(db: Session, user_id: str, *, window: str = "24h") -> dict:
    live = build_user_live_strategies(db, user_id, window=window, limit=100, offset=0)
    live_items = list(live.get("items") or [])
    backtests = db.query(BacktestResultCard).order_by(BacktestResultCard.updated_at.desc()).all()
    backtest_by_strategy = {str(row.strategy_type or ""): row for row in backtests}
    items = []
    for row in live_items:
        strategy_id = str(row.get("strategy_name") or row.get("strategy_type") or "unknown")
        backtest = backtest_by_strategy.get(strategy_id)
        live_return = _safe_float(row.get("avg_return"), 0.0)
        live_hit = _safe_float(row.get("win_rate"), 0.0)
        backtest_pf = _safe_float(getattr(backtest, "profit_factor", None), 0.0)
        backtest_win = _safe_float(getattr(backtest, "win_rate", None), 0.0)
        divergence_pct = round((live_return * 100) - backtest_win, 6)
        items.append(
            {
                "strategy_id": strategy_id,
                "parameter_hash": strategy_id,
                "backtest": {
                    "win_rate": backtest_win,
                    "max_drawdown": _safe_float(getattr(backtest, "max_drawdown", None), 0.0),
                    "profit_factor": backtest_pf,
                    "sample_size": int(getattr(backtest, "sample_size", 0) or 0),
                    "risk_label": getattr(backtest, "risk_label", None),
                },
                "live": {
                    "trades": int(row.get("trades") or 0),
                    "win_rate": live_hit,
                    "avg_return": live_return,
                    "quality_score": _safe_float(row.get("quality_score"), 0.0),
                },
                "deviation_pct": divergence_pct,
            }
        )
    return {"window": window, "items": items}


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