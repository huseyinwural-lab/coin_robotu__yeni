from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from db import SessionLocal
from services.slo_analytics_service import compute_slo_metrics, load_alert_rows_for_window
from services.system_alert_service import create_system_alert
from services.audit_service import create_audit_log


def _load_release_gate_payload(path: Path) -> dict:
    if not path.exists():
        return {"overall": "MISSING", "fail_count": None, "warn_count": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"overall": "INVALID_JSON", "fail_count": None, "warn_count": None}


def run(*, gate_file: str, dry_run: bool) -> dict:
    report_path = Path(gate_file)
    gate = _load_release_gate_payload(report_path)

    db = SessionLocal()
    try:
        actions: list[dict] = []
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
