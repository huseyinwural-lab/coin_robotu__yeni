#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="${ROOT_DIR}/artifacts"
LOG_FILE="${ARTIFACT_DIR}/canary_c2_run.log"
SUMMARY_JSON="${ARTIFACT_DIR}/canary_c2_summary.json"
METRICS_JSON="${ARTIFACT_DIR}/canary_c2_metrics_snapshot.json"

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
USER_EMAIL="${CANARY_TEST_USER_EMAIL:-canary_$(date +%s)@example.com}"
USER_PASSWORD="${CANARY_TEST_USER_PASSWORD:-CanaryPass123!}"
TESTNET_API_KEY="${BINANCE_TESTNET_API_KEY:-}"
TESTNET_API_SECRET="${BINANCE_TESTNET_API_SECRET:-}"

[[ -n "${TESTNET_API_KEY}" && -n "${TESTNET_API_SECRET}" ]] || fail "BINANCE_TESTNET_API_KEY/SECRET zorunlu"

CANARY_SYMBOLS_JSON='["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT"]'
CANARY_SYMBOLS=("BTCUSDT" "ETHUSDT" "BNBUSDT" "SOLUSDT" "XRPUSDT")
CANARY_CAPITAL="300"
CANARY_MAX_POSITIONS="3"
RUN_SECONDS=$((60 * 60))
INTERVAL_SECONDS="${CANARY_LOOP_INTERVAL_SECONDS:-300}"
if [[ "${INTERVAL_SECONDS}" -lt 30 ]]; then
  INTERVAL_SECONDS=30
fi

WARMUP_LOOPS=3
ERROR_RATE_FINAL_LIMIT=0.03
LATENCY_P95_LIMIT=4000

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
  code="$(request_json POST "${BASE_URL}/api/auth/login/admin" "{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PASSWORD}\"}" "" "/tmp/c2_admin_login.json")"
  [[ "${code}" == "200" ]] || fail "admin login başarısız http=${code}"
  ADMIN_TOKEN="$(extract_token /tmp/c2_admin_login.json)"
  [[ -n "${ADMIN_TOKEN}" ]] || fail "admin token yok"
  log "PASS: admin login"
}

ensure_user_login() {
  local login_code
  login_code="$(request_json POST "${BASE_URL}/api/auth/login/user" "{\"email\":\"${USER_EMAIL}\",\"password\":\"${USER_PASSWORD}\"}" "" "/tmp/c2_user_login.json")"
  if [[ "${login_code}" != "200" ]]; then
    local reg_code
    reg_code="$(request_json POST "${BASE_URL}/api/auth/register" "{\"email\":\"${USER_EMAIL}\",\"password\":\"${USER_PASSWORD}\",\"first_name\":\"Canary\",\"last_name\":\"C2\"}" "" "/tmp/c2_user_register.json")"
    [[ "${reg_code}" == "200" ]] || fail "user register başarısız http=${reg_code}"

    local pending_code
    pending_code="$(request_json GET "${BASE_URL}/api/auth/admin/user-approval-requests" "" "${ADMIN_TOKEN}" "/tmp/c2_pending_users.json")"
    [[ "${pending_code}" == "200" ]] || fail "pending approvals alınamadı"

    USER_ID="$(python - <<PY
import json
rows=json.load(open('/tmp/c2_pending_users.json', encoding='utf-8'))
target='${USER_EMAIL}'.lower()
row=next((r for r in rows if str(r.get('email','')).lower()==target), None)
print((row or {}).get('id',''))
PY
)"
    [[ -n "${USER_ID}" ]] || fail "kullanıcı pending listede yok"

    local approve_code
    approve_code="$(request_json POST "${BASE_URL}/api/auth/admin/user-approval-requests/${USER_ID}/approve" "{}" "${ADMIN_TOKEN}" "/tmp/c2_user_approve.json")"
    [[ "${approve_code}" == "200" ]] || fail "user approval başarısız http=${approve_code}"

    login_code="$(request_json POST "${BASE_URL}/api/auth/login/user" "{\"email\":\"${USER_EMAIL}\",\"password\":\"${USER_PASSWORD}\"}" "" "/tmp/c2_user_login.json")"
    [[ "${login_code}" == "200" ]] || fail "user login (approve sonrası) başarısız http=${login_code}"
  fi

  USER_TOKEN="$(extract_token /tmp/c2_user_login.json)"
  [[ -n "${USER_TOKEN}" ]] || fail "user token yok"
  log "PASS: user login"
}

set_exchange_keys() {
  local payload code
  payload="{\"exchange\":\"binance\",\"mode\":\"futures_testnet\",\"api_key\":\"${TESTNET_API_KEY}\",\"api_secret\":\"${TESTNET_API_SECRET}\"}"
  code="$(request_json PUT "${BASE_URL}/api/phase4/exchange-settings" "${payload}" "${USER_TOKEN}" "/tmp/c2_exchange_settings.json")"
  [[ "${code}" == "200" ]] || fail "exchange settings update başarısız http=${code}"
  log "PASS: exchange settings güncellendi"
}

load_live_config() {
  local code
  code="$(request_json GET "${BASE_URL}/api/phase4/live-config" "" "${ADMIN_TOKEN}" "/tmp/c2_live_get.json")"
  [[ "${code}" == "200" ]] || fail "live-config okunamadı http=${code}"
}

update_live_config_for_symbol() {
  local symbol="$1"
  python - <<PY
import json
cfg=json.load(open('/tmp/c2_live_get.json', encoding='utf-8'))
cfg.update({
  'canary_enabled': True,
  'canary_symbols': json.loads('${CANARY_SYMBOLS_JSON}'),
  'canary_max_capital_usdt': float('${CANARY_CAPITAL}'),
  'canary_max_positions': int('${CANARY_MAX_POSITIONS}'),
  'symbol_whitelist': ['${symbol}'],
  'trading_enabled': True,
  'kill_switch_enabled': False,
})
open('/tmp/c2_live_put.json','w',encoding='utf-8').write(json.dumps(cfg))
PY
  local payload code
  payload="$(cat /tmp/c2_live_put.json)"
  code="$(request_json PUT "${BASE_URL}/api/phase4/live-config" "${payload}" "${ADMIN_TOKEN}" "/tmp/c2_live_put_resp.json")"
  [[ "${code}" == "200" ]] || fail "live-config update başarısız http=${code}"
}

fetch_canary_status() {
  local code
  code="$(request_json GET "${BASE_URL}/api/admin/canary-status" "" "${ADMIN_TOKEN}" "/tmp/c2_canary_status.json")"
  [[ "${code}" == "200" ]] || fail "canary-status başarısız http=${code}"
}

test_order() {
  request_json POST "${BASE_URL}/api/phase4/test-order" "{}" "${USER_TOKEN}" "/tmp/c2_test_order.json"
}

kill_switch_toggle() {
  local trading_enabled="$1"
  local reason="$2"
  local code
  code="$(request_json POST "${BASE_URL}/api/admin/kill-switch" "{\"trading_enabled\":${trading_enabled},\"reason\":\"${reason}\"}" "${ADMIN_TOKEN}" "/tmp/c2_kill_switch.json")"
  [[ "${code}" == "200" ]] || fail "kill-switch toggle başarısız (${reason}) http=${code}"
}

log "C2 START config: symbols=5 capital=300 max_positions=3 duration=60m"

# T-C2.2 backend health gate
HCODE="$(curl -sS -o /tmp/c2_health_gate.json -w '%{http_code}' "${BASE_URL}/api/health" || true)"
RCODE="$(curl -sS -o /tmp/c2_ready_gate.json -w '%{http_code}' "${BASE_URL}/api/ready" || true)"
[[ "${HCODE}" == "200" ]] || fail "backend health gate fail (api/health=${HCODE})"
[[ "${RCODE}" == "200" ]] || fail "backend ready gate fail (api/ready=${RCODE})"
log "PASS: backend health gate (api/health=200, api/ready=200)"

login_admin
ensure_user_login
set_exchange_keys
load_live_config
update_live_config_for_symbol "BTCUSDT"
fetch_canary_status
log "PASS: canary-status config ok"

log "Kill-switch faz başı testi"
kill_switch_toggle false "c2_phase_start_kill_test"
BLOCK_CODE="$(test_order || true)"
if [[ "${BLOCK_CODE}" != "400" && "${BLOCK_CODE}" != "403" ]]; then
  fail "kill-switch faz başı reject bekleniyordu http=${BLOCK_CODE}"
fi
python - <<PY
import json
body=json.load(open('/tmp/c2_test_order.json', encoding='utf-8'))
if 'TRADING_DISABLED' not in str(body):
    raise SystemExit(f"kill-switch reject reason beklenen değil: {body}")
print('KILL_SWITCH_START_OK')
PY
kill_switch_toggle true "c2_phase_start_resume"

RUN_START="$(date +%s)"
RUN_END="$((RUN_START + RUN_SECONDS))"

LOOP_COUNT=0
CRASH_COUNT=0
ERROR_5XX_COUNT=0
REJECT_COUNT=0
LATENCY_LIMIT_BREACH_COUNT=0
VIOLATION_BREACH_COUNT=0

MAX_ERROR_RATE=0
MAX_ORDER_FAIL_RATE=0
MAX_REJECT_RATE=0
MAX_LATENCY_P95=0
MAX_PNL_DRIFT=0
PREV_ERROR_RATE=""
ERROR_MONOTONIC_BREAKS=0

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
s=json.load(open('/tmp/c2_canary_status.json', encoding='utf-8'))
print('STATUS', s)
PY

  error_rate="$(python - <<PY
import json
s=json.load(open('/tmp/c2_canary_status.json', encoding='utf-8'))
print(float(s.get('error_rate') or 0))
PY
)"
  order_fail_rate="$(python - <<PY
import json
s=json.load(open('/tmp/c2_canary_status.json', encoding='utf-8'))
print(float(s.get('order_fail_rate') or 0))
PY
)"
  reject_rate="$(python - <<PY
import json
s=json.load(open('/tmp/c2_canary_status.json', encoding='utf-8'))
print(float(s.get('reject_rate') or 0))
PY
)"
  latency_p95="$(python - <<PY
import json
s=json.load(open('/tmp/c2_canary_status.json', encoding='utf-8'))
print(float(s.get('latency_ms_p95') or 0))
PY
)"
  pnl_drift="$(python - <<PY
import json
s=json.load(open('/tmp/c2_canary_status.json', encoding='utf-8'))
print(float(s.get('pnl_drift') or 0))
PY
)"
  violations="$(python - <<PY
import json
s=json.load(open('/tmp/c2_canary_status.json', encoding='utf-8'))
print(int(s.get('violations') or 0))
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

  # T-C2.7 warm-up sonrası error trend kuralları
  if [[ "${LOOP_COUNT}" -gt "${WARMUP_LOOPS}" ]]; then
    if [[ -n "${PREV_ERROR_RATE}" ]]; then
      if ! python - <<PY
curr=float('${error_rate}')
prev=float('${PREV_ERROR_RATE}')
if curr > (prev + 1e-9):
    raise SystemExit(1)
PY
      then
        ERROR_MONOTONIC_BREAKS="$((ERROR_MONOTONIC_BREAKS + 1))"
      fi
    fi
  fi
  PREV_ERROR_RATE="${error_rate}"

  if ! python - <<PY
if float('${latency_p95}') < ${LATENCY_P95_LIMIT}:
    raise SystemExit(0)
raise SystemExit(1)
PY
  then
    LATENCY_LIMIT_BREACH_COUNT="$((LATENCY_LIMIT_BREACH_COUNT + 1))"
  fi

  if [[ "${violations}" -gt 0 ]]; then
    VIOLATION_BREACH_COUNT="$((VIOLATION_BREACH_COUNT + 1))"
  fi

  sleep "${INTERVAL_SECONDS}"
done

DURATION_MINUTES="$(( ( $(date +%s) - RUN_START ) / 60 ))"
[[ "${DURATION_MINUTES}" -ge 60 ]] || fail "C2 süresi 60dk altında (${DURATION_MINUTES})"
[[ "${LOOP_COUNT}" -ge 10 ]] || fail "minimum 10 loop sağlanmadı (${LOOP_COUNT})"

log "Kill-switch faz sonu testi"
kill_switch_toggle false "c2_phase_end_kill_test"
END_BLOCK_CODE="$(test_order || true)"
if [[ "${END_BLOCK_CODE}" != "400" && "${END_BLOCK_CODE}" != "403" ]]; then
  fail "kill-switch faz sonu reject bekleniyordu http=${END_BLOCK_CODE}"
fi
python - <<PY
import json
body=json.load(open('/tmp/c2_test_order.json', encoding='utf-8'))
if 'TRADING_DISABLED' not in str(body):
    raise SystemExit(f"kill-switch end reject reason beklenen değil: {body}")
print('KILL_SWITCH_END_OK')
PY
kill_switch_toggle true "c2_phase_end_resume"

HEALTH_CODE="$(curl -sS -o /tmp/c2_health.json -w '%{http_code}' "${BASE_URL}/health" || true)"
READY_CODE="$(curl -sS -o /tmp/c2_ready.json -w '%{http_code}' "${BASE_URL}/ready" || true)"
if [[ "${HEALTH_CODE}" != "200" ]]; then
  HEALTH_CODE="$(curl -sS -o /tmp/c2_health.json -w '%{http_code}' "${BASE_URL}/api/health" || true)"
fi
if [[ "${READY_CODE}" != "200" ]]; then
  READY_CODE="$(curl -sS -o /tmp/c2_ready.json -w '%{http_code}' "${BASE_URL}/api/ready" || true)"
fi
[[ "${HEALTH_CODE}" == "200" ]] || fail "health 200 değil"
[[ "${READY_CODE}" == "200" ]] || fail "ready 200 değil"

if [[ "${CRASH_COUNT}" -ne 0 ]]; then fail "crash_count=${CRASH_COUNT}"; fi
if [[ "${ERROR_5XX_COUNT}" -ne 0 ]]; then fail "error_5xx_count=${ERROR_5XX_COUNT}"; fi
if [[ "${REJECT_COUNT}" -ne 0 ]]; then fail "reject_count=${REJECT_COUNT}"; fi
if [[ "${VIOLATION_BREACH_COUNT}" -ne 0 ]]; then fail "violations>0 count=${VIOLATION_BREACH_COUNT}"; fi
if [[ "${LATENCY_LIMIT_BREACH_COUNT}" -ne 0 ]]; then fail "latency_limit_breach_count=${LATENCY_LIMIT_BREACH_COUNT}"; fi
if [[ "${ERROR_MONOTONIC_BREAKS}" -ne 0 ]]; then fail "error_rate_monotonic_breaks=${ERROR_MONOTONIC_BREAKS}"; fi

if ! python - <<PY
if float('${PREV_ERROR_RATE:-0}') <= ${ERROR_RATE_FINAL_LIMIT}:
    raise SystemExit(0)
raise SystemExit(1)
PY
then
  fail "final error_rate > ${ERROR_RATE_FINAL_LIMIT} (final=${PREV_ERROR_RATE})"
fi

python - <<PY
import json, datetime

summary = {
  "phase": "C2",
  "canary_rollout_test": "PASS",
  "symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"],
  "capital_usdt": 300,
  "max_positions": 3,
  "duration_minutes": int('${DURATION_MINUTES}'),
  "loop_count": int('${LOOP_COUNT}'),
  "crash_count": int('${CRASH_COUNT}'),
  "error_5xx_count": int('${ERROR_5XX_COUNT}'),
  "reject_count": int('${REJECT_COUNT}'),
  "violations": 0,
  "kill_switch_start_test": "PASS",
  "kill_switch_end_test": "PASS",
  "health_check": "PASS",
  "ready_check": "PASS",
  "error_rate_final": float('${PREV_ERROR_RATE:-0}'),
  "error_rate_rule": "PASS",
  "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
with open('${SUMMARY_JSON}', 'w', encoding='utf-8') as f:
  json.dump(summary, f, ensure_ascii=False, indent=2)

metrics = {
  "phase": "C2",
  "loop_count": int('${LOOP_COUNT}'),
  "warmup_loops": int('${WARMUP_LOOPS}'),
  "max_error_rate": float('${MAX_ERROR_RATE}'),
  "max_order_fail_rate": float('${MAX_ORDER_FAIL_RATE}'),
  "max_reject_rate": float('${MAX_REJECT_RATE}'),
  "max_latency_ms_p95": float('${MAX_LATENCY_P95}'),
  "max_pnl_drift": float('${MAX_PNL_DRIFT}'),
  "crash_count": int('${CRASH_COUNT}'),
  "error_5xx_count": int('${ERROR_5XX_COUNT}'),
  "reject_count": int('${REJECT_COUNT}'),
  "violations": 0,
  "latency_limit_breach_count": int('${LATENCY_LIMIT_BREACH_COUNT}'),
  "error_monotonic_breaks": int('${ERROR_MONOTONIC_BREAKS}'),
  "error_rate_final": float('${PREV_ERROR_RATE:-0}'),
  "health_http": int('${HEALTH_CODE}'),
  "ready_http": int('${READY_CODE}'),
  "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
with open('${METRICS_JSON}', 'w', encoding='utf-8') as f:
  json.dump(metrics, f, ensure_ascii=False, indent=2)
PY

log "SUMMARY: PASS"
