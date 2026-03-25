import csv
import io
from datetime import datetime, timedelta, timezone

from openpyxl import Workbook
from sqlalchemy.orm import Session

from models import CommercialTrade, RevenueLedger, User, UserEconomicsAggregate, UserEconomicsSnapshot


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


def _period_key(dt: datetime, granularity: str) -> str:
    utc_dt = dt.astimezone(timezone.utc)
    if granularity == "weekly":
        year, week, _ = utc_dt.isocalendar()
        return f"{year}-W{week:02d}"
    return utc_dt.strftime("%Y-%m")


def _classify_segment(*, revenue_usd: float, realized_pnl_usd: float, inactive_days: int, high_value_cutoff: float, churn_days: int) -> str:
    if revenue_usd >= high_value_cutoff and revenue_usd > 0:
        return "high_value"
    if realized_pnl_usd > 0 and inactive_days >= churn_days:
        return "profitable_but_inactive"
    if 7 <= inactive_days < churn_days and revenue_usd > 0:
        return "churn_risk"
    if realized_pnl_usd < 0 and abs(realized_pnl_usd) >= 10:
        return "loss_heavy_users"
    if inactive_days >= 7 and revenue_usd <= 0.5:
        return "low_activity_low_revenue"
    return "low_activity_low_revenue"


def sync_user_economics_aggregates(db: Session, *, environment: str, churn_inactive_days: int = 30) -> dict:
    users = {item.id: item.email for item in db.query(User.id, User.email).all()}

    revenue_rows = db.query(RevenueLedger).filter(RevenueLedger.environment == environment).all()
    trade_rows = db.query(CommercialTrade).filter(CommercialTrade.environment == environment).all()

    grouped: dict[str, dict] = {}

    def bucket(user_id: str) -> dict:
        if user_id not in grouped:
            grouped[user_id] = {
                "revenue": 0.0,
                "realized_pnl": 0.0,
                "first_activity": None,
                "last_activity": None,
            }
        return grouped[user_id]

    for row in revenue_rows:
        item = bucket(row.user_id)
        item["revenue"] += float(row.revenue_amount_usd or 0)
        if row.trade_time is not None:
            item["first_activity"] = min(item["first_activity"], row.trade_time) if item["first_activity"] else row.trade_time
            item["last_activity"] = max(item["last_activity"], row.trade_time) if item["last_activity"] else row.trade_time

    for row in trade_rows:
        item = bucket(row.user_id)
        item["realized_pnl"] += float(row.realized_pnl_usd or 0)
        if row.trade_time is not None:
            item["first_activity"] = min(item["first_activity"], row.trade_time) if item["first_activity"] else row.trade_time
            item["last_activity"] = max(item["last_activity"], row.trade_time) if item["last_activity"] else row.trade_time

    total_revenue = sum(max(0.0, value["revenue"]) for value in grouped.values())
    now = datetime.now(timezone.utc)

    existing_rows = db.query(UserEconomicsAggregate).filter(UserEconomicsAggregate.environment == environment).all()
    existing_by_user = {row.user_id: row for row in existing_rows}

    inserted = 0
    updated = 0
    for user_id, value in grouped.items():
        revenue = round(float(value["revenue"]), 10)
        realized_pnl = round(float(value["realized_pnl"]), 10)
        first_activity = value["first_activity"]
        last_activity = value["last_activity"]
        inactive_days = 9999 if last_activity is None else max(0, (now.date() - last_activity.date()).days)
        churned = bool(last_activity is not None and inactive_days >= churn_inactive_days)
        cohort_month = first_activity.strftime("%Y-%m") if first_activity else None
        contribution_pct = 0.0 if total_revenue <= 0 else (max(revenue, 0.0) / total_revenue) * 100.0

        row = existing_by_user.get(user_id)
        if row is None:
            row = UserEconomicsAggregate(
                user_id=user_id,
                environment=environment,
                user_email=users.get(user_id, "unknown"),
                ltv_usd=round(max(revenue, 0.0), 10),
                revenue_contribution_usd=revenue,
                realized_pnl_usd=realized_pnl,
                first_activity_at=first_activity,
                last_activity_at=last_activity,
                inactive_days=inactive_days,
                churned=churned,
                cohort_month=cohort_month,
                details={"revenue_contribution_pct": round(contribution_pct, 8)},
            )
            db.add(row)
            inserted += 1
            continue

        row.user_email = users.get(user_id, row.user_email)
        row.ltv_usd = round(max(revenue, 0.0), 10)
        row.revenue_contribution_usd = revenue
        row.realized_pnl_usd = realized_pnl
        row.first_activity_at = first_activity
        row.last_activity_at = last_activity
        row.inactive_days = inactive_days
        row.churned = churned
        row.cohort_month = cohort_month
        row.details = {"revenue_contribution_pct": round(contribution_pct, 8)}
        updated += 1

    db.flush()
    db.commit()
    return {
        "status": "ok",
        "environment": environment,
        "rows": len(grouped),
        "inserted": inserted,
        "updated": updated,
    }


def _build_filtered_datasets(
    db: Session,
    *,
    environment: str,
    start_date: str | None,
    end_date: str | None,
    user_email: str | None,
    symbol: str | None,
):
    revenue_query = db.query(RevenueLedger).filter(RevenueLedger.environment == environment)
    trade_query = db.query(CommercialTrade).filter(CommercialTrade.environment == environment)
    aggregate_query = db.query(UserEconomicsAggregate).filter(UserEconomicsAggregate.environment == environment)

    if user_email:
        user = db.query(User).filter(User.email == user_email.strip().lower()).first()
        if user is None:
            raise ValueError("target_user_not_found")
        revenue_query = revenue_query.filter(RevenueLedger.user_id == user.id)
        trade_query = trade_query.filter(CommercialTrade.user_id == user.id)
        aggregate_query = aggregate_query.filter(UserEconomicsAggregate.user_id == user.id)

    if symbol:
        normalized_symbol = symbol.strip().upper()
        revenue_query = revenue_query.filter(RevenueLedger.symbol == normalized_symbol)
        trade_query = trade_query.filter(CommercialTrade.symbol == normalized_symbol)

    start_dt = _parse_datetime(start_date)
    end_dt = _parse_datetime(end_date)
    if start_dt is not None:
        revenue_query = revenue_query.filter(RevenueLedger.trade_time >= start_dt)
        trade_query = trade_query.filter(CommercialTrade.trade_time >= start_dt)
    if end_dt is not None:
        revenue_query = revenue_query.filter(RevenueLedger.trade_time <= end_dt)
        trade_query = trade_query.filter(CommercialTrade.trade_time <= end_dt)

    return revenue_query.all(), trade_query.all(), aggregate_query.all()


def _compose_user_rows(
    *,
    revenue_rows: list[RevenueLedger],
    trade_rows: list[CommercialTrade],
    aggregate_rows: list[UserEconomicsAggregate],
    cohort_month: str | None,
) -> tuple[list[dict], dict[str, float]]:
    revenue_by_user: dict[str, float] = {}
    top_symbols_map: dict[str, float] = {}
    for row in revenue_rows:
        amount = float(row.revenue_amount_usd or 0)
        revenue_by_user[row.user_id] = revenue_by_user.get(row.user_id, 0.0) + amount
        top_symbols_map[row.symbol] = top_symbols_map.get(row.symbol, 0.0) + amount

    pnl_by_user: dict[str, float] = {}
    for row in trade_rows:
        amount = float(row.realized_pnl_usd or 0)
        pnl_by_user[row.user_id] = pnl_by_user.get(row.user_id, 0.0) + amount

    aggregate_by_user = {row.user_id: row for row in aggregate_rows}
    user_ids = sorted(set(revenue_by_user.keys()) | set(pnl_by_user.keys()) | set(aggregate_by_user.keys()))

    rows = []
    for user_id in user_ids:
        agg = aggregate_by_user.get(user_id)
        revenue_value = round(revenue_by_user.get(user_id, 0.0), 8)
        realized_pnl_value = round(pnl_by_user.get(user_id, 0.0), 8)
        ltv_value = round(float(agg.ltv_usd if agg else 0.0), 8)
        inactive_days = int(agg.inactive_days if agg else 9999)
        churned = bool(agg.churned if agg else False)
        row = {
            "user_id": user_id,
            "email": agg.user_email if agg else "unknown",
            "ltv_usd": ltv_value,
            "revenue_contribution_usd": revenue_value,
            "realized_pnl_usd": realized_pnl_value,
            "inactive_days": inactive_days,
            "churned": churned,
            "cohort_month": agg.cohort_month if agg else None,
            "last_activity_at": agg.last_activity_at.isoformat() if agg and agg.last_activity_at else None,
        }
        if cohort_month and row["cohort_month"] != cohort_month:
            continue
        rows.append(row)

    return rows, top_symbols_map


def get_user_economics_summary(
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
) -> dict:
    sync_result = sync_user_economics_aggregates(db, environment=environment, churn_inactive_days=churn_inactive_days)
    revenue_rows, trade_rows, aggregate_rows = _build_filtered_datasets(
        db,
        environment=environment,
        start_date=start_date,
        end_date=end_date,
        user_email=user_email,
        symbol=symbol,
    )
    rows, top_symbols_map = _compose_user_rows(
        revenue_rows=revenue_rows,
        trade_rows=trade_rows,
        aggregate_rows=aggregate_rows,
        cohort_month=cohort_month,
    )

    total_users = len(rows)
    total_revenue = round(sum(item["revenue_contribution_usd"] for item in rows), 8)
    paying_users = sum(1 for item in rows if item["revenue_contribution_usd"] > 0)
    churned_users = sum(1 for item in rows if item["churned"])
    arpu = round(total_revenue / total_users, 8) if total_users > 0 else 0.0
    arppu = round(total_revenue / paying_users, 8) if paying_users > 0 else 0.0
    avg_ltv = round(sum(item["ltv_usd"] for item in rows) / total_users, 8) if total_users > 0 else 0.0
    churn_rate = round((churned_users / total_users) * 100.0, 4) if total_users > 0 else 0.0

    top_users = sorted(rows, key=lambda item: (-item["revenue_contribution_usd"], item["user_id"]))[:top_limit]
    churn_list = sorted([item for item in rows if item["churned"]], key=lambda item: (-item["inactive_days"], item["user_id"]))[:top_limit]
    top_symbols = [
        {"symbol": symbol_key, "revenue_usd": round(amount, 8)}
        for symbol_key, amount in sorted(top_symbols_map.items(), key=lambda kv: (-kv[1], kv[0]))[:top_limit]
    ]

    cohort_map: dict[str, dict] = {}
    for item in rows:
        key = item["cohort_month"] or "unknown"
        bucket = cohort_map.setdefault(
            key,
            {
                "cohort_month": key,
                "users": 0,
                "paying_users": 0,
                "churned_users": 0,
                "total_revenue_usd": 0.0,
                "avg_ltv_usd": 0.0,
            },
        )
        bucket["users"] += 1
        if item["revenue_contribution_usd"] > 0:
            bucket["paying_users"] += 1
        if item["churned"]:
            bucket["churned_users"] += 1
        bucket["total_revenue_usd"] += item["revenue_contribution_usd"]
        bucket["avg_ltv_usd"] += item["ltv_usd"]

    cohorts = []
    for value in sorted(cohort_map.values(), key=lambda item: item["cohort_month"]):
        users_count = max(1, value["users"])
        cohorts.append(
            {
                "cohort_month": value["cohort_month"],
                "users": value["users"],
                "paying_users": value["paying_users"],
                "churned_users": value["churned_users"],
                "total_revenue_usd": round(value["total_revenue_usd"], 8),
                "avg_ltv_usd": round(value["avg_ltv_usd"] / users_count, 8),
            }
        )

    return {
        "status": "ok",
        "environment": environment,
        "filters": {
            "start_date": start_date,
            "end_date": end_date,
            "user_email": user_email,
            "symbol": symbol,
            "churn_inactive_days": churn_inactive_days,
            "cohort_month": cohort_month,
            "top_limit": top_limit,
        },
        "sync": sync_result,
        "kpis": {
            "total_users": total_users,
            "paying_users": paying_users,
            "churned_users": churned_users,
            "churn_rate_pct": churn_rate,
            "total_revenue_usd": total_revenue,
            "arpu_usd": arpu,
            "arppu_usd": arppu,
            "avg_ltv_usd": avg_ltv,
        },
        "top_users": top_users,
        "churn_list": churn_list,
        "top_symbols": top_symbols,
        "cohorts": cohorts,
        "rows": rows,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def get_retention_trend(
    db: Session,
    *,
    environment: str,
    granularity: str,
    lookback_periods: int,
) -> dict:
    if granularity not in {"weekly", "monthly"}:
        raise ValueError("invalid_granularity")

    revenue_rows = db.query(RevenueLedger).filter(RevenueLedger.environment == environment).all()
    trade_rows = db.query(CommercialTrade).filter(CommercialTrade.environment == environment).all()
    aggregate_rows = db.query(UserEconomicsAggregate).filter(UserEconomicsAggregate.environment == environment).all()

    first_key_by_user = {
        row.user_id: _period_key(row.first_activity_at, granularity)
        for row in aggregate_rows
        if row.first_activity_at is not None
    }

    activity_keys_by_user: dict[str, set[str]] = {}
    for row in trade_rows:
        key = _period_key(row.trade_time, granularity)
        activity_keys_by_user.setdefault(row.user_id, set()).add(key)

    revenue_map: dict[tuple[str, str], float] = {}
    for row in revenue_rows:
        cohort_key = first_key_by_user.get(row.user_id)
        if cohort_key is None:
            continue
        period_key = _period_key(row.trade_time, granularity)
        revenue_map[(cohort_key, period_key)] = revenue_map.get((cohort_key, period_key), 0.0) + float(row.revenue_amount_usd or 0)

    pnl_map: dict[tuple[str, str], float] = {}
    for row in trade_rows:
        cohort_key = first_key_by_user.get(row.user_id)
        if cohort_key is None:
            continue
        period_key = _period_key(row.trade_time, granularity)
        pnl_map[(cohort_key, period_key)] = pnl_map.get((cohort_key, period_key), 0.0) + float(row.realized_pnl_usd or 0)

    cohorts = sorted(set(first_key_by_user.values()))
    recent_cohorts = cohorts[-lookback_periods:]
    cohort_users: dict[str, list[str]] = {}
    for user_id, cohort_key in first_key_by_user.items():
        if cohort_key not in recent_cohorts:
            continue
        cohort_users.setdefault(cohort_key, []).append(user_id)

    points = []
    for cohort_key in sorted(cohort_users.keys()):
        users = sorted(cohort_users[cohort_key])
        cohort_size = len(users)
        all_periods = sorted({key for user_id in users for key in activity_keys_by_user.get(user_id, set())})
        for period_key in all_periods:
            active_users = sum(1 for user_id in users if period_key in activity_keys_by_user.get(user_id, set()))
            retention_rate = round((active_users / cohort_size) * 100.0, 6) if cohort_size else 0.0
            points.append(
                {
                    "cohort": cohort_key,
                    "period": period_key,
                    "cohort_size": cohort_size,
                    "active_users": active_users,
                    "retention_rate_pct": retention_rate,
                    "cohort_revenue_usd": round(revenue_map.get((cohort_key, period_key), 0.0), 8),
                    "cohort_realized_pnl_usd": round(pnl_map.get((cohort_key, period_key), 0.0), 8),
                }
            )

    return {
        "status": "ok",
        "environment": environment,
        "granularity": granularity,
        "lookback_periods": lookback_periods,
        "points": points,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def get_segment_profitability(
    db: Session,
    *,
    environment: str,
    churn_inactive_days: int,
    top_limit: int,
) -> dict:
    summary = get_user_economics_summary(
        db,
        environment=environment,
        start_date=None,
        end_date=None,
        user_email=None,
        symbol=None,
        churn_inactive_days=churn_inactive_days,
        cohort_month=None,
        top_limit=max(top_limit, 100),
    )
    rows = summary["rows"]
    sorted_revenue = sorted([row["revenue_contribution_usd"] for row in rows], reverse=True)
    high_idx = max(0, int(len(sorted_revenue) * 0.2) - 1)
    high_cutoff = sorted_revenue[high_idx] if sorted_revenue else 0.0

    buckets: dict[str, list[dict]] = {
        "high_value": [],
        "profitable_but_inactive": [],
        "churn_risk": [],
        "low_activity_low_revenue": [],
        "loss_heavy_users": [],
    }

    for row in rows:
        segment = _classify_segment(
            revenue_usd=float(row["revenue_contribution_usd"]),
            realized_pnl_usd=float(row["realized_pnl_usd"]),
            inactive_days=int(row["inactive_days"]),
            high_value_cutoff=float(high_cutoff),
            churn_days=churn_inactive_days,
        )
        row_copy = {**row, "segment": segment}
        buckets.setdefault(segment, []).append(row_copy)

    segment_cards = []
    for name in ["high_value", "profitable_but_inactive", "churn_risk", "low_activity_low_revenue", "loss_heavy_users"]:
        items = buckets.get(name, [])
        segment_cards.append(
            {
                "segment": name,
                "users": len(items),
                "total_revenue_usd": round(sum(float(item["revenue_contribution_usd"]) for item in items), 8),
                "total_realized_pnl_usd": round(sum(float(item["realized_pnl_usd"]) for item in items), 8),
            }
        )

    churn_risk_list = sorted(buckets.get("churn_risk", []), key=lambda item: (-item["inactive_days"], item["user_id"]))[:top_limit]
    reengagement_list = sorted(
        buckets.get("profitable_but_inactive", []) + buckets.get("churn_risk", []),
        key=lambda item: (-item["inactive_days"], -item["revenue_contribution_usd"], item["user_id"]),
    )[:top_limit]

    return {
        "status": "ok",
        "environment": environment,
        "churn_inactive_days": churn_inactive_days,
        "segment_cards": segment_cards,
        "churn_risk_list": churn_risk_list,
        "reengagement_list": reengagement_list,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def export_user_economics(
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
) -> tuple[bytes, str, str]:
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
    rows = summary["rows"]

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

    if output == "csv":
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in columns})
        payload = stream.getvalue().encode("utf-8")
        return payload, "text/csv", "user_economics_export.csv"

    if output == "xlsx":
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "user_economics"
        sheet.append(columns)
        for row in rows:
            sheet.append([row.get(key) for key in columns])
        bytes_io = io.BytesIO()
        workbook.save(bytes_io)
        return (
            bytes_io.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "user_economics_export.xlsx",
        )

    raise ValueError("invalid_export_format")


def run_user_economics_snapshot(
    db: Session,
    *,
    environment: str,
    snapshot_type: str,
    as_of_date: str | None,
    churn_inactive_days: int,
) -> dict:
    if snapshot_type not in {"daily", "weekly"}:
        raise ValueError("invalid_snapshot_type")

    summary = get_user_economics_summary(
        db,
        environment=environment,
        start_date=None,
        end_date=None,
        user_email=None,
        symbol=None,
        churn_inactive_days=churn_inactive_days,
        cohort_month=None,
        top_limit=100,
    )
    sorted_revenue = sorted([row["revenue_contribution_usd"] for row in summary["rows"]], reverse=True)
    high_idx = max(0, int(len(sorted_revenue) * 0.2) - 1)
    high_cutoff = sorted_revenue[high_idx] if sorted_revenue else 0.0

    raw_snapshot_dt = _parse_datetime(as_of_date) or datetime.now(timezone.utc)
    if snapshot_type == "weekly":
        snapshot_dt = (raw_snapshot_dt - timedelta(days=raw_snapshot_dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        snapshot_dt = raw_snapshot_dt.replace(hour=0, minute=0, second=0, microsecond=0)

    existing_rows = (
        db.query(UserEconomicsSnapshot)
        .filter(
            UserEconomicsSnapshot.environment == environment,
            UserEconomicsSnapshot.snapshot_type == snapshot_type,
            UserEconomicsSnapshot.snapshot_date == snapshot_dt,
        )
        .all()
    )
    existing_by_user = {row.user_id: row for row in existing_rows}

    inserted = 0
    updated = 0
    for row in summary["rows"]:
        existing = existing_by_user.get(row["user_id"])
        segment = _classify_segment(
            revenue_usd=float(row["revenue_contribution_usd"]),
            realized_pnl_usd=float(row["realized_pnl_usd"]),
            inactive_days=int(row["inactive_days"]),
            high_value_cutoff=float(high_cutoff),
            churn_days=churn_inactive_days,
        )
        payload = {
            "user_email": row["email"],
            "ltv_usd": row["ltv_usd"],
            "revenue_contribution_usd": row["revenue_contribution_usd"],
            "realized_pnl_usd": row["realized_pnl_usd"],
            "inactive_days": row["inactive_days"],
            "churned": row["churned"],
            "cohort_month": row["cohort_month"],
            "segment": segment,
            "details": {"last_activity_at": row["last_activity_at"]},
        }
        if existing is None:
            db.add(
                UserEconomicsSnapshot(
                    snapshot_type=snapshot_type,
                    snapshot_date=snapshot_dt,
                    environment=environment,
                    user_id=row["user_id"],
                    **payload,
                )
            )
            inserted += 1
            continue
        for key, value in payload.items():
            setattr(existing, key, value)
        updated += 1

    db.flush()
    db.commit()
    return {
        "status": "ok",
        "environment": environment,
        "snapshot_type": snapshot_type,
        "snapshot_date": snapshot_dt.isoformat(),
        "inserted": inserted,
        "updated": updated,
        "rows": len(summary["rows"]),
    }


def get_user_economics_snapshot_trend(
    db: Session,
    *,
    environment: str,
    snapshot_type: str,
    limit: int,
) -> dict:
    if snapshot_type not in {"daily", "weekly"}:
        raise ValueError("invalid_snapshot_type")

    rows = (
        db.query(UserEconomicsSnapshot)
        .filter(
            UserEconomicsSnapshot.environment == environment,
            UserEconomicsSnapshot.snapshot_type == snapshot_type,
        )
        .order_by(UserEconomicsSnapshot.snapshot_date.asc())
        .all()
    )

    grouped: dict[str, dict] = {}
    for row in rows:
        key = row.snapshot_date.date().isoformat()
        bucket = grouped.setdefault(
            key,
            {
                "snapshot_date": key,
                "users": 0,
                "churned_users": 0,
                "total_revenue_usd": 0.0,
                "avg_ltv_usd": 0.0,
            },
        )
        bucket["users"] += 1
        bucket["total_revenue_usd"] += float(row.revenue_contribution_usd or 0)
        bucket["avg_ltv_usd"] += float(row.ltv_usd or 0)
        if row.churned:
            bucket["churned_users"] += 1

    points = []
    for value in sorted(grouped.values(), key=lambda item: item["snapshot_date"])[-limit:]:
        users = max(1, value["users"])
        points.append(
            {
                "snapshot_date": value["snapshot_date"],
                "users": value["users"],
                "churned_users": value["churned_users"],
                "churn_rate_pct": round((value["churned_users"] / users) * 100.0, 6),
                "total_revenue_usd": round(value["total_revenue_usd"], 8),
                "avg_ltv_usd": round(value["avg_ltv_usd"] / users, 8),
            }
        )

    return {
        "status": "ok",
        "environment": environment,
        "snapshot_type": snapshot_type,
        "points": points,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
