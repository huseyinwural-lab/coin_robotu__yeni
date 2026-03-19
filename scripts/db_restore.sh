#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

if [[ $# -lt 1 ]]; then
  echo "Kullanım: bash /app/scripts/db_restore.sh <backup_path> [--reset]"
  exit 1
fi

BACKUP_PATH="$1"
RESET_DB="${2:-}"
DB_URL="${DATABASE_URL:-}"
PSQL_DB_URL=""
ARTIFACT_LOG="${APP_ROOT}/artifacts/restore.log"

mkdir -p "${APP_ROOT}/artifacts"

log() {
  local line
  line="[$(date '+%F %T')] $*"
  echo "$line" | tee -a "$ARTIFACT_LOG"
}

load_env_if_missing() {
  if [[ -n "$DB_URL" ]]; then
    return
  fi
  if [[ -f "${APP_ROOT}/backend/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${APP_ROOT}/backend/.env"
    set +a
    DB_URL="${DATABASE_URL:-}"
  fi
}

load_env_if_missing

PSQL_DB_URL="${DB_URL/postgresql+psycopg2:/postgresql:}"

if [[ ! -f "$BACKUP_PATH" ]]; then
  log "ERROR: backup bulunamadı: $BACKUP_PATH"
  exit 1
fi

if [[ -z "$DB_URL" ]]; then
  log "ERROR: DATABASE_URL boş olamaz"
  exit 1
fi

if [[ "$PSQL_DB_URL" != postgresql* ]]; then
  log "ERROR: Sadece PostgreSQL DATABASE_URL desteklenir"
  exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
  log "ERROR: psql bulunamadı"
  exit 1
fi

log "PSQL_VERSION=$(psql --version | tr -d '\n')"

log "RESTORE_START backup=$BACKUP_PATH reset=${RESET_DB:-none}"

if [[ "$RESET_DB" == "--reset" ]]; then
  if ! psql "$PSQL_DB_URL" -v ON_ERROR_STOP=1 -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"; then
    log "ERROR: reset işlemi başarısız"
    exit 1
  fi
  log "RESET_OK"
fi

if ! psql "$PSQL_DB_URL" -v ON_ERROR_STOP=1 -f "$BACKUP_PATH"; then
  log "ERROR: restore işlemi başarısız"
  exit 1
fi

log "RESTORE_OK backup=$BACKUP_PATH"
