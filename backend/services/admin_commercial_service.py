from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
from io import BytesIO

from openpyxl import Workbook
from sqlalchemy.orm import Session

from models import (
    CommercialAlertEvent,
    CommercialExportAudit,
    CommercialExportManifest,
    CommercialExportSchedule,
    CommercialOperationalControlState,
    CommercialOperationalControlTransition,
    CommercialSubscriptionProfile,
    CommercialTrade,
    CommercialUsageEvent,
    ExchangeReconciliationLog,
    ExecutionMetric,
    LiveActivationConfig,
    PaperPosition,
    PnlRecord,
    RevenueLedger,
    RiskOrchestratorPolicy,
    SystemAlert,
    User,
    UserEconomicsAggregate,
    UserRole,
)
from services.audit_service import create_audit_log

DEFAULT_OVERVIEW_TIME_WINDOW = "last_30_days"
DEFAULT_OVERVIEW_ENVIRONMENT = "live"
OVERVIEW_STALE_THRESHOLD_SECONDS = 6 * 60 * 60
DETAIL_LIST_LIMIT = 50
_FIXED_REVENUE_COMPONENTS = [
    "platform_fee",
    "subscription_fee",
    "tier_fee",
    "profit_split",
    "manual_adjustment",
    "fee",
    "pnl_share",
]

EXPORT_COLUMN_REGISTRY: dict[tuple[str, str], dict] = {
    ("monthly_pnl", "v1"): {
        "summary": [
            "window",
            "user_count",
            "total_pnl",
            "realized_total",
            "unrealized_total",
            "last_updated",
        ],
        "users": [
            "user_id",
            "user_email",
            "total_pnl",
            "realized_total",
            "unrealized_total",
            "trade_count",
            "win_rate",
        ],
    },
    ("pnl", "v1"): {"overview": ["realized_gross_usd", "unrealized_gross_usd", "net_total_usd"]},
    ("revenue", "v1"): {"overview": ["component_type", "revenue_usd", "source_amount_usd", "share_rate_avg"]},
    ("user_economics", "v1"): {"overview": ["user_id", "user_email", "ltv_usd", "revenue_contribution_usd"]},
}


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


def export_monthly_pnl_with_governance(
    db: Session,
    *,
    month: str | None,
    actor_user: User,
    filters_snapshot: dict | None = None,
) -> tuple[bytes, str, str, dict]:
    workbook_bytes, filename = export_monthly_pnl_excel(db, month=month)
    manifest_payload = create_commercial_export_manifest(
        db,
        actor_user=actor_user,
        export_type="monthly_pnl",
        schema_version="v1",
        filters_snapshot=filters_snapshot or {"month": month},
        column_mapping={},
        output_format="xlsx",
        row_count=0,
        reason_note="monthly_pnl_export",
    )
    delivery_payload = finalize_export_delivery(
        db,
        export_id=manifest_payload["export_id"],
        content_bytes=workbook_bytes,
        output_format="xlsx",
    )
    return workbook_bytes, filename, manifest_payload["export_id"], delivery_payload


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


def _safe_query_all(query):
    try:
        return query.all()
    except Exception:
        try:
            query.session.rollback()
        except Exception:
            pass
        return []


def _safe_query_first(query):
    try:
        return query.first()
    except Exception:
        try:
            query.session.rollback()
        except Exception:
            pass
        return None


def _notional_usd(row: CommercialTrade) -> float:
    quote_qty = _safe_float(getattr(row, "quote_qty", 0.0))
    if quote_qty > 0:
        return quote_qty
    return abs(_safe_float(getattr(row, "executed_qty", 0.0)) * _safe_float(getattr(row, "executed_price", 0.0)))


def _build_financial_accuracy_block(
    trades: list[CommercialTrade],
    pnl_records: list[PnlRecord],
    reconciliation_logs: list[ExchangeReconciliationLog] | None = None,
) -> dict:
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
    latest_reconciliation = max(
        reconciliation_logs or [],
        key=lambda row: getattr(row, "created_at", datetime.min.replace(tzinfo=timezone.utc)),
        default=None,
    )
    exchange_trade_count = int(getattr(latest_reconciliation, "exchange_trade_count", len(trades)) or len(trades))
    internal_trade_count = int(getattr(latest_reconciliation, "internal_trade_count", len(trades)) or len(trades))
    missing_trade_count = int(getattr(latest_reconciliation, "missing_trade_count", 0) or 0)
    duplicate_trade_count = int(getattr(latest_reconciliation, "duplicate_trade_count", 0) or 0)
    balance_drift_usd = _safe_float(getattr(latest_reconciliation, "balance_drift_usd", 0.0))
    position_drift_usd = _safe_float(getattr(latest_reconciliation, "position_drift_usd", 0.0))
    pnl_drift_usd = _safe_float(getattr(latest_reconciliation, "pnl_drift_usd", 0.0))
    drift_within_tolerance = bool(getattr(latest_reconciliation, "drift_within_tolerance", True))
    reconciliation_status = str(getattr(latest_reconciliation, "status", "unknown") or "unknown").lower()

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
        "exchange_trade_count": exchange_trade_count,
        "internal_trade_count": internal_trade_count,
        "missing_trade_count": missing_trade_count,
        "duplicate_trade_count": duplicate_trade_count,
        "balance_drift_usd": _round6(balance_drift_usd),
        "position_drift_usd": _round6(position_drift_usd),
        "pnl_drift_usd": _round6(pnl_drift_usd),
        "drift_within_tolerance": drift_within_tolerance,
        "reconciliation_status": reconciliation_status,
    }


def _build_revenue_model_block(
    revenue_rows: list[RevenueLedger],
    *,
    subscription_profiles: list[CommercialSubscriptionProfile] | None = None,
    user_email_map: dict[str, str] | None = None,
) -> dict:
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
    user_revenue: dict[str, float] = defaultdict(float)

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

        user_id = str(getattr(row, "user_id", "") or "")
        if user_id:
            user_revenue[user_id] += revenue_amount

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
    revenue_by_user_sorted = sorted(user_revenue.items(), key=lambda kv: kv[1], reverse=True)[:DETAIL_LIST_LIMIT]

    revenue_by_plan_map: dict[tuple[str, str, str], float] = defaultdict(float)
    if subscription_profiles:
        profile_map = {(str(row.user_id), str(row.environment or "live").lower()): row for row in subscription_profiles}
        for user_id, revenue_value in user_revenue.items():
            profile = profile_map.get((user_id, DEFAULT_OVERVIEW_ENVIRONMENT)) or next(
                (row for key, row in profile_map.items() if key[0] == user_id),
                None,
            )
            tier_code = str(getattr(profile, "tier_code", "free") or "free")
            status = str(getattr(profile, "subscription_status", "inactive") or "inactive")
            cycle = str(getattr(profile, "billing_cycle", "monthly") or "monthly")
            revenue_by_plan_map[(tier_code, status, cycle)] += revenue_value

    component_total_map = {item["component_type"]: item["revenue_usd"] for item in components}
    subscription_revenue_usd = component_total_map.get("subscription_fee", 0.0)
    platform_fee_revenue_usd = component_total_map.get("platform_fee", 0.0) + component_total_map.get("fee", 0.0)
    tier_fee_revenue_usd = component_total_map.get("tier_fee", 0.0)
    profit_split_revenue_usd = component_total_map.get("profit_split", 0.0) + component_total_map.get("pnl_share", 0.0)
    manual_adjustment_revenue_usd = component_total_map.get("manual_adjustment", 0.0)

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
        "subscription_revenue_usd": _round6(subscription_revenue_usd),
        "platform_fee_revenue_usd": _round6(platform_fee_revenue_usd),
        "tier_fee_revenue_usd": _round6(tier_fee_revenue_usd),
        "profit_split_revenue_usd": _round6(profit_split_revenue_usd),
        "manual_adjustment_revenue_usd": _round6(manual_adjustment_revenue_usd),
        "revenue_by_user": [
            {
                "user_id": user_id,
                "user_email": (user_email_map or {}).get(user_id, ""),
                "revenue_usd": _round6(revenue_value),
            }
            for user_id, revenue_value in revenue_by_user_sorted
        ],
        "revenue_by_plan": [
            {
                "tier_code": tier_code,
                "subscription_status": status,
                "billing_cycle": cycle,
                "revenue_usd": _round6(total),
            }
            for (tier_code, status, cycle), total in sorted(
                revenue_by_plan_map.items(), key=lambda kv: kv[1], reverse=True
            )[:DETAIL_LIST_LIMIT]
        ],
        "revenue_by_symbol": [
            {
                "symbol": symbol,
                "revenue_usd": _round6(total),
            }
            for symbol, total in sorted(symbol_revenue.items(), key=lambda kv: kv[1], reverse=True)[:DETAIL_LIST_LIMIT]
        ],
        "row_count": len(revenue_rows),
    }


def _build_user_economics_block(user_rows: list[UserEconomicsAggregate], *, top_limit: int = DETAIL_LIST_LIMIT) -> dict:
    total_users = len(user_rows)
    paying_users = sum(1 for row in user_rows if _safe_float(getattr(row, "revenue_contribution_usd", 0.0)) > 0)
    churned_users = sum(1 for row in user_rows if bool(getattr(row, "churned", False)))

    total_ltv = sum(_safe_float(getattr(row, "ltv_usd", 0.0)) for row in user_rows)
    total_revenue = sum(_safe_float(getattr(row, "revenue_contribution_usd", 0.0)) for row in user_rows)
    total_realized_pnl = sum(_safe_float(getattr(row, "realized_pnl_usd", 0.0)) for row in user_rows)
    inactive_user_count = sum(1 for row in user_rows if int(getattr(row, "inactive_days", 0) or 0) >= 30)
    avg_ltv = total_ltv / total_users if total_users else 0.0
    avg_inactive_days = (
        sum(int(getattr(row, "inactive_days", 0) or 0) for row in user_rows) / total_users if total_users else 0.0
    )

    segment_distribution: Counter[str] = Counter()
    for row in user_rows:
        details = getattr(row, "details", {}) or {}
        segment = str(details.get("segment") or "unknown")
        segment_distribution[segment] += 1

    paying_revenue_users = [row for row in user_rows if _safe_float(getattr(row, "revenue_contribution_usd", 0.0)) > 0]
    arpu_usd = total_revenue / total_users if total_users else 0.0
    arppu_usd = total_revenue / len(paying_revenue_users) if paying_revenue_users else 0.0
    churn_rate_pct = (churned_users / total_users * 100) if total_users else 0.0

    cohort_counter: Counter[str] = Counter()
    for row in user_rows:
        cohort_counter[str(getattr(row, "cohort_month", None) or "unknown")] += 1
    cohort_summary = [
        {"cohort": cohort, "user_count": count}
        for cohort, count in sorted(cohort_counter.items(), key=lambda kv: kv[0], reverse=True)[:DETAIL_LIST_LIMIT]
    ]

    signup_to_retention_summary = []
    for row in user_rows[:DETAIL_LIST_LIMIT]:
        first_activity_at = getattr(row, "first_activity_at", None)
        last_activity_at = getattr(row, "last_activity_at", None)
        days_active = 0
        if first_activity_at and last_activity_at:
            days_active = max(0, int((last_activity_at - first_activity_at).days))
        signup_to_retention_summary.append(
            {
                "user_id": str(getattr(row, "user_id", "")),
                "user_email": str(getattr(row, "user_email", "")),
                "days_active": days_active,
                "inactive_days": int(getattr(row, "inactive_days", 0) or 0),
                "churned": bool(getattr(row, "churned", False)),
            }
        )

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

    top_profitability_users = []
    for row in sorted(
        user_rows,
        key=lambda item: _safe_float(getattr(item, "realized_pnl_usd", 0.0)),
        reverse=True,
    )[:top_limit]:
        top_profitability_users.append(
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

    high_churn_risk_users = []
    risk_candidates = sorted(
        user_rows,
        key=lambda item: int(getattr(item, "inactive_days", 0) or 0),
        reverse=True,
    )
    for row in risk_candidates:
        inactive_days = int(getattr(row, "inactive_days", 0) or 0)
        if inactive_days < 20 and not bool(getattr(row, "churned", False)):
            continue
        high_churn_risk_users.append(
            {
                "user_id": str(getattr(row, "user_id", "")),
                "user_email": str(getattr(row, "user_email", "")),
                "ltv_usd": _round6(_safe_float(getattr(row, "ltv_usd", 0.0))),
                "revenue_contribution_usd": _round6(_safe_float(getattr(row, "revenue_contribution_usd", 0.0))),
                "realized_pnl_usd": _round6(_safe_float(getattr(row, "realized_pnl_usd", 0.0))),
                "inactive_days": inactive_days,
                "churned": bool(getattr(row, "churned", False)),
            }
        )
        if len(high_churn_risk_users) >= top_limit:
            break

    return {
        "total_users": total_users,
        "paying_users": paying_users,
        "churned_users": churned_users,
        "total_ltv_usd": _round6(total_ltv),
        "total_revenue_contribution_usd": _round6(total_revenue),
        "total_realized_pnl_usd": _round6(total_realized_pnl),
        "avg_ltv_usd": _round6(avg_ltv),
        "avg_inactive_days": _round6(avg_inactive_days),
        "arpu_usd": _round6(arpu_usd),
        "arppu_usd": _round6(arppu_usd),
        "churn_rate_pct": _round6(churn_rate_pct),
        "inactive_user_count": inactive_user_count,
        "cohort_summary": cohort_summary,
        "signup_to_retention_summary": signup_to_retention_summary,
        "segment_distribution": dict(segment_distribution),
        "top_users": top_users,
        "top_profitability_users": top_profitability_users,
        "high_churn_risk_users": high_churn_risk_users,
    }


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((percentile / 100.0) * (len(ordered) - 1)))))
    return ordered[index]


def _build_usage_analytics_block(
    trades: list[CommercialTrade],
    usage_events: list[CommercialUsageEvent] | None = None,
    *,
    top_symbol_limit: int = 8,
) -> dict:
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

    events = usage_events or []
    endpoint_counter: Counter[str] = Counter()
    event_type_counter: Counter[str] = Counter()
    if not events and trades:
        request_count = len(trades)
        success_count = len(trades)
        failure_count = 0
        error_rate_pct = 0.0
        avg_latency_ms = 0.0
        p95_latency_ms = 0.0
        rate_per_minute = float(request_count)
        endpoint_counter.update({"trade_ingest": len(trades)})
        event_type_counter.update({"trade": len(trades)})
    else:
        request_count = len(events)
        success_count = sum(1 for event in events if bool(getattr(event, "success", False)))
        failure_count = max(0, request_count - success_count)
        error_rate_pct = (failure_count / request_count * 100) if request_count else 0.0
        latency_values = [
            _safe_float(getattr(event, "latency_ms", None), default=0.0)
            for event in events
            if getattr(event, "latency_ms", None) is not None
        ]
        avg_latency_ms = sum(latency_values) / len(latency_values) if latency_values else 0.0
        p95_latency_ms = _percentile(latency_values, 95)
        for event in events:
            endpoint_counter[str(getattr(event, "endpoint", "unknown") or "unknown")] += 1
            event_type_counter[str(getattr(event, "event_type", "unknown") or "unknown")] += 1

        first_event_at = min((getattr(event, "created_at", None) for event in events), default=None)
        last_event_at = max((getattr(event, "created_at", None) for event in events), default=None)
        if first_event_at and last_event_at and first_event_at < last_event_at:
            span_minutes = max(1.0, (last_event_at - first_event_at).total_seconds() / 60.0)
            rate_per_minute = request_count / span_minutes
        elif request_count:
            rate_per_minute = float(request_count)
        else:
            rate_per_minute = 0.0

    return {
        "total_trades": total_trades,
        "unique_users": len([uid for uid in user_ids if uid]),
        "unique_symbols": len(symbol_counter),
        "total_notional_usd": _round6(total_notional),
        "avg_trade_notional_usd": _round6(avg_trade_notional),
        "activity_days": len(day_set),
        "by_market_type": dict(market_counter),
        "by_exchange": dict(exchange_counter),
        "request_count": request_count,
        "success_count": success_count,
        "failure_count": failure_count,
        "error_rate_pct": _round6(error_rate_pct),
        "avg_latency_ms": _round6(avg_latency_ms),
        "p95_latency_ms": _round6(p95_latency_ms),
        "rate_per_minute": _round6(rate_per_minute),
        "api_usage_by_endpoint": [
            {"endpoint": endpoint, "count": count}
            for endpoint, count in endpoint_counter.most_common(DETAIL_LIST_LIMIT)
        ],
        "event_type_distribution": [
            {"event_type": event_type, "count": count}
            for event_type, count in event_type_counter.most_common(DETAIL_LIST_LIMIT)
        ],
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
    open_positions: list[PaperPosition],
    risk_policy: RiskOrchestratorPolicy | None,
    live_config: LiveActivationConfig | None,
) -> dict:
    symbol_exposure: dict[str, float] = defaultdict(float)
    user_exposure: dict[str, float] = defaultdict(float)
    strategy_exposure: dict[str, float] = defaultdict(float)
    for row in trades:
        symbol = str(getattr(row, "symbol", "") or "").upper()
        user_id = str(getattr(row, "user_id", "") or "")
        strategy = str((getattr(row, "raw_payload", {}) or {}).get("strategy_code") or "default").lower()
        notional = _notional_usd(row)
        if symbol:
            symbol_exposure[symbol] += notional
        if user_id:
            user_exposure[user_id] += notional
        strategy_exposure[strategy] += notional

    sorted_exposure = sorted(symbol_exposure.items(), key=lambda kv: kv[1], reverse=True)[:7]
    high_drift_reconciliation_count = sum(
        1 for row in reconciliation_logs if not bool(getattr(row, "drift_within_tolerance", False))
    )

    risk_exposure_total = _round6(sum(symbol_exposure.values()))
    max_total_exposure = _safe_float(getattr(live_config, "max_total_exposure", 0.0))
    utilization = (risk_exposure_total / max_total_exposure) if max_total_exposure > 0 else 0.0
    liquidation_risk_score = min(100.0, max(0.0, utilization * 100.0))
    margin_risk_score = min(100.0, max(0.0, utilization * 100.0 + high_drift_reconciliation_count * 5.0))
    if liquidation_risk_score >= 80:
        forced_liquidation_risk = "high"
    elif liquidation_risk_score >= 45:
        forced_liquidation_risk = "medium"
    else:
        forced_liquidation_risk = "low"

    if margin_risk_score >= 80:
        margin_risk_state = "critical"
    elif margin_risk_score >= 50:
        margin_risk_state = "warning"
    else:
        margin_risk_state = "stable"

    breach_threshold = max_total_exposure * 0.25 if max_total_exposure > 0 else 0.0
    breached_users = [
        {"user_id": uid, "exposure_usd": _round6(value)}
        for uid, value in sorted(user_exposure.items(), key=lambda kv: kv[1], reverse=True)
        if breach_threshold > 0 and value >= breach_threshold
    ][:DETAIL_LIST_LIMIT]

    open_positions_payload = []
    for row in open_positions[:DETAIL_LIST_LIMIT]:
        open_positions_payload.append(
            {
                "position_id": str(getattr(row, "id", "")),
                "user_id": str(getattr(row, "user_id", "")),
                "symbol": str(getattr(row, "symbol", "") or "").upper(),
                "side": str(getattr(row, "side", "") or ""),
                "quantity": _round6(_safe_float(getattr(row, "quantity", 0.0))),
                "entry_price": _round6(_safe_float(getattr(row, "entry_price", 0.0))),
                "unrealized_pnl": _round6(_safe_float(getattr(row, "unrealized_pnl", 0.0))),
                "realized_pnl": _round6(_safe_float(getattr(row, "realized_pnl", 0.0))),
            }
        )

    return {
        "open_position_count": int(len(open_positions)),
        "risk_exposure_usd": risk_exposure_total,
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
        "user_exposure_breakdown": [
            {"user_id": user_id, "exposure_usd": _round6(exposure_usd)}
            for user_id, exposure_usd in sorted(user_exposure.items(), key=lambda kv: kv[1], reverse=True)[:DETAIL_LIST_LIMIT]
        ],
        "strategy_exposure_breakdown": [
            {"strategy": strategy, "exposure_usd": _round6(exposure_usd)}
            for strategy, exposure_usd in sorted(strategy_exposure.items(), key=lambda kv: kv[1], reverse=True)[:DETAIL_LIST_LIMIT]
        ],
        "symbol_exposure_breakdown": [
            {"symbol": symbol, "exposure_usd": _round6(exposure_usd)}
            for symbol, exposure_usd in sorted(symbol_exposure.items(), key=lambda kv: kv[1], reverse=True)[:DETAIL_LIST_LIMIT]
        ],
        "open_positions": open_positions_payload,
        "risk_limit_breach_count": len(breached_users),
        "breached_users": breached_users,
        "liquidation_risk_score": _round6(liquidation_risk_score),
        "forced_liquidation_risk": forced_liquidation_risk,
        "margin_risk_score": _round6(margin_risk_score),
        "margin_risk_state": margin_risk_state,
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
    reconciliation_logs: list[ExchangeReconciliationLog] | None = None,
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
    latest_reconciliation = max(
        reconciliation_logs or [],
        key=lambda row: getattr(row, "created_at", datetime.min.replace(tzinfo=timezone.utc)),
        default=None,
    )
    duplicate_trade_count = int(getattr(latest_reconciliation, "duplicate_trade_count", 0) or 0)
    missing_symbols = list(getattr(latest_reconciliation, "missing_symbols", []) or [])
    cross_source_validation_state = "ok"
    if missing_data_alert:
        cross_source_validation_state = "warning"
    if duplicate_trade_count > 0 or missing_symbols:
        cross_source_validation_state = "degraded"

    missing_data_sources = []
    if trade_age is None:
        missing_data_sources.append("trades")
    if pnl_age is None:
        missing_data_sources.append("pnl_records")
    if reconciliation_age is None:
        missing_data_sources.append("reconciliation")

    non_empty_sources = [
        total_trade_count > 0,
        total_pnl_records > 0,
        latest_reconciliation is not None,
    ]
    reconciliation_coverage_pct = (sum(1 for present in non_empty_sources if present) / 3 * 100) if non_empty_sources else 0.0

    freshness_by_source = {
        "trades": trade_age,
        "pnl_records": pnl_age,
        "reconciliation": reconciliation_age,
    }
    stale_source_count = sum(
        1 for source_age in [trade_age, pnl_age, reconciliation_age] if source_age is not None and source_age > stale_threshold_seconds
    )

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
        "duplicate_trade_count": duplicate_trade_count,
        "duplicate_trade_status": "warning" if duplicate_trade_count > 0 else "clean",
        "cross_source_validation_state": cross_source_validation_state,
        "missing_symbols": missing_symbols,
        "missing_data_sources": missing_data_sources,
        "reconciliation_coverage_pct": _round6(reconciliation_coverage_pct),
        "last_successful_reconciliation_at": (
            latest_reconciliation_at if latest_reconciliation and str(getattr(latest_reconciliation, "status", "")).lower() in {"completed", "success"} else None
        ),
        "freshness_by_source": freshness_by_source,
        "stale_source_count": stale_source_count,
    }


def _drawdown_series(points: list[dict]) -> tuple[list[dict], float, float]:
    peak = 0.0
    max_drawdown_usd = 0.0
    max_drawdown_pct = 0.0
    series: list[dict] = []
    for point in points:
        equity = _safe_float(point.get("total_pnl_usd", 0.0))
        peak = max(peak, equity)
        drawdown = peak - equity
        drawdown_pct = (drawdown / peak * 100.0) if peak > 0 else 0.0
        max_drawdown_usd = max(max_drawdown_usd, drawdown)
        max_drawdown_pct = max(max_drawdown_pct, drawdown_pct)
        series.append(
            {
                "bucket": point.get("bucket"),
                "equity_usd": _round6(equity),
                "drawdown_usd": _round6(drawdown),
                "drawdown_pct": _round6(drawdown_pct),
            }
        )
    return series, _round6(max_drawdown_usd), _round6(max_drawdown_pct)


def _build_pnl_analytics_block(
    trades: list[CommercialTrade],
    pnl_records: list[PnlRecord],
    *,
    top_limit: int = DETAIL_LIST_LIMIT,
) -> dict:
    strategy_map: dict[str, dict] = defaultdict(lambda: {"realized": 0.0, "unrealized": 0.0, "count": 0})
    symbol_map: dict[str, dict] = defaultdict(lambda: {"realized": 0.0, "unrealized": 0.0, "count": 0})

    for trade in trades:
        strategy = str((getattr(trade, "raw_payload", {}) or {}).get("strategy_code") or "default").lower()
        symbol = str(getattr(trade, "symbol", "") or "UNKNOWN").upper()
        realized = _safe_float(getattr(trade, "realized_pnl_usd", 0.0))
        strategy_map[strategy]["realized"] += realized
        strategy_map[strategy]["count"] += 1
        symbol_map[symbol]["realized"] += realized
        symbol_map[symbol]["count"] += 1

    daily_bucket_map: dict[str, dict] = defaultdict(lambda: {"realized": 0.0, "unrealized": 0.0})
    weekly_bucket_map: dict[str, dict] = defaultdict(lambda: {"realized": 0.0, "unrealized": 0.0})
    for row in pnl_records:
        as_of = getattr(row, "as_of", None)
        if as_of is None:
            continue
        day_bucket = as_of.date().isoformat()
        week_start = (as_of - timedelta(days=as_of.weekday())).date().isoformat()
        realized = _safe_float(getattr(row, "realized_net_usd", 0.0))
        unrealized = _safe_float(getattr(row, "unrealized_net_usd", 0.0))
        daily_bucket_map[day_bucket]["realized"] += realized
        daily_bucket_map[day_bucket]["unrealized"] += unrealized
        weekly_bucket_map[week_start]["realized"] += realized
        weekly_bucket_map[week_start]["unrealized"] += unrealized

    daily_pnl_trend = [
        {
            "bucket": bucket,
            "realized_pnl_usd": _round6(values["realized"]),
            "unrealized_pnl_usd": _round6(values["unrealized"]),
            "total_pnl_usd": _round6(values["realized"] + values["unrealized"]),
        }
        for bucket, values in sorted(daily_bucket_map.items(), key=lambda kv: kv[0])[-top_limit:]
    ]
    weekly_pnl_trend = [
        {
            "bucket": bucket,
            "realized_pnl_usd": _round6(values["realized"]),
            "unrealized_pnl_usd": _round6(values["unrealized"]),
            "total_pnl_usd": _round6(values["realized"] + values["unrealized"]),
        }
        for bucket, values in sorted(weekly_bucket_map.items(), key=lambda kv: kv[0])[-top_limit:]
    ]

    trend_for_drawdown = daily_pnl_trend or weekly_pnl_trend
    drawdown_series, max_drawdown_usd, max_drawdown_pct = _drawdown_series(trend_for_drawdown)

    return {
        "strategy_pnl_breakdown": [
            {
                "key": key,
                "realized_pnl_usd": _round6(values["realized"]),
                "unrealized_pnl_usd": _round6(values["unrealized"]),
                "total_pnl_usd": _round6(values["realized"] + values["unrealized"]),
                "trade_count": int(values["count"]),
            }
            for key, values in sorted(
                strategy_map.items(), key=lambda kv: kv[1]["realized"] + kv[1]["unrealized"], reverse=True
            )[:top_limit]
        ],
        "symbol_pnl_breakdown": [
            {
                "key": key,
                "realized_pnl_usd": _round6(values["realized"]),
                "unrealized_pnl_usd": _round6(values["unrealized"]),
                "total_pnl_usd": _round6(values["realized"] + values["unrealized"]),
                "trade_count": int(values["count"]),
            }
            for key, values in sorted(
                symbol_map.items(), key=lambda kv: kv[1]["realized"] + kv[1]["unrealized"], reverse=True
            )[:top_limit]
        ],
        "daily_pnl_trend": daily_pnl_trend,
        "weekly_pnl_trend": weekly_pnl_trend,
        "realized_vs_unrealized_trend": daily_pnl_trend,
        "max_drawdown_usd": max_drawdown_usd,
        "max_drawdown_pct": max_drawdown_pct,
        "drawdown_series": drawdown_series,
    }


def _build_export_ops_block(
    manifests: list[CommercialExportManifest],
    schedules: list[CommercialExportSchedule],
    audits: list[CommercialExportAudit] | None = None,
) -> dict:
    pending_exports = sum(1 for row in manifests if str(getattr(row, "status", "")).lower() in {"queued", "pending", "due", "running"})
    delivered_exports = sum(1 for row in manifests if str(getattr(row, "status", "")).lower() == "delivered")
    scheduler_health = "healthy"
    if any(str(getattr(row, "last_status", "")).lower() in {"failed", "error"} for row in schedules):
        scheduler_health = "degraded"
    if not schedules:
        scheduler_health = "unknown"
    return {
        "scheduler_health": scheduler_health,
        "pending_exports": pending_exports,
        "delivered_exports": delivered_exports,
        "recent_export_jobs": [
            {
                "schedule_id": str(getattr(row, "id", "")),
                "export_type": str(getattr(row, "export_type", "")),
                "schedule_period": str(getattr(row, "schedule_period", "")),
                "is_active": bool(getattr(row, "is_active", False)),
                "output_format": str(getattr(row, "output_format", "csv")),
                "last_status": str(getattr(row, "last_status", "never")),
                "last_run_at": getattr(row, "last_run_at", None),
                "last_output_ref": getattr(row, "last_output_ref", None),
                "failure_reason": (getattr(row, "filters_snapshot", {}) or {}).get("failure_reason"),
            }
            for row in sorted(schedules, key=lambda item: getattr(item, "updated_at", _now()), reverse=True)[:DETAIL_LIST_LIMIT]
        ],
        "recent_manifests": [
            {
                "export_id": str(getattr(row, "id", "")),
                "export_type": str(getattr(row, "export_type", "")),
                "status": str(getattr(row, "status", "pending")),
                "delivery_status": str(getattr(row, "delivery_status", "pending")),
                "requested_at": getattr(row, "requested_at", None),
                "delivered_at": getattr(row, "delivered_at", None),
                "artifact_ref": getattr(row, "artifact_ref", None),
                "file_hash": getattr(row, "file_hash", None),
                "failure_reason": getattr(row, "failure_reason", None),
            }
            for row in sorted(manifests, key=lambda item: getattr(item, "requested_at", _now()), reverse=True)[:DETAIL_LIST_LIMIT]
        ],
        "recent_audits": [
            {
                "audit_id": str(getattr(row, "id", "")),
                "export_id": str(getattr(row, "export_id", "")),
                "actor_email": str(getattr(row, "actor_email", "")),
                "export_type": str(getattr(row, "export_type", "")),
                "requested_at": getattr(row, "requested_at", None),
                "delivered_at": getattr(row, "delivered_at", None),
                "delivery_status": str(getattr(row, "delivery_status", "pending")),
                "artifact_ref": getattr(row, "artifact_ref", None),
                "file_hash": getattr(row, "file_hash", None),
            }
            for row in sorted(audits or [], key=lambda item: getattr(item, "created_at", _now()), reverse=True)[:DETAIL_LIST_LIMIT]
        ],
    }


def _build_alert_rail_block(
    commercial_alerts: list[CommercialAlertEvent],
    system_alerts: list,
) -> list[dict]:
    def _normalize_severity(raw_value: str | None) -> str:
        value = str(raw_value or "info").strip().lower()
        mapping = {
            "critical": "critical",
            "error": "high",
            "high": "high",
            "warning": "medium",
            "warn": "medium",
            "medium": "medium",
            "low": "low",
            "info": "info",
        }
        return mapping.get(value, "info")

    items: list[dict] = []
    for row in commercial_alerts[:DETAIL_LIST_LIMIT]:
        suggested_action = str(getattr(row, "suggested_action", "") or "").strip() or "Investigate and apply operational playbook"
        items.append(
            {
                "id": str(getattr(row, "id", "")),
                "alert_type": str(getattr(row, "alert_type", "")),
                "severity": _normalize_severity(str(getattr(row, "severity", "warning"))),
                "source": str(getattr(row, "source", "commercial.overview")),
                "entity_type": str(getattr(row, "entity_type", "system") or "system"),
                "entity_id": str(getattr(row, "entity_id", "global") or "global"),
                "title": str(getattr(row, "title", "")),
                "message": str(getattr(row, "message", "")),
                "suggested_action": suggested_action,
                "triage_status": str(getattr(row, "triage_status", "new") or "new"),
                "acknowledged_at": getattr(row, "acknowledged_at", None),
                "created_at": getattr(row, "created_at", _now()),
            }
        )

    for row in system_alerts[:DETAIL_LIST_LIMIT]:
        items.append(
            {
                "id": str(getattr(row, "id", "")),
                "alert_type": str(getattr(row, "alert_type", "system_alert")),
                "severity": _normalize_severity(str(getattr(row, "severity", "INFO"))),
                "source": "system.alerts",
                "entity_type": "system",
                "entity_id": str(getattr(row, "entity_key", "global") or "global"),
                "title": str(getattr(row, "alert_type", "system_alert")),
                "message": str(getattr(row, "message", "")),
                "suggested_action": str((getattr(row, "details", {}) or {}).get("suggested_action") or "Review alert details"),
                "triage_status": "new",
                "acknowledged_at": None,
                "created_at": getattr(row, "created_at", _now()),
            }
        )

    sorted_items = sorted(items, key=lambda item: item.get("created_at", _now()), reverse=True)
    return sorted_items[:DETAIL_LIST_LIMIT]


def _build_operational_controls_block(states: list[CommercialOperationalControlState], transitions: list[CommercialOperationalControlTransition]) -> dict:
    return {
        "trading_enabled_count": sum(1 for row in states if bool(getattr(row, "trading_enabled", False))),
        "emergency_stop_count": sum(1 for row in states if bool(getattr(row, "emergency_stop", False))),
        "capital_frozen_count": sum(1 for row in states if bool(getattr(row, "capital_frozen", False))),
        "withdraw_locked_count": sum(1 for row in states if bool(getattr(row, "withdraw_locked", False))),
        "recent_actions": [
            {
                "transition_id": str(getattr(row, "id", "")),
                "user_id": str(getattr(row, "user_id", "")),
                "actor_user_id": str(getattr(row, "actor_user_id", "")),
                "actor_email": str(getattr(row, "actor_email", "")),
                "changed_fields": list(getattr(row, "changed_fields", []) or []),
                "previous_state_snapshot": dict(getattr(row, "previous_state_snapshot", {}) or {}),
                "new_state_snapshot": dict(getattr(row, "new_state_snapshot", {}) or {}),
                "reason_note": str(getattr(row, "reason_note", "")),
                "created_at": getattr(row, "created_at", _now()),
            }
            for row in sorted(transitions, key=lambda item: getattr(item, "created_at", _now()), reverse=True)[:DETAIL_LIST_LIMIT]
        ],
    }


def _resolve_export_column_mapping(export_type: str, schema_version: str, column_mapping: dict | None) -> dict:
    key = (str(export_type or "").strip().lower(), str(schema_version or "v1").strip().lower())
    registry = EXPORT_COLUMN_REGISTRY.get(key)
    if registry is None:
        raise ValueError("unsupported_export_schema_version")
    provided = dict(column_mapping or {})
    if provided and provided != registry:
        raise ValueError("invalid_column_mapping_registry")
    return registry


def _ensure_export_artifact_dir() -> str:
    import os

    directory = "/tmp/commercial_exports"
    os.makedirs(directory, exist_ok=True)
    return directory


def finalize_export_delivery(
    db: Session,
    *,
    export_id: str,
    content_bytes: bytes,
    output_format: str,
    delivered_at: datetime | None = None,
    failure_reason: str | None = None,
) -> dict:
    manifest = _safe_query_first(db.query(CommercialExportManifest).filter(CommercialExportManifest.id == export_id))
    if manifest is None:
        raise ValueError("export_manifest_not_found")

    if failure_reason:
        manifest.status = "failed"
        manifest.delivery_status = "failed"
        manifest.failure_reason = str(failure_reason)
        db.commit()
        return {
            "export_id": export_id,
            "delivery_status": "failed",
            "failure_reason": manifest.failure_reason,
        }

    checksum = hashlib.sha256(content_bytes).hexdigest()
    artifact_dir = _ensure_export_artifact_dir()
    extension = "xlsx" if str(output_format).lower() == "xlsx" else "csv"
    artifact_ref = f"{artifact_dir}/{export_id}.{extension}"
    with open(artifact_ref, "wb") as handle:
        handle.write(content_bytes)

    delivered_ts = delivered_at or _now()
    manifest.status = "delivered"
    manifest.delivery_status = "success"
    manifest.file_hash = checksum
    manifest.delivered_at = delivered_ts
    manifest.artifact_ref = artifact_ref
    manifest.failure_reason = None

    audit_row = _safe_query_first(
        db.query(CommercialExportAudit)
        .filter(CommercialExportAudit.export_id == export_id)
        .order_by(CommercialExportAudit.created_at.desc())
    )
    if audit_row is not None:
        audit_row.file_hash = checksum
        audit_row.delivered_at = delivered_ts
        audit_row.artifact_ref = artifact_ref
        audit_row.delivery_status = "success"

    db.commit()
    return {
        "export_id": export_id,
        "artifact_ref": artifact_ref,
        "file_hash": checksum,
        "delivery_status": "success",
        "delivered_at": delivered_ts,
    }


def create_commercial_export_manifest(
    db: Session,
    *,
    actor_user: User,
    export_type: str,
    schema_version: str,
    filters_snapshot: dict,
    column_mapping: dict,
    output_format: str,
    row_count: int,
    reason_note: str,
) -> dict:
    actor_role = getattr(actor_user, "role", "")
    actor_role_value = str(getattr(actor_role, "value", actor_role)).lower()
    if actor_role_value != UserRole.SUPER_ADMIN.value:
        raise ValueError("admin_required")
    try:
        _ = db.query(CommercialExportManifest).limit(1).all()
    except Exception as exc:
        raise ValueError("export_manifest_table_unavailable") from exc
    resolved_export_type = str(export_type or "").strip().lower()
    resolved_schema_version = str(schema_version or "v1").strip().lower()
    resolved_mapping = _resolve_export_column_mapping(resolved_export_type, resolved_schema_version, column_mapping)
    checksum_base = f"{resolved_export_type}|{resolved_schema_version}|{output_format}|{row_count}|{sorted((filters_snapshot or {}).items())}|{sorted(resolved_mapping.items())}"
    checksum = hashlib.sha256(checksum_base.encode("utf-8")).hexdigest()
    manifest = CommercialExportManifest(
        export_type=resolved_export_type,
        schema_version=resolved_schema_version,
        requested_by=str(actor_user.id),
        filters_snapshot=dict(filters_snapshot or {}),
        column_mapping=resolved_mapping,
        row_count=int(row_count or 0),
        output_format=str(output_format or "csv"),
        checksum=checksum,
        status="pending",
        delivery_status="pending",
    )
    db.add(manifest)
    db.flush()

    audit = CommercialExportAudit(
        export_id=str(manifest.id),
        actor_user_id=str(actor_user.id),
        actor_email=str(actor_user.email),
        export_type=resolved_export_type,
        requested_at=getattr(manifest, "requested_at", _now()),
        filters_snapshot=dict(filters_snapshot or {}),
        reason_note=str(reason_note or ""),
        delivery_status="pending",
    )
    db.add(audit)
    db.flush()

    create_audit_log(
        db,
        action="COMMERCIAL_EXPORT_REQUESTED",
        entity_type="commercial_export_manifest",
        entity_id=str(manifest.id),
        actor_user_id=str(actor_user.id),
        actor_role=str(getattr(actor_user, "role", "super_admin")),
        details={
            "export_type": export_type,
            "schema_version": schema_version,
            "output_format": output_format,
            "reason_note": reason_note,
            "checksum": checksum,
        },
    )

    db.commit()
    db.refresh(manifest)
    return {
        "export_id": str(manifest.id),
        "export_type": str(manifest.export_type),
        "schema_version": str(manifest.schema_version),
        "requested_by": str(actor_user.id),
        "requested_at": manifest.requested_at,
        "output_format": str(manifest.output_format),
        "checksum": str(manifest.checksum),
        "status": str(manifest.status),
    }


def create_commercial_export_schedule(
    db: Session,
    *,
    actor_user: User,
    export_type: str,
    schedule_period: str,
    output_format: str,
    filters_snapshot: dict,
) -> dict:
    actor_role = getattr(actor_user, "role", "")
    actor_role_value = str(getattr(actor_role, "value", actor_role)).lower()
    if actor_role_value != UserRole.SUPER_ADMIN.value:
        raise ValueError("admin_required")
    try:
        _ = db.query(CommercialExportSchedule).limit(1).all()
    except Exception as exc:
        raise ValueError("export_schedule_table_unavailable") from exc
    schedule = CommercialExportSchedule(
        export_type=str(export_type),
        schedule_period=str(schedule_period),
        output_format=str(output_format),
        requested_by=str(actor_user.id),
        filters_snapshot=dict(filters_snapshot or {}),
        is_active=True,
        last_status="pending",
    )
    db.add(schedule)
    db.flush()
    create_audit_log(
        db,
        action="COMMERCIAL_EXPORT_SCHEDULE_CREATED",
        entity_type="commercial_export_schedule",
        entity_id=str(schedule.id),
        actor_user_id=str(actor_user.id),
        actor_role=str(getattr(actor_user, "role", "super_admin")),
        details={"export_type": export_type, "schedule_period": schedule_period},
    )
    db.commit()
    db.refresh(schedule)
    return {
        "schedule_id": str(schedule.id),
        "export_type": str(schedule.export_type),
        "schedule_period": str(schedule.schedule_period),
        "output_format": str(schedule.output_format),
        "is_active": bool(schedule.is_active),
        "last_status": str(schedule.last_status),
        "last_run_at": schedule.last_run_at,
    }


def list_commercial_export_schedules(db: Session) -> list[dict]:
    try:
        rows = (
            db.query(CommercialExportSchedule)
            .order_by(CommercialExportSchedule.updated_at.desc())
            .limit(DETAIL_LIST_LIMIT)
            .all()
        )
    except Exception:
        return []
    return [
        {
            "schedule_id": str(row.id),
            "export_type": str(row.export_type),
            "schedule_period": str(row.schedule_period),
            "output_format": str(row.output_format),
            "is_active": bool(row.is_active),
            "last_status": str(row.last_status),
            "last_run_at": row.last_run_at,
        }
        for row in rows
    ]


def update_user_operational_controls(
    db: Session,
    *,
    actor_user: User,
    target_user_id: str,
    trading_enabled: bool,
    capital_frozen: bool,
    withdraw_locked: bool,
    emergency_stop: bool,
    reason_note: str,
) -> dict:
    actor_role = getattr(actor_user, "role", "")
    actor_role_value = str(getattr(actor_role, "value", actor_role)).lower()
    if actor_role_value != UserRole.SUPER_ADMIN.value:
        raise ValueError("admin_required")
    normalized_reason = str(reason_note or "").strip()
    if len(normalized_reason) < 5:
        raise ValueError("reason_note_required")

    target_user = _safe_query_first(db.query(User).filter(User.id == target_user_id))
    if target_user is None:
        raise ValueError("target_user_not_found")

    try:
        state = db.query(CommercialOperationalControlState).filter(CommercialOperationalControlState.user_id == target_user_id).first()
    except Exception as exc:
        raise ValueError("operational_control_table_unavailable") from exc
    if state is None:
        state = CommercialOperationalControlState(user_id=target_user_id)
        db.add(state)
        db.flush()

    previous_state = {
        "trading_enabled": bool(getattr(state, "trading_enabled", True)),
        "capital_frozen": bool(getattr(state, "capital_frozen", False)),
        "withdraw_locked": bool(getattr(state, "withdraw_locked", False)),
        "emergency_stop": bool(getattr(state, "emergency_stop", False)),
    }
    if emergency_stop:
        trading_enabled = False
    next_state = {
        "trading_enabled": bool(trading_enabled),
        "capital_frozen": bool(capital_frozen),
        "withdraw_locked": bool(withdraw_locked),
        "emergency_stop": bool(emergency_stop),
    }
    changed_fields = [
        key
        for key in ["trading_enabled", "capital_frozen", "withdraw_locked", "emergency_stop"]
        if bool(previous_state.get(key)) != bool(next_state.get(key))
    ]
    state.trading_enabled = bool(trading_enabled)
    state.capital_frozen = bool(capital_frozen)
    state.withdraw_locked = bool(withdraw_locked)
    state.emergency_stop = bool(emergency_stop)
    state.reason_note = normalized_reason
    state.updated_by = str(actor_user.id)

    transition = CommercialOperationalControlTransition(
        user_id=target_user_id,
        actor_user_id=str(actor_user.id),
        actor_email=str(actor_user.email),
        previous_state=previous_state,
        next_state=next_state,
        previous_state_snapshot=previous_state,
        new_state_snapshot=next_state,
        changed_fields=changed_fields,
        reason_note=normalized_reason,
    )
    db.add(transition)
    db.flush()
    create_audit_log(
        db,
        action="COMMERCIAL_OPERATIONAL_CONTROL_UPDATED",
        entity_type="commercial_operational_control",
        entity_id=target_user_id,
        actor_user_id=str(actor_user.id),
        actor_role=str(getattr(actor_user, "role", "super_admin")),
        details={"reason_note": normalized_reason, "previous_state": previous_state, "next_state": next_state},
    )
    db.commit()
    db.refresh(state)

    return {
        "user_id": target_user_id,
        "trading_enabled": bool(state.trading_enabled),
        "capital_frozen": bool(state.capital_frozen),
        "withdraw_locked": bool(state.withdraw_locked),
        "emergency_stop": bool(state.emergency_stop),
        "reason_note": str(state.reason_note),
        "updated_at": state.updated_at,
    }


def update_commercial_alert_lifecycle(
    db: Session,
    *,
    actor_user: User,
    alert_id: str,
    triage_status: str,
    escalation_level: str,
    resolution_note: str | None,
    acknowledge: bool,
) -> dict:
    row = _safe_query_first(db.query(CommercialAlertEvent).filter(CommercialAlertEvent.id == alert_id))
    if row is None:
        raise ValueError("alert_not_found")

    if not str(getattr(row, "suggested_action", "") or "").strip():
        row.suggested_action = "Review affected entity and apply recovery runbook"

    row.triage_status = str(triage_status)
    row.escalation_level = str(escalation_level)
    if acknowledge:
        row.acknowledged_by = str(actor_user.id)
        row.acknowledged_at = _now()
    if resolution_note:
        row.resolution_note = str(resolution_note)
    if str(triage_status) == "resolved":
        row.resolution_at = _now()
        row.status = "closed"
    else:
        row.status = "open"

    create_audit_log(
        db,
        action="COMMERCIAL_ALERT_LIFECYCLE_UPDATED",
        entity_type="commercial_alert",
        entity_id=str(row.id),
        actor_user_id=str(actor_user.id),
        actor_role=str(getattr(actor_user.role, "value", actor_user.role)),
        details={
            "triage_status": triage_status,
            "escalation_level": escalation_level,
            "acknowledge": acknowledge,
            "resolution_note": resolution_note,
        },
    )
    db.commit()
    db.refresh(row)
    return {
        "alert_id": str(row.id),
        "triage_status": str(row.triage_status),
        "escalation_level": str(row.escalation_level),
        "acknowledged_by": str(row.acknowledged_by) if row.acknowledged_by else None,
        "acknowledged_at": row.acknowledged_at,
        "resolution_note": row.resolution_note,
        "resolution_at": row.resolution_at,
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
    usage_event_query = db.query(CommercialUsageEvent).filter(CommercialUsageEvent.environment == applied_environment)
    subscription_query = db.query(CommercialSubscriptionProfile).filter(
        CommercialSubscriptionProfile.environment == applied_environment
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
    usage_event_query = _apply_range_filters(usage_event_query, CommercialUsageEvent.created_at, range_start, range_end)
    subscription_query = _apply_range_filters(
        subscription_query,
        CommercialSubscriptionProfile.updated_at,
        range_start,
        range_end,
    )

    trades = _safe_query_all(trade_query)
    pnl_records = _safe_query_all(pnl_query)
    revenue_rows = _safe_query_all(revenue_query)
    reconciliation_logs = _safe_query_all(reconciliation_query)
    usage_events = _safe_query_all(usage_event_query)
    subscription_rows = _safe_query_all(subscription_query)

    user_economics_query = db.query(UserEconomicsAggregate).filter(UserEconomicsAggregate.environment == applied_environment)
    windowed_user_economics_query = _apply_range_filters(
        user_economics_query,
        UserEconomicsAggregate.updated_at,
        range_start,
        range_end,
    )
    user_economics_rows = _safe_query_all(windowed_user_economics_query)
    if not user_economics_rows and (range_start is not None or range_end is not None):
        user_economics_rows = _safe_query_all(user_economics_query)

    open_positions = _safe_query_all(db.query(PaperPosition).filter(PaperPosition.status == "open"))
    risk_policy = _safe_query_first(db.query(RiskOrchestratorPolicy).order_by(RiskOrchestratorPolicy.updated_at.desc()))
    live_config = _safe_query_first(db.query(LiveActivationConfig))
    export_manifests = _safe_query_all(
        db.query(CommercialExportManifest).order_by(CommercialExportManifest.requested_at.desc()).limit(DETAIL_LIST_LIMIT)
    )
    export_schedules = _safe_query_all(
        db.query(CommercialExportSchedule).order_by(CommercialExportSchedule.updated_at.desc()).limit(DETAIL_LIST_LIMIT)
    )
    export_audits = _safe_query_all(
        db.query(CommercialExportAudit).order_by(CommercialExportAudit.created_at.desc()).limit(DETAIL_LIST_LIMIT)
    )
    operational_states = _safe_query_all(
        db.query(CommercialOperationalControlState)
        .order_by(CommercialOperationalControlState.updated_at.desc())
        .limit(DETAIL_LIST_LIMIT)
    )
    operational_transitions = _safe_query_all(
        db.query(CommercialOperationalControlTransition)
        .order_by(CommercialOperationalControlTransition.created_at.desc())
        .limit(DETAIL_LIST_LIMIT)
    )
    commercial_alerts = _safe_query_all(
        db.query(CommercialAlertEvent).order_by(CommercialAlertEvent.created_at.desc()).limit(DETAIL_LIST_LIMIT)
    )
    system_alerts = _safe_query_all(db.query(SystemAlert).order_by(SystemAlert.created_at.desc()).limit(DETAIL_LIST_LIMIT))

    user_ids = {
        *{str(getattr(row, "user_id", "")) for row in revenue_rows if getattr(row, "user_id", None)},
        *{str(getattr(row, "user_id", "")) for row in user_economics_rows if getattr(row, "user_id", None)},
        *{str(getattr(row, "user_id", "")) for row in subscription_rows if getattr(row, "user_id", None)},
    }
    user_email_map: dict[str, str] = {}
    if user_ids:
        users = _safe_query_all(db.query(User).filter(User.id.in_(list(user_ids))))
        user_email_map = {str(user.id): str(user.email) for user in users}

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
        "contract_version": "v2",
        "applied_filters": {
            "environment": applied_environment,
            "time_window": applied_time_window,
            "from_ts": from_iso,
            "to_ts": to_iso,
            "range_start": range_start,
            "range_end": range_end,
        },
        "financial_accuracy": _build_financial_accuracy_block(trades, pnl_records, reconciliation_logs),
        "revenue_model": _build_revenue_model_block(
            revenue_rows,
            subscription_profiles=subscription_rows,
            user_email_map=user_email_map,
        ),
        "user_economics": _build_user_economics_block(user_economics_rows),
        "pnl_analytics": _build_pnl_analytics_block(trades, pnl_records),
        "risk_summary": _build_risk_summary_block(
            trades,
            reconciliation_logs,
            open_positions=open_positions,
            risk_policy=risk_policy,
            live_config=live_config,
        ),
        "usage_analytics": _build_usage_analytics_block(trades, usage_events),
        "data_quality": _build_data_quality_block(
            now=now,
            total_trade_count=len(trades),
            total_pnl_records=len(pnl_records),
            latest_trade_at=latest_trade_at,
            latest_pnl_at=latest_pnl_at,
            latest_reconciliation_at=latest_reconciliation_at,
            missing_data_alert=missing_data_alert,
            reconciliation_logs=reconciliation_logs,
        ),
        "export_ops": _build_export_ops_block(export_manifests, export_schedules, export_audits),
        "alert_rail": _build_alert_rail_block(commercial_alerts, system_alerts),
        "operational_controls": _build_operational_controls_block(operational_states, operational_transitions),
    }