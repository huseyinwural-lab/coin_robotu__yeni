#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ARTIFACT_LOG="${APP_ROOT}/artifacts/faz0_persistence_restart.log"
mkdir -p "${APP_ROOT}/artifacts"
: > "$ARTIFACT_LOG"

log() {
  local line="$1"
  echo "$line" | tee -a "$ARTIFACT_LOG" >/dev/null
}

load_env() {
  if [[ -f "${APP_ROOT}/backend/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${APP_ROOT}/backend/.env"
    set +a
  fi
}

read_backend_url() {
  local fe_env="${APP_ROOT}/frontend/.env"
  if [[ ! -f "$fe_env" ]]; then
    return 1
  fi

  python - <<'PY'
from pathlib import Path

env_path = Path('/app/frontend/.env')
for raw in env_path.read_text(encoding='utf-8').splitlines():
    line = raw.strip()
    if not line or line.startswith('#'):
        continue
    if line.startswith('REACT_APP_BACKEND_URL='):
        print(line.split('=', 1)[1].strip().strip('"').strip("'"))
        break
PY
}

json_get() {
  local raw_json="$1"
  local expr="$2"
  RAW_JSON="$raw_json" EXPR="$expr" python - <<'PY'
import json
import os

raw = str(os.environ.get('RAW_JSON') or '').strip()
if not raw:
    print("")
    raise SystemExit(0)

try:
    payload = json.loads(raw)
except json.JSONDecodeError:
    print("")
    raise SystemExit(0)

expr = os.environ['EXPR']
parts = [p for p in expr.split('.') if p]
current = payload
for part in parts:
    if isinstance(current, dict):
        current = current.get(part)
    else:
        current = None
        break
if current is None:
    print("")
else:
    print(current)
PY
}

load_env

BACKEND_URL="$(read_backend_url)"
if [[ -z "${BACKEND_URL:-}" ]]; then
  log "FAIL backend_url_missing"
  exit 1
fi

if [[ -z "${DEFAULT_ADMIN_EMAIL:-}" || -z "${DEFAULT_ADMIN_PASSWORD:-}" ]]; then
  log "FAIL admin_env_missing"
  exit 1
fi

unique_app_name="faz0-persist-$(date +%s)"
log "INSERT_START app_name=${unique_app_name}"

login_response="$(curl -sS -X POST "${BACKEND_URL}/api/auth/login/admin" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${DEFAULT_ADMIN_EMAIL}\",\"password\":\"${DEFAULT_ADMIN_PASSWORD}\"}")"
token="$(json_get "$login_response" "access_token")"
if [[ -z "$token" ]]; then
  log "FAIL admin_login_failed"
  exit 1
fi

update_payload="{\"app_name\":\"${unique_app_name}\"}"
update_response="$(curl -sS -X PUT "${BACKEND_URL}/api/admin/brand-settings" \
  -H "Authorization: Bearer ${token}" \
  -H "Content-Type: application/json" \
  -d "$update_payload")"
updated_name="$(json_get "$update_response" "app_name")"
if [[ "$updated_name" != "$unique_app_name" ]]; then
  log "FAIL insert_response_mismatch value=${updated_name}"
  exit 1
fi
log "INSERT_OK app_name=${unique_app_name}"

before_read="$(curl -sS "${BACKEND_URL}/api/branding/settings")"
before_name="$(json_get "$before_read" "app_name")"
if [[ "$before_name" != "$unique_app_name" ]]; then
  log "FAIL before_restart_read_mismatch value=${before_name}"
  exit 1
fi
log "PRE_RESTART_READ_OK app_name=${before_name}"

sudo supervisorctl restart backend >/dev/null
log "RESTART_OK backend"

health_ok=0
for _ in {1..40}; do
  health_raw="$(curl -sS "${BACKEND_URL}/api/health" || true)"
  health_status="$(json_get "$health_raw" "status")"
  if [[ "$health_status" == "ok" ]]; then
    health_ok=1
    break
  fi
  sleep 1
done

if [[ "$health_ok" != "1" ]]; then
  log "FAIL backend_health_timeout"
  exit 1
fi

after_read="$(curl -sS "${BACKEND_URL}/api/branding/settings")"
after_name="$(json_get "$after_read" "app_name")"
if [[ "$after_name" != "$unique_app_name" ]]; then
  log "FAIL post_restart_read_mismatch value=${after_name}"
  exit 1
fi

log "POST_RESTART_READ_OK app_name=${after_name}"
log "PERSISTENCE_RESULT PASS"
