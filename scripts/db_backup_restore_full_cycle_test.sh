#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ARTIFACT_LOG="${APP_ROOT}/artifacts/db_backup_restore_test.log"
mkdir -p "${APP_ROOT}/artifacts"
: > "$ARTIFACT_LOG"

log_line() {
  echo "$1" | tee -a "$ARTIFACT_LOG"
}

load_env() {
  if [[ -f "${APP_ROOT}/backend/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${APP_ROOT}/backend/.env"
    set +a
  fi
}

load_env

DB_URL="${DATABASE_URL:-}"
PSQL_DB_URL="${DB_URL/postgresql+psycopg2:/postgresql:}"
if [[ -z "$DB_URL" ]]; then
  echo "ERROR: DATABASE_URL missing" >&2
  exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "ERROR: psql not found" >&2
  exit 1
fi

if ! psql "$PSQL_DB_URL" -v ON_ERROR_STOP=1 -c "CREATE TABLE IF NOT EXISTS test_table (id SERIAL PRIMARY KEY, marker TEXT NOT NULL);" >/dev/null; then
  echo "ERROR: test_table create failed" >&2
  exit 1
fi

if ! psql "$PSQL_DB_URL" -v ON_ERROR_STOP=1 -c "TRUNCATE TABLE test_table; INSERT INTO test_table(marker) VALUES ('backup_test');" >/dev/null; then
  echo "ERROR: test data insert failed" >&2
  exit 1
fi

before_count="$(psql "$PSQL_DB_URL" -t -A -c "SELECT COUNT(*) FROM test_table;")"
before_count="$(echo "$before_count" | tr -d '[:space:]')"
log_line "INSERT_OK"

backup_path="$(bash "${APP_ROOT}/scripts/db_backup.sh")"
backup_path="$(echo "$backup_path" | tail -n 1)"
if [[ ! -s "$backup_path" ]]; then
  echo "ERROR: backup file empty" >&2
  exit 1
fi
log_line "BACKUP_OK"

if ! psql "$PSQL_DB_URL" -v ON_ERROR_STOP=1 -c "TRUNCATE TABLE test_table;" >/dev/null; then
  echo "ERROR: db reset failed" >&2
  exit 1
fi
log_line "DB_RESET_OK"

if ! bash "${APP_ROOT}/scripts/db_restore.sh" "$backup_path" --reset >/dev/null; then
  echo "ERROR: restore failed" >&2
  exit 1
fi
log_line "RESTORE_OK"

after_marker_count="$(psql "$PSQL_DB_URL" -t -A -c "SELECT COUNT(*) FROM test_table WHERE marker='backup_test';")"
after_marker_count="$(echo "$after_marker_count" | tr -d '[:space:]')"
after_count="$(psql "$PSQL_DB_URL" -t -A -c "SELECT COUNT(*) FROM test_table;")"
after_count="$(echo "$after_count" | tr -d '[:space:]')"

if [[ "$after_marker_count" -ge 1 && "$after_count" == "$before_count" ]]; then
  log_line "DATA_FOUND_AFTER_RESTORE"
else
  echo "ERROR: restore integrity check failed (before=$before_count after=$after_count marker=$after_marker_count)" >&2
  exit 1
fi
