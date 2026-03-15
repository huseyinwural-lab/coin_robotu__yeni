#!/usr/bin/env bash
set -euo pipefail

/app/scripts/ci_formula_gate.sh
/app/scripts/ci_contract_gate.sh
/app/scripts/ci_execution_contract_gate.sh
/app/scripts/ci_alembic_drift_gate.sh
cd /app/backend
PYTHONPATH=/app/backend pytest -q \
  tests/test_full_market_scan.py \
  tests/test_top_volume_fallback.py \
  tests/test_decision_contract.py \
  tests/test_runtime_candidate_persistence.py \
  tests/test_freshness_policy.py \
  tests/test_event_priority_scheduler.py
cd /app
/app/scripts/run_release_gate_check.sh --env=prod