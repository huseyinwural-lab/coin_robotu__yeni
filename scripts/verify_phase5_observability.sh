#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ARTIFACT_DIR="${APP_ROOT}/artifacts"
SUMMARY_LOG="${ARTIFACT_DIR}/faz5_verify_phase5_observability.log"

mkdir -p "$ARTIFACT_DIR"
: > "$SUMMARY_LOG"

export ALERT_TEST_MODE="${ALERT_TEST_MODE:-file_sink}"
export ALERT_TEST_SINK_FILE="${ALERT_TEST_SINK_FILE:-${ARTIFACT_DIR}/faz5_alert_delivery.log}"
export OBSERVABILITY_LOG_FILE="${OBSERVABILITY_LOG_FILE:-${APP_ROOT}/backend/logs/backend_observability.log}"

log() {
  local line="$1"
  echo "$line" | tee -a "$SUMMARY_LOG"
}

fail() {
  log "FAIL: $1"
  log "SUMMARY: FAIL"
  exit 1
}

log "T-5.1 logging config kontrolü"
for file in \
  "${APP_ROOT}/backend/core/structured_logging.py" \
  "${APP_ROOT}/backend/core/observability/http_logging_middleware.py" \
  "${APP_ROOT}/backend/services/observability_service.py"; do
  [[ -f "$file" ]] || fail "Eksik dosya: $file"
done

APP_ROOT="$APP_ROOT" python - <<'PY' > "${ARTIFACT_DIR}/faz5_logging_contract_check.log"
import os
from pathlib import Path

root = Path(os.environ["APP_ROOT"])
structured = (root / "backend/core/structured_logging.py").read_text(encoding="utf-8")
required = ["StructuredJsonFormatter", "FileHandler", "StreamHandler", "event_name", "component"]
for token in required:
    if token not in structured:
        raise SystemExit(f"MISSING_LOGGING_TOKEN {token}")
print("PASS logging contract tokens")
PY
log "PASS: logging contract tokenları bulundu"

log "T-5.1 stdout + file log + masking smoke"
(
  cd "${APP_ROOT}/backend"
  python - <<'PY'
import logging
from core.structured_logging import configure_structured_logging

configure_structured_logging(logging.INFO)
probe = logging.getLogger("phase5.verify")
probe.info(
    "phase5_logging_probe",
    extra={
        "event_name": "phase5_logging_probe",
        "request_id": "req-phase5-001",
        "user_id": "user-secret-123456",
        "reason_code": "PHASE5_PROBE",
        "api_key": "SG.very-sensitive-key-for-mask-check",
        "password": "SuperSecretPassword!",
    },
)
PY
) | tee "${ARTIFACT_DIR}/faz5_stdout_log_sample.log"

[[ -f "$OBSERVABILITY_LOG_FILE" ]] || fail "File log oluşmadı: $OBSERVABILITY_LOG_FILE"
tail -n 20 "$OBSERVABILITY_LOG_FILE" > "${ARTIFACT_DIR}/faz5_file_log_sample.log"

if grep -q "SG.very-sensitive-key-for-mask-check" "${ARTIFACT_DIR}/faz5_file_log_sample.log"; then
  fail "Masking başarısız: ham api key file log'da bulundu"
fi
if grep -q "SuperSecretPassword!" "${ARTIFACT_DIR}/faz5_file_log_sample.log"; then
  fail "Masking başarısız: ham password file log'da bulundu"
fi
log "PASS: stdout+file log üretimi ve masking doğrulandı"

log "T-5.2/T-5.3/T-5.4/T-5.6 entegrasyon testleri"
(
  cd "${APP_ROOT}/backend"
  alembic upgrade head > "${ARTIFACT_DIR}/faz5_alembic_upgrade.log" 2>&1
  pytest -q tests/test_phase5_observability_gate.py
) | tee "${ARTIFACT_DIR}/faz5_integration_tests.log"
log "PASS: observability backend senaryoları geçti"

log "T-5.2 metric output doğrulama"
[[ -f "${ARTIFACT_DIR}/faz5_metrics_output.txt" ]] || fail "metrics output artefaktı yok"
for metric in "observability_error_rate_ratio" "observability_latency_ms_p95" "observability_queue_size"; do
  grep -q "$metric" "${ARTIFACT_DIR}/faz5_metrics_output.txt" || fail "Eksik metric: $metric"
done
log "PASS: metrics output doğrulandı"

log "T-5.4 /health ve /ready artefakt kontrolü"
[[ -f "${ARTIFACT_DIR}/faz5_health_response.json" ]] || fail "health response artefaktı yok"
[[ -f "${ARTIFACT_DIR}/faz5_ready_healthy_response.json" ]] || fail "ready healthy response artefaktı yok"
[[ -f "${ARTIFACT_DIR}/faz5_ready_not_ready_response.json" ]] || fail "ready not-ready response artefaktı yok"
log "PASS: health/ready artefaktları mevcut"

log "T-5.3/T-5.6 alert kanalı ve fake error artefakt kontrolü"
[[ -f "${ARTIFACT_DIR}/faz5_alert_payload_sample.json" ]] || fail "alert payload artefaktı yok"
[[ -f "${ARTIFACT_DIR}/faz5_fake_error_test.log" ]] || fail "fake error test logu yok"
[[ -f "$ALERT_TEST_SINK_FILE" ]] || fail "alert delivery sink logu yok"
log "PASS: alert/fake-error artefaktları mevcut"

log "T-5.8 CI gate bağlantısı"
APP_ROOT="$APP_ROOT" python - <<'PY' > "${ARTIFACT_DIR}/faz5_ci_gate_check.log"
import os
from pathlib import Path

root = Path(os.environ["APP_ROOT"])
workflow = (root / ".github/workflows/deploy-gate.yml").read_text(encoding="utf-8")

if "phase5-observability-gate:" not in workflow:
    raise SystemExit("MISSING_CI_JOB phase5-observability-gate")
if "verify_phase5_observability.sh" not in workflow:
    raise SystemExit("MISSING_VERIFY_SCRIPT_CALL")

print("PASS phase5-observability-gate present")
PY
log "PASS: CI gate enforce aktif"

log "SUMMARY: PASS"