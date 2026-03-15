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

if [ "$CHECK_EXIT" -eq 0 ]; then
  echo "[drift-gate][PASS] Alembic drift kontrolü temiz."
  exit 0
fi

DETECTED_LINES=$(printf "%s\n" "$CHECK_OUTPUT" | grep "Detected " || true)

if [ -z "$DETECTED_LINES" ]; then
  echo "[drift-gate][FAIL] Alembic check başarısız; drift envanteri okunamadı."
  echo "$CHECK_OUTPUT"
  exit 1
fi

UNEXPECTED=0
while IFS= read -r line; do
  case "$line" in
    *"Detected NOT NULL on column 'bot_profiles.is_running'"*)
      ;;
    *"Detected NOT NULL on column 'strategy_observability_events.created_at'"*)
      ;;
    *"Detected NOT NULL on column 'users.updated_at'"*)
      ;;
    *"Detected type change"*"'users.role'"*)
      ;;
    *)
      echo "[drift-gate][FAIL] Beklenmeyen drift kalemi: $line"
      UNEXPECTED=1
      ;;
  esac
done <<< "$DETECTED_LINES"

if [ "$UNEXPECTED" -eq 1 ]; then
  echo "[drift-gate][FAIL] Non-destructive kapanış dışında drift kalemleri mevcut."
  echo "$CHECK_OUTPUT"
  exit 1
fi

echo "[drift-gate][PASS] Sadece onaylı deferred-destructive drift kalemleri mevcut (planlı)."
