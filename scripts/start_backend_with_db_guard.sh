#!/usr/bin/env bash
set -euo pipefail

cd /app/backend

set +e
/root/.venv/bin/python /app/scripts/wait_for_postgres_ready.py --attempts 10 --initial-delay 1.2 --connect-timeout 2.0
WAIT_STATUS=$?
set -e

if [ "$WAIT_STATUS" -ne 0 ]; then
  echo "[backend-start] postgres not ready; continuing with degraded startup (health will report not_ready)." >&2
fi

exec /root/.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8001 --workers 1 --reload
