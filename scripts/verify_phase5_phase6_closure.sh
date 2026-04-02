#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ARTIFACT_DIR="${APP_ROOT}/artifacts"
OUT_JSON="${ARTIFACT_DIR}/phase5_phase6_closure_check.json"

mkdir -p "$ARTIFACT_DIR"

APP_ROOT="$APP_ROOT" ARTIFACT_DIR="$ARTIFACT_DIR" OUT_JSON="$OUT_JSON" python - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

app_root = Path(os.environ['APP_ROOT'])
artifact_dir = Path(os.environ['ARTIFACT_DIR'])
out_json = Path(os.environ['OUT_JSON'])

phase5_required = [
    'faz5_verify_phase5_observability.log',
    'faz5_logging_contract_check.log',
    'faz5_stdout_log_sample.log',
    'faz5_file_log_sample.log',
    'faz5_secret_masking_proof.json',
    'faz5_alembic_upgrade.log',
    'faz5_integration_tests.log',
    'faz5_health_response.json',
    'faz5_ready_healthy_response.json',
    'faz5_ready_not_ready_response.json',
    'faz5_metrics_output.txt',
    'faz5_fake_error_test.log',
    'faz5_alert_payload_sample.json',
    'faz5_alert_delivery.log',
    'faz5_ci_gate_check.log',
    'faz5_closure_summary.json',
    'faz5_evidence_bundle.json',
]

phase6_required = [
    'faz6_security_summary.log',
    'faz6_jwt_rotation_proof.log',
    'faz6_admin_credential_scan.log',
    'faz6_rate_limit_test.log',
    'faz6_api_key_encryption_proof.log',
    'faz6_dump_backup_scan.log',
    'faz6_secret_scan_report.log',
    'faz6_secret_scan_report.json',
    'faz6_security_closure_summary.json',
    'faz6_security_evidence_bundle.json',
]

def check_set(files: list[str], expected_pass_line: str | None = None):
    rows = []
    missing = []
    for name in files:
        p = artifact_dir / name
        exists = p.exists()
        rows.append({'name': name, 'path': str(p), 'exists': exists})
        if not exists:
            missing.append(name)

    pass_line_ok = True
    if expected_pass_line:
        log_name = files[0]
        log_path = artifact_dir / log_name
        if not log_path.exists():
            pass_line_ok = False
        else:
            text = log_path.read_text(encoding='utf-8', errors='ignore')
            pass_line_ok = expected_pass_line in text
    return {
        'files': rows,
        'missing': missing,
        'missing_count': len(missing),
        'summary_pass_line_ok': pass_line_ok,
        'status': 'PASS' if len(missing) == 0 and pass_line_ok else 'FAIL',
    }

phase5 = check_set(phase5_required, 'SUMMARY: PASS')
phase6 = check_set(phase6_required, 'SUMMARY: PASS')

overall = 'PASS' if phase5['status'] == 'PASS' and phase6['status'] == 'PASS' else 'FAIL'
payload = {
    'generated_at': datetime.now(timezone.utc).isoformat(),
    'overall_status': overall,
    'phase5': phase5,
    'phase6': phase6,
}

out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'overall_status': overall, 'artifact': str(out_json)}, ensure_ascii=False))
if overall != 'PASS':
    raise SystemExit(1)
PY
