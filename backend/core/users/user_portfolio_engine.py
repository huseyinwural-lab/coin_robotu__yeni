from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from core.users.user_portfolio_mapper import map_user_portfolio
from core.users.user_risk_settings import get_or_create_user_risk_settings
from models import ExecutionMetric, PaperPosition, PendingSignal, UserDecisionTrace, UserExchangeConnection


def _safe_float(value: float | None) -> float:
    return float(value or 0)


def _is_settings_synced_connection(row: UserExchangeConnection) -> bool:
    snapshot = row.readiness_snapshot if isinstance(row.readiness_snapshot, dict) else {}
    source = str(snapshot.get("source") or "").strip().lower()
    label = str(row.account_label or "").strip().upper()
    return source == "phase4_exchange_settings_sync" or label.startswith("SETTINGS ")


def _snapshot_wallet_balance(snapshot: dict) -> float:
    wallet_value = _safe_float(snapshot.get("wallet_balance"))
    return wallet_value if wallet_value > 0 else 0.0


def _snapshot_trade_ready(snapshot: dict) -> bool:
    health = str(snapshot.get("connection_health") or "").strip().lower()
    can_trade = bool(snapshot.get("can_trade"))
    validation_success = bool(snapshot.get("validation_success") or snapshot.get("is_valid"))
    if health == "online" and can_trade:
        return True
    return validation_success and can_trade


def _pick_wallet_connection(rows: list[UserExchangeConnection], market_type: str) -> UserExchangeConnection | None:
    filtered = [
        row
        for row in rows
        if str(row.market_type or "").strip().lower() == market_type
        and str(row.environment or "live").strip().lower() == "live"
    ]
    if not filtered:
        return None

    def _score(row: UserExchangeConnection):
        snapshot = row.readiness_snapshot if isinstance(row.readiness_snapshot, dict) else {}
        wallet_score = 1 if _snapshot_wallet_balance(snapshot) > 0 else 0
        readiness_score = 1 if _snapshot_trade_ready(snapshot) else 0
        settings_score = 1 if _is_settings_synced_connection(row) else 0
        default_score = 1 if row.is_default else 0
        updated_score = row.updated_at or datetime.min.replace(tzinfo=timezone.utc)
        return wallet_score, readiness_score, settings_score, default_score, updated_score

    filtered.sort(key=_score, reverse=True)
    return filtered[0]


def _wallet_balance_from_connection(row: UserExchangeConnection | None) -> float:
    if row is None:
        return 0.0
    snapshot = row.readiness_snapshot if isinstance(row.readiness_snapshot, dict) else {}
    return _snapshot_wallet_balance(snapshot)


def build_user_portfolio_snapshot(db: Session, user_id: str) -> dict:
    mapped = map_user_portfolio(db, user_id=user_id, market_type="futures", leverage=1)
    connection = (
        db.query(UserExchangeConnection)
        .filter(UserExchangeConnection.user_id == user_id)
        .order_by(UserExchangeConnection.is_default.desc(), UserExchangeConnection.updated_at.desc())
        .first()
    )
    readiness_snapshot = connection.readiness_snapshot if connection and isinstance(connection.readiness_snapshot, dict) else {}
    can_trade_live = bool(readiness_snapshot.get("can_trade")) and bool(
        readiness_snapshot.get("validation_success") or readiness_snapshot.get("is_valid")
    )
    execution_mode = "live" if can_trade_live else "mocked"
    open_positions_count = int(mapped["open_positions_count"])
    closed_positions_count = (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id == user_id, PaperPosition.status != "open")
        .count()
    )
    live_wallet_balance = _safe_float(readiness_snapshot.get("wallet_balance"))
    live_available_balance = _safe_float(readiness_snapshot.get("available_balance"))

    if can_trade_live:
        current_capital = live_wallet_balance if live_wallet_balance > 0 else mapped["current_capital"]
        available_balance = live_available_balance if live_available_balance > 0 else mapped["available_balance"]
    else:
        # canlıya çıkış öncesi test/paper bakiye gösterimini sıfırla
        current_capital = 0.0
        available_balance = 0.0

    all_connections = (
        db.query(UserExchangeConnection)
        .filter(UserExchangeConnection.user_id == user_id)
        .order_by(UserExchangeConnection.updated_at.desc())
        .all()
    )

    spot_connection = _pick_wallet_connection(all_connections, "spot")
    futures_connection = _pick_wallet_connection(all_connections, "futures")

    spot_wallet_balance = _wallet_balance_from_connection(spot_connection)
    futures_wallet_balance = _wallet_balance_from_connection(futures_connection)

    total_wallet_balance = round(spot_wallet_balance + futures_wallet_balance, 8)

    return {
        "total_wallet_balance": total_wallet_balance,
        "spot_wallet_balance": round(spot_wallet_balance, 8),
        "futures_wallet_balance": round(futures_wallet_balance, 8),
        "current_capital": current_capital,
        "available_balance": available_balance,
        "execution_mode": execution_mode,
        "open_notional": mapped["open_notional"],
        "open_unrealized_pnl": mapped["open_unrealized_pnl"],
        "closed_pnl": mapped["closed_pnl"],
        "open_positions_count": open_positions_count,
        "closed_positions_count": int(closed_positions_count),
        "allocation_capital": mapped["allocation_capital"],
        "next_trade_base_capital": mapped["next_trade_base_capital"],
        "compounding_enabled": mapped["compounding_enabled"],
    }


def build_user_performance_snapshot(db: Session, user_id: str, lookback_days: int = 30) -> dict:
    risk_row = get_or_create_user_risk_settings(db, user_id)
    now = datetime.now(timezone.utc)
    from_ts = now - timedelta(days=lookback_days)

    closed_rows = (
        db.query(PaperPosition)
        .filter(
            PaperPosition.user_id == user_id,
            PaperPosition.status != "open",
            PaperPosition.closed_at.is_not(None),
            PaperPosition.closed_at >= from_ts,
        )
        .all()
    )
    open_rows = (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id == user_id, PaperPosition.status == "open")
        .all()
    )
    execution_rows = (
        db.query(ExecutionMetric)
        .filter(ExecutionMetric.user_id == user_id, ExecutionMetric.created_at >= from_ts)
        .all()
    )

    realized_pnl_total = round(sum(_safe_float(item.realized_pnl) for item in closed_rows), 2)
    unrealized_pnl_total = round(sum(_safe_float(item.unrealized_pnl) for item in open_rows), 2)
    wins = len([item for item in closed_rows if _safe_float(item.realized_pnl) > 0])
    losses = len([item for item in closed_rows if _safe_float(item.realized_pnl) < 0])
    total_closed = len(closed_rows)
    win_rate = round((wins / total_closed) * 100, 2) if total_closed else 0.0

    gross_profit = sum(_safe_float(item.realized_pnl) for item in closed_rows if _safe_float(item.realized_pnl) > 0)
    gross_loss_abs = abs(sum(_safe_float(item.realized_pnl) for item in closed_rows if _safe_float(item.realized_pnl) < 0))
    if gross_loss_abs == 0:
        profit_factor = round(gross_profit, 2) if gross_profit > 0 else 0.0
    else:
        profit_factor = round(gross_profit / gross_loss_abs, 2)

    roi_pct = round((realized_pnl_total / max(float(risk_row.base_capital), 1)) * 100, 2)
    avg_execution_quality = round(
        sum(_safe_float(item.execution_quality_score) for item in execution_rows) / max(len(execution_rows), 1),
        2,
    )

    return {
        "lookback_days": lookback_days,
        "total_closed_trades": total_closed,
        "winning_trades": wins,
        "losing_trades": losses,
        "win_rate": win_rate,
        "realized_pnl_total": realized_pnl_total,
        "unrealized_pnl_total": unrealized_pnl_total,
        "roi_pct": roi_pct,
        "profit_factor": profit_factor,
        "avg_execution_quality": avg_execution_quality,
        "execution_count": len(execution_rows),
    }


def build_user_trade_history(db: Session, user_id: str, limit: int = 50) -> list[dict]:
    position_rows = (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id == user_id)
        .order_by(PaperPosition.opened_at.desc())
        .limit(max(limit, 100))
        .all()
    )
    execution_rows = (
        db.query(ExecutionMetric)
        .filter(ExecutionMetric.user_id == user_id)
        .order_by(ExecutionMetric.created_at.desc())
        .limit(max(limit, 100))
        .all()
    )

    position_ids = [row.id for row in position_rows]
    pending_map: dict[str, PendingSignal] = {}
    if position_ids:
        pending_rows = (
            db.query(PendingSignal)
            .filter(PendingSignal.user_id == user_id, PendingSignal.order_position_id.in_(position_ids))
            .all()
        )
        pending_map = {str(row.order_position_id): row for row in pending_rows if row.order_position_id}

    trace_map: dict[str, UserDecisionTrace] = {}
    if position_ids:
        trade_traces = (
            db.query(UserDecisionTrace)
            .filter(
                UserDecisionTrace.user_id == user_id,
                UserDecisionTrace.trace_scope == "trade",
                UserDecisionTrace.entity_id.in_(position_ids),
            )
            .order_by(UserDecisionTrace.created_at.desc())
            .all()
        )
        for trace in trade_traces:
            trace_map.setdefault(trace.entity_id, trace)

    items: list[dict] = []
    for row in position_rows:
        pending = pending_map.get(row.id)
        trace = trace_map.get(row.id)
        trace_feature = (trace.feature_snapshot or {}) if trace else {}
        trace_context = (trace.context_payload or {}) if trace else {}

        strategy_weight = (
            float(pending.strategy_weight)
            if pending and pending.strategy_weight is not None
            else float(trace_feature.get("strategy_weight"))
            if trace_feature.get("strategy_weight") is not None
            else None
        )
        allocation_source = (
            pending.allocation_source
            if pending and pending.allocation_source
            else trace_context.get("allocation_source")
            if trace_context.get("allocation_source")
            else None
        )
        meta_engine_decision = (
            pending.meta_engine_decision
            if pending and pending.meta_engine_decision
            else trace.meta_engine_decision
            if trace and trace.meta_engine_decision
            else trace_context.get("meta_engine_decision")
        )

        items.append(
            {
                "source": "paper_position",
                "trade_id": row.id,
                "symbol": row.symbol,
                "side": row.side,
                "status": row.status,
                "quantity": float(row.quantity),
                "entry_price": float(row.entry_price),
                "exit_price": None,
                "realized_pnl": float(row.realized_pnl),
                "unrealized_pnl": float(row.unrealized_pnl),
                "opened_at": row.opened_at,
                "closed_at": row.closed_at,
                "strategy_weight": strategy_weight,
                "allocation_source": allocation_source,
                "meta_engine_decision": meta_engine_decision,
                "event_timestamp": row.closed_at or row.opened_at,
            }
        )

    for row in execution_rows:
        items.append(
            {
                "source": "execution_metric",
                "trade_id": row.order_id,
                "symbol": row.symbol,
                "side": row.side,
                "status": row.final_status,
                "quantity": float(row.executed_qty or 0),
                "entry_price": float(row.mid_price),
                "exit_price": float(row.price_avg) if row.price_avg is not None else None,
                "realized_pnl": None,
                "unrealized_pnl": None,
                "opened_at": row.submitted_at or row.created_at,
                "closed_at": row.final_at,
                "strategy_weight": None,
                "allocation_source": "execution_metric",
                "meta_engine_decision": None,
                "event_timestamp": row.final_at or row.created_at,
            }
        )

    sorted_items = sorted(items, key=lambda item: item["event_timestamp"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    for item in sorted_items:
        item.pop("event_timestamp", None)
    return sorted_items[:limit]