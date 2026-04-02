#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="${ROOT_DIR}/artifacts"
REPORT_JSON="${ARTIFACT_DIR}/prod_secret_readiness_report.json"

mkdir -p "${ARTIFACT_DIR}"

ROOT_DIR="${ROOT_DIR}" ARTIFACT_DIR="${ARTIFACT_DIR}" python - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

root = Path(os.environ.get('ROOT_DIR') or '/app')
artifact_dir = Path(os.environ.get('ARTIFACT_DIR') or (root / 'artifacts'))
artifact_dir.mkdir(parents=True, exist_ok=True)
report_path = artifact_dir / 'prod_secret_readiness_report.json'

required_keys = [
    'DATABASE_URL',
    'REDIS_URL',
    'JWT_SECRET',
    'EXCHANGE_CREDENTIALS_ENCRYPTION_KEY',
    'ADMIN_BOOTSTRAP_EMAIL',
    'ADMIN_BOOTSTRAP_PASSWORD',
    'REACT_APP_BACKEND_URL',
]
optional_keys = [
    'RESEND_API_KEY',
    'ALERT_FROM',
    'ALERT_TO',
    'BINANCE_TESTNET_API_KEY',
    'BINANCE_TESTNET_API_SECRET',
]


def parse_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        s = line.strip()
        if not s or s.startswith('#') or '=' not in s:
            continue
        key, raw = s.split('=', 1)
        values[key] = raw.strip().strip('"').strip("'")
    return values


backend_env = parse_env(root / 'backend' / '.env')
frontend_env = parse_env(root / 'frontend' / '.env')
process_env = dict(os.environ)
ci_mode = str(process_env.get('CI', '')).strip().lower() in {'1', 'true', 'yes'}
strict_secret_checks_default = 'false' if ci_mode else 'true'
strict_secret_checks_enabled = str(process_env.get('STRICT_SECRET_READINESS_CHECKS', strict_secret_checks_default)).strip().lower() in {'1', 'true', 'yes'}


def _runtime_env() -> str:
    return str(
        process_env.get('APP_ENV')
        or process_env.get('ENVIRONMENT')
        or process_env.get('RUNTIME_ENV')
        or ''
    ).strip().lower()


is_production_runtime = _runtime_env() in {'prod', 'production'}
strict_source_default = 'true' if is_production_runtime else 'false'
strict_source_enabled = str(process_env.get('STRICT_SECRET_SOURCE_POLICY', strict_source_default)).strip().lower() in {'1', 'true', 'yes'}


def resolve(key: str) -> tuple[str, str]:
    if key in process_env and str(process_env.get(key) or '').strip():
        return str(process_env[key]).strip(), 'process_env(platform_runtime)'
    if key in backend_env and backend_env[key]:
        return backend_env[key], 'backend/.env(repo_file)'
    if key in frontend_env and frontend_env[key]:
        return frontend_env[key], 'frontend/.env(repo_file)'
    return '', 'missing'


required_results = []
for key in required_keys:
    value, source = resolve(key)
    source_allowed = (not strict_source_enabled) or source.startswith('process_env(')
    key_present = bool(value)
    key_ok = key_present and source_allowed
    if not strict_secret_checks_enabled:
        key_ok = True
    required_results.append(
        {
            'key': key,
            'is_set': key_present,
            'source': source,
            'source_policy': 'platform_runtime_only' if strict_source_enabled else 'platform_or_repo',
            'source_policy_violation': bool(key_present and not source_allowed),
            'status': 'PASS' if key_ok else 'FAIL',
        }
    )

optional_results = []
for key in optional_keys:
    value, source = resolve(key)
    optional_results.append(
        {
            'key': key,
            'is_set': bool(value),
            'source': source,
            'status': 'PASS' if bool(value) else 'WARN',
        }
    )

repo_secret_hits = []
for key in required_keys + optional_keys:
    backend_val = backend_env.get(key, '')
    frontend_val = frontend_env.get(key, '')
    if backend_val:
        repo_secret_hits.append({'key': key, 'file': 'backend/.env'})
    if frontend_val:
        repo_secret_hits.append({'key': key, 'file': 'frontend/.env'})

status = 'PASS' if all(row['status'] == 'PASS' for row in required_results) else 'FAIL'

report = {
    'phase': 'FAZ_D0_TASK_2',
    'status': status,
    'generated_at': datetime.now(timezone.utc).isoformat(),
    'source_policy': {
        'runtime_env': _runtime_env() or 'unknown',
        'is_production_runtime': is_production_runtime,
        'strict_secret_checks_enabled': strict_secret_checks_enabled,
        'strict_source_enabled': strict_source_enabled,
        'required_source': 'process_env(platform_runtime)' if strict_source_enabled else 'process_env_or_repo',
    },
    'required_secret_checks': required_results,
    'optional_secret_checks': optional_results,
    'repo_secret_presence': repo_secret_hits,
    'notes': [
        'process_env(platform_runtime) kaynağı secret manager injection göstergesi olarak değerlendirildi.',
        'repo_file kaynağı production için risk kabul edilir; strict_source_enabled=true iken required secretlar repo dosyasından çözümlenemez.',
    ],
}

report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'status': status, 'artifact': str(report_path)}, ensure_ascii=False))
raise SystemExit(0 if status == 'PASS' else 1)
PY
