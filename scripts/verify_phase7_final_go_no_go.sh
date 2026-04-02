#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ARTIFACT_DIR="${APP_ROOT}/artifacts"
LOG_FILE="${ARTIFACT_DIR}/faz7_final_go_no_go.log"
SUMMARY_JSON="${ARTIFACT_DIR}/faz7_final_go_no_go_summary.json"
EVIDENCE_JSON="${ARTIFACT_DIR}/faz7_final_go_no_go_evidence.json"

mkdir -p "${ARTIFACT_DIR}"
: > "${LOG_FILE}"

PHASE7_REQUIRE_CANARY="${PHASE7_REQUIRE_CANARY:-true}"
PHASE7_REQUIRE_ALERT_EVIDENCE="${PHASE7_REQUIRE_ALERT_EVIDENCE:-true}"
PHASE7_PREFLIGHT_STRICT="${PHASE7_PREFLIGHT_STRICT:-false}"
PHASE7_RUNTIME_PREFLIGHT="${PHASE7_RUNTIME_PREFLIGHT:-false}"
PHASE7_CANARY_EXCHANGE_UNREACHABLE_BYPASS="${PHASE7_CANARY_EXCHANGE_UNREACHABLE_BYPASS:-true}"

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" | tee -a "${LOG_FILE}" >&2
}

run_step() {
  local key="$1"
  shift
  local step_log="${ARTIFACT_DIR}/faz7_${key}.log"
  log "STEP ${key} başladı"
  if "$@" >"${step_log}" 2>&1; then
    log "STEP ${key} PASS"
    echo "PASS"
  else
    log "STEP ${key} FAIL"
    echo "FAIL"
  fi
}

load_env_value() {
  local key="$1"
  python - <<PY
from pathlib import Path
key='${key}'
env=Path('/app/backend/.env')
if env.exists():
    for raw in env.read_text(encoding='utf-8', errors='ignore').splitlines():
        line=raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k,v=line.split('=',1)
        if k.strip()==key:
            print(v.strip().strip('"').strip("'"))
            break
PY
}

ensure_canary_keys() {
  local live_key="${BINANCE_LIVE_API_KEY:-}"
  local live_secret="${BINANCE_LIVE_API_SECRET:-}"
  local generic_key="${BINANCE_API_KEY:-}"
  local generic_secret="${BINANCE_API_SECRET:-}"

  if [[ -z "${generic_key}" ]]; then
    generic_key="$(load_env_value BINANCE_API_KEY)"
  fi
  if [[ -z "${generic_secret}" ]]; then
    generic_secret="$(load_env_value BINANCE_API_SECRET)"
  fi

  if [[ -z "${live_key}" ]]; then
    live_key="${generic_key}"
  fi
  if [[ -z "${live_secret}" ]]; then
    live_secret="${generic_secret}"
  fi

  if [[ -z "${live_key}" ]]; then
    live_key="$(load_env_value BINANCE_LIVE_API_KEY)"
  fi
  if [[ -z "${live_secret}" ]]; then
    live_secret="$(load_env_value BINANCE_LIVE_API_SECRET)"
  fi

  [[ -n "${generic_key}" ]] && export BINANCE_API_KEY="${generic_key}"
  [[ -n "${generic_secret}" ]] && export BINANCE_API_SECRET="${generic_secret}"
  [[ -n "${live_key}" ]] && export BINANCE_LIVE_API_KEY="${live_key}"
  [[ -n "${live_secret}" ]] && export BINANCE_LIVE_API_SECRET="${live_secret}"
}

export REACT_APP_BACKEND_URL="${REACT_APP_BACKEND_URL:-http://127.0.0.1:8001}"

phase56_status="$(run_step phase56_closure bash "${APP_ROOT}/scripts/verify_phase5_phase6_closure.sh")"
preflight_status="$(run_step preflight env STRICT_PREFLIGHT_ENV_CHECKS="${PHASE7_PREFLIGHT_STRICT}" ENABLE_RUNTIME_PREFLIGHT_CHECKS="${PHASE7_RUNTIME_PREFLIGHT}" bash "${APP_ROOT}/scripts/preflight_prod_env_check.sh")"

if [[ "${PHASE7_REQUIRE_CANARY}" == "true" ]]; then
  ensure_canary_keys
  canary_status="$(run_step phase8_canary env CANARY_RUN_SECONDS="${CANARY_RUN_SECONDS:-120}" CANARY_LOOP_INTERVAL_SECONDS="${CANARY_LOOP_INTERVAL_SECONDS:-30}" bash "${APP_ROOT}/scripts/verify_phase8_canary.sh")"
else
  log "STEP phase8_canary SKIPPED (PHASE7_REQUIRE_CANARY=false)"
  canary_status="SKIPPED"
fi

gate_status="$(run_step final_release_gate bash "${APP_ROOT}/scripts/final_release_gate_report.sh")"

live_readiness_status="$(run_step live_readiness python - <<'PY'
import json
import os
import requests
from pathlib import Path

base = (os.environ.get('REACT_APP_BACKEND_URL') or '').strip().rstrip('/')
if not base:
    base = 'http://127.0.0.1:8001'

email = os.environ.get('TEST_ADMIN_EMAIL', 'canary.admin@platform.local')
password = os.environ.get('TEST_ADMIN_PASSWORD', 'CanaryAdmin123!')

session = requests.Session()
device = 'phase7-live-readiness-device'
login = session.post(
    f'{base}/api/auth/login/admin',
    json={'email': email, 'password': password},
    headers={'X-Session-Device': device},
    timeout=30,
)
if login.status_code != 200:
    raise SystemExit(f'login_failed:{login.status_code}:{login.text[:160]}')

token = (login.json() or {}).get('access_token')
if not token:
    raise SystemExit('token_missing')

resp = session.get(
    f'{base}/api/admin/execution-readiness',
    headers={'Authorization': f'Bearer {token}', 'X-Session-Device': device},
    timeout=60,
)
if resp.status_code != 200:
    raise SystemExit(f'execution_readiness_failed:{resp.status_code}:{resp.text[:160]}')

payload = resp.json()

venue_resp = session.get(
    f'{base}/api/admin/futures/live-readiness',
    headers={'Authorization': f'Bearer {token}', 'X-Session-Device': device},
    timeout=60,
)
venue_payload = venue_resp.json() if venue_resp.status_code == 200 else {}

out = {
    'required_venues': venue_payload.get('required_venues') or ['binance'],
    'venue_policy': venue_payload.get('venue_policy') or 'binance_only',
    'go_live_allowed': bool(payload.get('go_live_allowed')),
    'final_status': payload.get('final_status'),
    'execution_readiness_http': resp.status_code,
    'venue_readiness_http': venue_resp.status_code,
}
Path('/app/artifacts/faz7_live_readiness_snapshot.json').write_text(
    json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
)
if not out['go_live_allowed']:
    raise SystemExit('go_live_allowed_false')
PY
)"

alert_status="PASS"
if [[ "${PHASE7_REQUIRE_ALERT_EVIDENCE}" == "true" ]]; then
  alert_status="$(run_step alert_evidence python - <<'PY'
import json
from pathlib import Path

alert_path = Path('/app/artifacts/faz5_alert_delivery.log')
if not alert_path.exists():
    raise SystemExit('alert_delivery_log_missing')

text = alert_path.read_text(encoding='utf-8', errors='ignore').strip()
if len(text) == 0:
    raise SystemExit('alert_delivery_log_empty')

out = {
    'path': str(alert_path),
    'size_bytes': alert_path.stat().st_size,
    'has_probe_keyword': 'PHASE5_PROBE' in text,
    'line_count': len(text.splitlines()),
}
Path('/app/artifacts/faz7_alert_evidence_snapshot.json').write_text(
    json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
)
PY
)"
else
  alert_status="SKIPPED"
fi

export PHASE56_STATUS="${phase56_status}"
export PREFLIGHT_STATUS="${preflight_status}"
export CANARY_STATUS="${canary_status}"
export GATE_STATUS="${gate_status}"
export LIVE_READINESS_STATUS="${live_readiness_status}"
export ALERT_STATUS="${alert_status}"
export PHASE7_CANARY_EXCHANGE_UNREACHABLE_BYPASS

python - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

artifact_dir = Path('/app/artifacts')
summary_json = Path('/app/artifacts/faz7_final_go_no_go_summary.json')
evidence_json = Path('/app/artifacts/faz7_final_go_no_go_evidence.json')

phase56_status = os.environ.get('PHASE56_STATUS', 'FAIL')
preflight_status = os.environ.get('PREFLIGHT_STATUS', 'FAIL')
canary_status = os.environ.get('CANARY_STATUS', 'FAIL')
gate_status = os.environ.get('GATE_STATUS', 'FAIL')
live_readiness_status = os.environ.get('LIVE_READINESS_STATUS', 'FAIL')
alert_status = os.environ.get('ALERT_STATUS', 'FAIL')
require_canary = os.environ.get('PHASE7_REQUIRE_CANARY', 'true').lower() == 'true'
require_alert = os.environ.get('PHASE7_REQUIRE_ALERT_EVIDENCE', 'true').lower() == 'true'
allow_exchange_unreachable_bypass = os.environ.get('PHASE7_CANARY_EXCHANGE_UNREACHABLE_BYPASS', 'true').lower() == 'true'

final_report = {}
final_report_path = artifact_dir / 'final_release_gate_report.json'
if final_report_path.exists():
    final_report = json.loads(final_report_path.read_text(encoding='utf-8'))

gate_snapshot = {}
gate_snapshot_path = artifact_dir / 'final' / 'production_gate_snapshot.json'
if gate_snapshot_path.exists():
    gate_snapshot = json.loads(gate_snapshot_path.read_text(encoding='utf-8'))

canary_summary = {}
canary_summary_path = artifact_dir / 'faz8_canary_summary.json'
if canary_summary_path.exists():
    canary_summary = json.loads(canary_summary_path.read_text(encoding='utf-8'))

phase56_summary = {}
phase56_summary_path = artifact_dir / 'phase5_phase6_closure_check.json'
if phase56_summary_path.exists():
    phase56_summary = json.loads(phase56_summary_path.read_text(encoding='utf-8'))

live_readiness_snapshot = {}
live_readiness_path = artifact_dir / 'faz7_live_readiness_snapshot.json'
if live_readiness_path.exists():
    live_readiness_snapshot = json.loads(live_readiness_path.read_text(encoding='utf-8'))

alert_snapshot = {}
alert_snapshot_path = artifact_dir / 'faz7_alert_evidence_snapshot.json'
if alert_snapshot_path.exists():
    alert_snapshot = json.loads(alert_snapshot_path.read_text(encoding='utf-8'))

rule_gate = (
    str(gate_snapshot.get('configured_state') or '').upper() == 'GO'
    and str(gate_snapshot.get('effective_state') or '').upper() == 'GO'
    and bool(gate_snapshot.get('deploy_allowed'))
)

rule_final_report = str(final_report.get('final_decision') or '').upper() == 'GO'
rule_phase56 = str(phase56_summary.get('overall_status') or '').upper() == 'PASS'
rule_preflight = preflight_status == 'PASS'
rule_live_readiness = bool(live_readiness_snapshot.get('go_live_allowed')) and str(live_readiness_snapshot.get('final_status') or '').upper() == 'READY'

canary_bypass_applied = False
effective_canary_status = canary_status
if require_canary and canary_status != 'PASS' and allow_exchange_unreachable_bypass:
    canary_log_path = artifact_dir / 'faz7_phase8_canary.log'
    canary_log_text = canary_log_path.read_text(encoding='utf-8', errors='ignore') if canary_log_path.exists() else ''
    if 'exchange_unreachable' in canary_log_text:
        canary_bypass_applied = True
        effective_canary_status = 'PASS_WITH_BYPASS'

rule_canary = (effective_canary_status in {'PASS', 'PASS_WITH_BYPASS'}) if require_canary else True
rule_alert = (alert_status == 'PASS') if require_alert else True

overall_go = all([
    rule_gate,
    rule_final_report,
    rule_phase56,
    rule_preflight,
    rule_live_readiness,
    rule_canary,
    rule_alert,
])

steps = {
    'phase56_closure': phase56_status,
    'preflight': preflight_status,
    'phase8_canary': canary_status,
    'phase8_canary_effective': effective_canary_status,
    'final_release_gate': gate_status,
    'live_readiness': live_readiness_status,
    'alert_evidence': alert_status,
}

rules = {
    'rule_gate_snapshot_go': rule_gate,
    'rule_final_release_decision_go': rule_final_report,
    'rule_phase56_closed': rule_phase56,
    'rule_preflight_pass': rule_preflight,
    'rule_live_readiness_ready': rule_live_readiness,
    'rule_canary_pass': rule_canary,
    'rule_alert_evidence': rule_alert,
    'canary_exchange_unreachable_bypass_applied': canary_bypass_applied,
}

summary = {
    'phase': 'FAZ-7',
    'generated_at': datetime.now(timezone.utc).isoformat(),
    'status': 'GO' if overall_go else 'NO_GO',
    'steps': steps,
    'rules': rules,
    'require_canary': require_canary,
    'require_alert_evidence': require_alert,
}

evidence = {
    **summary,
    'phase56_summary': phase56_summary,
    'preflight_report': json.loads((artifact_dir / 'prod_preflight_check.json').read_text(encoding='utf-8')) if (artifact_dir / 'prod_preflight_check.json').exists() else {},
    'canary_summary': canary_summary,
    'final_release_gate_report': final_report,
    'production_gate_snapshot': gate_snapshot,
    'live_readiness_snapshot': live_readiness_snapshot,
    'alert_snapshot': alert_snapshot,
}

summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
evidence_json.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'status': summary['status'], 'summary': str(summary_json), 'evidence': str(evidence_json)}, ensure_ascii=False))
if summary['status'] != 'GO':
    raise SystemExit(1)
PY

log "SUMMARY: GO"
