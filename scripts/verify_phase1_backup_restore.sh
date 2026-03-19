#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ARTIFACT_DIR="${APP_ROOT}/artifacts"
SUMMARY_LOG="${ARTIFACT_DIR}/faz1_verify_phase1_backup_restore.log"

mkdir -p "$ARTIFACT_DIR"
: > "$SUMMARY_LOG"

log() {
  local line="$1"
  echo "$line" | tee -a "$SUMMARY_LOG"
}

fail() {
  log "FAIL: $1"
  log "SUMMARY: FAIL"
  exit 1
}

log "T-1.R1 pg_dump/psql ve install zemini"
[[ -f "${APP_ROOT}/backend/Dockerfile" ]] || fail "backend/Dockerfile yok"
grep -q "postgresql-client" "${APP_ROOT}/backend/Dockerfile" || fail "Dockerfile postgresql-client içermiyor"

grep -q "backup-restore-s3-gate:" "${APP_ROOT}/.github/workflows/deploy-gate.yml" || fail "backup gate workflow'da yok"
grep -q "Install PostgreSQL client tools" "${APP_ROOT}/.github/workflows/deploy-gate.yml" || fail "CI'da postgresql-client install adımı yok"

command -v pg_dump >/dev/null 2>&1 || fail "pg_dump bulunamadı"
command -v psql >/dev/null 2>&1 || fail "psql bulunamadı"
pg_dump --version | tee "${ARTIFACT_DIR}/faz1_pg_dump_version.log"
psql --version | tee "${ARTIFACT_DIR}/faz1_psql_version.log"
log "PASS: pg_dump ve psql erişilebilir"

log "T-1.R2/R3 backup-restore script statik güvenlik kontrolleri"
for script in "${APP_ROOT}/scripts/db_backup.sh" "${APP_ROOT}/scripts/db_restore.sh"; do
  [[ -f "$script" ]] || fail "Eksik script: $script"
done

grep -q "Sadece PostgreSQL DATABASE_URL desteklenir" "${APP_ROOT}/scripts/db_backup.sh" || fail "backup script postgres guard eksik"
grep -q "pg_dump bulunamadı" "${APP_ROOT}/scripts/db_backup.sh" || fail "backup script pg_dump guard eksik"
grep -q "backup dosyası boş" "${APP_ROOT}/scripts/db_backup.sh" || fail "backup script empty file guard eksik"
grep -q "BACKUP_ROTATION_REMOVED" "${APP_ROOT}/scripts/db_backup.sh" || fail "backup rotation log eksik"
grep -q "S3 upload adımı başarısız" "${APP_ROOT}/scripts/db_backup.sh" || fail "backup S3 fail control eksik"

grep -q "backup bulunamadı" "${APP_ROOT}/scripts/db_restore.sh" || fail "restore missing file guard eksik"
grep -q "Sadece PostgreSQL DATABASE_URL desteklenir" "${APP_ROOT}/scripts/db_restore.sh" || fail "restore postgres guard eksik"
grep -q "psql bulunamadı" "${APP_ROOT}/scripts/db_restore.sh" || fail "restore psql guard eksik"
grep -q -- "--reset" "${APP_ROOT}/scripts/db_restore.sh" || fail "restore reset path eksik"
log "PASS: backup/restore guard statik kontrolleri tamam"

log "T-1.R4 scheduler modeli doğrulama"
SCHEDULER_FILE="${APP_ROOT}/backend/services/db_backup_scheduler_service.py"
[[ -f "$SCHEDULER_FILE" ]] || fail "scheduler service dosyası yok"
grep -q "SCHEDULER_MODEL = \"backend_scheduler\"" "$SCHEDULER_FILE" || fail "resmi scheduler modeli backend_scheduler değil"
grep -q "BACKUP_SCHEDULER_ENABLED" "$SCHEDULER_FILE" || fail "scheduler enable flag yok"
grep -q "BACKUP_SCHEDULER_INTERVAL_SECONDS" "$SCHEDULER_FILE" || fail "scheduler interval env yok"
cp "$SCHEDULER_FILE" "${ARTIFACT_DIR}/faz1_scheduler_model_source.py"
cat > "${ARTIFACT_DIR}/faz1_scheduler_model_decision.txt" <<'EOF'
OFFICIAL_SCHEDULER_MODEL=backend_scheduler
SECONDARY_CRON_STATUS=non-authoritative_reference_only
EOF
log "PASS: resmi scheduler modeli backend scheduler"

log "T-1.R5 full cycle revalidation"
bash "${APP_ROOT}/scripts/db_backup_restore_full_cycle_test.sh" || fail "full cycle test başarısız"
[[ -f "${ARTIFACT_DIR}/backup.log" ]] || fail "backup.log yok"
[[ -f "${ARTIFACT_DIR}/restore.log" ]] || fail "restore.log yok"
[[ -f "${ARTIFACT_DIR}/db_backup_restore_test.log" ]] || fail "full cycle log yok"
grep -Eq "S3_UPLOAD_(OK|SKIPPED|FAIL)" "${ARTIFACT_DIR}/backup.log" || fail "S3 upload sonucu backup logda yok"
grep -q "ROW_COUNT_BEFORE=" "${ARTIFACT_DIR}/db_backup_restore_test.log" || fail "before row count log eksik"
grep -q "ROW_COUNT_AFTER=" "${ARTIFACT_DIR}/db_backup_restore_test.log" || fail "after row count log eksik"
grep -q "ROW_COUNT_MARKER=" "${ARTIFACT_DIR}/db_backup_restore_test.log" || fail "marker row count log eksik"
grep -q "DATA_FOUND_AFTER_RESTORE" "${ARTIFACT_DIR}/db_backup_restore_test.log" || fail "marker restore doğrulaması yok"
log "PASS: full cycle backup->reset->restore zinciri geçti"

log "T-1.R6 backup security scan"
TMP_BACKUP_PATH="${APP_ROOT}/backups/faz1_security_scan_$(date +%s).sql"
TMP_BACKUP_PATH="$(bash "${APP_ROOT}/scripts/db_backup.sh" "$TMP_BACKUP_PATH" | tail -n 1)"
[[ -s "$TMP_BACKUP_PATH" ]] || fail "security scan için geçici backup üretilemedi"

if grep -E -i "(BEGIN PRIVATE KEY|AKIA[0-9A-Z]{16}|SG\.[A-Za-z0-9._-]{20,}|sk-[A-Za-z0-9]{20,}|xoxb-[A-Za-z0-9-]{20,}|Bearer [A-Za-z0-9._-]{20,})" "$TMP_BACKUP_PATH" \
  | grep -Eiv "(_encrypted|COPY public\.|changed_fields)" \
  > "${ARTIFACT_DIR}/faz1_dump_scan_findings.log"; then
  fail "backup dump içinde secret/token pattern bulundu"
else
  echo "NO_SECRET_PATTERN_FOUND" > "${ARTIFACT_DIR}/faz1_dump_scan_findings.log"
fi

rm -f "$TMP_BACKUP_PATH"

mapfile -t forbidden_tracked < <(git -C "$APP_ROOT" ls-files | grep -E '(^admin_token\.txt$|\.bak$|^backups/.*\.sql$)' || true)
if (( ${#forbidden_tracked[@]} > 0 )); then
  printf '%s\n' "${forbidden_tracked[@]}" > "${ARTIFACT_DIR}/faz1_repo_scan_forbidden_files.log"
  fail "repo içinde yasaklı tracked dump/token dosyası bulundu"
fi
echo "NO_FORBIDDEN_TRACKED_FILES" > "${ARTIFACT_DIR}/faz1_repo_scan_forbidden_files.log"

mapfile -t cleanup_candidates < <(ls -1 "${APP_ROOT}"/backups/*.sql "${APP_ROOT}"/backups/*.bak 2>/dev/null || true)
if (( ${#cleanup_candidates[@]} > 0 )); then
  printf '%s\n' "${cleanup_candidates[@]}" > "${ARTIFACT_DIR}/faz1_cleanup_removed_files.log"
  rm -f "${cleanup_candidates[@]}"
else
  echo "NO_CLEANUP_NEEDED" > "${ARTIFACT_DIR}/faz1_cleanup_removed_files.log"
fi

log "PASS: dump/repo scan ve cleanup tamam"

log "SUMMARY: PASS"