#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/app"
BACKEND_DIR="$ROOT_DIR/backend"

if [[ ! -d "$BACKEND_DIR" ]]; then
  echo "formula_gate_status=BLOCKED"
  echo "reason=backend_missing"
  exit 2
fi

cd "$BACKEND_DIR"
PYTHONPATH="$BACKEND_DIR" python -m cli.production_formula_gate_check