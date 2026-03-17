from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from io import BytesIO

from openpyxl import Workbook
from sqlalchemy.orm import Session

from models import ExecutionMetric, PaperPosition, User, UserRole


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