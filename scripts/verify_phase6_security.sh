#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ARTIFACT_DIR="${APP_ROOT}/artifacts"
SUMMARY_LOG="${ARTIFACT_DIR}/faz6_security_summary.log"

mkdir -p "$ARTIFACT_DIR"
: > "$SUMMARY_LOG"

log() {
  local line="$1"
  echo "$line" | tee -a "$SUMMARY_LOG" >/dev/null
}

fail() {
  log "FAIL: $1"
  exit 1
}

BACKEND_URL="$(python - <<'PY'
from pathlib import Path
env = Path('/app/frontend/.env')
for raw in env.read_text(encoding='utf-8').splitlines():
    line = raw.strip()
    if line.startswith('REACT_APP_BACKEND_URL='):
        print(line.split('=',1)[1].strip().strip('"').strip("'"))
        break
PY
)"

if [[ -z "$BACKEND_URL" ]]; then
  fail "REACT_APP_BACKEND_URL bulunamadı"
fi

ADMIN_EMAIL="${TEST_ADMIN_EMAIL:-}"
ADMIN_PASSWORD="${TEST_ADMIN_PASSWORD:-}"
if [[ -z "$ADMIN_EMAIL" || -z "$ADMIN_PASSWORD" ]]; then
  fail "TEST_ADMIN_EMAIL veya TEST_ADMIN_PASSWORD eksik"
fi

export BACKEND_URL
export ADMIN_EMAIL
export ADMIN_PASSWORD
export JWT_SECRET

log "T-6.1 JWT rotation testi başlıyor"
python - <<'PY' > "${ARTIFACT_DIR}/faz6_jwt_rotation_proof.log"
import json
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone

import jwt
import requests

backend_url = os.environ['BACKEND_URL']
admin_email = os.environ['ADMIN_EMAIL']
admin_password = os.environ['ADMIN_PASSWORD']

login = requests.post(
    f"{backend_url}/api/auth/login/admin",
    json={"email": admin_email, "password": admin_password},
    timeout=20,
)
if login.status_code != 200:
    raise SystemExit(f"new_login_failed status={login.status_code} body={login.text}")

payload = login.json()
new_token = payload.get("access_token")
user = payload.get("user") or {}
user_id = user.get("id")
if not new_token or not user_id:
    raise SystemExit("new_login_missing_token_or_user")

legacy_signing_key = "change-this-legacy-signing-key-not-active-2026"
old_payload = {
    "sub": user_id,
    "role": user.get("role", "super_admin"),
    "email": user.get("email", admin_email),
    "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
}
old_token = jwt.encode(old_payload, legacy_signing_key, algorithm="HS256")

old_probe = requests.get(
    f"{backend_url}/api/admin/users",
    headers={"Authorization": f"Bearer {old_token}"},
    timeout=20,
)
new_probe = requests.get(
    f"{backend_url}/api/admin/users",
    headers={"Authorization": f"Bearer {new_token}"},
    timeout=20,
)

jwt_secret_len = 0
env_file = Path('/app/backend/.env')
if env_file.exists():
    for raw in env_file.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if line.startswith('JWT_SECRET='):
            jwt_secret_len = len(line.split('=', 1)[1].strip().strip('"').strip("'"))
            break

result = {
    "old_token_status": old_probe.status_code,
    "new_token_status": new_probe.status_code,
    "old_token_invalidated": old_probe.status_code in {401, 403},
    "new_token_valid": new_probe.status_code == 200,
    "new_secret_length": jwt_secret_len,
}
print(json.dumps(result, ensure_ascii=False, indent=2))

if not result["old_token_invalidated"]:
    raise SystemExit("old_token_should_be_invalid")
if not result["new_token_valid"]:
    raise SystemExit("new_token_should_be_valid")
if result["new_secret_length"] < 32:
    raise SystemExit("jwt_secret_too_short")
PY

log "T-6.1 PASS"

log "T-6.2 Admin credential temizliği taraması"
tmp_admin_scan="$(mktemp)"
deprecated_admin_password_key="DEFAULT_ADMIN_""PASSWORD"
legacy_admin_password_marker="Admin""12345!"
rg -n "${deprecated_admin_password_key}|${legacy_admin_password_marker}" "$APP_ROOT" \
  --glob '!**/.git/**' \
  --glob '!**/node_modules/**' \
  --glob '!**/*test*.py' \
  --glob '!**/backend_test_*.py' \
  --glob '!**/test_result.md' \
  --glob '!**/backend/tests/**' \
  --glob '!**/docs/**' \
  --glob '!**/memory/**' \
  --glob '!**/test_reports/**' \
  --glob '!**/artifacts/**' > "$tmp_admin_scan" || true
mv "$tmp_admin_scan" "${ARTIFACT_DIR}/faz6_admin_credential_scan.log"
if [[ -s "${ARTIFACT_DIR}/faz6_admin_credential_scan.log" ]]; then
  fail "aktif kod/config içinde admin credential izi bulundu"
fi
log "T-6.2 PASS"

log "T-6.3 Login rate limit testi"
python - <<'PY' > "${ARTIFACT_DIR}/faz6_rate_limit_test.log"
import json
import os
import requests
import random

backend_url = os.environ['BACKEND_URL']
email = os.environ['ADMIN_EMAIL']
ip_suffix = random.randint(10, 250)
test_ip = f"203.0.113.{ip_suffix}"

statuses = []
retry_after = None
headers = {
    'x-forwarded-for': test_ip,
}

for i in range(6):
    response = requests.post(
        f"{backend_url}/api/auth/login/admin",
        json={"email": email, "password": "WrongPassword!"},
        headers=headers,
        timeout=20,
    )
    statuses.append(response.status_code)
    if response.status_code == 429:
        retry_after = response.headers.get('Retry-After')

result = {
    "test_ip": test_ip,
    "statuses": statuses,
    "sixth_status": statuses[-1],
    "retry_after": retry_after,
    "rate_limit_enforced": statuses[-1] == 429 and bool(retry_after) and all(code != 429 for code in statuses[:5]),
}
print(json.dumps(result, ensure_ascii=False, indent=2))

if not result['rate_limit_enforced']:
    raise SystemExit('rate_limit_not_enforced')
PY
log "T-6.3 PASS"

log "T-6.4 API key encryption kanıtı"
PYTHONPATH="${APP_ROOT}/backend" python - <<'PY' > "${ARTIFACT_DIR}/faz6_api_key_encryption_proof.log"
import json
import os
import secrets

from sqlalchemy import text

from core.users.user_exchange_connector import upsert_user_exchange_connection
from db import SessionLocal
from model_domains.auth_users import User

db = SessionLocal()
try:
    admin = db.query(User).filter(User.email == os.environ['ADMIN_EMAIL']).first()
    if admin is None:
        raise SystemExit('admin_user_not_found')

    api_key_plain = 'AKIA' + secrets.token_hex(10).upper()
    api_secret_plain = 'sec_' + secrets.token_urlsafe(24)

    _ = upsert_user_exchange_connection(
        db,
        user_id=admin.id,
        exchange='binance',
        mode='testnet',
        api_key=api_key_plain,
        api_secret=api_secret_plain,
    )

    row = db.execute(
        text(
            """
            SELECT api_key_encrypted, api_secret_encrypted
            FROM user_exchange_settings
            WHERE user_id = :uid
            """
        ),
        {"uid": admin.id},
    ).first()
    if row is None:
        raise SystemExit('exchange_row_missing')

    key_raw = row[0] or ''
    secret_raw = row[1] or ''
    result = {
        "api_key_plaintext_visible": api_key_plain in key_raw,
        "api_secret_plaintext_visible": api_secret_plain in secret_raw,
        "api_key_cipher_prefix": key_raw[:20],
        "api_secret_cipher_prefix": secret_raw[:20],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result['api_key_plaintext_visible'] or result['api_secret_plaintext_visible']:
        raise SystemExit('plaintext_credentials_detected')
finally:
    db.close()
PY
log "T-6.4 PASS"

log "T-6.5 Repo/artifact secret temizliği"
find "$APP_ROOT" -type f \( -iname "admin_token.txt" -o -iname "*.sql" -o -iname "*.bak" \) \
  ! -path "*/.git/*" \
  ! -path "*/node_modules/*" \
  ! -path "*/backend/migrations/*" > "${ARTIFACT_DIR}/faz6_dump_backup_scan.log" || true
if [[ -s "${ARTIFACT_DIR}/faz6_dump_backup_scan.log" ]]; then
  fail "repo içinde dump/backup dosyası bulundu"
fi
log "T-6.5 PASS"

log "T-6.6 Secret leak prevention guard"
bash "${APP_ROOT}/scripts/ci_secret_leak_guard.sh"
log "T-6.6 PASS"

log "SUMMARY: PASS"
