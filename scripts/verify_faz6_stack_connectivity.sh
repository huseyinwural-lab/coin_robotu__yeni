#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

LOG_DIR="/tmp/faz6"
mkdir -p "$LOG_DIR"

FRONTEND_BACKEND_URL="${REACT_APP_BACKEND_URL:-http://localhost:8001}"
export REACT_APP_BACKEND_URL="$FRONTEND_BACKEND_URL"

echo "[1/7] Starting docker stack"
docker compose up -d

echo "[1.1/7] Waiting services to be healthy"
for svc in postgres redis backend frontend; do
  ready=0
  for _ in $(seq 1 60); do
    cid="$(docker compose ps -q "$svc")"
    if [[ -z "$cid" ]]; then
      sleep 2
      continue
    fi
    status="$(docker inspect "$cid" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>/dev/null || true)"
    if [[ "$status" == "healthy" || "$status" == "running" ]]; then
      ready=1
      break
    fi
    sleep 2
  done
  if [[ "$ready" != "1" ]]; then
    echo "[ERROR] Service not ready: $svc"
    docker compose ps || true
    docker compose logs "$svc" --tail=200 || true
    exit 1
  fi
done

echo "[2/7] Stack status"
docker compose ps | tee "$LOG_DIR/compose_ps.txt"

for svc in postgres redis backend frontend; do
  cid="$(docker compose ps -q "$svc")"
  if [[ -z "$cid" ]]; then
    echo "[ERROR] Container missing: $svc"
    exit 1
  fi
  docker inspect "$cid" --format '{{json .State}}' > "$LOG_DIR/${svc}_state.json"
done

echo "[3/7] Validating healthcheck presence in compose"
python - <<'PY'
from pathlib import Path
import yaml

compose_path = Path('docker-compose.yml')
if not compose_path.exists():
    raise SystemExit(f"[ERROR] Missing compose file: {compose_path.resolve()}")

cfg = yaml.safe_load(compose_path.read_text())
services = cfg.get('services', {})
required = ['postgres', 'redis', 'backend', 'frontend']
missing = [s for s in required if 'healthcheck' not in (services.get(s) or {})]
if missing:
    raise SystemExit(f"[ERROR] Missing healthcheck for: {missing}")
print('[OK] Healthcheck structure present for all required services')
PY

echo "[4/7] Redis connectivity smoke"
docker compose logs redis --tail=100 > "$LOG_DIR/redis.log" || true
docker compose logs backend --tail=200 > "$LOG_DIR/backend.log" || true
docker compose exec -T redis redis-cli ping | tee "$LOG_DIR/redis_ping.txt"
docker compose exec -T backend sh -lc 'python - <<"PY"
import os, redis
url=os.environ["REDIS_URL"]
r=redis.from_url(url)
print(r.ping())
PY' | tee "$LOG_DIR/backend_redis_ping.txt"

echo "[5/7] Frontend runtime env validation"
docker compose exec -T frontend sh -lc 'env | grep REACT_APP_BACKEND_URL' | tee "$LOG_DIR/frontend_env.txt"

echo "[6/7] Frontend -> backend network validation"
docker compose exec -T frontend sh -lc 'node -e "require(\"http\").get(\"http://backend:8001/api/health\",r=>{console.log(\"status=\"+r.statusCode);process.exit(r.statusCode===200?0:1)}).on(\"error\",e=>{console.error(e.message);process.exit(1)})"' | tee "$LOG_DIR/frontend_backend_health.txt"

echo "[7/7] Frontend auth flow smoke (network-level)"
docker compose exec -T frontend sh -lc 'node - <<"JS"
const http = require("http");
const payload = JSON.stringify({ email: "admin@platform.local", password: "Admin12345!" });
const req = http.request({
  hostname: "backend",
  port: 8001,
  path: "/api/auth/login/admin",
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Content-Length": Buffer.byteLength(payload),
  },
}, (res) => {
  let body = "";
  res.on("data", (d) => (body += d));
  res.on("end", () => {
    console.log("status=" + res.statusCode);
    try {
      const parsed = JSON.parse(body);
      console.log("has_access_token=" + Boolean(parsed.access_token));
    } catch {
      console.log("raw_body=" + body.slice(0, 200));
    }
    process.exit(res.statusCode === 200 ? 0 : 1);
  });
});
req.on("error", (e) => {
  console.error(e.message);
  process.exit(1);
});
req.write(payload);
req.end();
JS' | tee "$LOG_DIR/frontend_auth_smoke.txt"

echo "Stack health: OK"
echo "Postgres: OK"
echo "Redis: OK"
echo "Backend: OK"
echo "Frontend: OK"
echo "Frontend backend URL: OK"
echo "Frontend network: OK"
echo "Frontend auth flow: OK"
echo "[SUCCESS] FAZ-6 stack/connectivity verification passed"
