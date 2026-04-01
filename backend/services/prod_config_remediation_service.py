import json
import os
import re
import subprocess
from pathlib import Path

from sqlalchemy.orm import Session

from core.users.user_exchange_connector import decrypt_exchange_secret, encrypt_exchange_secret
from db import redis_client
from services.live_mode_service import enforce_release_gate

ROOT_DIR = Path("/app")
BACKEND_ENV_PATH = ROOT_DIR / "backend" / ".env"
FRONTEND_ENV_PATH = ROOT_DIR / "frontend" / ".env"

OVERRIDES_REDIS_KEY = "prod_config:remediation:overrides:v1"

REQUEST_TO_ENV_KEY = {
    "database_url": "DATABASE_URL",
    "redis_url": "REDIS_URL",
    "jwt_secret": "JWT_SECRET",
    "exchange_credentials_encryption_key": "EXCHANGE_CREDENTIALS_ENCRYPTION_KEY",
    "admin_bootstrap_email": "ADMIN_BOOTSTRAP_EMAIL",
    "admin_bootstrap_password": "ADMIN_BOOTSTRAP_PASSWORD",
    "react_app_backend_url": "REACT_APP_BACKEND_URL",
    "resend_api_key": "RESEND_API_KEY",
    "alert_from": "ALERT_FROM",
    "alert_to": "ALERT_TO",
}

TRACKED_FIELDS = [
    "DATABASE_URL",
    "REDIS_URL",
    "JWT_SECRET",
    "EXCHANGE_CREDENTIALS_ENCRYPTION_KEY",
    "ADMIN_BOOTSTRAP_EMAIL",
    "ADMIN_BOOTSTRAP_PASSWORD",
    "REACT_APP_BACKEND_URL",
    "RESEND_API_KEY",
    "ALERT_FROM",
    "ALERT_TO",
]

LOCALHOST_PATTERN = re.compile(r"(localhost|127\.0\.0\.1|0\.0\.0\.0|::1)", re.IGNORECASE)
HTTPS_URL_PATTERN = re.compile(r"^https://", re.IGNORECASE)
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SCRIPT_PLAN = [
    {
        "check_name": "prod_env_resolution",
        "script": ROOT_DIR / "scripts" / "prod_env_resolution_report.sh",
        "artifact": ROOT_DIR / "artifacts" / "prod_env_resolution_report.json",
        "status_key": "status",
    },
    {
        "check_name": "secret_readiness",
        "script": ROOT_DIR / "scripts" / "prod_secret_readiness_check.sh",
        "artifact": ROOT_DIR / "artifacts" / "prod_secret_readiness_report.json",
        "status_key": "status",
    },
    {
        "check_name": "prod_env_preflight",
        "script": ROOT_DIR / "scripts" / "preflight_prod_env_check.sh",
        "artifact": ROOT_DIR / "artifacts" / "prod_preflight_check.json",
        "status_key": "status",
    },
    {
        "check_name": "final_release_gate",
        "script": ROOT_DIR / "scripts" / "final_release_gate_report.sh",
        "artifact": ROOT_DIR / "artifacts" / "final_release_gate_report.json",
        "status_key": "final_decision",
    },
]

PREFLIGHT_CHECK_TO_ENV = {
    "DATABASE_URL non-localhost": "DATABASE_URL",
    "REDIS_URL non-localhost": "REDIS_URL",
    "JWT_SECRET strong enough": "JWT_SECRET",
    "REACT_APP_BACKEND_URL production format": "REACT_APP_BACKEND_URL",
}

REMEDIATION_CATALOG = {
    "database_url_non_localhost": {
        "title": "DATABASE_URL production endpoint olmalı",
        "target_field": "DATABASE_URL",
    },
    "redis_url_non_localhost": {
        "title": "REDIS_URL production endpoint olmalı",
        "target_field": "REDIS_URL",
    },
    "admin_bootstrap_email_missing": {
        "title": "ADMIN_BOOTSTRAP_EMAIL gerekli",
        "target_field": "ADMIN_BOOTSTRAP_EMAIL",
    },
    "admin_bootstrap_password_missing": {
        "title": "ADMIN_BOOTSTRAP_PASSWORD gerekli",
        "target_field": "ADMIN_BOOTSTRAP_PASSWORD",
    },
    "jwt_secret_invalid": {
        "title": "JWT_SECRET güvenlik kuralına uymalı",
        "target_field": "JWT_SECRET",
    },
    "react_app_backend_url_invalid": {
        "title": "REACT_APP_BACKEND_URL production formatında olmalı",
        "target_field": "REACT_APP_BACKEND_URL",
    },
    "prod_env_preflight_fail": {
        "title": "Prod env preflight FAIL",
        "target_field": None,
    },
    "prod_secret_readiness_fail": {
        "title": "Secret readiness FAIL",
        "target_field": None,
    },
    "final_release_gate_no_go": {
        "title": "Final release gate NO_GO",
        "target_field": None,
    },
}


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw = stripped.split("=", 1)
        values[key.strip()] = raw.strip().strip('"').strip("'")
    return values


def _mask_value(key: str, value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return "missing"

    if key.endswith("_URL") and "://" in normalized and "@" in normalized:
        scheme, rest = normalized.split("://", 1)
        _, host = rest.rsplit("@", 1)
        return f"{scheme}://***@{host}"

    if key.endswith("_EMAIL") and "@" in normalized:
        local_part, domain = normalized.split("@", 1)
        if len(local_part) <= 2:
            return f"***@{domain}"
        return f"{local_part[:2]}***@{domain}"

    if len(normalized) <= 8:
        return "***"
    return f"{normalized[:4]}***{normalized[-3:]}"


def _to_plain_text(encrypted_or_plain: str) -> str:
    if not encrypted_or_plain:
        return ""
    if encrypted_or_plain.startswith("aesgcm:v1:"):
        return decrypt_exchange_secret(encrypted_or_plain)
    return encrypted_or_plain


def load_saved_overrides() -> dict[str, str]:
    raw = redis_client.get(OVERRIDES_REDIS_KEY)
    if not raw:
        return {}
    try:
        payload = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
    except Exception:
        return {}

    resolved: dict[str, str] = {}
    for key, encrypted_value in payload.items():
        plain = _to_plain_text(str(encrypted_value or ""))
        if plain:
            resolved[str(key)] = plain
    return resolved


def _save_overrides_payload(overrides: dict[str, str]) -> None:
    encrypted_payload = {
        key: encrypt_exchange_secret(value)
        for key, value in overrides.items()
        if str(value or "").strip()
    }
    redis_client.set(OVERRIDES_REDIS_KEY, json.dumps(encrypted_payload, ensure_ascii=False))


def build_runtime_env(overrides: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    active_overrides = overrides if overrides is not None else load_saved_overrides()
    for key, value in active_overrides.items():
        if str(value or "").strip():
            env[key] = str(value).strip()
    return env


def validate_prod_config_updates(payload: dict) -> tuple[dict[str, str], dict[str, str]]:
    updates: dict[str, str] = {}
    validation_errors: dict[str, str] = {}

    for request_key, env_key in REQUEST_TO_ENV_KEY.items():
        raw_value = payload.get(request_key)
        if raw_value is None:
            continue
        value = str(raw_value).strip()
        if not value:
            continue

        if env_key in {"DATABASE_URL", "REDIS_URL"} and LOCALHOST_PATTERN.search(value):
            validation_errors[request_key] = "localhost/127.0.0.1/0.0.0.0 kabul edilmez"
            continue

        if env_key == "JWT_SECRET" and len(value) < 32:
            validation_errors[request_key] = "en az 32 karakter olmalı"
            continue

        if env_key == "ADMIN_BOOTSTRAP_EMAIL" and not EMAIL_PATTERN.match(value):
            validation_errors[request_key] = "geçerli bir e-posta girin"
            continue

        if env_key == "ADMIN_BOOTSTRAP_PASSWORD" and len(value) < 10:
            validation_errors[request_key] = "en az 10 karakter olmalı"
            continue

        if env_key == "REACT_APP_BACKEND_URL":
            if not HTTPS_URL_PATTERN.match(value) or LOCALHOST_PATTERN.search(value):
                validation_errors[request_key] = "https:// ile başlamalı ve localhost içermemeli"
                continue

        updates[env_key] = value

    return updates, validation_errors


def save_prod_config_updates(updates: dict[str, str]) -> tuple[list[str], dict[str, str]]:
    existing = load_saved_overrides()
    merged = dict(existing)
    changed_keys: list[str] = []

    for key, value in updates.items():
        if merged.get(key) != value:
            changed_keys.append(key)
        merged[key] = value
        os.environ[key] = value

    if updates:
        _save_overrides_payload(merged)
    return sorted(set(changed_keys)), merged


def build_masked_update_preview(updates: dict[str, str]) -> dict[str, str]:
    return {key: _mask_value(key, value) for key, value in updates.items()}


def _run_script(script_path: Path, env: dict[str, str]) -> int:
    completed = subprocess.run(
        ["bash", str(script_path)],
        cwd=str(ROOT_DIR),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return int(completed.returncode)


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _status_to_contract(status: str) -> str:
    normalized = str(status or "").strip().upper()
    if normalized in {"PASS", "GO"}:
        return "PASS"
    if not normalized:
        return "UNKNOWN"
    return "FAIL"


def _resolve_value_with_source(
    env_key: str,
    *,
    overrides: dict[str, str],
    process_env: dict[str, str],
    backend_env: dict[str, str],
    frontend_env: dict[str, str],
) -> tuple[str, str]:
    if overrides.get(env_key):
        return overrides[env_key], "runtime_override"
    if process_env.get(env_key):
        return str(process_env[env_key]).strip(), "process_env"
    if backend_env.get(env_key):
        return backend_env[env_key], "backend/.env"
    if frontend_env.get(env_key):
        return frontend_env[env_key], "frontend/.env"
    return "", "missing"


def _compose_field_validation_errors(preflight_payload: dict, secret_payload: dict) -> dict[str, str]:
    errors: dict[str, str] = {}

    for check in preflight_payload.get("checks", []):
        if str(check.get("status") or "").upper() != "FAIL":
            continue
        mapped_field = PREFLIGHT_CHECK_TO_ENV.get(str(check.get("name") or ""))
        if mapped_field:
            errors[mapped_field] = str(check.get("detail") or "validation_failed")

    for row in secret_payload.get("required_secret_checks", []):
        if str(row.get("status") or "").upper() != "FAIL":
            continue
        key = str(row.get("key") or "").strip()
        if key:
            errors[key] = "zorunlu secret eksik"

    return errors


def _build_reason_codes(preflight_payload: dict, secret_payload: dict, final_payload: dict, gate_payload: dict) -> list[str]:
    reason_codes: list[str] = []

    preflight_status = str(preflight_payload.get("status") or "").upper()
    secret_status = str(secret_payload.get("status") or "").upper()
    final_decision = str(final_payload.get("final_decision") or "").upper()

    if preflight_status != "PASS":
        reason_codes.append("prod_env_preflight_fail")
    if secret_status != "PASS":
        reason_codes.append("prod_secret_readiness_fail")
    if final_decision != "GO":
        reason_codes.append("final_release_gate_no_go")

    for check in preflight_payload.get("checks", []):
        if str(check.get("status") or "").upper() != "FAIL":
            continue
        name = str(check.get("name") or "")
        if name == "DATABASE_URL non-localhost":
            reason_codes.append("database_url_non_localhost")
        elif name == "REDIS_URL non-localhost":
            reason_codes.append("redis_url_non_localhost")
        elif name == "JWT_SECRET strong enough":
            reason_codes.append("jwt_secret_invalid")
        elif name == "REACT_APP_BACKEND_URL production format":
            reason_codes.append("react_app_backend_url_invalid")

    for row in secret_payload.get("required_secret_checks", []):
        if str(row.get("status") or "").upper() != "FAIL":
            continue
        key = str(row.get("key") or "").strip().upper()
        if key == "ADMIN_BOOTSTRAP_EMAIL":
            reason_codes.append("admin_bootstrap_email_missing")
        elif key == "ADMIN_BOOTSTRAP_PASSWORD":
            reason_codes.append("admin_bootstrap_password_missing")
        else:
            reason_codes.append(f"{key.lower()}_missing")

    reason_codes.extend(list(gate_payload.get("reason_codes") or []))
    return list(dict.fromkeys([code for code in reason_codes if str(code).strip()]))


def _build_remediation_items(reason_codes: list[str]) -> list[dict]:
    items: list[dict] = []
    for code in reason_codes:
        catalog = REMEDIATION_CATALOG.get(code)
        title = catalog["title"] if catalog else f"{code} düzeltmesi gerekli"
        target_field = catalog["target_field"] if catalog else None
        items.append(
            {
                "code": code,
                "title": title,
                "current_state": "BLOCKED",
                "expected_state": "PASS",
                "target_field": target_field,
                "check_action": "save_and_revalidate",
            }
        )
    return items


def build_prod_config_remediation_state(db: Session) -> dict:
    overrides = load_saved_overrides()
    runtime_env = build_runtime_env(overrides)

    check_results: list[dict] = []
    for item in SCRIPT_PLAN:
        _run_script(item["script"], runtime_env)
        payload = _read_json(item["artifact"])
        status_key = item["status_key"]
        raw_status = str(payload.get(status_key) or "UNKNOWN")
        normalized_status = _status_to_contract(raw_status)
        if item["check_name"] == "final_release_gate" and raw_status.upper() == "NO_GO":
            normalized_status = "FAIL"
        check_results.append(
            {
                "check_name": item["check_name"],
                "status": normalized_status,
                "artifact_path": str(item["artifact"]),
                "detail": f"raw_status={raw_status}",
            }
        )

    preflight_payload = _read_json(ROOT_DIR / "artifacts" / "prod_preflight_check.json")
    secret_payload = _read_json(ROOT_DIR / "artifacts" / "prod_secret_readiness_report.json")
    final_payload = _read_json(ROOT_DIR / "artifacts" / "final_release_gate_report.json")

    try:
        gate_payload = enforce_release_gate(db, environment="prod")
    except Exception:
        db.rollback()
        gate_payload = {
            "status": "BLOCKED",
            "reason_codes": ["release_gate_runtime_error"],
            "deploy_enable_flag": False,
        }

    preflight_status = str(preflight_payload.get("status") or "UNKNOWN").upper()
    secret_status = str(secret_payload.get("status") or "UNKNOWN").upper()
    final_decision = str(final_payload.get("final_decision") or "UNKNOWN").upper()

    release_gate_status = "PASS"
    if final_decision != "GO" or str(gate_payload.get("status") or "").upper() == "BLOCKED":
        release_gate_status = "BLOCKED"

    reason_codes = _build_reason_codes(preflight_payload, secret_payload, final_payload, gate_payload)
    field_errors = _compose_field_validation_errors(preflight_payload, secret_payload)

    backend_env = _parse_env_file(BACKEND_ENV_PATH)
    frontend_env = _parse_env_file(FRONTEND_ENV_PATH)
    process_env = {key: str(value) for key, value in os.environ.items()}

    fields: list[dict] = []
    for env_key in TRACKED_FIELDS:
        value, source = _resolve_value_with_source(
            env_key,
            overrides=overrides,
            process_env=process_env,
            backend_env=backend_env,
            frontend_env=frontend_env,
        )
        fields.append(
            {
                "key": env_key,
                "source": source,
                "present": bool(value),
                "editable": True,
                "masked_value": _mask_value(env_key, value),
                "validation_error": field_errors.get(env_key),
            }
        )

    return {
        "release_gate_status": release_gate_status,
        "release_gate_reason_codes": reason_codes,
        "deploy_enable_allowed": release_gate_status == "PASS" and bool(gate_payload.get("deploy_enable_flag")),
        "remediation_allowed": release_gate_status != "PASS",
        "fields": fields,
        "remediation_items": _build_remediation_items(reason_codes),
        "preflight_status": preflight_status,
        "secret_readiness_status": secret_status,
        "final_release_gate_decision": final_decision,
        "checks": check_results,
    }


def remediation_summary_for_audit(state: dict) -> dict:
    return {
        "release_gate_status": state.get("release_gate_status"),
        "release_gate_reason_codes": state.get("release_gate_reason_codes", []),
        "preflight_status": state.get("preflight_status"),
        "secret_readiness_status": state.get("secret_readiness_status"),
        "final_release_gate_decision": state.get("final_release_gate_decision"),
        "deploy_enable_allowed": bool(state.get("deploy_enable_allowed")),
    }
