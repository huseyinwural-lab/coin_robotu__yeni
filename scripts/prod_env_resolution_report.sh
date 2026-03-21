#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="${ROOT_DIR}/artifacts"
REPORT_JSON="${ARTIFACT_DIR}/prod_env_resolution_report.json"

mkdir -p "${ARTIFACT_DIR}"

python - <<'PY'
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

root = Path('/app')
backend_env_path = root / 'backend' / '.env'
frontend_env_path = root / 'frontend' / '.env'
report_path = root / 'artifacts' / 'prod_env_resolution_report.json'


def parse_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in stripped:
            continue
        key, raw = stripped.split('=', 1)
        values[key] = raw.strip().strip('"').strip("'")
    return values


def resolve_value(key: str, env: dict[str, str], fallback: dict[str, str]) -> str:
    value = env.get(key)
    if value:
        return value
    return fallback.get(key, '')


backend_env = parse_env(backend_env_path)
frontend_env = parse_env(frontend_env_path)
proc_env = dict(os.environ)

database_url = resolve_value('DATABASE_URL', proc_env, backend_env)
redis_url = resolve_value('REDIS_URL', proc_env, backend_env)
react_backend_url = resolve_value('REACT_APP_BACKEND_URL', proc_env, frontend_env)

targets = {
    'DATABASE_URL': database_url,
    'REDIS_URL': redis_url,
    'REACT_APP_BACKEND_URL': react_backend_url,
}

localhost_pattern = re.compile(r"(localhost|127\.0\.0\.1|0\.0\.0\.0)", re.IGNORECASE)
container_local_pattern = re.compile(r"(postgres(:\d+)?$|redis(:\d+)?$|db(:\d+)?$)", re.IGNORECASE)

checks = []
for key, value in targets.items():
    is_set = bool(value)
    has_localhost = bool(localhost_pattern.search(value or ''))
    has_container_local = bool(container_local_pattern.search((value or '').split('@')[-1])) if value else False
    checks.append(
        {
            'key': key,
            'is_set': is_set,
            'contains_localhost': has_localhost,
            'contains_container_local': has_container_local,
            'resolved_source': 'process_env' if proc_env.get(key) else ('backend/.env' if key in backend_env else ('frontend/.env' if key in frontend_env else 'missing')),
            'value_preview': (value[:64] + '...') if value and len(value) > 64 else value,
            'status': 'PASS' if is_set and not has_localhost and not has_container_local else 'FAIL',
        }
    )

status = 'PASS' if all(item['status'] == 'PASS' for item in checks) else 'FAIL'

report = {
    'phase': 'FAZ_D0_TASK_1',
    'status': status,
    'generated_at': datetime.now(timezone.utc).isoformat(),
    'checks': checks,
    'notes': [
        'Production runtime değerlerinde localhost/container-local host kalmamalı.',
        'Bu rapor sadece çözümlenen env değerlerine göre deterministik kontrol üretir.',
    ],
}

report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'status': status, 'artifact': str(report_path)}, ensure_ascii=False))
PY
