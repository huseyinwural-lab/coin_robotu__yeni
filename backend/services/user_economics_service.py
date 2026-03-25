from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import CommercialTrade, RevenueLedger, User, UserEconomicsAggregate


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
    return {
        "status": "ok",
        "environment": environment,
        "rows": len(grouped),
        "inserted": inserted,
        "updated": updated,
    }


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

    aggregate_rows = aggregate_query.all()
    if cohort_month:
        aggregate_rows = [row for row in aggregate_rows if row.cohort_month == cohort_month]

    revenue_rows = revenue_query.all()
    trade_rows = trade_query.all()

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
        rows.append(
            {
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
