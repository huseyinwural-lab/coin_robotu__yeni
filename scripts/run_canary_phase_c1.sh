#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="${ROOT_DIR}/artifacts"
LOG_FILE="${ARTIFACT_DIR}/canary_c1_run.log"
SUMMARY_JSON="${ARTIFACT_DIR}/canary_c1_summary.json"
METRICS_JSON="${ARTIFACT_DIR}/canary_c1_metrics_snapshot.json"

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

ADMIN_EMAIL="${TEST_ADMIN_EMAIL:-canary.admin@platform.local}"
ADMIN_PASSWORD="${TEST_ADMIN_PASSWORD:-CanaryAdmin123!}"
USER_EMAIL="${CANARY_TEST_USER_EMAIL:-canary_c1_$(date +%s)@example.com}"
USER_PASSWORD="${CANARY_TEST_USER_PASSWORD:-CanaryPass123!}"
LIVE_API_KEY="${BINANCE_LIVE_API_KEY:-}"
LIVE_API_SECRET="${BINANCE_LIVE_API_SECRET:-}"

[[ -n "${LIVE_API_KEY}" && -n "${LIVE_API_SECRET}" ]] || fail "BINANCE_LIVE_API_KEY/SECRET zorunlu"

CANARY_SYMBOLS_JSON='["BTCUSDT","ETHUSDT","BNBUSDT"]'
CANARY_SYMBOLS=("BTCUSDT" "ETHUSDT" "BNBUSDT")
CANARY_CAPITAL="150"
CANARY_MAX_POSITIONS="2"
RUN_SECONDS=$((60 * 60))
INTERVAL_SECONDS="${CANARY_LOOP_INTERVAL_SECONDS:-300}"
if [[ "${INTERVAL_SECONDS}" -lt 30 ]]; then
  INTERVAL_SECONDS=30
fi

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

extract_token() {
  local body_path="$1"
  python - <<PY
import json
print((json.load(open('${body_path}', encoding='utf-8')).get('access_token') or '').strip())
PY
}

login_admin() {
  local code
  code="$(request_json POST "${BASE_URL}/api/auth/login/admin" "{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PASSWORD}\"}" "" "/tmp/c1_admin_login.json")"
  [[ "${code}" == "200" ]] || fail "admin login başarısız http=${code}"
  ADMIN_TOKEN="$(extract_token /tmp/c1_admin_login.json)"
  [[ -n "${ADMIN_TOKEN}" ]] || fail "admin token yok"
  log "PASS: admin login"
}

ensure_user_login() {
  local login_code
  login_code="$(request_json POST "${BASE_URL}/api/auth/login/user" "{\"email\":\"${USER_EMAIL}\",\"password\":\"${USER_PASSWORD}\"}" "" "/tmp/c1_user_login.json")"
  if [[ "${login_code}" != "200" ]]; then
    local reg_code
    reg_code="$(request_json POST "${BASE_URL}/api/auth/register" "{\"email\":\"${USER_EMAIL}\",\"password\":\"${USER_PASSWORD}\",\"first_name\":\"Canary\",\"last_name\":\"C1\"}" "" "/tmp/c1_user_register.json")"
    [[ "${reg_code}" == "200" ]] || fail "user register başarısız http=${reg_code}"

    local pending_code
    pending_code="$(request_json GET "${BASE_URL}/api/auth/admin/user-approval-requests" "" "${ADMIN_TOKEN}" "/tmp/c1_pending_users.json")"
    [[ "${pending_code}" == "200" ]] || fail "pending approvals alınamadı"

    USER_ID="$(python - <<PY
import json
rows=json.load(open('/tmp/c1_pending_users.json', encoding='utf-8'))
target='${USER_EMAIL}'.lower()
row=next((r for r in rows if str(r.get('email','')).lower()==target), None)
print((row or {}).get('id',''))
PY
)"
    [[ -n "${USER_ID}" ]] || fail "kullanıcı pending listede yok"

    local approve_code
    approve_code="$(request_json POST "${BASE_URL}/api/auth/admin/user-approval-requests/${USER_ID}/approve" "null" "${ADMIN_TOKEN}" "/tmp/c1_user_approve.json")"
    [[ "${approve_code}" == "200" ]] || fail "user approval başarısız http=${approve_code}"

    login_code="$(request_json POST "${BASE_URL}/api/auth/login/user" "{\"email\":\"${USER_EMAIL}\",\"password\":\"${USER_PASSWORD}\"}" "" "/tmp/c1_user_login.json")"
    [[ "${login_code}" == "200" ]] || fail "user login (approve sonrası) başarısız http=${login_code}"
  fi

  USER_TOKEN="$(extract_token /tmp/c1_user_login.json)"
  [[ -n "${USER_TOKEN}" ]] || fail "user token yok"
  log "PASS: user login"
}

set_exchange_keys() {
  local payload code
  payload="{\"exchange\":\"binance\",\"mode\":\"futures_live\",\"api_key\":\"${LIVE_API_KEY}\",\"api_secret\":\"${LIVE_API_SECRET}\"}"
  code="$(request_json PUT "${BASE_URL}/api/phase4/exchange-settings" "${payload}" "${USER_TOKEN}" "/tmp/c1_exchange_settings.json")"
  [[ "${code}" == "200" ]] || fail "exchange settings update başarısız http=${code}"
  log "PASS: exchange settings güncellendi"
}

load_live_config() {
  local code
  code="$(request_json GET "${BASE_URL}/api/phase4/live-config" "" "${ADMIN_TOKEN}" "/tmp/c1_live_get.json")"
  [[ "${code}" == "200" ]] || fail "live-config okunamadı http=${code}"
}

update_live_config_for_symbol() {
  local symbol="$1"
  python - <<PY
import json
cfg=json.load(open('/tmp/c1_live_get.json', encoding='utf-8'))
cfg.update({
  'canary_enabled': True,
  'canary_symbols': json.loads('${CANARY_SYMBOLS_JSON}'),
  'canary_max_capital_usdt': float('${CANARY_CAPITAL}'),
  'canary_max_positions': int('${CANARY_MAX_POSITIONS}'),
  'symbol_whitelist': ['${symbol}'],
  'trading_enabled': True,
  'kill_switch_enabled': False,
})
open('/tmp/c1_live_put.json','w',encoding='utf-8').write(json.dumps(cfg))
PY
  local payload code
  payload="$(cat /tmp/c1_live_put.json)"
  code="$(request_json PUT "${BASE_URL}/api/phase4/live-config" "${payload}" "${ADMIN_TOKEN}" "/tmp/c1_live_put_resp.json")"
  [[ "${code}" == "200" ]] || fail "live-config update başarısız http=${code}"
}

fetch_canary_status() {
  local code
  code="$(request_json GET "${BASE_URL}/api/admin/canary-status" "" "${ADMIN_TOKEN}" "/tmp/c1_canary_status.json")"
  [[ "${code}" == "200" ]] || fail "canary-status başarısız http=${code}"
}

test_order() {
  request_json POST "${BASE_URL}/api/phase4/test-order" "{}" "${USER_TOKEN}" "/tmp/c1_test_order.json"
}

kill_switch_toggle() {
  local trading_enabled="$1"
  local reason="$2"
  local code
  code="$(request_json POST "${BASE_URL}/api/admin/kill-switch" "{\"trading_enabled\":${trading_enabled},\"reason\":\"${reason}\"}" "${ADMIN_TOKEN}" "/tmp/c1_kill_switch.json")"
  [[ "${code}" == "200" ]] || fail "kill-switch toggle başarısız (${reason}) http=${code}"
}

log "C1 START config: symbols=3 capital=150 max_positions=2 duration=60m"
login_admin
ensure_user_login
set_exchange_keys
load_live_config
update_live_config_for_symbol "BTCUSDT"

log "Kill-switch faz başı testi"
kill_switch_toggle false "c1_phase_start_kill_test"
BLOCK_CODE="$(test_order || true)"
if [[ "${BLOCK_CODE}" != "400" && "${BLOCK_CODE}" != "403" ]]; then
  fail "kill-switch faz başı reject bekleniyordu http=${BLOCK_CODE}"
fi
python - <<PY
import json
body=json.load(open('/tmp/c1_test_order.json', encoding='utf-8'))
if 'TRADING_DISABLED' not in str(body):
    raise SystemExit(f"kill-switch reject reason beklenen değil: {body}")
print('KILL_SWITCH_START_OK')
PY
kill_switch_toggle true "c1_phase_start_resume"

RUN_START="$(date +%s)"
RUN_END="$((RUN_START + RUN_SECONDS))"

LOOP_COUNT=0
CRASH_COUNT=0
ERROR_5XX_COUNT=0
REJECT_COUNT=0
LATENCY_SPIKE_COUNT=0
REJECT_ANOMALY_COUNT=0

MAX_ERROR_RATE=0
MAX_ORDER_FAIL_RATE=0
MAX_REJECT_RATE=0
MAX_LATENCY_P95=0
MAX_PNL_DRIFT=0
PREV_LATENCY_P95=0

while [[ "$(date +%s)" -lt "${RUN_END}" ]]; do
  LOOP_COUNT="$((LOOP_COUNT + 1))"
  for symbol in "${CANARY_SYMBOLS[@]}"; do
    update_live_config_for_symbol "${symbol}"
    code="$(test_order || true)"
    if [[ -z "${code}" || "${code}" == "000" ]]; then
      CRASH_COUNT="$((CRASH_COUNT + 1))"
      log "LOOP_${LOOP_COUNT}_${symbol}: crash/network"
    elif [[ "${code}" -ge 500 ]]; then
      ERROR_5XX_COUNT="$((ERROR_5XX_COUNT + 1))"
      log "LOOP_${LOOP_COUNT}_${symbol}: 5xx=${code}"
    elif [[ "${code}" -ge 400 ]]; then
      REJECT_COUNT="$((REJECT_COUNT + 1))"
      log "LOOP_${LOOP_COUNT}_${symbol}: reject=${code}"
    else
      log "LOOP_${LOOP_COUNT}_${symbol}: success=${code}"
    fi
  done

  fetch_canary_status
  python - <<PY | tee -a "${LOG_FILE}"
import json
s=json.load(open('/tmp/c1_canary_status.json', encoding='utf-8'))
print('STATUS', s)
PY

  error_rate="$(python - <<PY
import json
s=json.load(open('/tmp/c1_canary_status.json', encoding='utf-8'))
print(float(s.get('error_rate') or 0))
PY
)"
  order_fail_rate="$(python - <<PY
import json
s=json.load(open('/tmp/c1_canary_status.json', encoding='utf-8'))
print(float(s.get('order_fail_rate') or 0))
PY
)"
  reject_rate="$(python - <<PY
import json
s=json.load(open('/tmp/c1_canary_status.json', encoding='utf-8'))
print(float(s.get('reject_rate') or 0))
PY
)"
  latency_p95="$(python - <<PY
import json
s=json.load(open('/tmp/c1_canary_status.json', encoding='utf-8'))
print(float(s.get('latency_ms_p95') or 0))
PY
)"
  pnl_drift="$(python - <<PY
import json
s=json.load(open('/tmp/c1_canary_status.json', encoding='utf-8'))
print(float(s.get('pnl_drift') or 0))
PY
)"

  MAX_ERROR_RATE="$(python - <<PY
print(max(float('${MAX_ERROR_RATE}'), float('${error_rate}')))
PY
)"
  MAX_ORDER_FAIL_RATE="$(python - <<PY
print(max(float('${MAX_ORDER_FAIL_RATE}'), float('${order_fail_rate}')))
PY
)"
  MAX_REJECT_RATE="$(python - <<PY
print(max(float('${MAX_REJECT_RATE}'), float('${reject_rate}')))
PY
)"
  MAX_LATENCY_P95="$(python - <<PY
print(max(float('${MAX_LATENCY_P95}'), float('${latency_p95}')))
PY
)"
  MAX_PNL_DRIFT="$(python - <<PY
print(max(float('${MAX_PNL_DRIFT}'), float('${pnl_drift}')))
PY
)"

  if ! python - <<PY
if float('${reject_rate}') > 0:
    raise SystemExit(1)
PY
  then
    REJECT_ANOMALY_COUNT="$((REJECT_ANOMALY_COUNT + 1))"
  fi

  if ! python - <<PY
curr=float('${latency_p95}')
prev=float('${PREV_LATENCY_P95}')
if prev > 0 and curr > 5000 and curr > (prev * 1.8):
    raise SystemExit(1)
PY
  then
    LATENCY_SPIKE_COUNT="$((LATENCY_SPIKE_COUNT + 1))"
  fi

  PREV_LATENCY_P95="${latency_p95}"

  sleep "${INTERVAL_SECONDS}"
done

DURATION_MINUTES="$(( ( $(date +%s) - RUN_START ) / 60 ))"
[[ "${DURATION_MINUTES}" -ge 60 ]] || fail "C1 süresi 60dk altında (${DURATION_MINUTES})"

log "Kill-switch faz sonu testi"
kill_switch_toggle false "c1_phase_end_kill_test"
END_BLOCK_CODE="$(test_order || true)"
if [[ "${END_BLOCK_CODE}" != "400" && "${END_BLOCK_CODE}" != "403" ]]; then
  fail "kill-switch faz sonu reject bekleniyordu http=${END_BLOCK_CODE}"
fi
python - <<PY
import json
body=json.load(open('/tmp/c1_test_order.json', encoding='utf-8'))
if 'TRADING_DISABLED' not in str(body):
    raise SystemExit(f"kill-switch end reject reason beklenen değil: {body}")
print('KILL_SWITCH_END_OK')
PY
kill_switch_toggle true "c1_phase_end_resume"

HEALTH_CODE="$(curl -sS -o /tmp/c1_health.json -w '%{http_code}' "${BASE_URL}/health" || true)"
READY_CODE="$(curl -sS -o /tmp/c1_ready.json -w '%{http_code}' "${BASE_URL}/ready" || true)"
if [[ "${HEALTH_CODE}" != "200" ]]; then
  HEALTH_CODE="$(curl -sS -o /tmp/c1_health.json -w '%{http_code}' "${BASE_URL}/api/health" || true)"
fi
if [[ "${READY_CODE}" != "200" ]]; then
  READY_CODE="$(curl -sS -o /tmp/c1_ready.json -w '%{http_code}' "${BASE_URL}/api/ready" || true)"
fi
[[ "${HEALTH_CODE}" == "200" ]] || fail "health 200 değil"
[[ "${READY_CODE}" == "200" ]] || fail "ready 200 değil"

if [[ "${CRASH_COUNT}" -ne 0 ]]; then fail "crash_count=${CRASH_COUNT}"; fi
if [[ "${ERROR_5XX_COUNT}" -ne 0 ]]; then fail "error_5xx_count=${ERROR_5XX_COUNT}"; fi
if [[ "${REJECT_ANOMALY_COUNT}" -ne 0 ]]; then fail "reject_anomaly_count=${REJECT_ANOMALY_COUNT}"; fi
if [[ "${LATENCY_SPIKE_COUNT}" -ne 0 ]]; then fail "latency_spike_count=${LATENCY_SPIKE_COUNT}"; fi

python - <<PY
import json, datetime

summary = {
  "phase": "C1",
  "canary_rollout_test": "PASS",
  "symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT"],
  "capital_usdt": 150,
  "max_positions": 2,
  "duration_minutes": int('${DURATION_MINUTES}'),
  "crash_count": int('${CRASH_COUNT}'),
  "error_5xx_count": int('${ERROR_5XX_COUNT}'),
  "reject_anomaly": False,
  "latency_spike": False,
  "kill_switch_start_test": "PASS",
  "kill_switch_end_test": "PASS",
  "health_check": "PASS",
  "ready_check": "PASS",
  "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
with open('${SUMMARY_JSON}', 'w', encoding='utf-8') as f:
  json.dump(summary, f, ensure_ascii=False, indent=2)

metrics = {
  "phase": "C1",
  "loop_count": int('${LOOP_COUNT}'),
  "max_error_rate": float('${MAX_ERROR_RATE}'),
  "max_order_fail_rate": float('${MAX_ORDER_FAIL_RATE}'),
  "max_reject_rate": float('${MAX_REJECT_RATE}'),
  "max_latency_ms_p95": float('${MAX_LATENCY_P95}'),
  "max_pnl_drift": float('${MAX_PNL_DRIFT}'),
  "crash_count": int('${CRASH_COUNT}'),
  "error_5xx_count": int('${ERROR_5XX_COUNT}'),
  "reject_count": int('${REJECT_COUNT}'),
  "reject_anomaly_count": int('${REJECT_ANOMALY_COUNT}'),
  "latency_spike_count": int('${LATENCY_SPIKE_COUNT}'),
  "health_http": int('${HEALTH_CODE}'),
  "ready_http": int('${READY_CODE}'),
  "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
with open('${METRICS_JSON}', 'w', encoding='utf-8') as f:
  json.dump(metrics, f, ensure_ascii=False, indent=2)
PY

log "SUMMARY: PASS"
