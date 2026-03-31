#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ARTIFACT_LOG="${APP_ROOT}/artifacts/db_backup_restore_test.log"
REPORT_JSON="${APP_ROOT}/artifacts/prod_backup_restore_proof.json"
PROBE_TABLE="phase0_backup_probe"
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

if ! psql "$PSQL_DB_URL" -v ON_ERROR_STOP=1 -c "CREATE SCHEMA IF NOT EXISTS public; CREATE TABLE IF NOT EXISTS public.${PROBE_TABLE} (id SERIAL PRIMARY KEY, marker TEXT NOT NULL);" >/dev/null; then
  echo "ERROR: test_table create failed" >&2
  exit 1
fi

if ! psql "$PSQL_DB_URL" -v ON_ERROR_STOP=1 -c "TRUNCATE TABLE public.${PROBE_TABLE}; INSERT INTO public.${PROBE_TABLE}(marker) VALUES ('backup_test');" >/dev/null; then
  echo "ERROR: test data insert failed" >&2
  exit 1
fi

before_count="$(psql "$PSQL_DB_URL" -t -A -c "SELECT COUNT(*) FROM public.${PROBE_TABLE};")"
before_count="$(echo "$before_count" | tr -d '[:space:]')"
table_count_before_reset="$(psql "$PSQL_DB_URL" -t -A -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" | tr -d '[:space:]')"
log_line "INSERT_OK"
log_line "ROW_COUNT_BEFORE=${before_count}"
log_line "TABLE_COUNT_BEFORE_RESET=${table_count_before_reset}"

backup_path="$(bash "${APP_ROOT}/scripts/db_backup.sh")"
backup_path="$(echo "$backup_path" | tail -n 1)"
if [[ ! -s "$backup_path" ]]; then
  echo "ERROR: backup file empty" >&2
  exit 1
fi
log_line "BACKUP_OK"
log_line "BACKUP_PATH=${backup_path}"

if ! psql "$PSQL_DB_URL" -v ON_ERROR_STOP=1 -c "DROP SCHEMA IF EXISTS public CASCADE;" >/dev/null; then
  echo "ERROR: db reset failed" >&2
  exit 1
fi
log_line "DB_RESET_OK"
table_count_after_reset="$(psql "$PSQL_DB_URL" -t -A -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" | tr -d '[:space:]')"
log_line "TABLE_COUNT_AFTER_RESET=${table_count_after_reset}"

if ! bash "${APP_ROOT}/scripts/db_restore.sh" "$backup_path" >/dev/null; then
  echo "ERROR: restore failed" >&2
  exit 1
fi
log_line "RESTORE_OK"

after_marker_count="$(psql "$PSQL_DB_URL" -t -A -c "SELECT COUNT(*) FROM public.${PROBE_TABLE} WHERE marker='backup_test';")"
after_marker_count="$(echo "$after_marker_count" | tr -d '[:space:]')"
after_count="$(psql "$PSQL_DB_URL" -t -A -c "SELECT COUNT(*) FROM public.${PROBE_TABLE};")"
after_count="$(echo "$after_count" | tr -d '[:space:]')"
table_count_after_restore="$(psql "$PSQL_DB_URL" -t -A -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" | tr -d '[:space:]')"
sample_marker_after_restore="$(psql "$PSQL_DB_URL" -t -A -c "SELECT marker FROM public.${PROBE_TABLE} ORDER BY id ASC LIMIT 1;" | tr -d '[:space:]')"
log_line "ROW_COUNT_AFTER=${after_count}"
log_line "ROW_COUNT_MARKER=${after_marker_count}"
log_line "TABLE_COUNT_AFTER_RESTORE=${table_count_after_restore}"
log_line "SAMPLE_MARKER_AFTER_RESTORE=${sample_marker_after_restore}"

if [[ "$after_marker_count" -ge 1 && "$after_count" == "$before_count" ]]; then
  log_line "DATA_FOUND_AFTER_RESTORE"
else
  echo "ERROR: restore integrity check failed (before=$before_count after=$after_count marker=$after_marker_count)" >&2
  exit 1
fi

python - <<PY
import json
from datetime import datetime, timezone
from pathlib import Path

report = {
    "status": "PASS",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "proof": {
        "backup_path": "${backup_path}",
        "row_count_before": int("${before_count}"),
        "row_count_after": int("${after_count}"),
        "marker_row_count_after": int("${after_marker_count}"),
        "table_count_before_reset": int("${table_count_before_reset}"),
        "table_count_after_reset": int("${table_count_after_reset}"),
        "table_count_after_restore": int("${table_count_after_restore}"),
        "sample_marker_after_restore": "${sample_marker_after_restore}",
    },
}

Path("${REPORT_JSON}").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
log_line "PROOF_JSON=${REPORT_JSON}"

psql "$PSQL_DB_URL" -v ON_ERROR_STOP=1 -c "DROP TABLE IF EXISTS public.${PROBE_TABLE};" >/dev/null || true
log_line "PROBE_TABLE_CLEANED=${PROBE_TABLE}"

if [[ -f "$backup_path" ]]; then
  rm -f "$backup_path"
  log_line "BACKUP_FILE_CLEANED path=${backup_path}"
fi
