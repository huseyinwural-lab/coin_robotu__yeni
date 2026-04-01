#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACTS_DIR="$ROOT_DIR/artifacts"
TEST_REPORTS_DIR="$ROOT_DIR/test_reports"

mkdir -p "$ARTIFACTS_DIR/final" "$ARTIFACTS_DIR/latest" "$ARTIFACTS_DIR/archive/obsolete" "$ARTIFACTS_DIR/archive/history"
mkdir -p "$TEST_REPORTS_DIR/archive"

echo "[cleanup] normalizing repeating canary/daily snapshots..."
python - <<'PY'
from pathlib import Path
import shutil

root = Path('/app')
art = root / 'artifacts'

def move(src: Path, dst: Path):
    if not src.exists() or not src.is_file():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        stem, suf = dst.stem, dst.suffix
        i = 1
        while True:
            cand = dst.with_name(f"{stem}__{i}{suf}")
            if not cand.exists():
                dst = cand
                break
            i += 1
    shutil.move(str(src), str(dst))

for pattern in ['daily_smoke_*.json', 'canary_*_summary.json', 'canary_*_metrics_snapshot.json']:
    files = sorted([p for p in art.glob(pattern) if p.is_file()])
    if not files:
        continue
    keep = files[-1]
    move(keep, art / 'latest' / keep.name)
    for p in files[:-1]:
        move(p, art / 'archive' / 'history' / p.name)
PY

echo "[cleanup] done"
