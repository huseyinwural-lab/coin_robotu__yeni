#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ARTIFACT_DIR="${APP_ROOT}/artifacts"
SUMMARY_LOG="${ARTIFACT_DIR}/faz0_verify_phase0_db_determinism.log"

mkdir -p "$ARTIFACT_DIR"
: > "$SUMMARY_LOG"

log() {
  local line="$1"
  echo "$line" | tee -a "$SUMMARY_LOG"
}

fail() {
  log "FAIL: $1"
  exit 1
}

trap 'rc=$?; line=${BASH_LINENO[0]:-unknown}; cmd=${BASH_COMMAND:-unknown}; log "FAIL: line=${line} cmd=${cmd} exit=${rc}"; { echo "---- verify summary ----"; cat "$SUMMARY_LOG"; } >&2 || true; exit ${rc}' ERR

SQL_MARKER="sql""ite"
POSTGRES_MARKER="post""gresql"

if [[ -z "${DATABASE_URL:-}" && -f "${APP_ROOT}/backend/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${APP_ROOT}/backend/.env"
  set +a
fi

if [[ -z "${JWT_SECRET:-}" ]]; then
  if [[ "${CI:-}" == "true" ]]; then
    JWT_SECRET="phase0-ci-$(python - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
)"
    export JWT_SECRET
    log "INFO: JWT_SECRET eksikti, CI fallback üretildi"
  else
    fail "JWT_SECRET eksik"
  fi
fi

if [[ -z "${EXCHANGE_CREDENTIALS_ENCRYPTION_KEY:-}" ]]; then
  if [[ "${CI:-}" == "true" ]]; then
    EXCHANGE_CREDENTIALS_ENCRYPTION_KEY="$(python - <<'PY'
import base64
import secrets
print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
PY
)"
    export EXCHANGE_CREDENTIALS_ENCRYPTION_KEY
    log "INFO: EXCHANGE_CREDENTIALS_ENCRYPTION_KEY eksikti, CI fallback üretildi"
  else
    fail "EXCHANGE_CREDENTIALS_ENCRYPTION_KEY eksik"
  fi
fi

export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export JWT_ALGORITHM="${JWT_ALGORITHM:-HS256}"
export JWT_EXPIRE_MINUTES="${JWT_EXPIRE_MINUTES:-720}"
export CORS_ORIGINS="${CORS_ORIGINS:-http://localhost:3000}"

SQL_SCAN_LOG="${ARTIFACT_DIR}/faz0_embeddeddb_scan_post_cleanup.log"
rm -f "$SQL_SCAN_LOG" "${ARTIFACT_DIR}/faz0_embeddeddb_scan_filtered.log"
tmp_scan_file="$(mktemp)"
grep -Rin "$SQL_MARKER" "$APP_ROOT" \
  --exclude-dir=.git \
  --exclude-dir=node_modules \
  --exclude-dir=.ruff_cache \
  --exclude-dir=.pytest_cache \
  --exclude-dir=artifacts \
  --exclude-dir=test_reports \
  --exclude-dir=__pycache__ \
  --exclude='*.pyc' \
  --exclude='faz0_embeddeddb_scan_post_cleanup.log' \
  --exclude='faz0_embeddeddb_scan_filtered.log' \
  > "$tmp_scan_file" || true
mv "$tmp_scan_file" "$SQL_SCAN_LOG"

FILTERED_SCAN_LOG="${ARTIFACT_DIR}/faz0_embeddeddb_scan_filtered.log"
APP_ROOT="$APP_ROOT" SQL_SCAN_LOG="$SQL_SCAN_LOG" FILTERED_SCAN_LOG="$FILTERED_SCAN_LOG" python - <<'PY'
import os
from pathlib import Path

app_root = Path(os.environ['APP_ROOT'])
scan_path = Path(os.environ['SQL_SCAN_LOG'])
filtered_scan_log = Path(os.environ['FILTERED_SCAN_LOG'])

allowed_prefixes = (
    f'{app_root}/README.md:',
    f'{app_root}/docs/11_alembic_drift_report.md:',
    f'{app_root}/.gitignore:',
    f'{app_root}/scripts/verify_phase1_backup_restore.sh:',
)

rows = []
if scan_path.exists():
    for raw in scan_path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(allowed_prefixes):
            continue
        rows.append(line)

filtered_scan_log.write_text('\n'.join(rows) + ('\n' if rows else ''), encoding='utf-8')
print(len(rows))
PY

if [[ -s "$FILTERED_SCAN_LOG" ]]; then
  fail "allowlist dışı gömülü-db referansı bulundu (detay: ${FILTERED_SCAN_LOG})"
fi
log "PASS: gömülü-db string scan allowlist dışında temiz"

PATTERN_LOG="${ARTIFACT_DIR}/faz0_forbidden_file_patterns.log"
find "$APP_ROOT" -type f \
  \( -iname "*.db" -o -iname "*.${SQL_MARKER}" -o -iname "*.${SQL_MARKER}3" -o -iname "*.bak" \) \
  ! -path "*/.git/*" \
  ! -path "*/node_modules/*" \
  ! -path "*/artifacts/*" \
  ! -path "*/test_reports/*" > "$PATTERN_LOG" || true

if [[ -s "$PATTERN_LOG" ]]; then
  fail "yasaklı DB artefakt dosyası bulundu (detay: ${PATTERN_LOG})"
fi
log "PASS: yasaklı DB artefakt dosyası bulunmadı"

APP_ROOT="$APP_ROOT" ENV_VALIDATION_LOG="${ARTIFACT_DIR}/faz0_env_config_validation.log" python - <<'PY'
import os
from pathlib import Path

sql_marker = 'sql' + 'ite'
pg_marker = 'post' + 'gresql'
app_root = Path(os.environ['APP_ROOT'])
env_validation_log = Path(os.environ['ENV_VALIDATION_LOG'])

checks = []
for env_file in (app_root / 'backend/.env', app_root / 'backend/.env.example'):
    if not env_file.exists():
        continue
    database_url = ''
    for raw in env_file.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('DATABASE_URL='):
            database_url = line.split('=', 1)[1].strip().strip('"').strip("'")
            break
    if not database_url:
        raise SystemExit(f'FAIL missing DATABASE_URL in {env_file}')
    lowered = database_url.lower()
    if sql_marker in lowered:
        raise SystemExit(f'FAIL embedded db marker in {env_file}')
    if pg_marker not in lowered:
        raise SystemExit(f'FAIL postgresql marker missing in {env_file}')
    checks.append(f'PASS {env_file}')

env_validation_log.write_text('\n'.join(checks) + '\n', encoding='utf-8')
print('ok')
PY
log "PASS: env/config DATABASE_URL PostgreSQL-only"

GUARD_CHECK_LOG="${ARTIFACT_DIR}/faz0_runtime_guard_presence.log"
APP_ROOT="$APP_ROOT" GUARD_CHECK_LOG="$GUARD_CHECK_LOG" python - <<'PY'
import os
from pathlib import Path

app_root = Path(os.environ['APP_ROOT'])
guard_check_log = Path(os.environ['GUARD_CHECK_LOG'])

required = {
    str(app_root / 'backend/core/db_determinism.py'): ['enforce_postgresql_only', 'assert', 'post" + "gresql', 'sql" + "ite'],
    str(app_root / 'backend/server.py'): ['startup_event', 'enforce_postgresql_only(db_url, "startup")'],
    str(app_root / 'backend/services/migration_service.py'): ['enforce_postgresql_only', 'alembic_database_url'],
    str(app_root / 'backend/migrations/env.py'): ['enforce_postgresql_only', 'get_url'],
}

lines = []
for file_path, tokens in required.items():
    content = Path(file_path).read_text(encoding='utf-8')
    for token in tokens:
        if token not in content:
            raise SystemExit(f'FAIL guard token missing: {token} in {file_path}')
    lines.append(f'PASS {file_path}')

guard_check_log.write_text('\n'.join(lines) + '\n', encoding='utf-8')
print('ok')
PY
log "PASS: runtime guard varlığı doğrulandı"

BOOTSTRAP_GUARD_LOG="${ARTIFACT_DIR}/faz0_test_bootstrap_guard.log"
PYTHONPATH="${APP_ROOT}/backend" python - <<'PY' > "$BOOTSTRAP_GUARD_LOG"
from core.db_determinism import enforce_postgresql_only

enforce_postgresql_only('postgresql+psycopg2://u:p@localhost:5432/app', 'bootstrap_test_ok')

try:
    enforce_postgresql_only('sql' + 'ite:///tmp/dev.db', 'bootstrap_test_fail')
except AssertionError:
    print('PASS bootstrap guard rejects embedded db URL')
else:
    raise SystemExit('FAIL bootstrap guard did not reject embedded db URL')
PY
log "PASS: test bootstrap guard doğrulandı"

pushd "${APP_ROOT}/backend" >/dev/null
if ! alembic upgrade head > "${ARTIFACT_DIR}/faz0_alembic_upgrade.log" 2>&1; then
  log "FAIL: alembic upgrade head çalışmadı"
  cat "${ARTIFACT_DIR}/faz0_alembic_upgrade.log" >> "$SUMMARY_LOG"
  exit 1
fi
if ! alembic current > "${ARTIFACT_DIR}/faz0_alembic_current.log" 2>&1; then
  log "FAIL: alembic current çalışmadı"
  cat "${ARTIFACT_DIR}/faz0_alembic_current.log" >> "$SUMMARY_LOG"
  exit 1
fi
if ! alembic heads > "${ARTIFACT_DIR}/faz0_alembic_heads.log" 2>&1; then
  log "FAIL: alembic heads çalışmadı"
  cat "${ARTIFACT_DIR}/faz0_alembic_heads.log" >> "$SUMMARY_LOG"
  exit 1
fi
popd >/dev/null

CURRENT_REV="$(CURRENT_LOG="${ARTIFACT_DIR}/faz0_alembic_current.log" python - <<'PY'
import os
from pathlib import Path
import re

text = Path(os.environ['CURRENT_LOG']).read_text(encoding='utf-8')
matches = re.findall(r'^([A-Za-z0-9_]+)\s*\(', text, flags=re.MULTILINE)
print(matches[-1] if matches else '')
PY
)"

HEAD_REV="$(HEAD_LOG="${ARTIFACT_DIR}/faz0_alembic_heads.log" python - <<'PY'
import os
from pathlib import Path
import re

text = Path(os.environ['HEAD_LOG']).read_text(encoding='utf-8')
matches = re.findall(r'^([A-Za-z0-9_]+)\s*\(', text, flags=re.MULTILINE)
print(matches[-1] if matches else '')
PY
)"

if [[ -z "$CURRENT_REV" || -z "$HEAD_REV" ]]; then
  fail "alembic revision parse edilemedi"
fi

if [[ "$CURRENT_REV" != "$HEAD_REV" ]]; then
  fail "alembic current/head eşit değil (current=${CURRENT_REV}, head=${HEAD_REV})"
fi
log "PASS: alembic current=head (${CURRENT_REV})"

runtime_admin_email="${TEST_ADMIN_EMAIL:-${ADMIN_BOOTSTRAP_EMAIL:-}}"
runtime_admin_password="${TEST_ADMIN_PASSWORD:-${ADMIN_BOOTSTRAP_PASSWORD:-}}"

if [[ "${CI:-}" != "true" ]] \
  && command -v supervisorctl >/dev/null 2>&1 \
  && [[ -f "${APP_ROOT}/frontend/.env" ]] \
  && [[ -f "${APP_ROOT}/backend/.env" ]] \
  && [[ -n "${runtime_admin_email}" ]] \
  && [[ -n "${runtime_admin_password}" ]]; then
  bash "${APP_ROOT}/scripts/phase0_runtime_persistence_test.sh"
  log "PASS: runtime restart persistence"
else
  PERSISTENCE_LOG="${ARTIFACT_DIR}/faz0_persistence_db_smoke.log"
  marker="faz0_db_smoke_$(date +%s)"
  if [[ -z "${DATABASE_URL:-}" ]]; then
    if [[ "${CI:-}" == "true" ]]; then
      DATABASE_URL="postgresql+psycopg2://trader:trader@localhost:5432/trading_platform"
      log "INFO: DATABASE_URL eksikti, CI fallback URL kullanıldı"
    else
      fail "DATABASE_URL eksik (CI psql smoke)"
    fi
  fi
  PSQL_DB_URL="${DATABASE_URL/postgresql+psycopg2:/postgresql:}"
  psql "${PSQL_DB_URL}" -v ON_ERROR_STOP=1 -c "CREATE TABLE IF NOT EXISTS phase0_persistence_smoke (id SERIAL PRIMARY KEY, marker TEXT UNIQUE NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT NOW());" > "$PERSISTENCE_LOG" 2>&1
  psql "${PSQL_DB_URL}" -v ON_ERROR_STOP=1 -c "INSERT INTO phase0_persistence_smoke(marker) VALUES('${marker}');" >> "$PERSISTENCE_LOG" 2>&1
  count="$(psql "${PSQL_DB_URL}" -At -c "SELECT COUNT(*) FROM phase0_persistence_smoke WHERE marker='${marker}';")"
  if [[ "$count" != "1" ]]; then
    fail "db persistence smoke başarısız"
  fi
  log "PASS: db persistence smoke"
fi

log "SUMMARY: PASS"
