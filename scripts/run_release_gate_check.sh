#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/app"
BACKEND_DIR="$ROOT_DIR/backend"

ENVIRONMENT=""
for arg in "$@"; do
  case "$arg" in
    --env=*)
      ENVIRONMENT="${arg#*=}"
      ;;
  esac
done

if [[ -z "$ENVIRONMENT" ]]; then
  echo "missing required argument: --env" >&2
  exit 2
fi

if [[ ! -d "$BACKEND_DIR" ]]; then
  echo "release_gate_status=BLOCKED"
  echo "reason=backend_missing"
  exit 2
fi

cd "$BACKEND_DIR"
PYTHONPATH="$BACKEND_DIR" python -m cli.release_gate_check --env="$ENVIRONMENT"