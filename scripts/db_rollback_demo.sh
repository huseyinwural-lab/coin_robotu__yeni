#!/usr/bin/env bash
set -euo pipefail

DB_URL="${DATABASE_URL:-}"
TMP_BACKUP="/tmp/rollback_demo_$(date +%s).bak"

if [[ -z "$DB_URL" ]]; then
  echo "ERROR: DATABASE_URL boş olamaz"
  exit 1
fi

bash /app/scripts/db_backup.sh "$TMP_BACKUP"

python - <<'PY'
import os
from sqlalchemy import create_engine, text

db_url = os.environ["DATABASE_URL"]
engine = create_engine(db_url, pool_pre_ping=True)
with engine.begin() as conn:
    conn.execute(text("CREATE TABLE IF NOT EXISTS rollback_demo_marker (id SERIAL PRIMARY KEY, marker TEXT)"))
    conn.execute(text("INSERT INTO rollback_demo_marker(marker) VALUES (:marker)"), {"marker": "mutated_after_backup"})
    count = conn.execute(text("SELECT COUNT(*) FROM rollback_demo_marker")).scalar_one()
    print("MUTATION_COUNT", int(count))
PY

bash /app/scripts/db_restore.sh "$TMP_BACKUP"

python - <<'PY'
import os
from sqlalchemy import create_engine, text

db_url = os.environ["DATABASE_URL"]
engine = create_engine(db_url, pool_pre_ping=True)

with engine.begin() as conn:
    table_exists = conn.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'rollback_demo_marker'
            )
            """
        )
    ).scalar_one()
    marker_count = 0
    if table_exists:
        marker_count = conn.execute(text("SELECT COUNT(*) FROM rollback_demo_marker")).scalar_one()

if table_exists and marker_count > 0:
    raise SystemExit("ROLLBACK_FAIL marker table still has data")

print("ROLLBACK_OK marker reverted")
PY

echo "DEMO_OK rollback verified"
