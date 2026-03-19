#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ARTIFACT_DIR="${APP_ROOT}/artifacts"
SUMMARY_LOG="${ARTIFACT_DIR}/faz1_verify_phase1_backup_restore.log"
GITIGNORE_SCAN_LOG="${ARTIFACT_DIR}/faz1_gitignore_scan.log"
REPO_SCAN_LOG="${ARTIFACT_DIR}/faz1_repo_scan.log"

mkdir -p "$ARTIFACT_DIR"
: > "$SUMMARY_LOG"
: > "$GITIGNORE_SCAN_LOG"
: > "$REPO_SCAN_LOG"

log() {
  local line="$1"
  echo "$line" | tee -a "$SUMMARY_LOG"
}

fail() {
  local step="$1"
  local reason="$2"
  log "FAIL[$step]: $reason"
  log "SUMMARY: FAIL"
  exit 1
}

log "T-1.R1 pg_dump / psql zemin doğrulaması"
[[ -f "${APP_ROOT}/backend/Dockerfile" ]] || fail "R1" "backend/Dockerfile yok"
grep -q "postgresql-client" "${APP_ROOT}/backend/Dockerfile" || fail "R1" "Dockerfile postgresql-client içermiyor"
grep -q "backup-restore-s3-gate:" "${APP_ROOT}/.github/workflows/deploy-gate.yml" || fail "R1" "backup gate workflow'da yok"
grep -q "Install PostgreSQL client tools" "${APP_ROOT}/.github/workflows/deploy-gate.yml" || fail "R1" "CI'da postgresql-client kurulum adımı yok"
command -v pg_dump >/dev/null 2>&1 || fail "R1" "pg_dump bulunamadı"
command -v psql >/dev/null 2>&1 || fail "R1" "psql bulunamadı"
pg_dump --version | tee "${ARTIFACT_DIR}/faz1_pg_dump_version.log"
psql --version | tee "${ARTIFACT_DIR}/faz1_psql_version.log"
log "PASS[R1]"

log "T-1.H1/H2 .gitignore yeniden yazım + zorunlu kural doğrulaması"
GITIGNORE_PATH="${APP_ROOT}/.gitignore"
[[ -f "$GITIGNORE_PATH" ]] || fail "H1" ".gitignore yok"

required_rules=(
  "backups/*.sql"
  "backups/*.bak"
  "admin_token.txt"
  "*.sqlite"
  "*.sqlite3"
  "*.db"
)
for rule in "${required_rules[@]}"; do
  grep -Fxq "$rule" "$GITIGNORE_PATH" || fail "H2" "eksik ignore kuralı: $rule"
  echo "REQUIRED_RULE_OK $rule" >> "$GITIGNORE_SCAN_LOG"
done

if grep -n '^[[:space:]]*-e[[:space:]]*$' "$GITIGNORE_PATH" > "${ARTIFACT_DIR}/faz1_gitignore_minus_e_scan.log"; then
  bad_lines="$(cat "${ARTIFACT_DIR}/faz1_gitignore_minus_e_scan.log")"
  fail "H2" "bozuk -e satırı bulundu: ${bad_lines}"
else
  echo "NO_MINUS_E_LINE" > "${ARTIFACT_DIR}/faz1_gitignore_minus_e_scan.log"
fi

NORMALIZED="$(sed 's/[[:space:]]\+$//' "$GITIGNORE_PATH" | sed '/^$/d')"
DUPLICATES="$(echo "$NORMALIZED" | sort | uniq -d || true)"
if [[ -n "$DUPLICATES" ]]; then
  echo "$DUPLICATES" > "${ARTIFACT_DIR}/faz1_gitignore_duplicates.log"
  fail "H2" "duplicate ignore satırı bulundu: $DUPLICATES"
else
  echo "NO_DUPLICATE_RULE" > "${ARTIFACT_DIR}/faz1_gitignore_duplicates.log"
fi

{
  echo "# gitignore_length"
  wc -l "$GITIGNORE_PATH"
  echo "# required_rules"
  printf '%s
' "${required_rules[@]}"
  echo "# minus_e_scan"
  cat "${ARTIFACT_DIR}/faz1_gitignore_minus_e_scan.log"
  echo "# duplicate_scan"
  cat "${ARTIFACT_DIR}/faz1_gitignore_duplicates.log"
} >> "$GITIGNORE_SCAN_LOG"
log "PASS[H1/H2]"

log "T-1.H5 CI gate enforce kontrolü"
grep -q "bash scripts/verify_phase1_backup_restore.sh" "${APP_ROOT}/.github/workflows/deploy-gate.yml" || fail "H5" "backup gate verify script çağrısı yok"
grep -q "faz1_repo_scan" "${APP_ROOT}/.github/workflows/deploy-gate.yml" || fail "H5" "repo scan artifact upload yok"
grep -q "faz1_gitignore" "${APP_ROOT}/.github/workflows/deploy-gate.yml" || fail "H5" "gitignore scan artifact upload yok"
log "PASS[H5]"

log "T-1.R2/R3 backup-restore script guard kontrolü"
grep -q "Sadece PostgreSQL DATABASE_URL desteklenir" "${APP_ROOT}/scripts/db_backup.sh" || fail "R2" "backup postgres guard eksik"
grep -q "pg_dump bulunamadı" "${APP_ROOT}/scripts/db_backup.sh" || fail "R2" "backup pg_dump guard eksik"
grep -q "backup dosyası boş" "${APP_ROOT}/scripts/db_backup.sh" || fail "R2" "backup empty dump guard eksik"
grep -q "Sadece PostgreSQL DATABASE_URL desteklenir" "${APP_ROOT}/scripts/db_restore.sh" || fail "R3" "restore postgres guard eksik"
grep -q "psql bulunamadı" "${APP_ROOT}/scripts/db_restore.sh" || fail "R3" "restore psql guard eksik"
grep -q -- "--reset" "${APP_ROOT}/scripts/db_restore.sh" || fail "R3" "restore reset akışı eksik"
log "PASS[R2/R3]"

log "T-1.R4 scheduler model doğrulaması"
SCHEDULER_FILE="${APP_ROOT}/backend/services/db_backup_scheduler_service.py"
[[ -f "$SCHEDULER_FILE" ]] || fail "R4" "scheduler dosyası yok"
grep -q 'SCHEDULER_MODEL = "backend_scheduler"' "$SCHEDULER_FILE" || fail "R4" "resmi scheduler backend değil"
grep -q "BACKUP_SCHEDULER_ENABLED" "$SCHEDULER_FILE" || fail "R4" "scheduler enable flag yok"
grep -q "BACKUP_SCHEDULER_INTERVAL_SECONDS" "$SCHEDULER_FILE" || fail "R4" "scheduler interval env yok"
cp "$SCHEDULER_FILE" "${ARTIFACT_DIR}/faz1_scheduler_model_source.py"
cat > "${ARTIFACT_DIR}/faz1_scheduler_model_decision.txt" <<'EOF'
OFFICIAL_SCHEDULER_MODEL=backend_scheduler
SECONDARY_CRON_STATUS=non-authoritative_reference_only
EOF
log "PASS[R4]"

log "T-1.R5 full cycle backup->reset->restore"
bash "${APP_ROOT}/scripts/db_backup_restore_full_cycle_test.sh" || fail "R5" "full cycle test başarısız"
[[ -f "${ARTIFACT_DIR}/backup.log" ]] || fail "R5" "backup.log yok"
[[ -f "${ARTIFACT_DIR}/restore.log" ]] || fail "R5" "restore.log yok"
[[ -f "${ARTIFACT_DIR}/db_backup_restore_test.log" ]] || fail "R5" "full cycle log yok"
grep -q "ROW_COUNT_BEFORE=" "${ARTIFACT_DIR}/db_backup_restore_test.log" || fail "R5" "before row count yok"
grep -q "ROW_COUNT_AFTER=" "${ARTIFACT_DIR}/db_backup_restore_test.log" || fail "R5" "after row count yok"
grep -q "ROW_COUNT_MARKER=" "${ARTIFACT_DIR}/db_backup_restore_test.log" || fail "R5" "marker row count yok"
grep -q "DATA_FOUND_AFTER_RESTORE" "${ARTIFACT_DIR}/db_backup_restore_test.log" || fail "R5" "restore marker doğrulaması yok"
log "PASS[R5]"

log "T-1.H3/T-1.R6 repo scan + dump güvenlik taraması"
TMP_BACKUP_PATH="${APP_ROOT}/backups/faz1_security_scan_$(date +%s).sql"
TMP_BACKUP_PATH="$(bash "${APP_ROOT}/scripts/db_backup.sh" "$TMP_BACKUP_PATH" | tail -n 1)"
[[ -s "$TMP_BACKUP_PATH" ]] || fail "R6" "security scan backup üretilemedi"

if grep -E -i "(AKIA[0-9A-Z]{16}|SG\.[A-Za-z0-9._-]{20,}|sk-[A-Za-z0-9]{20,}|xoxb-[A-Za-z0-9-]{20,}|Bearer [A-Za-z0-9._-]{20,})" "$TMP_BACKUP_PATH"   | grep -Eiv "(_encrypted|COPY public\.|changed_fields)"   > "${ARTIFACT_DIR}/faz1_dump_scan_findings.log"; then
  fail "R6" "dump security scan secret/token pattern buldu"
else
  echo "NO_SECRET_PATTERN_FOUND" > "${ARTIFACT_DIR}/faz1_dump_scan_findings.log"
fi
rm -f "$TMP_BACKUP_PATH"

(
  cd "$APP_ROOT"
  echo "# find . -iname "*.sql""
  find . -iname "*.sql"
  echo "# find . -iname "*.bak""
  find . -iname "*.bak"
  echo "# find . -iname "*.sqlite" -o -iname "*.sqlite3" -o -iname "*.db""
  find . -iname "*.sqlite" -o -iname "*.sqlite3" -o -iname "*.db"
  echo "# find . -name "admin_token.txt""
  find . -name "admin_token.txt"
  echo "# grep -n '^[[:space:]]*-e[[:space:]]*$' .gitignore"
  grep -n '^[[:space:]]*-e[[:space:]]*$' .gitignore || true
  echo "# sort .gitignore | uniq -d"
  sort .gitignore | uniq -d || true
) > "$REPO_SCAN_LOG"

scan_sql="$(cd "$APP_ROOT" && find . -iname "*.sql" | tr -d '[:space:]')"
scan_bak="$(cd "$APP_ROOT" && find . -iname "*.bak" | tr -d '[:space:]')"
scan_db="$(cd "$APP_ROOT" && find . -iname "*.sqlite" -o -iname "*.sqlite3" -o -iname "*.db" | tr -d '[:space:]')"
scan_token="$(cd "$APP_ROOT" && find . -name "admin_token.txt" | tr -d '[:space:]')"

if [[ -n "$scan_sql$scan_bak$scan_db$scan_token" ]]; then
  fail "H3" "repo scan yasaklı dosya buldu (detay: ${REPO_SCAN_LOG})"
fi

echo "NO_FORBIDDEN_TRACKED_FILES" > "${ARTIFACT_DIR}/faz1_repo_scan_forbidden_files.log"
echo "NO_FORBIDDEN_PATH_FOUND" > "${ARTIFACT_DIR}/faz1_repo_scan_found_forbidden_paths.log"
echo "NO_CLEANUP_NEEDED" > "${ARTIFACT_DIR}/faz1_cleanup_removed_files.log"
log "PASS[H3/R6]"

log "---- verify summary ----"
log "gitignore_hygiene: PASS"
log "repo_scan: PASS"
log "backup_restore: PASS"
log "SUMMARY: PASS"
