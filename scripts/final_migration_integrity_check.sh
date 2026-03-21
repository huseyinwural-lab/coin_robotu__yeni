#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="${ROOT_DIR}/artifacts"
REPORT_JSON="${ARTIFACT_DIR}/final_migration_integrity_report.json"

mkdir -p "${ARTIFACT_DIR}"

CURRENT_OUT="$(cd "${ROOT_DIR}/backend" && alembic current 2>&1 || true)"
HEADS_OUT="$(cd "${ROOT_DIR}/backend" && alembic heads 2>&1 || true)"

python - <<PY
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, inspect

root = Path('/app')
report_path = root / 'artifacts' / 'final_migration_integrity_report.json'

current_out = '''${CURRENT_OUT}'''
heads_out = '''${HEADS_OUT}'''

def parse_env(path: Path) -> dict[str, str]:
    values = {}
    if not path.exists():
      return values
    for line in path.read_text(encoding='utf-8').splitlines():
      s = line.strip()
      if not s or s.startswith('#') or '=' not in s:
        continue
      k, v = s.split('=', 1)
      values[k] = v.strip().strip('"').strip("'")
    return values


backend_env = parse_env(root / 'backend' / '.env')
database_url = os.environ.get('DATABASE_URL') or backend_env.get('DATABASE_URL', '')

current_rev_match = re.search(r'([0-9a-f_]+)\s*\(head\)', current_out)
heads_rev_match = re.search(r'([0-9a-f_]+)\s*\(head\)', heads_out)
current_rev = current_rev_match.group(1) if current_rev_match else None
head_rev = heads_rev_match.group(1) if heads_rev_match else None

table_names = []
critical_tables = [
  'users',
  'audit_logs',
  'execution_intents',
  'risk_policies',
  'user_scanner_results',
  'user_scanner_automation_profiles',
  'user_scanner_symbol_selections',
  'live_activation_config',
]
missing_tables = []
table_check_error = None

if database_url:
  try:
    engine = create_engine(database_url)
    inspector = inspect(engine)
    table_names = sorted(inspector.get_table_names())
    missing_tables = [name for name in critical_tables if name not in table_names]
  except Exception as exc:
    table_check_error = str(exc)
else:
  table_check_error = 'DATABASE_URL missing'

status = 'PASS'
if current_rev is None or head_rev is None or current_rev != head_rev:
  status = 'FAIL'
if table_check_error is not None:
  status = 'FAIL'
if missing_tables:
  status = 'FAIL'

report = {
  'phase': 'FAZ_D0_TASK_9',
  'status': status,
  'generated_at': datetime.now(timezone.utc).isoformat(),
  'alembic': {
    'current_output': current_out,
    'heads_output': heads_out,
    'current_revision': current_rev,
    'head_revision': head_rev,
    'current_equals_head': current_rev is not None and head_rev is not None and current_rev == head_rev,
  },
  'critical_table_check': {
    'required_tables': critical_tables,
    'existing_table_count': len(table_names),
    'missing_tables': missing_tables,
    'error': table_check_error,
  },
}

report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'status': status, 'missing_tables': missing_tables}, ensure_ascii=False))
raise SystemExit(0 if status == 'PASS' else 1)
PY
