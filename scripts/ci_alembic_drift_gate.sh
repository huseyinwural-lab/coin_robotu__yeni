#!/usr/bin/env bash
set -euo pipefail

ROOT="/app"
BACKEND_DIR="$ROOT/backend"

echo "[drift-gate] static guard: startup create_all kontrolü"
if grep -R --line-number "Base\.metadata\.create_all" "$BACKEND_DIR/server.py" >/dev/null; then
  echo "[drift-gate][FAIL] startup create_all geri gelmiş. Alembic tek otorite kuralı ihlal edildi."
  exit 1
fi

echo "[drift-gate] static guard: runtime schema patch kontrolü"
if grep -E --line-number "PRAGMA table_info|CREATE TABLE IF NOT EXISTS|ALTER TABLE .*ADD COLUMN" "$BACKEND_DIR/db.py" >/dev/null; then
  echo "[drift-gate][FAIL] runtime schema patch paterni bulundu. Alembic dışı şema mutasyonu yasak."
  exit 1
fi

echo "[drift-gate] alembic autogenerate drift kontrolü"
set +e
CHECK_OUTPUT=$(cd "$BACKEND_DIR" && PYTHONPATH=/app/backend alembic check 2>&1)
CHECK_EXIT=$?
set -e

if [ "$CHECK_EXIT" -ne 0 ]; then
  echo "[drift-gate][FAIL] Alembic drift tespit edildi veya check başarısız oldu."
  echo "$CHECK_OUTPUT"
  exit 1
fi

echo "[drift-gate][PASS] Alembic drift kontrolü temiz."
