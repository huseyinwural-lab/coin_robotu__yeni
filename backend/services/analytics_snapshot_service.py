import csv
import io
from datetime import datetime, timedelta, timezone

from openpyxl import Workbook
from sqlalchemy.orm import Session

from models import AnalyticsSnapshot, RevenueLedger, User
from services.revenue_engine_service import get_revenue_summary
from services.user_economics_service import get_segment_profitability, get_user_economics_summary


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_snapshot_type(snapshot_type: str) -> str:
    normalized = str(snapshot_type or "daily").strip().lower()
    if normalized not in {"daily", "weekly"}:
        raise ValueError("invalid_snapshot_type")
    return normalized


def _normalize_snapshot_date(snapshot_type: str, as_of_date: str | None) -> datetime:
    raw_snapshot_dt = _parse_datetime(as_of_date) or datetime.now(timezone.utc)
    if snapshot_type == "weekly":
        return (raw_snapshot_dt - timedelta(days=raw_snapshot_dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return raw_snapshot_dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _csv_bytes_iterator(columns: list[str], rows: list[dict] | tuple[dict, ...] | object):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    yield buffer.getvalue().encode("utf-8")
    buffer.seek(0)
    buffer.truncate(0)

    for row in rows:
        writer.writerow({column: row.get(column) for column in columns})
        yield buffer.getvalue().encode("utf-8")
        buffer.seek(0)
        buffer.truncate(0)


def _xlsx_bytes(columns: list[str], rows: list[dict] | tuple[dict, ...] | object, *, sheet_name: str) -> bytes:
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet(title=sheet_name)
    sheet.append(columns)
    for row in rows:
        sheet.append([row.get(column) for column in columns])
    bytes_io = io.BytesIO()
    workbook.save(bytes_io)
    return bytes_io.getvalue()


def export_revenue_ledger(
    db: Session,
    *,
    environment: str,
    start_date: str | None,
    end_date: str | None,
    user_id: str | None,
    user_email: str | None,
    symbol: str | None,
    output: str,
):
    query = db.query(RevenueLedger, User.email).outerjoin(User, RevenueLedger.user_id == User.id).filter(RevenueLedger.environment == environment)

    if user_email:
        target_user = db.query(User).filter(User.email == user_email.strip().lower()).first()
        if target_user is None:
            raise ValueError("target_user_not_found")
        query = query.filter(RevenueLedger.user_id == target_user.id)
    elif user_id:
        query = query.filter(RevenueLedger.user_id == user_id)

    if symbol:
        query = query.filter(RevenueLedger.symbol == symbol.strip().upper())

    start_dt = _parse_datetime(start_date)
    end_dt = _parse_datetime(end_date)
    if start_dt is not None:
        query = query.filter(RevenueLedger.trade_time >= start_dt)
    if end_dt is not None:
        query = query.filter(RevenueLedger.trade_time <= end_dt)

    columns = [
        "trade_time",
        "environment",
        "exchange",
        "market_type",
        "symbol",
        "user_id",
        "user_email",
        "trade_id",
        "component_type",
        "source_amount_usd",
        "share_rate",
        "revenue_amount_usd",
    ]

    def _rows():
        cursor = query.order_by(RevenueLedger.trade_time.asc(), RevenueLedger.id.asc()).yield_per(500)
        for ledger, joined_email in cursor:
            yield {
                "trade_time": ledger.trade_time.isoformat() if ledger.trade_time else None,
                "environment": ledger.environment,
                "exchange": ledger.exchange,
                "market_type": ledger.market_type,
                "symbol": ledger.symbol,
                "user_id": ledger.user_id,
                "user_email": joined_email or "unknown",
                "trade_id": ledger.trade_id,
                "component_type": ledger.component_type,
                "source_amount_usd": round(float(ledger.source_amount_usd or 0), 8),
                "share_rate": round(float(ledger.share_rate or 0), 8),
                "revenue_amount_usd": round(float(ledger.revenue_amount_usd or 0), 8),
            }

    if output == "csv":
        return (
            _csv_bytes_iterator(columns, _rows()),
            "text/csv",
            "revenue_export.csv",
        )

    if output == "xlsx":
        payload = _xlsx_bytes(columns, _rows(), sheet_name="revenue")
        return (
            iter([payload]),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "revenue_export.xlsx",
        )

    raise ValueError("invalid_export_format")


def export_user_economics_aggregates(
    db: Session,
    *,
    environment: str,
    start_date: str | None,
    end_date: str | None,
    user_email: str | None,
    symbol: str | None,
    churn_inactive_days: int,
    cohort_month: str | None,
    top_limit: int,
    output: str,
):
    summary = get_user_economics_summary(
        db,
        environment=environment,
        start_date=start_date,
        end_date=end_date,
        user_email=user_email,
        symbol=symbol,
        churn_inactive_days=churn_inactive_days,
        cohort_month=cohort_month,
        top_limit=top_limit,
    )

    columns = [
        "user_id",
        "email",
        "ltv_usd",
        "revenue_contribution_usd",
        "realized_pnl_usd",
        "inactive_days",
        "churned",
        "cohort_month",
        "last_activity_at",
    ]
    rows = summary.get("rows", [])

    if output == "csv":
        return (
            _csv_bytes_iterator(columns, rows),
            "text/csv",
            "user_economics_export.csv",
        )

    if output == "xlsx":
        payload = _xlsx_bytes(columns, rows, sheet_name="user_economics")
        return (
            iter([payload]),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "user_economics_export.xlsx",
        )

    raise ValueError("invalid_export_format")


def run_analytics_snapshot(
    db: Session,
    *,
    environment: str,
    snapshot_type: str,
    as_of_date: str | None,
    churn_inactive_days: int,
    top_limit: int,
) -> dict:
    normalized_type = _normalize_snapshot_type(snapshot_type)
    snapshot_date = _normalize_snapshot_date(normalized_type, as_of_date)

    revenue_summary = get_revenue_summary(
        db,
        environment=environment,
        start_date=None,
        end_date=None,
        user_id=None,
        user_email=None,
        symbol=None,
        top_limit=top_limit,
    )
    economics_summary = get_user_economics_summary(
        db,
        environment=environment,
        start_date=None,
        end_date=None,
        user_email=None,
        symbol=None,
        churn_inactive_days=churn_inactive_days,
        cohort_month=None,
        top_limit=top_limit,
    )
    segment_summary = get_segment_profitability(
        db,
        environment=environment,
        churn_inactive_days=churn_inactive_days,
        top_limit=top_limit,
    )

    payload = {
        "kpis": {
            "total_revenue_usd": revenue_summary.get("total_revenue_usd", 0.0),
            "today_revenue_usd": revenue_summary.get("today_revenue_usd", 0.0),
            "total_users": economics_summary.get("kpis", {}).get("total_users", 0),
            "paying_users": economics_summary.get("kpis", {}).get("paying_users", 0),
            "churned_users": economics_summary.get("kpis", {}).get("churned_users", 0),
            "churn_rate_pct": economics_summary.get("kpis", {}).get("churn_rate_pct", 0.0),
            "arpu_usd": economics_summary.get("kpis", {}).get("arpu_usd", 0.0),
            "arppu_usd": economics_summary.get("kpis", {}).get("arppu_usd", 0.0),
            "avg_ltv_usd": economics_summary.get("kpis", {}).get("avg_ltv_usd", 0.0),
        },
        "top_users": revenue_summary.get("top_users", [])[:top_limit],
        "segments": segment_summary.get("segment_cards", []),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    snapshot_row = (
        db.query(AnalyticsSnapshot)
        .filter(
            AnalyticsSnapshot.environment == environment,
            AnalyticsSnapshot.snapshot_type == normalized_type,
            AnalyticsSnapshot.snapshot_date == snapshot_date,
        )
        .first()
    )

    created = False
    if snapshot_row is None:
        snapshot_row = AnalyticsSnapshot(
            environment=environment,
            snapshot_type=normalized_type,
            snapshot_date=snapshot_date,
            payload=payload,
        )
        db.add(snapshot_row)
        created = True
    else:
        snapshot_row.payload = payload

    db.flush()
    db.commit()

    return {
        "status": "ok",
        "snapshot_id": snapshot_row.id,
        "snapshot_type": normalized_type,
        "environment": environment,
        "snapshot_date": snapshot_date.isoformat(),
        "created": created,
        "payload": {
            "kpis": payload["kpis"],
            "top_users_count": len(payload.get("top_users", [])),
            "segments_count": len(payload.get("segments", [])),
        },
    }


def list_analytics_snapshots(
    db: Session,
    *,
    environment: str,
    snapshot_type: str,
    limit: int,
) -> dict:
    normalized_type = _normalize_snapshot_type(snapshot_type)
    rows = (
        db.query(AnalyticsSnapshot)
        .filter(
            AnalyticsSnapshot.environment == environment,
            AnalyticsSnapshot.snapshot_type == normalized_type,
        )
        .order_by(AnalyticsSnapshot.snapshot_date.desc(), AnalyticsSnapshot.created_at.desc())
        .limit(limit)
        .all()
    )

    items = []
    for row in rows:
        payload = row.payload or {}
        items.append(
            {
                "id": row.id,
                "snapshot_type": row.snapshot_type,
                "environment": row.environment,
                "snapshot_date": row.snapshot_date.isoformat(),
                "kpis": payload.get("kpis", {}),
                "top_users_count": len(payload.get("top_users", [])),
                "segments_count": len(payload.get("segments", [])),
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )

    return {
        "status": "ok",
        "snapshot_type": normalized_type,
        "environment": environment,
        "items": items,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _build_kpi_delta(base_kpis: dict, target_kpis: dict) -> list[dict]:
    keys = sorted(set(base_kpis.keys()) | set(target_kpis.keys()))
    items = []
    for key in keys:
        base_value = float(base_kpis.get(key, 0) or 0)
        target_value = float(target_kpis.get(key, 0) or 0)
        delta = target_value - base_value
        delta_pct = None if base_value == 0 else (delta / base_value) * 100.0
        items.append(
            {
                "metric": key,
                "from": round(base_value, 8),
                "to": round(target_value, 8),
                "delta": round(delta, 8),
                "delta_pct": round(delta_pct, 6) if delta_pct is not None else None,
            }
        )
    return items


def _build_top_user_delta(base_users: list[dict], target_users: list[dict]) -> list[dict]:
    base_map = {item.get("user_id"): item for item in base_users if item.get("user_id")}
    target_map = {item.get("user_id"): item for item in target_users if item.get("user_id")}
    base_rank = {item.get("user_id"): index + 1 for index, item in enumerate(base_users) if item.get("user_id")}
    target_rank = {item.get("user_id"): index + 1 for index, item in enumerate(target_users) if item.get("user_id")}

    rows = []
    for user_id in sorted(set(base_map.keys()) | set(target_map.keys())):
        before = base_map.get(user_id, {})
        after = target_map.get(user_id, {})
        from_revenue = float(before.get("revenue_usd", 0) or 0)
        to_revenue = float(after.get("revenue_usd", 0) or 0)
        from_rank = base_rank.get(user_id)
        to_rank = target_rank.get(user_id)
        rows.append(
            {
                "user_id": user_id,
                "email": after.get("email") or before.get("email") or "unknown",
                "from_revenue_usd": round(from_revenue, 8),
                "to_revenue_usd": round(to_revenue, 8),
                "delta_revenue_usd": round(to_revenue - from_revenue, 8),
                "from_rank": from_rank,
                "to_rank": to_rank,
                "rank_change": (from_rank - to_rank) if (from_rank and to_rank) else None,
            }
        )

    rows.sort(key=lambda item: (-abs(item["delta_revenue_usd"]), item["user_id"]))
    return rows


def _build_segment_delta(base_segments: list[dict], target_segments: list[dict]) -> list[dict]:
    base_map = {item.get("segment"): item for item in base_segments if item.get("segment")}
    target_map = {item.get("segment"): item for item in target_segments if item.get("segment")}
    rows = []
    for segment in sorted(set(base_map.keys()) | set(target_map.keys())):
        before = base_map.get(segment, {})
        after = target_map.get(segment, {})
        from_users = int(before.get("users", 0) or 0)
        to_users = int(after.get("users", 0) or 0)
        from_revenue = float(before.get("total_revenue_usd", 0) or 0)
        to_revenue = float(after.get("total_revenue_usd", 0) or 0)
        rows.append(
            {
                "segment": segment,
                "from_users": from_users,
                "to_users": to_users,
                "delta_users": to_users - from_users,
                "from_revenue_usd": round(from_revenue, 8),
                "to_revenue_usd": round(to_revenue, 8),
                "delta_revenue_usd": round(to_revenue - from_revenue, 8),
            }
        )
    rows.sort(key=lambda item: item["segment"])
    return rows


def compare_analytics_snapshots(
    db: Session,
    *,
    base_snapshot_id: str,
    target_snapshot_id: str,
) -> dict:
    base_snapshot = db.query(AnalyticsSnapshot).filter(AnalyticsSnapshot.id == base_snapshot_id).first()
    target_snapshot = db.query(AnalyticsSnapshot).filter(AnalyticsSnapshot.id == target_snapshot_id).first()

    if base_snapshot is None or target_snapshot is None:
        raise ValueError("snapshot_not_found")
    if base_snapshot.environment != target_snapshot.environment:
        raise ValueError("snapshot_environment_mismatch")
    if base_snapshot.snapshot_type != target_snapshot.snapshot_type:
        raise ValueError("snapshot_type_mismatch")

    base_payload = base_snapshot.payload or {}
    target_payload = target_snapshot.payload or {}

    base_kpis = base_payload.get("kpis", {})
    target_kpis = target_payload.get("kpis", {})
    base_top_users = base_payload.get("top_users", [])
    target_top_users = target_payload.get("top_users", [])
    base_segments = base_payload.get("segments", [])
    target_segments = target_payload.get("segments", [])

    return {
        "status": "ok",
        "snapshot_type": base_snapshot.snapshot_type,
        "environment": base_snapshot.environment,
        "base_snapshot": {
            "id": base_snapshot.id,
            "snapshot_date": base_snapshot.snapshot_date.isoformat(),
        },
        "target_snapshot": {
            "id": target_snapshot.id,
            "snapshot_date": target_snapshot.snapshot_date.isoformat(),
        },
        "delta": {
            "kpis": _build_kpi_delta(base_kpis, target_kpis),
            "top_users": _build_top_user_delta(base_top_users, target_top_users),
            "segments": _build_segment_delta(base_segments, target_segments),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
