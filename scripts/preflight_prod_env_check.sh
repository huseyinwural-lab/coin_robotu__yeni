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
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import redis

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
redis_runtime = {}
health_probe = {}


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
add_check('pg_dump available', shutil.which('pg_dump') is not None, 'pg_dump kurulu olmalı')
add_check('psql available', shutil.which('psql') is not None, 'psql kurulu olmalı')

alert_from = get_value('ALERT_FROM', backend_env)
alert_to = get_value('ALERT_TO', backend_env)
resend_api_key = get_value('RESEND_API_KEY', backend_env)
if alert_from or alert_to:
    add_check('RESEND_API_KEY exists when alert emails configured', bool(resend_api_key), 'ALERT_FROM/ALERT_TO set ise RESEND_API_KEY zorunlu')

try:
    redis_client = redis.Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=3, socket_timeout=3)
    ping_ok = bool(redis_client.ping())
    cfg = redis_client.config_get('*')
    appendonly = str(cfg.get('appendonly', 'no')).strip().lower()
    save_rules = str(cfg.get('save', '')).strip()
    maxclients = int(cfg.get('maxclients', 0) or 0)
    timeout = int(cfg.get('timeout', 0) or 0)
    eviction_policy = str(cfg.get('maxmemory-policy', '')).strip().lower()

    redis_runtime = {
        'ping_ok': ping_ok,
        'appendonly': appendonly,
        'save_rules': save_rules,
        'maxclients': maxclients,
        'timeout': timeout,
        'maxmemory_policy': eviction_policy,
    }

    add_check('Redis ping', ping_ok, 'Redis bağlantısı başarılı olmalı')
    add_check('Redis persistence enabled', appendonly == 'yes' or bool(save_rules), 'Redis AOF veya RDB aktif olmalı')
    add_check('Redis maxclients sufficient', maxclients >= 1000, 'Redis maxclients >= 1000 olmalı')
    add_check('Redis timeout configured', timeout > 0, 'Redis timeout 0 olmamalı')
    add_check('Redis eviction policy configured', eviction_policy not in {'', 'noeviction'}, 'Redis maxmemory-policy noeviction olmamalı')
except Exception as exc:  # noqa: BLE001
    redis_runtime = {'error': str(exc)[:300]}
    add_check('Redis ping', False, f'Redis bağlantı hatası: {str(exc)[:200]}')
    add_check('Redis persistence enabled', False, 'Redis config okunamadı')
    add_check('Redis maxclients sufficient', False, 'Redis config okunamadı')
    add_check('Redis timeout configured', False, 'Redis config okunamadı')
    add_check('Redis eviction policy configured', False, 'Redis config okunamadı')

backend_logs = [
    Path('/var/log/supervisor/backend.out.log'),
    Path('/var/log/supervisor/backend.err.log'),
]
boot_log_ok = False
for path in backend_logs:
    if not path.exists():
        continue
    text = path.read_text(encoding='utf-8', errors='ignore')
    if 'REDIS_CONNECT_OK' in text:
        boot_log_ok = True
        break
add_check('App boot Redis connect success log', boot_log_ok, 'Backend log içinde REDIS_CONNECT_OK bulunmalı')

health_probe = {}
health_url = (frontend_backend_url.rstrip('/') + '/api/health') if frontend_backend_url else ''
if health_url:
    try:
        with urllib.request.urlopen(health_url, timeout=12) as resp:  # noqa: S310
            body = json.loads(resp.read().decode('utf-8'))
            health_probe = {
                'source': 'http_probe',
                'status_code': int(resp.status),
                'redis': body.get('checks', {}).get('redis', {}),
                'status': body.get('status'),
            }
    except Exception as exc:  # noqa: BLE001
        health_probe = {'source': 'http_probe', 'error': str(exc)[:300]}

if not health_probe.get('redis'):
    health_script = (
        "import json; from server import health_check; "
        "resp = health_check(); "
        "body = json.loads(resp.body.decode('utf-8')); "
        "print(json.dumps({'source': 'inprocess_probe', 'status_code': resp.status_code, 'redis': body.get('checks', {}).get('redis', {}), 'status': body.get('status')}))"
    )
    health_proc = subprocess.run(
        [sys.executable, '-c', health_script],
        cwd='/app/backend',
        capture_output=True,
        text=True,
        timeout=25,
    )
    if health_proc.returncode == 0:
        try:
            health_probe = json.loads((health_proc.stdout or '').strip().splitlines()[-1])
        except Exception:  # noqa: BLE001
            health_probe = {'source': 'inprocess_probe', 'parse_error': (health_proc.stdout or '')[-500:]}
    else:
        health_probe = {'source': 'inprocess_probe', 'error': (health_proc.stderr or health_proc.stdout or '')[-500:]}

health_redis_ok = health_probe.get('redis', {}).get('status') == 'ready'
add_check('Healthcheck endpoint Redis OK', health_redis_ok, 'health endpoint redis.status=ready dönmeli')

failfast_env = dict(os.environ)
failfast_env.update(backend_env)
failfast_env['REDIS_URL'] = 'redis://203.0.113.77:6399/0'
failfast_proc = subprocess.run(
    [sys.executable, '-c', 'import db'],
    cwd='/app/backend',
    capture_output=True,
    text=True,
    env=failfast_env,
    timeout=20,
)
failfast_payload = (failfast_proc.stdout or '') + '\n' + (failfast_proc.stderr or '')
failfast_ok = failfast_proc.returncode != 0 and 'redis_init_failed_fail_fast' in failfast_payload
add_check('Redis fail-fast behavior', failfast_ok, 'Redis erişilemezse app boot fail fast yapmalı')

status = 'PASS' if all(check['status'] == 'PASS' for check in checks) else 'FAIL'

report = {
    'phase': 'FAZ_0_FINAL_BLOCKER_CLEANUP',
    'status': status,
    'generated_at': datetime.now(timezone.utc).isoformat(),
    'checks': checks,
    'resolved_values_preview': {
        'DATABASE_URL': (database_url[:80] + '...') if len(database_url) > 80 else database_url,
        'REDIS_URL': (redis_url[:80] + '...') if len(redis_url) > 80 else redis_url,
        'REACT_APP_BACKEND_URL': frontend_backend_url,
        'JWT_SECRET_length': len(jwt_secret or ''),
    },
    'redis_runtime': redis_runtime,
    'health_probe': health_probe,
    'failfast_probe': {
        'return_code': failfast_proc.returncode,
        'matched': failfast_ok,
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
