#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
: "${TEST_ADMIN_EMAIL:?Missing TEST_ADMIN_EMAIL}"
: "${TEST_ADMIN_PASSWORD:?Missing TEST_ADMIN_PASSWORD}"

cd "$BACKEND_DIR"
PYTHONPATH="$BACKEND_DIR" python -m cli.validate_execution_contract

cd "$ROOT_DIR"
PYTHONPATH="$BACKEND_DIR" pytest -q "$ROOT_DIR/tests/test_execution_contracts.py"