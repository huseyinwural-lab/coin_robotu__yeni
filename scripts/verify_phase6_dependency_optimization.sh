#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ARTIFACT_DIR="${APP_ROOT}/artifacts"
SUMMARY_LOG="${ARTIFACT_DIR}/faz6_dependency_optimization.log"
INVENTORY_JSON="${ARTIFACT_DIR}/faz6_dependency_inventory.json"
DOCKER_CHECK_LOG="${ARTIFACT_DIR}/faz6_docker_optimization_check.log"
CLOSURE_JSON="${ARTIFACT_DIR}/faz6_closure_summary.json"

mkdir -p "$ARTIFACT_DIR"
: > "$SUMMARY_LOG"

log() {
  local line="$1"
  echo "$line" | tee -a "$SUMMARY_LOG"
}

fail() {
  log "FAIL: $1"
  log "SUMMARY: FAIL"
  write_closure "FAIL"
  exit 1
}

write_closure() {
  local final_status="$1"
  APP_ROOT="$APP_ROOT" ARTIFACT_DIR="$ARTIFACT_DIR" SUMMARY_LOG="$SUMMARY_LOG" INVENTORY_JSON="$INVENTORY_JSON" DOCKER_CHECK_LOG="$DOCKER_CHECK_LOG" CLOSURE_JSON="$CLOSURE_JSON" FINAL_STATUS="$final_status" python - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

app_root = Path(os.environ["APP_ROOT"])
artifact_dir = Path(os.environ["ARTIFACT_DIR"])
summary_log = Path(os.environ["SUMMARY_LOG"])
inventory_json = Path(os.environ["INVENTORY_JSON"])
docker_check_log = Path(os.environ["DOCKER_CHECK_LOG"])
closure_json = Path(os.environ["CLOSURE_JSON"])
status = str(os.environ.get("FINAL_STATUS") or "UNKNOWN").upper()

expected = [
    "artifacts/faz6_dependency_optimization.log",
    "artifacts/faz6_dependency_inventory.json",
    "artifacts/faz6_docker_optimization_check.log",
    "backend/.dockerignore",
    "frontend/.dockerignore",
    "backend/Dockerfile",
    "frontend/Dockerfile",
]

files = []
for rel in expected:
    p = app_root / rel
    files.append({"relative_path": rel, "exists": p.exists(), "path": str(p)})

missing = [item["relative_path"] for item in files if not item["exists"]]
tail = ""
if summary_log.exists():
    lines = summary_log.read_text(encoding="utf-8", errors="ignore").splitlines()
    tail = "\n".join(lines[-20:])

closure = {
    "phase": "FAZ-6",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "status": status,
    "summary_log": str(summary_log),
    "inventory_json": str(inventory_json),
    "docker_check_log": str(docker_check_log),
    "files": files,
    "missing_count": len(missing),
    "missing_files": missing,
    "log_tail": tail,
}

closure_json.write_text(json.dumps(closure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": status, "closure": str(closure_json), "missing_count": len(missing)}, ensure_ascii=False))
PY
}

log "T-6.1 dependency envanteri"
APP_ROOT="$APP_ROOT" python - <<'PY' > "$INVENTORY_JSON"
import json
import re
from datetime import datetime, timezone
from pathlib import Path

root = Path(__import__('os').environ['APP_ROOT'])
req_path = root / 'backend' / 'requirements.txt'
pkg_path = root / 'frontend' / 'package.json'

backend_lines = [line.strip() for line in req_path.read_text(encoding='utf-8').splitlines() if line.strip() and not line.strip().startswith('#')]
frontend_pkg = json.loads(pkg_path.read_text(encoding='utf-8'))
frontend_deps = frontend_pkg.get('dependencies') or {}

heavy_backend_markers = {
    'numpy', 'pandas', 'openai', 'google-genai', 'google-generativeai', 'tokenizers', 'pyiceberg', 'huggingface_hub', 'torch'
}
heavy_frontend_markers = {
    'framer-motion', 'recharts', '@xyflow/react', 'lightweight-charts', 'react-scripts'
}

backend_packages = []
for line in backend_lines:
    name = re.split(r'[<>=!~]', line, maxsplit=1)[0].strip().lower()
    backend_packages.append(name)

heavy_backend = sorted([name for name in backend_packages if name in heavy_backend_markers])
heavy_frontend = sorted([name for name in frontend_deps.keys() if name in heavy_frontend_markers])

payload = {
    'phase': 'FAZ-6',
    'generated_at': datetime.now(timezone.utc).isoformat(),
    'backend_dependency_count': len(backend_packages),
    'frontend_dependency_count': len(frontend_deps),
    'heavy_backend_dependencies': heavy_backend,
    'heavy_frontend_dependencies': heavy_frontend,
    'notes': [
        'Bu envanter build optimizasyonuna giriş için referanstır.',
        'Ağır paketler runtime ihtiyacına göre opsiyonel katmanlara ayrılabilir.',
    ],
}
print(json.dumps(payload, ensure_ascii=False, indent=2))
PY
log "PASS: dependency envanteri üretildi"

log "T-6.2 docker build optimizasyon kontrolü"
APP_ROOT="$APP_ROOT" python - <<'PY' > "$DOCKER_CHECK_LOG"
import os
from pathlib import Path

root = Path(os.environ['APP_ROOT'])
backend_docker = (root / 'backend' / 'Dockerfile').read_text(encoding='utf-8')
frontend_docker = (root / 'frontend' / 'Dockerfile').read_text(encoding='utf-8')

checks = {
    'backend_installs_from_requirements_before_copy_all': 'COPY requirements.txt' in backend_docker and 'COPY . .' in backend_docker,
    'backend_no_install_recommends': '--no-install-recommends' in backend_docker,
    'frontend_lockfile_layered_install': 'COPY package.json' in frontend_docker and 'COPY yarn.lock*' in frontend_docker,
    'frontend_copy_source_after_install': frontend_docker.find('COPY . .') > frontend_docker.find('yarn install'),
    'backend_dockerignore_exists': (root / 'backend' / '.dockerignore').exists(),
    'frontend_dockerignore_exists': (root / 'frontend' / '.dockerignore').exists(),
}

for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'} {name}")

if not all(checks.values()):
    failed = [name for name, ok in checks.items() if not ok]
    raise SystemExit('FAILED_CHECKS ' + ','.join(failed))

print('PASS docker optimization checks')
PY
log "PASS: docker optimization kontrolleri geçti"

log "SUMMARY: PASS"
write_closure "PASS"
