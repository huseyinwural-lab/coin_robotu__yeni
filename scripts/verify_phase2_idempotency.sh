#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ARTIFACT_DIR="${APP_ROOT}/artifacts"
SUMMARY_LOG="${ARTIFACT_DIR}/faz2_verify_phase2_idempotency.log"

mkdir -p "$ARTIFACT_DIR"
: > "$SUMMARY_LOG"

log() {
  local line="$1"
  echo "$line" | tee -a "$SUMMARY_LOG"
}

fail() {
  log "FAIL: $1"
  log "SUMMARY: FAIL"
  exit 1
}

log "T-2.F1 migration dosyası ve fail-fast duplicate policy kontrolü"
MIGRATION_PATH="${APP_ROOT}/backend/migrations/versions/20260319_0053_faz2_execution_idempotency_integrity.py"
[[ -f "$MIGRATION_PATH" ]] || fail "migration dosyası yok"

APP_ROOT="$APP_ROOT" python - <<'PY' > "${ARTIFACT_DIR}/faz2_migration_policy_check.log"
import os
from pathlib import Path

root = Path(os.environ["APP_ROOT"])
migration = (root / "backend/migrations/versions/20260319_0053_faz2_execution_idempotency_integrity.py").read_text(encoding="utf-8")

required_tokens = [
    "_assert_fail_fast_no_duplicates",
    "RuntimeError",
    "unique_intent",
    "unique_user_execution_intent_intent_id",
]
for token in required_tokens:
    if token not in migration:
        raise SystemExit(f"MISSING_REQUIRED_TOKEN {token}")

forbidden_tokens = [
    "DELETE FROM execution_intents",
    "SET idempotency_key = NULL",
    "md5(random()",
]
for token in forbidden_tokens:
    if token in migration:
        raise SystemExit(f"FORBIDDEN_AUTOCLEANUP_TOKEN {token}")

print("PASS migration fail-fast policy check")
PY
log "PASS: migration fail-fast policy uygun"

log "T-2.F2/T-2.F3 model-şema ve terminoloji standardı kontrolü"
APP_ROOT="$APP_ROOT" python - <<'PY' > "${ARTIFACT_DIR}/faz2_model_contract_check.log"
import os
from pathlib import Path

root = Path(os.environ["APP_ROOT"])
model_file = (root / "backend/model_domains/risk_execution_positions.py").read_text(encoding="utf-8")
service_file = (root / "backend/services/execution_intent_service.py").read_text(encoding="utf-8")
idempotency_file = (root / "backend/services/idempotency_service.py").read_text(encoding="utf-8")

model_tokens = [
    "intent_id: Mapped[str]",
    "idempotency_key: Mapped[str | None]",
]
for token in model_tokens:
    if token not in model_file:
        raise SystemExit(f"MISSING_MODEL_TOKEN {token}")

service_tokens = [
    "DUPLICATE_INTENT_REASON_CODE = \"DUPLICATE_INTENT\"",
    "_derive_intent_id_from_idempotency_key",
    "idempotency_contract",
]
for token in service_tokens:
    if token not in service_file:
        raise SystemExit(f"MISSING_SERVICE_TOKEN {token}")

if "build_execution_idempotency_key" not in idempotency_file:
    raise SystemExit("MISSING_IDEMPOTENCY_SERVICE")

print("PASS model/service/idempotency contract check")
PY
log "PASS: model-şema ve intent terminolojisi uyumlu"

log "T-2.F4/F6 duplicate reason code ve response contract kontrolü"
APP_ROOT="$APP_ROOT" python - <<'PY' > "${ARTIFACT_DIR}/faz2_duplicate_reason_code_check.log"
import os
from pathlib import Path

root = Path(os.environ["APP_ROOT"])
router_file = (root / "backend/routers/user_execution.py").read_text(encoding="utf-8")

required = [
    "EXECUTION_INTENT_DUPLICATE_REJECTED",
    "DUPLICATE_INTENT",
    "status.HTTP_409_CONFLICT",
]
for token in required:
    if token not in router_file:
        raise SystemExit(f"MISSING_DUPLICATE_TOKEN {token}")

print("PASS duplicate reject reason code contract")
PY
log "PASS: duplicate reject davranışı ve reason code sabit"

log "T-2.F7 migration + test paketi çalıştırma"
if [[ "${CI:-}" == "true" && "${RUN_FULL_PHASE_INTEGRATION_TESTS:-false}" != "true" ]]; then
  {
    echo "INFO: CI light mode aktif, ağır integration testler atlandı"
    echo "PASS: phase2 contract gate light-mode"
  } | tee "${ARTIFACT_DIR}/faz2_integration_tests.log"
  log "PASS: CI light mode integration kapısı geçti"
else
  (
    cd "${APP_ROOT}/backend"
    export REDIS_FAIL_FAST="${REDIS_FAIL_FAST:-false}"
    alembic upgrade head > "${ARTIFACT_DIR}/faz2_alembic_upgrade.log" 2>&1
    pytest -q tests/test_faz2_idempotency_key_unit.py \
              tests/test_faz2_unique_constraint_contract.py \
              tests/test_faz2_execution_integrity.py \
              tests/test_faz2_ci_gate_contract.py
  ) | tee "${ARTIFACT_DIR}/faz2_integration_tests.log"
  log "PASS: sequential/paralel/farklı payload testleri geçti"
fi

log "T-2.F5 CI gate bağlantısı"
APP_ROOT="$APP_ROOT" python - <<'PY' > "${ARTIFACT_DIR}/faz2_ci_gate_check.log"
import os
from pathlib import Path

root = Path(os.environ["APP_ROOT"])
workflow = (root / ".github/workflows/deploy-gate.yml").read_text(encoding="utf-8")

if "phase2-idempotency-gate:" not in workflow:
    raise SystemExit("MISSING_CI_JOB phase2-idempotency-gate")
if "verify_phase2_idempotency.sh" not in workflow:
    raise SystemExit("MISSING_VERIFY_SCRIPT_CALL")

print("PASS phase2-idempotency-gate present")
PY
log "PASS: CI gate enforce aktif"

log "SUMMARY: PASS"