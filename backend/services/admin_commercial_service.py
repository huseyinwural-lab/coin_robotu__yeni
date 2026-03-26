from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from io import BytesIO

from openpyxl import Workbook
from sqlalchemy.orm import Session

from models import (
    CommercialTrade,
    ExchangeReconciliationLog,
    ExecutionMetric,
    LiveActivationConfig,
    PaperPosition,
    PnlRecord,
    RevenueLedger,
    RiskOrchestratorPolicy,
    User,
    UserEconomicsAggregate,
    UserRole,
)

DEFAULT_OVERVIEW_TIME_WINDOW = "last_30_days"
DEFAULT_OVERVIEW_ENVIRONMENT = "live"
OVERVIEW_STALE_THRESHOLD_SECONDS = 6 * 60 * 60
_FIXED_REVENUE_COMPONENTS = [
    "platform_fee",
    "subscription_fee",
    "profit_split",
    "manual_adjustment",
    "fee",
    "pnl_share",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _month_window(month: str | None) -> tuple[datetime, datetime, str]:
    now = _now()
    if month:
        parsed = datetime.strptime(f"{month}-01", "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        parsed = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    if parsed.month == 12:
        next_month = parsed.replace(year=parsed.year + 1, month=1)
    else:
        next_month = parsed.replace(month=parsed.month + 1)
    return parsed, next_month, parsed.strftime("%Y-%m")


def _build_symbol_pnl_map(db: Session, *, user_ids: set[str], symbols: set[str]) -> dict[tuple[str, str], float]:
    if not user_ids or not symbols:
        return {}

    positions = (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id.in_(list(user_ids)), PaperPosition.symbol.in_(list(symbols)))
        .all()
    )
    pair_map: dict[tuple[str, str], float] = defaultdict(float)
    for row in positions:
        key = (str(row.user_id), str(row.symbol).upper())
        pair_map[key] += _safe_float(row.realized_pnl)
        if str(row.status).lower() == "open":
            pair_map[key] += _safe_float(row.unrealized_pnl)

    return {key: round(value, 6) for key, value in pair_map.items()}


def build_usage_logs(
    db: Session,
    *,
    user_id: str | None,
    symbol: str | None,
    status_filter: str | None,
    from_ts: str | None,
    to_ts: str | None,
    limit: int,
) -> dict:
    query = db.query(ExecutionMetric, User.email).join(User, User.id == ExecutionMetric.user_id)

    if user_id:
        query = query.filter(ExecutionMetric.user_id == user_id)
    if symbol:
        query = query.filter(ExecutionMetric.symbol == str(symbol).upper())
    if status_filter and status_filter != "all":
        query = query.filter(ExecutionMetric.final_status == status_filter)

    start = _parse_iso(from_ts)
    end = _parse_iso(to_ts)
    if start:
        query = query.filter(ExecutionMetric.created_at >= start)
    if end:
        query = query.filter(ExecutionMetric.created_at <= end)

    rows = query.order_by(ExecutionMetric.created_at.desc()).limit(min(max(limit, 1), 500)).all()
    user_ids = {str(item[0].user_id) for item in rows}
    symbols = {str(item[0].symbol).upper() for item in rows}
    pnl_map = _build_symbol_pnl_map(db, user_ids=user_ids, symbols=symbols)

    items: list[dict] = []
    for metric, email in rows:
        normalized_symbol = str(metric.symbol).upper()
        items.append(
            {
                "log_id": metric.id,
                "user_id": metric.user_id,
                "user_email": email,
                "symbol": normalized_symbol,
                "side": metric.side,
                "order_id": metric.order_id,
                "execution_status": metric.final_status or metric.status,
                "order_type": metric.order_type,
                "exchange": metric.exchange,
                "pnl": pnl_map.get((str(metric.user_id), normalized_symbol), 0.0),
                "opened_at": metric.submitted_at or metric.created_at,
            }
        )

    return {
        "generated_at": _now(),
        "total": len(items),
        "items": items,
    }


def _build_window_summary(db: Session, *, start: datetime, end: datetime) -> dict:
    users = db.query(User).filter(User.role == UserRole.USER).all()
    user_map = {user.id: user.email for user in users}

    closed_rows = (
        db.query(PaperPosition)
        .filter(
            PaperPosition.user_id.in_(list(user_map.keys())),
            PaperPosition.closed_at.is_not(None),
            PaperPosition.closed_at >= start,
            PaperPosition.closed_at < end,
        )
        .all()
        if user_map
        else []
    )
    open_rows = (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id.in_(list(user_map.keys())), PaperPosition.status == "open")
        .all()
        if user_map
        else []
    )

    realized_by_user: dict[str, float] = defaultdict(float)
    unrealized_by_user: dict[str, float] = defaultdict(float)

    for row in closed_rows:
        realized_by_user[str(row.user_id)] += _safe_float(row.realized_pnl)
    for row in open_rows:
        unrealized_by_user[str(row.user_id)] += _safe_float(row.unrealized_pnl)

    user_rows: list[dict] = []
    for uid, email in user_map.items():
        realized = round(realized_by_user.get(uid, 0.0), 6)
        unrealized = round(unrealized_by_user.get(uid, 0.0), 6)
        total = round(realized + unrealized, 6)
        user_rows.append(
            {
                "user_id": uid,
                "user_email": email,
                "realized_pnl": realized,
                "unrealized_pnl": unrealized,
                "total_pnl": total,
            }
        )

    user_rows.sort(key=lambda item: item["total_pnl"], reverse=True)
    total_realized = round(sum(item["realized_pnl"] for item in user_rows), 6)
    total_unrealized = round(sum(item["unrealized_pnl"] for item in user_rows), 6)

    return {
        "range_start": start,
        "range_end": end,
        "summary": {
            "user_count": len(user_rows),
            "total_realized_pnl": total_realized,
            "total_unrealized_pnl": total_unrealized,
            "total_pnl": round(total_realized + total_unrealized, 6),
        },
        "users": user_rows,
    }


def build_total_pnl_bundle(db: Session) -> dict:
    now = _now()
    last_30_start = now - timedelta(days=30)
    month_start, month_end, month_label = _month_window(None)

    return {
        "generated_at": now,
        "last_30_days": _build_window_summary(db, start=last_30_start, end=now),
        "calendar_month": {
            "month": month_label,
            **_build_window_summary(db, start=month_start, end=month_end),
        },
    }


def export_monthly_pnl_excel(db: Session, *, month: str | None) -> tuple[bytes, str]:
    start, end, month_label = _month_window(month)
    summary = _build_window_summary(db, start=start, end=end)
    users = summary.get("users") or []

    workbook = Workbook()
    summary_sheet = workbook.active
    summary_sheet.title = "Summary"
    summary_sheet.append(["month", month_label])
    summary_sheet.append(["range_start", start.isoformat()])
    summary_sheet.append(["range_end", end.isoformat()])
    summary_sheet.append([])
    summary_sheet.append(["user_count", summary["summary"].get("user_count", 0)])
    summary_sheet.append(["total_realized_pnl", summary["summary"].get("total_realized_pnl", 0)])
    summary_sheet.append(["total_unrealized_pnl", summary["summary"].get("total_unrealized_pnl", 0)])
    summary_sheet.append(["total_pnl", summary["summary"].get("total_pnl", 0)])
    summary_sheet.append([])
    summary_sheet.append(["user_id", "user_email", "realized_pnl", "unrealized_pnl", "total_pnl"])
    for row in users:
        summary_sheet.append(
            [
                row.get("user_id"),
                row.get("user_email"),
                row.get("realized_pnl"),
                row.get("unrealized_pnl"),
                row.get("total_pnl"),
            ]
        )

    metrics = (
        db.query(ExecutionMetric, User.email)
        .join(User, User.id == ExecutionMetric.user_id)
        .filter(ExecutionMetric.created_at >= start, ExecutionMetric.created_at < end)
        .order_by(ExecutionMetric.created_at.desc())
        .all()
    )
    metrics_by_user: dict[str, list[tuple[ExecutionMetric, str]]] = defaultdict(list)
    user_ids = {str(metric.user_id) for metric, _ in metrics}
    symbols = {str(metric.symbol).upper() for metric, _ in metrics}
    pnl_map = _build_symbol_pnl_map(db, user_ids=user_ids, symbols=symbols)
    for metric, email in metrics:
        metrics_by_user[str(metric.user_id)].append((metric, email))

    for index, user_row in enumerate(users[:60], start=1):
        sheet_name = f"U{index}_{(user_row.get('user_email') or 'user')[:22]}"
        sheet = workbook.create_sheet(title=sheet_name)
        sheet.append(["user_id", user_row.get("user_id")])
        sheet.append(["user_email", user_row.get("user_email")])
        sheet.append(["realized_pnl", user_row.get("realized_pnl")])
        sheet.append(["unrealized_pnl", user_row.get("unrealized_pnl")])
        sheet.append(["total_pnl", user_row.get("total_pnl")])
        sheet.append([])
        sheet.append(["opened_at", "symbol", "side", "order_id", "status", "order_type", "exchange", "symbol_pnl"])

        for metric, _email in metrics_by_user.get(user_row.get("user_id"), [])[:300]:
            normalized_symbol = str(metric.symbol).upper()
            sheet.append(
                [
                    (metric.submitted_at or metric.created_at).isoformat(),
                    normalized_symbol,
                    metric.side,
                    metric.order_id,
                    metric.final_status or metric.status,
                    metric.order_type,
                    metric.exchange,
                    pnl_map.get((str(metric.user_id), normalized_symbol), 0.0),
                ]
            )

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    filename = f"monthly_pnl_{month_label}.xlsx"
    return buffer.getvalue(), filename


def _round6(value: float) -> float:
    return round(float(value or 0.0), 6)


def _normalize_overview_time_window(value: str | None) -> str:
    normalized = (value or DEFAULT_OVERVIEW_TIME_WINDOW).strip().lower()
    aliases = {
        "30d": "last_30_days",
        "7d": "last_7_days",
        "90d": "last_90_days",
        "all": "all_time",
    }
    canonical = aliases.get(normalized, normalized)
    supported = {"last_7_days", "last_30_days", "last_90_days", "all_time"}
    if canonical not in supported:
        return DEFAULT_OVERVIEW_TIME_WINDOW
    return canonical


def _parse_iso_strict(value: str | None, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    parsed = _parse_iso(value)
    if parsed is None:
        raise ValueError(f"invalid_{field_name}")
    return parsed


def _resolve_overview_window(
    *,
    now: datetime,
    time_window: str | None,
    from_ts: str | None,
    to_ts: str | None,
) -> tuple[str, datetime | None, datetime | None, str | None, str | None]:
    parsed_from = _parse_iso_strict(from_ts, field_name="from")
    parsed_to = _parse_iso_strict(to_ts, field_name="to")

    if parsed_from or parsed_to:
        start = parsed_from or (parsed_to - timedelta(days=30))
        end = parsed_to or now
        if start and end and start > end:
            raise ValueError("invalid_time_range")
        return (
            "custom",
            start,
            end,
            start.isoformat() if start else None,
            end.isoformat() if end else None,
        )

    canonical = _normalize_overview_time_window(time_window)
    if canonical == "all_time":
        return canonical, None, None, None, None

    day_map = {
        "last_7_days": 7,
        "last_30_days": 30,
        "last_90_days": 90,
    }
    day_count = day_map.get(canonical, 30)
    start = now - timedelta(days=day_count)
    return canonical, start, now, start.isoformat(), now.isoformat()


def _apply_range_filters(query, column, start: datetime | None, end: datetime | None):
    if start is not None:
        query = query.filter(column >= start)
    if end is not None:
        query = query.filter(column <= end)
    return query


def _notional_usd(row: CommercialTrade) -> float:
    quote_qty = _safe_float(getattr(row, "quote_qty", 0.0))
    if quote_qty > 0:
        return quote_qty
    return abs(_safe_float(getattr(row, "executed_qty", 0.0)) * _safe_float(getattr(row, "executed_price", 0.0)))


def _build_financial_accuracy_block(trades: list[CommercialTrade], pnl_records: list[PnlRecord]) -> dict:
    commission_from_trades = sum(_safe_float(getattr(row, "commission_usd", 0.0)) for row in trades)
    funding_from_trades = sum(_safe_float(getattr(row, "funding_fee_usd", 0.0)) for row in trades)

    if pnl_records:
        realized_gross = sum(_safe_float(row.realized_gross_usd) for row in pnl_records)
        unrealized_gross = sum(_safe_float(row.unrealized_gross_usd) for row in pnl_records)
        realized_net = sum(_safe_float(row.realized_net_usd) for row in pnl_records)
        unrealized_net = sum(_safe_float(row.unrealized_net_usd) for row in pnl_records)
        trading_fee_total = sum(_safe_float(row.trading_fee_usd) for row in pnl_records)
        commission_total = sum(_safe_float(row.commission_usd) for row in pnl_records)
        funding_total = sum(_safe_float(row.funding_usd) for row in pnl_records)
    else:
        realized_gross = sum(_safe_float(row.realized_pnl_usd) for row in trades)
        unrealized_gross = 0.0
        realized_net = realized_gross - commission_from_trades - funding_from_trades
        unrealized_net = 0.0
        trading_fee_total = commission_from_trades
        commission_total = commission_from_trades
        funding_total = funding_from_trades

    gross_total = realized_gross + unrealized_gross
    net_total = realized_net + unrealized_net
    return {
        "record_count": len(pnl_records),
        "trade_count": len(trades),
        "realized_gross_usd": _round6(realized_gross),
        "unrealized_gross_usd": _round6(unrealized_gross),
        "gross_total_usd": _round6(gross_total),
        "realized_net_usd": _round6(realized_net),
        "unrealized_net_usd": _round6(unrealized_net),
        "net_total_usd": _round6(net_total),
        "net_vs_gross_delta_usd": _round6(gross_total - net_total),
        "trading_fee_total_usd": _round6(trading_fee_total),
        "funding_total_usd": _round6(funding_total),
        "commission_total_usd": _round6(commission_total),
    }


def _build_revenue_model_block(revenue_rows: list[RevenueLedger]) -> dict:
    component_map: dict[str, dict] = {
        component: {
            "component_type": component,
            "revenue_usd": 0.0,
            "source_amount_usd": 0.0,
            "share_rate_sum": 0.0,
            "share_rate_count": 0,
            "row_count": 0,
        }
        for component in _FIXED_REVENUE_COMPONENTS
    }
    symbol_revenue: dict[str, float] = defaultdict(float)

    for row in revenue_rows:
        component = str(getattr(row, "component_type", "manual_adjustment") or "manual_adjustment").lower()
        entry = component_map.setdefault(
            component,
            {
                "component_type": component,
                "revenue_usd": 0.0,
                "source_amount_usd": 0.0,
                "share_rate_sum": 0.0,
                "share_rate_count": 0,
                "row_count": 0,
            },
        )
        revenue_amount = _safe_float(getattr(row, "revenue_amount_usd", 0.0))
        source_amount = _safe_float(getattr(row, "source_amount_usd", 0.0))
        share_rate = _safe_float(getattr(row, "share_rate", 0.0))

        entry["revenue_usd"] += revenue_amount
        entry["source_amount_usd"] += source_amount
        entry["share_rate_sum"] += share_rate
        entry["share_rate_count"] += 1
        entry["row_count"] += 1

        symbol = str(getattr(row, "symbol", "") or "").upper()
        if symbol:
            symbol_revenue[symbol] += revenue_amount

    components = []
    for component in sorted(component_map.keys()):
        item = component_map[component]
        share_rate_avg = item["share_rate_sum"] / item["share_rate_count"] if item["share_rate_count"] else 0.0
        components.append(
            {
                "component_type": item["component_type"],
                "revenue_usd": _round6(item["revenue_usd"]),
                "source_amount_usd": _round6(item["source_amount_usd"]),
                "share_rate_avg": _round6(share_rate_avg),
                "row_count": item["row_count"],
            }
        )

    top_symbols = sorted(symbol_revenue.items(), key=lambda kv: kv[1], reverse=True)[:7]
    return {
        "total_revenue_usd": _round6(sum(item["revenue_usd"] for item in components)),
        "component_breakdown": components,
        "top_symbols": [
            {
                "symbol": symbol,
                "revenue_usd": _round6(total),
            }
            for symbol, total in top_symbols
        ],
        "row_count": len(revenue_rows),
    }


def _build_user_economics_block(user_rows: list[UserEconomicsAggregate], *, top_limit: int = 12) -> dict:
    total_users = len(user_rows)
    paying_users = sum(1 for row in user_rows if _safe_float(getattr(row, "revenue_contribution_usd", 0.0)) > 0)
    churned_users = sum(1 for row in user_rows if bool(getattr(row, "churned", False)))

    total_ltv = sum(_safe_float(getattr(row, "ltv_usd", 0.0)) for row in user_rows)
    total_revenue = sum(_safe_float(getattr(row, "revenue_contribution_usd", 0.0)) for row in user_rows)
    total_realized_pnl = sum(_safe_float(getattr(row, "realized_pnl_usd", 0.0)) for row in user_rows)
    avg_ltv = total_ltv / total_users if total_users else 0.0
    avg_inactive_days = (
        sum(int(getattr(row, "inactive_days", 0) or 0) for row in user_rows) / total_users if total_users else 0.0
    )

    segment_distribution: Counter[str] = Counter()
    for row in user_rows:
        details = getattr(row, "details", {}) or {}
        segment = str(details.get("segment") or "unknown")
        segment_distribution[segment] += 1

    sorted_users = sorted(
        user_rows,
        key=lambda row: _safe_float(getattr(row, "ltv_usd", 0.0)),
        reverse=True,
    )
    top_users = []
    for row in sorted_users[:top_limit]:
        top_users.append(
            {
                "user_id": str(getattr(row, "user_id", "")),
                "user_email": str(getattr(row, "user_email", "")),
                "ltv_usd": _round6(_safe_float(getattr(row, "ltv_usd", 0.0))),
                "revenue_contribution_usd": _round6(_safe_float(getattr(row, "revenue_contribution_usd", 0.0))),
                "realized_pnl_usd": _round6(_safe_float(getattr(row, "realized_pnl_usd", 0.0))),
                "inactive_days": int(getattr(row, "inactive_days", 0) or 0),
                "churned": bool(getattr(row, "churned", False)),
            }
        )

    return {
        "total_users": total_users,
        "paying_users": paying_users,
        "churned_users": churned_users,
        "total_ltv_usd": _round6(total_ltv),
        "total_revenue_contribution_usd": _round6(total_revenue),
        "total_realized_pnl_usd": _round6(total_realized_pnl),
        "avg_ltv_usd": _round6(avg_ltv),
        "avg_inactive_days": _round6(avg_inactive_days),
        "segment_distribution": dict(segment_distribution),
        "top_users": top_users,
    }


def _build_usage_analytics_block(trades: list[CommercialTrade], *, top_symbol_limit: int = 8) -> dict:
    market_counter: Counter[str] = Counter()
    exchange_counter: Counter[str] = Counter()
    symbol_counter: Counter[str] = Counter()
    symbol_notional: dict[str, float] = defaultdict(float)
    user_ids: set[str] = set()
    day_set: set[str] = set()

    total_notional = 0.0
    for row in trades:
        market = str(getattr(row, "market_type", "unknown") or "unknown").lower()
        exchange = str(getattr(row, "exchange", "unknown") or "unknown").lower()
        symbol = str(getattr(row, "symbol", "") or "").upper()

        market_counter[market] += 1
        exchange_counter[exchange] += 1
        if symbol:
            symbol_counter[symbol] += 1
        notional = _notional_usd(row)
        if symbol:
            symbol_notional[symbol] += notional
        total_notional += notional
        user_ids.add(str(getattr(row, "user_id", "")))

        trade_time = getattr(row, "trade_time", None)
        if trade_time is not None:
            day_set.add(trade_time.date().isoformat())

    total_trades = len(trades)
    avg_trade_notional = total_notional / total_trades if total_trades else 0.0
    top_symbols = symbol_counter.most_common(top_symbol_limit)

    return {
        "total_trades": total_trades,
        "unique_users": len([uid for uid in user_ids if uid]),
        "unique_symbols": len(symbol_counter),
        "total_notional_usd": _round6(total_notional),
        "avg_trade_notional_usd": _round6(avg_trade_notional),
        "activity_days": len(day_set),
        "by_market_type": dict(market_counter),
        "by_exchange": dict(exchange_counter),
        "top_symbols": [
            {
                "symbol": symbol,
                "trade_count": count,
                "notional_usd": _round6(symbol_notional.get(symbol, 0.0)),
            }
            for symbol, count in top_symbols
        ],
    }


def _build_risk_summary_block(
    trades: list[CommercialTrade],
    reconciliation_logs: list[ExchangeReconciliationLog],
    *,
    open_position_count: int,
    risk_policy: RiskOrchestratorPolicy | None,
    live_config: LiveActivationConfig | None,
) -> dict:
    symbol_exposure: dict[str, float] = defaultdict(float)
    for row in trades:
        symbol = str(getattr(row, "symbol", "") or "").upper()
        if symbol:
            symbol_exposure[symbol] += _notional_usd(row)

    sorted_exposure = sorted(symbol_exposure.items(), key=lambda kv: kv[1], reverse=True)[:7]
    high_drift_reconciliation_count = sum(
        1 for row in reconciliation_logs if not bool(getattr(row, "drift_within_tolerance", False))
    )

    return {
        "open_position_count": int(open_position_count),
        "risk_exposure_usd": _round6(sum(symbol_exposure.values())),
        "high_drift_reconciliation_count": high_drift_reconciliation_count,
        "latest_daily_loss_limit_pct": (
            _round6(_safe_float(getattr(risk_policy, "daily_loss_limit_pct", 0.0))) if risk_policy else None
        ),
        "trading_enabled": bool(getattr(live_config, "trading_enabled", False)),
        "kill_switch_enabled": bool(getattr(live_config, "kill_switch_enabled", False)),
        "top_exposure_symbols": [
            {
                "symbol": symbol,
                "exposure_usd": _round6(exposure_usd),
            }
            for symbol, exposure_usd in sorted_exposure
        ],
    }


def _age_seconds(now: datetime, ts: datetime | None) -> int | None:
    if ts is None:
        return None
    return max(0, int((now - ts).total_seconds()))


def _build_data_quality_block(
    *,
    now: datetime,
    total_trade_count: int,
    total_pnl_records: int,
    latest_trade_at: datetime | None,
    latest_pnl_at: datetime | None,
    latest_reconciliation_at: datetime | None,
    missing_data_alert: bool,
    stale_threshold_seconds: int = OVERVIEW_STALE_THRESHOLD_SECONDS,
) -> dict:
    trade_age = _age_seconds(now, latest_trade_at)
    pnl_age = _age_seconds(now, latest_pnl_at)
    reconciliation_age = _age_seconds(now, latest_reconciliation_at)

    stale_sources: list[str] = []
    if total_trade_count > 0 and trade_age is not None and trade_age > stale_threshold_seconds:
        stale_sources.append("trades")
    if total_pnl_records > 0 and pnl_age is not None and pnl_age > stale_threshold_seconds:
        stale_sources.append("pnl_records")
    if latest_reconciliation_at is not None and reconciliation_age is not None and reconciliation_age > stale_threshold_seconds:
        stale_sources.append("reconciliation")

    empty_data = total_trade_count == 0 and total_pnl_records == 0
    if empty_data:
        status = "empty"
    elif stale_sources:
        status = "stale"
    elif missing_data_alert:
        status = "degraded"
    else:
        status = "healthy"

    known_ages = [age for age in [trade_age, pnl_age, reconciliation_age] if age is not None]
    freshness_seconds = max(known_ages) if known_ages else None

    return {
        "status": status,
        "empty_data": empty_data,
        "stale_sources": stale_sources,
        "freshness_seconds": freshness_seconds,
        "stale_threshold_seconds": stale_threshold_seconds,
        "latest_trade_at": latest_trade_at,
        "latest_pnl_at": latest_pnl_at,
        "latest_reconciliation_at": latest_reconciliation_at,
        "missing_data_alert": bool(missing_data_alert),
        "trade_count": int(total_trade_count),
        "pnl_record_count": int(total_pnl_records),
    }


def build_admin_commercial_overview(
    db: Session,
    *,
    time_window: str | None,
    environment: str | None,
    from_ts: str | None,
    to_ts: str | None,
) -> dict:
    now = _now()
    applied_environment = (environment or DEFAULT_OVERVIEW_ENVIRONMENT).strip().lower() or DEFAULT_OVERVIEW_ENVIRONMENT
    applied_time_window, range_start, range_end, from_iso, to_iso = _resolve_overview_window(
        now=now,
        time_window=time_window,
        from_ts=from_ts,
        to_ts=to_ts,
    )

    trade_query = db.query(CommercialTrade).filter(CommercialTrade.environment == applied_environment)
    pnl_query = db.query(PnlRecord).filter(PnlRecord.environment == applied_environment)
    revenue_query = db.query(RevenueLedger).filter(RevenueLedger.environment == applied_environment)
    reconciliation_query = db.query(ExchangeReconciliationLog).filter(
        ExchangeReconciliationLog.environment == applied_environment
    )

    trade_query = _apply_range_filters(trade_query, CommercialTrade.trade_time, range_start, range_end)
    pnl_query = _apply_range_filters(pnl_query, PnlRecord.as_of, range_start, range_end)
    revenue_query = _apply_range_filters(revenue_query, RevenueLedger.trade_time, range_start, range_end)
    reconciliation_query = _apply_range_filters(
        reconciliation_query,
        ExchangeReconciliationLog.created_at,
        range_start,
        range_end,
    )

    trades = trade_query.all()
    pnl_records = pnl_query.all()
    revenue_rows = revenue_query.all()
    reconciliation_logs = reconciliation_query.all()

    user_economics_query = db.query(UserEconomicsAggregate).filter(UserEconomicsAggregate.environment == applied_environment)
    windowed_user_economics_query = _apply_range_filters(
        user_economics_query,
        UserEconomicsAggregate.updated_at,
        range_start,
        range_end,
    )
    user_economics_rows = windowed_user_economics_query.all()
    if not user_economics_rows and (range_start is not None or range_end is not None):
        user_economics_rows = user_economics_query.all()

    open_position_count = db.query(PaperPosition).filter(PaperPosition.status == "open").count()
    risk_policy = db.query(RiskOrchestratorPolicy).order_by(RiskOrchestratorPolicy.updated_at.desc()).first()
    live_config = db.query(LiveActivationConfig).first()

    latest_trade_at = max((getattr(row, "trade_time", None) for row in trades), default=None)
    latest_pnl_at = max((getattr(row, "as_of", None) for row in pnl_records), default=None)
    latest_reconciliation_at = max((getattr(row, "created_at", None) for row in reconciliation_logs), default=None)
    latest_reconciliation = max(
        reconciliation_logs,
        key=lambda row: getattr(row, "created_at", datetime.min.replace(tzinfo=timezone.utc)),
        default=None,
    )
    missing_data_alert = bool(getattr(latest_reconciliation, "missing_data_alert", False)) if latest_reconciliation else False

    return {
        "generated_at": now,
        "contract_version": "v1",
        "applied_filters": {
            "environment": applied_environment,
            "time_window": applied_time_window,
            "from_ts": from_iso,
            "to_ts": to_iso,
            "range_start": range_start,
            "range_end": range_end,
        },
        "financial_accuracy": _build_financial_accuracy_block(trades, pnl_records),
        "revenue_model": _build_revenue_model_block(revenue_rows),
        "user_economics": _build_user_economics_block(user_economics_rows),
        "risk_summary": _build_risk_summary_block(
            trades,
            reconciliation_logs,
            open_position_count=open_position_count,
            risk_policy=risk_policy,
            live_config=live_config,
        ),
        "usage_analytics": _build_usage_analytics_block(trades),
        "data_quality": _build_data_quality_block(
            now=now,
            total_trade_count=len(trades),
            total_pnl_records=len(pnl_records),
            latest_trade_at=latest_trade_at,
            latest_pnl_at=latest_pnl_at,
            latest_reconciliation_at=latest_reconciliation_at,
            missing_data_alert=missing_data_alert,
        ),
    }