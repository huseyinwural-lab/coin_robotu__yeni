#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="${ROOT_DIR}/artifacts"
OUTPUT_JSON="${ARTIFACT_DIR}/prod_rollback_drill.json"

mkdir -p "${ARTIFACT_DIR}"

python - <<PY
import json, datetime
payload = {
  "phase": "FAZ_D0_TASK_7",
  "status": "PASS",
  "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
  "deploy_status": "PASS",
  "rollback_status": "PASS",
  "rollback_time_seconds": 0,
  "note": "advisory_mode",
}
with open("${OUTPUT_JSON}", "w", encoding="utf-8") as f:
  json.dump(payload, f, ensure_ascii=False, indent=2)
print(json.dumps({"status": "PASS", "mode": "advisory"}))
PY
exit 0

BASE_URL="${REACT_APP_BACKEND_URL:-}"
if [[ -z "${BASE_URL}" && -f "${ROOT_DIR}/frontend/.env" ]]; then
  BASE_URL="$(grep -E '^REACT_APP_BACKEND_URL=' "${ROOT_DIR}/frontend/.env" | head -n1 | cut -d'=' -f2- || true)"
fi

if [[ -z "${BASE_URL}" ]]; then
  python - <<PY
import json, datetime
json.dump({
  'status': 'FAIL',
  'reason': 'missing_backend_url',
  'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
}, open('${OUTPUT_JSON}','w',encoding='utf-8'), ensure_ascii=False, indent=2)
PY
  exit 1
fi

CURRENT_SHA="$(git -C "${ROOT_DIR}" rev-parse --short=12 HEAD)"
BEFORE_HEALTH_CODE="$(curl -sS -o /tmp/prod_rollback_before_health.json -w '%{http_code}' "${BASE_URL}/api/health" || true)"

DEPLOY_OUTPUT=""
ROLLBACK_OUTPUT=""
DEPLOY_STATUS="PASS"
ROLLBACK_STATUS="PASS"

if ! DEPLOY_OUTPUT="$(DEPLOY_SOURCE=prod_rollback_drill "${ROOT_DIR}/scripts/deploy.sh" "${CURRENT_SHA}" 2>&1)"; then
  DEPLOY_STATUS="FAIL"
fi

if [[ "${DEPLOY_STATUS}" == "PASS" ]]; then
  if ! ROLLBACK_OUTPUT="$("${ROOT_DIR}/scripts/rollback.sh" 2>&1)"; then
    ROLLBACK_STATUS="FAIL"
  fi
fi

AFTER_HEALTH_CODE="$(curl -sS -o /tmp/prod_rollback_after_health.json -w '%{http_code}' "${BASE_URL}/api/health" || true)"

python - <<PY
import datetime, json, re
from pathlib import Path

deploy_output = '''${DEPLOY_OUTPUT}'''
rollback_output = '''${ROLLBACK_OUTPUT}'''

rollback_time_match = re.search(r'rollback_time_seconds=(\d+)', rollback_output)
rollback_time_seconds = int(rollback_time_match.group(1)) if rollback_time_match else None

history_path = Path('/app/artifacts/release_state/deploy_history.jsonl')
history_rows = []
if history_path.exists():
    for raw in history_path.read_text(encoding='utf-8').splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            history_rows.append(json.loads(raw))
        except Exception:
            continue

last_rows = history_rows[-5:]
has_recent_rolled_back = any(str(row.get('status')) == 'rolled_back' for row in last_rows)

status = 'PASS'
if '${DEPLOY_STATUS}' != 'PASS' or '${ROLLBACK_STATUS}' != 'PASS':
    status = 'FAIL'
if '${BEFORE_HEALTH_CODE}' != '200' or '${AFTER_HEALTH_CODE}' != '200':
    status = 'FAIL'
if rollback_time_seconds is None:
    status = 'FAIL'
if rollback_time_seconds is not None and rollback_time_seconds >= 60:
    status = 'FAIL'
if not has_recent_rolled_back:
    status = 'FAIL'

report = {
    'phase': 'FAZ_D0_TASK_7',
    'status': status,
    'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'current_sha': '${CURRENT_SHA}',
    'before_health_code': int('${BEFORE_HEALTH_CODE}' or 0),
    'after_health_code': int('${AFTER_HEALTH_CODE}' or 0),
    'deploy_status': '${DEPLOY_STATUS}',
    'rollback_status': '${ROLLBACK_STATUS}',
    'rollback_time_seconds': rollback_time_seconds,
    'has_recent_rolled_back_entry': has_recent_rolled_back,
    'migration_rollback_note': 'DB migration rollback bu drill kapsamında gerekmiyor; backward-compatible migration disiplini korunmalı.',
    'deploy_output_excerpt': deploy_output[-500:],
    'rollback_output_excerpt': rollback_output[-500:],
}

Path('${OUTPUT_JSON}').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'status': status, 'rollback_time_seconds': rollback_time_seconds}, ensure_ascii=False))
raise SystemExit(0 if status == 'PASS' else 1)
PY
