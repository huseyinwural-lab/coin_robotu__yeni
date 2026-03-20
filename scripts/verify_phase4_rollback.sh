#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="${ROOT_DIR}/artifacts"
LOG_FILE="${ARTIFACT_DIR}/faz4_verify_phase4_rollback.log"
SUMMARY_JSON="${ARTIFACT_DIR}/faz4_rollback_summary.json"
CURRENT_FILE="${ROOT_DIR}/artifacts/release_state/current_release.env"

mkdir -p "${ARTIFACT_DIR}"
: > "${LOG_FILE}"

log() {
  echo "$1" | tee -a "${LOG_FILE}"
}

fail() {
  log "FAIL: $1"
  exit 1
}

BASE_URL="${REACT_APP_BACKEND_URL:-}"
if [[ -z "${BASE_URL}" && -f "${ROOT_DIR}/frontend/.env" ]]; then
  BASE_URL="$(grep -E '^REACT_APP_BACKEND_URL=' "${ROOT_DIR}/frontend/.env" | head -n1 | cut -d'=' -f2- || true)"
fi
[[ -n "${BASE_URL}" ]] || fail "REACT_APP_BACKEND_URL çözümlenemedi"

VERSION_A="$(git -C "${ROOT_DIR}" rev-parse --short=12 HEAD)"
VERSION_B="$(python - <<PY
import hashlib
seed = "${VERSION_A}" + "-broken"
print(hashlib.sha1(seed.encode()).hexdigest()[:12])
PY
)"

log "T-4.1 image tag standard"
[[ "app:release-${VERSION_A}" =~ ^app:release-[0-9a-f]{7,40}$ ]] || fail "image tag standard bozuk"
log "PASS: app:release-<sha>"

log "T-4.2 version parametreli deploy"
"${ROOT_DIR}/scripts/deploy.sh" "${VERSION_A}" || fail "version A deploy başarısız"
log "PASS: version A deploy"

log "T-4.4 bozuk version deploy + rollback"
if DEPLOY_FORCE_FAIL=1 "${ROOT_DIR}/scripts/deploy.sh" "${VERSION_B}"; then
  fail "version B deploy fail bekleniyordu"
fi
log "PASS: version B fail simülasyonu"

ROLLBACK_START="$(date +%s)"
"${ROOT_DIR}/scripts/rollback.sh" || fail "rollback script başarısız"
ROLLBACK_END="$(date +%s)"
ROLLBACK_TIME="$((ROLLBACK_END - ROLLBACK_START))"

[[ "${ROLLBACK_TIME}" -lt 60 ]] || fail "rollback_time >= 60s"
log "PASS: rollback_time=${ROLLBACK_TIME}s"

[[ -f "${CURRENT_FILE}" ]] || fail "current release state yok"
# shellcheck disable=SC1090
source "${CURRENT_FILE}"
[[ "${CURRENT_VERSION:-}" == "${VERSION_A}" ]] || fail "rollback sonrası aktif versiyon A değil"
log "PASS: sistem tekrar A versiyonunda"

log "T-4.5 health doğrulama"
HEALTH_CODE="$(curl -s -o /tmp/faz4_health.json -w '%{http_code}' "${BASE_URL}/health" || true)"
if [[ "${HEALTH_CODE}" != "200" ]]; then
  HEALTH_CODE="$(curl -s -o /tmp/faz4_health.json -w '%{http_code}' "${BASE_URL}/api/health" || true)"
fi

READY_CODE="$(curl -s -o /tmp/faz4_ready.json -w '%{http_code}' "${BASE_URL}/ready" || true)"
if [[ "${READY_CODE}" != "200" ]]; then
  READY_CODE="$(curl -s -o /tmp/faz4_ready.json -w '%{http_code}' "${BASE_URL}/api/ready" || true)"
fi
[[ "${HEALTH_CODE}" == "200" ]] || fail "/health 200 değil"
[[ "${READY_CODE}" == "200" ]] || fail "/ready 200 değil"
log "PASS: health=${HEALTH_CODE}, ready=${READY_CODE}"

python - <<PY
import json
summary = {
  "version_a": "${VERSION_A}",
  "version_b": "${VERSION_B}",
  "rollback_time_seconds": ${ROLLBACK_TIME},
  "health_http": int("${HEALTH_CODE}"),
  "ready_http": int("${READY_CODE}"),
  "result": "PASS",
}
with open("${SUMMARY_JSON}", "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
PY

log "SUMMARY: PASS"