#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="${ROOT_DIR}/artifacts"
LOG_FILE="${ARTIFACT_DIR}/canary_c4_run.log"
SUMMARY_JSON="${ARTIFACT_DIR}/canary_c4_summary.json"
METRICS_JSON="${ARTIFACT_DIR}/canary_c4_metrics_snapshot.json"

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
USER_EMAIL="${CANARY_TEST_USER_EMAIL:-canary_1774010877@example.com}"
USER_PASSWORD="${CANARY_TEST_USER_PASSWORD:-TestPass123!}"
LIVE_API_KEY="${BINANCE_LIVE_API_KEY:-}"
LIVE_API_SECRET="${BINANCE_LIVE_API_SECRET:-}"

HAS_LIVE_KEYS="0"
if [[ -n "${LIVE_API_KEY}" && -n "${LIVE_API_SECRET}" ]]; then
  HAS_LIVE_KEYS="1"
fi

# C4: all symbols + production limits + 2h gözlem
RUN_MINUTES="${CANARY_C4_RUN_MINUTES:-120}"
if ! python - <<PY
v=int('${RUN_MINUTES}')
if 120 <= v <= 150:
    raise SystemExit(0)
raise SystemExit(1)
PY
then
  fail "CANARY_C4_RUN_MINUTES 120-150 aralığında olmalı (current=${RUN_MINUTES})"
fi
RUN_SECONDS="$((RUN_MINUTES * 60))"

INTERVAL_SECONDS="${CANARY_LOOP_INTERVAL_SECONDS:-300}"
if [[ "${INTERVAL_SECONDS}" -lt 30 ]]; then
  INTERVAL_SECONDS=30
fi

WARMUP_LOOPS=3
ERROR_RATE_FINAL_LIMIT=0.03
LATENCY_P95_LIMIT=4000

ORDER_QUEUE_DEPTH_LIMIT=300
ORDER_QUEUE_GROWTH_STREAK_LIMIT=5
PARALLEL_QUEUE_DEPTH_LIMIT=80
PARALLEL_CYCLE_LATENCY_LIMIT=5000
PARALLEL_DROPPED_EVAL_LIMIT=0

request_json() {
  local method="$1"
  local url="$2"
  local body="$3"
  local token="${4:-}"
  local out="$5"
  local headers=(-H "Content-Type: application/json")
  local http_code=""
  local attempt
  if [[ -n "${token}" ]]; then
    headers+=(-H "Authorization: Bearer ${token}")
  fi

  for attempt in 1 2 3; do
    if [[ "${method}" == "GET" ]]; then
      http_code="$(curl -sS -o "${out}" -w '%{http_code}' "${headers[@]}" "${url}" 2>>"${LOG_FILE}" || true)"
    else
      http_code="$(curl -sS -o "${out}" -w '%{http_code}' -X "${method}" "${headers[@]}" -d "${body}" "${url}" 2>>"${LOG_FILE}" || true)"
    fi

    if [[ -n "${http_code}" ]]; then
      echo "${http_code}"
      return 0
    fi

    log "WARN: request retry method=${method} attempt=${attempt}"
    sleep 2
  done

  printf '{}' > "${out}"
  echo "000"
  return 0
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
  code="$(request_json POST "${BASE_URL}/api/auth/login/admin" "{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PASSWORD}\"}" "" "/tmp/c4_admin_login.json")"
  [[ "${code}" == "200" ]] || fail "admin login başarısız http=${code}"
  ADMIN_TOKEN="$(extract_token /tmp/c4_admin_login.json)"
  [[ -n "${ADMIN_TOKEN}" ]] || fail "admin token yok"
  log "PASS: admin login"
}

ensure_user_login() {
  local login_code
  login_code="$(request_json POST "${BASE_URL}/api/auth/login/user" "{\"email\":\"${USER_EMAIL}\",\"password\":\"${USER_PASSWORD}\"}" "" "/tmp/c4_user_login.json")"
  [[ "${login_code}" == "200" ]] || fail "user login başarısız http=${login_code}"
  USER_TOKEN="$(extract_token /tmp/c4_user_login.json)"
  [[ -n "${USER_TOKEN}" ]] || fail "user token yok"
  log "PASS: user login"
}

set_exchange_keys() {
  if [[ "${HAS_LIVE_KEYS}" != "1" ]]; then
    log "WARN: BINANCE_LIVE_API_KEY/SECRET bulunamadı, kayıtlı user exchange key kullanılacak"
    return 0
  fi
  local payload code
  payload="{\"exchange\":\"binance\",\"mode\":\"futures_live\",\"api_key\":\"${LIVE_API_KEY}\",\"api_secret\":\"${LIVE_API_SECRET}\"}"
  code="$(request_json PUT "${BASE_URL}/api/phase4/exchange-settings" "${payload}" "${USER_TOKEN}" "/tmp/c4_exchange_settings.json")"
  [[ "${code}" == "200" ]] || fail "exchange settings update başarısız http=${code}"
  log "PASS: exchange settings güncellendi"
}

load_live_config() {
  local code
  code="$(request_json GET "${BASE_URL}/api/phase4/live-config" "" "${ADMIN_TOKEN}" "/tmp/c4_live_get.json")"
  [[ "${code}" == "200" ]] || fail "live-config okunamadı http=${code}"
}

update_live_config_full() {
  PROD_CANARY_CAPITAL="$(python - <<PY
import json
cfg=json.load(open('/tmp/c4_live_get.json', encoding='utf-8'))
current=float(cfg.get('canary_max_capital_usdt') or 0)
override='${CANARY_C4_CAPITAL_USDT:-}'
print(float(override) if override else current)
PY
)"
  PROD_CANARY_MAX_POSITIONS="$(python - <<PY
import json
cfg=json.load(open('/tmp/c4_live_get.json', encoding='utf-8'))
current=int(cfg.get('canary_max_positions') or 0)
override='${CANARY_C4_MAX_POSITIONS:-}'
print(int(override) if override else current)
PY
)"

  python - <<PY
import json
cfg=json.load(open('/tmp/c4_live_get.json', encoding='utf-8'))
cfg.update({
  'canary_enabled': True,
  'canary_symbols': [],
  'canary_max_capital_usdt': float('${PROD_CANARY_CAPITAL}'),
  'canary_max_positions': int('${PROD_CANARY_MAX_POSITIONS}'),
  'symbol_whitelist': [],
  'trading_enabled': True,
  'kill_switch_enabled': False,
})
open('/tmp/c4_live_put.json','w',encoding='utf-8').write(json.dumps(cfg))
PY
  local payload code
  payload="$(cat /tmp/c4_live_put.json)"
  code="$(request_json PUT "${BASE_URL}/api/phase4/live-config" "${payload}" "${ADMIN_TOKEN}" "/tmp/c4_live_put_resp.json")"
  [[ "${code}" == "200" ]] || fail "live-config full enable update başarısız http=${code}"
}

fetch_canary_status() {
  local code
  code="$(request_json GET "${BASE_URL}/api/admin/canary-status" "" "${ADMIN_TOKEN}" "/tmp/c4_canary_status.json")"
  [[ "${code}" == "200" ]] || fail "canary-status başarısız http=${code}"
}

fetch_execution_queue_summary() {
  local code
  code="$(request_json GET "${BASE_URL}/api/admin/execution-queue/rejection-summary" "" "${ADMIN_TOKEN}" "/tmp/c4_execution_queue.json")"
  [[ "${code}" == "200" ]] || fail "execution-queue/rejection-summary başarısız http=${code}"
}

fetch_universe_monitor() {
  local code
  code="$(request_json GET "${BASE_URL}/api/admin/universe-monitor?market_type=futures" "" "${ADMIN_TOKEN}" "/tmp/c4_universe_monitor.json")"
  [[ "${code}" == "200" ]] || fail "admin/universe-monitor başarısız http=${code}"
}

fetch_kill_switch_state() {
  local code
  code="$(request_json GET "${BASE_URL}/api/admin/kill-switch" "" "${ADMIN_TOKEN}" "/tmp/c4_kill_switch_state.json")"
  [[ "${code}" == "200" ]] || fail "admin/kill-switch state okunamadı http=${code}"
}

apply_production_limits() {
  fetch_kill_switch_state
  PROD_MAX_TOTAL_EXPOSURE="$(python - <<PY
import json
cfg=json.load(open('/tmp/c4_kill_switch_state.json', encoding='utf-8'))
current=float(cfg.get('max_total_exposure') or 0)
override='${CANARY_C4_MAX_TOTAL_EXPOSURE:-}'
print(float(override) if override else current)
PY
)"
  PROD_MAX_ACTIVE_POSITIONS="$(python - <<PY
import json
cfg=json.load(open('/tmp/c4_kill_switch_state.json', encoding='utf-8'))
current=int(cfg.get('max_active_positions') or 0)
override='${CANARY_C4_MAX_ACTIVE_POSITIONS:-}'
print(int(override) if override else current)
PY
)"

  local payload code
  payload="{\"trading_enabled\":true,\"reason\":\"c4_production_limits_apply\",\"max_total_exposure\":${PROD_MAX_TOTAL_EXPOSURE},\"max_active_positions\":${PROD_MAX_ACTIVE_POSITIONS}}"
  code="$(request_json POST "${BASE_URL}/api/admin/kill-switch" "${payload}" "${ADMIN_TOKEN}" "/tmp/c4_kill_switch_apply.json")"
  [[ "${code}" == "200" ]] || fail "production limits apply başarısız http=${code}"
}

test_order() {
  request_json POST "${BASE_URL}/api/phase4/test-order" "{}" "${USER_TOKEN}" "/tmp/c4_test_order.json"
}

kill_switch_toggle() {
  local trading_enabled="$1"
  local reason="$2"
  local payload code
  payload="{\"trading_enabled\":${trading_enabled},\"reason\":\"${reason}\"}"
  code="$(request_json POST "${BASE_URL}/api/admin/kill-switch" "${payload}" "${ADMIN_TOKEN}" "/tmp/c4_kill_switch.json")"
  [[ "${code}" == "200" ]] || fail "kill-switch toggle başarısız (${reason}) http=${code}"
}

log "C4 START config: all_symbols=enabled production_limits=enabled duration=${RUN_MINUTES}m"

HCODE="$(curl -sS -o /tmp/c4_health_gate.json -w '%{http_code}' "${BASE_URL}/api/health" || true)"
RCODE="$(curl -sS -o /tmp/c4_ready_gate.json -w '%{http_code}' "${BASE_URL}/api/ready" || true)"
[[ "${HCODE}" == "200" ]] || fail "backend health gate fail (api/health=${HCODE})"
[[ "${RCODE}" == "200" ]] || fail "backend ready gate fail (api/ready=${RCODE})"
log "PASS: backend health gate (api/health=200, api/ready=200)"

login_admin
ensure_user_login
set_exchange_keys
load_live_config
update_live_config_full
apply_production_limits
fetch_canary_status
fetch_execution_queue_summary
fetch_universe_monitor
fetch_kill_switch_state
log "PASS: c4 başlangıç status endpoint kontrolleri"

log "Kill-switch faz başı testi"
kill_switch_toggle false "c4_phase_start_kill_test"
BLOCK_CODE="$(test_order || true)"
if [[ "${BLOCK_CODE}" != "400" && "${BLOCK_CODE}" != "403" ]]; then
  fail "kill-switch faz başı reject bekleniyordu http=${BLOCK_CODE}"
fi
python - <<PY
import json
body=json.load(open('/tmp/c4_test_order.json', encoding='utf-8'))
if 'TRADING_DISABLED' not in str(body):
    raise SystemExit(f"kill-switch reject reason beklenen değil: {body}")
print('KILL_SWITCH_START_OK')
PY
kill_switch_toggle true "c4_phase_start_resume"

RUN_START="$(date +%s)"
RUN_END="$((RUN_START + RUN_SECONDS))"

LOOP_COUNT=0
CRASH_COUNT=0
ERROR_5XX_COUNT=0
REJECT_COUNT=0
LATENCY_LIMIT_BREACH_COUNT=0
VIOLATION_BREACH_COUNT=0

ORDER_QUEUE_DEPTH_BREACH_COUNT=0
ORDER_QUEUE_GROWTH_BREACH_COUNT=0
PARALLEL_QUEUE_BREACH_COUNT=0
PARALLEL_LATENCY_BREACH_COUNT=0
PARALLEL_DROPPED_BREACH_COUNT=0

EXPOSURE_BREACH_COUNT=0
ACTIVE_POSITION_BREACH_COUNT=0

MAX_ERROR_RATE=0
MAX_ORDER_FAIL_RATE=0
MAX_REJECT_RATE=0
MAX_LATENCY_P95=0
MAX_PNL_DRIFT=0
PREV_ERROR_RATE=""
ERROR_MONOTONIC_BREAKS=0

MAX_QUEUE_QUEUED=0
MAX_QUEUE_TOTAL=0
PREV_QUEUE_QUEUED=0
QUEUE_GROWTH_STREAK=0

MAX_PARALLEL_QUEUE_DEPTH=0
MAX_PARALLEL_CYCLE_LATENCY=0
MAX_WORKER_UTILIZATION=0
MAX_DROPPED_EVALUATIONS=0

MAX_CURRENT_TOTAL_EXPOSURE=0
MAX_CURRENT_ACTIVE_POSITIONS=0

while [[ "$(date +%s)" -lt "${RUN_END}" ]]; do
  LOOP_COUNT="$((LOOP_COUNT + 1))"

  code="$(test_order || true)"
  if [[ -z "${code}" || "${code}" == "000" ]]; then
    CRASH_COUNT="$((CRASH_COUNT + 1))"
    log "LOOP_${LOOP_COUNT}: crash/network"
  elif [[ "${code}" -ge 500 ]]; then
    ERROR_5XX_COUNT="$((ERROR_5XX_COUNT + 1))"
    log "LOOP_${LOOP_COUNT}: 5xx=${code}"
  elif [[ "${code}" -ge 400 ]]; then
    REJECT_COUNT="$((REJECT_COUNT + 1))"
    log "LOOP_${LOOP_COUNT}: reject=${code}"
  else
    log "LOOP_${LOOP_COUNT}: success=${code}"
  fi

  fetch_canary_status
  fetch_execution_queue_summary
  fetch_universe_monitor
  fetch_kill_switch_state

  python - <<PY | tee -a "${LOG_FILE}"
import json
status=json.load(open('/tmp/c4_canary_status.json', encoding='utf-8'))
queue=json.load(open('/tmp/c4_execution_queue.json', encoding='utf-8'))
um=json.load(open('/tmp/c4_universe_monitor.json', encoding='utf-8'))
ks=json.load(open('/tmp/c4_kill_switch_state.json', encoding='utf-8'))
print('STATUS', status)
print('QUEUE', queue.get('queue', {}))
print('PARALLEL', {
  'queue_depth': um.get('queue_depth'),
  'average_cycle_latency_ms': um.get('average_cycle_latency_ms'),
  'dropped_evaluations': um.get('dropped_evaluations'),
  'worker_utilization': um.get('worker_utilization'),
})
print('EXPOSURE', {
  'current_total_exposure': ks.get('current_total_exposure'),
  'max_total_exposure': ks.get('max_total_exposure'),
  'current_active_positions': ks.get('current_active_positions'),
  'max_active_positions': ks.get('max_active_positions'),
})
PY

  error_rate="$(python - <<PY
import json
s=json.load(open('/tmp/c4_canary_status.json', encoding='utf-8'))
print(float(s.get('error_rate') or 0))
PY
)"
  order_fail_rate="$(python - <<PY
import json
s=json.load(open('/tmp/c4_canary_status.json', encoding='utf-8'))
print(float(s.get('order_fail_rate') or 0))
PY
)"
  reject_rate="$(python - <<PY
import json
s=json.load(open('/tmp/c4_canary_status.json', encoding='utf-8'))
print(float(s.get('reject_rate') or 0))
PY
)"
  latency_p95="$(python - <<PY
import json
s=json.load(open('/tmp/c4_canary_status.json', encoding='utf-8'))
print(float(s.get('latency_ms_p95') or 0))
PY
)"
  pnl_drift="$(python - <<PY
import json
s=json.load(open('/tmp/c4_canary_status.json', encoding='utf-8'))
print(float(s.get('pnl_drift') or 0))
PY
)"
  violations="$(python - <<PY
import json
s=json.load(open('/tmp/c4_canary_status.json', encoding='utf-8'))
print(int(s.get('violations') or 0))
PY
)"

  queue_queued="$(python - <<PY
import json
q=json.load(open('/tmp/c4_execution_queue.json', encoding='utf-8'))
print(int(((q.get('queue') or {}).get('queued')) or 0))
PY
)"
  queue_total="$(python - <<PY
import json
q=json.load(open('/tmp/c4_execution_queue.json', encoding='utf-8'))
print(int(((q.get('queue') or {}).get('total')) or 0))
PY
)"

  parallel_queue_depth="$(python - <<PY
import json
u=json.load(open('/tmp/c4_universe_monitor.json', encoding='utf-8'))
print(int(u.get('queue_depth') or 0))
PY
)"
  parallel_cycle_latency_ms="$(python - <<PY
import json
u=json.load(open('/tmp/c4_universe_monitor.json', encoding='utf-8'))
print(float(u.get('average_cycle_latency_ms') or 0))
PY
)"
  parallel_dropped_evaluations="$(python - <<PY
import json
u=json.load(open('/tmp/c4_universe_monitor.json', encoding='utf-8'))
print(int(u.get('dropped_evaluations') or 0))
PY
)"
  worker_utilization="$(python - <<PY
import json
u=json.load(open('/tmp/c4_universe_monitor.json', encoding='utf-8'))
print(float(u.get('worker_utilization') or 0))
PY
)"

  current_total_exposure="$(python - <<PY
import json
k=json.load(open('/tmp/c4_kill_switch_state.json', encoding='utf-8'))
print(float(k.get('current_total_exposure') or 0))
PY
)"
  max_total_exposure="$(python - <<PY
import json
k=json.load(open('/tmp/c4_kill_switch_state.json', encoding='utf-8'))
print(float(k.get('max_total_exposure') or 0))
PY
)"
  current_active_positions="$(python - <<PY
import json
k=json.load(open('/tmp/c4_kill_switch_state.json', encoding='utf-8'))
print(int(k.get('current_active_positions') or 0))
PY
)"
  max_active_positions="$(python - <<PY
import json
k=json.load(open('/tmp/c4_kill_switch_state.json', encoding='utf-8'))
print(int(k.get('max_active_positions') or 0))
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

  MAX_QUEUE_QUEUED="$(python - <<PY
print(max(int('${MAX_QUEUE_QUEUED}'), int('${queue_queued}')))
PY
)"
  MAX_QUEUE_TOTAL="$(python - <<PY
print(max(int('${MAX_QUEUE_TOTAL}'), int('${queue_total}')))
PY
)"

  MAX_PARALLEL_QUEUE_DEPTH="$(python - <<PY
print(max(int('${MAX_PARALLEL_QUEUE_DEPTH}'), int('${parallel_queue_depth}')))
PY
)"
  MAX_PARALLEL_CYCLE_LATENCY="$(python - <<PY
print(max(float('${MAX_PARALLEL_CYCLE_LATENCY}'), float('${parallel_cycle_latency_ms}')))
PY
)"
  MAX_WORKER_UTILIZATION="$(python - <<PY
print(max(float('${MAX_WORKER_UTILIZATION}'), float('${worker_utilization}')))
PY
)"
  MAX_DROPPED_EVALUATIONS="$(python - <<PY
print(max(int('${MAX_DROPPED_EVALUATIONS}'), int('${parallel_dropped_evaluations}')))
PY
)"

  MAX_CURRENT_TOTAL_EXPOSURE="$(python - <<PY
print(max(float('${MAX_CURRENT_TOTAL_EXPOSURE}'), float('${current_total_exposure}')))
PY
)"
  MAX_CURRENT_ACTIVE_POSITIONS="$(python - <<PY
print(max(int('${MAX_CURRENT_ACTIVE_POSITIONS}'), int('${current_active_positions}')))
PY
)"

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

  if [[ "${queue_queued}" -gt "${ORDER_QUEUE_DEPTH_LIMIT}" ]]; then
    ORDER_QUEUE_DEPTH_BREACH_COUNT="$((ORDER_QUEUE_DEPTH_BREACH_COUNT + 1))"
  fi
  if [[ "${queue_queued}" -gt "${PREV_QUEUE_QUEUED}" ]]; then
    QUEUE_GROWTH_STREAK="$((QUEUE_GROWTH_STREAK + 1))"
  else
    QUEUE_GROWTH_STREAK=0
  fi
  if [[ "${QUEUE_GROWTH_STREAK}" -gt "${ORDER_QUEUE_GROWTH_STREAK_LIMIT}" ]]; then
    ORDER_QUEUE_GROWTH_BREACH_COUNT="$((ORDER_QUEUE_GROWTH_BREACH_COUNT + 1))"
  fi
  PREV_QUEUE_QUEUED="${queue_queued}"

  if [[ "${parallel_queue_depth}" -gt "${PARALLEL_QUEUE_DEPTH_LIMIT}" ]]; then
    PARALLEL_QUEUE_BREACH_COUNT="$((PARALLEL_QUEUE_BREACH_COUNT + 1))"
  fi
  if ! python - <<PY
if float('${parallel_cycle_latency_ms}') < ${PARALLEL_CYCLE_LATENCY_LIMIT}:
    raise SystemExit(0)
raise SystemExit(1)
PY
  then
    PARALLEL_LATENCY_BREACH_COUNT="$((PARALLEL_LATENCY_BREACH_COUNT + 1))"
  fi
  if [[ "${parallel_dropped_evaluations}" -gt "${PARALLEL_DROPPED_EVAL_LIMIT}" ]]; then
    PARALLEL_DROPPED_BREACH_COUNT="$((PARALLEL_DROPPED_BREACH_COUNT + 1))"
  fi

  if ! python - <<PY
curr=float('${current_total_exposure}')
lim=float('${max_total_exposure}')
if curr <= (lim + 1e-9):
    raise SystemExit(0)
raise SystemExit(1)
PY
  then
    EXPOSURE_BREACH_COUNT="$((EXPOSURE_BREACH_COUNT + 1))"
  fi
  if [[ "${current_active_positions}" -gt "${max_active_positions}" ]]; then
    ACTIVE_POSITION_BREACH_COUNT="$((ACTIVE_POSITION_BREACH_COUNT + 1))"
  fi

  sleep "${INTERVAL_SECONDS}"
done

DURATION_MINUTES="$(( ( $(date +%s) - RUN_START ) / 60 ))"
[[ "${DURATION_MINUTES}" -ge 120 ]] || fail "C4 süresi 120dk altında (${DURATION_MINUTES})"
[[ "${LOOP_COUNT}" -ge 20 ]] || fail "minimum 20 loop sağlanmadı (${LOOP_COUNT})"

log "Kill-switch faz sonu testi"
kill_switch_toggle false "c4_phase_end_kill_test"
END_BLOCK_CODE="$(test_order || true)"
if [[ "${END_BLOCK_CODE}" != "400" && "${END_BLOCK_CODE}" != "403" ]]; then
  fail "kill-switch faz sonu reject bekleniyordu http=${END_BLOCK_CODE}"
fi
python - <<PY
import json
body=json.load(open('/tmp/c4_test_order.json', encoding='utf-8'))
if 'TRADING_DISABLED' not in str(body):
    raise SystemExit(f"kill-switch end reject reason beklenen değil: {body}")
print('KILL_SWITCH_END_OK')
PY
kill_switch_toggle true "c4_phase_end_resume"

HEALTH_CODE="$(curl -sS -o /tmp/c4_health.json -w '%{http_code}' "${BASE_URL}/api/health" || true)"
READY_CODE="$(curl -sS -o /tmp/c4_ready.json -w '%{http_code}' "${BASE_URL}/api/ready" || true)"
[[ "${HEALTH_CODE}" == "200" ]] || fail "health 200 değil"
[[ "${READY_CODE}" == "200" ]] || fail "ready 200 değil"

if [[ "${CRASH_COUNT}" -ne 0 ]]; then fail "crash_count=${CRASH_COUNT}"; fi
if [[ "${ERROR_5XX_COUNT}" -ne 0 ]]; then fail "error_5xx_count=${ERROR_5XX_COUNT}"; fi
if [[ "${REJECT_COUNT}" -ne 0 ]]; then fail "reject_count=${REJECT_COUNT}"; fi
if [[ "${VIOLATION_BREACH_COUNT}" -ne 0 ]]; then fail "violations>0 count=${VIOLATION_BREACH_COUNT}"; fi
if [[ "${LATENCY_LIMIT_BREACH_COUNT}" -ne 0 ]]; then fail "latency_limit_breach_count=${LATENCY_LIMIT_BREACH_COUNT}"; fi
if [[ "${ERROR_MONOTONIC_BREAKS}" -ne 0 ]]; then fail "error_rate_monotonic_breaks=${ERROR_MONOTONIC_BREAKS}"; fi

if [[ "${ORDER_QUEUE_DEPTH_BREACH_COUNT}" -ne 0 ]]; then fail "order_queue_depth_breach_count=${ORDER_QUEUE_DEPTH_BREACH_COUNT}"; fi
if [[ "${ORDER_QUEUE_GROWTH_BREACH_COUNT}" -ne 0 ]]; then fail "order_queue_growth_breach_count=${ORDER_QUEUE_GROWTH_BREACH_COUNT}"; fi
if [[ "${PARALLEL_QUEUE_BREACH_COUNT}" -ne 0 ]]; then fail "parallel_queue_breach_count=${PARALLEL_QUEUE_BREACH_COUNT}"; fi
if [[ "${PARALLEL_LATENCY_BREACH_COUNT}" -ne 0 ]]; then fail "parallel_latency_breach_count=${PARALLEL_LATENCY_BREACH_COUNT}"; fi
if [[ "${PARALLEL_DROPPED_BREACH_COUNT}" -ne 0 ]]; then fail "parallel_dropped_breach_count=${PARALLEL_DROPPED_BREACH_COUNT}"; fi

if [[ "${EXPOSURE_BREACH_COUNT}" -ne 0 ]]; then fail "exposure_breach_count=${EXPOSURE_BREACH_COUNT}"; fi
if [[ "${ACTIVE_POSITION_BREACH_COUNT}" -ne 0 ]]; then fail "active_position_breach_count=${ACTIVE_POSITION_BREACH_COUNT}"; fi

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
  "phase": "C4",
  "canary_rollout_test": "PASS",
  "scope": "all_symbols_full_enable",
  "capital_usdt": float('${PROD_CANARY_CAPITAL:-0}'),
  "max_positions": int('${PROD_CANARY_MAX_POSITIONS:-0}'),
  "production_max_total_exposure": float('${PROD_MAX_TOTAL_EXPOSURE:-0}'),
  "production_max_active_positions": int('${PROD_MAX_ACTIVE_POSITIONS:-0}'),
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
  "order_queue_behavior": "PASS",
  "execution_latency_check": "PASS",
  "parallel_processing_stability": "PASS",
  "exposure_distribution_check": "PASS",
  "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
with open('${SUMMARY_JSON}', 'w', encoding='utf-8') as f:
  json.dump(summary, f, ensure_ascii=False, indent=2)

metrics = {
  "phase": "C4",
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
  "order_queue": {
    "max_queued": int('${MAX_QUEUE_QUEUED}'),
    "max_total": int('${MAX_QUEUE_TOTAL}'),
    "queue_depth_limit": int('${ORDER_QUEUE_DEPTH_LIMIT}'),
    "queue_depth_breach_count": int('${ORDER_QUEUE_DEPTH_BREACH_COUNT}'),
    "queue_growth_streak_limit": int('${ORDER_QUEUE_GROWTH_STREAK_LIMIT}'),
    "queue_growth_breach_count": int('${ORDER_QUEUE_GROWTH_BREACH_COUNT}'),
  },
  "parallel_stability": {
    "max_queue_depth": int('${MAX_PARALLEL_QUEUE_DEPTH}'),
    "queue_depth_limit": int('${PARALLEL_QUEUE_DEPTH_LIMIT}'),
    "queue_depth_breach_count": int('${PARALLEL_QUEUE_BREACH_COUNT}'),
    "max_average_cycle_latency_ms": float('${MAX_PARALLEL_CYCLE_LATENCY}'),
    "average_cycle_latency_limit_ms": int('${PARALLEL_CYCLE_LATENCY_LIMIT}'),
    "average_cycle_latency_breach_count": int('${PARALLEL_LATENCY_BREACH_COUNT}'),
    "max_dropped_evaluations": int('${MAX_DROPPED_EVALUATIONS}'),
    "dropped_evaluations_limit": int('${PARALLEL_DROPPED_EVAL_LIMIT}'),
    "dropped_evaluations_breach_count": int('${PARALLEL_DROPPED_BREACH_COUNT}'),
    "max_worker_utilization": float('${MAX_WORKER_UTILIZATION}'),
  },
  "exposure_distribution": {
    "max_current_total_exposure": float('${MAX_CURRENT_TOTAL_EXPOSURE}'),
    "max_total_exposure_limit": float('${PROD_MAX_TOTAL_EXPOSURE:-0}'),
    "exposure_breach_count": int('${EXPOSURE_BREACH_COUNT}'),
    "max_current_active_positions": int('${MAX_CURRENT_ACTIVE_POSITIONS}'),
    "max_active_positions_limit": int('${PROD_MAX_ACTIVE_POSITIONS:-0}'),
    "active_position_breach_count": int('${ACTIVE_POSITION_BREACH_COUNT}'),
  },
  "health_http": int('${HEALTH_CODE}'),
  "ready_http": int('${READY_CODE}'),
  "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
with open('${METRICS_JSON}', 'w', encoding='utf-8') as f:
  json.dump(metrics, f, ensure_ascii=False, indent=2)
PY

log "SUMMARY: PASS"
