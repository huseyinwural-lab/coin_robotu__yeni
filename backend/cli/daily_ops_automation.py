from __future__ import annotations
# ruff: noqa: E402

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from db import SessionLocal
from models import UserDecisionTrace
from services.slo_analytics_service import compute_slo_metrics, load_alert_rows_for_window
from services.strategy_observability_service import prune_strategy_observability_events
from services.system_alert_service import create_system_alert
from services.audit_service import create_audit_log
from services.audit_retention_service import prune_audit_logs_with_policy
from services.readiness_history_maintenance_service import run_readiness_history_maintenance


def _load_release_gate_payload(path: Path) -> dict:
    if not path.exists():
        return {"overall": "MISSING", "fail_count": None, "warn_count": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"overall": "INVALID_JSON", "fail_count": None, "warn_count": None}


def _disk_snapshot(path: str = "/app") -> dict:
    usage = shutil.disk_usage(path)
    total = int(usage.total)
    used = int(usage.used)
    free = int(usage.free)
    usage_pct = (used / total) * 100 if total > 0 else 0.0
    return {
        "path": path,
        "total_gb": round(total / (1024**3), 2),
        "used_gb": round(used / (1024**3), 2),
        "free_gb": round(free / (1024**3), 2),
        "usage_pct": round(usage_pct, 2),
    }


def _prune_old_audit_logs(db, *, days: int, dry_run: bool) -> dict:
    days = min(max(int(days), 1), 365)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    try:
        result = prune_audit_logs_with_policy(db, cutoff=cutoff, dry_run=dry_run)
    except SQLAlchemyError as exc:
        db.rollback()
        return {
            "retention_days": days,
            "deleted_count": 0,
            "dry_run": bool(dry_run),
            "status": "SKIPPED",
            "reason": str(exc)[:220],
        }

    return {
        "retention_days": days,
        "deleted_count": int(result.get("deleted_count") or 0),
        "protected_count": int(result.get("protected_count") or 0),
        "retention_policy_applied": bool(result.get("retention_policy_applied")),
        "preserved_categories": result.get("preserved_categories") or [],
        "dry_run": bool(dry_run),
    }


def _prune_old_decision_traces(db, *, days: int, dry_run: bool) -> dict:
    days = min(max(int(days), 1), 365)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    try:
        to_delete_ids = [
            row[0]
            for row in db.query(UserDecisionTrace.id)
            .filter(UserDecisionTrace.created_at < cutoff)
            .order_by(UserDecisionTrace.created_at.asc())
            .all()
        ]
    except SQLAlchemyError as exc:
        db.rollback()
        return {
            "retention_days": days,
            "deleted_count": 0,
            "dry_run": bool(dry_run),
            "status": "SKIPPED",
            "reason": str(exc)[:220],
        }
    delete_count = len(to_delete_ids)
    if not dry_run and to_delete_ids:
        db.query(UserDecisionTrace).filter(UserDecisionTrace.id.in_(to_delete_ids)).delete(synchronize_session=False)
        db.commit()
    return {
        "retention_days": days,
        "deleted_count": int(delete_count),
        "dry_run": bool(dry_run),
    }


def run(*, gate_file: str, dry_run: bool) -> dict:
    report_path = Path(gate_file)
    gate = _load_release_gate_payload(report_path)

    db = SessionLocal()
    try:
        actions: list[dict] = []
        storage_before = _disk_snapshot("/app")
        storage_pressure = float(storage_before.get("usage_pct") or 0.0) >= 85.0

        strategy_retention_days = 2 if storage_pressure else 3
        strategy_max_rows = 120000 if storage_pressure else 300000
        audit_retention_days = 7 if storage_pressure else 30
        trace_retention_days = 14 if storage_pressure else 30

        try:
            strategy_prune = prune_strategy_observability_events(
                db,
                retention_days=strategy_retention_days,
                max_rows=strategy_max_rows,
                dry_run=dry_run,
            )
            strategy_status = str(strategy_prune.get("status") or ("DRY_RUN" if dry_run else "DONE"))
        except Exception as exc:  # pragma: no cover - runtime defensive guard
            db.rollback()
            strategy_prune = {
                "retention_days": strategy_retention_days,
                "max_rows": strategy_max_rows,
                "status": "SKIPPED",
                "reason": str(exc)[:220],
            }
            strategy_status = "SKIPPED"
        actions.append({
            "type": "strategy_observability_prune",
            "status": strategy_status,
            "summary": strategy_prune,
        })

        audit_prune = _prune_old_audit_logs(
            db,
            days=audit_retention_days,
            dry_run=dry_run,
        )
        actions.append({
            "type": "audit_logs_prune",
            "status": "DRY_RUN" if dry_run else "DONE",
            "summary": audit_prune,
        })

        trace_prune = _prune_old_decision_traces(
            db,
            days=trace_retention_days,
            dry_run=dry_run,
        )
        actions.append({
            "type": "decision_trace_prune",
            "status": "DRY_RUN" if dry_run else "DONE",
            "summary": trace_prune,
        })

        readiness_maintenance = run_readiness_history_maintenance(db, dry_run=dry_run)
        actions.append(
            {
                "type": "readiness_history_maintenance",
                "status": "DRY_RUN" if dry_run else "DONE",
                "summary": readiness_maintenance,
            }
        )

        if str(gate.get("overall") or "").upper() == "FAIL":
            payload = {
                "alert_type": "release_gate_failure",
                "severity": "CRITICAL",
                "message": "Daily automation detected release gate failure",
                "details": {
                    "source": "daily_ops_automation",
                    "gate_file": str(report_path),
                    "gate_overall": gate.get("overall"),
                    "fail_count": gate.get("fail_count"),
                    "warn_count": gate.get("warn_count"),
                },
                "entity_key": "release_gate",
                "root_cause_code": "release_gate_failed",
                "state_key": f"gate:{gate.get('generated_at') or datetime.now(timezone.utc).isoformat()}",
                "dedupe_window_seconds": 0,
            }
            if not dry_run:
                try:
                    alert = create_system_alert(db, **payload)
                    actions.append({"type": "release_gate_incident", "status": "CREATED", "alert_id": alert.id})
                except Exception as exc:  # pragma: no cover - runtime defensive guard
                    actions.append({"type": "release_gate_incident", "status": "SKIPPED", "reason": str(exc)[:300]})
            else:
                actions.append({"type": "release_gate_incident", "status": "DRY_RUN", "payload": payload})

        try:
            slo_rows = load_alert_rows_for_window(db, days=30)
            slo_metrics = compute_slo_metrics(slo_rows)
        except Exception as exc:  # pragma: no cover - runtime defensive guard
            slo_metrics = {
                "availability_pct": 0.0,
                "sla_target_pct": 99.5,
                "sla_breached": False,
                "error_budget_consumed_pct": 0.0,
                "error": str(exc),
            }
            actions.append({"type": "slo_metrics", "status": "SKIPPED", "reason": "system_alerts_table_missing"})
        if bool(slo_metrics.get("sla_breached")):
            if not dry_run:
                create_audit_log(
                    db,
                    action="SLO_BREACH_DETECTED",
                    entity_type="slo_monitoring",
                    entity_id="window_30d",
                    actor_role="system",
                    severity="warning",
                    details={
                        "source": "daily_ops_automation",
                        "window_days": 30,
                        "availability_pct": slo_metrics.get("availability_pct"),
                        "sla_target_pct": slo_metrics.get("sla_target_pct"),
                        "error_budget_consumed_pct": slo_metrics.get("error_budget_consumed_pct"),
                    },
                )
                actions.append({"type": "slo_breach_log", "status": "LOGGED"})
            else:
                actions.append({"type": "slo_breach_log", "status": "DRY_RUN", "metrics": slo_metrics})
        else:
            actions.append({"type": "slo_breach_log", "status": "SKIPPED_NO_BREACH"})

        output = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "gate_file": str(report_path),
            "gate_overall": gate.get("overall"),
            "storage": {
                "before": storage_before,
                "after": _disk_snapshot("/app"),
                "pressure_threshold_pct": 85.0,
                "pressure_mode": storage_pressure,
            },
            "slo_30d": {
                "availability_pct": slo_metrics.get("availability_pct"),
                "sla_target_pct": slo_metrics.get("sla_target_pct"),
                "sla_breached": slo_metrics.get("sla_breached"),
                "error_budget_consumed_pct": slo_metrics.get("error_budget_consumed_pct"),
            },
            "dry_run": dry_run,
            "actions": actions,
        }
        return output
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily ops automation runner")
    parser.add_argument("--gate-file", default="/app/test_reports/release_gate_latest.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    output = run(gate_file=args.gate_file, dry_run=bool(args.dry_run))
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
