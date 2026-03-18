#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Kullanım: bash /app/scripts/db_restore.sh <backup_path>"
  exit 1
fi

BACKUP_PATH="$1"
DB_URL="${DATABASE_URL:-}"

if [[ ! -f "$BACKUP_PATH" ]]; then
  echo "ERROR: backup bulunamadı: $BACKUP_PATH"
  exit 1
fi

if [[ -z "$DB_URL" ]]; then
  echo "ERROR: DATABASE_URL boş olamaz"
  exit 1
fi

if [[ "$DB_URL" != postgresql* ]]; then
  echo "ERROR: Sadece PostgreSQL DATABASE_URL desteklenir"
  exit 1
fi

if ! command -v pg_restore >/dev/null 2>&1; then
  echo "ERROR: pg_restore bulunamadı"
  exit 1
fi

pg_restore --clean --if-exists --no-owner --no-privileges --dbname "$DB_URL" "$BACKUP_PATH"
echo "RESTORE_OK postgres $BACKUP_PATH"
