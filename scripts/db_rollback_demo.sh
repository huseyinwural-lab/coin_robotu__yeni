#!/usr/bin/env bash
set -euo pipefail

SQLITE_PATH="${SQLITE_PATH:-/tmp/trading_platform_local.db}"
TMP_BACKUP="/tmp/rollback_demo_$(date +%s).bak"

bash /app/scripts/db_backup.sh "$TMP_BACKUP"

python - <<'PY'
import sqlite3, os
db_path = os.environ.get('SQLITE_PATH', '/tmp/trading_platform_local.db')
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS rollback_demo_marker (id INTEGER PRIMARY KEY, marker TEXT)")
cur.execute("INSERT INTO rollback_demo_marker(marker) VALUES ('mutated_after_backup')")
conn.commit()
cur.execute("SELECT COUNT(*) FROM rollback_demo_marker")
print('MUTATION_COUNT', cur.fetchone()[0])
conn.close()
PY

bash /app/scripts/db_restore.sh "$TMP_BACKUP"

python - <<'PY'
import sqlite3, os
db_path = os.environ.get('SQLITE_PATH', '/tmp/trading_platform_local.db')
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rollback_demo_marker'")
table_exists = cur.fetchone() is not None
count = 0
if table_exists:
    cur.execute("SELECT COUNT(*) FROM rollback_demo_marker")
    count = cur.fetchone()[0]
conn.close()
if table_exists and count > 0:
    raise SystemExit('ROLLBACK_FAIL marker table still has data')
print('ROLLBACK_OK marker reverted')
PY

echo "DEMO_OK rollback verified"
