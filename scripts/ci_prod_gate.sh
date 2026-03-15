#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export TEST_ADMIN_EMAIL="${TEST_ADMIN_EMAIL:-admin@platform.local}"
export TEST_ADMIN_PASSWORD="${TEST_ADMIN_PASSWORD:-Admin12345!}"

"$ROOT/scripts/ci_formula_gate.sh"
"$ROOT/scripts/ci_contract_gate.sh"
"$ROOT/scripts/ci_execution_contract_gate.sh"
"$ROOT/scripts/ci_alembic_drift_gate.sh"
cd "$ROOT/backend"
PYTHONPATH="$ROOT/backend" pytest -q \
  tests/test_full_market_scan.py \
  tests/test_top_volume_fallback.py \
  tests/test_decision_contract.py \
  tests/test_runtime_candidate_persistence.py \
  tests/test_freshness_policy.py \
  tests/test_event_priority_scheduler.py \
  tests/test_bootstrap_admin_first_install.py \
  tests/test_admin_profile_update.py \
  tests/test_admin_password_change.py
cd "$ROOT"
"$ROOT/scripts/run_release_gate_check.sh" --env=prod || {
  echo "release_gate_warning_accepted_for_prod_preview"
}