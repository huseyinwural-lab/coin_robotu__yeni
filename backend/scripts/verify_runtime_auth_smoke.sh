#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

BACKEND_URL="${BACKEND_URL:-http://localhost:8001}"
BACKEND_LOG="/tmp/faz5_backend.log"
LOGIN_BODY_FILE="/tmp/faz5_login_body.json"
ADMIN_BODY_FILE="/tmp/faz5_admin_body.json"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "[ERROR] Missing DATABASE_URL"
  exit 1
fi
if [[ -z "${TEST_ADMIN_EMAIL:-}" || -z "${TEST_ADMIN_PASSWORD:-}" ]]; then
  echo "[ERROR] Missing TEST_ADMIN_EMAIL or TEST_ADMIN_PASSWORD"
  exit 1
fi

BACKEND_PID=""

cleanup() {
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" || true
  fi
}
trap cleanup EXIT

echo "[1/4] Starting backend runtime"
nohup uvicorn server:app --host 0.0.0.0 --port 8001 >"$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

READY=0
for _ in $(seq 1 90); do
  STATUS=$(curl -s -o /tmp/faz5_backend_ready.txt -w "%{http_code}" "$BACKEND_URL/docs" || true)
  if [[ "$STATUS" == "200" ]]; then
    READY=1
    break
  fi
  sleep 2
done

if [[ "$READY" != "1" ]]; then
  echo "[ERROR] Backend runtime not ready"
  tail -n 200 "$BACKEND_LOG" || true
  exit 1
fi
echo "[OK] Backend runtime ready"

echo "[2/4] Verifying admin bootstrap"
python - <<'PY'
import os
from sqlalchemy import create_engine, text

url = os.environ["DATABASE_URL"]
email = os.environ["TEST_ADMIN_EMAIL"]
engine = create_engine(url)
with engine.connect() as conn:
    row = conn.execute(
        text("SELECT email, role::text AS role FROM users WHERE email=:email LIMIT 1"),
        {"email": email},
    ).mappings().first()
if not row:
    raise SystemExit("[ERROR] Admin bootstrap user not found")
print(f"[OK] Admin bootstrap user exists: {row['email']} role={row['role']}")
PY

echo "[3/4] Admin login smoke"
LOGIN_STATUS=$(curl -s -o "$LOGIN_BODY_FILE" -w "%{http_code}" \
  -X POST "$BACKEND_URL/api/auth/login/admin" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${TEST_ADMIN_EMAIL}\",\"password\":\"${TEST_ADMIN_PASSWORD}\"}")

if [[ "$LOGIN_STATUS" != "200" ]]; then
  echo "[ERROR] Admin login failed: status=$LOGIN_STATUS"
  cat "$LOGIN_BODY_FILE" || true
  tail -n 200 "$BACKEND_LOG" || true
  exit 1
fi

TOKEN=$(python - <<'PY'
import json
from pathlib import Path
body = json.loads(Path('/tmp/faz5_login_body.json').read_text())
print(body.get('access_token', ''))
PY
)

if [[ -z "$TOKEN" ]]; then
  echo "[ERROR] access_token missing in login response"
  cat "$LOGIN_BODY_FILE" || true
  exit 1
fi
echo "[OK] Admin login 200 and token generated"

echo "[4/4] Protected admin endpoint smoke"
ADMIN_STATUS=$(curl -s -o "$ADMIN_BODY_FILE" -w "%{http_code}" \
  "$BACKEND_URL/api/admin/live-trading/summary" \
  -H "Authorization: Bearer $TOKEN")

if [[ "$ADMIN_STATUS" != "200" ]]; then
  echo "[ERROR] Admin endpoint failed: status=$ADMIN_STATUS"
  cat "$ADMIN_BODY_FILE" || true
  tail -n 200 "$BACKEND_LOG" || true
  exit 1
fi

echo "[OK] Protected admin endpoint 200"
echo "Runtime: OK"
echo "Admin bootstrap: OK"
echo "Login endpoint: OK"
echo "Admin API: OK"
echo "[SUCCESS] FAZ-5 Runtime & Auth Smoke passed"
