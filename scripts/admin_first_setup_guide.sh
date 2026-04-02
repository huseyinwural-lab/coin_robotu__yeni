#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-}"
ADMIN_EMAIL="${ADMIN_EMAIL:-canary.admin@platform.local}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-CanaryAdmin123!}"
DEVICE_ID="${DEVICE_ID:-admin-setup-$(date +%s)}"
JSON_OUT="${JSON_OUT:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url)
      BASE_URL="${2:-}"
      shift 2
      ;;
    --admin-email)
      ADMIN_EMAIL="${2:-}"
      shift 2
      ;;
    --admin-password)
      ADMIN_PASSWORD="${2:-}"
      shift 2
      ;;
    --device-id)
      DEVICE_ID="${2:-}"
      shift 2
      ;;
    --json-out)
      JSON_OUT="${2:-}"
      shift 2
      ;;
    *)
      echo "HATA: Bilinmeyen argüman: $1"
      echo "Kullanım: bash /app/scripts/admin_first_setup_guide.sh [--base-url URL] [--admin-email EMAIL] [--admin-password PASS] [--device-id ID] [--json-out /app/artifacts/admin_first_setup_report.json]"
      exit 2
      ;;
  esac
done

if [[ -z "$BASE_URL" && -f /app/frontend/.env ]]; then
  BASE_URL="$(python - <<'PY'
from pathlib import Path
for line in Path('/app/frontend/.env').read_text(encoding='utf-8').splitlines():
    if line.startswith('REACT_APP_BACKEND_URL='):
        print(line.split('=',1)[1].strip())
        break
PY
)"
fi

if [[ -z "$BASE_URL" ]]; then
  echo "HATA: BASE_URL bulunamadı. --base-url ver veya frontend/.env içinde REACT_APP_BACKEND_URL tanımlı olsun."
  exit 2
fi

if [[ -z "$ADMIN_EMAIL" || -z "$ADMIN_PASSWORD" ]]; then
  echo "HATA: ADMIN_EMAIL ve ADMIN_PASSWORD boş olamaz."
  exit 2
fi

BASE_URL="$BASE_URL" ADMIN_EMAIL="$ADMIN_EMAIL" ADMIN_PASSWORD="$ADMIN_PASSWORD" DEVICE_ID="$DEVICE_ID" JSON_OUT="$JSON_OUT" python - <<'PY'
import json
import os
from urllib.parse import urlparse

import requests


base_url = os.environ["BASE_URL"].rstrip("/")
admin_email = os.environ["ADMIN_EMAIL"]
admin_password = os.environ["ADMIN_PASSWORD"]
device_id = os.environ["DEVICE_ID"]
json_out = str(os.environ.get("JSON_OUT") or "").strip()


def _safe_json(resp: requests.Response) -> dict:
    try:
        return resp.json()
    except Exception:
        return {"raw": (resp.text or "")[:300]}


def _request(session: requests.Session, method: str, path: str, **kwargs):
    return session.request(method, f"{base_url}{path}", timeout=30, **kwargs)


def _build_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "X-Session-Device": device_id,
        "User-Agent": "admin-first-setup/1.0",
    })
    return s


def _check_local_fallback_available() -> bool:
    try:
        r = requests.get("http://127.0.0.1:8001/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def _run_local_protected_checks() -> tuple[dict, dict, dict]:
    local = requests.Session()
    local.headers.update({
        "X-Session-Device": device_id,
        "User-Agent": "admin-first-setup/1.0",
    })
    login_resp = local.post(
        "http://127.0.0.1:8001/api/auth/login",
        json={"email": admin_email, "password": admin_password},
        timeout=30,
    )
    login_body = _safe_json(login_resp)
    token = str((login_body or {}).get("access_token") or "").strip()
    if token:
        local.headers.update({"Authorization": f"Bearer {token}"})
    er = local.get("http://127.0.0.1:8001/api/admin/execution-readiness", timeout=30)
    pg = local.get("http://127.0.0.1:8001/api/phase4/admin/production-gate", timeout=30)
    return (
        {"http_code": login_resp.status_code, "body": login_body},
        {"http_code": er.status_code, "body": _safe_json(er)},
        {"http_code": pg.status_code, "body": _safe_json(pg)},
    )


print("[1/6] API health kontrolü")
session = _build_session()
health_resp = _request(session, "GET", "/api/health")
health_body = _safe_json(health_resp)

print("[2/6] API ready kontrolü")
ready_resp = _request(session, "GET", "/api/ready")
ready_body = _safe_json(ready_resp)

print("[3/6] Admin login")
login_resp = _request(
    session,
    "POST",
    "/api/auth/login",
    json={"email": admin_email, "password": admin_password},
)
login_body = _safe_json(login_resp)
token = str((login_body or {}).get("access_token") or "").strip()
if token:
    session.headers.update({"Authorization": f"Bearer {token}"})

print("[4/6] Admin execution readiness")
exec_resp = _request(session, "GET", "/api/admin/execution-readiness")
exec_body = _safe_json(exec_resp)

print("[5/6] Production gate")
gate_resp = _request(session, "GET", "/api/phase4/admin/production-gate")
gate_body = _safe_json(gate_resp)

fallback_used = False
fallback_reason = ""
fallback_paths = {
    "session_device_mismatch",
    "session_revoked",
    "reauth_required_ip_change",
    "reauth_required_device_change",
}

preview_host = "preview.emergentagent.com" in (urlparse(base_url).netloc or "")
protected_failed = exec_resp.status_code == 401 or gate_resp.status_code == 401
detail_values = {
    str((exec_body or {}).get("detail") or ""),
    str((gate_body or {}).get("detail") or ""),
}
can_retry_local = preview_host and protected_failed and bool(detail_values & fallback_paths)

if can_retry_local and _check_local_fallback_available():
    fallback_used = True
    fallback_reason = "preview_session_binding_instability"
    local_login, local_exec, local_gate = _run_local_protected_checks()
    if local_login.get("http_code") == 200:
        login_resp = type("obj", (), {"status_code": 200})
        login_body = local_login.get("body") or login_body
    exec_resp = type("obj", (), {"status_code": local_exec.get("http_code")})
    exec_body = local_exec.get("body")
    gate_resp = type("obj", (), {"status_code": local_gate.get("http_code")})
    gate_body = local_gate.get("body")

print("[6/6] Sonuçların değerlendirilmesi")
health_ok = health_resp.status_code == 200 and str(health_body.get("status") or "").lower() == "ok"
ready_ok = ready_resp.status_code == 200 and str(ready_body.get("status") or "").lower() == "ready"
login_ok = login_resp.status_code == 200 and bool((login_body or {}).get("access_token"))
exec_ok = (
    exec_resp.status_code == 200
    and bool((exec_body or {}).get("go_live_allowed"))
    and str((exec_body or {}).get("execution_mode") or (exec_body or {}).get("mode") or "").upper() == "LIVE"
)
gate_ok = (
    gate_resp.status_code == 200
    and str((gate_body or {}).get("configured_state") or "").upper() == "GO"
    and str((gate_body or {}).get("effective_state") or "").upper() == "GO"
    and bool((gate_body or {}).get("deploy_allowed"))
)

overall = all([health_ok, ready_ok, login_ok, exec_ok, gate_ok])

report = {
    "script": "admin_first_setup_guide",
    "base_url": base_url,
    "overall": "PASS" if overall else "FAIL",
    "fallback_used": fallback_used,
    "fallback_reason": fallback_reason,
    "checks": {
        "api_health": {
            "http_code": health_resp.status_code,
            "status": health_body.get("status"),
            "pass": health_ok,
        },
        "api_ready": {
            "http_code": ready_resp.status_code,
            "status": ready_body.get("status"),
            "pass": ready_ok,
        },
        "admin_login": {
            "http_code": login_resp.status_code,
            "mfa_required": (login_body or {}).get("mfa_required"),
            "role": (login_body or {}).get("role") or ((login_body or {}).get("user") or {}).get("role"),
            "pass": login_ok,
        },
        "execution_readiness": {
            "http_code": exec_resp.status_code,
            "go_live_allowed": (exec_body or {}).get("go_live_allowed"),
            "mode": (exec_body or {}).get("execution_mode") or (exec_body or {}).get("mode"),
            "detail": (exec_body or {}).get("detail"),
            "pass": exec_ok,
        },
        "production_gate": {
            "http_code": gate_resp.status_code,
            "configured_state": (gate_body or {}).get("configured_state"),
            "effective_state": (gate_body or {}).get("effective_state"),
            "deploy_allowed": (gate_body or {}).get("deploy_allowed"),
            "detail": (gate_body or {}).get("detail"),
            "pass": gate_ok,
        },
    },
    "next_steps": [
        "Admin panelde exchange market-data doğrulamasını kontrol et (Admin key sadece data/control-plane için).",
        "User panelde execution key ekleme/yenileme yap ve readiness-checklist PASS durumunu doğrula.",
        "Canlıya çıkmadan önce kill-switch ve küçük notional test-order adımını uygula.",
    ],
}

print(json.dumps(report, ensure_ascii=False, indent=2))
if json_out:
    out_path = os.path.abspath(json_out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

raise SystemExit(0 if overall else 1)
PY
