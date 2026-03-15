#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
export TEST_ADMIN_EMAIL="${TEST_ADMIN_EMAIL:-admin@platform.local}"
export TEST_ADMIN_PASSWORD="${TEST_ADMIN_PASSWORD:-Admin12345!}"

cd "$BACKEND_DIR"
PYTHONPATH="$BACKEND_DIR" python -m cli.validate_contract_snapshot

cd "$ROOT_DIR"
PYTHONPATH="$BACKEND_DIR" pytest -q "$ROOT_DIR/tests/test_api_contracts.py"