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


def _http_request(method: str, url: str, *, timeout: int = 20, **kwargs) -> tuple[requests.Response | None, str | None]:
    try:
        response = requests.request(method=method, url=url, timeout=timeout, **kwargs)
        return response, None
    except requests.RequestException as exc:
        return None, str(exc)


def _safe_json(response: requests.Response | None) -> dict:
    if response is None:
        return {}
    try:
        payload = response.json()
        return payload if isinstance(payload, dict) else {}
    except ValueError:
        return {}


def run() -> int:
    base = _resolve_base_url()
    admin_email = (os.environ.get("TEST_ADMIN_EMAIL") or "").strip()
    admin_password = (os.environ.get("TEST_ADMIN_PASSWORD") or "").strip()
    if not admin_email or not admin_password:
        print(
            json.dumps(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "base_url": base,
                    "checks": [
                        _check(False, "admin_credentials_present", {"reason": "missing_TEST_ADMIN_EMAIL_or_TEST_ADMIN_PASSWORD"})
                    ],
                    "overall": "FAIL",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    checks: list[dict] = []

    health, health_error = _http_request("GET", f"{base}/api/health", timeout=20)
    health_status = health.status_code if health is not None else None
    checks.append(_check(health_status == 200, "health_endpoint", {"status_code": health_status, "error": health_error}))

    auth, auth_error = _http_request(
        "POST",
        f"{base}/api/auth/login/admin",
        json={"email": admin_email, "password": admin_password},
        timeout=20,
    )
    auth_status = auth.status_code if auth is not None else None
    auth_payload = _safe_json(auth)
    auth_ok = auth_status == 200 and bool(auth_payload.get("access_token"))
    checks.append(_check(auth_ok, "admin_login", {"status_code": auth_status, "error": auth_error}))
    if not auth_ok:
        print(
            json.dumps(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "base_url": base,
                    "checks": checks,
                    "overall": "FAIL",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    token = auth_payload["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    gate, gate_error = _http_request("GET", f"{base}/api/admin/release-gate", headers=headers, timeout=20)
    gate_status = gate.status_code if gate is not None else None
    gate_ok = gate_status == 200
    gate_payload = _safe_json(gate)
    gate_contract_ok = gate_ok and isinstance(gate_payload.get("reason_codes"), list) and isinstance(gate_payload.get("blocking_metrics"), dict)
    if gate_ok and str(gate_payload.get("status") or "") == "BLOCKED":
        gate_contract_ok = gate_contract_ok and len(gate_payload.get("reason_codes") or []) > 0
    checks.append(
        _check(
            gate_contract_ok,
            "release_gate_contract",
            {
                "status_code": gate_status,
                "status": gate_payload.get("status"),
                "reason_codes": gate_payload.get("reason_codes"),
                "deploy_enable_flag": gate_payload.get("deploy_enable_flag"),
                "error": gate_error,
            },
        )
    )

    readiness, readiness_error = _http_request("GET", f"{base}/api/admin/execution-readiness", headers=headers, timeout=20)
    readiness_status = readiness.status_code if readiness is not None else None
    readiness_ok = readiness_status == 200
    readiness_payload = _safe_json(readiness)
    readiness_contract_ok = readiness_ok and readiness_payload.get("final_status") == "READY" and isinstance(readiness_payload.get("latency_ms"), int)
    checks.append(
        _check(
            readiness_contract_ok,
            "execution_readiness_ready",
            {
                "status_code": readiness_status,
                "final_status": readiness_payload.get("final_status"),
                "mode": readiness_payload.get("mode"),
                "latency_ms": readiness_payload.get("latency_ms"),
                "error": readiness_error,
            },
        )
    )

    guard_email = f"smoke_guard_{uuid.uuid4().hex[:8]}@example.com"
    guard_password = "SmokeGuard123!"

    register, register_error = _http_request(
        "POST",
        f"{base}/api/auth/register",
        json={"email": guard_email, "password": guard_password},
        timeout=20,
    )
    register_status = register.status_code if register is not None else None
    register_payload = _safe_json(register)
    register_ok = register_status == 200 and bool(register_payload.get("id"))
    checks.append(_check(register_ok, "guard_user_register", {"status_code": register_status, "error": register_error}))

    if register_ok:
        user_id = register_payload["id"]
        approve, approve_error = _http_request(
            "POST",
            f"{base}/api/auth/admin/user-approval-requests/{user_id}/approve",
            headers=headers,
            timeout=20,
        )
        approve_status = approve.status_code if approve is not None else None
        approve_ok = approve_status == 200
        checks.append(_check(approve_ok, "guard_user_approve", {"status_code": approve_status, "error": approve_error}))
    else:
        approve_ok = False

    if approve_ok:
        user_login, user_login_error = _http_request(
            "POST",
            f"{base}/api/auth/login/user",
            json={"email": guard_email, "password": guard_password},
            timeout=20,
        )
        user_login_status = user_login.status_code if user_login is not None else None
        user_login_payload = _safe_json(user_login)
        user_login_ok = user_login_status == 200 and bool(user_login_payload.get("access_token"))
        checks.append(_check(user_login_ok, "guard_user_login", {"status_code": user_login_status, "error": user_login_error}))
    else:
        user_login_ok = False

    if user_login_ok:
        user_headers = {"Authorization": f"Bearer {user_login_payload['access_token']}"}
        validate_order, validate_order_error = _http_request(
            "POST",
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
        validate_status = validate_order.status_code if validate_order is not None else None
        validate_ok = validate_status == 200
        validate_payload = _safe_json(validate_order)
        checks.append(
            _check(
                validate_ok,
                "validate_order_endpoint",
                {
                    "status_code": validate_status,
                    "valid": validate_payload.get("valid"),
                    "violations_count": len(validate_payload.get("violations") or []),
                    "execution_mode": validate_payload.get("execution_mode"),
                    "error": validate_order_error,
                },
            )
        )

        guard_probe, guard_probe_error = _http_request(
            "POST",
            f"{base}/api/user/manual-trade",
            headers=user_headers,
            json={"intent_token": "smoke_guard_token", "preview_hash": "smoke_guard_hash"},
            timeout=20,
        )
        guard_probe_status = guard_probe.status_code if guard_probe is not None else None
        guard_probe_body = guard_probe.text[:180] if guard_probe is not None else ""
        checks.append(
            _check(
                guard_probe_status == 423,
                "execution_guard_423",
                {"status_code": guard_probe_status, "body": guard_probe_body, "error": guard_probe_error},
            )
        )

    futures_path, futures_path_error = _http_request(
        "GET",
        f"{base}/api/admin/users/futures-live-path-check",
        params={"limit": 200},
        headers=headers,
        timeout=30,
    )
    futures_status = futures_path.status_code if futures_path is not None else None
    futures_ok = futures_status == 200
    futures_payload = _safe_json(futures_path)
    checks.append(
        _check(
            futures_ok,
            "futures_live_path_check",
            {
                "status_code": futures_status,
                "total_users": futures_payload.get("total_users"),
                "fail_count": futures_payload.get("fail_count"),
                "error": futures_path_error,
            },
        )
    )

    burnin, burnin_error = _http_request(
        "GET",
        f"{base}/api/admin/system-alerts/burn-in",
        params={"days": 7},
        headers=headers,
        timeout=20,
    )
    burnin_status = burnin.status_code if burnin is not None else None
    burnin_ok = burnin_status == 200
    burnin_payload = _safe_json(burnin)
    checks.append(
        _check(
            burnin_ok,
            "alert_burnin",
            {
                "status_code": burnin_status,
                "total_alerts": burnin_payload.get("total_alerts"),
                "recommendation": burnin_payload.get("recommendation"),
                "error": burnin_error,
            },
        )
    )

    timeline, timeline_error = _http_request(
        "GET",
        f"{base}/api/audit-logs/timeline",
        params={"limit": 100},
        headers=headers,
        timeout=20,
    )
    timeline_status = timeline.status_code if timeline is not None else None
    timeline_ok = timeline_status == 200
    timeline_payload = _safe_json(timeline)
    checks.append(
        _check(
            timeline_ok,
            "audit_timeline",
            {
                "status_code": timeline_status,
                "total": timeline_payload.get("total"),
                "error": timeline_error,
            },
        )
    )

    export, export_error = _http_request(
        "GET",
        f"{base}/api/audit-logs/admin/incident-export",
        params={"window_days": 7, "limit": 200},
        headers=headers,
        timeout=40,
    )
    export_status = export.status_code if export is not None else None
    export_content_type = export.headers.get("content-type", "") if export is not None else ""
    export_bytes = len(export.content or b"") if export is not None else 0
    export_ok = export_status == 200 and "application/zip" in export_content_type
    checks.append(
        _check(
            export_ok,
            "incident_export",
            {
                "status_code": export_status,
                "content_type": export_content_type,
                "bytes": export_bytes,
                "error": export_error,
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
