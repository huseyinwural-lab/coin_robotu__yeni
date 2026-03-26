#!/usr/bin/env python3

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.append("/app/backend")

from core.alerts.runtime_alert_triggers import trigger_runtime_threshold_alert  # noqa: E402
from core.runtime_alert_thresholds import get_runtime_alert_thresholds  # noqa: E402
from db import SessionLocal  # noqa: E402
from models import RuntimeSmokeRun  # noqa: E402
from services.runtime_smoke_service import record_runtime_smoke_run  # noqa: E402


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"missing_env:{name}")
    return value


def _run_step(name: str, fn):
    started = time.time()
    try:
        payload = fn()
        if payload.get("status") in {"SKIPPED_CREDENTIAL_MISSING", "FAIL"}:
            return payload
        return {
            "status": "PASS",
            "detail": payload,
            "latency_ms": int((time.time() - started) * 1000),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "FAIL",
            "detail": {"error": str(exc)[:500], "step": name},
            "latency_ms": int((time.time() - started) * 1000),
        }


def main() -> int:
    started_at = datetime.now(timezone.utc)
    base_url = _required_env("REACT_APP_BACKEND_URL").rstrip("/")
    admin_email = _required_env("DAILY_SMOKE_ADMIN_EMAIL")
    admin_password = _required_env("DAILY_SMOKE_ADMIN_PASSWORD")
    target_user_email = os.environ.get("DAILY_SMOKE_TARGET_USER_EMAIL")

    login = requests.post(
        f"{base_url}/api/auth/login",
        json={"email": admin_email, "password": admin_password},
        timeout=25,
    )
    login.raise_for_status()
    token = login.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    def ingest_step():
        if not target_user_email:
            return {
                "status": "SKIPPED_CREDENTIAL_MISSING",
                "detail": {"reason": "DAILY_SMOKE_TARGET_USER_EMAIL missing"},
            }
        resp = requests.post(
            f"{base_url}/api/admin/commercial/p0/ingestion/rest-run",
            json={
                "target_user_email": target_user_email,
                "exchange": "binance",
                "environment": "live",
                "market_types": ["spot", "futures"],
                "limit_per_market": 100,
            },
            headers=headers,
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()

    def pnl_step():
        resp = requests.get(
            f"{base_url}/api/admin/commercial/p0/pnl/latest",
            params={"environment": "live", "lookback_hours": 24},
            headers=headers,
            timeout=45,
        )
        resp.raise_for_status()
        return resp.json()

    def reconciliation_step():
        resp = requests.post(
            f"{base_url}/api/admin/commercial/p0/reconciliation/run",
            params={"environment": "live", "lookback_hours": 24},
            headers=headers,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()

    def revenue_step():
        resp = requests.get(
            f"{base_url}/api/admin/revenue/summary",
            params={"environment": "live", "top_limit": 10},
            headers=headers,
            timeout=45,
        )
        resp.raise_for_status()
        return resp.json()

    def snapshot_compare_step():
        now = datetime.now(timezone.utc)
        prev = now - timedelta(days=1)
        for as_of in [now, prev]:
            run_resp = requests.post(
                f"{base_url}/api/admin/snapshots/run",
                params={
                    "environment": "live",
                    "snapshot_type": "daily",
                    "as_of_date": as_of.isoformat(),
                    "top_limit": 20,
                },
                headers=headers,
                timeout=60,
            )
            run_resp.raise_for_status()

        listing = requests.get(
            f"{base_url}/api/admin/snapshots",
            params={"environment": "live", "snapshot_type": "daily", "limit": 5},
            headers=headers,
            timeout=45,
        )
        listing.raise_for_status()
        items = listing.json().get("items", [])
        if len(items) < 2:
            raise RuntimeError("snapshot_compare_insufficient_data")

        cmp_resp = requests.get(
            f"{base_url}/api/admin/snapshots/compare",
            params={"base_snapshot_id": items[1]["id"], "target_snapshot_id": items[0]["id"]},
            headers=headers,
            timeout=45,
        )
        cmp_resp.raise_for_status()
        return cmp_resp.json()

    steps = {
        "ingest": _run_step("ingest", ingest_step),
        "pnl": _run_step("pnl", pnl_step),
        "reconciliation": _run_step("reconciliation", reconciliation_step),
        "revenue": _run_step("revenue", revenue_step),
        "snapshot_compare": _run_step("snapshot_compare", snapshot_compare_step),
    }

    if steps["ingest"].get("status") == "SKIPPED_CREDENTIAL_MISSING":
        for dependent_step in ["pnl", "reconciliation", "revenue", "snapshot_compare"]:
            if steps[dependent_step].get("status") == "FAIL":
                steps[dependent_step] = {
                    "status": "SKIPPED_CREDENTIAL_MISSING",
                    "detail": {
                        "reason": "upstream_ingest_skipped_credential_missing",
                        "upstream_step": "ingest",
                    },
                }

    has_fail = any(step.get("status") == "FAIL" for step in steps.values())
    has_skipped = any(step.get("status") == "SKIPPED_CREDENTIAL_MISSING" for step in steps.values())
    overall = "FAIL" if has_fail else "DEGRADED" if has_skipped else "PASS"

    summary = f"daily_smoke:{overall}"
    report = {
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall,
        "steps": steps,
    }

    artifacts_dir = Path("/app/artifacts")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    report_path = artifacts_dir / f"daily_smoke_{started_at.strftime('%Y%m%d_%H%M%S')}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    db = SessionLocal()
    try:
        thresholds = get_runtime_alert_thresholds()
        record_runtime_smoke_run(
            db,
            status=overall,
            summary=summary,
            steps=steps,
            trigger_source="script",
            report_path=str(report_path),
            started_at=started_at,
        )

        if overall != "PASS":
            degraded_repeats = (
                db.query(RuntimeSmokeRun)
                .filter(RuntimeSmokeRun.status == "DEGRADED")
                .count()
            )
            repeat_threshold = int(thresholds.get("smoke_degraded_repeat_threshold") or 2)
            severity = "CRITICAL" if overall == "FAIL" or degraded_repeats >= repeat_threshold else "WARNING"
            trigger_runtime_threshold_alert(
                db,
                alert_type="runtime_daily_smoke_degraded",
                severity=severity,
                message=f"Daily smoke {overall}",
                source="daily_smoke",
                threshold=repeat_threshold,
                actual_value=degraded_repeats,
                root_cause_code="daily_smoke_not_pass",
            )
    finally:
        db.close()

    print(json.dumps(report, ensure_ascii=False))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
