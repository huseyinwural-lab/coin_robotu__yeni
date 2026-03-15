#!/usr/bin/env bash
set -euo pipefail

/app/scripts/ci_formula_gate.sh
/app/scripts/ci_contract_gate.sh
/app/scripts/ci_execution_contract_gate.sh
/app/scripts/ci_alembic_drift_gate.sh
/app/scripts/run_release_gate_check.sh --env=prod