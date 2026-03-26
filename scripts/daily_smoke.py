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


def _build_http_client(base_url: str):
    try:
        probe = requests.get(f"{base_url}/api/health/live", timeout=8)
        if probe.status_code in {200, 503}:
            return {"mode": "external", "base_url": base_url, "client": None}
    except Exception:  # noqa: BLE001
        pass

    from fastapi.testclient import TestClient  # noqa: E402
    from server import fastapi_app  # noqa: E402

    return {"mode": "testclient", "base_url": "", "client": TestClient(fastapi_app)}


def _http_request(http_ctx: dict, method: str, path: str, *, json_payload=None, params=None, headers=None, timeout=30):
    mode = http_ctx["mode"]
    if mode == "external":
        url = f"{http_ctx['base_url']}{path}"
        response = requests.request(method, url, json=json_payload, params=params, headers=headers, timeout=timeout)
    else:
        client = http_ctx["client"]
        response = client.request(method, path, json=json_payload, params=params, headers=headers)

    if response.status_code >= 400:
        raise RuntimeError(f"http_error:{method}:{path}:{response.status_code}:{response.text[:300]}")
    return response.json() if response.text else {}


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"missing_env:{name}")
    return value


def _required_env_any(*names: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    raise RuntimeError(f"missing_env_any:{','.join(names)}")


def _run_step(name: str, fn):
    started = time.time()
    try:
        payload = fn() or {}
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
    base_url = _required_env_any("BACKEND_PUBLIC_URL", "REACT_APP_BACKEND_URL").rstrip("/")
    admin_email = _required_env("DAILY_SMOKE_ADMIN_EMAIL")
    admin_password = _required_env("DAILY_SMOKE_ADMIN_PASSWORD")
    ingest_admin_email = _required_env("DAILY_SMOKE_INGEST_ADMIN_EMAIL")
    ingest_admin_password = _required_env("DAILY_SMOKE_INGEST_ADMIN_PASSWORD")
    ingest_target_user_email = _required_env("DAILY_SMOKE_INGEST_TARGET_USER_EMAIL")
    smoke_environment = str(os.environ.get("DAILY_SMOKE_ENVIRONMENT") or "testnet").strip().lower()
    market_types = [item.strip().lower() for item in str(os.environ.get("DAILY_SMOKE_MARKET_TYPES") or "futures").split(",") if item.strip()]
    if not market_types:
        market_types = ["futures"]

    http_ctx = _build_http_client(base_url)

    login_payload = _http_request(
        http_ctx,
        "POST",
        "/api/auth/login",
        json_payload={"email": admin_email, "password": admin_password},
        timeout=25,
    )
    token = login_payload.get("access_token") or login_payload.get("token")
    headers = {"Authorization": f"Bearer {token}"}

    ingest_login_payload = _http_request(
        http_ctx,
        "POST",
        "/api/auth/login",
        json_payload={"email": ingest_admin_email, "password": ingest_admin_password},
        timeout=25,
    )
    ingest_token = ingest_login_payload.get("access_token") or ingest_login_payload.get("token")
    ingest_headers = {"Authorization": f"Bearer {ingest_token}"}

    def ingest_step():
        return _http_request(
            http_ctx,
            "POST",
            "/api/admin/commercial/p0/ingestion/rest-run",
            json_payload={
                "target_user_email": ingest_target_user_email,
                "exchange": "binance",
                "environment": smoke_environment,
                "market_types": market_types,
                "limit_per_market": 100,
            },
            headers=ingest_headers,
            timeout=120,
        )

    def pnl_step():
        return _http_request(
            http_ctx,
            "GET",
            "/api/admin/commercial/p0/pnl/latest",
            params={"environment": smoke_environment, "target_user_email": ingest_target_user_email, "market_types": market_types},
            headers=headers,
            timeout=45,
        )

    def reconciliation_step():
        return _http_request(
            http_ctx,
            "POST",
            "/api/admin/commercial/p0/reconciliation/run",
            json_payload={
                "environment": smoke_environment,
                "target_user_email": ingest_target_user_email,
                "market_types": market_types,
                "limit_per_symbol": 100,
            },
            headers=headers,
            timeout=60,
        )

    def revenue_step():
        return _http_request(
            http_ctx,
            "GET",
            "/api/admin/revenue/summary",
            params={"environment": smoke_environment, "top_limit": 10},
            headers=headers,
            timeout=45,
        )

    def snapshot_compare_step():
        now = datetime.now(timezone.utc)
        prev = now - timedelta(days=1)
        for as_of in [now, prev]:
            _http_request(
                http_ctx,
                "POST",
                "/api/admin/snapshots/run",
                params={
                    "environment": smoke_environment,
                    "snapshot_type": "daily",
                    "as_of_date": as_of.isoformat(),
                    "top_limit": 20,
                },
                headers=headers,
                timeout=60,
            )

        listing = _http_request(
            http_ctx,
            "GET",
            "/api/admin/snapshots",
            params={"environment": smoke_environment, "snapshot_type": "daily", "limit": 5},
            headers=headers,
            timeout=45,
        )
        items = listing.get("items", [])
        if len(items) < 2:
            raise RuntimeError("snapshot_compare_insufficient_data")

        return _http_request(
            http_ctx,
            "GET",
            "/api/admin/snapshots/compare",
            params={"base_snapshot_id": items[1]["id"], "target_snapshot_id": items[0]["id"]},
            headers=headers,
            timeout=45,
        )

    steps = {
        "ingest": _run_step("ingest", ingest_step),
        "pnl": _run_step("pnl", pnl_step),
        "reconciliation": _run_step("reconciliation", reconciliation_step),
        "revenue": _run_step("revenue", revenue_step),
        "snapshot_compare": _run_step("snapshot_compare", snapshot_compare_step),
    }

    has_fail = any(step.get("status") == "FAIL" for step in steps.values())
    overall = "FAIL" if has_fail else "PASS"

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
