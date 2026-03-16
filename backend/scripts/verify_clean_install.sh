#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

EXPECTED_HEAD="20260316_0046"

DB_URL="${ALEMBIC_DATABASE_URL:-${DATABASE_URL:-}}"
if [[ -z "$DB_URL" ]]; then
  echo "[ERROR] Missing ALEMBIC_DATABASE_URL or DATABASE_URL"
  exit 1
fi

echo "[1/5] Running alembic upgrade head"
ALEMBIC_DATABASE_URL="$DB_URL" alembic upgrade head

echo "[2/5] Validating alembic head revision"
python - <<'PY'
import os
from sqlalchemy import create_engine, text

expected = "20260316_0046"
url = os.environ.get("ALEMBIC_DATABASE_URL") or os.environ.get("DATABASE_URL")
engine = create_engine(url)
with engine.connect() as conn:
    rev = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar_one_or_none()
if rev != expected:
    raise SystemExit(f"[ERROR] alembic_version mismatch: got={rev} expected={expected}")
print(f"[OK] alembic_version={rev}")
PY

echo "[3/5] Checking critical table presence"
python - <<'PY'
import os
from sqlalchemy import create_engine, inspect

url = os.environ.get("ALEMBIC_DATABASE_URL") or os.environ.get("DATABASE_URL")
critical = {
    "users",
    "bot_profiles",
    "risk_policies",
    "pending_signals",
    "admin_control",
    "audit_logs",
    "signal_events",
    "paper_positions",
}
engine = create_engine(url)
inspector = inspect(engine)
tables = set(inspector.get_table_names())
missing = sorted(critical - tables)
if missing:
    raise SystemExit(f"[ERROR] Missing critical tables: {missing}")
print("[OK] Critical tables present")
PY

echo "[4/5] Checking critical FK pending_signals.risk_policy_id -> risk_policies.id"
python - <<'PY'
import os
from sqlalchemy import create_engine, inspect

url = os.environ.get("ALEMBIC_DATABASE_URL") or os.environ.get("DATABASE_URL")
engine = create_engine(url)
inspector = inspect(engine)
fks = inspector.get_foreign_keys("pending_signals")
found = False
for fk in fks:
    cols = fk.get("constrained_columns") or []
    ref_table = fk.get("referred_table")
    ref_cols = fk.get("referred_columns") or []
    if cols == ["risk_policy_id"] and ref_table == "risk_policies" and ref_cols == ["id"]:
        found = True
        break
if not found:
    raise SystemExit("[ERROR] Missing FK pending_signals.risk_policy_id -> risk_policies.id")
print("[OK] Critical FK present")
PY

echo "[5/5] Clean install verification complete"
echo "[SUCCESS] Migration layer is ready for FAZ-4 clean-install proof"
