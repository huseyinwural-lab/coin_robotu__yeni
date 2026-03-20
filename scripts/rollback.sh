#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${ROOT_DIR}/artifacts/release_state"
HISTORY_FILE="${STATE_DIR}/deploy_history.jsonl"
CURRENT_FILE="${STATE_DIR}/current_release.env"

if [[ ! -f "${HISTORY_FILE}" ]]; then
  echo "[ERROR] deploy geçmişi bulunamadı: ${HISTORY_FILE}"
  exit 1
fi

CURRENT_VERSION=""
if [[ -f "${CURRENT_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${CURRENT_FILE}" || true
  CURRENT_VERSION="${CURRENT_VERSION:-}"
fi

PREVIOUS_VERSION="$(python - <<PY
import json
from pathlib import Path

history_path = Path("${HISTORY_FILE}")
current = "${CURRENT_VERSION}"
rows = []
for raw in history_path.read_text(encoding="utf-8").splitlines():
    raw = raw.strip()
    if not raw:
        continue
    try:
        rows.append(json.loads(raw))
    except Exception:
        continue

success_status = {"deployed", "rolled_back"}
candidates = [r for r in rows if str(r.get("status")) in success_status]

target = ""
for row in reversed(candidates):
    version = str(row.get("version") or "")
    if not version:
        continue
    if current and version == current:
        continue
    target = version
    break

print(target)
PY
)"

if [[ -z "${PREVIOUS_VERSION}" ]]; then
  echo "[ERROR] previous version otomatik çözümlenemedi"
  exit 1
fi

START_TS="$(date +%s)"
DEPLOY_SOURCE="rollback" "${ROOT_DIR}/scripts/deploy.sh" "${PREVIOUS_VERSION}"
END_TS="$(date +%s)"
ROLLBACK_TIME="$((END_TS - START_TS))"

if [[ "${ROLLBACK_TIME}" -ge 60 ]]; then
  echo "[ERROR] rollback_time=${ROLLBACK_TIME}s (beklenen <60s)"
  exit 1
fi

python - <<PY
import json, datetime
entry = {
  "version": "${PREVIOUS_VERSION}",
  "image_tag": "app:release-${PREVIOUS_VERSION}",
  "status": "rolled_back",
  "source": "rollback",
  "rollback_time_seconds": ${ROLLBACK_TIME},
  "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
with open("${HISTORY_FILE}", "a", encoding="utf-8") as f:
    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
PY

echo "[OK] previous_version=${PREVIOUS_VERSION}"
echo "[OK] rollback_time_seconds=${ROLLBACK_TIME}"