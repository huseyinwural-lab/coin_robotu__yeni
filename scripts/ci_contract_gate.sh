#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/app"
BACKEND_DIR="$ROOT_DIR/backend"

cd "$BACKEND_DIR"
PYTHONPATH="$BACKEND_DIR" python -m cli.validate_contract_snapshot

cd "$ROOT_DIR"
PYTHONPATH="$BACKEND_DIR" pytest -q /app/tests/test_api_contracts.py