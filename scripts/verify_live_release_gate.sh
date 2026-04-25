#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/app"
BACKEND_ENV="$ROOT_DIR/backend/.env"

echo "[INFO] Live release gate verification başladı"

required_pairs=(
  "ALEMBIC_ALLOW_SQLITE_FALLBACK=0"
  "DB_ALLOW_SQLITE_FALLBACK=0"
  "REDIS_ALLOW_INMEMORY_FALLBACK=0"
  "LIVE_TRADING_BLOCKS_DISABLED=0"
  "EXECUTION_AUTO_RELEASE=0"
)

for pair in "${required_pairs[@]}"; do
  key="${pair%%=*}"
  val="${pair##*=}"
  current=$(grep -E "^${key}=" "$BACKEND_ENV" | head -n1 | sed -E 's/^[^=]+=//; s/^"//; s/"$//')
  if [[ "$current" != "$val" ]]; then
    echo "[ERROR] $key beklenen=$val mevcut=${current:-MISSING}"
    exit 1
  fi
done

python - <<'PY'
import json
import re
import subprocess
from pathlib import Path

env_text = Path('/app/frontend/.env').read_text()
base_match = re.search(r'^REACT_APP_BACKEND_URL=(.+)$', env_text, re.M)
if not base_match:
    raise SystemExit('[ERROR] REACT_APP_BACKEND_URL bulunamadı')
base = base_match.group(1).strip() + '/api'

def call(method, endpoint, token=None, payload=None):
    out = '/tmp/live_gate_resp.json'
    cmd = ['curl', '-s', '-o', out, '-w', '%{http_code}', '-X', method, f'{base}{endpoint}']
    if token:
        cmd += ['-H', f'Authorization: Bearer {token}']
    if payload is not None:
        cmd += ['-H', 'Content-Type: application/json', '-d', json.dumps(payload)]
    code = subprocess.check_output(cmd).decode().strip()
    body = Path(out).read_text(errors='ignore')
    try:
        parsed = json.loads(body)
    except Exception:
        parsed = {'raw': body}
    return code, parsed

health, _ = call('GET', '/health')
if health != '200':
    raise SystemExit(f'[ERROR] health check failed: {health}')

login_code, login_body = call('POST', '/auth/login/admin', payload={
    'email': 'admin@platform.local',
    'password': 'Admin12345!'
})
if login_code != '200':
    raise SystemExit(f'[ERROR] admin login failed: {login_code}')

token = login_body.get('access_token')
if not token:
    raise SystemExit('[ERROR] admin token alınamadı')

gate_code, gate_body = call('GET', '/phase4/admin/release-gate?environment=prod', token=token)
if gate_code != '200':
    raise SystemExit(f'[ERROR] release gate endpoint failed: {gate_code}')

if gate_body.get('status') != 'READY':
    raise SystemExit(f"[ERROR] release gate READY değil: {gate_body.get('status')} reasons={gate_body.get('reasons')}")

reasons = {str(item) for item in (gate_body.get('reasons') or [])}
if 'live_trading_blocks_disabled' in reasons:
    raise SystemExit('[ERROR] release gate bypass reason tespit edildi: live_trading_blocks_disabled')

keys_code, keys_body = call('GET', '/venues/admin/market-data-keys', token=token)
if keys_code != '200':
    raise SystemExit(f'[ERROR] market data key summary failed: {keys_code}')

items = keys_body.get('items') or []
if not items:
    raise SystemExit('[ERROR] aktif market data key kaydı yok')

active_items = [row for row in items if str(row.get('status')).lower() == 'active']
if not active_items:
    raise SystemExit('[ERROR] active status market data key bulunamadı')

for row in active_items:
    note = str(row.get('note') or '').lower()
    if any(x in note for x in ['demo', 'test', 'mock']):
        raise SystemExit(f"[ERROR] test/demo key notu tespit edildi: provider={row.get('provider')} note={note}")

print('[SUCCESS] Live release gate doğrulaması geçti')
print(json.dumps({
    'release_gate': gate_body,
    'active_market_data_keys': active_items,
}, ensure_ascii=False, indent=2))
PY
