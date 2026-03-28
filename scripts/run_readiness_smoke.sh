#!/usr/bin/env bash
set -euo pipefail

TARGET_ENV="${1:-local}"
BASE_URL_OVERRIDE="${2:-}"

ADMIN_EMAIL="${READINESS_SMOKE_ADMIN_EMAIL:-canary.admin@platform.local}"
ADMIN_PASSWORD="${READINESS_SMOKE_ADMIN_PASSWORD:-CanaryAdmin123!}"

if [[ -n "${BASE_URL_OVERRIDE}" ]]; then
  BASE_URL="${BASE_URL_OVERRIDE}"
elif [[ "${TARGET_ENV}" == "local" ]]; then
  BASE_URL="http://127.0.0.1:8001"
elif [[ "${TARGET_ENV}" == "preview" ]]; then
  BASE_URL="${REACT_APP_BACKEND_URL:-}"
elif [[ "${TARGET_ENV}" == "ops" ]]; then
  BASE_URL="${OPS_BASE_URL:-}"
else
  echo "Unknown target env: ${TARGET_ENV}"
  exit 2
fi

if [[ -z "${BASE_URL}" ]]; then
  echo "BASE_URL bulunamadı. preview için REACT_APP_BACKEND_URL, ops için OPS_BASE_URL tanımla."
  exit 2
fi

echo "[readiness-smoke] env=${TARGET_ENV} base_url=${BASE_URL}"

python /app/backend/cli/ops_smoke_readiness.py \
  --base-url "${BASE_URL}" \
  --email "${ADMIN_EMAIL}" \
  --password "${ADMIN_PASSWORD}" \
  --output "/app/test_reports/readiness_ops_smoke_${TARGET_ENV}_latest.json"
