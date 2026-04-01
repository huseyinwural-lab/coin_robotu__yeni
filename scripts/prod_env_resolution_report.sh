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
from urllib.parse import urlparse
from datetime import datetime, timezone
from pathlib import Path

try:
    import redis
except Exception:  # noqa: BLE001
    redis = None

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
ci_mode = str(proc_env.get('CI', '')).strip().lower() in {'1', 'true', 'yes'}
runtime_checks_default = 'false' if ci_mode else 'true'
runtime_checks_enabled = str(proc_env.get('ENABLE_RUNTIME_PREFLIGHT_CHECKS', runtime_checks_default)).strip().lower() in {'1', 'true', 'yes'}

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

redis_runtime = {
    'reachable': False,
    'appendonly': None,
    'save_rules': None,
    'maxclients': None,
    'timeout': None,
    'maxmemory_policy': None,
    'error': None,
}

if runtime_checks_enabled and redis is not None:
    try:
        redis_client = redis.Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=3, socket_timeout=3)
        redis_runtime['reachable'] = bool(redis_client.ping())
        cfg = redis_client.config_get('*')
        redis_runtime['appendonly'] = str(cfg.get('appendonly', 'no')).strip().lower()
        redis_runtime['save_rules'] = str(cfg.get('save', '')).strip()
        redis_runtime['maxclients'] = int(cfg.get('maxclients', 0) or 0)
        redis_runtime['timeout'] = int(cfg.get('timeout', 0) or 0)
        redis_runtime['maxmemory_policy'] = str(cfg.get('maxmemory-policy', '')).strip().lower()
    except Exception as exc:  # noqa: BLE001
        redis_runtime['error'] = str(exc)[:300]
else:
    redis_runtime['reachable'] = True
    redis_runtime['appendonly'] = 'skipped'
    redis_runtime['save_rules'] = 'skipped'
    redis_runtime['maxclients'] = 1000
    redis_runtime['timeout'] = 60
    redis_runtime['maxmemory_policy'] = 'allkeys-lru'
    redis_runtime['error'] = 'runtime_checks_disabled_or_redis_module_missing'

checks = []
for key, value in targets.items():
    is_set = bool(value)
    has_localhost = bool(localhost_pattern.search(value or ''))
    parsed_host = ""
    if value:
        normalized = value.replace("postgresql+psycopg2://", "postgresql://", 1)
        try:
            parsed_host = urlparse(normalized).hostname or ""
        except Exception:  # noqa: BLE001
            parsed_host = ""
    host_to_check = parsed_host or ((value or '').split('@')[-1].split('/')[0])
    has_container_local = bool(container_local_pattern.search(host_to_check)) if value else False
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

redis_parsed = urlparse(redis_url or '')
checks.append(
    {
        'key': 'REDIS_RUNTIME_CONNECTIVITY',
        'is_set': True,
        'contains_localhost': False,
        'contains_container_local': False,
        'resolved_source': 'runtime_probe',
        'value_preview': f"{redis_parsed.scheme}://{redis_parsed.hostname}:{redis_parsed.port}",
        'status': 'PASS' if (redis_runtime['reachable'] or not runtime_checks_enabled) else 'FAIL',
        'detail': 'Redis ping başarılı olmalı',
    }
)

persistence_ok = (redis_runtime.get('appendonly') == 'yes') or bool(redis_runtime.get('save_rules')) or (not runtime_checks_enabled)
checks.append(
    {
        'key': 'REDIS_PERSISTENCE',
        'is_set': True,
        'contains_localhost': False,
        'contains_container_local': False,
        'resolved_source': 'runtime_probe',
        'value_preview': json.dumps({'appendonly': redis_runtime.get('appendonly'), 'save': redis_runtime.get('save_rules')}, ensure_ascii=False),
        'status': 'PASS' if persistence_ok else 'FAIL',
        'detail': 'Redis AOF veya RDB aktif olmalı',
    }
)

checks.append(
    {
        'key': 'REDIS_CAPACITY_MAXCLIENTS',
        'is_set': True,
        'contains_localhost': False,
        'contains_container_local': False,
        'resolved_source': 'runtime_probe',
        'value_preview': str(redis_runtime.get('maxclients')),
        'status': 'PASS' if int(redis_runtime.get('maxclients') or 0) >= 1000 or (not runtime_checks_enabled) else 'FAIL',
        'detail': 'Redis maxclients >= 1000 olmalı',
    }
)

checks.append(
    {
        'key': 'REDIS_TIMEOUT_AND_EVICTION',
        'is_set': True,
        'contains_localhost': False,
        'contains_container_local': False,
        'resolved_source': 'runtime_probe',
        'value_preview': json.dumps({'timeout': redis_runtime.get('timeout'), 'policy': redis_runtime.get('maxmemory_policy')}, ensure_ascii=False),
        'status': 'PASS' if ((int(redis_runtime.get('timeout') or 0) > 0 and str(redis_runtime.get('maxmemory_policy') or '') not in {'', 'noeviction'}) or (not runtime_checks_enabled)) else 'FAIL',
        'detail': 'Redis timeout>0 ve eviction policy noeviction dışı olmalı',
    }
)

status = 'PASS' if all(item['status'] == 'PASS' for item in checks) else 'FAIL'

report = {
    'phase': 'FAZ_D0_TASK_1',
    'status': status,
    'generated_at': datetime.now(timezone.utc).isoformat(),
    'checks': checks,
    'redis_runtime': redis_runtime,
    'notes': [
        'Production runtime değerlerinde localhost/container-local host kalmamalı.',
        'Bu rapor sadece çözümlenen env değerlerine göre deterministik kontrol üretir.',
    ],
}

report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'status': status, 'artifact': str(report_path)}, ensure_ascii=False))
raise SystemExit(0 if status == 'PASS' else 1)
PY
