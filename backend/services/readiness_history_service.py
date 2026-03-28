from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models import AuditLog

READINESS_ACTIONS = {
    "FUTURES_LIVE_READINESS_VIEWED",
    "SYSTEM_LIVE_READINESS_VIEWED",
    "FUTURES_LIVE_READINESS_SCORE_VIEWED",
    "FUTURES_READINESS_SCORE_VIEWED",
    "SYSTEM_READINESS_SCORE_VIEWED",
    "FUTURES_EXECUTION_READINESS_VIEWED",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def build_readiness_audit_details(payload: dict) -> dict:
    payload = payload or {}
    return {
        "readiness_state": payload.get("readiness_state"),
        "readiness_score": payload.get("readiness_score", payload.get("score", 0.0)),
        "reason_codes": payload.get("reason_codes") or [],
        "blocking_failures": payload.get("blocking_failures") or [],
        "warnings": payload.get("warnings") or [],
        "unknowns": payload.get("unknowns") or [],
        "scores": payload.get("scores") or {},
        "summary": payload.get("summary") or {},
        "exchange_readiness": payload.get("exchange_readiness") or {},
        "symbol_readiness": payload.get("symbol_readiness") or {},
        "strategy_readiness": payload.get("strategy_readiness") or {},
        "readiness_matrix": payload.get("readiness_matrix") or {},
        "generated_at": payload.get("generated_at"),
    }


def get_readiness_history(
    db: Session,
    *,
    limit: int = 50,
    days: int = 14,
) -> dict:
    now = _utcnow()
    since = now - timedelta(days=max(int(days or 1), 1))

    query = (
        db.query(AuditLog)
        .filter(AuditLog.action.in_(tuple(READINESS_ACTIONS)))
        .filter(AuditLog.created_at >= since)
        .order_by(AuditLog.created_at.desc())
        .limit(max(limit * 10, 200))
    )
    rows = query.all()

    reason_counter: Counter[str] = Counter()
    blocker_counter: Counter[str] = Counter()
    day_state_counter: dict[str, Counter[str]] = defaultdict(Counter)
    layer_fail_counter: Counter[str] = Counter()
    layer_total_counter: Counter[str] = Counter()

    items: list[dict] = []
    state_counter: Counter[str] = Counter()

    for row in rows:
        details = dict(row.details or {})
        state = str(details.get("readiness_state") or "UNKNOWN").upper()
        score = float(details.get("readiness_score") or 0.0)
        reason_codes = [str(code) for code in (details.get("reason_codes") or []) if str(code).strip()]
        blocking_failures = details.get("blocking_failures") or []
        scores = details.get("scores") or {}

        state_counter[state] += 1
        day_key = row.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d") if row.created_at else now.strftime("%Y-%m-%d")
        day_state_counter[day_key][state] += 1

        reason_counter.update(reason_codes)
        for item in blocking_failures:
            code = str((item or {}).get("reason_code") or "UNKNOWN_BLOCKER")
            blocker_counter[code] += 1
            layer = str((item or {}).get("layer") or "unknown")
            layer_fail_counter[layer] += 1

        for layer, value in scores.items():
            layer_total_counter[str(layer)] += 1
            try:
                if float(value) < 100:
                    layer_fail_counter[str(layer)] += 1
            except Exception:
                layer_fail_counter[str(layer)] += 1

        items.append(
            {
                "audit_id": row.id,
                "timestamp": row.created_at.isoformat() if row.created_at else None,
                "action": row.action,
                "severity": row.severity,
                "readiness_state": state,
                "readiness_score": round(score, 4),
                "reason_codes": reason_codes,
                "blocking_failures": blocking_failures,
                "summary": details.get("summary") or {},
                "scores": scores,
                "top_reason_codes": [code for code, _ in Counter(reason_codes).most_common(3)],
            }
        )

    items = items[: max(limit, 1)]

    failure_frequency = {
        "total": len(items),
        "ready": state_counter.get("READY", 0),
        "blocked": state_counter.get("BLOCKED", 0),
        "warning": state_counter.get("WARNING", 0),
        "unknown": state_counter.get("UNKNOWN", 0),
        "failure_rate": round(
            (state_counter.get("BLOCKED", 0) + state_counter.get("UNKNOWN", 0)) / max(sum(state_counter.values()), 1),
            6,
        ),
    }

    failure_trend = []
    for day_key in sorted(day_state_counter.keys()):
        bucket = day_state_counter[day_key]
        failure_trend.append(
            {
                "date": day_key,
                "ready": bucket.get("READY", 0),
                "blocked": bucket.get("BLOCKED", 0),
                "warning": bucket.get("WARNING", 0),
                "unknown": bucket.get("UNKNOWN", 0),
            }
        )

    layer_failure_rate = {}
    all_layers = sorted(set(layer_total_counter.keys()) | set(layer_fail_counter.keys()))
    for layer in all_layers:
        total = layer_total_counter.get(layer, 0)
        failed = layer_fail_counter.get(layer, 0)
        layer_failure_rate[layer] = {
            "failed": failed,
            "total": total,
            "rate": round(failed / max(total, 1), 6),
        }

    top_reason_codes = [{"reason_code": code, "count": count} for code, count in reason_counter.most_common(10)]
    top_blockers = [{"reason_code": code, "count": count} for code, count in blocker_counter.most_common(10)]

    return {
        "items": items,
        "last_n_summary": {
            "count": len(items),
            "states": dict(state_counter),
        },
        "top_reason_codes": top_reason_codes,
        "top_blockers": top_blockers,
        "failure_frequency": failure_frequency,
        "failure_trend": failure_trend,
        "layer_failure_rate": layer_failure_rate,
    }
