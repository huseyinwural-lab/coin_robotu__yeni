#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND_ENV="$ROOT/frontend/.env"

if [[ ! -f "$FRONTEND_ENV" ]]; then
  echo "frontend_env_missing"
  exit 1
fi

BASE_URL="$(grep '^REACT_APP_BACKEND_URL=' "$FRONTEND_ENV" | cut -d'=' -f2-)"
if [[ -z "$BASE_URL" ]]; then
  echo "backend_url_missing"
  exit 1
fi

TOKEN="$(curl -sS -X POST "$BASE_URL/api/auth/login/admin" -H 'Content-Type: application/json' -d '{"email":"admin@platform.local","password":"Admin12345!"}' | python -c 'import json,sys; print(json.load(sys.stdin).get("access_token",""))')"

if [[ -z "$TOKEN" ]]; then
  echo "admin_token_missing"
  exit 1
fi

echo "rollout_snapshot_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
curl -sS "$BASE_URL/api/admin/universe/runtime-summary?scanner_mode=all_market_symbols&top_n=200" -H "Authorization: Bearer $TOKEN" | python -c 'import json,sys
p=json.load(sys.stdin)
rt=(p.get("runtime_metrics") or {})
ro=(p.get("risk_overview") or {})
print(json.dumps({
"scan_latency_ms": rt.get("scan_latency_ms"),
"decision_latency_ms": rt.get("decision_latency_ms"),
"fallback_active": (p.get("fallback_state") or {}).get("active"),
"snapshot_age_ms": rt.get("snapshot_age_ms"),
"queue_depth": rt.get("queue_depth"),
"candidate_count": rt.get("candidate_count"),
"execution_quality_score": ro.get("execution_quality_score")}, ensure_ascii=False))'