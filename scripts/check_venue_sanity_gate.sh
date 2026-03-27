#!/usr/bin/env bash
set -euo pipefail

SANITY_FILE="${VENUE_SANITY_CACHE_PATH:-/tmp/venue_control_plane_sanity.json}"

if [ ! -f "$SANITY_FILE" ]; then
  echo "[sanity-gate] FAIL: sanity cache not found at $SANITY_FILE"
  exit 1
fi

NET_STATUS=$(python - <<'PYTHON'
import json, os
path=os.environ.get('VENUE_SANITY_CACHE_PATH','/tmp/venue_control_plane_sanity.json')
with open(path,'r',encoding='utf-8') as f:
    payload=json.load(f)
print(str(payload.get('net_status') or '').upper())
PYTHON
)

if [ "$NET_STATUS" != "PASS" ]; then
  echo "[sanity-gate] FAIL: net_status=$NET_STATUS"
  exit 1
fi

echo "[sanity-gate] PASS"
