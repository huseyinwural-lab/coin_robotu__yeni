#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${ROOT_DIR}/artifacts/release_state"
HISTORY_FILE="${STATE_DIR}/deploy_history.jsonl"
CURRENT_FILE="${STATE_DIR}/current_release.env"

mkdir -p "${STATE_DIR}"

usage() {
  echo "Kullanım: ./scripts/deploy.sh <version_sha>"
}

resolve_backend_url() {
  if [[ -n "${REACT_APP_BACKEND_URL:-}" ]]; then
    echo "${REACT_APP_BACKEND_URL}"
    return
  fi

  if [[ -f "${ROOT_DIR}/frontend/.env" ]]; then
    local from_env
    from_env="$(grep -E '^REACT_APP_BACKEND_URL=' "${ROOT_DIR}/frontend/.env" | head -n1 | cut -d'=' -f2- || true)"
    if [[ -n "${from_env}" ]]; then
      echo "${from_env}"
      return
    fi
  fi

  if [[ -n "${APP_URL:-}" ]]; then
    echo "${APP_URL}"
    return
  fi

  echo "http://127.0.0.1:8001"
}

record_history() {
  local version="$1"
  local image_tag="$2"
  local status="$3"
  local source_name="$4"
  local started_at="$5"
  local finished_at="$6"

  python - <<PY
import json, datetime
entry = {
  "version": "${version}",
  "image_tag": "${image_tag}",
  "status": "${status}",
  "timestamp": "${finished_at}",
  "source": "${source_name}",
  "started_at": "${started_at}",
  "finished_at": "${finished_at}",
  "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
with open("${HISTORY_FILE}", "a", encoding="utf-8") as f:
    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
PY
}

check_health() {
  local base_url="$1"
  local health_code ready_code

  health_code="$(curl -s -o /tmp/deploy_health_body.json -w '%{http_code}' "${base_url}/health" || true)"
  if [[ "${health_code}" != "200" ]]; then
    health_code="$(curl -s -o /tmp/deploy_health_body.json -w '%{http_code}' "${base_url}/api/health" || true)"
  fi

  ready_code="$(curl -s -o /tmp/deploy_ready_body.json -w '%{http_code}' "${base_url}/ready" || true)"
  if [[ "${ready_code}" != "200" ]]; then
    ready_code="$(curl -s -o /tmp/deploy_ready_body.json -w '%{http_code}' "${base_url}/api/ready" || true)"
  fi

  [[ "${health_code}" == "200" && "${ready_code}" == "200" ]]
}

if [[ "${1:-}" == "" ]]; then
  usage
  exit 1
fi

VERSION="$1"
if [[ ! "${VERSION}" =~ ^[0-9a-f]{7,40}$ ]]; then
  echo "[ERROR] version git SHA formatında olmalı (7-40 hex): ${VERSION}"
  exit 1
fi

RELEASE_VERSION="release-${VERSION}"
IMAGE_TAG="app:release-${VERSION}"
DEPLOY_SOURCE="${DEPLOY_SOURCE:-deploy}"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
BACKEND_URL="$(resolve_backend_url)"

echo "[INFO] version=${RELEASE_VERSION}"
echo "[INFO] image_tag=${IMAGE_TAG}"
echo "[INFO] backend_url=${BACKEND_URL}"

cat > "${CURRENT_FILE}" <<EOF
CURRENT_VERSION=${RELEASE_VERSION}
CURRENT_VERSION_SHA=${VERSION}
CURRENT_IMAGE_TAG=${IMAGE_TAG}
CURRENT_STATUS=deploying
UPDATED_AT=${STARTED_AT}
EOF

if [[ "${DEPLOY_FORCE_FAIL:-0}" == "1" ]]; then
  FINISHED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  record_history "${RELEASE_VERSION}" "${IMAGE_TAG}" "failed" "${DEPLOY_SOURCE}" "${STARTED_AT}" "${FINISHED_AT}"
  echo "[ERROR] DEPLOY_FORCE_FAIL=1 nedeniyle deploy başarısız simüle edildi"
  exit 1
fi

if ! check_health "${BACKEND_URL}"; then
  FINISHED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  record_history "${RELEASE_VERSION}" "${IMAGE_TAG}" "failed" "${DEPLOY_SOURCE}" "${STARTED_AT}" "${FINISHED_AT}"
  echo "[ERROR] health/ready başarısız, deploy iptal"
  exit 1
fi

FINISHED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
record_history "${RELEASE_VERSION}" "${IMAGE_TAG}" "success" "${DEPLOY_SOURCE}" "${STARTED_AT}" "${FINISHED_AT}"

cat > "${CURRENT_FILE}" <<EOF
CURRENT_VERSION=${RELEASE_VERSION}
CURRENT_VERSION_SHA=${VERSION}
CURRENT_IMAGE_TAG=${IMAGE_TAG}
CURRENT_STATUS=deployed
UPDATED_AT=${FINISHED_AT}
EOF

echo "[OK] requested_version_deployed=${RELEASE_VERSION}"
echo "[OK] deployed_image_tag=${IMAGE_TAG}"