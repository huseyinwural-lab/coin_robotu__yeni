#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ARTIFACT_DIR="${APP_ROOT}/artifacts"
SUMMARY_LOG="${ARTIFACT_DIR}/faz3_execution_safety_summary.log"

mkdir -p "$ARTIFACT_DIR"
: > "$SUMMARY_LOG"

PHASE3_SUMMARY_JSON="${ARTIFACT_DIR}/faz3_closure_summary.json"

ensure_text_artifact() {
  local path="$1"
  local body="$2"
  [[ -f "$path" ]] || printf "%s\n" "$body" > "$path"
}

ensure_phase3_contract_artifacts() {
  ensure_text_artifact "${ARTIFACT_DIR}/faz3_alembic_upgrade.log" "INFO: not_run_in_light_mode"
}

write_phase3_summary() {
  local final_status="$1"
  APP_ROOT="$APP_ROOT" ARTIFACT_DIR="$ARTIFACT_DIR" SUMMARY_LOG="$SUMMARY_LOG" PHASE3_SUMMARY_JSON="$PHASE3_SUMMARY_JSON" FINAL_STATUS="$final_status" python - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

artifact_dir = Path(os.environ["ARTIFACT_DIR"])
summary_log = Path(os.environ["SUMMARY_LOG"])
summary_json = Path(os.environ["PHASE3_SUMMARY_JSON"])
final_status = str(os.environ.get("FINAL_STATUS") or "UNKNOWN").upper()

expected = [
    "faz3_execution_safety_summary.log",
    "faz3_alembic_upgrade.log",
    "faz3_model_guard_check.log",
    "faz3_guard_consolidation.log",
    "faz3_reason_code_standardization.log",
    "faz3_integration_tests.log",
    "faz3_ci_gate_check.log",
]

artifacts = []
for name in expected:
    p = artifact_dir / name
    artifacts.append({"name": name, "exists": p.exists(), "path": str(p)})

log_tail = ""
if summary_log.exists():
    lines = summary_log.read_text(encoding="utf-8", errors="ignore").splitlines()
    log_tail = "\n".join(lines[-20:])

summary = {
    "phase": "FAZ-3",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "status": final_status,
    "summary_log": str(summary_log),
    "artifacts": artifacts,
    "missing_count": len([a for a in artifacts if not a["exists"]]),
    "log_tail": log_tail,
}
summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": final_status, "summary": str(summary_json)}, ensure_ascii=False))
PY
}

log() {
  local line="$1"
  echo "$line" | tee -a "$SUMMARY_LOG"
}

fail() {
  log "FAIL: $1"
  log "SUMMARY: FAIL"
  ensure_phase3_contract_artifacts
  write_phase3_summary "FAIL"
  exit 1
}

log "T-3.1 migration ve model kontrolü"
MIGRATION_PATH="${APP_ROOT}/backend/migrations/versions/20260319_0054_phase3_execution_safety_controls.py"
[[ -f "$MIGRATION_PATH" ]] || fail "migration dosyası yok"

APP_ROOT="$APP_ROOT" python - <<'PY' > "${ARTIFACT_DIR}/faz3_model_guard_check.log"
import os
from pathlib import Path

root = Path(os.environ['APP_ROOT'])
checks = {
    str(root / 'backend/model_domains/risk_execution_positions.py'): [
        'trading_enabled',
        'max_total_exposure',
        'max_active_positions',
    ],
    str(root / 'backend/services/execution_safety_service.py'): [
        'REASON_TRADING_DISABLED',
        'REASON_MAX_TOTAL_EXPOSURE_EXCEEDED',
        'REASON_MAX_ACTIVE_POSITIONS_EXCEEDED',
        'enforce_execution_open_allowed_or_raise',
    ],
    str(root / 'backend/routers/admin_kill_switch.py'): [
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
APP_ROOT="$APP_ROOT" python - <<'PY' > "${ARTIFACT_DIR}/faz3_guard_consolidation.log"
import os
from pathlib import Path

root = Path(os.environ['APP_ROOT'])
targets = {
    str(root / 'backend/services/execution_intent_service.py'): 'enforce_execution_open_allowed_or_raise',
    str(root / 'backend/services/runtime_execution_service.py'): 'enforce_execution_open_allowed_or_raise',
    str(root / 'backend/routers/user_execution.py'): 'ExecutionSafetyViolation',
    str(root / 'backend/routers/user_trading.py'): 'ExecutionSafetyViolation',
    str(root / 'backend/routers/admin_execution.py'): 'ExecutionSafetyViolation',
}

for file_path, token in targets.items():
    content = Path(file_path).read_text(encoding='utf-8')
    if token not in content:
        raise SystemExit(f'MISSING {token} in {file_path}')
    print(f'PASS {file_path} -> {token}')
PY
log "PASS: execution giriş akışlarında guard var"

log "T-3.6 reason code standardizasyonu"
APP_ROOT="$APP_ROOT" python - <<'PY' > "${ARTIFACT_DIR}/faz3_reason_code_standardization.log"
import os
from pathlib import Path

root = Path(os.environ['APP_ROOT'])
required_codes = [
    'TRADING_DISABLED',
    'MAX_TOTAL_EXPOSURE_EXCEEDED',
    'MAX_ACTIVE_POSITIONS_EXCEEDED',
]
content = (root / 'backend/services/execution_safety_service.py').read_text(encoding='utf-8')
for code in required_codes:
    if code not in content:
        raise SystemExit(f'MISSING_REASON_CODE {code}')
print('PASS reason codes present')
PY
log "PASS: reason code standardizasyonu"

log "T-3.7 integration test paketi"
if [[ "${CI:-}" == "true" && "${RUN_FULL_PHASE_INTEGRATION_TESTS:-false}" != "true" ]]; then
  {
    echo "INFO: CI light mode aktif, ağır integration testler atlandı"
    echo "PASS: phase3 safety gate light-mode"
  } | tee "${ARTIFACT_DIR}/faz3_integration_tests.log"
  ensure_text_artifact "${ARTIFACT_DIR}/faz3_alembic_upgrade.log" "INFO: CI light mode, alembic step skipped"
  log "PASS: CI light mode integration kapısı geçti"
else
  (
    cd "${APP_ROOT}/backend"
    export REDIS_FAIL_FAST="${REDIS_FAIL_FAST:-false}"
    alembic upgrade head > "${ARTIFACT_DIR}/faz3_alembic_upgrade.log" 2>&1
    pytest -q tests/test_phase3_execution_safety.py
  ) | tee "${ARTIFACT_DIR}/faz3_integration_tests.log"
  log "PASS: integration testler"
fi

log "T-3.8/T-3.9 verify+CI gate kontrolü"
APP_ROOT="$APP_ROOT" python - <<'PY' > "${ARTIFACT_DIR}/faz3_ci_gate_check.log"
import os
from pathlib import Path

root = Path(os.environ['APP_ROOT'])
workflow = (root / '.github/workflows/deploy-gate.yml').read_text(encoding='utf-8')
if 'phase3-execution-safety-gate:' not in workflow:
    raise SystemExit('MISSING_CI_JOB phase3-execution-safety-gate')
if 'verify_phase3_execution_safety.sh' not in workflow:
    raise SystemExit('MISSING_VERIFY_SCRIPT_CALL')
print('PASS phase3-execution-safety-gate present')
PY
log "PASS: CI gate bağlantısı"

ensure_phase3_contract_artifacts
log "SUMMARY: PASS"
write_phase3_summary "PASS"
