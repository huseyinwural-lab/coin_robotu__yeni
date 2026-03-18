#!/usr/bin/env bash
set -euo pipefail

OUT_PATH="${1:-/app/artifacts/db_backup_$(date +%Y%m%d_%H%M%S).bak}"
DB_URL="${DATABASE_URL:-}"
SQLITE_PATH="${SQLITE_PATH:-/tmp/trading_platform_local.db}"

mkdir -p "$(dirname "$OUT_PATH")"

if [[ -n "$DB_URL" && "$DB_URL" == postgresql* ]]; then
  if ! command -v pg_dump >/dev/null 2>&1; then
    echo "ERROR: pg_dump bulunamadı"
    exit 1
  fi
  pg_dump "$DB_URL" --format=custom --no-owner --no-privileges --file "$OUT_PATH"
  echo "BACKUP_OK postgres $OUT_PATH"
  exit 0
fi

if [[ ! -f "$SQLITE_PATH" ]]; then
  echo "ERROR: SQLite dosyası bulunamadı: $SQLITE_PATH"
  exit 1
fi

cp "$SQLITE_PATH" "$OUT_PATH"
echo "BACKUP_OK sqlite $OUT_PATH"
