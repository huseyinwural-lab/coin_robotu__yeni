from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests


def _resolve_base_url() -> str:
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if direct:
        return direct
    env_file = Path("/app/frontend/.env")
    if env_file.exists():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            if raw_line.startswith("REACT_APP_BACKEND_URL="):
                return raw_line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


def _check(status: bool, name: str, details: dict | None = None) -> dict:
    return {
        "name": name,
        "status": "PASS" if status else "FAIL",
        "details": details or {},
    }


def run() -> int:
    base = _resolve_base_url()
    admin_email = os.environ.get("TEST_ADMIN_EMAIL", "admin@platform.local")
    admin_password = os.environ.get("TEST_ADMIN_PASSWORD", "Admin12345!")

    checks: list[dict] = []

    health = requests.get(f"{base}/api/health", timeout=20)
    checks.append(_check(health.status_code == 200, "health_endpoint", {"status_code": health.status_code}))

    auth = requests.post(
        f"{base}/api/auth/login/admin",
        json={"email": admin_email, "password": admin_password},
        timeout=20,
    )
    auth_ok = auth.status_code == 200 and bool(auth.json().get("access_token")) if auth.status_code == 200 else False
    checks.append(_check(auth_ok, "admin_login", {"status_code": auth.status_code}))
    if not auth_ok:
        print(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "checks": checks}, ensure_ascii=False, indent=2))
        return 1

    token = auth.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    gate = requests.get(f"{base}/api/admin/release-gate", headers=headers, timeout=20)
    gate_ok = gate.status_code == 200
    gate_payload = gate.json() if gate_ok else {}
    gate_contract_ok = gate_ok and isinstance(gate_payload.get("reason_codes"), list) and isinstance(gate_payload.get("blocking_metrics"), dict)
    if gate_ok and str(gate_payload.get("status") or "") == "BLOCKED":
        gate_contract_ok = gate_contract_ok and len(gate_payload.get("reason_codes") or []) > 0
    checks.append(
        _check(
            gate_contract_ok,
            "release_gate_contract",
            {
                "status_code": gate.status_code,
                "status": gate_payload.get("status"),
                "reason_codes": gate_payload.get("reason_codes"),
                "deploy_enable_flag": gate_payload.get("deploy_enable_flag"),
            },
        )
    )

    readiness = requests.get(f"{base}/api/admin/execution-readiness", headers=headers, timeout=20)
    readiness_ok = readiness.status_code == 200
    readiness_payload = readiness.json() if readiness_ok else {}
    readiness_contract_ok = readiness_ok and readiness_payload.get("final_status") == "READY" and isinstance(readiness_payload.get("latency_ms"), int)
    checks.append(
        _check(
            readiness_contract_ok,
            "execution_readiness_ready",
            {
                "status_code": readiness.status_code,
                "final_status": readiness_payload.get("final_status"),
                "mode": readiness_payload.get("mode"),
                "latency_ms": readiness_payload.get("latency_ms"),
            },
        )
    )

    guard_email = f"smoke_guard_{uuid.uuid4().hex[:8]}@example.com"
    guard_password = "SmokeGuard123!"

    register = requests.post(
        f"{base}/api/auth/register",
        json={"email": guard_email, "password": guard_password},
        timeout=20,
    )
    register_ok = register.status_code == 200 and bool(register.json().get("id")) if register.status_code == 200 else False
    checks.append(_check(register_ok, "guard_user_register", {"status_code": register.status_code}))

    if register_ok:
        user_id = register.json()["id"]
        approve = requests.post(
            f"{base}/api/auth/admin/user-approval-requests/{user_id}/approve",
            headers=headers,
            timeout=20,
        )
        approve_ok = approve.status_code == 200
        checks.append(_check(approve_ok, "guard_user_approve", {"status_code": approve.status_code}))
    else:
        approve_ok = False

    if approve_ok:
        user_login = requests.post(
            f"{base}/api/auth/login/user",
            json={"email": guard_email, "password": guard_password},
            timeout=20,
        )
        user_login_ok = user_login.status_code == 200 and bool(user_login.json().get("access_token")) if user_login.status_code == 200 else False
        checks.append(_check(user_login_ok, "guard_user_login", {"status_code": user_login.status_code}))
    else:
        user_login_ok = False

    if user_login_ok:
        user_headers = {"Authorization": f"Bearer {user_login.json()['access_token']}"}
        validate_order = requests.post(
            f"{base}/api/user/validate-order",
            headers=user_headers,
            json={
                "symbol": "BTCUSDT",
                "market_type": "futures",
                "order_type": "market",
                "side": "buy",
                "price": 100,
                "size": 0.0001,
                "leverage": 100,
                "margin_mode": "isolated",
            },
            timeout=20,
        )
        validate_ok = validate_order.status_code == 200
        validate_payload = validate_order.json() if validate_ok else {}
        checks.append(
            _check(
                validate_ok,
                "validate_order_endpoint",
                {
                    "status_code": validate_order.status_code,
                    "valid": validate_payload.get("valid"),
                    "violations_count": len(validate_payload.get("violations") or []),
                    "execution_mode": validate_payload.get("execution_mode"),
                },
            )
        )

        guard_probe = requests.post(
            f"{base}/api/user/manual-trade",
            headers=user_headers,
            json={"intent_token": "smoke_guard_token", "preview_hash": "smoke_guard_hash"},
            timeout=20,
        )
        checks.append(
            _check(
                guard_probe.status_code == 423,
                "execution_guard_423",
                {"status_code": guard_probe.status_code, "body": guard_probe.text[:180]},
            )
        )

    futures_path = requests.get(
        f"{base}/api/admin/users/futures-live-path-check",
        params={"limit": 200},
        headers=headers,
        timeout=30,
    )
    futures_ok = futures_path.status_code == 200
    futures_payload = futures_path.json() if futures_ok else {}
    checks.append(
        _check(
            futures_ok,
            "futures_live_path_check",
            {
                "status_code": futures_path.status_code,
                "total_users": futures_payload.get("total_users"),
                "fail_count": futures_payload.get("fail_count"),
            },
        )
    )

    burnin = requests.get(
        f"{base}/api/admin/system-alerts/burn-in",
        params={"days": 7},
        headers=headers,
        timeout=20,
    )
    burnin_ok = burnin.status_code == 200
    burnin_payload = burnin.json() if burnin_ok else {}
    checks.append(
        _check(
            burnin_ok,
            "alert_burnin",
            {
                "status_code": burnin.status_code,
                "total_alerts": burnin_payload.get("total_alerts"),
                "recommendation": burnin_payload.get("recommendation"),
            },
        )
    )

    timeline = requests.get(
        f"{base}/api/audit-logs/timeline",
        params={"limit": 100},
        headers=headers,
        timeout=20,
    )
    timeline_ok = timeline.status_code == 200
    timeline_payload = timeline.json() if timeline_ok else {}
    checks.append(
        _check(
            timeline_ok,
            "audit_timeline",
            {
                "status_code": timeline.status_code,
                "total": timeline_payload.get("total"),
            },
        )
    )

    export = requests.get(
        f"{base}/api/audit-logs/admin/incident-export",
        params={"window_days": 7, "limit": 200},
        headers=headers,
        timeout=40,
    )
    export_ok = export.status_code == 200 and "application/zip" in export.headers.get("content-type", "")
    checks.append(
        _check(
            export_ok,
            "incident_export",
            {
                "status_code": export.status_code,
                "content_type": export.headers.get("content-type"),
                "bytes": len(export.content or b""),
            },
        )
    )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base,
        "checks": checks,
        "overall": "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(run())
