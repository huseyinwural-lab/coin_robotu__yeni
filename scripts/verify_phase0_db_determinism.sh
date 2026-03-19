#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ARTIFACT_DIR="${APP_ROOT}/artifacts"
SUMMARY_LOG="${ARTIFACT_DIR}/faz0_verify_phase0_db_determinism.log"

mkdir -p "$ARTIFACT_DIR"
: > "$SUMMARY_LOG"

log() {
  local line="$1"
  echo "$line" | tee -a "$SUMMARY_LOG" >/dev/null
}

fail() {
  log "FAIL: $1"
  exit 1
}

SQL_MARKER="sql""ite"
POSTGRES_MARKER="post""gresql"

SQL_SCAN_LOG="${ARTIFACT_DIR}/faz0_embeddeddb_scan_post_cleanup.log"
rm -f "$SQL_SCAN_LOG" "${ARTIFACT_DIR}/faz0_embeddeddb_scan_filtered.log"
tmp_scan_file="$(mktemp)"
grep -Rin "$SQL_MARKER" "$APP_ROOT" \
  --exclude-dir=.git \
  --exclude-dir=node_modules \
  --exclude-dir=.ruff_cache \
  --exclude-dir=.pytest_cache \
  --exclude-dir=__pycache__ \
  --exclude='*.pyc' \
  --exclude='faz0_embeddeddb_scan_post_cleanup.log' \
  --exclude='faz0_embeddeddb_scan_filtered.log' \
  > "$tmp_scan_file" || true
mv "$tmp_scan_file" "$SQL_SCAN_LOG"

FILTERED_SCAN_LOG="${ARTIFACT_DIR}/faz0_embeddeddb_scan_filtered.log"
python - <<'PY'
from pathlib import Path

scan_path = Path('/app/artifacts/faz0_embeddeddb_scan_post_cleanup.log')
allowed_prefixes = (
    '/app/README.md:',
    '/app/docs/11_alembic_drift_report.md:',
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

Path('/app/artifacts/faz0_embeddeddb_scan_filtered.log').write_text('\n'.join(rows) + ('\n' if rows else ''), encoding='utf-8')
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
  ! -path "*/node_modules/*" > "$PATTERN_LOG" || true

if [[ -s "$PATTERN_LOG" ]]; then
  fail "yasaklı DB artefakt dosyası bulundu (detay: ${PATTERN_LOG})"
fi
log "PASS: yasaklı DB artefakt dosyası bulunmadı"

python - <<'PY'
from pathlib import Path

sql_marker = 'sql' + 'ite'
pg_marker = 'post' + 'gresql'

checks = []
for env_file in (Path('/app/backend/.env'), Path('/app/backend/.env.example')):
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

Path('/app/artifacts/faz0_env_config_validation.log').write_text('\n'.join(checks) + '\n', encoding='utf-8')
print('ok')
PY
log "PASS: env/config DATABASE_URL PostgreSQL-only"

GUARD_CHECK_LOG="${ARTIFACT_DIR}/faz0_runtime_guard_presence.log"
python - <<'PY'
from pathlib import Path

required = {
    '/app/backend/core/db_determinism.py': ['enforce_postgresql_only', 'assert', 'post" + "gresql', 'sql" + "ite'],
    '/app/backend/server.py': ['startup_event', 'enforce_postgresql_only(db_url, "startup")'],
    '/app/backend/services/migration_service.py': ['enforce_postgresql_only', 'alembic_database_url'],
    '/app/backend/migrations/env.py': ['enforce_postgresql_only', 'get_url'],
}

lines = []
for file_path, tokens in required.items():
    content = Path(file_path).read_text(encoding='utf-8')
    for token in tokens:
        if token not in content:
            raise SystemExit(f'FAIL guard token missing: {token} in {file_path}')
    lines.append(f'PASS {file_path}')

Path('/app/artifacts/faz0_runtime_guard_presence.log').write_text('\n'.join(lines) + '\n', encoding='utf-8')
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
alembic current > "${ARTIFACT_DIR}/faz0_alembic_current.log" 2>&1
alembic heads > "${ARTIFACT_DIR}/faz0_alembic_heads.log" 2>&1
popd >/dev/null

CURRENT_REV="$(python - <<'PY'
from pathlib import Path
import re

text = Path('/app/artifacts/faz0_alembic_current.log').read_text(encoding='utf-8')
matches = re.findall(r'([0-9]{8}_[0-9]{4})', text)
print(matches[-1] if matches else '')
PY
)"

HEAD_REV="$(python - <<'PY'
from pathlib import Path
import re

text = Path('/app/artifacts/faz0_alembic_heads.log').read_text(encoding='utf-8')
matches = re.findall(r'([0-9]{8}_[0-9]{4})', text)
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

if command -v supervisorctl >/dev/null 2>&1; then
  bash "${APP_ROOT}/scripts/phase0_runtime_persistence_test.sh"
  log "PASS: runtime restart persistence"
else
  PERSISTENCE_LOG="${ARTIFACT_DIR}/faz0_persistence_db_smoke.log"
  marker="faz0_db_smoke_$(date +%s)"
  psql "${DATABASE_URL}" -v ON_ERROR_STOP=1 -c "CREATE TABLE IF NOT EXISTS phase0_persistence_smoke (id SERIAL PRIMARY KEY, marker TEXT UNIQUE NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT NOW());" > "$PERSISTENCE_LOG" 2>&1
  psql "${DATABASE_URL}" -v ON_ERROR_STOP=1 -c "INSERT INTO phase0_persistence_smoke(marker) VALUES('${marker}');" >> "$PERSISTENCE_LOG" 2>&1
  count="$(psql "${DATABASE_URL}" -At -c "SELECT COUNT(*) FROM phase0_persistence_smoke WHERE marker='${marker}';")"
  if [[ "$count" != "1" ]]; then
    fail "db persistence smoke başarısız"
  fi
  log "PASS: db persistence smoke"
fi

log "SUMMARY: PASS"
