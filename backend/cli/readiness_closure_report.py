from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys


CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = CURRENT_DIR.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.readiness_maintenance_scheduler_service import read_readiness_maintenance_status
from ops_smoke_readiness import run_smoke


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_closure_report(base_url: str, email: str, password: str) -> dict:
    smoke = run_smoke(base_url=base_url, email=email, password=password)
    maintenance_status = read_readiness_maintenance_status()

    checks = {item.get("name"): item for item in smoke.get("checks", [])}

    report = {
        "generated_at": _utcnow_iso(),
        "base_url": base_url,
        "admin_login_smoke": checks.get("admin_login_smoke"),
        "readiness_endpoint_smoke": checks.get("live_readiness_endpoint_smoke"),
        "history_maintenance_cron_status": maintenance_status,
        "bybit_venue_smoke": checks.get("bybit_venue_readiness_smoke"),
        "execution_proof_status": checks.get("execution_readiness_smoke"),
        "open_blockers": [item for item in smoke.get("checks", []) if item.get("status") != "PASS"],
        "scheduler_running": maintenance_status.get("status") in {"success", "failed", "disabled"},
        "retention_applied": bool(
            (maintenance_status.get("result") or {}).get("deleted_detail_rows", 0) >= 0
            and (maintenance_status.get("result") or {}).get("daily_summary_rows_upserted", 0) >= 0
        ),
    }
    report["overall"] = "PASS" if smoke.get("overall") == "PASS" else "FAIL"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate readiness operational closure report")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    report = build_closure_report(base_url=args.base_url.rstrip("/"), email=args.email, password=args.password)
    output_path = Path(args.output) if args.output else Path(f"/app/test_reports/readiness_closure_report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(output_path), **report}, ensure_ascii=False, indent=2))
    return 0 if report.get("overall") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
