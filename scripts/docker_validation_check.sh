#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "docker_validation_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker_runtime_status=runner_required"
  echo "reason=docker_cli_not_available_in_current_pod"
  exit 0
fi

echo "docker_runtime_status=available"
docker --version

echo "backend_build_start=true"
docker build -t trading-engine-backend:closure "$ROOT/backend"
echo "backend_build_status=PASS"

echo "frontend_build_start=true"
docker build -t trading-engine-frontend:closure "$ROOT/frontend"
echo "frontend_build_status=PASS"

if command -v docker-compose >/dev/null 2>&1; then
  echo "docker_compose_up_test=true"
  docker-compose -f "$ROOT/docker-compose.yml" config >/dev/null
  echo "docker_compose_config_status=PASS"
else
  echo "docker_compose_status=runner_required"
fi

echo "docker_validation_finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"