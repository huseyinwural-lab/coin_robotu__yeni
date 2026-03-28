export const READINESS_RUNBOOK_MAP = {
  STRATEGY_ENGINE_UNKNOWN: "runbook_strategy_engine_heartbeat_missing",
  STRATEGY_ENGINE_HEARTBEAT_STALE: "runbook_strategy_engine_stale_heartbeat",
  STRATEGY_ENGINE_IDLE_NO_OUTPUT: "runbook_strategy_engine_idle_without_execution",
  STRATEGY_ENGINE_ERROR: "runbook_strategy_engine_error_state",
  FUNDING_DATA_MISSING: "runbook_funding_source_unavailable",
  FUNDING_DATA_STALE: "runbook_funding_stale_data",
  LIQUIDATION_INPUT_COVERAGE_LOW: "runbook_liquidation_input_coverage",
  LIQUIDATION_MAINT_MARGIN_MISSING: "runbook_liquidation_maintenance_margin",
  EXECUTION_PROOF_ONLY_MOCKED: "runbook_execution_real_proof_required",
  EXECUTION_LIFECYCLE_SYNC_FAIL: "runbook_execution_lifecycle_sync",
  REDUCE_ONLY_ACCEPTED: "runbook_reduce_only_enforcement",
  EXPOSURE_LIMIT_BREACH: "runbook_exposure_limit_breach",
  CAPITAL_EXPOSURE_BREACH: "runbook_capital_guard_exposure_breach",
};

export const resolveRunbookKey = (reasonCode) => READINESS_RUNBOOK_MAP[reasonCode] || "runbook_generic_readiness_triage";
