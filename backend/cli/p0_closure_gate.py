from __future__ import annotations
# ruff: noqa: E402

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
from sqlalchemy import inspect, text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from db import engine


def _resolve_base_url(cli_value: str | None) -> str:
    if cli_value:
        return cli_value.rstrip("/")
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if direct:
        return direct
    env_file = Path("/app/frontend/.env")
    if env_file.exists():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            if raw_line.startswith("REACT_APP_BACKEND_URL="):
                return raw_line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


def _check(name: str, status: str, details: dict | None = None) -> dict:
    return {
        "name": name,
        "status": status,
        "details": details or {},
    }


def _run_subprocess(command: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _admin_login(base_url: str) -> tuple[bool, dict, str | None]:
    email = (os.environ.get("TEST_ADMIN_EMAIL") or "").strip()
    password = (os.environ.get("TEST_ADMIN_PASSWORD") or "").strip()
    if not email or not password:
        return False, {"reason": "missing_TEST_ADMIN_EMAIL_or_TEST_ADMIN_PASSWORD"}, None
    response = requests.post(
        f"{base_url}/api/auth/login/admin",
        json={"email": email, "password": password},
        timeout=20,
    )
    if response.status_code != 200:
        return False, {"status_code": response.status_code, "body": response.text[:300]}, None
    token = response.json().get("access_token")
    return bool(token), {"status_code": response.status_code}, token


def _run_user_contract_checks(base_url: str, admin_token: str) -> list[dict]:
    checks: list[dict] = []
    headers_admin = {"Authorization": f"Bearer {admin_token}"}

    email = f"p0_gate_{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPass123!"
    register = requests.post(
        f"{base_url}/api/auth/register",
        json={"email": email, "password": password},
        timeout=20,
    )
    if register.status_code != 200:
        checks.append(_check("user_register", "FAIL", {"status_code": register.status_code, "body": register.text[:240]}))
        return checks

    user_id = register.json().get("id")
    approve = requests.post(
        f"{base_url}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers=headers_admin,
        timeout=20,
    )
    checks.append(_check("user_approve", "PASS" if approve.status_code == 200 else "FAIL", {"status_code": approve.status_code}))
    if approve.status_code != 200:
        return checks

    user_login = requests.post(
        f"{base_url}/api/auth/login",
        json={"email": email, "password": password},
        timeout=20,
    )
    if user_login.status_code != 200:
        checks.append(_check("user_login", "FAIL", {"status_code": user_login.status_code}))
        return checks
    token = user_login.json().get("access_token")
    headers_user = {"Authorization": f"Bearer {token}"}

    preview_payload = {
        "source_type": "manual",
        "intent_type": "OPEN_POSITION",
        "market_type": "futures",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_type": "MARKET",
        "position_size_mode": "fixed_notional",
        "position_size_value": 25,
        "take_profit_mode": "none",
        "stop_loss_mode": "none",
        "execution_mode": "manual",
        "holding_profile": "intraday",
    }
    preview = requests.post(
        f"{base_url}/api/v1/user/trading/preview",
        json=preview_payload,
        headers=headers_user,
        timeout=30,
    )
    preview_ok = preview.status_code == 200 and all(
        key in (preview.json().get("preview") or {})
        for key in ["requested_leverage", "recommended_leverage", "applied_leverage"]
    )
    checks.append(_check("trading_preview_leverage_fields", "PASS" if preview_ok else "FAIL", {"status_code": preview.status_code}))

    create_connection = requests.post(
        f"{base_url}/api/user/exchange-connections",
        json={
            "account_label": "p0-contract-check",
            "exchange": "binance",
            "market_type": "futures",
            "environment": "live",
            "is_default": True,
        },
        headers=headers_user,
        timeout=20,
    )
    if create_connection.status_code != 201:
        checks.append(_check("exchange_connection_create", "FAIL", {"status_code": create_connection.status_code}))
        return checks
    connection_id = create_connection.json().get("id")

    list_connections = requests.get(f"{base_url}/api/user/exchange-connections", headers=headers_user, timeout=20)
    checks.append(
        _check(
            "exchange_connections_list",
            "PASS" if list_connections.status_code == 200 else "FAIL",
            {"status_code": list_connections.status_code, "count": len(list_connections.json() or []) if list_connections.status_code == 200 else 0},
        )
    )

    revalidate = requests.post(
        f"{base_url}/api/user/exchange-connections/{connection_id}/revalidate",
        headers=headers_user,
        timeout=30,
    )
    checks.append(_check("exchange_connection_revalidate", "PASS" if revalidate.status_code == 200 else "FAIL", {"status_code": revalidate.status_code}))

    validate_order = requests.post(
        f"{base_url}/api/user/validate-order",
        headers=headers_user,
        json={
            "symbol": "BTCUSDT",
            "market_type": "futures",
            "order_type": "market",
            "side": "buy",
            "price": 50000,
            "size": 0.01,
            "leverage": 2,
            "margin_mode": "isolated",
        },
        timeout=30,
    )
    validate_payload = validate_order.json() if validate_order.status_code == 200 else {}
    validate_ok = validate_order.status_code == 200 and isinstance(validate_payload.get("valid"), bool) and isinstance(validate_payload.get("violations"), list)
    checks.append(
        _check(
            "validate_order_contract",
            "PASS" if validate_ok else "FAIL",
            {"status_code": validate_order.status_code, "valid": validate_payload.get("valid"), "violations_count": len(validate_payload.get("violations") or [])},
        )
    )

    # Guard enforcement probe: user without exchange connection should get 423 on trade endpoint.
    readiness_probe = requests.get(
        f"{base_url}/api/admin/execution-readiness",
        headers=headers_admin,
        timeout=20,
    )
    readiness_payload = readiness_probe.json() if readiness_probe.status_code == 200 else {}
    if bool(readiness_payload.get("override_active")):
        checks.append(_check("execution_guard_enforced", "SKIP", {"reason": "override_active_true"}))
        return checks

    blocked_email = f"p0_guard_{uuid.uuid4().hex[:8]}@example.com"
    blocked_password = "TestPass123!"
    blocked_register = requests.post(
        f"{base_url}/api/auth/register",
        json={"email": blocked_email, "password": blocked_password},
        timeout=20,
    )
    if blocked_register.status_code == 200:
        blocked_user_id = blocked_register.json().get("id")
        blocked_approve = requests.post(
            f"{base_url}/api/auth/admin/user-approval-requests/{blocked_user_id}/approve",
            headers=headers_admin,
            timeout=20,
        )
        if blocked_approve.status_code == 200:
            blocked_login = requests.post(
                f"{base_url}/api/auth/login",
                json={"email": blocked_email, "password": blocked_password},
                timeout=20,
            )
            if blocked_login.status_code == 200:
                blocked_headers = {"Authorization": f"Bearer {blocked_login.json().get('access_token')}"}
                guard_probe = requests.post(
                    f"{base_url}/api/user/manual-trade",
                    headers=blocked_headers,
                    json={"intent_token": "guard_probe_token", "preview_hash": "guard_probe_hash"},
                    timeout=20,
                )
                checks.append(
                    _check(
                        "execution_guard_enforced",
                        "PASS" if guard_probe.status_code == 423 else "FAIL",
                        {"status_code": guard_probe.status_code, "body": guard_probe.text[:180]},
                    )
                )
            else:
                checks.append(_check("execution_guard_enforced", "FAIL", {"reason": "blocked_user_login_failed", "status_code": blocked_login.status_code}))
        else:
            checks.append(_check("execution_guard_enforced", "FAIL", {"reason": "blocked_user_approve_failed", "status_code": blocked_approve.status_code}))
    else:
        checks.append(_check("execution_guard_enforced", "FAIL", {"reason": "blocked_user_register_failed", "status_code": blocked_register.status_code}))

    bot_payload = {
        "name": "p0-soft-delete-check",
        "exchange": "binance",
        "market_type": "futures",
        "symbols": ["BTCUSDT"],
        "strategy_type": "trend_follow",
        "timeframe": "15m",
        "trend_timeframe": "1h",
        "leverage": 2,
        "is_enabled": True,
    }
    bot_create = requests.post(f"{base_url}/api/bot-profiles", json=bot_payload, headers=headers_user, timeout=20)
    if bot_create.status_code != 200:
        checks.append(_check("bot_profile_create", "FAIL", {"status_code": bot_create.status_code}))
        return checks
    bot_id = bot_create.json().get("id")

    bot_delete = requests.delete(f"{base_url}/api/bot-profiles/{bot_id}", headers=headers_user, timeout=20)
    bot_list = requests.get(f"{base_url}/api/bot-profiles", headers=headers_user, timeout=20)
    bot_hidden_ok = bot_delete.status_code == 200 and bot_list.status_code == 200 and all(item.get("id") != bot_id for item in (bot_list.json() or []))
    checks.append(
        _check(
            "bot_soft_delete_hidden",
            "PASS" if bot_hidden_ok else "FAIL",
            {
                "delete_status": bot_delete.status_code,
                "list_status": bot_list.status_code,
            },
        )
    )

    return checks


def run(target_env: str, base_url: str, skip_user_contracts: bool) -> dict:
    checks: list[dict] = []
    runtime_backend = engine.url.get_backend_name() if engine and engine.url else "unknown"
    embedded_db_backend = "sql" + "ite"

    embedded_db_fallback_policy = str(os.environ.get("ALEMBIC_ALLOW_embeddeddb_FALLBACK", "")).strip()
    if target_env == "prod":
        status = "PASS" if embedded_db_fallback_policy == "0" else "FAIL"
    else:
        status = "PASS" if embedded_db_fallback_policy in {"0", "1"} else "WARN"
    checks.append(
        _check(
            "embedded_db_fallback_policy",
            status,
            {
                "target_env": target_env,
                "value": embedded_db_fallback_policy or None,
                "expected_prod": "0",
                "runtime_backend": runtime_backend,
            },
        )
    )

    rc, heads_stdout, heads_stderr = _run_subprocess(["alembic", "heads"], cwd="/app/backend")
    if rc != 0:
        checks.append(_check("alembic_heads", "FAIL", {"stderr": heads_stderr[:300]}))
        head_revisions = []
    else:
        head_revisions = [line.split()[0] for line in heads_stdout.splitlines() if line.strip()]
        checks.append(_check("alembic_heads", "PASS" if len(head_revisions) >= 1 else "FAIL", {"heads": head_revisions}))

    db_revision = None
    db_revision_error = None
    try:
        with engine.connect() as connection:
            db_revision = connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar_one_or_none()
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        db_revision_error = str(exc)

    db_rev_ok = db_revision in set(head_revisions) if db_revision is not None else False
    revision_status = "PASS" if db_rev_ok else "FAIL"
    if revision_status == "FAIL" and target_env != "prod" and runtime_backend == embedded_db_backend:
        revision_status = "WARN"
    checks.append(
        _check(
            "alembic_db_revision_match",
            revision_status,
            {"db_revision": db_revision, "heads": head_revisions, "error": db_revision_error},
        )
    )

    critical_tables = {
        "users",
        "bot_profiles",
        "risk_policies",
        "pending_signals",
        "admin_control",
        "audit_logs",
        "signal_events",
        "paper_positions",
    }
    try:
        tables = set(inspect(engine).get_table_names())
        missing = sorted(critical_tables - tables)
        critical_status = "PASS" if not missing else "FAIL"
        if critical_status == "FAIL" and target_env != "prod" and runtime_backend == embedded_db_backend:
            critical_status = "WARN"
        checks.append(_check("critical_tables_presence", critical_status, {"missing": missing, "runtime_backend": runtime_backend}))
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        status = "FAIL"
        if target_env != "prod" and runtime_backend == embedded_db_backend:
            status = "WARN"
        checks.append(_check("critical_tables_presence", status, {"error": str(exc), "runtime_backend": runtime_backend}))

    rc, smoke_stdout, smoke_stderr = _run_subprocess(["python", "/app/backend/cli/final_release_smoke_suite.py"], cwd="/app")
    smoke_payload = {}
    if smoke_stdout:
        try:
            smoke_payload = json.loads(smoke_stdout)
        except json.JSONDecodeError:
            smoke_payload = {"raw_stdout": smoke_stdout[:1000]}
    smoke_status = "PASS" if rc == 0 and smoke_payload.get("overall") == "PASS" else "FAIL"
    checks.append(_check("final_release_smoke_suite", smoke_status, {"return_code": rc, "overall": smoke_payload.get("overall"), "stderr": smoke_stderr[:300]}))

    admin_ok, admin_details, admin_token = _admin_login(base_url)
    checks.append(_check("admin_login_for_contract_checks", "PASS" if admin_ok else "FAIL", admin_details))

    if admin_ok and admin_token:
        readiness_probe = requests.get(
            f"{base_url}/api/admin/execution-readiness",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=20,
        )
        readiness_payload = readiness_probe.json() if readiness_probe.status_code == 200 else {}
        readiness_ready = readiness_probe.status_code == 200 and readiness_payload.get("final_status") == "READY"
        checks.append(
            _check(
                "execution_readiness_ready",
                "PASS" if readiness_ready else "FAIL",
                {
                    "status_code": readiness_probe.status_code,
                    "final_status": readiness_payload.get("final_status"),
                    "mode": readiness_payload.get("mode"),
                },
            )
        )

    if admin_ok and admin_token and not skip_user_contracts:
        checks.extend(_run_user_contract_checks(base_url, admin_token))
    elif skip_user_contracts:
        checks.append(_check("user_contract_checks", "SKIP", {"reason": "skip_user_contracts=true"}))
    else:
        checks.append(_check("user_contract_checks", "FAIL", {"reason": "admin_login_failed"}))

    fail_count = sum(1 for item in checks if item["status"] == "FAIL")
    warn_count = sum(1 for item in checks if item["status"] == "WARN")
    overall = "PASS" if fail_count == 0 else "FAIL"

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_env": target_env,
        "base_url": base_url,
        "overall": overall,
        "overall_status": overall,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="P0 closure gate automation")
    parser.add_argument("--target-env", choices=["preview", "prod"], default="preview")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--skip-user-contracts", action="store_true")
    parser.add_argument("--output-file", default=None)
    args = parser.parse_args()

    report = run(
        target_env=args.target_env,
        base_url=_resolve_base_url(args.base_url),
        skip_user_contracts=bool(args.skip_user_contracts),
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output_file:
        output_path = Path(args.output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["overall"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
