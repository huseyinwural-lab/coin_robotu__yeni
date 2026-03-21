#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="${ROOT_DIR}/artifacts"
LOG_FILE="${ARTIFACT_DIR}/prod_preflight_check.log"
JSON_FILE="${ARTIFACT_DIR}/prod_preflight_check.json"

mkdir -p "${ARTIFACT_DIR}"
: > "${LOG_FILE}"

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" | tee -a "${LOG_FILE}"
}

python - <<'PY'
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

root = Path('/app')
json_file = root / 'artifacts' / 'prod_preflight_check.json'
log_file = root / 'artifacts' / 'prod_preflight_check.log'


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in stripped:
            continue
        key, value = stripped.split('=', 1)
        data[key] = value.strip().strip('"').strip("'")
    return data


backend_env = parse_env_file(root / 'backend' / '.env')
frontend_env = parse_env_file(root / 'frontend' / '.env')
proc_env = dict(os.environ)


def get_value(key: str, fallback: dict[str, str]) -> str:
    value = proc_env.get(key)
    if value is not None and str(value).strip() != '':
        return str(value).strip()
    return fallback.get(key, '')


database_url = get_value('DATABASE_URL', backend_env)
redis_url = get_value('REDIS_URL', backend_env)
jwt_secret = get_value('JWT_SECRET', backend_env)
frontend_backend_url = get_value('REACT_APP_BACKEND_URL', frontend_env)

localhost_pattern = re.compile(r"(localhost|127\.0\.0\.1|0\.0\.0\.0)", re.IGNORECASE)
development_secret_pattern = re.compile(r"(dev|test|changeme|default|phase8-ci-jwt-secret)", re.IGNORECASE)
prod_url_pattern = re.compile(r"^https://[a-zA-Z0-9.-]+(?:/.*)?$")

checks = []


def add_check(name: str, passed: bool, detail: str) -> None:
    checks.append({
        'name': name,
        'status': 'PASS' if passed else 'FAIL',
        'detail': detail,
    })


add_check('DATABASE_URL not empty', bool(database_url), 'DATABASE_URL değeri boş olamaz')
add_check('REDIS_URL not empty', bool(redis_url), 'REDIS_URL değeri boş olamaz')
add_check('DATABASE_URL non-localhost', bool(database_url) and not localhost_pattern.search(database_url), 'DATABASE_URL localhost/127.0.0.1 içermemeli')
add_check('REDIS_URL non-localhost', bool(redis_url) and not localhost_pattern.search(redis_url), 'REDIS_URL localhost/127.0.0.1 içermemeli')
add_check('JWT_SECRET strong enough', bool(jwt_secret) and len(jwt_secret) >= 32 and not development_secret_pattern.search(jwt_secret), 'JWT_SECRET min 32 karakter ve default/dev pattern içermemeli')
add_check('REACT_APP_BACKEND_URL production format', bool(frontend_backend_url) and bool(prod_url_pattern.match(frontend_backend_url)) and not localhost_pattern.search(frontend_backend_url), 'REACT_APP_BACKEND_URL https://domain formatında olmalı')

alert_from = get_value('ALERT_FROM', backend_env)
alert_to = get_value('ALERT_TO', backend_env)
resend_api_key = get_value('RESEND_API_KEY', backend_env)
if alert_from or alert_to:
    add_check('RESEND_API_KEY exists when alert emails configured', bool(resend_api_key), 'ALERT_FROM/ALERT_TO set ise RESEND_API_KEY zorunlu')

status = 'PASS' if all(check['status'] == 'PASS' for check in checks) else 'FAIL'

report = {
    'phase': 'FAZ_D0_TASK_3',
    'status': status,
    'generated_at': datetime.now(timezone.utc).isoformat(),
    'checks': checks,
    'resolved_values_preview': {
        'DATABASE_URL': (database_url[:80] + '...') if len(database_url) > 80 else database_url,
        'REDIS_URL': (redis_url[:80] + '...') if len(redis_url) > 80 else redis_url,
        'REACT_APP_BACKEND_URL': frontend_backend_url,
        'JWT_SECRET_length': len(jwt_secret or ''),
    },
}

json_file.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

with log_file.open('a', encoding='utf-8') as log:
    for check in checks:
        log.write(f"{check['status']} :: {check['name']} :: {check['detail']}\n")
    log.write(f"FINAL_STATUS={status}\n")

print(json.dumps({'status': status, 'artifact': str(json_file)}, ensure_ascii=False))
raise SystemExit(0 if status == 'PASS' else 1)
PY
