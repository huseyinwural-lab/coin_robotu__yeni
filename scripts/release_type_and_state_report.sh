#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${ROOT_DIR}/artifacts/release_state"
CURRENT_FILE="${STATE_DIR}/current_release.env"
HISTORY_FILE="${STATE_DIR}/deploy_history.jsonl"
REPORT_JSON="${ROOT_DIR}/artifacts/release_type_and_state_report.json"

mkdir -p "${STATE_DIR}" "${ROOT_DIR}/artifacts"

python - <<'PY'
import json
from datetime import datetime, timezone
from pathlib import Path

root = Path('/app')
state_dir = root / 'artifacts' / 'release_state'
current_file = state_dir / 'current_release.env'
history_file = state_dir / 'deploy_history.jsonl'
report_file = root / 'artifacts' / 'release_type_and_state_report.json'


def parse_env_file(path: Path) -> dict[str, str]:
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding='utf-8').splitlines():
        s = line.strip()
        if not s or s.startswith('#') or '=' not in s:
            continue
        key, value = s.split('=', 1)
        values[key] = value.strip()
    return values


def load_history(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    for raw in path.read_text(encoding='utf-8').splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            rows.append(json.loads(raw))
        except Exception:
            continue
    return rows


before_state = parse_env_file(current_file)
history_rows = load_history(history_file)

release_type = 'first_deploy' if len(history_rows) == 0 else 'redeploy'
if len(history_rows) >= 2:
    last = history_rows[-1]
    prev = history_rows[-2]
    if str(last.get('source')) == 'deploy' and str(prev.get('source')) == 'deploy' and str(last.get('version')) != str(prev.get('version')):
        release_type = 'replace'

latest_success_like = None
for row in reversed(history_rows):
    if str(row.get('status')) in {'success', 'rolled_back'}:
        latest_success_like = row
        break

state_cleaned = False
after_state = dict(before_state)
if before_state.get('CURRENT_STATUS') == 'deploying' and latest_success_like:
    version = str(latest_success_like.get('version') or before_state.get('CURRENT_VERSION') or '')
    image_tag = str(latest_success_like.get('image_tag') or before_state.get('CURRENT_IMAGE_TAG') or '')
    sha = version.replace('release-', '') if version.startswith('release-') else before_state.get('CURRENT_VERSION_SHA', '')
    updated_at = datetime.now(timezone.utc).isoformat()
    after_state = {
        'CURRENT_VERSION': version,
        'CURRENT_VERSION_SHA': sha,
        'CURRENT_IMAGE_TAG': image_tag,
        'CURRENT_STATUS': 'deployed',
        'UPDATED_AT': updated_at,
    }
    current_file.write_text('\n'.join(f"{k}={v}" for k, v in after_state.items()) + '\n', encoding='utf-8')
    state_cleaned = True

report = {
    'phase': 'FAZ_D0_TASK_8',
    'status': 'PASS',
    'generated_at': datetime.now(timezone.utc).isoformat(),
    'release_type': release_type,
    'history_count': len(history_rows),
    'state_cleaned': state_cleaned,
    'before_state': before_state,
    'after_state': after_state,
    'latest_history_entry': history_rows[-1] if history_rows else None,
}

report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'release_type': release_type, 'state_cleaned': state_cleaned}, ensure_ascii=False))
PY
