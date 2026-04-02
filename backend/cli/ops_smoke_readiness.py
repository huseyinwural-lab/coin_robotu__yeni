from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request(session: requests.Session, method: str, url: str, **kwargs):
    timeout_sec = int(kwargs.pop("timeout", 45))
    attempts = int(kwargs.pop("attempts", 2))
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            response = session.request(method, url, timeout=timeout_sec, **kwargs)
            body = response.json() if "application/json" in response.headers.get("content-type", "") else response.text
            return response.status_code, body
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            if attempt < attempts:
                time.sleep(1.2)
    return 599, {"error": last_error}


def run_smoke(base_url: str, email: str, password: str) -> dict:
    session = requests.Session()
    base_url = base_url.rstrip("/")

    checks: list[dict] = []
    passed = 0
    failed = 0

    def add_check(name: str, ok: bool, detail: dict):
        nonlocal passed, failed
        checks.append({"name": name, "status": "PASS" if ok else "FAIL", "detail": detail})
        if ok:
            passed += 1
        else:
            failed += 1

    status_code, login_payload = _request(
        session,
        "POST",
        f"{base_url}/api/auth/login/admin",
        json={"email": email, "password": password},
    )
    token = login_payload.get("access_token") if isinstance(login_payload, dict) else None
    add_check(
        "admin_login_smoke",
        status_code == 200 and bool(token),
        {"status_code": status_code, "has_token": bool(token), "payload": login_payload if status_code != 200 else None},
    )

    if not token:
        return {
            "generated_at": _utcnow_iso(),
            "base_url": base_url,
            "overall": "FAIL",
            "passed": passed,
            "failed": failed,
            "checks": checks,
        }

    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Session-Device": "legacy-session",
    })

    status_code, live_payload = _request(session, "GET", f"{base_url}/api/admin/futures/live-readiness")
    live_ok = status_code == 200 and isinstance(live_payload, dict) and "readiness_matrix" in live_payload and "execution_proof" in live_payload
    add_check("live_readiness_endpoint_smoke", live_ok, {"status_code": status_code, "keys": sorted(list((live_payload or {}).keys()))[:20] if isinstance(live_payload, dict) else []})

    status_code, history_payload = _request(session, "GET", f"{base_url}/api/admin/futures/readiness/history", params={"limit": 20, "days": 14})
    history_ok = status_code == 200 and isinstance(history_payload, dict) and "top_blockers" in history_payload and "failure_trend" in history_payload
    add_check("history_endpoint_smoke", history_ok, {"status_code": status_code, "has_runbook_mapping": bool((history_payload or {}).get("runbook_mapping")) if isinstance(history_payload, dict) else False})

    status_code, execution_payload = _request(session, "GET", f"{base_url}/api/admin/execution-readiness")
    execution_ok = status_code == 200 and isinstance(execution_payload, dict) and "execution_proof" in execution_payload
    add_check(
        "execution_readiness_smoke",
        execution_ok,
        {
            "status_code": status_code,
            "proof_status": (execution_payload or {}).get("execution_proof", {}).get("proof_status") if isinstance(execution_payload, dict) else None,
            "mocked_paths": (execution_payload or {}).get("mocked_paths") if isinstance(execution_payload, dict) else None,
        },
    )

    status_code, maintenance_payload = _request(
        session,
        "POST",
        f"{base_url}/api/admin/futures/readiness/history/maintenance",
        params={"dry_run": "true"},
    )
    maintenance_ok = status_code == 200 and isinstance(maintenance_payload, dict) and "policy" in maintenance_payload
    add_check("maintenance_trigger_smoke", maintenance_ok, {"status_code": status_code, "dry_run": (maintenance_payload or {}).get("dry_run") if isinstance(maintenance_payload, dict) else None})

    required_venues = []
    if isinstance(live_payload, dict):
        required_venues = [str(item).strip().lower() for item in (live_payload.get("required_venues") or []) if str(item).strip()]
    if not required_venues:
        required_venues = ["binance"]

    bybit_required = "bybit" in required_venues
    bybit_state = None
    if isinstance(live_payload, dict):
        bybit_state = ((live_payload.get("readiness_matrix") or {}).get("exchange") or {}).get("bybit", {}).get("state")
    bybit_ok = bool(bybit_state) if bybit_required else True
    add_check(
        "bybit_venue_readiness_smoke",
        bybit_ok,
        {
            "required": bybit_required,
            "required_venues": required_venues,
            "state": bybit_state,
            "skipped": not bybit_required,
        },
    )

    runbook_ok = isinstance(history_payload, dict) and bool(history_payload.get("runbook_mapping"))
    add_check("runbook_mapping_smoke", runbook_ok, {"mapping_size": len((history_payload or {}).get("runbook_mapping") or {}) if isinstance(history_payload, dict) else 0})

    overall = "PASS" if failed == 0 else "FAIL"
    return {
        "generated_at": _utcnow_iso(),
        "base_url": base_url,
        "overall": overall,
        "passed": passed,
        "failed": failed,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Operational readiness smoke suite")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    report = run_smoke(base_url=args.base_url, email=args.email, password=args.password)
    report_path = Path(args.output) if args.output else Path(f"/app/test_reports/readiness_ops_smoke_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(report_path), **report}, ensure_ascii=False, indent=2))
    return 0 if report.get("overall") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
