#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ARTIFACT_DIR="$ROOT_DIR/artifacts"
LOG_FILE="$ARTIFACT_DIR/faz6_secret_scan_report.log"
JSON_FILE="$ARTIFACT_DIR/faz6_secret_scan_report.json"
ALLOWLIST_FILE="$ROOT_DIR/.secret-scan-allowlist"

mkdir -p "$ARTIFACT_DIR"

ROOT_DIR="$ROOT_DIR" ARTIFACT_DIR="$ARTIFACT_DIR" ALLOWLIST_FILE="$ALLOWLIST_FILE" python - <<'PY'
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

root = Path(os.environ['ROOT_DIR'])
artifact_dir = Path(os.environ['ARTIFACT_DIR'])
log_file = artifact_dir / 'faz6_secret_scan_report.log'
json_file = artifact_dir / 'faz6_secret_scan_report.json'
allowlist_file = Path(os.environ['ALLOWLIST_FILE'])

allowlist: list[str] = []
if allowlist_file.exists():
    for raw in allowlist_file.read_text(encoding='utf-8').splitlines():
        row = raw.strip()
        if not row or row.startswith('#'):
            continue
        allowlist.append(row)


def is_allowlisted(path: str) -> bool:
    normalized = path.strip()
    for item in allowlist:
        if item.endswith('/'):
            if normalized.startswith(item):
                return True
        elif normalized == item:
            return True
    return False


def is_probably_text(path: Path) -> bool:
    binary_ext = {
        '.png', '.jpg', '.jpeg', '.webp', '.gif', '.ico', '.pdf', '.zip', '.gz',
        '.mp3', '.mp4', '.mov', '.woff', '.woff2', '.ttf', '.eot', '.pyc', '.db',
    }
    if path.suffix.lower() in binary_ext:
        return False
    try:
        _ = path.read_text(encoding='utf-8')
        return True
    except Exception:
        return False


def run(command: list[str]) -> list[str]:
    proc = subprocess.run(command, cwd=str(root), capture_output=True, text=True, check=True)
    return [line for line in proc.stdout.splitlines() if line.strip()]


tracked_files = run(['git', 'ls-files'])
forbidden_patterns = ('*.sql', '*.bak', 'admin_token.txt')

leak_patterns = {
    'private_key_block': re.compile(r'BEGIN\s+(?:RSA\s+|EC\s+|OPENSSH\s+|DSA\s+)?PRIVATE KEY', re.IGNORECASE),
    'aws_access_key': re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
    'jwt_like_token': re.compile(r'\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b'),
    'resend_key': re.compile(r'\bre_[A-Za-z0-9]{20,}\b'),
    'generic_api_key': re.compile(r'\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b', re.IGNORECASE),
}

assignment_pattern = re.compile(
    r'(?i)(jwt[_-]?secret|api[_-]?key|secret|password)\s*[:=]\s*["\']([^"\']{10,})["\']'
)

safe_value_markers = (
    'CHANGE_ME',
    'PLACEHOLDER',
    'EXAMPLE',
    '${{',
    '${',
    '$',
    'missing',
    'dummy',
)

findings: list[dict] = []
for tracked in tracked_files:
    if is_allowlisted(tracked):
        continue

    path = root / tracked
    if not path.exists() or not path.is_file():
        continue

    if any(path.match(pattern) for pattern in forbidden_patterns):
        findings.append({'file': tracked, 'line': 0, 'rule': 'forbidden_dump_or_backup', 'snippet': tracked})

    if not is_probably_text(path):
        continue

    lines = path.read_text(encoding='utf-8').splitlines()
    for idx, line in enumerate(lines, start=1):
        row = line.strip()
        if not row:
            continue

        for rule, pattern in leak_patterns.items():
            if pattern.search(row):
                findings.append({'file': tracked, 'line': idx, 'rule': rule, 'snippet': row[:220]})

        assigned = assignment_pattern.search(row)
        if assigned:
            value = assigned.group(2).strip()
            if any(ch.isspace() for ch in value):
                continue
            if any(marker.lower() in value.lower() for marker in safe_value_markers):
                continue
            if len(value) >= 16:
                findings.append({'file': tracked, 'line': idx, 'rule': 'suspicious_secret_assignment', 'snippet': row[:220]})

summary = {
    'status': 'FAIL' if findings else 'PASS',
    'allowlist_entries': len(allowlist),
    'checked_files': len(tracked_files),
    'finding_count': len(findings),
    'findings': findings,
}

artifact_dir.mkdir(parents=True, exist_ok=True)
log_lines = [
    f"status={summary['status']}",
    f"checked_files={summary['checked_files']}",
    f"finding_count={summary['finding_count']}",
]
for finding in findings:
    log_lines.append(
        f"{finding['file']}:{finding['line']} [{finding['rule']}] {finding['snippet']}"
    )

log_file.write_text('\n'.join(log_lines) + '\n', encoding='utf-8')
json_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

print(log_file)
print(json_file)
if findings:
    raise SystemExit(1)
PY
