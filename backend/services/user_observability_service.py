from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import (
    AuditLog,
    ExecutionMetric,
    LoginHistoryEvent,
    Position,
    User,
    UserBotScope,
    UserExchangeConnection,
    UserIdentityProfile,
    UserRoleBinding,
    UserStrategyScope,
)


SUCCESS_EXECUTION_STATUSES = {"FILLED", "SUCCESS", "COMPLETED"}
WINDOWS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _severity_from_score(score: float) -> str:
    if score >= 85:
        return "critical"
    if score >= 65:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _window_summary_from_timestamps(items: list[datetime]) -> dict:
    now = _now()
    payload = {}
    for key, delta in WINDOWS.items():
        since = now - delta
        payload[key] = len([item for item in items if item and item >= since])
    return payload


def get_user_activity_timeline(db: Session, *, user_id: str, limit: int = 120) -> dict:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        return {"items": [], "summary": {"24h": 0, "7d": 0, "30d": 0}}

    login_rows = (
        db.query(LoginHistoryEvent)
        .filter(LoginHistoryEvent.user_id == user_id)
        .order_by(LoginHistoryEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    audit_rows = (
        db.query(AuditLog)
        .filter((AuditLog.entity_id == user_id) | (AuditLog.actor_user_id == user_id))
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )

    items: list[dict] = []
    for row in login_rows:
        event_name = "login_success" if row.outcome == "SUCCESS" else "login_failed"
        items.append(
            {
                "timestamp": _to_iso(row.created_at),
                "event": event_name,
                "category": "login",
                "severity": "low" if row.outcome == "SUCCESS" else "high",
                "details": {
                    "ip_address": row.ip_address,
                    "device_fingerprint": row.device_fingerprint,
                    "failure_reason": row.failure_reason,
                    "attempt_count": row.attempt_count,
                },
            }
        )

    for row in audit_rows:
        action = str(row.action or "").lower()
        category = "activity"
        if "disable" in action or "enable" in action:
            category = "status"
        if "delete" in action or "restore" in action:
            category = "delete_restore"
        if "role" in action:
            category = "role_change"
        if "kill_switch" in action:
            category = "kill_switch"
        if "trading" in action:
            category = "trading"
        items.append(
            {
                "timestamp": _to_iso(row.created_at),
                "event": row.action,
                "category": category,
                "severity": str(row.severity or "info").lower(),
                "details": row.details or {},
            }
        )

    items = sorted(items, key=lambda item: item.get("timestamp") or "", reverse=True)[:limit]
    timestamps = [datetime.fromisoformat(item["timestamp"]) for item in items if item.get("timestamp")]
    return {
        "items": items,
        "summary": _window_summary_from_timestamps(timestamps),
    }


def get_user_security_telemetry(db: Session, *, user_id: str) -> dict:
    now = _now()
    since_30d = now - WINDOWS["30d"]
    failed_rows = (
        db.query(LoginHistoryEvent)
        .filter(
            LoginHistoryEvent.user_id == user_id,
            LoginHistoryEvent.created_at >= since_30d,
            LoginHistoryEvent.outcome != "SUCCESS",
        )
        .order_by(LoginHistoryEvent.created_at.desc())
        .all()
    )
    failed_timestamps = [row.created_at for row in failed_rows if row.created_at]
    failed_summary = _window_summary_from_timestamps(failed_timestamps)

    recent_24h = [row for row in failed_rows if row.created_at and row.created_at >= now - WINDOWS["24h"]]
    distinct_ips_24h = len({row.ip_address for row in recent_24h if row.ip_address})
    distinct_devices_24h = len({row.device_fingerprint for row in recent_24h if row.device_fingerprint})

    suspicious_signals = []
    if failed_summary["24h"] >= 5:
        suspicious_signals.append({"signal": "failed_login_burst", "severity": "high", "score": 80})
    if distinct_ips_24h >= 3:
        suspicious_signals.append({"signal": "ip_variance_anomaly", "severity": "medium", "score": 60})
    if distinct_devices_24h >= 3:
        suspicious_signals.append({"signal": "device_variance_anomaly", "severity": "medium", "score": 58})
    if len([row for row in recent_24h if row.lock_until is not None]) > 0:
        suspicious_signals.append({"signal": "policy_lock_events", "severity": "high", "score": 75})

    mfa_failure_rows = (
        db.query(AuditLog)
        .filter(
            AuditLog.created_at >= since_30d,
            AuditLog.severity.in_(["warning", "error", "critical"]),
            AuditLog.action.ilike("%mfa%"),
            (AuditLog.entity_id == user_id) | (AuditLog.actor_user_id == user_id),
        )
        .order_by(AuditLog.created_at.desc())
        .limit(20)
        .all()
    )

    normalized_score = min(100, (failed_summary["24h"] * 8) + (distinct_ips_24h * 6) + (distinct_devices_24h * 5))
    return {
        "failed_login_trend": failed_summary,
        "ip_device_anomaly_summary": {
            "distinct_ips_24h": distinct_ips_24h,
            "distinct_devices_24h": distinct_devices_24h,
            "suspicious": normalized_score >= 50,
        },
        "recent_mfa_failures": [
            {
                "id": row.id,
                "action": row.action,
                "severity": row.severity,
                "created_at": _to_iso(row.created_at),
                "details": row.details or {},
            }
            for row in mfa_failure_rows
        ],
        "high_risk_signals": suspicious_signals,
        "normalized_severity": _severity_from_score(float(normalized_score)),
        "normalized_risk_score": normalized_score,
    }


def get_user_execution_metrics(db: Session, *, user_id: str) -> dict:
    now = _now()
    since_30d = now - WINDOWS["30d"]
    metrics = (
        db.query(ExecutionMetric)
        .filter(ExecutionMetric.user_id == user_id, ExecutionMetric.created_at >= since_30d)
        .order_by(ExecutionMetric.created_at.desc())
        .all()
    )

    total = len(metrics)
    success_rows = [row for row in metrics if str(row.final_status or "").upper() in SUCCESS_EXECUTION_STATUSES]
    error_rows = [row for row in metrics if row.failure_code or str(row.final_status or "").upper() not in SUCCESS_EXECUTION_STATUSES]
    success_rate = round((len(success_rows) / total) * 100, 2) if total else 0.0

    latencies = [float(row.execution_time_ms) for row in metrics if row.execution_time_ms is not None]
    avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0
    p95_latency = 0.0
    if latencies:
        sorted_lat = sorted(latencies)
        idx = min(int(len(sorted_lat) * 0.95), len(sorted_lat) - 1)
        p95_latency = round(sorted_lat[idx], 2)

    error_categories = Counter([str(row.failure_code or "unknown_error") for row in error_rows])
    created_at_rows = [row.created_at for row in metrics if row.created_at]
    window_summary = _window_summary_from_timestamps(created_at_rows)

    normalized_score = max(0, min(100, int((100 - success_rate) + (len(error_rows) * 2))))
    return {
        "execution_success_rate": success_rate,
        "execution_error_count": len(error_rows),
        "recent_error_categories": [{"code": code, "count": count} for code, count in error_categories.most_common(6)],
        "execution_latency_summary": {
            "avg_ms": avg_latency,
            "p95_ms": p95_latency,
            "sample_size": len(latencies),
        },
        "window_summary": window_summary,
        "normalized_severity": _severity_from_score(float(normalized_score)),
        "normalized_risk_score": normalized_score,
    }


def get_user_trading_observability(db: Session, *, user_id: str) -> dict:
    now = _now()
    profile = db.query(UserIdentityProfile).filter(UserIdentityProfile.user_id == user_id).first()
    trade_rows = (
        db.query(ExecutionMetric)
        .filter(ExecutionMetric.user_id == user_id, ExecutionMetric.created_at >= now - WINDOWS["30d"])
        .order_by(ExecutionMetric.created_at.desc())
        .all()
    )
    trade_timestamps = [row.created_at for row in trade_rows if row.created_at]

    strategy_scope_count = db.query(func.count(UserStrategyScope.id)).filter(UserStrategyScope.user_id == user_id).scalar() or 0
    bot_scope_count = db.query(func.count(UserBotScope.id)).filter(UserBotScope.user_id == user_id).scalar() or 0
    account_mapping_count = db.query(func.count(UserExchangeConnection.id)).filter(UserExchangeConnection.user_id == user_id).scalar() or 0
    open_positions = (
        db.query(func.count(Position.position_id))
        .filter(Position.user_id == user_id, Position.status.in_(["open", "OPEN", "running", "RUNNING"]))
        .scalar()
        or 0
    )

    window_summary = _window_summary_from_timestamps(trade_timestamps)
    return {
        "trade_history_link": f"/admin/trading/history?user_id={user_id}",
        "recent_trade_count": window_summary,
        "live_trading_status": {
            "trading_enabled": bool(profile.trading_enabled) if profile else False,
            "live_trading_eligible": bool(profile.live_trading_eligible) if profile else False,
            "kill_switch_active": bool(profile.kill_switch_active) if profile else False,
        },
        "impact_summary": {
            "strategy_scope_count": int(strategy_scope_count),
            "bot_scope_count": int(bot_scope_count),
            "account_mapping_count": int(account_mapping_count),
            "open_positions": int(open_positions),
            "role_binding_present": bool(db.query(UserRoleBinding).filter(UserRoleBinding.user_id == user_id).first()),
        },
    }
