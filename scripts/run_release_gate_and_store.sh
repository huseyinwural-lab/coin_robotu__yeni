#!/usr/bin/env bash
set -euo pipefail

TARGET_ENV="${1:-preview}"
OUT_FILE="/app/test_reports/release_gate_latest.json"

echo "[INFO] Running P0 closure gate for target_env=${TARGET_ENV}"
python /app/backend/cli/p0_closure_gate.py \
  --target-env "${TARGET_ENV}" \
  --output-file "${OUT_FILE}"

echo "[INFO] Gate report written to ${OUT_FILE}"
