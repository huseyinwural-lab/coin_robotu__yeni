#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ARTIFACT_LOG="${APP_ROOT}/artifacts/backup.log"
BACKUP_DIR="${APP_ROOT}/backups"
KEEP_COUNT="${BACKUP_KEEP_COUNT:-7}"
NOW_TS="$(date +%F_%H-%M-%S)"
OUT_PATH="${1:-${BACKUP_DIR}/db_${NOW_TS}.sql}"
DB_URL="${DATABASE_URL:-}"
PSQL_DB_URL=""

mkdir -p "${APP_ROOT}/artifacts" "$BACKUP_DIR"

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

if [[ -z "$DB_URL" ]]; then
  log "ERROR: DATABASE_URL boş olamaz"
  exit 1
fi

if [[ "$PSQL_DB_URL" != postgresql* ]]; then
  log "ERROR: Sadece PostgreSQL DATABASE_URL desteklenir"
  exit 1
fi

if ! command -v pg_dump >/dev/null 2>&1; then
  log "ERROR: pg_dump bulunamadı"
  exit 1
fi

log "BACKUP_START path=$OUT_PATH"
if ! pg_dump "$PSQL_DB_URL" --schema=public --no-owner --no-privileges --format=plain > "$OUT_PATH"; then
  log "ERROR: pg_dump başarısız"
  exit 1
fi

if [[ ! -s "$OUT_PATH" ]]; then
  log "ERROR: backup dosyası boş"
  exit 1
fi

if command -v git >/dev/null 2>&1 && git -C "$APP_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if [[ "$OUT_PATH" == "${APP_ROOT}/"* ]]; then
    rel_path="${OUT_PATH#${APP_ROOT}/}"
    if ! git -C "$APP_ROOT" check-ignore -q "$rel_path"; then
      log "ERROR: backup output gitignore kapsamında değil path=$rel_path"
      exit 1
    fi
  fi
fi

# rotation: son 7 backup kalsın
log "BACKUP_ROTATION_KEEP_COUNT=${KEEP_COUNT}"
mapfile -t backup_files < <(ls -1t "$BACKUP_DIR"/db_*.sql 2>/dev/null || true)
if (( ${#backup_files[@]} > KEEP_COUNT )); then
  for file in "${backup_files[@]:KEEP_COUNT}"; do
    rm -f "$file"
    log "BACKUP_ROTATION_REMOVED path=$file"
  done
fi

log "BACKUP_OK path=$OUT_PATH size_bytes=$(wc -c < "$OUT_PATH")"

S3_UPLOAD_CLI="${APP_ROOT}/backend/cli/upload_backup_to_s3.py"
if [[ -f "$S3_UPLOAD_CLI" ]]; then
  if ! s3_output="$(PYTHONPATH="${APP_ROOT}/backend" python "$S3_UPLOAD_CLI" "$OUT_PATH" 2>&1)"; then
    while IFS= read -r line; do
      [[ -n "$line" ]] && log "$line"
    done <<< "$s3_output"
    log "ERROR: S3 upload adımı başarısız"
    exit 1
  fi
  while IFS= read -r line; do
    [[ -n "$line" ]] && log "$line"
  done <<< "$s3_output"
fi

echo "$OUT_PATH"
