#!/usr/bin/env bash
set -euo pipefail

GATE_FILE="${1:-/app/test_reports/release_gate_latest.json}"

python /app/backend/cli/daily_ops_automation.py --gate-file "${GATE_FILE}"
