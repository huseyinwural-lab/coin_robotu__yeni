from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
import os

from sqlalchemy.orm import Session

from models import AuditLog
from services.readiness_history_service import READINESS_ACTIONS


DEFAULT_POLICY = {
    "details_retention_days": 30,
    "aggregate_retention_days": 90,
    "cleanup_batch_size": 1000,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_readiness_retention_policy() -> dict:
    policy = dict(DEFAULT_POLICY)
    raw = os.environ.get("READINESS_HISTORY_RETENTION_JSON")
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                for key in policy.keys():
                    if parsed.get(key) is not None:
                        policy[key] = int(parsed.get(key))
        except Exception:
            pass
    policy["details_retention_days"] = max(int(policy.get("details_retention_days") or 30), 1)
    policy["aggregate_retention_days"] = max(int(policy.get("aggregate_retention_days") or 90), policy["details_retention_days"])
    policy["cleanup_batch_size"] = max(int(policy.get("cleanup_batch_size") or 1000), 100)
    return policy


def _build_daily_summary(rows: list[AuditLog]) -> dict:
    state_counter: Counter[str] = Counter()
    reason_counter: Counter[str] = Counter()
    blocker_counter: Counter[str] = Counter()
    layer_counter: dict[str, Counter[str]] = defaultdict(Counter)

    for row in rows:
        details = dict(row.details or {})
        state = str(details.get("readiness_state") or "UNKNOWN").upper()
        state_counter[state] += 1
        reason_codes = [str(code) for code in (details.get("reason_codes") or []) if str(code).strip()]
        reason_counter.update(reason_codes)
        for blocker in details.get("blocking_failures") or []:
            code = str((blocker or {}).get("reason_code") or "UNKNOWN_BLOCKER")
            layer = str((blocker or {}).get("layer") or "unknown")
            blocker_counter[code] += 1
            layer_counter[layer]["failed"] += 1
        for layer in (details.get("scores") or {}).keys():
            layer_counter[str(layer)]["total"] += 1

    layer_failure_rate = {}
    for layer, bucket in layer_counter.items():
        failed = int(bucket.get("failed") or 0)
        total = int(bucket.get("total") or 0)
        layer_failure_rate[layer] = {
            "failed": failed,
            "total": total,
            "rate": round(failed / max(total, 1), 6),
        }

    return {
        "count": len(rows),
        "states": dict(state_counter),
        "top_reason_codes": [{"reason_code": code, "count": count} for code, count in reason_counter.most_common(10)],
        "top_blockers": [{"reason_code": code, "count": count} for code, count in blocker_counter.most_common(10)],
        "layer_failure_rate": layer_failure_rate,
    }


def _upsert_daily_summary(db: Session, *, day_key: str, summary: dict, dry_run: bool) -> None:
    if dry_run:
        return
    existing = (
        db.query(AuditLog)
        .filter(AuditLog.action == "READINESS_DAILY_SUMMARY")
        .filter(AuditLog.entity_id == day_key)
        .first()
    )
    payload = {
        "day": day_key,
        "summary": summary,
        "generated_at": _utcnow().isoformat(),
    }
    if existing:
        existing.details = payload
        existing.severity = "info"
        existing.created_at = _utcnow()
    else:
        db.add(
            AuditLog(
                action="READINESS_DAILY_SUMMARY",
                entity_type="readiness_history",
                entity_id=day_key,
                actor_role="system",
                severity="info",
                details=payload,
            )
        )


def run_readiness_history_maintenance(db: Session, *, dry_run: bool = False) -> dict:
    policy = get_readiness_retention_policy()
    now = _utcnow()
    detail_cutoff = now - timedelta(days=int(policy["details_retention_days"]))
    aggregate_cutoff = now - timedelta(days=int(policy["aggregate_retention_days"]))

    candidate_rows = (
        db.query(AuditLog)
        .filter(AuditLog.action.in_(tuple(READINESS_ACTIONS)))
        .filter(AuditLog.created_at < detail_cutoff)
        .order_by(AuditLog.created_at.asc())
        .limit(int(policy["cleanup_batch_size"]))
        .all()
    )

    grouped: dict[str, list[AuditLog]] = defaultdict(list)
    for row in candidate_rows:
        day_key = row.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d") if row.created_at else now.strftime("%Y-%m-%d")
        grouped[day_key].append(row)

    for day_key, rows in grouped.items():
        summary = _build_daily_summary(rows)
        _upsert_daily_summary(db, day_key=day_key, summary=summary, dry_run=dry_run)

    deleted_detail = len(candidate_rows)
    if not dry_run and candidate_rows:
        ids = [row.id for row in candidate_rows]
        db.query(AuditLog).filter(AuditLog.id.in_(ids)).delete(synchronize_session=False)

    summary_rows_to_delete = (
        db.query(AuditLog)
        .filter(AuditLog.action == "READINESS_DAILY_SUMMARY")
        .filter(AuditLog.created_at < aggregate_cutoff)
        .limit(int(policy["cleanup_batch_size"]))
        .all()
    )
    deleted_aggregate = len(summary_rows_to_delete)
    if not dry_run and summary_rows_to_delete:
        ids = [row.id for row in summary_rows_to_delete]
        db.query(AuditLog).filter(AuditLog.id.in_(ids)).delete(synchronize_session=False)

    if not dry_run:
        db.commit()

    return {
        "policy": policy,
        "dry_run": bool(dry_run),
        "detail_cutoff": detail_cutoff.isoformat(),
        "aggregate_cutoff": aggregate_cutoff.isoformat(),
        "deleted_detail_rows": deleted_detail,
        "deleted_aggregate_rows": deleted_aggregate,
        "daily_summary_rows_upserted": len(grouped),
        "maintenance_generated_at": now.isoformat(),
    }
