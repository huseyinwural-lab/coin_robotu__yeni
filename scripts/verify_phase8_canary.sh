#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="${ROOT_DIR}/artifacts"
LOG_FILE="${ARTIFACT_DIR}/faz8_canary_run.log"
SUMMARY_JSON="${ARTIFACT_DIR}/faz8_canary_summary.json"
METRICS_JSON="${ARTIFACT_DIR}/faz8_metrics_snapshot.json"

mkdir -p "${ARTIFACT_DIR}"
: > "${LOG_FILE}"

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" | tee -a "${LOG_FILE}"
}

fail() {
  log "FAIL: $1"
  exit 1
}

BASE_URL="${REACT_APP_BACKEND_URL:-}"
if [[ -z "${BASE_URL}" && -f "${ROOT_DIR}/frontend/.env" ]]; then
  BASE_URL="$(grep -E '^REACT_APP_BACKEND_URL=' "${ROOT_DIR}/frontend/.env" | head -n1 | cut -d'=' -f2- || true)"
fi
[[ -n "${BASE_URL}" ]] || fail "REACT_APP_BACKEND_URL bulunamadı"

ADMIN_EMAIL="${TEST_ADMIN_EMAIL:-admin@platform.local}"
ADMIN_PASSWORD="${TEST_ADMIN_PASSWORD:-Admin12345!}"
USER_EMAIL="${CANARY_TEST_USER_EMAIL:-canary_$(date +%s)@example.com}"
USER_PASSWORD="${CANARY_TEST_USER_PASSWORD:-CanaryPass123!}"
TESTNET_API_KEY="${BINANCE_TESTNET_API_KEY:-}"
TESTNET_API_SECRET="${BINANCE_TESTNET_API_SECRET:-}"

[[ -n "${TESTNET_API_KEY}" && -n "${TESTNET_API_SECRET}" ]] || fail "Gerçek execution için BINANCE_TESTNET_API_KEY/SECRET zorunlu"

RUN_SECONDS=$((60 * 60))
INTERVAL_SECONDS="${CANARY_LOOP_INTERVAL_SECONDS:-300}"
if [[ "${INTERVAL_SECONDS}" -lt 30 ]]; then
  INTERVAL_SECONDS=30
fi

log "FAZ-8 canary verify başladı"
log "BASE_URL=${BASE_URL}"
log "RUN_SECONDS=${RUN_SECONDS} INTERVAL_SECONDS=${INTERVAL_SECONDS}"

extract_token() {
  local body_path="$1"
  python - <<PY
import json
data=json.load(open("${body_path}", encoding="utf-8"))
print(((data.get("access_token") or "").strip()))
PY
}

request_json() {
  local method="$1"
  local url="$2"
  local body="$3"
  local token="${4:-}"
  local out="$5"
  local headers=(-H "Content-Type: application/json")
  if [[ -n "${token}" ]]; then
    headers+=(-H "Authorization: Bearer ${token}")
  fi
  if [[ "${method}" == "GET" ]]; then
    curl -sS -o "${out}" -w '%{http_code}' "${headers[@]}" "${url}"
  else
    curl -sS -o "${out}" -w '%{http_code}' -X "${method}" "${headers[@]}" -d "${body}" "${url}"
  fi
}

login_admin() {
  local code
  code="$(request_json POST "${BASE_URL}/api/auth/login/admin" "{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PASSWORD}\"}" "" "/tmp/faz8_admin_login.json")"
  [[ "${code}" == "200" ]] || fail "Admin login başarısız http=${code}"
  ADMIN_TOKEN="$(extract_token /tmp/faz8_admin_login.json)"
  [[ -n "${ADMIN_TOKEN}" ]] || fail "Admin token alınamadı"
  log "PASS: admin login"
}

ensure_user_login() {
  local login_code
  login_code="$(request_json POST "${BASE_URL}/api/auth/login/user" "{\"email\":\"${USER_EMAIL}\",\"password\":\"${USER_PASSWORD}\"}" "" "/tmp/faz8_user_login.json")"
  if [[ "${login_code}" != "200" ]]; then
    local reg_code
    reg_code="$(request_json POST "${BASE_URL}/api/auth/register" "{\"email\":\"${USER_EMAIL}\",\"password\":\"${USER_PASSWORD}\",\"first_name\":\"Canary\",\"last_name\":\"Runner\"}" "" "/tmp/faz8_user_register.json")"
    [[ "${reg_code}" == "200" ]] || fail "User register başarısız http=${reg_code}"
    # admin approval required
    local pending_code
    pending_code="$(request_json GET "${BASE_URL}/api/auth/admin/user-approval-requests" "" "${ADMIN_TOKEN}" "/tmp/faz8_pending_users.json")"
    [[ "${pending_code}" == "200" ]] || fail "pending approvals alınamadı"
    USER_ID="$(python - <<PY
import json
rows=json.load(open('/tmp/faz8_pending_users.json', encoding='utf-8'))
target='${USER_EMAIL}'.lower()
row=next((r for r in rows if str(r.get('email','')).lower()==target), None)
print((row or {}).get('id',''))
PY
)"
    [[ -n "${USER_ID}" ]] || fail "Yeni kullanıcı pending listede bulunamadı"
    local approve_code
    approve_code="$(request_json POST "${BASE_URL}/api/auth/admin/user-approval-requests/${USER_ID}/approve" "{}" "${ADMIN_TOKEN}" "/tmp/faz8_user_approve.json")"
    [[ "${approve_code}" == "200" ]] || fail "User approval başarısız http=${approve_code}"
    login_code="$(request_json POST "${BASE_URL}/api/auth/login/user" "{\"email\":\"${USER_EMAIL}\",\"password\":\"${USER_PASSWORD}\"}" "" "/tmp/faz8_user_login.json")"
    [[ "${login_code}" == "200" ]] || fail "User login (approval sonrası) başarısız http=${login_code}"
  fi
  USER_TOKEN="$(extract_token /tmp/faz8_user_login.json)"
  [[ -n "${USER_TOKEN}" ]] || fail "User token alınamadı"
  log "PASS: user login"
}

set_exchange_keys() {
  local payload
  payload="{\"exchange\":\"binance\",\"mode\":\"futures_testnet\",\"api_key\":\"${TESTNET_API_KEY}\",\"api_secret\":\"${TESTNET_API_SECRET}\"}"
  local code
  code="$(request_json PUT "${BASE_URL}/api/phase4/exchange-settings" "${payload}" "${USER_TOKEN}" "/tmp/faz8_exchange_settings.json")"
  [[ "${code}" == "200" ]] || fail "Exchange settings update başarısız http=${code}"
  log "PASS: exchange settings güncellendi"
}

load_live_config() {
  local code
  code="$(request_json GET "${BASE_URL}/api/phase4/live-config" "" "${ADMIN_TOKEN}" "/tmp/faz8_live_config_get.json")"
  [[ "${code}" == "200" ]] || fail "live-config okunamadı http=${code}"
}

update_live_config_canary() {
  local symbols_json="$1"
  local max_capital="$2"
  local max_positions="$3"
  local symbol_whitelist_json="$4"

  python - <<PY
import json
cfg=json.load(open('/tmp/faz8_live_config_get.json', encoding='utf-8'))
cfg.update({
  'canary_enabled': True,
  'canary_symbols': json.loads('${symbols_json}'),
  'canary_max_capital_usdt': float('${max_capital}'),
  'canary_max_positions': int('${max_positions}'),
  'symbol_whitelist': json.loads('${symbol_whitelist_json}'),
  'trading_enabled': True,
  'kill_switch_enabled': False,
})
open('/tmp/faz8_live_config_put.json','w',encoding='utf-8').write(json.dumps(cfg))
PY
  local payload code
  payload="$(cat /tmp/faz8_live_config_put.json)"
  code="$(request_json PUT "${BASE_URL}/api/phase4/live-config" "${payload}" "${ADMIN_TOKEN}" "/tmp/faz8_live_config_updated.json")"
  [[ "${code}" == "200" ]] || fail "live-config update başarısız http=${code}"
  log "PASS: canary config güncellendi symbols=${symbols_json} cap=${max_capital} max_pos=${max_positions}"
}

test_order_expect() {
  local expected_mode="$1" # success or reject
  local expected_reason="${2:-}"
  local code
  code="$(request_json POST "${BASE_URL}/api/phase4/test-order" "{}" "${USER_TOKEN}" "/tmp/faz8_test_order_resp.json")"
  if [[ "${expected_mode}" == "success" ]]; then
    [[ "${code}" == "200" ]] || fail "Test order success bekleniyordu, http=${code}"
    log "PASS: real test-order success"
    return
  fi

  [[ "${code}" == "400" || "${code}" == "422" || "${code}" == "403" ]] || fail "Test order reject bekleniyordu, http=${code}"
  if [[ -n "${expected_reason}" ]]; then
    python - <<PY
import json,sys
body=json.load(open('/tmp/faz8_test_order_resp.json', encoding='utf-8'))
text=str(body)
expected='${expected_reason}'
if expected not in text:
    raise SystemExit(f"Expected reject reason not found: {expected} body={text}")
print('REJECT_REASON_OK', expected)
PY
  fi
  log "PASS: test-order reject (${expected_reason})"
}

fetch_canary_status() {
  local code
  code="$(request_json GET "${BASE_URL}/api/admin/canary-status" "" "${ADMIN_TOKEN}" "/tmp/faz8_canary_status.json")"
  [[ "${code}" == "200" ]] || fail "canary-status başarısız http=${code}"
  log "PASS: /api/admin/canary-status"
}

log "T-8.1 canary config runtime"
login_admin
ensure_user_login
set_exchange_keys
load_live_config
update_live_config_canary '["BTCUSDT"]' '50' '1' '["BTCUSDT"]'
fetch_canary_status

log "T-8.2 execution enforce"
update_live_config_canary '["BTCUSDT"]' '50' '1' '["ETHUSDT"]'
test_order_expect reject "CANARY_SYMBOL_BLOCKED"

update_live_config_canary '["BTCUSDT"]' '1' '1' '["BTCUSDT"]'
test_order_expect reject "CANARY_CAPITAL_LIMIT_EXCEEDED"

update_live_config_canary '["BTCUSDT"]' '50' '0' '["BTCUSDT"]'
test_order_expect reject "CANARY_MAX_POSITIONS_EXCEEDED"

update_live_config_canary '["BTCUSDT"]' '50' '1' '["BTCUSDT"]'
test_order_expect success

log "T-8.4 monitoring metrikleri"
fetch_canary_status
cp /tmp/faz8_canary_status.json "${METRICS_JSON}"

log "T-8.6 gradual rollout"
update_live_config_canary '["BTCUSDT"]' '50' '1' '["BTCUSDT"]'
fetch_canary_status

update_live_config_canary '["BTCUSDT","ETHUSDT","BNBUSDT"]' '50' '1' '["BTCUSDT"]'
fetch_canary_status

update_live_config_canary '["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","ADAUSDT","SOLUSDT","DOGEUSDT","MATICUSDT","LTCUSDT","DOTUSDT"]' '50' '1' '["BTCUSDT"]'
fetch_canary_status

update_live_config_canary '[]' '50' '1' '["BTCUSDT"]'
fetch_canary_status

log "T-8.5 canary run (gerçek 60dk)"
RUN_START="$(date +%s)"
RUN_END="$((RUN_START + RUN_SECONDS))"
CRASH_COUNT=0
ERROR_5XX_COUNT=0
REJECT_COUNT=0
LOOP_COUNT=0

while [[ "$(date +%s)" -lt "${RUN_END}" ]]; do
  LOOP_COUNT="$((LOOP_COUNT + 1))"
  code="$(request_json POST "${BASE_URL}/api/phase4/test-order" "{}" "${USER_TOKEN}" "/tmp/faz8_loop_test_order.json" || true)"
  if [[ -z "${code}" || "${code}" == "000" ]]; then
    CRASH_COUNT="$((CRASH_COUNT + 1))"
    log "RUN_LOOP_${LOOP_COUNT}: crash/network"
  elif [[ "${code}" -ge 500 ]]; then
    ERROR_5XX_COUNT="$((ERROR_5XX_COUNT + 1))"
    log "RUN_LOOP_${LOOP_COUNT}: 5xx=${code}"
  elif [[ "${code}" -ge 400 ]]; then
    REJECT_COUNT="$((REJECT_COUNT + 1))"
    log "RUN_LOOP_${LOOP_COUNT}: reject=${code}"
  else
    log "RUN_LOOP_${LOOP_COUNT}: success=${code}"
  fi
  fetch_canary_status
  sleep "${INTERVAL_SECONDS}"
done

DURATION_MINUTES="$(( ( $(date +%s) - RUN_START ) / 60 ))"
if [[ "${DURATION_MINUTES}" -lt 60 ]]; then
  fail "canary run süresi 60dk altında (${DURATION_MINUTES})"
fi

log "T-8.7 kill switch entegrasyonu"
KS_OFF_CODE="$(request_json POST "${BASE_URL}/api/admin/kill-switch" '{"trading_enabled":false,"reason":"canary_kill_switch_test"}' "${ADMIN_TOKEN}" "/tmp/faz8_kill_switch_off.json")"
[[ "${KS_OFF_CODE}" == "200" ]] || fail "kill-switch OFF başarısız http=${KS_OFF_CODE}"
test_order_expect reject "TRADING_DISABLED"

KS_ON_CODE="$(request_json POST "${BASE_URL}/api/admin/kill-switch" '{"trading_enabled":true,"reason":"canary_resume"}' "${ADMIN_TOKEN}" "/tmp/faz8_kill_switch_on.json")"
[[ "${KS_ON_CODE}" == "200" ]] || fail "kill-switch ON başarısız http=${KS_ON_CODE}"

log "T-8.5 stabilite kuralları"
[[ "${CRASH_COUNT}" -eq 0 ]] || fail "crash > 0 (${CRASH_COUNT})"
[[ "${ERROR_5XX_COUNT}" -eq 0 ]] || fail "5xx > 0 (${ERROR_5XX_COUNT})"
[[ "${REJECT_COUNT}" -eq 0 ]] || fail "anormal reject > 0 (${REJECT_COUNT})"

log "Health/Ready doğrulama"
HEALTH_CODE="$(curl -sS -o /tmp/faz8_health.json -w '%{http_code}' "${BASE_URL}/health" || true)"
READY_CODE="$(curl -sS -o /tmp/faz8_ready.json -w '%{http_code}' "${BASE_URL}/ready" || true)"
if [[ "${HEALTH_CODE}" != "200" ]]; then
  HEALTH_CODE="$(curl -sS -o /tmp/faz8_health.json -w '%{http_code}' "${BASE_URL}/api/health" || true)"
fi
if [[ "${READY_CODE}" != "200" ]]; then
  READY_CODE="$(curl -sS -o /tmp/faz8_ready.json -w '%{http_code}' "${BASE_URL}/api/ready" || true)"
fi
[[ "${HEALTH_CODE}" == "200" ]] || fail "health 200 değil"
[[ "${READY_CODE}" == "200" ]] || fail "ready 200 değil"

fetch_canary_status

python - <<PY
import json, datetime
status = json.load(open('/tmp/faz8_canary_status.json', encoding='utf-8'))
summary = {
  "phase": "FAZ-8",
  "canary_test": "PASS",
  "duration_minutes": int('${DURATION_MINUTES}'),
  "symbols_tested": len(status.get("active_symbols") or ["BTCUSDT"]) or 1,
  "error_rate": float(status.get("error_rate") or 0),
  "reject_anomaly": False,
  "kill_switch_test": "PASS",
  "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
with open('${SUMMARY_JSON}', 'w', encoding='utf-8') as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

metrics = {
  "phase": "FAZ-8",
  "health_http": int('${HEALTH_CODE}'),
  "ready_http": int('${READY_CODE}'),
  "crash_count": int('${CRASH_COUNT}'),
  "error_5xx_count": int('${ERROR_5XX_COUNT}'),
  "reject_count": int('${REJECT_COUNT}'),
  "loop_count": int('${LOOP_COUNT}'),
  "canary_status": status,
  "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
with open('${METRICS_JSON}', 'w', encoding='utf-8') as f:
    json.dump(metrics, f, ensure_ascii=False, indent=2)
PY

log "PASS: artifacts üretildi"
log "SUMMARY: PASS"
