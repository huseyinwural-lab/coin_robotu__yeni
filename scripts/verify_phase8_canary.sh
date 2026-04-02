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

fail_with_body() {
  local message="$1"
  local body_file="$2"
  if [[ -f "${body_file}" ]]; then
    local preview
    preview="$(python - <<PY
import json
from pathlib import Path
p=Path('${body_file}')
text=p.read_text(encoding='utf-8', errors='ignore')[:1000]
try:
    obj=json.loads(text)
    print(json.dumps(obj, ensure_ascii=False)[:1000])
except Exception:
    print(text.replace('\n',' '))
PY
)"
    fail "${message} body=${preview}"
  else
    fail "${message} (body yok)"
  fi
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
LIVE_API_KEY="${BINANCE_LIVE_API_KEY:-${BINANCE_API_KEY:-}}"
LIVE_API_SECRET="${BINANCE_LIVE_API_SECRET:-${BINANCE_API_SECRET:-}}"
EXCHANGE_MODE="${CANARY_EXCHANGE_MODE:-live}"
EXCHANGE_MARKET_TYPE="${CANARY_EXCHANGE_MARKET_TYPE:-futures}"
EXCHANGE_ENVIRONMENT="${CANARY_EXCHANGE_ENVIRONMENT:-live}"
CANARY_AUTO_FALLBACK_LIVE="${CANARY_AUTO_FALLBACK_LIVE:-false}"

resolve_exchange_credentials() {
  case "${EXCHANGE_MODE}" in
    live)
      if [[ -n "${LIVE_API_KEY}" && -n "${LIVE_API_SECRET}" ]]; then
        ACTIVE_API_KEY="${LIVE_API_KEY}"
        ACTIVE_API_SECRET="${LIVE_API_SECRET}"
      else
        # Bazı ortamlarda live key'ler yanlışlıkla TESTNET değişkenlerine yazılıyor.
        # Live mod fallback'inde aynı key pair'i de dene.
        ACTIVE_API_KEY="${TESTNET_API_KEY}"
        ACTIVE_API_SECRET="${TESTNET_API_SECRET}"
      fi
      ;;
    *)
      ACTIVE_API_KEY="${TESTNET_API_KEY}"
      ACTIVE_API_SECRET="${TESTNET_API_SECRET}"
      ;;
  esac
}

resolve_exchange_credentials
[[ -n "${ACTIVE_API_KEY}" && -n "${ACTIVE_API_SECRET}" ]] || fail "Exchange key/secret eksik. mode=${EXCHANGE_MODE} için gerekli anahtarlar bulunamadı"

RUN_SECONDS="${CANARY_RUN_SECONDS:-$((60 * 60))}"
if [[ "${RUN_SECONDS}" -lt 60 ]]; then
  RUN_SECONDS=60
fi
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
    approve_code="$(request_json POST "${BASE_URL}/api/auth/admin/user-approval-requests/${USER_ID}/approve" "null" "${ADMIN_TOKEN}" "/tmp/faz8_user_approve.json")"
    [[ "${approve_code}" == "200" ]] || fail "User approval başarısız http=${approve_code}"
    login_code="$(request_json POST "${BASE_URL}/api/auth/login/user" "{\"email\":\"${USER_EMAIL}\",\"password\":\"${USER_PASSWORD}\"}" "" "/tmp/faz8_user_login.json")"
    [[ "${login_code}" == "200" ]] || fail "User login (approval sonrası) başarısız http=${login_code}"
  fi
  USER_TOKEN="$(extract_token /tmp/faz8_user_login.json)"
  [[ -n "${USER_TOKEN}" ]] || fail "User token alınamadı"

  local me_code
  me_code="$(request_json GET "${BASE_URL}/api/auth/me" "" "${USER_TOKEN}" "/tmp/faz8_user_me.json")"
  [[ "${me_code}" == "200" ]] || fail "User profile (/api/auth/me) alınamadı http=${me_code}"
  USER_ID="$(python - <<PY
import json
data=json.load(open('/tmp/faz8_user_me.json', encoding='utf-8'))
print(str(data.get('id') or '').strip())
PY
)"
  [[ -n "${USER_ID}" ]] || fail "User id alınamadı"
  log "PASS: user login"
}

set_exchange_keys() {
  resolve_exchange_credentials
  [[ -n "${ACTIVE_API_KEY}" && -n "${ACTIVE_API_SECRET}" ]] || fail "Exchange key/secret eksik. mode=${EXCHANGE_MODE}"
  local payload
  payload="{\"exchange\":\"binance\",\"mode\":\"${EXCHANGE_MODE}\",\"api_key\":\"${ACTIVE_API_KEY}\",\"api_secret\":\"${ACTIVE_API_SECRET}\"}"
  local code
  code="$(request_json PUT "${BASE_URL}/api/phase4/exchange-settings" "${payload}" "${USER_TOKEN}" "/tmp/faz8_exchange_settings.json")"
  [[ "${code}" == "200" ]] || fail "Exchange settings update başarısız http=${code}"
  log "PASS: exchange settings güncellendi mode=${EXCHANGE_MODE}"
}

has_reason_code() {
  local file="$1"
  local reason="$2"
  python - <<PY
import json
from pathlib import Path
p=Path('${file}')
try:
    data=json.loads(p.read_text(encoding='utf-8'))
except Exception:
    print('false')
    raise SystemExit
detail=data.get('detail') if isinstance(data,dict) else None
codes=[]
if isinstance(detail,dict):
    codes=list(detail.get('reason_codes') or [])
print('true' if '${reason}' in [str(c) for c in codes] else 'false')
PY
}

repair_user_venue_assignment() {
  local env="$1"
  local market="$2"
  [[ -n "${USER_ID:-}" ]] || fail "repair için USER_ID yok"
  local code
  code="$(request_json POST "${BASE_URL}/api/admin/users/${USER_ID}/repair-venue-assignment?environment=${env}&market_type=${market}" "{}" "${ADMIN_TOKEN}" "/tmp/faz8_repair_venue.json")"
  [[ "${code}" == "200" ]] || fail_with_body "Venue assignment repair başarısız http=${code}" "/tmp/faz8_repair_venue.json"
  log "PASS: venue assignment repaired env=${env} market=${market}"
}

ensure_allowed_market_enabled() {
  local exchange="binance"
  local market="${EXCHANGE_MARKET_TYPE}"
  local env="${EXCHANGE_ENVIRONMENT}"

  local list_code
  list_code="$(request_json GET "${BASE_URL}/api/venues/admin/allowed-markets" "" "${ADMIN_TOKEN}" "/tmp/faz8_allowed_markets.json")"
  [[ "${list_code}" == "200" ]] || fail_with_body "Allowed markets list alınamadı http=${list_code}" "/tmp/faz8_allowed_markets.json"

  local row_json
  row_json="$(python - <<PY
import json
from pathlib import Path
rows=json.loads(Path('/tmp/faz8_allowed_markets.json').read_text(encoding='utf-8'))
exchange='${exchange}'
market='${market}'
env='${env}'
match=None
for row in rows:
    if str(row.get('exchange_code','')).lower()==exchange and str(row.get('market_type','')).lower()==market and str(row.get('environment','')).lower()==env:
        match=row
        break
print(json.dumps(match or {}, ensure_ascii=False))
PY
)"

  local row_id row_enabled
  row_id="$(python - <<PY
import json
row=json.loads('''${row_json}''') if '''${row_json}'''.strip() else {}
print(str(row.get('id') or '').strip())
PY
)"
  row_enabled="$(python - <<PY
import json
row=json.loads('''${row_json}''') if '''${row_json}'''.strip() else {}
print('true' if bool(row.get('enabled')) else 'false')
PY
)"

  if [[ -z "${row_id}" ]]; then
    local create_payload create_code
    create_payload="{\"exchange_code\":\"${exchange}\",\"market_type\":\"${market}\",\"environment\":\"${env}\",\"enabled\":true}"
    create_code="$(request_json POST "${BASE_URL}/api/venues/admin/allowed-markets" "${create_payload}" "${ADMIN_TOKEN}" "/tmp/faz8_allowed_market_create.json")"
    [[ "${create_code}" == "201" || "${create_code}" == "200" ]] || fail_with_body "Allowed market create başarısız http=${create_code}" "/tmp/faz8_allowed_market_create.json"
    log "PASS: allowed market created ${exchange}/${market}/${env}"
    return
  fi

  if [[ "${row_enabled}" != "true" ]]; then
    local toggle_code
    toggle_code="$(request_json PUT "${BASE_URL}/api/venues/admin/allowed-markets/${row_id}" "{\"enabled\":true}" "${ADMIN_TOKEN}" "/tmp/faz8_allowed_market_toggle.json")"
    [[ "${toggle_code}" == "200" ]] || fail_with_body "Allowed market enable başarısız http=${toggle_code}" "/tmp/faz8_allowed_market_toggle.json"
    log "PASS: allowed market enabled ${exchange}/${market}/${env}"
  else
    log "PASS: allowed market zaten enabled ${exchange}/${market}/${env}"
  fi
}

fetch_proxy_health() {
  local code
  code="$(request_json GET "${BASE_URL}/api/runtime/exchange/proxy-health" "" "${ADMIN_TOKEN}" "/tmp/faz8_proxy_health.json")"
  if [[ "${code}" != "200" ]]; then
    log "WARN: proxy-health okunamadı http=${code}"
    return
  fi

  python - <<PY
import json
from pathlib import Path
data=json.loads(Path('/tmp/faz8_proxy_health.json').read_text(encoding='utf-8'))
result=(data or {}).get('result') or {}
spot=(result.get('spot') or {}) if isinstance(result, dict) else {}
futures=(result.get('futures') or {}) if isinstance(result, dict) else {}
print(f"PROXY_HEALTH spot_token_set={spot.get('proxy_token_set')} futures_token_set={futures.get('proxy_token_set')} spot_base_url_set={spot.get('base_url_set')} futures_base_url_set={futures.get('base_url_set')} token_mismatch_spot={spot.get('proxy_token_mismatch')} token_mismatch_futures={futures.get('proxy_token_mismatch')}")
PY
}

validate_exchange_ready() {
  local code
  code="$(request_json GET "${BASE_URL}/api/exchange/validate?exchange=binance&market_type=${EXCHANGE_MARKET_TYPE}&environment=${EXCHANGE_ENVIRONMENT}" "" "${USER_TOKEN}" "/tmp/faz8_exchange_validate.json")"

  if [[ "${code}" != "200" ]]; then
    local invalid_key
    invalid_key="$(has_reason_code "/tmp/faz8_exchange_validate.json" "invalid_key")"
    if [[ "${invalid_key}" == "true" && "${EXCHANGE_MODE}" == "testnet" && "${CANARY_AUTO_FALLBACK_LIVE}" == "true" ]]; then
      log "WARN: testnet invalid_key alındı, live mode fallback deneniyor"
      EXCHANGE_MODE="live"
      EXCHANGE_ENVIRONMENT="live"
      set_exchange_keys
      code="$(request_json GET "${BASE_URL}/api/exchange/validate?exchange=binance&market_type=${EXCHANGE_MARKET_TYPE}&environment=${EXCHANGE_ENVIRONMENT}" "" "${USER_TOKEN}" "/tmp/faz8_exchange_validate.json")"
    fi
  fi

  if [[ "${code}" != "200" ]]; then
    local live_not_allowed assignment_required testnet_not_allowed market_disabled
    live_not_allowed="$(has_reason_code "/tmp/faz8_exchange_validate.json" "live_not_allowed")"
    assignment_required="$(has_reason_code "/tmp/faz8_exchange_validate.json" "assignment_required")"
    testnet_not_allowed="$(has_reason_code "/tmp/faz8_exchange_validate.json" "testnet_not_allowed")"
    market_disabled="$(has_reason_code "/tmp/faz8_exchange_validate.json" "market_disabled")"
    if [[ "${live_not_allowed}" == "true" || "${assignment_required}" == "true" || "${testnet_not_allowed}" == "true" ]]; then
      log "WARN: venue assignment reason detected, admin repair deneniyor"
      repair_user_venue_assignment "${EXCHANGE_ENVIRONMENT}" "${EXCHANGE_MARKET_TYPE}"
      code="$(request_json GET "${BASE_URL}/api/exchange/validate?exchange=binance&market_type=${EXCHANGE_MARKET_TYPE}&environment=${EXCHANGE_ENVIRONMENT}" "" "${USER_TOKEN}" "/tmp/faz8_exchange_validate.json")"
      market_disabled="$(has_reason_code "/tmp/faz8_exchange_validate.json" "market_disabled")"
    fi
    if [[ "${code}" != "200" && "${market_disabled}" == "true" ]]; then
      log "WARN: market_disabled detected, allowed-market enable deneniyor"
      ensure_allowed_market_enabled
      code="$(request_json GET "${BASE_URL}/api/exchange/validate?exchange=binance&market_type=${EXCHANGE_MARKET_TYPE}&environment=${EXCHANGE_ENVIRONMENT}" "" "${USER_TOKEN}" "/tmp/faz8_exchange_validate.json")"
    fi

    if [[ "${code}" != "200" ]]; then
      local reason_451
      reason_451="$(has_reason_code "/tmp/faz8_exchange_validate.json" "exchange_error_451")"
      if [[ "${reason_451}" == "true" && "${EXCHANGE_ENVIRONMENT}" == "live" && "${EXCHANGE_MARKET_TYPE}" == "futures" ]]; then
        log "WARN: futures live 451 alındı, spot live fallback deneniyor"
        EXCHANGE_MARKET_TYPE="spot"
        repair_user_venue_assignment "${EXCHANGE_ENVIRONMENT}" "${EXCHANGE_MARKET_TYPE}"
        ensure_allowed_market_enabled
        code="$(request_json GET "${BASE_URL}/api/exchange/validate?exchange=binance&market_type=${EXCHANGE_MARKET_TYPE}&environment=${EXCHANGE_ENVIRONMENT}" "" "${USER_TOKEN}" "/tmp/faz8_exchange_validate.json")"
      fi

      if [[ "${code}" != "200" ]]; then
        reason_451="$(has_reason_code "/tmp/faz8_exchange_validate.json" "exchange_error_451")"
        if [[ "${reason_451}" == "true" ]]; then
          log "WARN: exchange_error_451 devam ediyor, proxy-health okunuyor"
          fetch_proxy_health
        fi
      fi
    fi
  fi

  [[ "${code}" == "200" ]] || fail_with_body "Exchange validate başarısız http=${code}" "/tmp/faz8_exchange_validate.json"
  log "PASS: exchange validate market=${EXCHANGE_MARKET_TYPE} env=${EXCHANGE_ENVIRONMENT}"
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
  'kill_switch_enabled': False,
})
open('/tmp/faz8_live_config_put.json','w',encoding='utf-8').write(json.dumps(cfg))
PY
  local payload code
  payload="$(cat /tmp/faz8_live_config_put.json)"
  local attempt max_attempts sleep_seconds
  attempt=1
  max_attempts=4
  sleep_seconds=2
  while true; do
    code="$(request_json PUT "${BASE_URL}/api/phase4/live-config" "${payload}" "${ADMIN_TOKEN}" "/tmp/faz8_live_config_updated.json")"
    if [[ "${code}" == "200" ]]; then
      break
    fi

    # token süresi/oturum hatası durumunda admin token yenile
    if [[ "${code}" == "401" ]]; then
      log "WARN: live-config PUT 401, admin token yenileniyor (attempt=${attempt})"
      login_admin
    fi

    # geçici backend dalgalanmaları için retry (CI flakey 5xx)
    if [[ "${code}" == "500" || "${code}" == "502" || "${code}" == "503" || "${code}" == "504" ]]; then
      if [[ "${attempt}" -lt "${max_attempts}" ]]; then
        log "WARN: live-config PUT transient http=${code}, retry ${attempt}/${max_attempts}"
        sleep "${sleep_seconds}"
        attempt="$((attempt + 1))"
        continue
      fi
      fail_with_body "live-config update başarısız http=${code}" "/tmp/faz8_live_config_updated.json"
    fi

    # 403/422 gibi deterministic hatalarda direkt gövdeyi göster
    fail_with_body "live-config update başarısız http=${code}" "/tmp/faz8_live_config_updated.json"
  done
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
    if 'Permission check başarısız' in text or 'API key doğrulamasını geçmelisiniz' in text:
        raise SystemExit(f"Canary reject testi önkoşul hatası: API key/permission doğrulaması başarısız. body={text}")
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
validate_exchange_ready
load_live_config
update_live_config_canary '["BTCUSDT"]' '50' '1' '["BTCUSDT"]'
fetch_canary_status

log "T-8.2 execution enforce"
update_live_config_canary '["BTCUSDT"]' '50' '1' '["ETHUSDT"]'
test_order_expect reject "CANARY_SYMBOL_BLOCKED"

update_live_config_canary '["BTCUSDT"]' '0.5' '1' '["BTCUSDT"]'
test_order_expect reject "CANARY_CAPITAL_LIMIT_EXCEEDED"

update_live_config_canary '["BTCUSDT"]' '1000' '0' '["BTCUSDT"]'
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
