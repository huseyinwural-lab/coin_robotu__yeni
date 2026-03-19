#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
: "${TEST_ADMIN_EMAIL:?Missing TEST_ADMIN_EMAIL}"
: "${TEST_ADMIN_PASSWORD:?Missing TEST_ADMIN_PASSWORD}"

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
  tests/test_discovery_scan.py \
  tests/test_qualification_scan.py \
  tests/test_tiered_scan_pipeline.py \
  tests/test_risk_engine_exposure_limits.py \
  tests/test_risk_engine_stale_spread_veto.py \
  tests/test_risk_engine_daily_loss_cooldown.py \
  tests/test_kill_switch.py \
  tests/test_risk_config_governance.py \
  tests/test_scanner_regime_tuning.py \
  tests/test_execution_quality_calibration.py \
  tests/test_exchange_adapter_smoke.py \
  tests/test_exchange_execution_activation.py \
  tests/test_risk_engine_api_contracts.py \
  tests/test_risk_policy_profiles.py \
  tests/test_bootstrap_admin_first_install.py \
  tests/test_admin_profile_update.py \
  tests/test_admin_password_change.py
cd "$ROOT"
GATE_OUTPUT="$($ROOT/scripts/run_release_gate_check.sh --env=prod 2>&1)" || true
echo "$GATE_OUTPUT"
if echo "$GATE_OUTPUT" | grep -q "release_gate_status=BLOCKED\|release_gate_status=WARNING"; then
  REASON_CODE="$(echo "$GATE_OUTPUT" | grep "reason_code=" | tail -1 | cut -d'=' -f2)"
  echo "release_gate_policy_documented_for_prod_preview=true"
  echo "release_gate_policy_reason_code=${REASON_CODE:-unknown}"
fi