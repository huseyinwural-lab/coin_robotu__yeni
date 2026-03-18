#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Kullanım: bash /app/scripts/db_restore.sh <backup_path>"
  exit 1
fi

BACKUP_PATH="$1"
DB_URL="${DATABASE_URL:-}"
SQLITE_PATH="${SQLITE_PATH:-/tmp/trading_platform_local.db}"

if [[ ! -f "$BACKUP_PATH" ]]; then
  echo "ERROR: backup bulunamadı: $BACKUP_PATH"
  exit 1
fi

if [[ -n "$DB_URL" && "$DB_URL" == postgresql* ]]; then
  if ! command -v pg_restore >/dev/null 2>&1; then
    echo "ERROR: pg_restore bulunamadı"
    exit 1
  fi
  pg_restore --clean --if-exists --no-owner --no-privileges --dbname "$DB_URL" "$BACKUP_PATH"
  echo "RESTORE_OK postgres $BACKUP_PATH"
  exit 0
fi

cp "$BACKUP_PATH" "$SQLITE_PATH"
echo "RESTORE_OK sqlite $BACKUP_PATH"
