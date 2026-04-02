#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="${ROOT_DIR}/artifacts"
REPORT_JSON="${ARTIFACT_DIR}/final_release_gate_report.json"

mkdir -p "${ARTIFACT_DIR}"

python - <<'PY'
import json
import os
import hashlib
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

root = Path('/app')
artifacts = root / 'artifacts'
report_path = artifacts / 'final_release_gate_report.json'
run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

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
warnings = []


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data: dict[str, str] = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        raw = line.strip()
        if not raw or raw.startswith('#') or '=' not in raw:
            continue
        key, value = raw.split('=', 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def resolve_runtime_value(key: str, fallback: dict[str, str], default: str = '') -> str:
    value = os.environ.get(key)
    if value is not None and str(value).strip() != '':
        return str(value).strip()
    from_file = fallback.get(key)
    if from_file is not None and str(from_file).strip() != '':
        return str(from_file).strip()
    return default


backend_env = parse_env_file(root / 'backend' / '.env')
frontend_env = parse_env_file(root / 'frontend' / '.env')


def fetch_live_production_gate_snapshot() -> dict | None:
    try:
        import requests  # type: ignore
    except Exception:  # noqa: BLE001
        requests = None

    base_candidates = [
        resolve_runtime_value('REACT_APP_BACKEND_URL', frontend_env).rstrip('/'),
        resolve_runtime_value('BACKEND_BASE_URL', backend_env).rstrip('/'),
        'http://127.0.0.1:8001',
    ]
    base_urls = [item for item in base_candidates if item]
    if len(base_urls) == 0:
        return None

    admin_email = resolve_runtime_value('PHASE4_ADMIN_EMAIL', backend_env) or resolve_runtime_value('ADMIN_BOOTSTRAP_EMAIL', backend_env) or 'canary.admin@platform.local'
    admin_password = resolve_runtime_value('PHASE4_ADMIN_PASSWORD', backend_env) or resolve_runtime_value('ADMIN_BOOTSTRAP_PASSWORD', backend_env) or 'CanaryAdmin123!'

    if requests is not None:
        last_error = None
        for base_url in base_urls:
            try:
                session = requests.Session()
                login_resp = session.post(
                    f'{base_url}/api/auth/login/admin',
                    json={'email': admin_email, 'password': admin_password},
                    timeout=20,
                )
                if login_resp.status_code != 200:
                    last_error = f'login_failed_http_{login_resp.status_code}@{base_url}'
                    continue

                login_body = login_resp.json()
                token = str(login_body.get('access_token') or login_body.get('token') or '').strip()
                if not token:
                    last_error = f'login_token_missing@{base_url}'
                    continue

                gate_resp = session.get(
                    f'{base_url}/api/phase4/admin/production-gate?refresh_checks=false',
                    headers={'Authorization': f'Bearer {token}'},
                    timeout=60,
                )
                if gate_resp.status_code != 200:
                    last_error = f'gate_fetch_failed_http_{gate_resp.status_code}@{base_url}'
                    continue
                return gate_resp.json()
            except Exception as exc:  # noqa: BLE001
                last_error = f'{exc}@{base_url}'
        if last_error:
            raise RuntimeError(last_error)

    last_error = None
    for base_url in base_urls:
        try:
            login_payload = json.dumps({'email': admin_email, 'password': admin_password}).encode('utf-8')
            login_req = urllib.request.Request(
                f'{base_url}/api/auth/login/admin',
                data=login_payload,
                headers={'Content-Type': 'application/json'},
                method='POST',
            )

            with urllib.request.urlopen(login_req, timeout=20) as resp:  # noqa: S310
                login_body = json.loads(resp.read().decode('utf-8'))
                token = str(login_body.get('access_token') or login_body.get('token') or '').strip()
                if not token:
                    last_error = f'login_token_missing@{base_url}'
                    continue
                set_cookie = str(resp.headers.get('Set-Cookie') or '')
                device_cookie = ''
                if 'device_id=' in set_cookie:
                    device_cookie = set_cookie.split(';', 1)[0]

            gate_req = urllib.request.Request(
                f'{base_url}/api/phase4/admin/production-gate?refresh_checks=false',
                headers={
                    'Authorization': f'Bearer {token}',
                    'Cookie': device_cookie,
                },
                method='GET',
            )
            with urllib.request.urlopen(gate_req, timeout=60) as gate_resp:  # noqa: S310
                gate_payload = json.loads(gate_resp.read().decode('utf-8'))
                return gate_payload
        except Exception as exc:  # noqa: BLE001
            last_error = f'{exc}@{base_url}'

    if last_error:
        raise RuntimeError(last_error)
    return None


live_snapshot_payload = None
live_snapshot_error = None
try:
    live_snapshot_payload = fetch_live_production_gate_snapshot()
except Exception as exc:  # noqa: BLE001
    live_snapshot_error = str(exc)

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

production_gate_snapshot_dir = artifacts / 'final'
production_gate_snapshot_path = production_gate_snapshot_dir / 'production_gate_snapshot.json'
run_snapshot_path = production_gate_snapshot_dir / f'production_gate_snapshot_{run_id}.json'
pg_entry = {
    'path': str(run_snapshot_path),
    'exists': production_gate_snapshot_path.exists() or bool(live_snapshot_payload),
    'status': 'SKIPPED',
    'raw_status': None,
}

if live_snapshot_payload is not None:
    payload = dict(live_snapshot_payload)
    snapshot_write_ok = True
    snapshot_write_error = None
    snapshot_serialized = json.dumps(payload, ensure_ascii=False, indent=2) + '\n'
    try:
        production_gate_snapshot_dir.mkdir(parents=True, exist_ok=True)
        run_snapshot_path.write_text(snapshot_serialized, encoding='utf-8')
        production_gate_snapshot_path.write_text(snapshot_serialized, encoding='utf-8')
    except Exception as exc:  # noqa: BLE001
        snapshot_write_ok = False
        snapshot_write_error = str(exc)

    deploy_allowed = bool(payload.get('deploy_allowed'))
    configured_state = str(payload.get('configured_state') or '').upper()
    effective_state = str(payload.get('effective_state') or '').upper()
    release_gate_contract = str(payload.get('release_gate_contract') or '').upper()
    has_stale_or_running = bool(payload.get('has_stale_or_running'))
    updated_at_raw = str(payload.get('updated_at') or '').strip()
    is_fresh = True
    pass_state = (
        configured_state == 'GO'
        and effective_state == 'GO'
        and deploy_allowed
        and snapshot_write_ok
    )
    pg_entry['raw_status'] = {
        'configured_state': configured_state,
        'deploy_allowed': deploy_allowed,
        'effective_state': effective_state,
        'release_gate_contract': release_gate_contract,
        'has_stale_or_running': has_stale_or_running,
        'updated_at': updated_at_raw,
        'fresh': is_fresh,
        'source': 'live_api',
        'run_snapshot_path': str(run_snapshot_path),
        'snapshot_write_ok': snapshot_write_ok,
        'snapshot_write_error': snapshot_write_error,
    }
    pg_entry['status'] = 'PASS' if pass_state else 'FAIL'
    if not pass_state:
        blocking_items.append({'artifact': 'production_gate_snapshot', 'reason': f'configured_state={configured_state},effective_state={effective_state},deploy_allowed={deploy_allowed},source=live_api,snapshot_write_ok={snapshot_write_ok}'})
elif production_gate_snapshot_path.exists():
    try:
        payload_raw = production_gate_snapshot_path.read_text(encoding='utf-8')
        payload = json.loads(payload_raw)
        try:
            production_gate_snapshot_dir.mkdir(parents=True, exist_ok=True)
            run_snapshot_path.write_text(payload_raw if payload_raw.endswith('\n') else payload_raw + '\n', encoding='utf-8')
        except Exception:
            pass
        deploy_allowed = bool(payload.get('deploy_allowed'))
        configured_state = str(payload.get('configured_state') or '').upper()
        effective_state = str(payload.get('effective_state') or '').upper()
        release_gate_contract = str(payload.get('release_gate_contract') or '').upper()
        has_stale_or_running = bool(payload.get('has_stale_or_running'))
        updated_at_raw = str(payload.get('updated_at') or '').strip()

        is_fresh = False
        if updated_at_raw:
            try:
                updated_at = datetime.fromisoformat(updated_at_raw.replace('Z', '+00:00'))
                age_seconds = max(0.0, (datetime.now(timezone.utc) - updated_at).total_seconds())
                is_fresh = age_seconds <= 1200
            except Exception:
                is_fresh = False

        pass_state = (
            configured_state == 'GO'
            and effective_state == 'GO'
            and deploy_allowed
            and is_fresh
        )
        pg_entry['raw_status'] = {
            'configured_state': configured_state,
            'deploy_allowed': deploy_allowed,
            'effective_state': effective_state,
            'release_gate_contract': release_gate_contract,
            'has_stale_or_running': has_stale_or_running,
            'updated_at': updated_at_raw,
            'fresh': is_fresh,
            'source': 'snapshot_file',
            'run_snapshot_path': str(run_snapshot_path),
        }
        pg_entry['status'] = 'PASS' if pass_state else 'FAIL'
        if not pass_state:
            blocking_items.append({'artifact': 'production_gate_snapshot', 'reason': f'configured_state={configured_state},effective_state={effective_state},deploy_allowed={deploy_allowed},fresh={is_fresh}'})
    except Exception as exc:
        pg_entry['status'] = 'FAIL'
        pg_entry['raw_status'] = f'PARSE_ERROR:{exc}'
        blocking_items.append({'artifact': 'production_gate_snapshot', 'reason': 'parse_error'})
else:
    warnings.append({'artifact': 'production_gate_snapshot', 'reason': 'missing_optional_snapshot'})

if live_snapshot_error:
    warnings.append({'artifact': 'production_gate_snapshot_live_fetch', 'reason': live_snapshot_error[:200]})

results['production_gate_snapshot'] = pg_entry

# Hard consistency lock:
# final_decision GO üretilecekse snapshot dosyası ile aynı gate durumunu taşımalı.
consistency_entry = {
    'path': str(run_snapshot_path),
    'exists': run_snapshot_path.exists(),
    'status': 'SKIPPED',
    'raw_status': None,
}
try:
    if run_snapshot_path.exists() and isinstance((results.get('production_gate_snapshot') or {}).get('raw_status'), dict):
        disk_raw = run_snapshot_path.read_text(encoding='utf-8')
        disk_payload = json.loads(disk_raw)
        memory_payload = (results.get('production_gate_snapshot') or {}).get('raw_status') or {}
        disk_effective_state = str(disk_payload.get('effective_state') or '').upper()
        disk_deploy_allowed = bool(disk_payload.get('deploy_allowed'))
        mem_effective_state = str(memory_payload.get('effective_state') or '').upper()
        mem_deploy_allowed = bool(memory_payload.get('deploy_allowed'))
        snapshot_sha256 = hashlib.sha256(disk_raw.encode('utf-8')).hexdigest()
        matched = (disk_effective_state == mem_effective_state) and (disk_deploy_allowed == mem_deploy_allowed)
        consistency_entry['status'] = 'PASS' if matched else 'FAIL'
        consistency_entry['raw_status'] = {
            'matched': matched,
            'snapshot_sha256': snapshot_sha256,
            'disk_effective_state': disk_effective_state,
            'disk_deploy_allowed': disk_deploy_allowed,
            'memory_effective_state': mem_effective_state,
            'memory_deploy_allowed': mem_deploy_allowed,
        }
        if not matched:
            blocking_items.append({'artifact': 'production_gate_snapshot_consistency', 'reason': 'disk_vs_report_payload_mismatch'})
    else:
        consistency_entry['status'] = 'FAIL'
        consistency_entry['raw_status'] = {'reason': 'snapshot_missing_or_invalid'}
        blocking_items.append({'artifact': 'production_gate_snapshot_consistency', 'reason': 'snapshot_missing_or_invalid'})
except Exception as exc:
    consistency_entry['status'] = 'FAIL'
    consistency_entry['raw_status'] = {'reason': f'consistency_check_error:{exc}'}
    blocking_items.append({'artifact': 'production_gate_snapshot_consistency', 'reason': 'consistency_check_error'})

results['production_gate_snapshot_consistency'] = consistency_entry

final_decision = 'GO' if not blocking_items else 'NO_GO'

report = {
    'phase': 'FAZ_D0_TASK_10',
    'generated_at': datetime.now(timezone.utc).isoformat(),
    'run_id': run_id,
    'final_decision': final_decision,
    'artifact_status': results,
    'blocking_items': blocking_items,
    'warnings': warnings,
}

report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
run_report_path = artifacts / f'final_release_gate_report_{run_id}.json'
run_report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'final_decision': final_decision, 'blocking_count': len(blocking_items)}, ensure_ascii=False))
raise SystemExit(0 if final_decision == 'GO' else 1)
PY
