#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ARTIFACT_DIR="${APP_ROOT}/artifacts"
SUMMARY_LOG="${ARTIFACT_DIR}/faz3_execution_safety_summary.log"

mkdir -p "$ARTIFACT_DIR"
: > "$SUMMARY_LOG"

log() {
  local line="$1"
  echo "$line" | tee -a "$SUMMARY_LOG"
}

fail() {
  log "FAIL: $1"
  exit 1
}

log "T-3.1 migration ve model kontrolü"
MIGRATION_PATH="${APP_ROOT}/backend/migrations/versions/20260319_0054_phase3_execution_safety_controls.py"
[[ -f "$MIGRATION_PATH" ]] || fail "migration dosyası yok"

python - <<'PY' > "${ARTIFACT_DIR}/faz3_model_guard_check.log"
from pathlib import Path

checks = {
    '/app/backend/model_domains/risk_execution_positions.py': [
        'trading_enabled',
        'max_total_exposure',
        'max_active_positions',
    ],
    '/app/backend/services/execution_safety_service.py': [
        'REASON_TRADING_DISABLED',
        'REASON_MAX_TOTAL_EXPOSURE_EXCEEDED',
        'REASON_MAX_ACTIVE_POSITIONS_EXCEEDED',
        'enforce_execution_open_allowed_or_raise',
    ],
    '/app/backend/routers/admin_kill_switch.py': [
        '@router.post("/kill-switch"',
    ],
}

for file_path, tokens in checks.items():
    content = Path(file_path).read_text(encoding='utf-8')
    for token in tokens:
        if token not in content:
            raise SystemExit(f'MISSING {token} in {file_path}')
    print(f'PASS {file_path}')
PY
log "PASS: model/safety service/admin endpoint var"

log "T-3.5 guard consolidation kontrolü"
python - <<'PY' > "${ARTIFACT_DIR}/faz3_guard_consolidation.log"
from pathlib import Path

targets = {
    '/app/backend/services/execution_intent_service.py': 'enforce_execution_open_allowed_or_raise',
    '/app/backend/services/runtime_execution_service.py': 'enforce_execution_open_allowed_or_raise',
    '/app/backend/routers/user_execution.py': 'ExecutionSafetyViolation',
    '/app/backend/routers/user_trading.py': 'ExecutionSafetyViolation',
    '/app/backend/routers/admin_execution.py': 'ExecutionSafetyViolation',
}

for file_path, token in targets.items():
    content = Path(file_path).read_text(encoding='utf-8')
    if token not in content:
        raise SystemExit(f'MISSING {token} in {file_path}')
    print(f'PASS {file_path} -> {token}')
PY
log "PASS: execution giriş akışlarında guard var"

log "T-3.6 reason code standardizasyonu"
python - <<'PY' > "${ARTIFACT_DIR}/faz3_reason_code_standardization.log"
from pathlib import Path

required_codes = [
    'TRADING_DISABLED',
    'MAX_TOTAL_EXPOSURE_EXCEEDED',
    'MAX_ACTIVE_POSITIONS_EXCEEDED',
]
content = Path('/app/backend/services/execution_safety_service.py').read_text(encoding='utf-8')
for code in required_codes:
    if code not in content:
        raise SystemExit(f'MISSING_REASON_CODE {code}')
print('PASS reason codes present')
PY
log "PASS: reason code standardizasyonu"

log "T-3.7 integration test paketi"
(
  cd "${APP_ROOT}/backend"
  pytest -q tests/test_phase3_execution_safety.py
) | tee "${ARTIFACT_DIR}/faz3_integration_tests.log"
log "PASS: integration testler"

log "T-3.8/T-3.9 verify+CI gate kontrolü"
python - <<'PY' > "${ARTIFACT_DIR}/faz3_ci_gate_check.log"
from pathlib import Path

workflow = Path('/app/.github/workflows/deploy-gate.yml').read_text(encoding='utf-8')
if 'phase3-execution-safety-gate:' not in workflow:
    raise SystemExit('MISSING_CI_JOB phase3-execution-safety-gate')
if 'verify_phase3_execution_safety.sh' not in workflow:
    raise SystemExit('MISSING_VERIFY_SCRIPT_CALL')
print('PASS phase3-execution-safety-gate present')
PY
log "PASS: CI gate bağlantısı"

log "SUMMARY: PASS"
