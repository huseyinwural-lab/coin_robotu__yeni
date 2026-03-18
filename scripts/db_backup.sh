#!/usr/bin/env bash
set -euo pipefail

OUT_PATH="${1:-/app/artifacts/db_backup_$(date +%Y%m%d_%H%M%S).bak}"
DB_URL="${DATABASE_URL:-}"

mkdir -p "$(dirname "$OUT_PATH")"

if [[ -z "$DB_URL" ]]; then
  echo "ERROR: DATABASE_URL boş olamaz"
  exit 1
fi

if [[ "$DB_URL" != postgresql* ]]; then
  echo "ERROR: Sadece PostgreSQL DATABASE_URL desteklenir"
  exit 1
fi

if ! command -v pg_dump >/dev/null 2>&1; then
  echo "ERROR: pg_dump bulunamadı"
  exit 1
fi

pg_dump "$DB_URL" --format=custom --no-owner --no-privileges --file "$OUT_PATH"
echo "BACKUP_OK postgres $OUT_PATH"
