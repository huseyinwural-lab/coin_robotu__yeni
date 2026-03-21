#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="${ROOT_DIR}/artifacts"
REPORT_JSON="${ARTIFACT_DIR}/final_release_gate_report.json"

mkdir -p "${ARTIFACT_DIR}"

python - <<'PY'
import json
from datetime import datetime, timezone
from pathlib import Path

root = Path('/app')
artifacts = root / 'artifacts'
report_path = artifacts / 'final_release_gate_report.json'

required_artifacts = {
    'prod_env_preflight': artifacts / 'prod_preflight_check.json',
    'secret_readiness': artifacts / 'prod_secret_readiness_report.json',
    'prod_like_smoke': artifacts / 'prod_like_smoke_summary.json',
    'kill_switch_dry_run': artifacts / 'prod_kill_switch_dry_run.json',
    'rollback_drill': artifacts / 'prod_rollback_drill.json',
    'migration_integrity': artifacts / 'final_migration_integrity_report.json',
}

results = {}
blocking_items = []

for name, path in required_artifacts.items():
    entry = {
        'path': str(path),
        'exists': path.exists(),
        'status': 'MISSING',
        'raw_status': None,
    }
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
            raw_status = str(payload.get('status') or 'UNKNOWN').upper()
            entry['raw_status'] = raw_status
            entry['status'] = 'PASS' if raw_status == 'PASS' else 'FAIL'
            if raw_status != 'PASS':
                blocking_items.append({'artifact': name, 'reason': f'status={raw_status}'})
        except Exception as exc:
            entry['status'] = 'FAIL'
            entry['raw_status'] = f'PARSE_ERROR:{exc}'
            blocking_items.append({'artifact': name, 'reason': 'parse_error'})
    else:
        blocking_items.append({'artifact': name, 'reason': 'missing_artifact'})
    results[name] = entry

final_decision = 'GO' if not blocking_items else 'NO_GO'

report = {
    'phase': 'FAZ_D0_TASK_10',
    'generated_at': datetime.now(timezone.utc).isoformat(),
    'final_decision': final_decision,
    'artifact_status': results,
    'blocking_items': blocking_items,
}

report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'final_decision': final_decision, 'blocking_count': len(blocking_items)}, ensure_ascii=False))
raise SystemExit(0 if final_decision == 'GO' else 1)
PY
