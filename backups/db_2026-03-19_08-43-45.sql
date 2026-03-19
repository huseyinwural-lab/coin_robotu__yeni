--
-- PostgreSQL database dump
--

\restrict ny1qrhqgbrB7JhIHeLwNKQaw1iHzhabw0ATmv7WTe77HNpWWyiCKhEA8BtmZ5sM

-- Dumped from database version 15.16 (Debian 15.16-0+deb12u1)
-- Dumped by pg_dump version 15.16 (Debian 15.16-0+deb12u1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

ALTER TABLE IF EXISTS ONLY public.user_venue_assignments DROP CONSTRAINT IF EXISTS user_venue_assignments_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.user_signal_modes DROP CONSTRAINT IF EXISTS user_signal_modes_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.user_scanner_symbol_selections DROP CONSTRAINT IF EXISTS user_scanner_symbol_selections_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.user_scanner_results DROP CONSTRAINT IF EXISTS user_scanner_results_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.user_scanner_automation_profiles DROP CONSTRAINT IF EXISTS user_scanner_automation_profiles_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.user_scanner_automation_configs DROP CONSTRAINT IF EXISTS user_scanner_automation_configs_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.user_risk_settings DROP CONSTRAINT IF EXISTS user_risk_settings_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.user_onboarding_profiles DROP CONSTRAINT IF EXISTS user_onboarding_profiles_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.user_mfa_preferences DROP CONSTRAINT IF EXISTS user_mfa_preferences_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.user_mfa_backup_codes DROP CONSTRAINT IF EXISTS user_mfa_backup_codes_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.user_learning_simulation_suggestions DROP CONSTRAINT IF EXISTS user_learning_simulation_suggestions_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.user_learning_simulation_suggestions DROP CONSTRAINT IF EXISTS user_learning_simulation_suggestions_reviewed_by_fkey;
ALTER TABLE IF EXISTS ONLY public.user_indicator_watchlist DROP CONSTRAINT IF EXISTS user_indicator_watchlist_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.user_indicator_saved_queries DROP CONSTRAINT IF EXISTS user_indicator_saved_queries_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.user_execution_intents DROP CONSTRAINT IF EXISTS user_execution_intents_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.user_execution_intents DROP CONSTRAINT IF EXISTS user_execution_intents_admin_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.user_exchange_settings DROP CONSTRAINT IF EXISTS user_exchange_settings_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.user_exchange_connections DROP CONSTRAINT IF EXISTS user_exchange_connections_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.user_decision_traces DROP CONSTRAINT IF EXISTS user_decision_traces_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.universe_rollout_state DROP CONSTRAINT IF EXISTS universe_rollout_state_approved_by_fkey;
ALTER TABLE IF EXISTS ONLY public.testnet_execution_logs DROP CONSTRAINT IF EXISTS testnet_execution_logs_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.symbol_selection_watchlists DROP CONSTRAINT IF EXISTS symbol_selection_watchlists_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.strategy_versions DROP CONSTRAINT IF EXISTS strategy_versions_strategy_id_fkey;
ALTER TABLE IF EXISTS ONLY public.strategy_versions DROP CONSTRAINT IF EXISTS strategy_versions_created_by_fkey;
ALTER TABLE IF EXISTS ONLY public.strategy_templates DROP CONSTRAINT IF EXISTS strategy_templates_created_by_fkey;
ALTER TABLE IF EXISTS ONLY public.strategy_regime_bindings DROP CONSTRAINT IF EXISTS strategy_regime_bindings_strategy_version_id_fkey;
ALTER TABLE IF EXISTS ONLY public.strategy_regime_bindings DROP CONSTRAINT IF EXISTS strategy_regime_bindings_created_by_fkey;
ALTER TABLE IF EXISTS ONLY public.strategy_observability_events DROP CONSTRAINT IF EXISTS strategy_observability_events_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.strategy_definitions DROP CONSTRAINT IF EXISTS strategy_definitions_created_by_fkey;
ALTER TABLE IF EXISTS ONLY public.signal_events DROP CONSTRAINT IF EXISTS signal_events_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.signal_events DROP CONSTRAINT IF EXISTS signal_events_bot_profile_id_fkey;
ALTER TABLE IF EXISTS ONLY public.scanner_performance_snapshots DROP CONSTRAINT IF EXISTS scanner_performance_snapshots_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.risk_policy_audit_events DROP CONSTRAINT IF EXISTS risk_policy_audit_events_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.risk_policy_audit_events DROP CONSTRAINT IF EXISTS risk_policy_audit_events_replay_run_id_fkey;
ALTER TABLE IF EXISTS ONLY public.risk_policies DROP CONSTRAINT IF EXISTS risk_policies_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.replay_runs DROP CONSTRAINT IF EXISTS replay_runs_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.replay_executions DROP CONSTRAINT IF EXISTS replay_executions_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.replay_executions DROP CONSTRAINT IF EXISTS replay_executions_replay_run_id_fkey;
ALTER TABLE IF EXISTS ONLY public.replay_equity_points DROP CONSTRAINT IF EXISTS replay_equity_points_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.replay_equity_points DROP CONSTRAINT IF EXISTS replay_equity_points_replay_run_id_fkey;
ALTER TABLE IF EXISTS ONLY public.release_gate_overrides DROP CONSTRAINT IF EXISTS release_gate_overrides_admin_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.regime_snapshots DROP CONSTRAINT IF EXISTS regime_snapshots_strategy_version_id_fkey;
ALTER TABLE IF EXISTS ONLY public.positions DROP CONSTRAINT IF EXISTS positions_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.position_ledger_events DROP CONSTRAINT IF EXISTS position_ledger_events_position_id_fkey;
ALTER TABLE IF EXISTS ONLY public.portfolio_exposure_snapshot DROP CONSTRAINT IF EXISTS portfolio_exposure_snapshot_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.permission_drift_events DROP CONSTRAINT IF EXISTS permission_drift_events_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.pending_signals DROP CONSTRAINT IF EXISTS pending_signals_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.paper_positions DROP CONSTRAINT IF EXISTS paper_positions_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.paper_positions DROP CONSTRAINT IF EXISTS paper_positions_bot_profile_id_fkey;
ALTER TABLE IF EXISTS ONLY public.manual_override_log DROP CONSTRAINT IF EXISTS manual_override_log_admin_id_fkey;
ALTER TABLE IF EXISTS ONLY public.learning_decision_events DROP CONSTRAINT IF EXISTS learning_decision_events_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.learning_decision_events DROP CONSTRAINT IF EXISTS learning_decision_events_scanner_result_id_fkey;
ALTER TABLE IF EXISTS ONLY public.learning_decision_events DROP CONSTRAINT IF EXISTS learning_decision_events_pending_signal_id_fkey;
ALTER TABLE IF EXISTS ONLY public.pending_signals DROP CONSTRAINT IF EXISTS fk_ps_risk_policy;
ALTER TABLE IF EXISTS ONLY public.pending_signals DROP CONSTRAINT IF EXISTS fk_ps_order_intent;
ALTER TABLE IF EXISTS ONLY public.pending_signals DROP CONSTRAINT IF EXISTS fk_ps_exc_conn;
ALTER TABLE IF EXISTS ONLY public.execution_metrics DROP CONSTRAINT IF EXISTS execution_metrics_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.execution_lifecycle_events DROP CONSTRAINT IF EXISTS execution_lifecycle_events_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.execution_lifecycle_events DROP CONSTRAINT IF EXISTS execution_lifecycle_events_execution_metric_id_fkey;
ALTER TABLE IF EXISTS ONLY public.execution_intents DROP CONSTRAINT IF EXISTS execution_intents_strategy_version_id_fkey;
ALTER TABLE IF EXISTS ONLY public.execution_intents DROP CONSTRAINT IF EXISTS execution_intents_strategy_id_fkey;
ALTER TABLE IF EXISTS ONLY public.execution_intent_events DROP CONSTRAINT IF EXISTS execution_intent_events_intent_id_fkey;
ALTER TABLE IF EXISTS ONLY public.execution_events DROP CONSTRAINT IF EXISTS execution_events_bot_profile_id_fkey;
ALTER TABLE IF EXISTS ONLY public.execution_correction_events DROP CONSTRAINT IF EXISTS execution_correction_events_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.execution_correction_events DROP CONSTRAINT IF EXISTS execution_correction_events_execution_metric_id_fkey;
ALTER TABLE IF EXISTS ONLY public.decision_trace_hot DROP CONSTRAINT IF EXISTS decision_trace_hot_strategy_version_id_fkey;
ALTER TABLE IF EXISTS ONLY public.decision_trace_cold DROP CONSTRAINT IF EXISTS decision_trace_cold_strategy_version_id_fkey;
ALTER TABLE IF EXISTS ONLY public.brand_settings DROP CONSTRAINT IF EXISTS brand_settings_updated_by_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.bot_profiles DROP CONSTRAINT IF EXISTS bot_profiles_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.auth_mfa_challenges DROP CONSTRAINT IF EXISTS auth_mfa_challenges_user_id_fkey;
DROP INDEX IF EXISTS public.ix_weekly_report_archives_trigger_source;
DROP INDEX IF EXISTS public.ix_weekly_report_archives_status;
DROP INDEX IF EXISTS public.ix_weekly_report_archives_report_type;
DROP INDEX IF EXISTS public.ix_weekly_report_archives_generated_at;
DROP INDEX IF EXISTS public.ix_users_email;
DROP INDEX IF EXISTS public.ix_user_venue_assignments_user_id;
DROP INDEX IF EXISTS public.ix_user_venue_assignments_exchange_code;
DROP INDEX IF EXISTS public.ix_user_signal_modes_user_id;
DROP INDEX IF EXISTS public.ix_user_scanner_symbol_selections_user_id;
DROP INDEX IF EXISTS public.ix_user_scanner_symbol_selections_scanner_id;
DROP INDEX IF EXISTS public.ix_user_scanner_symbol_selections_saved_at;
DROP INDEX IF EXISTS public.ix_user_scanner_results_user_id;
DROP INDEX IF EXISTS public.ix_user_scanner_results_symbol;
DROP INDEX IF EXISTS public.ix_user_scanner_results_run_id;
DROP INDEX IF EXISTS public.ix_user_scanner_results_generated_at;
DROP INDEX IF EXISTS public.ix_user_scanner_automation_profiles_user_id;
DROP INDEX IF EXISTS public.ix_user_scanner_automation_profiles_name;
DROP INDEX IF EXISTS public.ix_user_scanner_automation_profiles_auto_enabled;
DROP INDEX IF EXISTS public.ix_user_scanner_automation_configs_user_id;
DROP INDEX IF EXISTS public.ix_user_scanner_automation_configs_auto_enabled;
DROP INDEX IF EXISTS public.ix_user_risk_settings_user_id;
DROP INDEX IF EXISTS public.ix_user_onboarding_profiles_user_id;
DROP INDEX IF EXISTS public.ix_user_onboarding_profiles_password_reset_token_hash;
DROP INDEX IF EXISTS public.ix_user_mfa_preferences_user_id;
DROP INDEX IF EXISTS public.ix_user_mfa_backup_codes_user_id;
DROP INDEX IF EXISTS public.ix_user_mfa_backup_codes_code_hash;
DROP INDEX IF EXISTS public.ix_user_learning_simulation_suggestions_user_id;
DROP INDEX IF EXISTS public.ix_user_learning_simulation_suggestions_symbol;
DROP INDEX IF EXISTS public.ix_user_learning_simulation_suggestions_strategy_id;
DROP INDEX IF EXISTS public.ix_user_learning_simulation_suggestions_status;
DROP INDEX IF EXISTS public.ix_user_learning_simulation_suggestions_recommendation_type;
DROP INDEX IF EXISTS public.ix_user_learning_simulation_suggestions_family;
DROP INDEX IF EXISTS public.ix_user_learning_simulation_suggestions_created_at;
DROP INDEX IF EXISTS public.ix_user_indicator_watchlist_user_id;
DROP INDEX IF EXISTS public.ix_user_indicator_watchlist_symbol;
DROP INDEX IF EXISTS public.ix_user_indicator_saved_queries_user_id;
DROP INDEX IF EXISTS public.ix_user_execution_intents_user_id;
DROP INDEX IF EXISTS public.ix_user_execution_intents_symbol;
DROP INDEX IF EXISTS public.ix_user_execution_intents_status;
DROP INDEX IF EXISTS public.ix_user_execution_intents_preview_hash;
DROP INDEX IF EXISTS public.ix_user_execution_intents_position_id;
DROP INDEX IF EXISTS public.ix_user_execution_intents_intent_type;
DROP INDEX IF EXISTS public.ix_user_execution_intents_intent_token;
DROP INDEX IF EXISTS public.ix_user_exchange_settings_user_id;
DROP INDEX IF EXISTS public.ix_user_exchange_connections_user_id;
DROP INDEX IF EXISTS public.ix_user_decision_traces_user_id;
DROP INDEX IF EXISTS public.ix_user_decision_traces_strategy;
DROP INDEX IF EXISTS public.ix_user_decision_traces_scope;
DROP INDEX IF EXISTS public.ix_user_decision_traces_expires_at;
DROP INDEX IF EXISTS public.ix_user_decision_traces_entity_id;
DROP INDEX IF EXISTS public.ix_user_decision_traces_decision;
DROP INDEX IF EXISTS public.ix_user_decision_traces_created_at;
DROP INDEX IF EXISTS public.ix_testnet_execution_logs_user_id;
DROP INDEX IF EXISTS public.ix_system_alerts_fingerprint;
DROP INDEX IF EXISTS public.ix_system_alerts_entity_key;
DROP INDEX IF EXISTS public.ix_system_alerts_alert_type;
DROP INDEX IF EXISTS public.ix_symbol_selection_watchlists_user_id;
DROP INDEX IF EXISTS public.ix_symbol_selection_watchlists_source;
DROP INDEX IF EXISTS public.ix_symbol_selection_watchlists_name;
DROP INDEX IF EXISTS public.ix_strategy_versions_version_hash;
DROP INDEX IF EXISTS public.ix_strategy_versions_strategy_id;
DROP INDEX IF EXISTS public.ix_strategy_versions_created_by;
DROP INDEX IF EXISTS public.ix_strategy_templates_strategy_type;
DROP INDEX IF EXISTS public.ix_strategy_regime_bindings_strategy_version_id;
DROP INDEX IF EXISTS public.ix_strategy_regime_bindings_created_by;
DROP INDEX IF EXISTS public.ix_strategy_outcome_memory_strategy_id;
DROP INDEX IF EXISTS public.ix_strategy_observability_events_user_id;
DROP INDEX IF EXISTS public.ix_strategy_observability_events_symbol;
DROP INDEX IF EXISTS public.ix_strategy_observability_events_strategy_id;
DROP INDEX IF EXISTS public.ix_strategy_observability_events_selection_cycle_id;
DROP INDEX IF EXISTS public.ix_strategy_observability_events_rejection_reason;
DROP INDEX IF EXISTS public.ix_strategy_observability_events_market_regime;
DROP INDEX IF EXISTS public.ix_strategy_observability_events_event_type;
DROP INDEX IF EXISTS public.ix_strategy_observability_events_created_at;
DROP INDEX IF EXISTS public.ix_strategy_observability_events_bot_profile_id;
DROP INDEX IF EXISTS public.ix_strategy_observability_events_audit_log_id;
DROP INDEX IF EXISTS public.ix_strategy_definitions_name;
DROP INDEX IF EXISTS public.ix_strategy_definitions_created_by;
DROP INDEX IF EXISTS public.ix_strategy_definitions_code;
DROP INDEX IF EXISTS public.ix_strategy_allocations_state;
DROP INDEX IF EXISTS public.ix_signal_events_user_id;
DROP INDEX IF EXISTS public.ix_signal_events_bot_profile_id;
DROP INDEX IF EXISTS public.ix_scanner_performance_snapshots_user_id;
DROP INDEX IF EXISTS public.ix_scanner_performance_snapshots_stage;
DROP INDEX IF EXISTS public.ix_scanner_performance_snapshots_run_id;
DROP INDEX IF EXISTS public.ix_scanner_performance_snapshots_created_at;
DROP INDEX IF EXISTS public.ix_scanner_fallback_events_run_id;
DROP INDEX IF EXISTS public.ix_scanner_fallback_events_event_type;
DROP INDEX IF EXISTS public.ix_scanner_fallback_events_created_at;
DROP INDEX IF EXISTS public.ix_runtime_scan_candidates_symbol;
DROP INDEX IF EXISTS public.ix_runtime_scan_candidates_scan_timestamp;
DROP INDEX IF EXISTS public.ix_runtime_scan_candidates_market_type;
DROP INDEX IF EXISTS public.ix_runtime_scan_candidates_decision;
DROP INDEX IF EXISTS public.ix_risk_policy_audit_events_user_id;
DROP INDEX IF EXISTS public.ix_risk_policy_audit_events_replay_run_id;
DROP INDEX IF EXISTS public.ix_risk_policies_user_id;
DROP INDEX IF EXISTS public.ix_replay_runs_user_id;
DROP INDEX IF EXISTS public.ix_replay_executions_user_id;
DROP INDEX IF EXISTS public.ix_replay_executions_replay_run_id;
DROP INDEX IF EXISTS public.ix_replay_equity_points_user_id;
DROP INDEX IF EXISTS public.ix_replay_equity_points_replay_run_id;
DROP INDEX IF EXISTS public.ix_release_gate_overrides_admin_user_id;
DROP INDEX IF EXISTS public.ix_regime_snapshots_timestamp_utc;
DROP INDEX IF EXISTS public.ix_regime_snapshots_timeframe;
DROP INDEX IF EXISTS public.ix_regime_snapshots_symbol;
DROP INDEX IF EXISTS public.ix_regime_snapshots_strategy_version_id;
DROP INDEX IF EXISTS public.ix_regime_snapshots_regime_label;
DROP INDEX IF EXISTS public.ix_regime_snapshots_regime_hash;
DROP INDEX IF EXISTS public.ix_positions_user_id;
DROP INDEX IF EXISTS public.ix_positions_symbol;
DROP INDEX IF EXISTS public.ix_positions_strategy_id;
DROP INDEX IF EXISTS public.ix_positions_status;
DROP INDEX IF EXISTS public.ix_positions_cluster_id;
DROP INDEX IF EXISTS public.ix_position_ledger_events_position_id;
DROP INDEX IF EXISTS public.ix_portfolio_exposure_snapshot_user_id;
DROP INDEX IF EXISTS public.ix_portfolio_exposure_snapshot_timestamp;
DROP INDEX IF EXISTS public.ix_portfolio_exposure_snapshot_symbol;
DROP INDEX IF EXISTS public.ix_portfolio_exposure_snapshot_strategy_id;
DROP INDEX IF EXISTS public.ix_portfolio_exposure_snapshot_cluster_id;
DROP INDEX IF EXISTS public.ix_permission_drift_events_user_id;
DROP INDEX IF EXISTS public.ix_pending_signals_user_id;
DROP INDEX IF EXISTS public.ix_pending_signals_symbol;
DROP INDEX IF EXISTS public.ix_pending_signals_status;
DROP INDEX IF EXISTS public.ix_pending_signals_signal_id;
DROP INDEX IF EXISTS public.ix_pending_signals_risk_policy_id;
DROP INDEX IF EXISTS public.ix_pending_signals_order_position_id;
DROP INDEX IF EXISTS public.ix_pending_signals_exchange_connection_id;
DROP INDEX IF EXISTS public.ix_pending_signals_current_state;
DROP INDEX IF EXISTS public.ix_pending_signals_created_order_intent_id;
DROP INDEX IF EXISTS public.ix_pending_signals_bot_profile_id;
DROP INDEX IF EXISTS public.ix_paper_positions_user_id;
DROP INDEX IF EXISTS public.ix_paper_positions_symbol;
DROP INDEX IF EXISTS public.ix_paper_positions_bot_profile_id;
DROP INDEX IF EXISTS public.ix_manual_override_log_timestamp;
DROP INDEX IF EXISTS public.ix_manual_override_log_admin_id;
DROP INDEX IF EXISTS public.ix_manual_override_log_action_type;
DROP INDEX IF EXISTS public.ix_learning_recommendations_type;
DROP INDEX IF EXISTS public.ix_learning_recommendations_strategy_id;
DROP INDEX IF EXISTS public.ix_learning_recommendations_family;
DROP INDEX IF EXISTS public.ix_learning_decision_events_symbol;
DROP INDEX IF EXISTS public.ix_learning_decision_events_outcome_label;
DROP INDEX IF EXISTS public.ix_learning_decision_events_decision;
DROP INDEX IF EXISTS public.ix_learning_decision_events_created_at;
DROP INDEX IF EXISTS public.ix_indicator_computation_cache_timeframe;
DROP INDEX IF EXISTS public.ix_indicator_computation_cache_symbol;
DROP INDEX IF EXISTS public.ix_indicator_computation_cache_params_version;
DROP INDEX IF EXISTS public.ix_indicator_computation_cache_indicator_name;
DROP INDEX IF EXISTS public.ix_indicator_computation_cache_expires_at;
DROP INDEX IF EXISTS public.ix_indicator_computation_cache_cache_key;
DROP INDEX IF EXISTS public.ix_indicator_computation_cache_bar_close_time;
DROP INDEX IF EXISTS public.ix_family_outcome_memory_family;
DROP INDEX IF EXISTS public.ix_execution_state_transitions_state;
DROP INDEX IF EXISTS public.ix_execution_state_transitions_execution_event_id;
DROP INDEX IF EXISTS public.ix_execution_metrics_user_id;
DROP INDEX IF EXISTS public.ix_execution_metrics_order_id;
DROP INDEX IF EXISTS public.ix_execution_metrics_exchange_order_id;
DROP INDEX IF EXISTS public.ix_execution_lifecycle_events_user_id;
DROP INDEX IF EXISTS public.ix_execution_lifecycle_events_execution_metric_id;
DROP INDEX IF EXISTS public.ix_execution_intents_strategy_version_id;
DROP INDEX IF EXISTS public.ix_execution_intents_strategy_id;
DROP INDEX IF EXISTS public.ix_execution_intents_intent_hash;
DROP INDEX IF EXISTS public.ix_execution_intents_decision_hash;
DROP INDEX IF EXISTS public.ix_execution_intents_correlation_id;
DROP INDEX IF EXISTS public.ix_execution_intents_context_hash;
DROP INDEX IF EXISTS public.ix_execution_intents_account_id;
DROP INDEX IF EXISTS public.ix_execution_intent_events_intent_id;
DROP INDEX IF EXISTS public.ix_execution_intent_events_event_type;
DROP INDEX IF EXISTS public.ix_execution_events_bot_profile_id;
DROP INDEX IF EXISTS public.ix_execution_correction_events_user_id;
DROP INDEX IF EXISTS public.ix_execution_correction_events_execution_metric_id;
DROP INDEX IF EXISTS public.ix_exchange_registry_exchange_code;
DROP INDEX IF EXISTS public.ix_exchange_capabilities_exchange_code;
DROP INDEX IF EXISTS public.ix_decision_trace_hot_strategy_version_id;
DROP INDEX IF EXISTS public.ix_decision_trace_hot_decision_hash;
DROP INDEX IF EXISTS public.ix_decision_trace_hot_correlation_id;
DROP INDEX IF EXISTS public.ix_decision_trace_hot_context_hash;
DROP INDEX IF EXISTS public.ix_decision_trace_cold_strategy_version_id;
DROP INDEX IF EXISTS public.ix_decision_trace_cold_decision_hash;
DROP INDEX IF EXISTS public.ix_decision_trace_cold_correlation_id;
DROP INDEX IF EXISTS public.ix_decision_trace_cold_context_hash;
DROP INDEX IF EXISTS public.ix_canonical_strategy_registry_family;
DROP INDEX IF EXISTS public.ix_canonical_strategy_registry_enabled;
DROP INDEX IF EXISTS public.ix_bot_profiles_user_id;
DROP INDEX IF EXISTS public.ix_bot_profiles_is_deleted;
DROP INDEX IF EXISTS public.ix_auth_mfa_challenges_user_id;
DROP INDEX IF EXISTS public.ix_auth_mfa_challenges_expires_at;
DROP INDEX IF EXISTS public.ix_auth_mfa_challenges_challenge_token_hash;
DROP INDEX IF EXISTS public.ix_audit_logs_action;
DROP INDEX IF EXISTS public.ix_allowed_markets_exchange_code;
ALTER TABLE IF EXISTS ONLY public.weekly_report_archives DROP CONSTRAINT IF EXISTS weekly_report_archives_pkey;
ALTER TABLE IF EXISTS ONLY public.users DROP CONSTRAINT IF EXISTS users_pkey;
ALTER TABLE IF EXISTS ONLY public.users DROP CONSTRAINT IF EXISTS users_email_key;
ALTER TABLE IF EXISTS ONLY public.user_venue_assignments DROP CONSTRAINT IF EXISTS user_venue_assignments_pkey;
ALTER TABLE IF EXISTS ONLY public.user_signal_modes DROP CONSTRAINT IF EXISTS user_signal_modes_user_id_key;
ALTER TABLE IF EXISTS ONLY public.user_signal_modes DROP CONSTRAINT IF EXISTS user_signal_modes_pkey;
ALTER TABLE IF EXISTS ONLY public.user_scanner_symbol_selections DROP CONSTRAINT IF EXISTS user_scanner_symbol_selections_pkey;
ALTER TABLE IF EXISTS ONLY public.user_scanner_results DROP CONSTRAINT IF EXISTS user_scanner_results_pkey;
ALTER TABLE IF EXISTS ONLY public.user_scanner_automation_profiles DROP CONSTRAINT IF EXISTS user_scanner_automation_profiles_pkey;
ALTER TABLE IF EXISTS ONLY public.user_scanner_automation_configs DROP CONSTRAINT IF EXISTS user_scanner_automation_configs_user_id_key;
ALTER TABLE IF EXISTS ONLY public.user_scanner_automation_configs DROP CONSTRAINT IF EXISTS user_scanner_automation_configs_pkey;
ALTER TABLE IF EXISTS ONLY public.user_risk_settings DROP CONSTRAINT IF EXISTS user_risk_settings_user_id_key;
ALTER TABLE IF EXISTS ONLY public.user_risk_settings DROP CONSTRAINT IF EXISTS user_risk_settings_pkey;
ALTER TABLE IF EXISTS ONLY public.user_onboarding_profiles DROP CONSTRAINT IF EXISTS user_onboarding_profiles_pkey;
ALTER TABLE IF EXISTS ONLY public.user_mfa_preferences DROP CONSTRAINT IF EXISTS user_mfa_preferences_pkey;
ALTER TABLE IF EXISTS ONLY public.user_mfa_backup_codes DROP CONSTRAINT IF EXISTS user_mfa_backup_codes_pkey;
ALTER TABLE IF EXISTS ONLY public.user_learning_simulation_suggestions DROP CONSTRAINT IF EXISTS user_learning_simulation_suggestions_pkey;
ALTER TABLE IF EXISTS ONLY public.user_indicator_watchlist DROP CONSTRAINT IF EXISTS user_indicator_watchlist_pkey;
ALTER TABLE IF EXISTS ONLY public.user_indicator_saved_queries DROP CONSTRAINT IF EXISTS user_indicator_saved_queries_pkey;
ALTER TABLE IF EXISTS ONLY public.user_execution_intents DROP CONSTRAINT IF EXISTS user_execution_intents_pkey;
ALTER TABLE IF EXISTS ONLY public.user_execution_intents DROP CONSTRAINT IF EXISTS user_execution_intents_intent_token_key;
ALTER TABLE IF EXISTS ONLY public.user_exchange_settings DROP CONSTRAINT IF EXISTS user_exchange_settings_user_id_key;
ALTER TABLE IF EXISTS ONLY public.user_exchange_settings DROP CONSTRAINT IF EXISTS user_exchange_settings_pkey;
ALTER TABLE IF EXISTS ONLY public.user_exchange_connections DROP CONSTRAINT IF EXISTS user_exchange_connections_pkey;
ALTER TABLE IF EXISTS ONLY public.user_decision_traces DROP CONSTRAINT IF EXISTS user_decision_traces_pkey;
ALTER TABLE IF EXISTS ONLY public.user_scanner_symbol_selections DROP CONSTRAINT IF EXISTS uq_user_scanner_symbol_selection;
ALTER TABLE IF EXISTS ONLY public.user_indicator_watchlist DROP CONSTRAINT IF EXISTS uq_user_indicator_watchlist_symbol;
ALTER TABLE IF EXISTS ONLY public.strategy_versions DROP CONSTRAINT IF EXISTS uq_strategy_versions_strategy_version;
ALTER TABLE IF EXISTS ONLY public.indicator_computation_cache DROP CONSTRAINT IF EXISTS uq_indicator_computation_cache_key;
ALTER TABLE IF EXISTS ONLY public.universe_rollout_state DROP CONSTRAINT IF EXISTS universe_rollout_state_pkey;
ALTER TABLE IF EXISTS ONLY public.user_execution_intents DROP CONSTRAINT IF EXISTS unique_user_execution_intent_idempotency_key;
ALTER TABLE IF EXISTS ONLY public.execution_intents DROP CONSTRAINT IF EXISTS unique_intent;
ALTER TABLE IF EXISTS ONLY public.testnet_execution_logs DROP CONSTRAINT IF EXISTS testnet_execution_logs_pkey;
ALTER TABLE IF EXISTS ONLY public.test_table DROP CONSTRAINT IF EXISTS test_table_pkey;
ALTER TABLE IF EXISTS ONLY public.system_alerts DROP CONSTRAINT IF EXISTS system_alerts_pkey;
ALTER TABLE IF EXISTS ONLY public.symbol_selection_watchlists DROP CONSTRAINT IF EXISTS symbol_selection_watchlists_pkey;
ALTER TABLE IF EXISTS ONLY public.strategy_versions DROP CONSTRAINT IF EXISTS strategy_versions_pkey;
ALTER TABLE IF EXISTS ONLY public.strategy_templates DROP CONSTRAINT IF EXISTS strategy_templates_pkey;
ALTER TABLE IF EXISTS ONLY public.strategy_templates DROP CONSTRAINT IF EXISTS strategy_templates_name_key;
ALTER TABLE IF EXISTS ONLY public.strategy_regime_bindings DROP CONSTRAINT IF EXISTS strategy_regime_bindings_pkey;
ALTER TABLE IF EXISTS ONLY public.strategy_outcome_memory DROP CONSTRAINT IF EXISTS strategy_outcome_memory_pkey;
ALTER TABLE IF EXISTS ONLY public.strategy_observability_events DROP CONSTRAINT IF EXISTS strategy_observability_events_pkey;
ALTER TABLE IF EXISTS ONLY public.strategy_family_gates DROP CONSTRAINT IF EXISTS strategy_family_gates_pkey;
ALTER TABLE IF EXISTS ONLY public.strategy_definitions DROP CONSTRAINT IF EXISTS strategy_definitions_pkey;
ALTER TABLE IF EXISTS ONLY public.strategy_allocations DROP CONSTRAINT IF EXISTS strategy_allocations_pkey;
ALTER TABLE IF EXISTS ONLY public.state_rebuild_logs DROP CONSTRAINT IF EXISTS state_rebuild_logs_pkey;
ALTER TABLE IF EXISTS ONLY public.signal_events DROP CONSTRAINT IF EXISTS signal_events_pkey;
ALTER TABLE IF EXISTS ONLY public.scanner_performance_snapshots DROP CONSTRAINT IF EXISTS scanner_performance_snapshots_pkey;
ALTER TABLE IF EXISTS ONLY public.scanner_fallback_events DROP CONSTRAINT IF EXISTS scanner_fallback_events_pkey;
ALTER TABLE IF EXISTS ONLY public.runtime_scan_candidates DROP CONSTRAINT IF EXISTS runtime_scan_candidates_pkey;
ALTER TABLE IF EXISTS ONLY public.risk_policy_audit_events DROP CONSTRAINT IF EXISTS risk_policy_audit_events_pkey;
ALTER TABLE IF EXISTS ONLY public.risk_policies DROP CONSTRAINT IF EXISTS risk_policies_pkey;
ALTER TABLE IF EXISTS ONLY public.risk_orchestrator_policies DROP CONSTRAINT IF EXISTS risk_orchestrator_policies_pkey;
ALTER TABLE IF EXISTS ONLY public.risk_exposure_groups DROP CONSTRAINT IF EXISTS risk_exposure_groups_pkey;
ALTER TABLE IF EXISTS ONLY public.risk_exposure_groups DROP CONSTRAINT IF EXISTS risk_exposure_groups_name_key;
ALTER TABLE IF EXISTS ONLY public.risk_clusters DROP CONSTRAINT IF EXISTS risk_clusters_pkey;
ALTER TABLE IF EXISTS ONLY public.replay_runs DROP CONSTRAINT IF EXISTS replay_runs_pkey;
ALTER TABLE IF EXISTS ONLY public.replay_executions DROP CONSTRAINT IF EXISTS replay_executions_pkey;
ALTER TABLE IF EXISTS ONLY public.replay_equity_points DROP CONSTRAINT IF EXISTS replay_equity_points_pkey;
ALTER TABLE IF EXISTS ONLY public.release_gate_overrides DROP CONSTRAINT IF EXISTS release_gate_overrides_pkey;
ALTER TABLE IF EXISTS ONLY public.regime_snapshots DROP CONSTRAINT IF EXISTS regime_snapshots_pkey;
ALTER TABLE IF EXISTS ONLY public.positions DROP CONSTRAINT IF EXISTS positions_pkey;
ALTER TABLE IF EXISTS ONLY public.position_ledger_events DROP CONSTRAINT IF EXISTS position_ledger_events_pkey;
ALTER TABLE IF EXISTS ONLY public.portfolio_exposure_snapshot DROP CONSTRAINT IF EXISTS portfolio_exposure_snapshot_pkey;
ALTER TABLE IF EXISTS ONLY public.permission_drift_events DROP CONSTRAINT IF EXISTS permission_drift_events_pkey;
ALTER TABLE IF EXISTS ONLY public.pending_signals DROP CONSTRAINT IF EXISTS pending_signals_pkey;
ALTER TABLE IF EXISTS ONLY public.paper_positions DROP CONSTRAINT IF EXISTS paper_positions_pkey;
ALTER TABLE IF EXISTS ONLY public.manual_override_log DROP CONSTRAINT IF EXISTS manual_override_log_pkey;
ALTER TABLE IF EXISTS ONLY public.live_activation_config DROP CONSTRAINT IF EXISTS live_activation_config_pkey;
ALTER TABLE IF EXISTS ONLY public.learning_recommendations DROP CONSTRAINT IF EXISTS learning_recommendations_pkey;
ALTER TABLE IF EXISTS ONLY public.learning_decision_events DROP CONSTRAINT IF EXISTS learning_decision_events_scanner_result_id_key;
ALTER TABLE IF EXISTS ONLY public.learning_decision_events DROP CONSTRAINT IF EXISTS learning_decision_events_pkey;
ALTER TABLE IF EXISTS ONLY public.learning_decision_events DROP CONSTRAINT IF EXISTS learning_decision_events_pending_signal_id_key;
ALTER TABLE IF EXISTS ONLY public.indicator_computation_cache DROP CONSTRAINT IF EXISTS indicator_computation_cache_pkey;
ALTER TABLE IF EXISTS ONLY public.hardening_checklist_runs DROP CONSTRAINT IF EXISTS hardening_checklist_runs_pkey;
ALTER TABLE IF EXISTS ONLY public.family_outcome_memory DROP CONSTRAINT IF EXISTS family_outcome_memory_pkey;
ALTER TABLE IF EXISTS ONLY public.failed_events DROP CONSTRAINT IF EXISTS failed_events_pkey;
ALTER TABLE IF EXISTS ONLY public.external_provider_credentials DROP CONSTRAINT IF EXISTS external_provider_credentials_pkey;
ALTER TABLE IF EXISTS ONLY public.execution_state_transitions DROP CONSTRAINT IF EXISTS execution_state_transitions_pkey;
ALTER TABLE IF EXISTS ONLY public.execution_policies DROP CONSTRAINT IF EXISTS execution_policies_strategy_type_key;
ALTER TABLE IF EXISTS ONLY public.execution_policies DROP CONSTRAINT IF EXISTS execution_policies_pkey;
ALTER TABLE IF EXISTS ONLY public.execution_metrics DROP CONSTRAINT IF EXISTS execution_metrics_pkey;
ALTER TABLE IF EXISTS ONLY public.execution_lifecycle_events DROP CONSTRAINT IF EXISTS execution_lifecycle_events_pkey;
ALTER TABLE IF EXISTS ONLY public.execution_intents DROP CONSTRAINT IF EXISTS execution_intents_pkey;
ALTER TABLE IF EXISTS ONLY public.execution_intents DROP CONSTRAINT IF EXISTS execution_intents_intent_hash_key;
ALTER TABLE IF EXISTS ONLY public.execution_intent_events DROP CONSTRAINT IF EXISTS execution_intent_events_pkey;
ALTER TABLE IF EXISTS ONLY public.execution_events DROP CONSTRAINT IF EXISTS execution_events_pkey;
ALTER TABLE IF EXISTS ONLY public.execution_correction_events DROP CONSTRAINT IF EXISTS execution_correction_events_pkey;
ALTER TABLE IF EXISTS ONLY public.exchange_registry DROP CONSTRAINT IF EXISTS exchange_registry_pkey;
ALTER TABLE IF EXISTS ONLY public.exchange_registry DROP CONSTRAINT IF EXISTS exchange_registry_exchange_code_key;
ALTER TABLE IF EXISTS ONLY public.exchange_capabilities DROP CONSTRAINT IF EXISTS exchange_capabilities_pkey;
ALTER TABLE IF EXISTS ONLY public.decision_trace_hot DROP CONSTRAINT IF EXISTS decision_trace_hot_pkey;
ALTER TABLE IF EXISTS ONLY public.decision_trace_cold DROP CONSTRAINT IF EXISTS decision_trace_cold_pkey;
ALTER TABLE IF EXISTS ONLY public.canonical_strategy_registry DROP CONSTRAINT IF EXISTS canonical_strategy_registry_pkey;
ALTER TABLE IF EXISTS ONLY public.brand_settings DROP CONSTRAINT IF EXISTS brand_settings_pkey;
ALTER TABLE IF EXISTS ONLY public.bot_profiles DROP CONSTRAINT IF EXISTS bot_profiles_pkey;
ALTER TABLE IF EXISTS ONLY public.backtest_result_cards DROP CONSTRAINT IF EXISTS backtest_result_cards_pkey;
ALTER TABLE IF EXISTS ONLY public.auth_mfa_challenges DROP CONSTRAINT IF EXISTS auth_mfa_challenges_pkey;
ALTER TABLE IF EXISTS ONLY public.audit_logs DROP CONSTRAINT IF EXISTS audit_logs_pkey;
ALTER TABLE IF EXISTS ONLY public.allowed_markets DROP CONSTRAINT IF EXISTS allowed_markets_pkey;
ALTER TABLE IF EXISTS ONLY public.alert_policies DROP CONSTRAINT IF EXISTS alert_policies_pkey;
ALTER TABLE IF EXISTS ONLY public.alert_channel_configs DROP CONSTRAINT IF EXISTS alert_channel_configs_pkey;
ALTER TABLE IF EXISTS ONLY public.alembic_version DROP CONSTRAINT IF EXISTS alembic_version_pkc;
ALTER TABLE IF EXISTS ONLY public.admin_control DROP CONSTRAINT IF EXISTS admin_control_pkey;
ALTER TABLE IF EXISTS public.test_table ALTER COLUMN id DROP DEFAULT;
DROP TABLE IF EXISTS public.weekly_report_archives;
DROP TABLE IF EXISTS public.users;
DROP TABLE IF EXISTS public.user_venue_assignments;
DROP TABLE IF EXISTS public.user_signal_modes;
DROP TABLE IF EXISTS public.user_scanner_symbol_selections;
DROP TABLE IF EXISTS public.user_scanner_results;
DROP TABLE IF EXISTS public.user_scanner_automation_profiles;
DROP TABLE IF EXISTS public.user_scanner_automation_configs;
DROP TABLE IF EXISTS public.user_risk_settings;
DROP TABLE IF EXISTS public.user_onboarding_profiles;
DROP TABLE IF EXISTS public.user_mfa_preferences;
DROP TABLE IF EXISTS public.user_mfa_backup_codes;
DROP TABLE IF EXISTS public.user_learning_simulation_suggestions;
DROP TABLE IF EXISTS public.user_indicator_watchlist;
DROP TABLE IF EXISTS public.user_indicator_saved_queries;
DROP TABLE IF EXISTS public.user_execution_intents;
DROP TABLE IF EXISTS public.user_exchange_settings;
DROP TABLE IF EXISTS public.user_exchange_connections;
DROP TABLE IF EXISTS public.user_decision_traces;
DROP TABLE IF EXISTS public.universe_rollout_state;
DROP TABLE IF EXISTS public.testnet_execution_logs;
DROP SEQUENCE IF EXISTS public.test_table_id_seq;
DROP TABLE IF EXISTS public.test_table;
DROP TABLE IF EXISTS public.system_alerts;
DROP TABLE IF EXISTS public.symbol_selection_watchlists;
DROP TABLE IF EXISTS public.strategy_versions;
DROP TABLE IF EXISTS public.strategy_templates;
DROP TABLE IF EXISTS public.strategy_regime_bindings;
DROP TABLE IF EXISTS public.strategy_outcome_memory;
DROP TABLE IF EXISTS public.strategy_observability_events;
DROP TABLE IF EXISTS public.strategy_family_gates;
DROP TABLE IF EXISTS public.strategy_definitions;
DROP TABLE IF EXISTS public.strategy_allocations;
DROP TABLE IF EXISTS public.state_rebuild_logs;
DROP TABLE IF EXISTS public.signal_events;
DROP TABLE IF EXISTS public.scanner_performance_snapshots;
DROP TABLE IF EXISTS public.scanner_fallback_events;
DROP TABLE IF EXISTS public.runtime_scan_candidates;
DROP TABLE IF EXISTS public.risk_policy_audit_events;
DROP TABLE IF EXISTS public.risk_policies;
DROP TABLE IF EXISTS public.risk_orchestrator_policies;
DROP TABLE IF EXISTS public.risk_exposure_groups;
DROP TABLE IF EXISTS public.risk_clusters;
DROP TABLE IF EXISTS public.replay_runs;
DROP TABLE IF EXISTS public.replay_executions;
DROP TABLE IF EXISTS public.replay_equity_points;
DROP TABLE IF EXISTS public.release_gate_overrides;
DROP TABLE IF EXISTS public.regime_snapshots;
DROP TABLE IF EXISTS public.positions;
DROP TABLE IF EXISTS public.position_ledger_events;
DROP TABLE IF EXISTS public.portfolio_exposure_snapshot;
DROP TABLE IF EXISTS public.permission_drift_events;
DROP TABLE IF EXISTS public.pending_signals;
DROP TABLE IF EXISTS public.paper_positions;
DROP TABLE IF EXISTS public.manual_override_log;
DROP TABLE IF EXISTS public.live_activation_config;
DROP TABLE IF EXISTS public.learning_recommendations;
DROP TABLE IF EXISTS public.learning_decision_events;
DROP TABLE IF EXISTS public.indicator_computation_cache;
DROP TABLE IF EXISTS public.hardening_checklist_runs;
DROP TABLE IF EXISTS public.family_outcome_memory;
DROP TABLE IF EXISTS public.failed_events;
DROP TABLE IF EXISTS public.external_provider_credentials;
DROP TABLE IF EXISTS public.execution_state_transitions;
DROP TABLE IF EXISTS public.execution_policies;
DROP TABLE IF EXISTS public.execution_metrics;
DROP TABLE IF EXISTS public.execution_lifecycle_events;
DROP TABLE IF EXISTS public.execution_intents;
DROP TABLE IF EXISTS public.execution_intent_events;
DROP TABLE IF EXISTS public.execution_events;
DROP TABLE IF EXISTS public.execution_correction_events;
DROP TABLE IF EXISTS public.exchange_registry;
DROP TABLE IF EXISTS public.exchange_capabilities;
DROP TABLE IF EXISTS public.decision_trace_hot;
DROP TABLE IF EXISTS public.decision_trace_cold;
DROP TABLE IF EXISTS public.canonical_strategy_registry;
DROP TABLE IF EXISTS public.brand_settings;
DROP TABLE IF EXISTS public.bot_profiles;
DROP TABLE IF EXISTS public.backtest_result_cards;
DROP TABLE IF EXISTS public.auth_mfa_challenges;
DROP TABLE IF EXISTS public.audit_logs;
DROP TABLE IF EXISTS public.allowed_markets;
DROP TABLE IF EXISTS public.alert_policies;
DROP TABLE IF EXISTS public.alert_channel_configs;
DROP TABLE IF EXISTS public.alembic_version;
DROP TABLE IF EXISTS public.admin_control;
DROP TYPE IF EXISTS public.userrole;
-- *not* dropping schema, since initdb creates it
--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

-- *not* creating schema, since initdb creates it


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS '';


--
-- Name: userrole; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.userrole AS ENUM (
    'SUPER_ADMIN',
    'ADMIN',
    'OPS',
    'USER'
);


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: admin_control; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.admin_control (
    id character varying NOT NULL,
    max_leverage_cap integer NOT NULL,
    max_open_positions_cap integer NOT NULL,
    minimum_volume_usd double precision NOT NULL,
    max_spread_bps integer NOT NULL,
    spot_universe json NOT NULL,
    futures_universe json NOT NULL,
    whitelist json NOT NULL,
    blacklist json NOT NULL,
    emergency_mode boolean NOT NULL,
    disable_futures boolean NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: alert_channel_configs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alert_channel_configs (
    id character varying NOT NULL,
    resend_api_key_encrypted text DEFAULT ''::text NOT NULL,
    alert_from character varying(255) DEFAULT ''::character varying NOT NULL,
    alert_to text DEFAULT ''::text NOT NULL,
    slack_webhook_url_encrypted text DEFAULT ''::text NOT NULL,
    updated_at timestamp with time zone
);


--
-- Name: alert_policies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alert_policies (
    id character varying NOT NULL,
    admin_notification_enabled boolean NOT NULL,
    ops_webhook_url text NOT NULL,
    monitoring_alert_log_enabled boolean NOT NULL,
    execution_quality_warning_threshold double precision NOT NULL,
    execution_quality_critical_threshold double precision NOT NULL,
    permission_drift_warning_per_day integer NOT NULL,
    permission_drift_critical_per_day integer NOT NULL,
    gate_override_warning_per_day integer NOT NULL,
    gate_override_critical_per_day integer NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: allowed_markets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.allowed_markets (
    id character varying NOT NULL,
    exchange_code character varying(40) NOT NULL,
    market_type character varying(20) NOT NULL,
    environment character varying(20) NOT NULL,
    enabled boolean NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: audit_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_logs (
    id character varying NOT NULL,
    actor_user_id character varying,
    actor_role character varying(20) NOT NULL,
    action character varying(120) NOT NULL,
    entity_type character varying(50) NOT NULL,
    entity_id character varying(120) NOT NULL,
    severity character varying(20) NOT NULL,
    details json NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: auth_mfa_challenges; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.auth_mfa_challenges (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    challenge_token_hash character varying(128) NOT NULL,
    allowed_methods json NOT NULL,
    email_otp_hash character varying(128),
    email_delivery_status character varying(20) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    consumed_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: backtest_result_cards; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.backtest_result_cards (
    id character varying NOT NULL,
    strategy_type character varying(50) NOT NULL,
    market_type character varying(20) NOT NULL,
    timeframe character varying(10) NOT NULL,
    sample_size integer NOT NULL,
    win_rate double precision NOT NULL,
    max_drawdown double precision NOT NULL,
    profit_factor double precision NOT NULL,
    sharpe_like_score double precision NOT NULL,
    performance_summary text NOT NULL,
    risk_label character varying(20) NOT NULL,
    period_start character varying(30) NOT NULL,
    period_end character varying(30) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: bot_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bot_profiles (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    name character varying(120) NOT NULL,
    exchange character varying(50) NOT NULL,
    market_type character varying(20) NOT NULL,
    symbols json NOT NULL,
    strategy_type character varying(50) NOT NULL,
    timeframe character varying(10) NOT NULL,
    trend_timeframe character varying(10) NOT NULL,
    leverage integer NOT NULL,
    is_enabled boolean NOT NULL,
    is_running boolean NOT NULL,
    is_deleted boolean NOT NULL,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: brand_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.brand_settings (
    id character varying NOT NULL,
    app_name character varying(120) NOT NULL,
    logo_filename character varying(255),
    logo_mime_type character varying(80),
    logo_blob bytea,
    logo_storage_note text NOT NULL,
    metadata_json json NOT NULL,
    updated_by_user_id character varying,
    updated_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: canonical_strategy_registry; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.canonical_strategy_registry (
    strategy_id character varying(120) NOT NULL,
    strategy_family character varying(60) NOT NULL,
    direction character varying(10) DEFAULT 'both'::character varying NOT NULL,
    market_regime character varying(40) DEFAULT 'any'::character varying NOT NULL,
    entry_logic_version character varying(40) DEFAULT 'v1'::character varying NOT NULL,
    exit_logic_version character varying(40) DEFAULT 'v1'::character varying NOT NULL,
    risk_profile character varying(40) DEFAULT 'balanced'::character varying NOT NULL,
    is_enabled boolean DEFAULT false NOT NULL,
    priority integer DEFAULT 100 NOT NULL,
    cooldown_policy character varying(80) DEFAULT 'symbol:180s'::character varying NOT NULL,
    weight double precision DEFAULT '1'::double precision NOT NULL,
    entry_long json DEFAULT '{}'::json NOT NULL,
    entry_short json DEFAULT '{}'::json NOT NULL,
    exit_long json DEFAULT '{}'::json NOT NULL,
    exit_short json DEFAULT '{}'::json NOT NULL,
    invalid_state_rules json DEFAULT '[]'::json NOT NULL,
    cooldown_rules json DEFAULT '{}'::json NOT NULL,
    risk_rules json DEFAULT '{}'::json NOT NULL,
    is_legacy_candidate boolean DEFAULT false NOT NULL,
    in_production_path boolean DEFAULT true NOT NULL,
    last_50_signal_quality double precision DEFAULT '0'::double precision NOT NULL,
    false_allow_rate double precision DEFAULT '0'::double precision NOT NULL,
    false_reject_rate double precision DEFAULT '0'::double precision NOT NULL,
    cooldown_state character varying(20) DEFAULT 'ready'::character varying NOT NULL,
    risk_block_reason character varying(120),
    forced_disable_reason character varying(200),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    stop_loss json DEFAULT '{}'::json NOT NULL,
    take_profit json DEFAULT '{}'::json NOT NULL,
    invalidation json DEFAULT '{}'::json NOT NULL,
    signal_score json DEFAULT '{}'::json NOT NULL
);


--
-- Name: decision_trace_cold; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.decision_trace_cold (
    archive_id character varying NOT NULL,
    correlation_id character varying(120) NOT NULL,
    strategy_version_id character varying NOT NULL,
    context_hash character varying(128) NOT NULL,
    decision_hash character varying(128) NOT NULL,
    intent_hash character varying(128),
    artifact_id character varying(80),
    lifecycle_summary json NOT NULL,
    terminal_state character varying(30) NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: decision_trace_hot; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.decision_trace_hot (
    trace_id character varying NOT NULL,
    correlation_id character varying(120) NOT NULL,
    strategy_version_id character varying NOT NULL,
    context_hash character varying(128) NOT NULL,
    decision_hash character varying(128) NOT NULL,
    intent_hash character varying(128),
    context_payload json NOT NULL,
    decision_payload json NOT NULL,
    intent_payload json NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: exchange_capabilities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.exchange_capabilities (
    id character varying NOT NULL,
    exchange_code character varying(40) NOT NULL,
    market_type character varying(20) NOT NULL,
    supports_spot boolean NOT NULL,
    supports_futures boolean NOT NULL,
    supports_test_order boolean NOT NULL,
    supports_quote_qty boolean NOT NULL,
    supports_reduce_only boolean NOT NULL,
    supports_leverage boolean NOT NULL,
    supports_margin_mode boolean NOT NULL,
    supports_hedge_mode boolean NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: exchange_registry; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.exchange_registry (
    id character varying NOT NULL,
    exchange_code character varying(40) NOT NULL,
    exchange_name character varying(120) NOT NULL,
    status character varying(20) NOT NULL,
    supported_market_types json NOT NULL,
    supports_testnet boolean NOT NULL,
    supports_live boolean NOT NULL,
    health_status character varying(20) NOT NULL,
    rate_limit_status character varying(20) NOT NULL,
    adapter_version character varying(40) NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: execution_correction_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.execution_correction_events (
    id character varying NOT NULL,
    execution_metric_id character varying NOT NULL,
    user_id character varying NOT NULL,
    correction_type character varying(40) DEFAULT 'annotation'::character varying NOT NULL,
    reason_code character varying(40) DEFAULT 'manual_correction'::character varying NOT NULL,
    note text DEFAULT ''::text NOT NULL,
    patch_payload json NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: execution_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.execution_events (
    id character varying NOT NULL,
    bot_profile_id character varying NOT NULL,
    exchange character varying(50) NOT NULL,
    symbol character varying(30) NOT NULL,
    side character varying(10) NOT NULL,
    quantity double precision NOT NULL,
    mock_price double precision NOT NULL,
    execution_status character varying(30) NOT NULL,
    response_payload json NOT NULL,
    note text NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: execution_intent_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.execution_intent_events (
    id character varying NOT NULL,
    intent_id character varying NOT NULL,
    event_type character varying(60) NOT NULL,
    event_status character varying(20) NOT NULL,
    external_order_id character varying(80),
    payload json NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: execution_intents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.execution_intents (
    intent_id character varying NOT NULL,
    strategy_id character varying NOT NULL,
    strategy_version_id character varying NOT NULL,
    symbol character varying(20) NOT NULL,
    side character varying(20) NOT NULL,
    order_type character varying(20) NOT NULL,
    quantity double precision NOT NULL,
    price_reference json NOT NULL,
    decision_hash character varying(128) NOT NULL,
    context_hash character varying(128) NOT NULL,
    intent_hash character varying(128) NOT NULL,
    correlation_id character varying(120) NOT NULL,
    status character varying(20) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    account_id character varying(120)
);


--
-- Name: execution_lifecycle_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.execution_lifecycle_events (
    id character varying NOT NULL,
    execution_metric_id character varying NOT NULL,
    user_id character varying NOT NULL,
    event_name character varying(40) NOT NULL,
    event_timestamp timestamp with time zone NOT NULL,
    payload json NOT NULL
);


--
-- Name: execution_metrics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.execution_metrics (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    symbol character varying(20) NOT NULL,
    order_id character varying(80) NOT NULL,
    exchange_order_id character varying(80) NOT NULL,
    order_type character varying(20) NOT NULL,
    side character varying(10) NOT NULL,
    quote_qty double precision NOT NULL,
    mid_price double precision NOT NULL,
    mid_price_timestamp character varying(40) NOT NULL,
    price_avg double precision,
    executed_qty double precision,
    slippage_pct double precision,
    execution_time_ms double precision,
    status character varying(30) NOT NULL,
    strategy_type character varying(50) NOT NULL,
    volatility_regime character varying(20) NOT NULL,
    volatility_pct double precision NOT NULL,
    execution_quality_score double precision NOT NULL,
    state_machine_path json NOT NULL,
    created_at timestamp with time zone NOT NULL,
    client_order_id character varying(120) DEFAULT ''::character varying NOT NULL,
    final_status character varying(30) DEFAULT 'NEW'::character varying NOT NULL,
    failure_code character varying(40),
    submitted_at timestamp with time zone,
    ack_at timestamp with time zone,
    final_at timestamp with time zone,
    validation_snapshot_id character varying(120),
    raw_exchange_status json NOT NULL,
    exchange character varying(30) DEFAULT 'binance'::character varying NOT NULL,
    market_type character varying(20) DEFAULT 'futures'::character varying NOT NULL,
    environment character varying(20) DEFAULT 'testnet'::character varying NOT NULL
);


--
-- Name: execution_policies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.execution_policies (
    id character varying NOT NULL,
    strategy_type character varying(50) NOT NULL,
    execution_style character varying(20) NOT NULL,
    order_preference character varying(20) NOT NULL,
    timeout_seconds integer NOT NULL,
    fallback_behavior character varying(30) NOT NULL,
    partial_fill_tolerance_pct double precision NOT NULL,
    execution_urgency character varying(20) NOT NULL,
    retry_limit integer NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: execution_state_transitions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.execution_state_transitions (
    id character varying NOT NULL,
    execution_event_id character varying NOT NULL,
    state character varying(30) NOT NULL,
    sequence integer NOT NULL,
    details json NOT NULL,
    occurred_at timestamp with time zone NOT NULL
);


--
-- Name: external_provider_credentials; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.external_provider_credentials (
    provider character varying(80) NOT NULL,
    api_key_encrypted text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: failed_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.failed_events (
    id character varying NOT NULL,
    event_type character varying(50) NOT NULL,
    entity_type character varying(50) NOT NULL,
    entity_id character varying(120) NOT NULL,
    payload json NOT NULL,
    error_message text NOT NULL,
    status character varying(20) NOT NULL,
    retry_count integer NOT NULL,
    max_retry integer NOT NULL,
    next_retry_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    resolved_at timestamp with time zone
);


--
-- Name: family_outcome_memory; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.family_outcome_memory (
    id character varying NOT NULL,
    family character varying(30) NOT NULL,
    regime character varying(30) DEFAULT 'any'::character varying NOT NULL,
    sample_count integer DEFAULT 0 NOT NULL,
    hit_rate double precision DEFAULT '0'::double precision NOT NULL,
    avg_return double precision DEFAULT '0'::double precision NOT NULL,
    volatility_success double precision DEFAULT '0'::double precision NOT NULL,
    conflict_success double precision DEFAULT '0'::double precision NOT NULL,
    solo_vs_combo_success json DEFAULT '{}'::json NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: hardening_checklist_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hardening_checklist_runs (
    id character varying NOT NULL,
    score double precision NOT NULL,
    critical_blocked boolean NOT NULL,
    readiness_status character varying(20) NOT NULL,
    checklist_items json NOT NULL,
    summary json NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: indicator_computation_cache; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.indicator_computation_cache (
    id character varying NOT NULL,
    cache_key character varying(280) NOT NULL,
    symbol character varying(30) NOT NULL,
    timeframe character varying(12) NOT NULL,
    bar_close_time character varying(64) NOT NULL,
    indicator_name character varying(80) NOT NULL,
    params_version character varying(40) NOT NULL,
    payload json NOT NULL,
    expires_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: learning_decision_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.learning_decision_events (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    symbol character varying(30) NOT NULL,
    decision character varying(20) DEFAULT 'NO_TRADE'::character varying NOT NULL,
    source_strategies json DEFAULT '[]'::json NOT NULL,
    family_scores json DEFAULT '{}'::json NOT NULL,
    regime_snapshot json DEFAULT '{}'::json NOT NULL,
    risk_snapshot json DEFAULT '{}'::json NOT NULL,
    entry_price double precision,
    exit_price double precision,
    max_favorable_excursion double precision DEFAULT '0'::double precision NOT NULL,
    max_adverse_excursion double precision DEFAULT '0'::double precision NOT NULL,
    hold_duration_minutes double precision DEFAULT '0'::double precision NOT NULL,
    outcome_label character varying(20) DEFAULT 'OPEN'::character varying NOT NULL,
    pnl_normalized double precision DEFAULT '0'::double precision NOT NULL,
    stop_hit boolean DEFAULT false NOT NULL,
    tp_hit boolean DEFAULT false NOT NULL,
    timed_exit boolean DEFAULT false NOT NULL,
    invalidated boolean DEFAULT false NOT NULL,
    strategy_id character varying(120),
    strategy_family character varying(40),
    scanner_result_id character varying,
    pending_signal_id character varying,
    position_id character varying,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    closed_at timestamp with time zone
);


--
-- Name: learning_recommendations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.learning_recommendations (
    id character varying NOT NULL,
    strategy_id character varying(120),
    family character varying(30),
    recommendation_type character varying(30) NOT NULL,
    recommendation_value json DEFAULT '{}'::json NOT NULL,
    note character varying(280) DEFAULT ''::character varying NOT NULL,
    severity character varying(20) DEFAULT 'medium'::character varying NOT NULL,
    is_applied boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    applied_at timestamp with time zone
);


--
-- Name: live_activation_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.live_activation_config (
    id character varying NOT NULL,
    exchange character varying(30) NOT NULL,
    market_type character varying(20) NOT NULL,
    safe_mode_enabled boolean NOT NULL,
    live_mode_enabled boolean NOT NULL,
    symbol_whitelist json NOT NULL,
    max_position_pct double precision NOT NULL,
    leverage_cap integer NOT NULL,
    max_trades_per_hour integer NOT NULL,
    max_notional_exposure double precision NOT NULL,
    kill_switch_enabled boolean NOT NULL,
    disable_futures boolean NOT NULL,
    ip_whitelist_ready boolean NOT NULL,
    trading_permission_ready boolean NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: manual_override_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.manual_override_log (
    override_id character varying(120) NOT NULL,
    admin_id character varying NOT NULL,
    action_type character varying(80) NOT NULL,
    reason text DEFAULT ''::text NOT NULL,
    payload json NOT NULL,
    "timestamp" timestamp with time zone
);


--
-- Name: paper_positions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.paper_positions (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    bot_profile_id character varying NOT NULL,
    symbol character varying(30) NOT NULL,
    market_type character varying(20) NOT NULL,
    side character varying(10) NOT NULL,
    quantity double precision NOT NULL,
    leverage integer NOT NULL,
    entry_price double precision NOT NULL,
    stop_loss double precision NOT NULL,
    take_profit double precision NOT NULL,
    status character varying(20) NOT NULL,
    unrealized_pnl double precision NOT NULL,
    realized_pnl double precision NOT NULL,
    opened_at timestamp with time zone NOT NULL,
    closed_at timestamp with time zone,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: pending_signals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pending_signals (
    id character varying NOT NULL,
    signal_id character varying NOT NULL,
    user_id character varying NOT NULL,
    symbol character varying(30) NOT NULL,
    strategy_code character varying(80) NOT NULL,
    confidence double precision DEFAULT '0'::double precision NOT NULL,
    mode character varying(20) DEFAULT 'ASSISTED'::character varying NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    order_position_id character varying,
    created_at timestamp with time zone,
    decided_at timestamp with time zone,
    decision_note text DEFAULT ''::text NOT NULL,
    strategy_weight double precision DEFAULT '1'::double precision NOT NULL,
    allocation_source character varying(40) DEFAULT 'default_allocation'::character varying NOT NULL,
    meta_engine_decision character varying(30) DEFAULT 'ALLOW'::character varying NOT NULL,
    previous_state character varying(40) DEFAULT 'DETECTED'::character varying NOT NULL,
    current_state character varying(40) DEFAULT 'DETECTED'::character varying NOT NULL,
    blocked_reason_code character varying(60) DEFAULT ''::character varying NOT NULL,
    blocked_reason_message character varying(220) DEFAULT ''::character varying NOT NULL,
    blocked_solution_hint character varying(240) DEFAULT ''::character varying NOT NULL,
    requires_manual_approval boolean DEFAULT true NOT NULL,
    execution_eligible boolean DEFAULT false NOT NULL,
    bot_profile_id character varying,
    risk_policy_id character varying,
    exchange_connection_id character varying,
    created_order_intent_id character varying,
    runtime_owner character varying(120) DEFAULT ''::character varying NOT NULL,
    last_eligibility_check_at timestamp with time zone,
    last_transition_at timestamp with time zone
);


--
-- Name: permission_drift_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.permission_drift_events (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    exchange character varying(30) NOT NULL,
    old_permissions json NOT NULL,
    new_permissions json NOT NULL,
    old_can_trade boolean,
    new_can_trade boolean,
    is_critical boolean NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: portfolio_exposure_snapshot; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.portfolio_exposure_snapshot (
    id character varying NOT NULL,
    "timestamp" timestamp with time zone,
    user_id character varying NOT NULL,
    symbol character varying(30) NOT NULL,
    position_size double precision DEFAULT '0'::double precision NOT NULL,
    notional double precision DEFAULT '0'::double precision NOT NULL,
    strategy_id character varying(80),
    cluster_id character varying(40),
    exposure_weight double precision DEFAULT '0'::double precision NOT NULL
);


--
-- Name: position_ledger_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.position_ledger_events (
    id character varying NOT NULL,
    position_id character varying NOT NULL,
    event_type character varying(30) NOT NULL,
    payload json NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: positions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.positions (
    position_id character varying(120) NOT NULL,
    user_id character varying NOT NULL,
    symbol character varying(30) NOT NULL,
    size double precision DEFAULT '0'::double precision NOT NULL,
    entry_price double precision DEFAULT '0'::double precision NOT NULL,
    current_price double precision DEFAULT '0'::double precision NOT NULL,
    unrealized_pnl double precision DEFAULT '0'::double precision NOT NULL,
    leverage integer DEFAULT 1 NOT NULL,
    strategy_id character varying(80),
    cluster_id character varying(40),
    status character varying(20) DEFAULT 'open'::character varying NOT NULL,
    created_at timestamp with time zone,
    updated_at timestamp with time zone
);


--
-- Name: regime_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.regime_snapshots (
    regime_snapshot_id character varying NOT NULL,
    timestamp_utc character varying(40) NOT NULL,
    symbol character varying(20) NOT NULL,
    timeframe character varying(10) NOT NULL,
    strategy_version_id character varying NOT NULL,
    volatility_regime character varying(40) NOT NULL,
    trend_regime character varying(40) NOT NULL,
    liquidity_regime character varying(40) NOT NULL,
    market_state_features json NOT NULL,
    feature_set_version character varying(30) NOT NULL,
    regime_score double precision NOT NULL,
    regime_label character varying(50) NOT NULL,
    regime_hash character varying(128) NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: release_gate_overrides; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.release_gate_overrides (
    id character varying NOT NULL,
    admin_user_id character varying NOT NULL,
    reason_code character varying(40) NOT NULL,
    reason_note text NOT NULL,
    release_gate_snapshot json NOT NULL,
    deploy_context json NOT NULL,
    created_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    last_used_at timestamp with time zone,
    used_deploy_count integer NOT NULL
);


--
-- Name: replay_equity_points; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.replay_equity_points (
    id character varying NOT NULL,
    replay_run_id character varying NOT NULL,
    user_id character varying NOT NULL,
    point_timestamp character varying(40) NOT NULL,
    equity double precision NOT NULL,
    pnl_delta double precision NOT NULL,
    drawdown_pct double precision NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: replay_executions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.replay_executions (
    id character varying NOT NULL,
    replay_run_id character varying NOT NULL,
    user_id character varying NOT NULL,
    symbol character varying(20) NOT NULL,
    timeframe character varying(10) NOT NULL,
    signal character varying(20) NOT NULL,
    direction character varying(10) NOT NULL,
    market_price double precision NOT NULL,
    simulated_fill_price double precision,
    simulated_latency_ms double precision,
    simulated_slippage_pct double precision,
    lifecycle json NOT NULL,
    status character varying(20) NOT NULL,
    risk_tags json NOT NULL,
    candle_timestamp character varying(40) NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: replay_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.replay_runs (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    exchange character varying(30) NOT NULL,
    market_type character varying(20) NOT NULL,
    environment character varying(20) NOT NULL,
    symbol character varying(20) NOT NULL,
    timeframe character varying(10) NOT NULL,
    strategy_type character varying(50) NOT NULL,
    candles_processed integer NOT NULL,
    executions_count integer NOT NULL,
    filled_count integer NOT NULL,
    canceled_count integer NOT NULL,
    avg_simulated_latency_ms double precision NOT NULL,
    avg_simulated_slippage_pct double precision NOT NULL,
    metrics json NOT NULL,
    status character varying(20) NOT NULL,
    started_at timestamp with time zone NOT NULL,
    completed_at timestamp with time zone
);


--
-- Name: risk_clusters; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.risk_clusters (
    cluster_id character varying(40) NOT NULL,
    symbols json NOT NULL,
    cluster_type character varying(60) DEFAULT 'custom'::character varying NOT NULL,
    correlation_score double precision DEFAULT '0'::double precision NOT NULL,
    risk_weight double precision DEFAULT '1'::double precision NOT NULL,
    created_at timestamp with time zone,
    updated_at timestamp with time zone
);


--
-- Name: risk_exposure_groups; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.risk_exposure_groups (
    id character varying NOT NULL,
    name character varying(40) NOT NULL,
    label character varying(120) NOT NULL,
    symbols json NOT NULL,
    max_group_open_positions integer NOT NULL,
    max_group_directional_positions integer NOT NULL,
    max_group_risk_pct double precision NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: risk_orchestrator_policies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.risk_orchestrator_policies (
    id character varying NOT NULL,
    reference_equity_usd double precision NOT NULL,
    account_max_notional_pct double precision NOT NULL,
    symbol_max_notional_pct double precision NOT NULL,
    strategy_max_concurrent_positions integer NOT NULL,
    strategy_cooldown_seconds integer NOT NULL,
    max_order_frequency_per_min integer NOT NULL,
    max_order_burst_per_10s integer NOT NULL,
    daily_loss_limit_pct double precision NOT NULL,
    duplicate_suppression_window_seconds integer NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: risk_policies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.risk_policies (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    name character varying(120) NOT NULL,
    position_size_pct double precision NOT NULL,
    atr_stop_multiplier double precision NOT NULL,
    risk_reward_ratio double precision NOT NULL,
    daily_loss_cutoff_pct double precision NOT NULL,
    max_open_positions integer NOT NULL,
    max_leverage integer NOT NULL,
    spread_limit_bps integer NOT NULL,
    slippage_limit_bps integer NOT NULL,
    min_liquidity_usdt integer NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: risk_policy_audit_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.risk_policy_audit_events (
    id character varying NOT NULL,
    replay_run_id character varying NOT NULL,
    user_id character varying NOT NULL,
    strategy_version character varying(120) NOT NULL,
    regime_bucket character varying(40) NOT NULL,
    drawdown double precision NOT NULL,
    exposure_breach integer NOT NULL,
    reject_count integer NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: runtime_scan_candidates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.runtime_scan_candidates (
    id character varying NOT NULL,
    symbol character varying(30) NOT NULL,
    market_type character varying(20) NOT NULL,
    scan_timestamp timestamp with time zone NOT NULL,
    strategy_signal character varying(20) DEFAULT 'PASS'::character varying NOT NULL,
    risk_score double precision DEFAULT '0'::double precision NOT NULL,
    decision character varying(10) DEFAULT 'PASS'::character varying NOT NULL,
    confidence double precision DEFAULT '0'::double precision NOT NULL
);


--
-- Name: scanner_fallback_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.scanner_fallback_events (
    id character varying NOT NULL,
    run_id character varying(120),
    event_type character varying(20) NOT NULL,
    requested_mode character varying(40) DEFAULT 'all_market_symbols'::character varying NOT NULL,
    effective_mode character varying(40) DEFAULT 'all_market_symbols'::character varying NOT NULL,
    trigger_metric character varying(80),
    threshold_breach json NOT NULL,
    exit_reason character varying(120),
    cycle_snapshot json NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: scanner_performance_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.scanner_performance_snapshots (
    id character varying NOT NULL,
    user_id character varying,
    run_id character varying(120),
    stage character varying(40) DEFAULT 'top_volume_subset'::character varying NOT NULL,
    metrics json NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: signal_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.signal_events (
    id character varying NOT NULL,
    bot_profile_id character varying NOT NULL,
    user_id character varying NOT NULL,
    symbol character varying(30) NOT NULL,
    market_type character varying(20) NOT NULL,
    timeframe character varying(10) NOT NULL,
    strategy_id character varying(50) NOT NULL,
    signal character varying(20) NOT NULL,
    direction character varying(10) NOT NULL,
    confidence double precision NOT NULL,
    reason_codes json NOT NULL,
    generated_at timestamp with time zone NOT NULL
);


--
-- Name: state_rebuild_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.state_rebuild_logs (
    id character varying NOT NULL,
    rebuild_type character varying(40) NOT NULL,
    status character varying(20) NOT NULL,
    trigger_source character varying(30) NOT NULL,
    details json NOT NULL,
    started_at timestamp with time zone NOT NULL,
    finished_at timestamp with time zone
);


--
-- Name: strategy_allocations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.strategy_allocations (
    strategy_id character varying(80) NOT NULL,
    capital_weight double precision DEFAULT '1'::double precision NOT NULL,
    max_capital double precision DEFAULT '10000'::double precision NOT NULL,
    current_capital double precision DEFAULT '0'::double precision NOT NULL,
    confidence_score double precision DEFAULT '0'::double precision NOT NULL,
    performance_score double precision DEFAULT '0'::double precision NOT NULL,
    state character varying(20) DEFAULT 'ACTIVE'::character varying NOT NULL,
    expected_return double precision DEFAULT '0'::double precision NOT NULL,
    realized_return double precision DEFAULT '0'::double precision NOT NULL,
    signal_decay double precision DEFAULT '0'::double precision NOT NULL,
    execution_quality_score double precision DEFAULT '0'::double precision NOT NULL,
    updated_at timestamp with time zone
);


--
-- Name: strategy_definitions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.strategy_definitions (
    strategy_id character varying NOT NULL,
    name character varying(120) NOT NULL,
    code character varying(80) NOT NULL,
    description text NOT NULL,
    owner_type character varying(20) NOT NULL,
    created_by character varying NOT NULL,
    status character varying(20) NOT NULL,
    active_version_id character varying,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: strategy_family_gates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.strategy_family_gates (
    family character varying(30) NOT NULL,
    is_enabled boolean DEFAULT true NOT NULL,
    long_threshold double precision DEFAULT '5'::double precision NOT NULL,
    short_threshold double precision DEFAULT '5'::double precision NOT NULL,
    min_strategy_count integer DEFAULT 1 NOT NULL,
    max_conflict_score double precision DEFAULT '2'::double precision NOT NULL,
    regime_match_required boolean DEFAULT true NOT NULL,
    risk_clear_required boolean DEFAULT true NOT NULL,
    reversal_extra_confirmation boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: strategy_observability_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.strategy_observability_events (
    id character varying NOT NULL,
    selection_cycle_id character varying(120) NOT NULL,
    audit_log_id character varying,
    bot_profile_id character varying,
    user_id character varying,
    symbol character varying(30) NOT NULL,
    strategy_id character varying(80) NOT NULL,
    strategy_name character varying(120) DEFAULT 'SPOT_TREND_PULLBACK'::character varying NOT NULL,
    event_type character varying(40) NOT NULL,
    market_regime character varying(30) DEFAULT 'RANGING'::character varying NOT NULL,
    multiplier_version character varying(20) DEFAULT 'v1'::character varying NOT NULL,
    multiplier_set json NOT NULL,
    base_score double precision DEFAULT '0'::double precision NOT NULL,
    adjusted_score double precision DEFAULT '0'::double precision NOT NULL,
    score_delta double precision DEFAULT '0'::double precision NOT NULL,
    selection_rank integer,
    trend_strength character varying(20),
    relative_volume double precision,
    hard_gate_pass boolean DEFAULT false NOT NULL,
    threshold_pass boolean DEFAULT false NOT NULL,
    rejection_reason character varying(120),
    metadata json NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: strategy_outcome_memory; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.strategy_outcome_memory (
    id character varying NOT NULL,
    strategy_id character varying(120) NOT NULL,
    direction character varying(10) DEFAULT 'both'::character varying NOT NULL,
    regime character varying(30) DEFAULT 'any'::character varying NOT NULL,
    sample_count integer DEFAULT 0 NOT NULL,
    hit_rate double precision DEFAULT '0'::double precision NOT NULL,
    avg_return double precision DEFAULT '0'::double precision NOT NULL,
    avg_mfe double precision DEFAULT '0'::double precision NOT NULL,
    avg_mae double precision DEFAULT '0'::double precision NOT NULL,
    false_allow_rate double precision DEFAULT '0'::double precision NOT NULL,
    false_reject_rate double precision DEFAULT '0'::double precision NOT NULL,
    recent_rolling_score double precision DEFAULT '0'::double precision NOT NULL,
    decay_adjusted_quality_score double precision DEFAULT '0'::double precision NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: strategy_regime_bindings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.strategy_regime_bindings (
    binding_id character varying NOT NULL,
    strategy_version_id character varying NOT NULL,
    allowed_regimes json NOT NULL,
    blocked_regimes json NOT NULL,
    priority integer NOT NULL,
    gating_policy_version character varying(30) NOT NULL,
    created_by character varying NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: strategy_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.strategy_templates (
    id character varying NOT NULL,
    name character varying(120) NOT NULL,
    strategy_type character varying(50) NOT NULL,
    parameters json NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_by character varying NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: strategy_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.strategy_versions (
    version_id character varying NOT NULL,
    strategy_id character varying NOT NULL,
    version_number integer NOT NULL,
    config_json json NOT NULL,
    config_schema_version character varying(30) NOT NULL,
    created_by character varying NOT NULL,
    created_at timestamp with time zone NOT NULL,
    version_hash character varying(128) NOT NULL
);


--
-- Name: symbol_selection_watchlists; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.symbol_selection_watchlists (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    name character varying(120) NOT NULL,
    source character varying(20) NOT NULL,
    exchange character varying(50) NOT NULL,
    market_type character varying(20) NOT NULL,
    symbols json NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: system_alerts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.system_alerts (
    id character varying NOT NULL,
    alert_type character varying(80) NOT NULL,
    severity character varying(20) NOT NULL,
    message text NOT NULL,
    details json NOT NULL,
    status character varying(20) NOT NULL,
    occurrences integer NOT NULL,
    last_triggered_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    fingerprint character varying(128),
    entity_key character varying(120),
    root_cause_code character varying(80),
    state_key character varying(120),
    delivery_status json DEFAULT '{}'::json NOT NULL
);


--
-- Name: test_table; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.test_table (
    id integer NOT NULL,
    marker text NOT NULL
);


--
-- Name: test_table_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.test_table_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: test_table_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.test_table_id_seq OWNED BY public.test_table.id;


--
-- Name: testnet_execution_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.testnet_execution_logs (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    symbol character varying(20) NOT NULL,
    strategy_direction character varying(10) NOT NULL,
    expected_price double precision NOT NULL,
    fill_price double precision,
    slippage double precision,
    execution_latency double precision,
    execution_quality_score double precision NOT NULL,
    status character varying(30) NOT NULL,
    state_machine_path json NOT NULL,
    permission_snapshot json NOT NULL,
    release_gate_status character varying(20) NOT NULL,
    details json NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: universe_rollout_state; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.universe_rollout_state (
    id character varying NOT NULL,
    current_stage character varying(40) DEFAULT 'full_market'::character varying NOT NULL,
    recommended_stage character varying(40),
    recommendation_payload json NOT NULL,
    requires_admin_approval boolean DEFAULT true NOT NULL,
    approved_by character varying,
    approved_at timestamp with time zone,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: user_decision_traces; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_decision_traces (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    trace_scope character varying(20) DEFAULT 'signal'::character varying NOT NULL,
    trace_type character varying(40) DEFAULT 'decision'::character varying NOT NULL,
    entity_id character varying(120) NOT NULL,
    strategy_code character varying(120),
    decision_status character varying(40) DEFAULT 'UNKNOWN'::character varying NOT NULL,
    reason_codes json NOT NULL,
    reason_details json NOT NULL,
    feature_snapshot json NOT NULL,
    context_payload json NOT NULL,
    created_at timestamp with time zone,
    expires_at timestamp with time zone,
    portfolio_risk_score double precision,
    strategy_allocation_reason character varying(120),
    cluster_risk_flag character varying(80),
    meta_engine_decision character varying(30),
    position_action_reason character varying(120),
    risk_adjustment_reason character varying(120),
    strategy_override_reason character varying(120),
    hedge_recommendation character varying(160),
    risk_reduction_score double precision,
    correlation_basis character varying(160)
);


--
-- Name: user_exchange_connections; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_exchange_connections (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    account_label character varying(80) DEFAULT 'default'::character varying NOT NULL,
    exchange character varying(30) DEFAULT 'binance'::character varying NOT NULL,
    market_type character varying(20) DEFAULT 'spot'::character varying NOT NULL,
    environment character varying(20) DEFAULT 'testnet'::character varying NOT NULL,
    is_default boolean DEFAULT false NOT NULL,
    readiness_snapshot json DEFAULT '{}'::json NOT NULL,
    permission_snapshot json DEFAULT '[]'::json NOT NULL,
    api_key_encrypted text DEFAULT ''::text NOT NULL,
    api_secret_encrypted text DEFAULT ''::text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: user_exchange_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_exchange_settings (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    exchange character varying(30) NOT NULL,
    mode character varying(20) NOT NULL,
    api_key_encrypted text NOT NULL,
    api_secret_encrypted text NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    permissions_snapshot json NOT NULL,
    can_trade_snapshot boolean,
    validation_checked_at timestamp with time zone,
    last_validation_success boolean,
    last_reason_codes json NOT NULL,
    validation_snapshot_id character varying(120)
);


--
-- Name: user_execution_intents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_execution_intents (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    source_type character varying(30) DEFAULT 'manual'::character varying NOT NULL,
    source_ref_id character varying(80),
    status character varying(30) DEFAULT 'PREVIEWED'::character varying NOT NULL,
    intent_token character varying(120) NOT NULL,
    preview_hash character varying(120) NOT NULL,
    queue_mode character varying(20) DEFAULT 'ASSISTED'::character varying NOT NULL,
    approval_required boolean DEFAULT true NOT NULL,
    symbol character varying(30) NOT NULL,
    market_type character varying(20) DEFAULT 'spot'::character varying NOT NULL,
    side character varying(10) DEFAULT 'buy'::character varying NOT NULL,
    notional double precision DEFAULT '0'::double precision NOT NULL,
    normalized_order_payload json NOT NULL,
    reject_reason_codes json NOT NULL,
    risk_flags json NOT NULL,
    submitted_at timestamp with time zone,
    approved_at timestamp with time zone,
    released_at timestamp with time zone,
    cancelled_at timestamp with time zone,
    admin_user_id character varying,
    admin_note text DEFAULT ''::text NOT NULL,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    risk_score double precision DEFAULT '0'::double precision NOT NULL,
    gate_decision character varying(30) DEFAULT 'ALLOW'::character varying NOT NULL,
    meta_engine_decision character varying(30) DEFAULT 'ALLOW'::character varying NOT NULL,
    cluster_id character varying(40),
    intent_type character varying(40) DEFAULT 'OPEN_POSITION'::character varying NOT NULL,
    position_id character varying(120),
    size double precision DEFAULT '0'::double precision NOT NULL,
    reduce_only boolean DEFAULT false NOT NULL,
    price double precision,
    stop_price double precision,
    take_profit_price double precision,
    idempotency_key character varying(128)
);


--
-- Name: user_indicator_saved_queries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_indicator_saved_queries (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    name character varying(120) DEFAULT ''::character varying NOT NULL,
    exchange character varying(30) DEFAULT 'binance'::character varying NOT NULL,
    market_type character varying(20) DEFAULT 'spot'::character varying NOT NULL,
    timeframe character varying(10) DEFAULT '15m'::character varying NOT NULL,
    query_expression text DEFAULT ''::text NOT NULL,
    symbol_universe json NOT NULL,
    result_limit integer DEFAULT 50 NOT NULL,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    filter_snapshot json DEFAULT '{}'::json NOT NULL,
    schema_version integer DEFAULT 1 NOT NULL
);


--
-- Name: user_indicator_watchlist; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_indicator_watchlist (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    exchange character varying(30) DEFAULT 'binance'::character varying NOT NULL,
    market_type character varying(20) DEFAULT 'spot'::character varying NOT NULL,
    symbol character varying(30) NOT NULL,
    note text DEFAULT ''::text NOT NULL,
    created_at timestamp with time zone,
    context_snapshot json DEFAULT '{}'::json NOT NULL
);


--
-- Name: user_learning_simulation_suggestions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_learning_simulation_suggestions (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    symbol character varying(30),
    strategy_id character varying(120),
    family character varying(40),
    recommendation_type character varying(40) NOT NULL,
    simulation_payload json NOT NULL,
    note character varying(280) NOT NULL,
    status character varying(20) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    reviewed_at timestamp with time zone,
    reviewed_by character varying
);


--
-- Name: user_mfa_backup_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_mfa_backup_codes (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    code_hash character varying(128) NOT NULL,
    used_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: user_mfa_preferences; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_mfa_preferences (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    is_enabled boolean NOT NULL,
    enabled_methods json NOT NULL,
    totp_secret character varying(120),
    totp_verified boolean NOT NULL,
    email_otp_verified boolean NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: user_onboarding_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_onboarding_profiles (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    full_name character varying(120),
    phone character varying(40),
    email_verified boolean NOT NULL,
    verification_code character varying(12),
    verification_expires_at timestamp with time zone,
    verification_requested_at timestamp with time zone,
    password_reset_token_hash character varying(128),
    password_reset_expires_at timestamp with time zone,
    password_reset_requested_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: user_risk_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_risk_settings (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    allocation_pct double precision NOT NULL,
    trade_risk_pct double precision NOT NULL,
    daily_loss_limit_pct double precision NOT NULL,
    compounding_enabled boolean NOT NULL,
    base_capital double precision NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: user_scanner_automation_configs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_scanner_automation_configs (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    auto_enabled boolean DEFAULT true NOT NULL,
    interval_seconds integer DEFAULT 180 NOT NULL,
    max_results integer DEFAULT 25 NOT NULL,
    symbol_source character varying(20) DEFAULT 'crypto'::character varying NOT NULL,
    symbol_selection_mode character varying(40) DEFAULT 'top_active_50'::character varying NOT NULL,
    selected_symbols json DEFAULT '[]'::json NOT NULL,
    last_run_id character varying(120),
    last_run_status character varying(20) DEFAULT 'idle'::character varying NOT NULL,
    last_run_error character varying(240),
    last_run_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    last_actionable_count integer DEFAULT 0 NOT NULL
);


--
-- Name: user_scanner_automation_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_scanner_automation_profiles (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    name character varying(80) DEFAULT 'default'::character varying NOT NULL,
    auto_enabled boolean DEFAULT true NOT NULL,
    is_active boolean DEFAULT false NOT NULL,
    interval_seconds integer DEFAULT 180 NOT NULL,
    max_results integer DEFAULT 25 NOT NULL,
    symbol_source character varying(20) DEFAULT 'crypto'::character varying NOT NULL,
    symbol_selection_mode character varying(40) DEFAULT 'top_active_50'::character varying NOT NULL,
    selected_symbols json DEFAULT '[]'::json NOT NULL,
    last_run_id character varying(120),
    last_run_status character varying(20) DEFAULT 'idle'::character varying NOT NULL,
    last_actionable_count integer DEFAULT 0 NOT NULL,
    last_run_error character varying(240),
    last_run_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: user_scanner_results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_scanner_results (
    id character varying NOT NULL,
    run_id character varying(64) NOT NULL,
    user_id character varying NOT NULL,
    symbol character varying(30) NOT NULL,
    strategy_code character varying(80) DEFAULT 'spot_pullback_v1'::character varying NOT NULL,
    signal character varying(20) DEFAULT 'none'::character varying NOT NULL,
    confidence double precision DEFAULT '0'::double precision NOT NULL,
    signal_score double precision DEFAULT '0'::double precision NOT NULL,
    reason_codes json NOT NULL,
    payload json NOT NULL,
    generated_at timestamp with time zone
);


--
-- Name: user_scanner_symbol_selections; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_scanner_symbol_selections (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    scanner_id character varying(60) NOT NULL,
    selected_symbols json NOT NULL,
    symbol_source character varying(20) NOT NULL,
    symbol_selection_mode character varying(40) NOT NULL,
    saved_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: user_signal_modes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_signal_modes (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    mode character varying(20) DEFAULT 'ASSISTED'::character varying NOT NULL,
    updated_at timestamp with time zone
);


--
-- Name: user_venue_assignments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_venue_assignments (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    exchange_code character varying(40) NOT NULL,
    spot_allowed boolean NOT NULL,
    futures_allowed boolean NOT NULL,
    testnet_allowed boolean NOT NULL,
    live_allowed boolean NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id character varying NOT NULL,
    email character varying NOT NULL,
    password_hash character varying NOT NULL,
    role public.userrole DEFAULT 'USER'::public.userrole NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    approval_status character varying(20) DEFAULT 'approved'::character varying NOT NULL,
    approval_requested_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    approved_at timestamp with time zone,
    disabled_at timestamp with time zone
);


--
-- Name: weekly_report_archives; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.weekly_report_archives (
    report_id character varying NOT NULL,
    report_type character varying(40) NOT NULL,
    period_start timestamp with time zone NOT NULL,
    period_end timestamp with time zone NOT NULL,
    generated_at timestamp with time zone NOT NULL,
    timezone character varying(40) NOT NULL,
    filename character varying(200) NOT NULL,
    storage_path text NOT NULL,
    size_bytes integer NOT NULL,
    sha256 character varying(128) NOT NULL,
    status character varying(20) NOT NULL,
    trigger_source character varying(20) NOT NULL,
    generated_by character varying(120) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: test_table id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.test_table ALTER COLUMN id SET DEFAULT nextval('public.test_table_id_seq'::regclass);


--
-- Data for Name: admin_control; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.admin_control (id, max_leverage_cap, max_open_positions_cap, minimum_volume_usd, max_spread_bps, spot_universe, futures_universe, whitelist, blacklist, emergency_mode, disable_futures, updated_at) FROM stdin;
global	5	10	1000000	40	[]	[]	[]	[]	f	f	2026-03-19 06:49:08.729196+00
\.


--
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.alembic_version (version_num) FROM stdin;
20260319_0053
\.


--
-- Data for Name: alert_channel_configs; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.alert_channel_configs (id, resend_api_key_encrypted, alert_from, alert_to, slack_webhook_url_encrypted, updated_at) FROM stdin;
\.


--
-- Data for Name: alert_policies; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.alert_policies (id, admin_notification_enabled, ops_webhook_url, monitoring_alert_log_enabled, execution_quality_warning_threshold, execution_quality_critical_threshold, permission_drift_warning_per_day, permission_drift_critical_per_day, gate_override_warning_per_day, gate_override_critical_per_day, updated_at) FROM stdin;
global	t		t	60	40	2	5	2	5	2026-03-19 06:49:07.190023+00
\.


--
-- Data for Name: allowed_markets; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.allowed_markets (id, exchange_code, market_type, environment, enabled, updated_at) FROM stdin;
0d0b5770-217d-4c62-8314-4bc1acf9e717	binance	spot	testnet	t	2026-03-19 06:49:08.774557+00
6f67a21d-c00f-4b67-8944-d63faa96eeb3	binance	spot	live	f	2026-03-19 06:49:08.774912+00
46975a60-2586-4a35-bc06-b47f4c796ccb	binance	futures	testnet	t	2026-03-19 06:49:08.775235+00
cb34e3d8-7e66-4558-984e-a9f2544c8b22	binance	futures	live	f	2026-03-19 06:49:08.775518+00
4b63de5d-e0b9-48c7-bdce-f9062470e639	bybit	spot	testnet	t	2026-03-19 06:49:08.775782+00
2fb07027-1c3d-4666-b6f5-6058175177bb	bybit	spot	live	f	2026-03-19 06:49:08.776032+00
045497d0-62f3-450a-b699-d850b8226a09	bybit	futures	testnet	t	2026-03-19 06:49:08.776308+00
cccf8173-b7a0-4151-b804-c3f858e3efc4	bybit	futures	live	f	2026-03-19 06:49:08.776555+00
20713eff-87d9-437f-9f62-35476ddfeeb3	okx	spot	testnet	t	2026-03-19 06:49:08.776803+00
76ca7649-ed25-4603-9926-ede73263d69d	okx	spot	live	f	2026-03-19 06:49:08.777041+00
a660bf46-8491-4067-86ef-ceb04403ef50	okx	futures	testnet	t	2026-03-19 06:49:08.777304+00
df9520f2-f622-4868-b691-42cdccd5df94	okx	futures	live	f	2026-03-19 06:49:08.777536+00
\.


--
-- Data for Name: audit_logs; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.audit_logs (id, actor_user_id, actor_role, action, entity_type, entity_id, severity, details, created_at) FROM stdin;
69334b75-4533-4d21-af72-56dd0355932a	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	bootstrap_admin_created	user	9ca118ab-d054-415a-92e0-023e9e08fe22	info	{"email": "admin@platform.local", "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 06:49:08.724348+00
b07b5ee8-dd03-4cfb-a422-36dfc12652f9	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 06:49:12.049882+00
1edb75a6-ec1b-41b7-a168-bda40265e826	\N	system	release_gate_status_changed	release_gate	phase4	warning	{"status": "BLOCKED", "reasons": ["permission_check_fail", "execution_quality_score_warning", "kill_switch_not_tested", "proof_pipeline_empty", "live_mode_disabled"], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 06:49:42.593888+00
2214197d-1907-46fa-9ce0-d4c1096cd476	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:07:48.974209+00
d3a24bc7-f0e9-4ca2-b7ef-99c4e7cea825	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:07:59.380893+00
77cb23a6-8880-4403-a64c-f52941c37836	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:08:50.881284+00
aa608354-a0cd-4981-abcf-27c54e24120d	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:09:11.005931+00
58d4da93-a452-4713-b1a4-fbbbb4c50276	\N	system	release_gate_status_changed	release_gate	phase4	warning	{"status": "BLOCKED", "reasons": ["permission_check_fail", "execution_quality_score_warning", "kill_switch_not_tested", "proof_pipeline_empty", "live_mode_disabled"], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:09:41.262567+00
64b06b28-59ac-4202-b8d5-005ce78ffe9a	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	user_login	user	9ca118ab-d054-415a-92e0-023e9e08fe22	info	{"email": "admin@platform.local", "request_id": "d73b388b-440b-4509-b38d-f6c291a93d90", "session_id": null, "route": "/api/auth/login/admin", "method": "POST"}	2026-03-19 07:11:30.219522+00
fc248101-b09f-4eae-b443-3d1500a4cfa3	c89bb203-b2e8-4230-ba9a-a01e603ae93e	user	user_registration_requested	user	c89bb203-b2e8-4230-ba9a-a01e603ae93e	warning	{"email": "testuser1773706589@example.com", "approval_status": "pending", "request_id": "9924d1b4-e49d-4698-b078-131816b717a1", "session_id": null, "route": "/api/auth/register", "method": "POST"}	2026-03-19 07:11:30.796045+00
45bebf0a-1b76-41c2-b6a7-67848b79f67c	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	user_login	user	9ca118ab-d054-415a-92e0-023e9e08fe22	info	{"email": "admin@platform.local", "request_id": "bd0361a7-4dd7-480a-aaa1-a56f0f5b78e7", "session_id": null, "route": "/api/auth/login/admin", "method": "POST"}	2026-03-19 07:11:31.252407+00
5aaf73dd-55c9-46ac-8f5d-e5378263e088	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	user_approval_approved	user	c89bb203-b2e8-4230-ba9a-a01e603ae93e	info	{"email": "testuser1773706589@example.com", "request_id": "6272fbd4-91d3-4553-b1ff-1af1b62cac84", "session_id": null, "route": "/api/auth/admin/user-approval-requests/c89bb203-b2e8-4230-ba9a-a01e603ae93e/approve", "method": "POST"}	2026-03-19 07:11:31.606649+00
821e3151-946a-4e28-b7a7-7fa481d45495	c89bb203-b2e8-4230-ba9a-a01e603ae93e	user	user_login	user	c89bb203-b2e8-4230-ba9a-a01e603ae93e	info	{"email": "testuser1773706589@example.com", "request_id": "6adb5d50-7ec6-4b65-be30-2472f55bd35d", "session_id": null, "route": "/api/auth/login/user", "method": "POST"}	2026-03-19 07:11:32.010606+00
957e1b00-2399-4074-b54e-07b564277a30	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	user_login	user	9ca118ab-d054-415a-92e0-023e9e08fe22	info	{"email": "admin@platform.local", "request_id": "a44e998d-3226-46a2-906a-5613c392cbd1", "session_id": null, "route": "/api/auth/login/admin", "method": "POST"}	2026-03-19 07:15:13.444364+00
873549b8-4b1e-4000-a71c-37f7426cc110	c89bb203-b2e8-4230-ba9a-a01e603ae93e	user	user_login	user	c89bb203-b2e8-4230-ba9a-a01e603ae93e	info	{"email": "testuser1773706589@example.com", "request_id": "939cc60c-270b-465b-aabd-068ac61faf8a", "session_id": null, "route": "/api/auth/login/user", "method": "POST"}	2026-03-19 07:15:13.96591+00
a391a282-6c43-4498-bd80-bbacc5edd697	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:28:18.173723+00
46c0ea51-c13f-42a6-bf79-9757771c89df	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:28:26.251471+00
782006e8-963e-4da8-b5fa-663f008e4a27	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:29:11.671375+00
7f89a710-1ca0-4fc4-9c04-db9dbddb75c2	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:29:46.227378+00
ad1fcab3-9bde-463e-83a7-b84cae142a91	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:30:46.462914+00
17b201ac-aa21-4b75-bb19-4e39c43213da	\N	system	release_gate_status_changed	release_gate	phase4	warning	{"status": "BLOCKED", "reasons": ["permission_check_fail", "execution_quality_score_warning", "kill_switch_not_tested", "proof_pipeline_empty", "live_mode_disabled"], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:31:16.738002+00
c9e8bb32-37c8-4189-8b86-d3cdf6d5e859	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:34:19.116747+00
3a6eca45-6d1f-4bba-a8a5-3152eca6f4f1	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:34:29.983045+00
9f69cf2b-ab24-49f6-b011-02d24ec5cb8c	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:34:38.195435+00
4622189b-97e8-4c3d-be3f-6b13a0912d81	\N	system	release_gate_status_changed	release_gate	phase4	warning	{"status": "BLOCKED", "reasons": ["permission_check_fail", "execution_quality_score_warning", "kill_switch_not_tested", "proof_pipeline_empty", "live_mode_disabled"], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:35:08.759928+00
2c7f5942-83de-44c8-b1c6-59b1426d9e17	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:35:17.991641+00
b4c92bd8-f745-41df-9f70-8f2b5bfaf6cf	94fa99c0-f373-4f00-95a8-7677ef165fa9	user	ORDER_PREFLIGHT	execution_intent	ca0f2159-19db-4f1e-a4d5-76989118dca0	info	{"stage": "ORDER PREFLIGHT", "validation_status": "valid", "symbol_integrity_ok": true, "reject_reason_codes": [], "request_id": "0cc4552e-131c-41a2-8faf-2b282f88805f", "session_id": null, "route": "/api/user/execution/intent/preview", "method": "POST"}	2026-03-19 07:35:18.071434+00
14a6b499-809e-4a77-ac2a-97e39b1af4b0	94fa99c0-f373-4f00-95a8-7677ef165fa9	user	RISK_RESULT	execution_intent	ca0f2159-19db-4f1e-a4d5-76989118dca0	info	{"stage": "RISK RESULT", "risk_flags": ["stop_loss_missing_warning"], "gate_decision": "ALLOW", "meta_engine_decision": "ALLOW", "portfolio_risk_impact": {"risk_score": 0.0067, "risk_flags": [], "approval_required": false, "position_adjustment": {"applied": false, "requested_notional": 40.0, "adjusted_notional": 40.0, "adjustment_factor": 1.0}, "decision": "ALLOW", "cluster_id": "L1", "current_portfolio_leverage": 0.004, "symbol_exposure_pct": 0.4, "cluster_exposure_pct": 0.4, "strategy_exposure_pct": 0.4, "single_trade_risk_pct": 0.4, "portfolio_state": {"base_capital": 10000.0, "current_capital": 10000.0, "intraday_drawdown_pct": 0.0, "total_drawdown_pct": 0.0}, "limits": {"max_portfolio_leverage": 3.0, "max_symbol_exposure": 35.0, "max_cluster_exposure": 50.0, "max_strategy_exposure": 40.0, "max_single_trade_risk": 10.0, "max_intraday_drawdown": 5.0, "max_total_drawdown": 15.0}}, "request_id": "0cc4552e-131c-41a2-8faf-2b282f88805f", "session_id": null, "route": "/api/user/execution/intent/preview", "method": "POST"}	2026-03-19 07:35:18.074744+00
d29fb8f5-5e55-4080-b1b9-31f9e004fc16	94fa99c0-f373-4f00-95a8-7677ef165fa9	user	EXECUTION_INTENT	execution_intent	ca0f2159-19db-4f1e-a4d5-76989118dca0	info	{"stage": "EXECUTION INTENT", "symbol": "BTCUSDT", "side": "buy", "strategy": "faz2_integrity_strategy", "confidence": null, "score": null, "timestamp": "2026-03-19T12:45:10Z", "request_id": "0cc4552e-131c-41a2-8faf-2b282f88805f", "session_id": null, "route": "/api/user/execution/intent/preview", "method": "POST"}	2026-03-19 07:35:18.07665+00
7c14578f-3ce1-44ea-a2b8-67032baaa2e4	94fa99c0-f373-4f00-95a8-7677ef165fa9	user	EXECUTION_INTENT_PREVIEWED	execution_intent	ca0f2159-19db-4f1e-a4d5-76989118dca0	info	{"intent_status": "PREVIEWED", "validation_status": "valid", "reason_codes": [], "request_id": "0cc4552e-131c-41a2-8faf-2b282f88805f", "session_id": null, "route": "/api/user/execution/intent/preview", "method": "POST"}	2026-03-19 07:35:18.07844+00
ed2a5e20-2cbf-4be2-a1ef-bd92db40d8a6	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:35:54.094657+00
4441f042-fb0a-4df1-8f48-b9be362c89b2	3f01b548-f272-4c42-95fa-80d7734e9578	user	ORDER_PREFLIGHT	execution_intent	0c7b03f1-da69-4e79-8ff9-95e4c048675d	info	{"stage": "ORDER PREFLIGHT", "validation_status": "valid", "symbol_integrity_ok": true, "reject_reason_codes": [], "request_id": "046c321a-4ca0-4908-9530-ff80aeb2ac70", "session_id": null, "route": "/api/user/execution/intent/preview", "method": "POST"}	2026-03-19 07:35:54.149648+00
26c623b9-0b38-4a9f-ab46-442a6139b2bc	3f01b548-f272-4c42-95fa-80d7734e9578	user	RISK_RESULT	execution_intent	0c7b03f1-da69-4e79-8ff9-95e4c048675d	info	{"stage": "RISK RESULT", "risk_flags": ["stop_loss_missing_warning"], "gate_decision": "ALLOW", "meta_engine_decision": "ALLOW", "portfolio_risk_impact": {"risk_score": 0.0067, "risk_flags": [], "approval_required": false, "position_adjustment": {"applied": false, "requested_notional": 40.0, "adjusted_notional": 40.0, "adjustment_factor": 1.0}, "decision": "ALLOW", "cluster_id": "L1", "current_portfolio_leverage": 0.004, "symbol_exposure_pct": 0.4, "cluster_exposure_pct": 0.4, "strategy_exposure_pct": 0.4, "single_trade_risk_pct": 0.4, "portfolio_state": {"base_capital": 10000.0, "current_capital": 10000.0, "intraday_drawdown_pct": 0.0, "total_drawdown_pct": 0.0}, "limits": {"max_portfolio_leverage": 3.0, "max_symbol_exposure": 35.0, "max_cluster_exposure": 50.0, "max_strategy_exposure": 40.0, "max_single_trade_risk": 10.0, "max_intraday_drawdown": 5.0, "max_total_drawdown": 15.0}}, "request_id": "046c321a-4ca0-4908-9530-ff80aeb2ac70", "session_id": null, "route": "/api/user/execution/intent/preview", "method": "POST"}	2026-03-19 07:35:54.15984+00
03f05061-1606-4b40-8b80-cf47956c04f8	3f01b548-f272-4c42-95fa-80d7734e9578	user	EXECUTION_INTENT	execution_intent	0c7b03f1-da69-4e79-8ff9-95e4c048675d	info	{"stage": "EXECUTION INTENT", "symbol": "BTCUSDT", "side": "buy", "strategy": "faz2_integrity_strategy", "confidence": null, "score": null, "timestamp": "2026-03-19T12:45:10Z", "request_id": "046c321a-4ca0-4908-9530-ff80aeb2ac70", "session_id": null, "route": "/api/user/execution/intent/preview", "method": "POST"}	2026-03-19 07:35:54.162369+00
b697e0d2-1d9a-41d7-8c79-d1e88ecb37dc	3f01b548-f272-4c42-95fa-80d7734e9578	user	EXECUTION_INTENT_PREVIEWED	execution_intent	0c7b03f1-da69-4e79-8ff9-95e4c048675d	info	{"intent_status": "PREVIEWED", "validation_status": "valid", "reason_codes": [], "request_id": "046c321a-4ca0-4908-9530-ff80aeb2ac70", "session_id": null, "route": "/api/user/execution/intent/preview", "method": "POST"}	2026-03-19 07:35:54.164635+00
622669a1-0438-4693-a8ec-6bf0ed3b37f1	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:36:03.050884+00
d38f8645-ad01-41aa-8b28-149df4f4e059	3f01b548-f272-4c42-95fa-80d7734e9578	user	trade_close	paper_position	6e275418-6445-4412-a4b9-72e36eaa8181	info	{"reason": "stop_hit", "realized_pnl": -2.90316, "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:36:27.887462+00
bfad1447-1bb3-44cf-933f-57259ffa2376	059dab08-b67a-43a5-ba71-e0721d317f78	user	trade_close	paper_position	2e0b4e67-5556-4acf-a0ee-053ed87f8e9a	info	{"reason": "stop_hit", "realized_pnl": -2.90316, "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:36:27.891264+00
f39c8eb9-6e59-48dc-9c59-bd2b6afc584b	\N	system	release_gate_status_changed	release_gate	phase4	warning	{"status": "BLOCKED", "reasons": ["permission_check_fail", "execution_quality_score_warning", "kill_switch_not_tested", "proof_pipeline_empty", "live_mode_disabled"], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:36:33.306144+00
a7ec4730-1e0b-427e-a741-162a5cb950eb	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:39:19.342777+00
a357ebfa-8ca9-48e2-8b23-df84fb0f4e87	\N	system	release_gate_status_changed	release_gate	phase4	warning	{"status": "BLOCKED", "reasons": ["permission_check_fail", "execution_quality_score_warning", "kill_switch_not_tested", "proof_pipeline_empty", "live_mode_disabled"], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:39:49.658379+00
8b4fa2d7-5395-438a-af0c-b6bc4f297488	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:49:26.728286+00
f87e13fa-dda0-4325-beb3-94cf7f037bd1	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:49:36.408616+00
2f91db97-9635-4028-a227-d643265323f3	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:49:56.133039+00
61bc447d-fd7e-48cb-9d1e-da463b961e96	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:50:06.279791+00
061bac92-8d2c-4ae5-a248-59e5b35d05b1	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:51:27.088631+00
df6f393a-99dc-49a7-81db-e200e4272a4c	\N	system	release_gate_status_changed	release_gate	phase4	warning	{"status": "BLOCKED", "reasons": ["permission_check_fail", "execution_quality_score_warning", "kill_switch_not_tested", "proof_pipeline_empty", "live_mode_disabled"], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:51:57.618748+00
0913f4b0-b439-421a-893c-694be9189291	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	user_login	user	9ca118ab-d054-415a-92e0-023e9e08fe22	info	{"email": "admin@platform.local", "request_id": "a0e0fb67-2577-47a3-8475-726ad10f6217", "session_id": null, "route": "/api/auth/login/admin", "method": "POST"}	2026-03-19 07:56:17.314513+00
c462335b-805d-45bf-9f5c-173a88912010	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	brand_settings_updated	brand_settings	default	info	{"app_name": "faz0-persist-1773906976", "request_id": "9da4f437-93bb-44ae-83eb-685423d31e75", "session_id": null, "route": "/api/admin/brand-settings", "method": "PUT"}	2026-03-19 07:56:17.48745+00
c37fb998-4b7c-4551-833f-5658ab1d01de	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:56:23.468656+00
9ce4d7a0-a955-49a9-8d7f-debbea9337b4	\N	system	release_gate_status_changed	release_gate	phase4	warning	{"status": "BLOCKED", "reasons": ["permission_check_fail", "execution_quality_score_warning", "kill_switch_not_tested", "proof_pipeline_empty", "live_mode_disabled"], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:56:53.769815+00
28e1ce9c-9fe2-4731-adf8-f6ace714a957	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:57:02.439008+00
2fb92b2a-0e69-436f-9672-37fd69aa4425	\N	system	release_gate_status_changed	release_gate	phase4	warning	{"status": "BLOCKED", "reasons": ["permission_check_fail", "execution_quality_score_warning", "kill_switch_not_tested", "proof_pipeline_empty", "live_mode_disabled"], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:57:33.026297+00
f3e076c3-e1d8-4d85-941d-fcc003fbc462	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	user_login	user	9ca118ab-d054-415a-92e0-023e9e08fe22	info	{"email": "admin@platform.local", "request_id": "d653bab8-5a54-45fa-888e-c4fce9f4b012", "session_id": null, "route": "/api/auth/login/admin", "method": "POST"}	2026-03-19 07:57:35.274651+00
1c667ab0-3602-4630-a0f7-22e625640bd9	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	brand_settings_updated	brand_settings	default	info	{"app_name": "faz0-persist-1773907054", "request_id": "4d917608-6072-490d-9e6f-2d5022c5340e", "session_id": null, "route": "/api/admin/brand-settings", "method": "PUT"}	2026-03-19 07:57:35.50333+00
4577d591-5754-43e9-bf67-c2ae34a1be4c	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:57:41.18683+00
59d44a17-9d00-415e-9711-4a224a59c8a2	\N	system	release_gate_status_changed	release_gate	phase4	warning	{"status": "BLOCKED", "reasons": ["permission_check_fail", "execution_quality_score_warning", "kill_switch_not_tested", "proof_pipeline_empty", "live_mode_disabled"], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:58:11.753545+00
35e4a70a-9340-47bf-8a4b-f41e4e8d0f94	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	user_login	user	9ca118ab-d054-415a-92e0-023e9e08fe22	info	{"email": "admin@platform.local", "request_id": "07a84db1-73c8-4bb3-8fb9-55689133f83f", "session_id": null, "route": "/api/auth/login/admin", "method": "POST"}	2026-03-19 07:58:32.179608+00
1973d9b6-9b47-41c7-8e73-471d155bec52	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	brand_settings_updated	brand_settings	default	info	{"app_name": "faz0-persist-1773907111", "request_id": "8e083f98-c990-43d3-9ede-587999de0d5e", "session_id": null, "route": "/api/admin/brand-settings", "method": "PUT"}	2026-03-19 07:58:32.357706+00
a09a0c18-ed0b-4d4e-8aad-20435a77e65e	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:58:37.887535+00
8dd2bf2d-0806-4aef-836f-c996554b1ef2	\N	system	release_gate_status_changed	release_gate	phase4	warning	{"status": "BLOCKED", "reasons": ["permission_check_fail", "execution_quality_score_warning", "kill_switch_not_tested", "proof_pipeline_empty", "live_mode_disabled"], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:59:08.186401+00
29c45a3f-ab34-4d66-a5a3-fbde3aa88889	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 07:59:41.808463+00
f1f0abe0-92e2-4cbc-be30-5d9369b427d3	\N	system	release_gate_status_changed	release_gate	phase4	warning	{"status": "BLOCKED", "reasons": ["permission_check_fail", "execution_quality_score_warning", "kill_switch_not_tested", "proof_pipeline_empty", "live_mode_disabled"], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 08:00:12.06334+00
d0f2bfe4-3d45-425c-971f-1ea27c73a24b	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 08:01:52.72437+00
b2af7f83-dace-4368-87db-245d3eb48f90	\N	system	release_gate_status_changed	release_gate	phase4	warning	{"status": "BLOCKED", "reasons": ["permission_check_fail", "execution_quality_score_warning", "kill_switch_not_tested", "proof_pipeline_empty", "live_mode_disabled"], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 08:02:23.046239+00
85297db1-6612-4c86-876a-07f0d6bb1838	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	user_login	user	9ca118ab-d054-415a-92e0-023e9e08fe22	info	{"email": "admin@platform.local", "request_id": "1ee620ae-ffe7-4dbe-9a58-41d923713ef0", "session_id": null, "route": "/api/auth/login/admin", "method": "POST"}	2026-03-19 08:02:26.396805+00
943d11a5-3c23-4cf7-a095-a747c3997f79	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	brand_settings_updated	brand_settings	default	info	{"app_name": "faz0-persist-1773907345", "request_id": "276d9b3e-f563-434d-94f1-f4fc9d8d1e1c", "session_id": null, "route": "/api/admin/brand-settings", "method": "PUT"}	2026-03-19 08:02:26.566496+00
ee9b567f-d43b-467b-b5c2-dc53c6ee88ec	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 08:02:32.230929+00
d6375259-3514-491a-a50e-95889b3db460	\N	system	release_gate_status_changed	release_gate	phase4	warning	{"status": "BLOCKED", "reasons": ["permission_check_fail", "execution_quality_score_warning", "kill_switch_not_tested", "proof_pipeline_empty", "live_mode_disabled"], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 08:03:02.594793+00
c2d3b2b8-9b41-47ba-b492-b7d1ff6d5533	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	user_login	user	9ca118ab-d054-415a-92e0-023e9e08fe22	info	{"email": "admin@platform.local", "request_id": "ecc7f640-a974-4568-920d-5c929fdf422d", "session_id": null, "route": "/api/auth/login/admin", "method": "POST"}	2026-03-19 08:04:09.135429+00
f9410096-179f-421d-8f7f-f434987e4db8	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	brand_settings_updated	brand_settings	default	info	{"app_name": "faz0-persist-1773907448", "request_id": "16d4ab4e-0d18-41e9-a487-e140dd031700", "session_id": null, "route": "/api/admin/brand-settings", "method": "PUT"}	2026-03-19 08:04:09.282964+00
48325041-8dfa-4ede-974a-8904d86e7c9c	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 08:04:14.96509+00
52c78bdc-4fcb-46f0-b921-ef3f2069e0f6	\N	system	release_gate_status_changed	release_gate	phase4	warning	{"status": "BLOCKED", "reasons": ["permission_check_fail", "execution_quality_score_warning", "kill_switch_not_tested", "proof_pipeline_empty", "live_mode_disabled"], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 08:04:45.564563+00
ea442049-42b3-4b88-8db8-e6d445021c1c	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	user_login	user	9ca118ab-d054-415a-92e0-023e9e08fe22	info	{"email": "admin@platform.local", "request_id": "2bd4cdbf-7aa9-4490-9359-756b780fb1a5", "session_id": null, "route": "/api/auth/login/admin", "method": "POST"}	2026-03-19 08:05:11.943752+00
43bd418a-d323-49ad-9de8-b74c3243a90b	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	brand_settings_updated	brand_settings	default	info	{"app_name": "faz0-persist-1773907511", "request_id": "3a0e0d5e-b4f0-44c0-bc6e-a6a130817db2", "session_id": null, "route": "/api/admin/brand-settings", "method": "PUT"}	2026-03-19 08:05:12.083578+00
9a467ba5-873a-4763-8948-787c6c065cea	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 08:05:17.679294+00
bf168a80-2dfc-4d48-986b-c1b6000ca645	\N	system	release_gate_status_changed	release_gate	phase4	warning	{"status": "BLOCKED", "reasons": ["permission_check_fail", "execution_quality_score_warning", "kill_switch_not_tested", "proof_pipeline_empty", "live_mode_disabled"], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 08:05:48.606851+00
2fd11601-0925-4e5e-ab04-8be39c479433	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	user_login	user	9ca118ab-d054-415a-92e0-023e9e08fe22	info	{"email": "admin@platform.local", "request_id": "1665e369-3db4-4485-bec7-659ff4acade9", "session_id": null, "route": "/api/auth/login/admin", "method": "POST"}	2026-03-19 08:25:57.236347+00
3172f038-3654-42d1-9b44-4bc2c3114a98	c89bb203-b2e8-4230-ba9a-a01e603ae93e	user	user_login	user	c89bb203-b2e8-4230-ba9a-a01e603ae93e	info	{"email": "testuser1773706589@example.com", "request_id": "3b0da08d-36e1-4854-957e-3bc7d49475cc", "session_id": null, "route": "/api/auth/login/user", "method": "POST"}	2026-03-19 08:25:57.622785+00
601c6d4e-5a4b-45c5-82b6-2f61858d8ec5	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	user_login	user	9ca118ab-d054-415a-92e0-023e9e08fe22	info	{"email": "admin@platform.local", "request_id": "39518772-f28f-4b20-9530-91ff1466d4a3", "session_id": null, "route": "/api/auth/login/admin", "method": "POST"}	2026-03-19 08:29:00.432628+00
5ac10904-6e2e-42f5-b3df-7b5d400d217c	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	brand_settings_updated	brand_settings	default	info	{"app_name": "faz0-persist-1773908939", "request_id": "4f5db544-f1fd-40b9-bfd0-e045212dd21c", "session_id": null, "route": "/api/admin/brand-settings", "method": "PUT"}	2026-03-19 08:29:00.560974+00
6848fe5e-1b31-4e16-8df0-1a90e8b97932	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 08:29:06.466621+00
d6f05030-7bf9-4381-901a-4542b0c19a40	\N	system	release_gate_status_changed	release_gate	phase4	warning	{"status": "BLOCKED", "reasons": ["permission_check_fail", "execution_quality_score_warning", "kill_switch_not_tested", "proof_pipeline_empty", "live_mode_disabled"], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 08:29:36.772845+00
c1d7309f-0c02-4db9-91e0-f56a5b32a8bc	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	user_login	user	9ca118ab-d054-415a-92e0-023e9e08fe22	info	{"email": "admin@platform.local", "request_id": "539d0d15-fd7c-44a6-b4f7-c0d5b7ded316", "session_id": null, "route": "/api/auth/login/admin", "method": "POST"}	2026-03-19 08:29:54.607336+00
cf4b3677-7a81-4d50-8251-ca3d9bbc2a18	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	brand_settings_updated	brand_settings	default	info	{"app_name": "faz0-persist-1773908994", "request_id": "12986580-e0b6-4b29-b83b-9f194dd26d43", "session_id": null, "route": "/api/admin/brand-settings", "method": "PUT"}	2026-03-19 08:29:54.784634+00
8901ae4f-92a3-473e-a974-c3a8f73bec4d	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 08:30:00.531231+00
b2138678-fa4c-46d5-b7e5-43c6934490e5	\N	system	release_gate_status_changed	release_gate	phase4	warning	{"status": "BLOCKED", "reasons": ["permission_check_fail", "execution_quality_score_warning", "kill_switch_not_tested", "proof_pipeline_empty", "live_mode_disabled"], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 08:30:31.091392+00
23003328-329b-40f9-b649-32e0142c5d10	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	user_login	user	9ca118ab-d054-415a-92e0-023e9e08fe22	info	{"email": "admin@platform.local", "request_id": "497930ec-bf4d-497e-92ff-5ae581e32741", "session_id": null, "route": "/api/auth/login/admin", "method": "POST"}	2026-03-19 08:31:04.873467+00
534b4e55-051b-498d-bbbf-7e0a61b51b6a	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	brand_settings_updated	brand_settings	default	info	{"app_name": "faz0-persist-1773909064", "request_id": "fc955e0d-8ba8-4158-bacf-3cdc389a406c", "session_id": null, "route": "/api/admin/brand-settings", "method": "PUT"}	2026-03-19 08:31:05.010796+00
5c9b35b0-7966-44a7-be35-0e551b895275	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 08:31:10.719353+00
b5b66cfa-ec48-4f4f-8dbb-35fc8df7498f	\N	system	release_gate_status_changed	release_gate	phase4	warning	{"status": "BLOCKED", "reasons": ["permission_check_fail", "execution_quality_score_warning", "kill_switch_not_tested", "proof_pipeline_empty", "live_mode_disabled"], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 08:31:41.538253+00
3ec4f603-5c3b-48a0-95c1-bb9d137e93d8	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	user_login	user	9ca118ab-d054-415a-92e0-023e9e08fe22	info	{"email": "admin@platform.local", "request_id": "0046835e-a6ea-4ab4-8745-6876e9a48ae5", "session_id": null, "route": "/api/auth/login/admin", "method": "POST"}	2026-03-19 08:33:53.020208+00
dbbb1a93-04b4-4a8f-b0ab-4f56d4eefeb0	c89bb203-b2e8-4230-ba9a-a01e603ae93e	user	user_login	user	c89bb203-b2e8-4230-ba9a-a01e603ae93e	info	{"email": "testuser1773706589@example.com", "request_id": "330763c4-8a10-4255-85a4-e9fa6bb09db7", "session_id": null, "route": "/api/auth/login/user", "method": "POST"}	2026-03-19 08:33:53.417329+00
1c31f3cb-002e-41c0-affc-e27053bfc14e	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	user_login	user	9ca118ab-d054-415a-92e0-023e9e08fe22	info	{"email": "admin@platform.local", "request_id": "7ad5deae-69d2-4a0a-946c-4e48a7af61a7", "session_id": null, "route": "/api/auth/login/admin", "method": "POST"}	2026-03-19 08:35:59.345778+00
cf6ac812-a748-4357-a02e-02aaaa76c235	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	brand_settings_updated	brand_settings	default	info	{"app_name": "faz0-persist-1773909358", "request_id": "da06eebb-82e4-480d-9b14-1c2e314d4fd3", "session_id": null, "route": "/api/admin/brand-settings", "method": "PUT"}	2026-03-19 08:35:59.475133+00
786bcef5-e8f5-4532-9f98-7dee0edd30b6	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 08:36:05.240378+00
da99a588-9ca3-43e1-ac7a-153eeaa23c9d	\N	system	release_gate_status_changed	release_gate	phase4	warning	{"status": "BLOCKED", "reasons": ["permission_check_fail", "execution_quality_score_warning", "kill_switch_not_tested", "proof_pipeline_empty", "live_mode_disabled"], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 08:36:36.026979+00
b611d605-7e80-4d01-b9ed-ba4a8bb04a81	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	user_login	user	9ca118ab-d054-415a-92e0-023e9e08fe22	info	{"email": "admin@platform.local", "request_id": "35ed323c-d5f1-4ac2-ac41-337b88e7d899", "session_id": null, "route": "/api/auth/login/admin", "method": "POST"}	2026-03-19 08:38:33.787275+00
40c0cb2b-f124-4367-a65d-1b39352c99f4	c89bb203-b2e8-4230-ba9a-a01e603ae93e	user	user_login	user	c89bb203-b2e8-4230-ba9a-a01e603ae93e	info	{"email": "testuser1773706589@example.com", "request_id": "296ef08a-2285-4401-96ee-6a8bf2c122f0", "session_id": null, "route": "/api/auth/login/user", "method": "POST"}	2026-03-19 08:38:34.208376+00
3222fa49-cd1e-4521-9c9e-d3fb40805b98	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	user_login	user	9ca118ab-d054-415a-92e0-023e9e08fe22	info	{"email": "admin@platform.local", "request_id": "96d9fd19-de4f-4564-932b-5616f19bae96", "session_id": null, "route": "/api/auth/login/admin", "method": "POST"}	2026-03-19 08:40:22.824123+00
ee6c11ac-d8fe-42c4-bdae-a19bc16ed8e2	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	brand_settings_updated	brand_settings	default	info	{"app_name": "faz0-persist-1773909622", "request_id": "970e1941-ae49-4c46-8663-1fea2258a779", "session_id": null, "route": "/api/admin/brand-settings", "method": "PUT"}	2026-03-19 08:40:23.413883+00
59efcc33-4857-49a6-be01-3dc235480c54	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 08:40:29.136272+00
963aac3b-f0f3-4c26-aa5f-8ffacf5fdcd8	\N	system	release_gate_status_changed	release_gate	phase4	warning	{"status": "BLOCKED", "reasons": ["permission_check_fail", "execution_quality_score_warning", "kill_switch_not_tested", "proof_pipeline_empty", "live_mode_disabled"], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 08:41:00.060557+00
5421b3be-a723-4ea6-bae7-a1628bfeb0ce	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	user_login	user	9ca118ab-d054-415a-92e0-023e9e08fe22	info	{"email": "admin@platform.local", "request_id": "a714fc8e-fcab-4d2f-a361-6d679d30945b", "session_id": null, "route": "/api/auth/login/admin", "method": "POST"}	2026-03-19 08:42:30.08796+00
6f5030d3-e33f-4134-a85b-c10de9db5af3	c89bb203-b2e8-4230-ba9a-a01e603ae93e	user	user_login	user	c89bb203-b2e8-4230-ba9a-a01e603ae93e	info	{"email": "testuser1773706589@example.com", "request_id": "fa75f245-d112-44d3-bfc3-a9ca70975d82", "session_id": null, "route": "/api/auth/login/user", "method": "POST"}	2026-03-19 08:42:30.598322+00
52654f5f-a0a9-4a39-a4d2-4a0d52627429	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	user_login	user	9ca118ab-d054-415a-92e0-023e9e08fe22	info	{"email": "admin@platform.local", "request_id": "9138ea22-bc53-4e50-829a-65d2c7cb491b", "session_id": null, "route": "/api/auth/login/admin", "method": "POST"}	2026-03-19 08:43:38.983609+00
532fdad6-5633-43fb-bcfe-536d640f17cd	9ca118ab-d054-415a-92e0-023e9e08fe22	super_admin	brand_settings_updated	brand_settings	default	info	{"app_name": "faz0-persist-1773909818", "request_id": "78273770-afe5-4d2c-8399-d3b049331c96", "session_id": null, "route": "/api/admin/brand-settings", "method": "PUT"}	2026-03-19 08:43:39.694574+00
481f5f90-1033-49b5-aa45-52851744b50b	\N	system	SPOT_UNIVERSE_REFRESHED	spot_universe	2026-03-19	info	{"symbol_count": 0, "seeded": 0, "failed": [], "request_id": null, "session_id": null, "route": null, "method": null}	2026-03-19 08:43:45.38428+00
\.


--
-- Data for Name: auth_mfa_challenges; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.auth_mfa_challenges (id, user_id, challenge_token_hash, allowed_methods, email_otp_hash, email_delivery_status, expires_at, consumed_at, created_at) FROM stdin;
\.


--
-- Data for Name: backtest_result_cards; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.backtest_result_cards (id, strategy_type, market_type, timeframe, sample_size, win_rate, max_drawdown, profit_factor, sharpe_like_score, performance_summary, risk_label, period_start, period_end, created_at, updated_at) FROM stdin;
7a68f6c2-2533-41a2-aedd-45d33a7498c1	trend_following	spot	15m	240	54.2	9.8	1.34	0.88	Stable trend capture with moderate drawdown.	medium	2025-01-01	2025-12-31	2026-03-19 06:49:08.743245+00	2026-03-19 06:49:08.743248+00
29abf183-4252-422f-851b-7b96c97e4415	mean_reversion	spot	15m	260	61.1	12.4	1.21	0.73	Higher win rate but lower payoff consistency.	medium-high	2025-01-01	2025-12-31	2026-03-19 06:49:08.743253+00	2026-03-19 06:49:08.743253+00
\.


--
-- Data for Name: bot_profiles; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.bot_profiles (id, user_id, name, exchange, market_type, symbols, strategy_type, timeframe, trend_timeframe, leverage, is_enabled, is_running, is_deleted, deleted_at, created_at, updated_at) FROM stdin;
afe2c4d8-f226-4f10-a712-a3f522335aeb	3f01b548-f272-4c42-95fa-80d7734e9578	Execution Intent Bot	binance	futures	["BTCUSDT"]	manual_execution	15m	1h	3	t	f	f	\N	2026-03-19 07:35:54.182475+00	2026-03-19 07:35:54.182478+00
cbccc782-c5d9-452f-b167-03bce90b16a2	059dab08-b67a-43a5-ba71-e0721d317f78	Execution Intent Bot	binance	futures	["BTCUSDT"]	manual_execution	15m	1h	3	t	f	f	\N	2026-03-19 07:36:21.105559+00	2026-03-19 07:36:21.105562+00
\.


--
-- Data for Name: brand_settings; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.brand_settings (id, app_name, logo_filename, logo_mime_type, logo_blob, logo_storage_note, metadata_json, updated_by_user_id, updated_at, created_at) FROM stdin;
default	faz0-persist-1773909818	\N	\N	\N	db_blob	{}	9ca118ab-d054-415a-92e0-023e9e08fe22	2026-03-19 08:43:39.690089+00	2026-03-19 07:07:48.991274+00
\.


--
-- Data for Name: canonical_strategy_registry; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.canonical_strategy_registry (strategy_id, strategy_family, direction, market_regime, entry_logic_version, exit_logic_version, risk_profile, is_enabled, priority, cooldown_policy, weight, entry_long, entry_short, exit_long, exit_short, invalid_state_rules, cooldown_rules, risk_rules, is_legacy_candidate, in_production_path, last_50_signal_quality, false_allow_rate, false_reject_rate, cooldown_state, risk_block_reason, forced_disable_reason, created_at, updated_at, stop_loss, take_profit, invalidation, signal_score) FROM stdin;
ichimoku_trend_continuation	trend	both	trend	v2	v2	global_standardized	t	10	symbol:21600s	3	{"rules": ["tenkan_cross_up_kijun", "price_above_kumo", "senkou_a_above_senkou_b", "chikou_above_price"], "version": "v2"}	{"rules": ["tenkan_cross_down_kijun", "price_below_kumo", "senkou_a_below_senkou_b", "chikou_below_price"], "version": "v2"}	{"rules": ["tenkan_below_kijun", "price_below_kijun"], "version": "v2"}	{"rules": ["tenkan_above_kijun", "price_above_kijun"], "version": "v2"}	["double_intent_conflict", "symbol_direction_conflict"]	{"policy": "symbol", "seconds": 21600}	{"single_symbol_single_direction": true, "atr_stop_required": true, "rr_target_required": true, "max_positions": 5, "risk_per_trade_pct": 1.5}	f	t	0	0	0	ready	\N	\N	2026-03-19 06:49:08.75936+00	2026-03-19 06:49:08.759363+00	{"type": "atr", "multiplier": 2.0}	{"type": "rr", "ratio": 2.5}	{"rules": ["price_returns_into_kumo"], "version": "v2"}	{"strong": 3, "medium": 2}
golden_cross_regime	trend	both	trend	v2	v2	global_standardized	f	20	symbol:21600s	2	{"rules": ["ma50_above_ma200", "price_above_ma50", "ma50_slope_positive"], "version": "v2"}	{"rules": ["ma50_below_ma200", "price_below_ma50", "ma50_slope_negative"], "version": "v2"}	{"rules": ["ma50_below_ma200"], "version": "v2"}	{"rules": ["ma50_above_ma200"], "version": "v2"}	["double_intent_conflict", "symbol_direction_conflict"]	{"policy": "symbol", "seconds": 21600}	{"single_symbol_single_direction": true, "atr_stop_required": true, "rr_target_required": true, "max_positions": 5, "risk_per_trade_pct": 1.5}	f	t	0	0	0	ready	\N	\N	2026-03-19 06:49:08.759364+00	2026-03-19 06:49:08.759365+00	{"type": "atr", "multiplier": 1.8}	{"type": "rr", "ratio": 3.0}	{"rules": ["price_inside_ma_cluster"], "version": "v2"}	{"base": 2}
supertrend_flip	trend	both	trend	v2	v2	global_standardized	t	15	symbol:21600s	2	{"rules": ["price_crosses_above_supertrend"], "version": "v2"}	{"rules": ["price_crosses_below_supertrend"], "version": "v2"}	{"rules": ["supertrend_flip_bearish"], "version": "v2"}	{"rules": ["supertrend_flip_bullish"], "version": "v2"}	["double_intent_conflict", "symbol_direction_conflict"]	{"policy": "symbol", "seconds": 21600}	{"single_symbol_single_direction": true, "atr_stop_required": true, "rr_target_required": true, "max_positions": 5, "risk_per_trade_pct": 1.5}	f	t	0	0	0	ready	\N	\N	2026-03-19 06:49:08.759365+00	2026-03-19 06:49:08.759366+00	{"type": "supertrend_band"}	{"type": "trailing_stop"}	{"rules": ["price_sideways_inside_atr_band"], "version": "v2"}	{"base": 2}
vortex_directional_cross	trend	both	trend	v2	v2	global_standardized	f	30	symbol:21600s	2	{"rules": ["vortex_plus_crosses_above_minus"], "version": "v2"}	{"rules": ["vortex_minus_crosses_above_plus"], "version": "v2"}	{"rules": ["opposite_vortex_cross"], "version": "v2"}	{"rules": ["opposite_vortex_cross"], "version": "v2"}	["double_intent_conflict", "symbol_direction_conflict"]	{"policy": "symbol", "seconds": 21600}	{"single_symbol_single_direction": true, "atr_stop_required": true, "rr_target_required": true, "max_positions": 5, "risk_per_trade_pct": 1.5}	f	t	0	0	0	ready	\N	\N	2026-03-19 06:49:08.759366+00	2026-03-19 06:49:08.759367+00	{"type": "atr", "multiplier": 1.5}	{"type": "rr", "ratio": 2.0}	{"rules": ["vortex_lines_converge"], "version": "v2"}	{"base": 2}
bollinger_squeeze_breakout	breakout	both	breakout	v2	v2	global_standardized	t	12	symbol:21600s	3	{"rules": ["bandwidth_below_percentile", "price_breaks_upper_band", "volume_spike"], "version": "v2"}	{"rules": ["bandwidth_below_percentile", "price_breaks_lower_band", "volume_spike"], "version": "v2"}	{"rules": ["price_returns_inside_bands"], "version": "v2"}	{"rules": ["price_returns_inside_bands"], "version": "v2"}	["double_intent_conflict", "symbol_direction_conflict"]	{"policy": "symbol", "seconds": 21600}	{"single_symbol_single_direction": true, "atr_stop_required": true, "rr_target_required": true, "max_positions": 5, "risk_per_trade_pct": 1.5}	f	t	0	0	0	ready	\N	\N	2026-03-19 06:49:08.759368+00	2026-03-19 06:49:08.759368+00	{"type": "atr", "multiplier": 1.5}	{"type": "rr", "ratio": 2.5}	{"rules": ["breakout_fails_next_3_bars"], "version": "v2"}	{"breakout": 3}
moving_momentum	trend	both	trend	v2	v2	global_standardized	f	25	symbol:21600s	2	{"rules": ["ma20_above_ma150", "macd_bullish_cross", "stoch_oversold_recovery"], "version": "v2"}	{"rules": ["ma20_below_ma150", "macd_bearish_cross", "stoch_overbought_rejection"], "version": "v2"}	{"rules": ["macd_cross_down"], "version": "v2"}	{"rules": ["macd_cross_up"], "version": "v2"}	["double_intent_conflict", "symbol_direction_conflict"]	{"policy": "symbol", "seconds": 21600}	{"single_symbol_single_direction": true, "atr_stop_required": true, "rr_target_required": true, "max_positions": 5, "risk_per_trade_pct": 1.5}	f	t	0	0	0	ready	\N	\N	2026-03-19 06:49:08.759369+00	2026-03-19 06:49:08.759369+00	{"type": "atr", "multiplier": 1.7}	{"type": "rr", "ratio": 2.0}	{"rules": ["ma_slope_flat"], "version": "v2"}	{"base": 2}
fibonacci_pullback_continuation	pullback	both	pullback	v2	v2	global_standardized	f	35	symbol:21600s	2	{"rules": ["price_above_ma200", "pullback_in_38_61_zone", "bullish_trigger_candle"], "version": "v2"}	{"rules": ["price_below_ma200", "pullback_in_38_61_zone", "bearish_trigger_candle"], "version": "v2"}	{"rules": ["price_breaks_previous_swing_low"], "version": "v2"}	{"rules": ["price_breaks_previous_swing_high"], "version": "v2"}	["double_intent_conflict", "symbol_direction_conflict"]	{"policy": "symbol", "seconds": 21600}	{"single_symbol_single_direction": true, "atr_stop_required": true, "rr_target_required": true, "max_positions": 5, "risk_per_trade_pct": 1.5}	f	t	0	0	0	ready	\N	\N	2026-03-19 06:49:08.75937+00	2026-03-19 06:49:08.75937+00	{"type": "swing_below_above"}	{"type": "previous_swing_target"}	{"rules": ["fib_zone_breaks"], "version": "v2"}	{"base": 2}
macd_impulse	trend	both	trend	v2	v2	global_standardized	t	18	symbol:21600s	2	{"rules": ["macd_above_signal", "histogram_positive", "close_above_recent_high"], "version": "v2"}	{"rules": ["macd_below_signal", "histogram_negative", "close_below_recent_low"], "version": "v2"}	{"rules": ["histogram_turns_negative"], "version": "v2"}	{"rules": ["histogram_turns_positive"], "version": "v2"}	["double_intent_conflict", "symbol_direction_conflict"]	{"policy": "symbol", "seconds": 21600}	{"single_symbol_single_direction": true, "atr_stop_required": true, "rr_target_required": true, "max_positions": 5, "risk_per_trade_pct": 1.5}	f	t	0	0	0	ready	\N	\N	2026-03-19 06:49:08.759371+00	2026-03-19 06:49:08.759372+00	{"type": "atr", "multiplier": 1.5}	{"type": "rr", "ratio": 2.0}	{"rules": ["macd_flat"], "version": "v2"}	{"base": 2}
fisher_reversal	reversal	both	reversal	v2	v2	global_standardized	f	50	symbol:21600s	1	{"rules": ["fisher_crosses_up_previous", "fisher_extreme_negative_zone"], "version": "v2"}	{"rules": ["fisher_crosses_down_previous", "fisher_extreme_positive_zone"], "version": "v2"}	{"rules": ["fisher_peak"], "version": "v2"}	{"rules": ["fisher_trough"], "version": "v2"}	["double_intent_conflict", "symbol_direction_conflict"]	{"policy": "symbol", "seconds": 21600}	{"single_symbol_single_direction": true, "atr_stop_required": true, "rr_target_required": true, "max_positions": 5, "risk_per_trade_pct": 1.5}	f	t	0	0	0	ready	\N	\N	2026-03-19 06:49:08.759372+00	2026-03-19 06:49:08.759373+00	{"type": "recent_swing"}	{"type": "rr", "ratio": 1.8}	{"rules": ["fisher_stays_flat"], "version": "v2"}	{"base": 1}
divergence_reversal_suite	reversal	both	reversal	v2	v2	global_standardized	f	55	symbol:21600s	1	{"rules": ["price_lower_low", "indicator_higher_low"], "version": "v2"}	{"rules": ["price_higher_high", "indicator_lower_high"], "version": "v2"}	{"rules": ["trend_continuation_resumes"], "version": "v2"}	{"rules": ["trend_continuation_resumes"], "version": "v2"}	["double_intent_conflict", "symbol_direction_conflict"]	{"policy": "symbol", "seconds": 21600}	{"single_symbol_single_direction": true, "atr_stop_required": true, "rr_target_required": true, "max_positions": 5, "risk_per_trade_pct": 1.5}	f	t	0	0	0	ready	\N	\N	2026-03-19 06:49:08.759374+00	2026-03-19 06:49:08.759374+00	{"type": "swing_low_high"}	{"type": "mid_range"}	{"rules": ["divergence_disappears"], "version": "v2"}	{"base": 1}
structure_breakout	breakout	both	breakout	v2	v2	global_standardized	f	22	symbol:21600s	2	{"rules": ["descending_trendline_break", "triangle_breakout", "double_bottom_neckline_break"], "version": "v2"}	{"rules": ["ascending_trendline_break", "triangle_breakdown", "double_top_neckline_break"], "version": "v2"}	{"rules": ["return_inside_structure"], "version": "v2"}	{"rules": ["return_inside_structure"], "version": "v2"}	["double_intent_conflict", "symbol_direction_conflict"]	{"policy": "symbol", "seconds": 21600}	{"single_symbol_single_direction": true, "atr_stop_required": true, "rr_target_required": true, "max_positions": 5, "risk_per_trade_pct": 1.5}	f	t	0	0	0	ready	\N	\N	2026-03-19 06:49:08.759375+00	2026-03-19 06:49:08.759375+00	{"type": "atr", "multiplier": 1.6}	{"type": "pattern_projection"}	{"rules": ["false_breakout"], "version": "v2"}	{"base": 2}
stochastic_exhaustion_reentry	reversal	both	reversal	v2	v2	global_standardized	f	60	symbol:21600s	1	{"rules": ["stochastic_below_20", "price_breaks_trigger_high"], "version": "v2"}	{"rules": ["stochastic_above_80", "price_breaks_trigger_low"], "version": "v2"}	{"rules": ["stochastic_above_70"], "version": "v2"}	{"rules": ["stochastic_below_30"], "version": "v2"}	["double_intent_conflict", "symbol_direction_conflict"]	{"policy": "symbol", "seconds": 21600}	{"single_symbol_single_direction": true, "atr_stop_required": true, "rr_target_required": true, "max_positions": 5, "risk_per_trade_pct": 1.5}	f	t	0	0	0	ready	\N	\N	2026-03-19 06:49:08.759376+00	2026-03-19 06:49:08.759376+00	{"type": "atr", "multiplier": 1.4}	{"type": "rr", "ratio": 1.5}	{"rules": ["oscillator_stays_extreme"], "version": "v2"}	{"base": 1}
legacy_ichimoku_variants	legacy	both	any	legacy	legacy	legacy	f	999	symbol:300s	0	{}	{}	{}	{}	["legacy_blocked"]	{"policy": "none"}	{"mode": "legacy_candidate"}	t	f	0	0	0	ready	\N	legacy_candidate_removed_from_production	2026-03-19 06:49:08.759377+00	2026-03-19 06:49:08.759377+00	{}	{}	{}	{}
legacy_macd_variants	legacy	both	any	legacy	legacy	legacy	f	999	symbol:300s	0	{}	{}	{}	{}	["legacy_blocked"]	{"policy": "none"}	{"mode": "legacy_candidate"}	t	f	0	0	0	ready	\N	legacy_candidate_removed_from_production	2026-03-19 06:49:08.759378+00	2026-03-19 06:49:08.759378+00	{}	{}	{}	{}
legacy_rsi_variants	legacy	both	any	legacy	legacy	legacy	f	999	symbol:300s	0	{}	{}	{}	{}	["legacy_blocked"]	{"policy": "none"}	{"mode": "legacy_candidate"}	t	f	0	0	0	ready	\N	legacy_candidate_removed_from_production	2026-03-19 06:49:08.759379+00	2026-03-19 06:49:08.75938+00	{}	{}	{}	{}
legacy_fibonacci_variants	legacy	both	any	legacy	legacy	legacy	f	999	symbol:300s	0	{}	{}	{}	{}	["legacy_blocked"]	{"policy": "none"}	{"mode": "legacy_candidate"}	t	f	0	0	0	ready	\N	legacy_candidate_removed_from_production	2026-03-19 06:49:08.75938+00	2026-03-19 06:49:08.759381+00	{}	{}	{}	{}
legacy_vortex_variants	legacy	both	any	legacy	legacy	legacy	f	999	symbol:300s	0	{}	{}	{}	{}	["legacy_blocked"]	{"policy": "none"}	{"mode": "legacy_candidate"}	t	f	0	0	0	ready	\N	legacy_candidate_removed_from_production	2026-03-19 06:49:08.759381+00	2026-03-19 06:49:08.759383+00	{}	{}	{}	{}
legacy_moving_average_variants	legacy	both	any	legacy	legacy	legacy	f	999	symbol:300s	0	{}	{}	{}	{}	["legacy_blocked"]	{"policy": "none"}	{"mode": "legacy_candidate"}	t	f	0	0	0	ready	\N	legacy_candidate_removed_from_production	2026-03-19 06:49:08.759384+00	2026-03-19 06:49:08.759384+00	{}	{}	{}	{}
legacy_pattern_scanners	legacy	both	any	legacy	legacy	legacy	f	999	symbol:300s	0	{}	{}	{}	{}	["legacy_blocked"]	{"policy": "none"}	{"mode": "legacy_candidate"}	t	f	0	0	0	ready	\N	legacy_candidate_removed_from_production	2026-03-19 06:49:08.759385+00	2026-03-19 06:49:08.759385+00	{}	{}	{}	{}
legacy_statistical_explorers	legacy	both	any	legacy	legacy	legacy	f	999	symbol:300s	0	{}	{}	{}	{}	["legacy_blocked"]	{"policy": "none"}	{"mode": "legacy_candidate"}	t	f	0	0	0	ready	\N	legacy_candidate_removed_from_production	2026-03-19 06:49:08.759386+00	2026-03-19 06:49:08.759386+00	{}	{}	{}	{}
legacy_buy_sell_duplications	legacy	both	any	legacy	legacy	legacy	f	999	symbol:300s	0	{}	{}	{}	{}	["legacy_blocked"]	{"policy": "none"}	{"mode": "legacy_candidate"}	t	f	0	0	0	ready	\N	legacy_candidate_removed_from_production	2026-03-19 06:49:08.759387+00	2026-03-19 06:49:08.759387+00	{}	{}	{}	{}
\.


--
-- Data for Name: decision_trace_cold; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.decision_trace_cold (archive_id, correlation_id, strategy_version_id, context_hash, decision_hash, intent_hash, artifact_id, lifecycle_summary, terminal_state, created_at) FROM stdin;
\.


--
-- Data for Name: decision_trace_hot; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.decision_trace_hot (trace_id, correlation_id, strategy_version_id, context_hash, decision_hash, intent_hash, context_payload, decision_payload, intent_payload, expires_at, created_at) FROM stdin;
\.


--
-- Data for Name: exchange_capabilities; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.exchange_capabilities (id, exchange_code, market_type, supports_spot, supports_futures, supports_test_order, supports_quote_qty, supports_reduce_only, supports_leverage, supports_margin_mode, supports_hedge_mode, updated_at) FROM stdin;
bf4caa19-4cc8-453e-aff0-64d08e840e0c	binance	spot	t	f	t	t	f	f	f	f	2026-03-19 06:49:08.771997+00
6d9cf1ce-4f2b-4fbc-ad2b-71d7486bfbb1	binance	futures	f	t	t	t	t	t	t	t	2026-03-19 06:49:08.772403+00
1e9bcde1-b82f-44ea-a088-13d3b325c58f	bybit	spot	t	f	t	t	f	f	f	f	2026-03-19 06:49:08.772709+00
c0a852e5-1166-4614-80fc-d5a5897fd379	bybit	futures	f	t	t	t	t	t	t	t	2026-03-19 06:49:08.772998+00
f7ebcfc8-9472-4539-ae36-8b4fcd03315d	okx	spot	t	f	t	t	f	f	f	f	2026-03-19 06:49:08.77329+00
c23a8075-809e-4d7b-acb9-80b823fbe94d	okx	futures	f	t	t	t	t	t	t	t	2026-03-19 06:49:08.773551+00
\.


--
-- Data for Name: exchange_registry; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.exchange_registry (id, exchange_code, exchange_name, status, supported_market_types, supports_testnet, supports_live, health_status, rate_limit_status, adapter_version, updated_at) FROM stdin;
b777a8ae-8dfe-4526-b137-e16e52f144e0	binance	Binance	active	["spot", "futures"]	t	f	healthy	ok	v1	2026-03-19 06:49:08.770031+00
c00c9a77-6c10-4a9b-bc7d-5e20d8e93bd4	bybit	Bybit	active	["spot", "futures"]	t	f	healthy	ok	v1-alpha	2026-03-19 06:49:08.770435+00
5ca88596-b2ab-49b3-99b6-68482400cebb	okx	OKX	active	["spot", "futures"]	t	f	healthy	ok	v1-alpha	2026-03-19 06:49:08.770729+00
\.


--
-- Data for Name: execution_correction_events; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.execution_correction_events (id, execution_metric_id, user_id, correction_type, reason_code, note, patch_payload, created_at) FROM stdin;
\.


--
-- Data for Name: execution_events; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.execution_events (id, bot_profile_id, exchange, symbol, side, quantity, mock_price, execution_status, response_payload, note, created_at) FROM stdin;
\.


--
-- Data for Name: execution_intent_events; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.execution_intent_events (id, intent_id, event_type, event_status, external_order_id, payload, created_at) FROM stdin;
\.


--
-- Data for Name: execution_intents; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.execution_intents (intent_id, strategy_id, strategy_version_id, symbol, side, order_type, quantity, price_reference, decision_hash, context_hash, intent_hash, correlation_id, status, created_at, account_id) FROM stdin;
\.


--
-- Data for Name: execution_lifecycle_events; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.execution_lifecycle_events (id, execution_metric_id, user_id, event_name, event_timestamp, payload) FROM stdin;
\.


--
-- Data for Name: execution_metrics; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.execution_metrics (id, user_id, symbol, order_id, exchange_order_id, order_type, side, quote_qty, mid_price, mid_price_timestamp, price_avg, executed_qty, slippage_pct, execution_time_ms, status, strategy_type, volatility_regime, volatility_pct, execution_quality_score, state_machine_path, created_at, client_order_id, final_status, failure_code, submitted_at, ack_at, final_at, validation_snapshot_id, raw_exchange_status, exchange, market_type, environment) FROM stdin;
\.


--
-- Data for Name: execution_policies; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.execution_policies (id, strategy_type, execution_style, order_preference, timeout_seconds, fallback_behavior, partial_fill_tolerance_pct, execution_urgency, retry_limit, is_active, created_at, updated_at) FROM stdin;
a7b86186-fede-4379-b6dc-5d078c0f3a46	breakout	aggressive	market_first	4	market_fallback	85	high	1	t	2026-03-19 06:49:08.734141+00	2026-03-19 06:49:08.734144+00
571cc674-e7b7-48a6-b302-8f58a2bd69cb	mean_reversion	passive	limit_first	12	cancel_no_fill	35	low	3	t	2026-03-19 06:49:08.734153+00	2026-03-19 06:49:08.734154+00
68c615c4-89c4-4e79-8e90-45a6dc073274	trend_following	balanced	limit_first	8	market_fallback	60	medium	2	t	2026-03-19 06:49:08.734159+00	2026-03-19 06:49:08.734159+00
45b474bf-85d8-4cf7-b1ec-fa322d41afe5	volatility_expansion	balanced	market_first	6	limit_retry_then_market	70	medium	2	t	2026-03-19 06:49:08.734163+00	2026-03-19 06:49:08.734163+00
e4f5ff5c-ff10-427b-b3ef-82949f313942	spot_pullback_v1	balanced	limit_first	8	market_fallback	60	medium	1	t	2026-03-19 06:49:08.734166+00	2026-03-19 06:49:08.734167+00
b033ec85-d0b1-4764-9745-fc9e59211758	spot_range_reversion_v1	balanced	limit_first	10	market_fallback	55	low	1	t	2026-03-19 06:49:08.734171+00	2026-03-19 06:49:08.734172+00
8b7ca4be-b6ff-435d-8e19-76d5df623499	spot_volatility_breakout_v1	aggressive	market_first	6	market_fallback	70	high	2	t	2026-03-19 06:49:08.734175+00	2026-03-19 06:49:08.734175+00
\.


--
-- Data for Name: execution_state_transitions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.execution_state_transitions (id, execution_event_id, state, sequence, details, occurred_at) FROM stdin;
\.


--
-- Data for Name: external_provider_credentials; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.external_provider_credentials (provider, api_key_encrypted, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: failed_events; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.failed_events (id, event_type, entity_type, entity_id, payload, error_message, status, retry_count, max_retry, next_retry_at, created_at, updated_at, resolved_at) FROM stdin;
\.


--
-- Data for Name: family_outcome_memory; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.family_outcome_memory (id, family, regime, sample_count, hit_rate, avg_return, volatility_success, conflict_success, solo_vs_combo_success, updated_at) FROM stdin;
\.


--
-- Data for Name: hardening_checklist_runs; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.hardening_checklist_runs (id, score, critical_blocked, readiness_status, checklist_items, summary, created_at) FROM stdin;
\.


--
-- Data for Name: indicator_computation_cache; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.indicator_computation_cache (id, cache_key, symbol, timeframe, bar_close_time, indicator_name, params_version, payload, expires_at, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: learning_decision_events; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.learning_decision_events (id, user_id, symbol, decision, source_strategies, family_scores, regime_snapshot, risk_snapshot, entry_price, exit_price, max_favorable_excursion, max_adverse_excursion, hold_duration_minutes, outcome_label, pnl_normalized, stop_hit, tp_hit, timed_exit, invalidated, strategy_id, strategy_family, scanner_result_id, pending_signal_id, position_id, created_at, closed_at) FROM stdin;
\.


--
-- Data for Name: learning_recommendations; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.learning_recommendations (id, strategy_id, family, recommendation_type, recommendation_value, note, severity, is_applied, created_at, applied_at) FROM stdin;
\.


--
-- Data for Name: live_activation_config; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.live_activation_config (id, exchange, market_type, safe_mode_enabled, live_mode_enabled, symbol_whitelist, max_position_pct, leverage_cap, max_trades_per_hour, max_notional_exposure, kill_switch_enabled, disable_futures, ip_whitelist_ready, trading_permission_ready, updated_at) FROM stdin;
global	binance	futures_testnet	t	f	[]	0.1	1	6	150	f	f	f	f	2026-03-19 08:43:33.297146+00
\.


--
-- Data for Name: manual_override_log; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.manual_override_log (override_id, admin_id, action_type, reason, payload, "timestamp") FROM stdin;
\.


--
-- Data for Name: paper_positions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.paper_positions (id, user_id, bot_profile_id, symbol, market_type, side, quantity, leverage, entry_price, stop_loss, take_profit, status, unrealized_pnl, realized_pnl, opened_at, closed_at, updated_at) FROM stdin;
2e0b4e67-5556-4acf-a0ee-053ed87f8e9a	059dab08-b67a-43a5-ba71-e0721d317f78	cbccc782-c5d9-452f-b167-03bce90b16a2	BTCUSDT	futures	long	0.4	3	100	99	102	stop_hit	-2.90316	-2.90316	2026-03-19 07:36:21.105906+00	2026-03-19 07:36:27.880005+00	2026-03-19 07:36:27.880666+00
6e275418-6445-4412-a4b9-72e36eaa8181	3f01b548-f272-4c42-95fa-80d7734e9578	afe2c4d8-f226-4f10-a712-a3f522335aeb	BTCUSDT	futures	long	0.4	3	100	99	102	stop_hit	-2.90316	-2.90316	2026-03-19 07:35:54.183129+00	2026-03-19 07:36:27.879933+00	2026-03-19 07:36:27.880668+00
\.


--
-- Data for Name: pending_signals; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.pending_signals (id, signal_id, user_id, symbol, strategy_code, confidence, mode, status, order_position_id, created_at, decided_at, decision_note, strategy_weight, allocation_source, meta_engine_decision, previous_state, current_state, blocked_reason_code, blocked_reason_message, blocked_solution_hint, requires_manual_approval, execution_eligible, bot_profile_id, risk_policy_id, exchange_connection_id, created_order_intent_id, runtime_owner, last_eligibility_check_at, last_transition_at) FROM stdin;
\.


--
-- Data for Name: permission_drift_events; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.permission_drift_events (id, user_id, exchange, old_permissions, new_permissions, old_can_trade, new_can_trade, is_critical, created_at) FROM stdin;
\.


--
-- Data for Name: portfolio_exposure_snapshot; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.portfolio_exposure_snapshot (id, "timestamp", user_id, symbol, position_size, notional, strategy_id, cluster_id, exposure_weight) FROM stdin;
115be1fc-f872-4848-b814-01f8096b29d6	2026-03-19 07:35:18.034126+00	94fa99c0-f373-4f00-95a8-7677ef165fa9	BTCUSDT	40	40	faz2_integrity_strategy	L1	0.4
53934eb7-1133-4a9c-ac1e-9f8657724da4	2026-03-19 07:35:21.803272+00	c5fa2cfb-138f-4ba2-8836-b0aebadc2e9b	BTCUSDT	40	40	faz2_integrity_strategy	L1	0.4
df7d5394-6583-4721-9210-1ccc667bdba3	2026-03-19 07:35:54.126418+00	3f01b548-f272-4c42-95fa-80d7734e9578	BTCUSDT	40	40	faz2_integrity_strategy	L1	0.4
6afa8f13-772f-4302-b192-acaa96f9715b	2026-03-19 07:36:21.076995+00	059dab08-b67a-43a5-ba71-e0721d317f78	BTCUSDT	40	40	faz2_integrity_strategy	L1	0.4
\.


--
-- Data for Name: position_ledger_events; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.position_ledger_events (id, position_id, event_type, payload, created_at) FROM stdin;
4a4410e3-7a9d-4637-9b72-5bf01873e3c6	6e275418-6445-4412-a4b9-72e36eaa8181	execution_order_released	{"intent_id": "0c7b03f1-da69-4e79-8ff9-95e4c048675d", "intent_token": "3166ce93-18eb-44c3-9ff1-1cbfde5b663a", "symbol": "BTCUSDT"}	2026-03-19 07:35:54.184252+00
2c0a59bf-b499-48fa-9189-46a4946428e4	2e0b4e67-5556-4acf-a0ee-053ed87f8e9a	execution_order_released	{"intent_id": "f142e6db-d723-4600-84df-2a3bd40390f3", "intent_token": "ba5c9913-273e-4c7e-8ec1-45924f7380e6", "symbol": "BTCUSDT"}	2026-03-19 07:36:21.106363+00
7cac4266-a703-4d5c-b49c-a9104bbbaaf4	6e275418-6445-4412-a4b9-72e36eaa8181	trade_close	{"reason": "stop_hit", "exit_price": 97.5807, "realized_pnl": -2.90316, "lifecycle_state": "STOPPED"}	2026-03-19 07:36:27.881903+00
8c2436ed-b65c-4c06-8830-240dc2933a24	2e0b4e67-5556-4acf-a0ee-053ed87f8e9a	trade_close	{"reason": "stop_hit", "exit_price": 97.5807, "realized_pnl": -2.90316, "lifecycle_state": "STOPPED"}	2026-03-19 07:36:27.881909+00
\.


--
-- Data for Name: positions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.positions (position_id, user_id, symbol, size, entry_price, current_price, unrealized_pnl, leverage, strategy_id, cluster_id, status, created_at, updated_at) FROM stdin;
6e275418-6445-4412-a4b9-72e36eaa8181	3f01b548-f272-4c42-95fa-80d7734e9578	BTCUSDT	0.4	100	100	0	3	faz2_integrity_strategy	L1	open	2026-03-19 07:35:54.183129+00	2026-03-19 07:35:54.185206+00
2e0b4e67-5556-4acf-a0ee-053ed87f8e9a	059dab08-b67a-43a5-ba71-e0721d317f78	BTCUSDT	0.4	100	100	0	3	faz2_integrity_strategy	L1	open	2026-03-19 07:36:21.105906+00	2026-03-19 07:36:21.106814+00
\.


--
-- Data for Name: regime_snapshots; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.regime_snapshots (regime_snapshot_id, timestamp_utc, symbol, timeframe, strategy_version_id, volatility_regime, trend_regime, liquidity_regime, market_state_features, feature_set_version, regime_score, regime_label, regime_hash, created_at) FROM stdin;
\.


--
-- Data for Name: release_gate_overrides; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.release_gate_overrides (id, admin_user_id, reason_code, reason_note, release_gate_snapshot, deploy_context, created_at, expires_at, revoked_at, last_used_at, used_deploy_count) FROM stdin;
\.


--
-- Data for Name: replay_equity_points; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.replay_equity_points (id, replay_run_id, user_id, point_timestamp, equity, pnl_delta, drawdown_pct, created_at) FROM stdin;
\.


--
-- Data for Name: replay_executions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.replay_executions (id, replay_run_id, user_id, symbol, timeframe, signal, direction, market_price, simulated_fill_price, simulated_latency_ms, simulated_slippage_pct, lifecycle, status, risk_tags, candle_timestamp, created_at) FROM stdin;
\.


--
-- Data for Name: replay_runs; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.replay_runs (id, user_id, exchange, market_type, environment, symbol, timeframe, strategy_type, candles_processed, executions_count, filled_count, canceled_count, avg_simulated_latency_ms, avg_simulated_slippage_pct, metrics, status, started_at, completed_at) FROM stdin;
\.


--
-- Data for Name: risk_clusters; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.risk_clusters (cluster_id, symbols, cluster_type, correlation_score, risk_weight, created_at, updated_at) FROM stdin;
L1	["BTCUSDT", "ETHUSDT"]	crypto_market_beta	0.82	1	2026-03-19 07:35:18.028458+00	2026-03-19 07:35:18.028461+00
L2	["SOLUSDT", "AVAXUSDT", "LINKUSDT"]	high_beta_alts	0.76	1.15	2026-03-19 07:35:18.028462+00	2026-03-19 07:35:18.028462+00
\.


--
-- Data for Name: risk_exposure_groups; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.risk_exposure_groups (id, name, label, symbols, max_group_open_positions, max_group_directional_positions, max_group_risk_pct, created_at, updated_at) FROM stdin;
d62a51ea-df31-4753-bfad-6dfdab2c793d	majors	Majors Cluster (BTC, ETH)	["BTCUSDT", "ETHUSDT"]	6	4	22	2026-03-19 06:49:08.73865+00	2026-03-19 06:49:08.738653+00
c56172da-a8be-437d-8ba0-2b92fd8cfb65	high_beta_alts	High Beta Alts (SOL, AVAX, LINK)	["SOLUSDT", "AVAXUSDT", "LINKUSDT"]	5	3	18	2026-03-19 06:49:08.738658+00	2026-03-19 06:49:08.738658+00
42d78eef-c071-4b30-9191-be6c082c7eb9	mid_cap	Mid Cap & Others (Fallback Group)	[]	8	5	20	2026-03-19 06:49:08.738662+00	2026-03-19 06:49:08.738662+00
\.


--
-- Data for Name: risk_orchestrator_policies; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.risk_orchestrator_policies (id, reference_equity_usd, account_max_notional_pct, symbol_max_notional_pct, strategy_max_concurrent_positions, strategy_cooldown_seconds, max_order_frequency_per_min, max_order_burst_per_10s, daily_loss_limit_pct, duplicate_suppression_window_seconds, updated_at) FROM stdin;
global	10000	60	25	3	60	6	3	5	300	2026-03-19 06:49:08.749672+00
\.


--
-- Data for Name: risk_policies; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.risk_policies (id, user_id, name, position_size_pct, atr_stop_multiplier, risk_reward_ratio, daily_loss_cutoff_pct, max_open_positions, max_leverage, spread_limit_bps, slippage_limit_bps, min_liquidity_usdt, created_at, updated_at) FROM stdin;
3f7a00f0-9971-45f1-a3a6-730ce176d496	c89bb203-b2e8-4230-ba9a-a01e603ae93e	Starter Safe (Auto)	1	1.8	1.8	3	2	2	25	35	150000	2026-03-19 07:11:31.592589+00	2026-03-19 07:11:31.592589+00
\.


--
-- Data for Name: risk_policy_audit_events; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.risk_policy_audit_events (id, replay_run_id, user_id, strategy_version, regime_bucket, drawdown, exposure_breach, reject_count, created_at) FROM stdin;
\.


--
-- Data for Name: runtime_scan_candidates; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.runtime_scan_candidates (id, symbol, market_type, scan_timestamp, strategy_signal, risk_score, decision, confidence) FROM stdin;
\.


--
-- Data for Name: scanner_fallback_events; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.scanner_fallback_events (id, run_id, event_type, requested_mode, effective_mode, trigger_metric, threshold_breach, exit_reason, cycle_snapshot, created_at) FROM stdin;
\.


--
-- Data for Name: scanner_performance_snapshots; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.scanner_performance_snapshots (id, user_id, run_id, stage, metrics, created_at) FROM stdin;
\.


--
-- Data for Name: signal_events; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.signal_events (id, bot_profile_id, user_id, symbol, market_type, timeframe, strategy_id, signal, direction, confidence, reason_codes, generated_at) FROM stdin;
\.


--
-- Data for Name: state_rebuild_logs; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.state_rebuild_logs (id, rebuild_type, status, trigger_source, details, started_at, finished_at) FROM stdin;
850b990d-3341-44b4-b25c-6f050fbc3166	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 06:49:08.781747+00	2026-03-19 06:49:08.789409+00
4c4db20b-c7a1-4baf-a94f-13a1f4fca832	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 07:07:45.709984+00	2026-03-19 07:07:45.718329+00
67438634-7831-41ff-a229-c7cb00899c69	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 07:07:56.229517+00	2026-03-19 07:07:56.237543+00
0a241231-f395-4cc4-b576-dbce010bce3f	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 07:08:27.255141+00	2026-03-19 07:08:27.26325+00
adde7aa1-b721-421e-8487-73ae56661c35	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 07:09:07.835466+00	2026-03-19 07:09:07.843287+00
1a38a39b-5890-420a-a6cf-87dc6ac81cb9	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 07:28:15.25486+00	2026-03-19 07:28:15.262482+00
973dd34b-ab47-4b0b-bc1a-039fcac41d82	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 07:28:23.426807+00	2026-03-19 07:28:23.434909+00
5ccdc91d-84e0-4b4c-acbb-c532a0d046da	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 07:28:39.394667+00	2026-03-19 07:28:39.463394+00
88cc7c76-855c-4dfc-9be2-7be79375aa39	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 07:29:43.34163+00	2026-03-19 07:29:43.348949+00
d2978cc2-974a-4034-8982-a754039f1b86	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 07:30:43.54368+00	2026-03-19 07:30:43.552836+00
12c71d18-d1c0-46ed-b90b-1095a0abed5d	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 07:34:16.238375+00	2026-03-19 07:34:16.245865+00
d7f3913d-abd4-4e3e-ac74-56b9627ffef1	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 07:34:27.176265+00	2026-03-19 07:34:27.186565+00
52530c60-742b-4946-8720-8779fc86aafd	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 07:34:35.343552+00	2026-03-19 07:34:35.351859+00
7aae80a6-faab-402a-b7b8-a2ebe75b7f7b	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 07:35:15.044147+00	2026-03-19 07:35:15.052617+00
9b737eec-7406-467b-896f-5957c2cb42de	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 07:35:33.828313+00	2026-03-19 07:35:33.835922+00
7560d08b-bc8b-4d0a-8481-61f1bdd0b40f	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 07:35:44.259576+00	2026-03-19 07:35:44.268133+00
2e592129-2929-4492-afab-283cc918af04	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 07:39:16.357762+00	2026-03-19 07:39:16.365987+00
e939828d-f595-4ed8-bc47-25a5c26a7fbf	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 07:49:23.741755+00	2026-03-19 07:49:23.749974+00
11ea5245-1101-42d7-9b9d-b8e2a9c203ee	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 07:49:33.550823+00	2026-03-19 07:49:33.55876+00
5bb4e3ff-78c4-402e-bf94-8c24fb138beb	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 07:49:53.245554+00	2026-03-19 07:49:53.254771+00
31a64829-6250-4650-b41d-0ff8b5c5fe05	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 07:50:03.43756+00	2026-03-19 07:50:03.446307+00
fbe85480-b1dc-4b09-b391-c86b89dcb613	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 07:51:12.91353+00	2026-03-19 07:51:12.921239+00
fdde9683-e95e-4219-8064-24649cfd874b	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 07:56:20.617831+00	2026-03-19 07:56:20.625691+00
63a18e64-86a4-47e3-b213-a419e1fff988	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 07:56:59.536658+00	2026-03-19 07:56:59.544468+00
a9209713-b00b-4743-a7bf-c92d0a335715	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 07:57:38.232143+00	2026-03-19 07:57:38.23988+00
67cbfb65-0e23-4b0f-a51e-25bf02999dd4	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 07:58:35.07616+00	2026-03-19 07:58:35.084913+00
291a9ce8-e429-4c5f-bcd2-a1d986109206	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 07:59:38.835089+00	2026-03-19 07:59:38.842623+00
f37d5836-13bd-44e9-a020-9e456cdb71e7	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 08:01:49.76099+00	2026-03-19 08:01:49.76888+00
c6362b59-6a2d-4c98-8975-f49bb5bd6e7b	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 08:02:29.250884+00	2026-03-19 08:02:29.259138+00
2b234648-2649-4744-ba2b-512205b4d74c	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 08:04:12.028449+00	2026-03-19 08:04:12.03627+00
846a5ed5-5901-42d2-968d-3679c44df2f3	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 08:05:14.748131+00	2026-03-19 08:05:14.755827+00
9adeb988-f7a5-4544-abab-511ff33ead07	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 08:29:03.538467+00	2026-03-19 08:29:03.546678+00
3a40e9de-91ef-4a93-9932-a4566aec6fe1	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 08:29:57.631669+00	2026-03-19 08:29:57.639333+00
1c2e0816-a8f6-4042-8849-5b0264b3f7f3	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 08:31:07.779844+00	2026-03-19 08:31:07.788506+00
e08f86e3-29bf-4f4b-8f78-72d0e11821fe	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 08:36:02.259414+00	2026-03-19 08:36:02.267199+00
cccd1b2f-d4c8-45ed-b310-0dd3d082e2a0	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 08:40:26.15566+00	2026-03-19 08:40:26.163775+00
c26f7137-2147-405c-b98c-46d8ba736a9a	full_runtime_state	completed	startup	{"open_positions_count": 0, "running_bots_count": 0, "position_sample": []}	2026-03-19 08:43:42.45225+00	2026-03-19 08:43:42.460496+00
\.


--
-- Data for Name: strategy_allocations; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.strategy_allocations (strategy_id, capital_weight, max_capital, current_capital, confidence_score, performance_score, state, expected_return, realized_return, signal_decay, execution_quality_score, updated_at) FROM stdin;
faz2_integrity_strategy	1	10000	0	0.65	64.1026	ACTIVE	3.9	2.5	0	75	2026-03-19 07:36:21.074569+00
\.


--
-- Data for Name: strategy_definitions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.strategy_definitions (strategy_id, name, code, description, owner_type, created_by, status, active_version_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: strategy_family_gates; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.strategy_family_gates (family, is_enabled, long_threshold, short_threshold, min_strategy_count, max_conflict_score, regime_match_required, risk_clear_required, reversal_extra_confirmation, created_at, updated_at) FROM stdin;
breakout	t	4	4	1	2	t	t	f	2026-03-19 06:49:08.767588+00	2026-03-19 08:43:42.440642+00
pullback	t	4	4	1	2	t	t	f	2026-03-19 06:49:08.767589+00	2026-03-19 08:43:42.440649+00
reversal	t	3	3	1	1.5	t	t	t	2026-03-19 06:49:08.76759+00	2026-03-19 08:43:42.440655+00
trend	t	5	5	1	2	t	t	f	2026-03-19 06:49:08.767585+00	2026-03-19 08:43:42.440631+00
\.


--
-- Data for Name: strategy_observability_events; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.strategy_observability_events (id, selection_cycle_id, audit_log_id, bot_profile_id, user_id, symbol, strategy_id, strategy_name, event_type, market_regime, multiplier_version, multiplier_set, base_score, adjusted_score, score_delta, selection_rank, trend_strength, relative_volume, hard_gate_pass, threshold_pass, rejection_reason, metadata, created_at) FROM stdin;
\.


--
-- Data for Name: strategy_outcome_memory; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.strategy_outcome_memory (id, strategy_id, direction, regime, sample_count, hit_rate, avg_return, avg_mfe, avg_mae, false_allow_rate, false_reject_rate, recent_rolling_score, decay_adjusted_quality_score, updated_at) FROM stdin;
\.


--
-- Data for Name: strategy_regime_bindings; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.strategy_regime_bindings (binding_id, strategy_version_id, allowed_regimes, blocked_regimes, priority, gating_policy_version, created_by, created_at) FROM stdin;
\.


--
-- Data for Name: strategy_templates; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.strategy_templates (id, name, strategy_type, parameters, is_active, created_by, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: strategy_versions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.strategy_versions (version_id, strategy_id, version_number, config_json, config_schema_version, created_by, created_at, version_hash) FROM stdin;
\.


--
-- Data for Name: symbol_selection_watchlists; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.symbol_selection_watchlists (id, user_id, name, source, exchange, market_type, symbols, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: system_alerts; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.system_alerts (id, alert_type, severity, message, details, status, occurrences, last_triggered_at, created_at, updated_at, fingerprint, entity_key, root_cause_code, state_key, delivery_status) FROM stdin;
bb9f036e-7a74-4bef-a4b9-68b2b7413a3b	release_gate_blocked	CRITICAL	Release gate BLOCKED	{"reasons": ["permission_check_fail", "execution_quality_score_warning", "kill_switch_not_tested", "proof_pipeline_empty", "live_mode_disabled"], "environment": "prod"}	open	200	2026-03-19 08:43:33.294466+00	2026-03-19 06:49:42.585021+00	2026-03-19 08:43:33.295055+00	67e0bac46e45e360f1ef30fddbad9c8b2a0cbec688a3c53fb5861a3050ca72f7	prod	permission_check_fail	blocked	{"status": "DEDUPED", "dedupe_window_seconds": 600}
\.


--
-- Data for Name: test_table; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.test_table (id, marker) FROM stdin;
6	backup_test
\.


--
-- Data for Name: testnet_execution_logs; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.testnet_execution_logs (id, user_id, symbol, strategy_direction, expected_price, fill_price, slippage, execution_latency, execution_quality_score, status, state_machine_path, permission_snapshot, release_gate_status, details, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: universe_rollout_state; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.universe_rollout_state (id, current_stage, recommended_stage, recommendation_payload, requires_admin_approval, approved_by, approved_at, updated_at) FROM stdin;
\.


--
-- Data for Name: user_decision_traces; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.user_decision_traces (id, user_id, trace_scope, trace_type, entity_id, strategy_code, decision_status, reason_codes, reason_details, feature_snapshot, context_payload, created_at, expires_at, portfolio_risk_score, strategy_allocation_reason, cluster_risk_flag, meta_engine_decision, position_action_reason, risk_adjustment_reason, strategy_override_reason, hedge_recommendation, risk_reduction_score, correlation_basis) FROM stdin;
267db9ea-13b8-4fe8-8b48-833ddf0357fa	94fa99c0-f373-4f00-95a8-7677ef165fa9	execution	execution_preview	ca0f2159-19db-4f1e-a4d5-76989118dca0	faz2_integrity_strategy	VALID	["execution_preview_valid"]	[{"code": "execution_preview_valid", "title": "Execution Preview Valid", "description": "Execution preview policy kontrollerinden ge\\u00e7ti."}]	{"symbol": "BTCUSDT", "market_type": "futures", "side": "buy", "notional": 40.0, "size": 0.001, "risk_flags": ["stop_loss_missing_warning"], "strategy_weight": 1.0}	{"intent_type": "OPEN_POSITION", "position_id": null, "queue_mode": "ASSISTED", "normalized_order_payload": {"symbol": "BTCUSDT", "quote_asset": "USDT", "market_type": "futures", "side": "buy", "order_type": "market", "margin_mode": "isolated", "leverage": 3, "position_size_mode": "fixed_notional", "position_size_value": 40.0, "take_profit_mode": "none", "take_profit_value": 0.0, "stop_loss_mode": "none", "stop_loss_value": 0.0, "execution_mode": "manual", "strategy_binding": "faz2_integrity_strategy", "holding_profile": "intraday", "source_type": "manual", "source_ref_id": "evt-23a2650a", "scanner_signal_snapshot": {"signal_id": "evt-23a2650a", "timestamp": "2026-03-19T12:45:10Z"}, "exchange": "binance", "environment": "testnet", "account_label": "default", "exchange_connection_id": null, "venue_context": {"exchange": "binance", "market_type": "futures", "environment": "testnet", "account_label": "default", "exchange_connection_id": null, "allowed": false, "venue_state": "no_assigned_venues", "capability_match": false, "reason_codes": ["assignment_required"]}, "leverage_requested": 3, "leverage_recommended": 5, "leverage_applied": 3, "leverage_policy_mode": "hybrid_user_override", "leverage_clamp_reasons": [], "meta_strategy_summary": {"strategy_id": "faz2_integrity_strategy", "symbol": "BTCUSDT", "meta_engine_decision": "ALLOW", "allocation_source": "weight_based", "strategy_allocation_reason": "normal_allocation", "strategy_weight": 1.0, "state": "ACTIVE", "requested_notional": 40.0, "adjusted_notional": 40.0, "remaining_capital": 10000.0, "max_capital": 10000.0, "expected_return": 0.5, "realized_return": 2.5, "signal_decay": 0.0, "execution_quality_score": 75.0}, "portfolio_risk_impact": {"risk_score": 0.0067, "risk_flags": [], "decision": "ALLOW", "cluster_id": "L1", "current_portfolio_leverage": 0.004, "symbol_exposure_pct": 0.4, "cluster_exposure_pct": 0.4, "strategy_exposure_pct": 0.4, "single_trade_risk_pct": 0.4, "portfolio_state": {"base_capital": 10000.0, "current_capital": 10000.0, "intraday_drawdown_pct": 0.0, "total_drawdown_pct": 0.0}}, "strategy_conflict": {"conflict_detected": false, "winning_strategy": "faz2_integrity_strategy", "losing_strategy": null, "resolution_reason": "no_conflict", "conflict_count": 0, "strategy_conflict_warning": null}, "capital_rebalance": {"allocation_drift": 0.0, "strategy_performance_delta": 499.35, "risk_adjusted_return": 2.5, "events": [{"strategy_id": "faz2_integrity_strategy", "old_strategy_weight": 1.0, "new_strategy_weight": 1.0, "target_strategy_weight": 1.0, "capital_shift": 0.0, "throttle_signal": false, "allocation_drift": 0.0, "strategy_performance_delta": 499.35, "risk_adjusted_return": 2.5, "cadence_window_blocked": true, "minutes_since_last_rebalance": 0.0, "max_weight_shift_applied": false, "max_capital_shift_applied": false}], "governance_summary": {"cadence_window_minutes": 30, "max_weight_shift_per_cycle": 0.12, "max_capital_shift_pct": 0.2, "drift_threshold": 0.08, "cadence_blocked_strategies": 1, "weight_shift_capped_strategies": 0, "capital_shift_capped_strategies": 0}, "allocation_adjustment_notice": "rebalance_cadence_hold aktif: 1 strategy pencere i\\u00e7inde"}, "hedge_suggestion": {"hedge_symbol": null, "hedge_size": 0.0, "hedge_direction": null, "risk_reduction_score": 0.0, "correlation_basis": "insufficient_exposure", "recommended_action": "no_hedge_needed"}, "risk_engine": {"risk_decision": "ALLOW", "size_multiplier": 1.0, "adjusted_notional_usdt": 40.0, "adjusted_leverage": 3, "reason_codes": [], "warnings": [], "exposure_snapshot": {"wallet_usdt_balance": 10000.0, "open_exposure_usdt": 0, "pending_exposure_usdt": 0, "symbol_exposure_usdt": 0, "cluster_exposure_usdt": 0, "cluster_id": "majors", "proposed_notional_usdt": 40.0, "projected_total_exposure_usdt": 40.0, "projected_symbol_exposure_usdt": 40.0, "projected_cluster_exposure_usdt": 40.0}, "execution_quality": {"score": 100.0, "severity": "normal", "recommendation": "ALLOW", "components": {"stale_ratio": 0.0, "spread_ratio": 0.0, "slippage_ratio": 0.0, "latency_ratio": 0.0, "depth_penalty": 0.0, "partial_fill_rate": 0.0, "reject_rate": 0.0}, "metrics": {"snapshot_age_ms": 0.0, "spread_bps": 0.0, "slippage_pct": 0.0, "execution_latency_ms": 0.0, "orderbook_depth_score": 1.0, "partial_fill_rate": 0.0, "reject_rate": 0.0}}, "execution_quality_trend": {"ema_score": 100.0, "sample_count": 1, "warning_count": 0, "partial_fill_count": 0, "reject_count": 0, "warning_rate": 0.0, "partial_fill_rate": 0.0, "reject_rate": 0.0, "updated_at": "2026-03-19T07:35:18.038581+00:00"}, "cooldown_state": {"global": {"active": false, "remaining_seconds": 0, "expires_at": null, "reason": null}, "symbol": {"active": false, "remaining_seconds": 0, "expires_at": null, "reason": null}, "strategy": {"active": false, "remaining_seconds": 0, "expires_at": null, "reason": null}}, "kill_switch_active": false, "daily_loss": {"daily_loss_usdt": 0, "daily_loss_pct": 0.0}, "consecutive_losses": 0, "metrics": {"trade_risk_pct": 0.4, "projected_total_exposure_pct": 0.4, "projected_symbol_exposure_pct": 0.4, "projected_cluster_exposure_pct": 0.4, "snapshot_age_ms": 0.0, "spread_bps": 0.0, "execution_latency_ms": 0.0}}}, "preview_hash": "1f7465e9cad4cad594af1fe8d086a024f6cca551fbfabed61f7e997b41886f80", "meta_strategy_summary": {"strategy_id": "faz2_integrity_strategy", "symbol": "BTCUSDT", "meta_engine_decision": "ALLOW", "allocation_source": "weight_based", "strategy_allocation_reason": "normal_allocation", "strategy_weight": 1.0, "state": "ACTIVE", "requested_notional": 40.0, "adjusted_notional": 40.0, "remaining_capital": 10000.0, "max_capital": 10000.0, "expected_return": 0.5, "realized_return": 2.5, "signal_decay": 0.0, "execution_quality_score": 75.0}, "portfolio_risk_impact": {"risk_score": 0.0067, "risk_flags": [], "approval_required": false, "position_adjustment": {"applied": false, "requested_notional": 40.0, "adjusted_notional": 40.0, "adjustment_factor": 1.0}, "decision": "ALLOW", "cluster_id": "L1", "current_portfolio_leverage": 0.004, "symbol_exposure_pct": 0.4, "cluster_exposure_pct": 0.4, "strategy_exposure_pct": 0.4, "single_trade_risk_pct": 0.4, "portfolio_state": {"base_capital": 10000.0, "current_capital": 10000.0, "intraday_drawdown_pct": 0.0, "total_drawdown_pct": 0.0}, "limits": {"max_portfolio_leverage": 3.0, "max_symbol_exposure": 35.0, "max_cluster_exposure": 50.0, "max_strategy_exposure": 40.0, "max_single_trade_risk": 10.0, "max_intraday_drawdown": 5.0, "max_total_drawdown": 15.0}}, "strategy_conflict": {"conflict_detected": false, "winning_strategy": "faz2_integrity_strategy", "losing_strategy": null, "resolution_reason": "no_conflict", "conflict_count": 0, "strategy_conflict_warning": null}, "capital_rebalance": {"allocation_drift": 0.0, "strategy_performance_delta": 499.35, "risk_adjusted_return": 2.5, "events": [{"strategy_id": "faz2_integrity_strategy", "old_strategy_weight": 1.0, "new_strategy_weight": 1.0, "target_strategy_weight": 1.0, "capital_shift": 0.0, "throttle_signal": false, "allocation_drift": 0.0, "strategy_performance_delta": 499.35, "risk_adjusted_return": 2.5, "cadence_window_blocked": true, "minutes_since_last_rebalance": 0.0, "max_weight_shift_applied": false, "max_capital_shift_applied": false}], "governance_summary": {"cadence_window_minutes": 30, "max_weight_shift_per_cycle": 0.12, "max_capital_shift_pct": 0.2, "drift_threshold": 0.08, "cadence_blocked_strategies": 1, "weight_shift_capped_strategies": 0, "capital_shift_capped_strategies": 0}, "allocation_adjustment_notice": "rebalance_cadence_hold aktif: 1 strategy pencere i\\u00e7inde"}, "hedge_suggestion": {"hedge_symbol": null, "hedge_size": 0.0, "hedge_direction": null, "risk_reduction_score": 0.0, "correlation_basis": "insufficient_exposure", "recommended_action": "no_hedge_needed"}}	2026-03-19 07:35:18.050451+00	2026-06-17 07:35:18.050451+00	0.0067	normal_allocation	\N	ALLOW	\N	\N	\N	\N	0	insufficient_exposure
31425223-c7b9-42fc-871c-6e16fdd64430	c5fa2cfb-138f-4ba2-8836-b0aebadc2e9b	execution	execution_preview	7ed98ca8-6d2d-46c1-a205-88f97fe692da	faz2_integrity_strategy	VALID	["execution_preview_valid"]	[{"code": "execution_preview_valid", "title": "Execution Preview Valid", "description": "Execution preview policy kontrollerinden ge\\u00e7ti."}]	{"symbol": "BTCUSDT", "market_type": "futures", "side": "buy", "notional": 40.0, "size": 0.001, "risk_flags": ["stop_loss_missing_warning"], "strategy_weight": 1.0}	{"intent_type": "OPEN_POSITION", "position_id": null, "queue_mode": "ASSISTED", "normalized_order_payload": {"symbol": "BTCUSDT", "quote_asset": "USDT", "market_type": "futures", "side": "buy", "order_type": "market", "margin_mode": "isolated", "leverage": 3, "position_size_mode": "fixed_notional", "position_size_value": 40.0, "take_profit_mode": "none", "take_profit_value": 0, "stop_loss_mode": "none", "stop_loss_value": 0, "execution_mode": "manual", "strategy_binding": "faz2_integrity_strategy", "holding_profile": "intraday", "source_type": "manual", "source_ref_id": "evt-concurrent-0f80c755", "scanner_signal_snapshot": {"signal_id": "evt-concurrent-0f80c755", "timestamp": "2026-03-19T12:45:10Z"}, "exchange": "binance", "environment": "testnet", "account_label": "default", "exchange_connection_id": null, "venue_context": {"exchange": "binance", "market_type": "futures", "environment": "testnet", "account_label": "default", "exchange_connection_id": null, "allowed": false, "venue_state": "no_assigned_venues", "capability_match": false, "reason_codes": ["assignment_required"]}, "leverage_requested": 3, "leverage_recommended": 5, "leverage_applied": 3, "leverage_policy_mode": "hybrid_user_override", "leverage_clamp_reasons": [], "meta_strategy_summary": {"strategy_id": "faz2_integrity_strategy", "symbol": "BTCUSDT", "meta_engine_decision": "ALLOW", "allocation_source": "weight_based", "strategy_allocation_reason": "normal_allocation", "strategy_weight": 1.0, "state": "ACTIVE", "requested_notional": 40.0, "adjusted_notional": 40.0, "remaining_capital": 10000.0, "max_capital": 10000.0, "expected_return": 3.9, "realized_return": 2.5, "signal_decay": 0.0, "execution_quality_score": 75.0}, "portfolio_risk_impact": {"risk_score": 0.0067, "risk_flags": [], "decision": "ALLOW", "cluster_id": "L1", "current_portfolio_leverage": 0.004, "symbol_exposure_pct": 0.4, "cluster_exposure_pct": 0.4, "strategy_exposure_pct": 0.4, "single_trade_risk_pct": 0.4, "portfolio_state": {"base_capital": 10000.0, "current_capital": 10000.0, "intraday_drawdown_pct": 0.0, "total_drawdown_pct": 0.0}}, "strategy_conflict": {"conflict_detected": false, "winning_strategy": "faz2_integrity_strategy", "losing_strategy": null, "resolution_reason": "no_conflict", "conflict_count": 0, "strategy_conflict_warning": null}, "capital_rebalance": {"allocation_drift": 0.0, "strategy_performance_delta": 63.4526, "risk_adjusted_return": 2.5, "events": [{"strategy_id": "faz2_integrity_strategy", "old_strategy_weight": 1.0, "new_strategy_weight": 1.0, "target_strategy_weight": 1.0, "capital_shift": 0.0, "throttle_signal": false, "allocation_drift": 0.0, "strategy_performance_delta": 63.4526, "risk_adjusted_return": 2.5, "cadence_window_blocked": true, "minutes_since_last_rebalance": 0.0, "max_weight_shift_applied": false, "max_capital_shift_applied": false}], "governance_summary": {"cadence_window_minutes": 30, "max_weight_shift_per_cycle": 0.12, "max_capital_shift_pct": 0.2, "drift_threshold": 0.08, "cadence_blocked_strategies": 1, "weight_shift_capped_strategies": 0, "capital_shift_capped_strategies": 0}, "allocation_adjustment_notice": "rebalance_cadence_hold aktif: 1 strategy pencere i\\u00e7inde"}, "hedge_suggestion": {"hedge_symbol": null, "hedge_size": 0.0, "hedge_direction": null, "risk_reduction_score": 0.0, "correlation_basis": "insufficient_exposure", "recommended_action": "no_hedge_needed"}, "risk_engine": {"risk_decision": "ALLOW", "size_multiplier": 1.0, "adjusted_notional_usdt": 40.0, "adjusted_leverage": 3, "reason_codes": [], "warnings": [], "exposure_snapshot": {"wallet_usdt_balance": 10000.0, "open_exposure_usdt": 0, "pending_exposure_usdt": 0, "symbol_exposure_usdt": 0, "cluster_exposure_usdt": 0, "cluster_id": "majors", "proposed_notional_usdt": 40.0, "projected_total_exposure_usdt": 40.0, "projected_symbol_exposure_usdt": 40.0, "projected_cluster_exposure_usdt": 40.0}, "execution_quality": {"score": 100.0, "severity": "normal", "recommendation": "ALLOW", "components": {"stale_ratio": 0.0, "spread_ratio": 0.0, "slippage_ratio": 0.0, "latency_ratio": 0.0, "depth_penalty": 0.0, "partial_fill_rate": 0.0, "reject_rate": 0.0}, "metrics": {"snapshot_age_ms": 0.0, "spread_bps": 0.0, "slippage_pct": 0.0, "execution_latency_ms": 0.0, "orderbook_depth_score": 1.0, "partial_fill_rate": 0.0, "reject_rate": 0.0}}, "execution_quality_trend": {"ema_score": 100.0, "sample_count": 2, "warning_count": 0, "partial_fill_count": 0, "reject_count": 0, "warning_rate": 0.0, "partial_fill_rate": 0.0, "reject_rate": 0.0, "updated_at": "2026-03-19T07:35:21.805568+00:00"}, "cooldown_state": {"global": {"active": false, "remaining_seconds": 0, "expires_at": null, "reason": null}, "symbol": {"active": false, "remaining_seconds": 0, "expires_at": null, "reason": null}, "strategy": {"active": false, "remaining_seconds": 0, "expires_at": null, "reason": null}}, "kill_switch_active": false, "daily_loss": {"daily_loss_usdt": 0, "daily_loss_pct": 0.0}, "consecutive_losses": 0, "metrics": {"trade_risk_pct": 0.4, "projected_total_exposure_pct": 0.4, "projected_symbol_exposure_pct": 0.4, "projected_cluster_exposure_pct": 0.4, "snapshot_age_ms": 0.0, "spread_bps": 0.0, "execution_latency_ms": 0.0}}}, "preview_hash": "e3725780848e3f93338cafaef918e64c8694491d422f31d43627e93f50dbf82c", "meta_strategy_summary": {"strategy_id": "faz2_integrity_strategy", "symbol": "BTCUSDT", "meta_engine_decision": "ALLOW", "allocation_source": "weight_based", "strategy_allocation_reason": "normal_allocation", "strategy_weight": 1.0, "state": "ACTIVE", "requested_notional": 40.0, "adjusted_notional": 40.0, "remaining_capital": 10000.0, "max_capital": 10000.0, "expected_return": 3.9, "realized_return": 2.5, "signal_decay": 0.0, "execution_quality_score": 75.0}, "portfolio_risk_impact": {"risk_score": 0.0067, "risk_flags": [], "approval_required": false, "position_adjustment": {"applied": false, "requested_notional": 40.0, "adjusted_notional": 40.0, "adjustment_factor": 1.0}, "decision": "ALLOW", "cluster_id": "L1", "current_portfolio_leverage": 0.004, "symbol_exposure_pct": 0.4, "cluster_exposure_pct": 0.4, "strategy_exposure_pct": 0.4, "single_trade_risk_pct": 0.4, "portfolio_state": {"base_capital": 10000.0, "current_capital": 10000.0, "intraday_drawdown_pct": 0.0, "total_drawdown_pct": 0.0}, "limits": {"max_portfolio_leverage": 3.0, "max_symbol_exposure": 35.0, "max_cluster_exposure": 50.0, "max_strategy_exposure": 40.0, "max_single_trade_risk": 10.0, "max_intraday_drawdown": 5.0, "max_total_drawdown": 15.0}}, "strategy_conflict": {"conflict_detected": false, "winning_strategy": "faz2_integrity_strategy", "losing_strategy": null, "resolution_reason": "no_conflict", "conflict_count": 0, "strategy_conflict_warning": null}, "capital_rebalance": {"allocation_drift": 0.0, "strategy_performance_delta": 63.4526, "risk_adjusted_return": 2.5, "events": [{"strategy_id": "faz2_integrity_strategy", "old_strategy_weight": 1.0, "new_strategy_weight": 1.0, "target_strategy_weight": 1.0, "capital_shift": 0.0, "throttle_signal": false, "allocation_drift": 0.0, "strategy_performance_delta": 63.4526, "risk_adjusted_return": 2.5, "cadence_window_blocked": true, "minutes_since_last_rebalance": 0.0, "max_weight_shift_applied": false, "max_capital_shift_applied": false}], "governance_summary": {"cadence_window_minutes": 30, "max_weight_shift_per_cycle": 0.12, "max_capital_shift_pct": 0.2, "drift_threshold": 0.08, "cadence_blocked_strategies": 1, "weight_shift_capped_strategies": 0, "capital_shift_capped_strategies": 0}, "allocation_adjustment_notice": "rebalance_cadence_hold aktif: 1 strategy pencere i\\u00e7inde"}, "hedge_suggestion": {"hedge_symbol": null, "hedge_size": 0.0, "hedge_direction": null, "risk_reduction_score": 0.0, "correlation_basis": "insufficient_exposure", "recommended_action": "no_hedge_needed"}}	2026-03-19 07:35:21.808889+00	2026-06-17 07:35:21.808889+00	0.0067	normal_allocation	\N	ALLOW	\N	\N	\N	\N	0	insufficient_exposure
c1e8c15b-6021-4e97-b9ad-951c25b77ad7	3f01b548-f272-4c42-95fa-80d7734e9578	execution	execution_preview	0c7b03f1-da69-4e79-8ff9-95e4c048675d	faz2_integrity_strategy	VALID	["execution_preview_valid"]	[{"code": "execution_preview_valid", "title": "Execution Preview Valid", "description": "Execution preview policy kontrollerinden ge\\u00e7ti."}]	{"symbol": "BTCUSDT", "market_type": "futures", "side": "buy", "notional": 40.0, "size": 0.001, "risk_flags": ["stop_loss_missing_warning"], "strategy_weight": 1.0}	{"intent_type": "OPEN_POSITION", "position_id": null, "queue_mode": "ASSISTED", "normalized_order_payload": {"symbol": "BTCUSDT", "quote_asset": "USDT", "market_type": "futures", "side": "buy", "order_type": "market", "margin_mode": "isolated", "leverage": 3, "position_size_mode": "fixed_notional", "position_size_value": 40.0, "take_profit_mode": "none", "take_profit_value": 0.0, "stop_loss_mode": "none", "stop_loss_value": 0.0, "execution_mode": "manual", "strategy_binding": "faz2_integrity_strategy", "holding_profile": "intraday", "source_type": "manual", "source_ref_id": "evt-0b942488", "scanner_signal_snapshot": {"signal_id": "evt-0b942488", "timestamp": "2026-03-19T12:45:10Z"}, "exchange": "binance", "environment": "testnet", "account_label": "default", "exchange_connection_id": null, "venue_context": {"exchange": "binance", "market_type": "futures", "environment": "testnet", "account_label": "default", "exchange_connection_id": null, "allowed": false, "venue_state": "no_assigned_venues", "capability_match": false, "reason_codes": ["assignment_required"]}, "leverage_requested": 3, "leverage_recommended": 5, "leverage_applied": 3, "leverage_policy_mode": "hybrid_user_override", "leverage_clamp_reasons": [], "meta_strategy_summary": {"strategy_id": "faz2_integrity_strategy", "symbol": "BTCUSDT", "meta_engine_decision": "ALLOW", "allocation_source": "weight_based", "strategy_allocation_reason": "normal_allocation", "strategy_weight": 1.0, "state": "ACTIVE", "requested_notional": 40.0, "adjusted_notional": 40.0, "remaining_capital": 10000.0, "max_capital": 10000.0, "expected_return": 3.9, "realized_return": 2.5, "signal_decay": 0.0, "execution_quality_score": 75.0}, "portfolio_risk_impact": {"risk_score": 0.0067, "risk_flags": [], "decision": "ALLOW", "cluster_id": "L1", "current_portfolio_leverage": 0.004, "symbol_exposure_pct": 0.4, "cluster_exposure_pct": 0.4, "strategy_exposure_pct": 0.4, "single_trade_risk_pct": 0.4, "portfolio_state": {"base_capital": 10000.0, "current_capital": 10000.0, "intraday_drawdown_pct": 0.0, "total_drawdown_pct": 0.0}}, "strategy_conflict": {"conflict_detected": false, "winning_strategy": "faz2_integrity_strategy", "losing_strategy": null, "resolution_reason": "no_conflict", "conflict_count": 0, "strategy_conflict_warning": null}, "capital_rebalance": {"allocation_drift": 0.0, "strategy_performance_delta": 63.4526, "risk_adjusted_return": 2.5, "events": [{"strategy_id": "faz2_integrity_strategy", "old_strategy_weight": 1.0, "new_strategy_weight": 1.0, "target_strategy_weight": 1.0, "capital_shift": 0.0, "throttle_signal": false, "allocation_drift": 0.0, "strategy_performance_delta": 63.4526, "risk_adjusted_return": 2.5, "cadence_window_blocked": true, "minutes_since_last_rebalance": 0.0, "max_weight_shift_applied": false, "max_capital_shift_applied": false}], "governance_summary": {"cadence_window_minutes": 30, "max_weight_shift_per_cycle": 0.12, "max_capital_shift_pct": 0.2, "drift_threshold": 0.08, "cadence_blocked_strategies": 1, "weight_shift_capped_strategies": 0, "capital_shift_capped_strategies": 0}, "allocation_adjustment_notice": "rebalance_cadence_hold aktif: 1 strategy pencere i\\u00e7inde"}, "hedge_suggestion": {"hedge_symbol": null, "hedge_size": 0.0, "hedge_direction": null, "risk_reduction_score": 0.0, "correlation_basis": "insufficient_exposure", "recommended_action": "no_hedge_needed"}, "risk_engine": {"risk_decision": "ALLOW", "size_multiplier": 1.0, "adjusted_notional_usdt": 40.0, "adjusted_leverage": 3, "reason_codes": [], "warnings": [], "exposure_snapshot": {"wallet_usdt_balance": 10000.0, "open_exposure_usdt": 0, "pending_exposure_usdt": 0, "symbol_exposure_usdt": 0, "cluster_exposure_usdt": 0, "cluster_id": "majors", "proposed_notional_usdt": 40.0, "projected_total_exposure_usdt": 40.0, "projected_symbol_exposure_usdt": 40.0, "projected_cluster_exposure_usdt": 40.0}, "execution_quality": {"score": 100.0, "severity": "normal", "recommendation": "ALLOW", "components": {"stale_ratio": 0.0, "spread_ratio": 0.0, "slippage_ratio": 0.0, "latency_ratio": 0.0, "depth_penalty": 0.0, "partial_fill_rate": 0.0, "reject_rate": 0.0}, "metrics": {"snapshot_age_ms": 0.0, "spread_bps": 0.0, "slippage_pct": 0.0, "execution_latency_ms": 0.0, "orderbook_depth_score": 1.0, "partial_fill_rate": 0.0, "reject_rate": 0.0}}, "execution_quality_trend": {"ema_score": 100.0, "sample_count": 1, "warning_count": 0, "partial_fill_count": 0, "reject_count": 0, "warning_rate": 0.0, "partial_fill_rate": 0.0, "reject_rate": 0.0, "updated_at": "2026-03-19T07:35:54.130814+00:00"}, "cooldown_state": {"global": {"active": false, "remaining_seconds": 0, "expires_at": null, "reason": null}, "symbol": {"active": false, "remaining_seconds": 0, "expires_at": null, "reason": null}, "strategy": {"active": false, "remaining_seconds": 0, "expires_at": null, "reason": null}}, "kill_switch_active": false, "daily_loss": {"daily_loss_usdt": 0, "daily_loss_pct": 0.0}, "consecutive_losses": 0, "metrics": {"trade_risk_pct": 0.4, "projected_total_exposure_pct": 0.4, "projected_symbol_exposure_pct": 0.4, "projected_cluster_exposure_pct": 0.4, "snapshot_age_ms": 0.0, "spread_bps": 0.0, "execution_latency_ms": 0.0}}}, "preview_hash": "acda0d4b69f3fb1407c2c9c4ed366f27cf5cb6010b989231811d720971d2528e", "meta_strategy_summary": {"strategy_id": "faz2_integrity_strategy", "symbol": "BTCUSDT", "meta_engine_decision": "ALLOW", "allocation_source": "weight_based", "strategy_allocation_reason": "normal_allocation", "strategy_weight": 1.0, "state": "ACTIVE", "requested_notional": 40.0, "adjusted_notional": 40.0, "remaining_capital": 10000.0, "max_capital": 10000.0, "expected_return": 3.9, "realized_return": 2.5, "signal_decay": 0.0, "execution_quality_score": 75.0}, "portfolio_risk_impact": {"risk_score": 0.0067, "risk_flags": [], "approval_required": false, "position_adjustment": {"applied": false, "requested_notional": 40.0, "adjusted_notional": 40.0, "adjustment_factor": 1.0}, "decision": "ALLOW", "cluster_id": "L1", "current_portfolio_leverage": 0.004, "symbol_exposure_pct": 0.4, "cluster_exposure_pct": 0.4, "strategy_exposure_pct": 0.4, "single_trade_risk_pct": 0.4, "portfolio_state": {"base_capital": 10000.0, "current_capital": 10000.0, "intraday_drawdown_pct": 0.0, "total_drawdown_pct": 0.0}, "limits": {"max_portfolio_leverage": 3.0, "max_symbol_exposure": 35.0, "max_cluster_exposure": 50.0, "max_strategy_exposure": 40.0, "max_single_trade_risk": 10.0, "max_intraday_drawdown": 5.0, "max_total_drawdown": 15.0}}, "strategy_conflict": {"conflict_detected": false, "winning_strategy": "faz2_integrity_strategy", "losing_strategy": null, "resolution_reason": "no_conflict", "conflict_count": 0, "strategy_conflict_warning": null}, "capital_rebalance": {"allocation_drift": 0.0, "strategy_performance_delta": 63.4526, "risk_adjusted_return": 2.5, "events": [{"strategy_id": "faz2_integrity_strategy", "old_strategy_weight": 1.0, "new_strategy_weight": 1.0, "target_strategy_weight": 1.0, "capital_shift": 0.0, "throttle_signal": false, "allocation_drift": 0.0, "strategy_performance_delta": 63.4526, "risk_adjusted_return": 2.5, "cadence_window_blocked": true, "minutes_since_last_rebalance": 0.0, "max_weight_shift_applied": false, "max_capital_shift_applied": false}], "governance_summary": {"cadence_window_minutes": 30, "max_weight_shift_per_cycle": 0.12, "max_capital_shift_pct": 0.2, "drift_threshold": 0.08, "cadence_blocked_strategies": 1, "weight_shift_capped_strategies": 0, "capital_shift_capped_strategies": 0}, "allocation_adjustment_notice": "rebalance_cadence_hold aktif: 1 strategy pencere i\\u00e7inde"}, "hedge_suggestion": {"hedge_symbol": null, "hedge_size": 0.0, "hedge_direction": null, "risk_reduction_score": 0.0, "correlation_basis": "insufficient_exposure", "recommended_action": "no_hedge_needed"}}	2026-03-19 07:35:54.140579+00	2026-06-17 07:35:54.140579+00	0.0067	normal_allocation	\N	ALLOW	\N	\N	\N	\N	0	insufficient_exposure
f1c2ef79-72ea-47ae-96c6-af79df5557cf	3f01b548-f272-4c42-95fa-80d7734e9578	execution	execution_submit	0c7b03f1-da69-4e79-8ff9-95e4c048675d	faz2_integrity_strategy	QUEUED_FOR_APPROVAL	["execution_intent_submitted"]	[{"code": "execution_intent_submitted", "title": "Execution Intent Submitted", "description": "Intent submit edilerek onay kuyru\\u011funa g\\u00f6nderildi."}]	{"symbol": "BTCUSDT", "market_type": "futures", "side": "buy", "notional": 40.0, "size": 0.001}	{"intent_type": "OPEN_POSITION", "position_id": null, "intent_token": "3166ce93-18eb-44c3-9ff1-1cbfde5b663a", "preview_hash": "acda0d4b69f3fb1407c2c9c4ed366f27cf5cb6010b989231811d720971d2528e", "queue_mode": "ASSISTED", "capital_rebalance": {"allocation_drift": 0.0, "strategy_performance_delta": 63.4526, "risk_adjusted_return": 2.5, "events": [{"strategy_id": "faz2_integrity_strategy", "old_strategy_weight": 1.0, "new_strategy_weight": 1.0, "target_strategy_weight": 1.0, "capital_shift": 0.0, "throttle_signal": false, "allocation_drift": 0.0, "strategy_performance_delta": 63.4526, "risk_adjusted_return": 2.5, "cadence_window_blocked": true, "minutes_since_last_rebalance": 0.001, "max_weight_shift_applied": false, "max_capital_shift_applied": false}], "governance_summary": {"cadence_window_minutes": 30, "max_weight_shift_per_cycle": 0.12, "max_capital_shift_pct": 0.2, "drift_threshold": 0.08, "cadence_blocked_strategies": 1, "weight_shift_capped_strategies": 0, "capital_shift_capped_strategies": 0}, "allocation_adjustment_notice": "rebalance_cadence_hold aktif: 1 strategy pencere i\\u00e7inde"}}	2026-03-19 07:35:54.174325+00	2026-06-17 07:35:54.174325+00	0.0067	normal_allocation	\N	ALLOW	\N	\N	\N	\N	\N	\N
549b5377-c3af-4be6-ad4e-2bb0fcfd6d65	3f01b548-f272-4c42-95fa-80d7734e9578	execution	execution_admin_approval	0c7b03f1-da69-4e79-8ff9-95e4c048675d	faz2_integrity_strategy	RELEASED	["execution_intent_released"]	[{"code": "execution_intent_released", "title": "Execution Intent Released", "description": "Admin onay\\u0131 sonras\\u0131 intent release edilerek i\\u015fleme al\\u0131nd\\u0131."}]	{"symbol": "BTCUSDT", "market_type": "futures", "side": "long", "quantity": 0.4, "intent_type": "OPEN_POSITION"}	{"admin_user_id": "f4441738-fced-4ad6-92b8-4fb45afeeb51", "admin_note": "faz2_same_payload_test", "intent_token": "3166ce93-18eb-44c3-9ff1-1cbfde5b663a", "position_id": "6e275418-6445-4412-a4b9-72e36eaa8181"}	2026-03-19 07:35:54.187417+00	2026-06-17 07:35:54.187417+00	0.0067	normal_allocation	\N	ALLOW	\N	\N	\N	\N	\N	\N
3d0f6a83-787d-4940-9888-1ecc96b6e41c	3f01b548-f272-4c42-95fa-80d7734e9578	trade	trade_opened_from_execution	6e275418-6445-4412-a4b9-72e36eaa8181	faz2_integrity_strategy	OPENED	["trade_opened_from_execution"]	[{"code": "trade_opened_from_execution", "title": "Trade Opened From Execution", "description": "Onaylanan execution intent sonucu pozisyon a\\u00e7\\u0131ld\\u0131."}]	{"entry_price": 100.0, "quantity": 0.4, "side": "long", "leverage": 3, "intent_type": "OPEN_POSITION"}	{"intent_id": "0c7b03f1-da69-4e79-8ff9-95e4c048675d", "intent_token": "3166ce93-18eb-44c3-9ff1-1cbfde5b663a", "symbol": "BTCUSDT", "position_id": "6e275418-6445-4412-a4b9-72e36eaa8181", "strategy_weight": 1.0, "allocation_source": "weight_based", "meta_engine_decision": "ALLOW"}	2026-03-19 07:35:54.188914+00	2026-06-17 07:35:54.188914+00	0.0067	normal_allocation	\N	ALLOW	\N	\N	\N	\N	\N	\N
3174c7ae-7053-451a-a270-a7fb49de8b86	059dab08-b67a-43a5-ba71-e0721d317f78	execution	execution_preview	f142e6db-d723-4600-84df-2a3bd40390f3	faz2_integrity_strategy	VALID	["execution_preview_valid"]	[{"code": "execution_preview_valid", "title": "Execution Preview Valid", "description": "Execution preview policy kontrollerinden ge\\u00e7ti."}]	{"symbol": "BTCUSDT", "market_type": "futures", "side": "buy", "notional": 40.0, "size": 0.001, "risk_flags": ["stop_loss_missing_warning"], "strategy_weight": 1.0}	{"intent_type": "OPEN_POSITION", "position_id": null, "queue_mode": "ASSISTED", "normalized_order_payload": {"symbol": "BTCUSDT", "quote_asset": "USDT", "market_type": "futures", "side": "buy", "order_type": "market", "margin_mode": "isolated", "leverage": 3, "position_size_mode": "fixed_notional", "position_size_value": 40.0, "take_profit_mode": "none", "take_profit_value": 0, "stop_loss_mode": "none", "stop_loss_value": 0, "execution_mode": "manual", "strategy_binding": "faz2_integrity_strategy", "holding_profile": "intraday", "source_type": "manual", "source_ref_id": "evt-concurrent-d9785978", "scanner_signal_snapshot": {"signal_id": "evt-concurrent-d9785978", "timestamp": "2026-03-19T12:45:10Z"}, "exchange": "binance", "environment": "testnet", "account_label": "default", "exchange_connection_id": null, "venue_context": {"exchange": "binance", "market_type": "futures", "environment": "testnet", "account_label": "default", "exchange_connection_id": null, "allowed": false, "venue_state": "no_assigned_venues", "capability_match": false, "reason_codes": ["assignment_required"]}, "leverage_requested": 3, "leverage_recommended": 5, "leverage_applied": 3, "leverage_policy_mode": "hybrid_user_override", "leverage_clamp_reasons": [], "meta_strategy_summary": {"strategy_id": "faz2_integrity_strategy", "symbol": "BTCUSDT", "meta_engine_decision": "ALLOW", "allocation_source": "weight_based", "strategy_allocation_reason": "normal_allocation", "strategy_weight": 1.0, "state": "ACTIVE", "requested_notional": 40.0, "adjusted_notional": 40.0, "remaining_capital": 10000.0, "max_capital": 10000.0, "expected_return": 3.9, "realized_return": 2.5, "signal_decay": 0.0, "execution_quality_score": 75.0}, "portfolio_risk_impact": {"risk_score": 0.0067, "risk_flags": [], "decision": "ALLOW", "cluster_id": "L1", "current_portfolio_leverage": 0.004, "symbol_exposure_pct": 0.4, "cluster_exposure_pct": 0.4, "strategy_exposure_pct": 0.4, "single_trade_risk_pct": 0.4, "portfolio_state": {"base_capital": 10000.0, "current_capital": 10000.0, "intraday_drawdown_pct": 0.0, "total_drawdown_pct": 0.0}}, "strategy_conflict": {"conflict_detected": false, "winning_strategy": "faz2_integrity_strategy", "losing_strategy": null, "resolution_reason": "no_conflict", "conflict_count": 0, "strategy_conflict_warning": null}, "capital_rebalance": {"allocation_drift": 0.0, "strategy_performance_delta": 63.4526, "risk_adjusted_return": 2.5, "events": [{"strategy_id": "faz2_integrity_strategy", "old_strategy_weight": 1.0, "new_strategy_weight": 1.0, "target_strategy_weight": 1.0, "capital_shift": 0.0, "throttle_signal": false, "allocation_drift": 0.0, "strategy_performance_delta": 63.4526, "risk_adjusted_return": 2.5, "cadence_window_blocked": true, "minutes_since_last_rebalance": 0.0, "max_weight_shift_applied": false, "max_capital_shift_applied": false}], "governance_summary": {"cadence_window_minutes": 30, "max_weight_shift_per_cycle": 0.12, "max_capital_shift_pct": 0.2, "drift_threshold": 0.08, "cadence_blocked_strategies": 1, "weight_shift_capped_strategies": 0, "capital_shift_capped_strategies": 0}, "allocation_adjustment_notice": "rebalance_cadence_hold aktif: 1 strategy pencere i\\u00e7inde"}, "hedge_suggestion": {"hedge_symbol": null, "hedge_size": 0.0, "hedge_direction": null, "risk_reduction_score": 0.0, "correlation_basis": "insufficient_exposure", "recommended_action": "no_hedge_needed"}, "risk_engine": {"risk_decision": "ALLOW", "size_multiplier": 1.0, "adjusted_notional_usdt": 40.0, "adjusted_leverage": 3, "reason_codes": [], "warnings": [], "exposure_snapshot": {"wallet_usdt_balance": 10000.0, "open_exposure_usdt": 0, "pending_exposure_usdt": 0, "symbol_exposure_usdt": 0, "cluster_exposure_usdt": 0, "cluster_id": "majors", "proposed_notional_usdt": 40.0, "projected_total_exposure_usdt": 40.0, "projected_symbol_exposure_usdt": 40.0, "projected_cluster_exposure_usdt": 40.0}, "execution_quality": {"score": 100.0, "severity": "normal", "recommendation": "ALLOW", "components": {"stale_ratio": 0.0, "spread_ratio": 0.0, "slippage_ratio": 0.0, "latency_ratio": 0.0, "depth_penalty": 0.0, "partial_fill_rate": 0.0, "reject_rate": 0.0}, "metrics": {"snapshot_age_ms": 0.0, "spread_bps": 0.0, "slippage_pct": 0.0, "execution_latency_ms": 0.0, "orderbook_depth_score": 1.0, "partial_fill_rate": 0.0, "reject_rate": 0.0}}, "execution_quality_trend": {"ema_score": 100.0, "sample_count": 3, "warning_count": 0, "partial_fill_count": 0, "reject_count": 0, "warning_rate": 0.0, "partial_fill_rate": 0.0, "reject_rate": 0.0, "updated_at": "2026-03-19T07:36:21.078936+00:00"}, "cooldown_state": {"global": {"active": false, "remaining_seconds": 0, "expires_at": null, "reason": null}, "symbol": {"active": false, "remaining_seconds": 0, "expires_at": null, "reason": null}, "strategy": {"active": false, "remaining_seconds": 0, "expires_at": null, "reason": null}}, "kill_switch_active": false, "daily_loss": {"daily_loss_usdt": 0, "daily_loss_pct": 0.0}, "consecutive_losses": 0, "metrics": {"trade_risk_pct": 0.4, "projected_total_exposure_pct": 0.4, "projected_symbol_exposure_pct": 0.4, "projected_cluster_exposure_pct": 0.4, "snapshot_age_ms": 0.0, "spread_bps": 0.0, "execution_latency_ms": 0.0}}}, "preview_hash": "9984f6f5d678477ca90914ca0febbc1dfc5c0a1423b84c7f2e569e1a8300b389", "meta_strategy_summary": {"strategy_id": "faz2_integrity_strategy", "symbol": "BTCUSDT", "meta_engine_decision": "ALLOW", "allocation_source": "weight_based", "strategy_allocation_reason": "normal_allocation", "strategy_weight": 1.0, "state": "ACTIVE", "requested_notional": 40.0, "adjusted_notional": 40.0, "remaining_capital": 10000.0, "max_capital": 10000.0, "expected_return": 3.9, "realized_return": 2.5, "signal_decay": 0.0, "execution_quality_score": 75.0}, "portfolio_risk_impact": {"risk_score": 0.0067, "risk_flags": [], "approval_required": false, "position_adjustment": {"applied": false, "requested_notional": 40.0, "adjusted_notional": 40.0, "adjustment_factor": 1.0}, "decision": "ALLOW", "cluster_id": "L1", "current_portfolio_leverage": 0.004, "symbol_exposure_pct": 0.4, "cluster_exposure_pct": 0.4, "strategy_exposure_pct": 0.4, "single_trade_risk_pct": 0.4, "portfolio_state": {"base_capital": 10000.0, "current_capital": 10000.0, "intraday_drawdown_pct": 0.0, "total_drawdown_pct": 0.0}, "limits": {"max_portfolio_leverage": 3.0, "max_symbol_exposure": 35.0, "max_cluster_exposure": 50.0, "max_strategy_exposure": 40.0, "max_single_trade_risk": 10.0, "max_intraday_drawdown": 5.0, "max_total_drawdown": 15.0}}, "strategy_conflict": {"conflict_detected": false, "winning_strategy": "faz2_integrity_strategy", "losing_strategy": null, "resolution_reason": "no_conflict", "conflict_count": 0, "strategy_conflict_warning": null}, "capital_rebalance": {"allocation_drift": 0.0, "strategy_performance_delta": 63.4526, "risk_adjusted_return": 2.5, "events": [{"strategy_id": "faz2_integrity_strategy", "old_strategy_weight": 1.0, "new_strategy_weight": 1.0, "target_strategy_weight": 1.0, "capital_shift": 0.0, "throttle_signal": false, "allocation_drift": 0.0, "strategy_performance_delta": 63.4526, "risk_adjusted_return": 2.5, "cadence_window_blocked": true, "minutes_since_last_rebalance": 0.0, "max_weight_shift_applied": false, "max_capital_shift_applied": false}], "governance_summary": {"cadence_window_minutes": 30, "max_weight_shift_per_cycle": 0.12, "max_capital_shift_pct": 0.2, "drift_threshold": 0.08, "cadence_blocked_strategies": 1, "weight_shift_capped_strategies": 0, "capital_shift_capped_strategies": 0}, "allocation_adjustment_notice": "rebalance_cadence_hold aktif: 1 strategy pencere i\\u00e7inde"}, "hedge_suggestion": {"hedge_symbol": null, "hedge_size": 0.0, "hedge_direction": null, "risk_reduction_score": 0.0, "correlation_basis": "insufficient_exposure", "recommended_action": "no_hedge_needed"}}	2026-03-19 07:36:21.082168+00	2026-06-17 07:36:21.082168+00	0.0067	normal_allocation	\N	ALLOW	\N	\N	\N	\N	0	insufficient_exposure
63493b7d-ed37-45d7-973f-51c47171dcb6	059dab08-b67a-43a5-ba71-e0721d317f78	execution	execution_submit	f142e6db-d723-4600-84df-2a3bd40390f3	faz2_integrity_strategy	QUEUED_FOR_APPROVAL	["execution_intent_submitted"]	[{"code": "execution_intent_submitted", "title": "Execution Intent Submitted", "description": "Intent submit edilerek onay kuyru\\u011funa g\\u00f6nderildi."}]	{"symbol": "BTCUSDT", "market_type": "futures", "side": "buy", "notional": 40.0, "size": 0.001}	{"intent_type": "OPEN_POSITION", "position_id": null, "intent_token": "ba5c9913-273e-4c7e-8ec1-45924f7380e6", "preview_hash": "9984f6f5d678477ca90914ca0febbc1dfc5c0a1423b84c7f2e569e1a8300b389", "queue_mode": "ASSISTED", "capital_rebalance": {"allocation_drift": 0.0, "strategy_performance_delta": 63.4526, "risk_adjusted_return": 2.5, "events": [{"strategy_id": "faz2_integrity_strategy", "old_strategy_weight": 1.0, "new_strategy_weight": 1.0, "target_strategy_weight": 1.0, "capital_shift": 0.0, "throttle_signal": false, "allocation_drift": 0.0, "strategy_performance_delta": 63.4526, "risk_adjusted_return": 2.5, "cadence_window_blocked": true, "minutes_since_last_rebalance": 0.0, "max_weight_shift_applied": false, "max_capital_shift_applied": false}], "governance_summary": {"cadence_window_minutes": 30, "max_weight_shift_per_cycle": 0.12, "max_capital_shift_pct": 0.2, "drift_threshold": 0.08, "cadence_blocked_strategies": 1, "weight_shift_capped_strategies": 0, "capital_shift_capped_strategies": 0}, "allocation_adjustment_notice": "rebalance_cadence_hold aktif: 1 strategy pencere i\\u00e7inde"}}	2026-03-19 07:36:21.099707+00	2026-06-17 07:36:21.099707+00	0.0067	normal_allocation	\N	ALLOW	\N	\N	\N	\N	\N	\N
b3b5cbc5-435c-4076-b78b-b354d42546c1	059dab08-b67a-43a5-ba71-e0721d317f78	execution	execution_admin_approval	f142e6db-d723-4600-84df-2a3bd40390f3	faz2_integrity_strategy	RELEASED	["execution_intent_released"]	[{"code": "execution_intent_released", "title": "Execution Intent Released", "description": "Admin onay\\u0131 sonras\\u0131 intent release edilerek i\\u015fleme al\\u0131nd\\u0131."}]	{"symbol": "BTCUSDT", "market_type": "futures", "side": "long", "quantity": 0.4, "intent_type": "OPEN_POSITION"}	{"admin_user_id": "4ae95fbf-c1af-4cff-aed3-c5fba3a4838c", "admin_note": "faz2_concurrent_test", "intent_token": "ba5c9913-273e-4c7e-8ec1-45924f7380e6", "position_id": "2e0b4e67-5556-4acf-a0ee-053ed87f8e9a"}	2026-03-19 07:36:21.10751+00	2026-06-17 07:36:21.10751+00	0.0067	normal_allocation	\N	ALLOW	\N	\N	\N	\N	\N	\N
b78f5f42-1f82-4a1a-8b82-09009395fcf6	059dab08-b67a-43a5-ba71-e0721d317f78	trade	trade_opened_from_execution	2e0b4e67-5556-4acf-a0ee-053ed87f8e9a	faz2_integrity_strategy	OPENED	["trade_opened_from_execution"]	[{"code": "trade_opened_from_execution", "title": "Trade Opened From Execution", "description": "Onaylanan execution intent sonucu pozisyon a\\u00e7\\u0131ld\\u0131."}]	{"entry_price": 100.0, "quantity": 0.4, "side": "long", "leverage": 3, "intent_type": "OPEN_POSITION"}	{"intent_id": "f142e6db-d723-4600-84df-2a3bd40390f3", "intent_token": "ba5c9913-273e-4c7e-8ec1-45924f7380e6", "symbol": "BTCUSDT", "position_id": "2e0b4e67-5556-4acf-a0ee-053ed87f8e9a", "strategy_weight": 1.0, "allocation_source": "weight_based", "meta_engine_decision": "ALLOW"}	2026-03-19 07:36:21.108605+00	2026-06-17 07:36:21.108605+00	0.0067	normal_allocation	\N	ALLOW	\N	\N	\N	\N	\N	\N
\.


--
-- Data for Name: user_exchange_connections; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.user_exchange_connections (id, user_id, account_label, exchange, market_type, environment, is_default, readiness_snapshot, permission_snapshot, api_key_encrypted, api_secret_encrypted, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: user_exchange_settings; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.user_exchange_settings (id, user_id, exchange, mode, api_key_encrypted, api_secret_encrypted, updated_at, permissions_snapshot, can_trade_snapshot, validation_checked_at, last_validation_success, last_reason_codes, validation_snapshot_id) FROM stdin;
548017da-b2e8-4423-b780-cff46bde732d	c89bb203-b2e8-4230-ba9a-a01e603ae93e	binance	testnet			2026-03-19 07:11:32.150275+00	[]	\N	\N	\N	[]	\N
\.


--
-- Data for Name: user_execution_intents; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.user_execution_intents (id, user_id, source_type, source_ref_id, status, intent_token, preview_hash, queue_mode, approval_required, symbol, market_type, side, notional, normalized_order_payload, reject_reason_codes, risk_flags, submitted_at, approved_at, released_at, cancelled_at, admin_user_id, admin_note, created_at, updated_at, risk_score, gate_decision, meta_engine_decision, cluster_id, intent_type, position_id, size, reduce_only, price, stop_price, take_profit_price, idempotency_key) FROM stdin;
ca0f2159-19db-4f1e-a4d5-76989118dca0	94fa99c0-f373-4f00-95a8-7677ef165fa9	manual	evt-23a2650a	PREVIEWED	a1fc264b-3169-410d-a7d8-ab1eec6581a8	1f7465e9cad4cad594af1fe8d086a024f6cca551fbfabed61f7e997b41886f80	ASSISTED	f	BTCUSDT	futures	buy	40	{"symbol": "BTCUSDT", "quote_asset": "USDT", "market_type": "futures", "side": "buy", "order_type": "market", "margin_mode": "isolated", "leverage": 3, "position_size_mode": "fixed_notional", "position_size_value": 40.0, "take_profit_mode": "none", "take_profit_value": 0.0, "stop_loss_mode": "none", "stop_loss_value": 0.0, "execution_mode": "manual", "strategy_binding": "faz2_integrity_strategy", "holding_profile": "intraday", "source_type": "manual", "source_ref_id": "evt-23a2650a", "scanner_signal_snapshot": {"signal_id": "evt-23a2650a", "timestamp": "2026-03-19T12:45:10Z"}, "exchange": "binance", "environment": "testnet", "account_label": "default", "exchange_connection_id": null, "venue_context": {"exchange": "binance", "market_type": "futures", "environment": "testnet", "account_label": "default", "exchange_connection_id": null, "allowed": false, "venue_state": "no_assigned_venues", "capability_match": false, "reason_codes": ["assignment_required"]}, "leverage_requested": 3, "leverage_recommended": 5, "leverage_applied": 3, "leverage_policy_mode": "hybrid_user_override", "leverage_clamp_reasons": [], "meta_strategy_summary": {"strategy_id": "faz2_integrity_strategy", "symbol": "BTCUSDT", "meta_engine_decision": "ALLOW", "allocation_source": "weight_based", "strategy_allocation_reason": "normal_allocation", "strategy_weight": 1.0, "state": "ACTIVE", "requested_notional": 40.0, "adjusted_notional": 40.0, "remaining_capital": 10000.0, "max_capital": 10000.0, "expected_return": 0.5, "realized_return": 2.5, "signal_decay": 0.0, "execution_quality_score": 75.0}, "portfolio_risk_impact": {"risk_score": 0.0067, "risk_flags": [], "decision": "ALLOW", "cluster_id": "L1", "current_portfolio_leverage": 0.004, "symbol_exposure_pct": 0.4, "cluster_exposure_pct": 0.4, "strategy_exposure_pct": 0.4, "single_trade_risk_pct": 0.4, "portfolio_state": {"base_capital": 10000.0, "current_capital": 10000.0, "intraday_drawdown_pct": 0.0, "total_drawdown_pct": 0.0}}, "strategy_conflict": {"conflict_detected": false, "winning_strategy": "faz2_integrity_strategy", "losing_strategy": null, "resolution_reason": "no_conflict", "conflict_count": 0, "strategy_conflict_warning": null}, "capital_rebalance": {"allocation_drift": 0.0, "strategy_performance_delta": 499.35, "risk_adjusted_return": 2.5, "events": [{"strategy_id": "faz2_integrity_strategy", "old_strategy_weight": 1.0, "new_strategy_weight": 1.0, "target_strategy_weight": 1.0, "capital_shift": 0.0, "throttle_signal": false, "allocation_drift": 0.0, "strategy_performance_delta": 499.35, "risk_adjusted_return": 2.5, "cadence_window_blocked": true, "minutes_since_last_rebalance": 0.0, "max_weight_shift_applied": false, "max_capital_shift_applied": false}], "governance_summary": {"cadence_window_minutes": 30, "max_weight_shift_per_cycle": 0.12, "max_capital_shift_pct": 0.2, "drift_threshold": 0.08, "cadence_blocked_strategies": 1, "weight_shift_capped_strategies": 0, "capital_shift_capped_strategies": 0}, "allocation_adjustment_notice": "rebalance_cadence_hold aktif: 1 strategy pencere i\\u00e7inde"}, "hedge_suggestion": {"hedge_symbol": null, "hedge_size": 0.0, "hedge_direction": null, "risk_reduction_score": 0.0, "correlation_basis": "insufficient_exposure", "recommended_action": "no_hedge_needed"}, "risk_engine": {"risk_decision": "ALLOW", "size_multiplier": 1.0, "adjusted_notional_usdt": 40.0, "adjusted_leverage": 3, "reason_codes": [], "warnings": [], "exposure_snapshot": {"wallet_usdt_balance": 10000.0, "open_exposure_usdt": 0, "pending_exposure_usdt": 0, "symbol_exposure_usdt": 0, "cluster_exposure_usdt": 0, "cluster_id": "majors", "proposed_notional_usdt": 40.0, "projected_total_exposure_usdt": 40.0, "projected_symbol_exposure_usdt": 40.0, "projected_cluster_exposure_usdt": 40.0}, "execution_quality": {"score": 100.0, "severity": "normal", "recommendation": "ALLOW", "components": {"stale_ratio": 0.0, "spread_ratio": 0.0, "slippage_ratio": 0.0, "latency_ratio": 0.0, "depth_penalty": 0.0, "partial_fill_rate": 0.0, "reject_rate": 0.0}, "metrics": {"snapshot_age_ms": 0.0, "spread_bps": 0.0, "slippage_pct": 0.0, "execution_latency_ms": 0.0, "orderbook_depth_score": 1.0, "partial_fill_rate": 0.0, "reject_rate": 0.0}}, "execution_quality_trend": {"ema_score": 100.0, "sample_count": 1, "warning_count": 0, "partial_fill_count": 0, "reject_count": 0, "warning_rate": 0.0, "partial_fill_rate": 0.0, "reject_rate": 0.0, "updated_at": "2026-03-19T07:35:18.038581+00:00"}, "cooldown_state": {"global": {"active": false, "remaining_seconds": 0, "expires_at": null, "reason": null}, "symbol": {"active": false, "remaining_seconds": 0, "expires_at": null, "reason": null}, "strategy": {"active": false, "remaining_seconds": 0, "expires_at": null, "reason": null}}, "kill_switch_active": false, "daily_loss": {"daily_loss_usdt": 0, "daily_loss_pct": 0.0}, "consecutive_losses": 0, "metrics": {"trade_risk_pct": 0.4, "projected_total_exposure_pct": 0.4, "projected_symbol_exposure_pct": 0.4, "projected_cluster_exposure_pct": 0.4, "snapshot_age_ms": 0.0, "spread_bps": 0.0, "execution_latency_ms": 0.0}}}	[]	["stop_loss_missing_warning"]	\N	\N	\N	\N	\N		2026-03-19 07:35:18.065566+00	2026-03-19 07:35:18.065568+00	0.0067	ALLOW	ALLOW	L1	OPEN_POSITION	\N	0.001	f	\N	\N	\N	2b2db58ea3ab37e5507c7f1676db3d62acf483a320fce86fcc9cd812026a07fd
7ed98ca8-6d2d-46c1-a205-88f97fe692da	c5fa2cfb-138f-4ba2-8836-b0aebadc2e9b	manual	evt-concurrent-0f80c755	PREVIEWED	9bbdf93a-7e46-4dec-86ba-9c266905c261	e3725780848e3f93338cafaef918e64c8694491d422f31d43627e93f50dbf82c	ASSISTED	f	BTCUSDT	futures	buy	40	{"symbol": "BTCUSDT", "quote_asset": "USDT", "market_type": "futures", "side": "buy", "order_type": "market", "margin_mode": "isolated", "leverage": 3, "position_size_mode": "fixed_notional", "position_size_value": 40.0, "take_profit_mode": "none", "take_profit_value": 0, "stop_loss_mode": "none", "stop_loss_value": 0, "execution_mode": "manual", "strategy_binding": "faz2_integrity_strategy", "holding_profile": "intraday", "source_type": "manual", "source_ref_id": "evt-concurrent-0f80c755", "scanner_signal_snapshot": {"signal_id": "evt-concurrent-0f80c755", "timestamp": "2026-03-19T12:45:10Z"}, "exchange": "binance", "environment": "testnet", "account_label": "default", "exchange_connection_id": null, "venue_context": {"exchange": "binance", "market_type": "futures", "environment": "testnet", "account_label": "default", "exchange_connection_id": null, "allowed": false, "venue_state": "no_assigned_venues", "capability_match": false, "reason_codes": ["assignment_required"]}, "leverage_requested": 3, "leverage_recommended": 5, "leverage_applied": 3, "leverage_policy_mode": "hybrid_user_override", "leverage_clamp_reasons": [], "meta_strategy_summary": {"strategy_id": "faz2_integrity_strategy", "symbol": "BTCUSDT", "meta_engine_decision": "ALLOW", "allocation_source": "weight_based", "strategy_allocation_reason": "normal_allocation", "strategy_weight": 1.0, "state": "ACTIVE", "requested_notional": 40.0, "adjusted_notional": 40.0, "remaining_capital": 10000.0, "max_capital": 10000.0, "expected_return": 3.9, "realized_return": 2.5, "signal_decay": 0.0, "execution_quality_score": 75.0}, "portfolio_risk_impact": {"risk_score": 0.0067, "risk_flags": [], "decision": "ALLOW", "cluster_id": "L1", "current_portfolio_leverage": 0.004, "symbol_exposure_pct": 0.4, "cluster_exposure_pct": 0.4, "strategy_exposure_pct": 0.4, "single_trade_risk_pct": 0.4, "portfolio_state": {"base_capital": 10000.0, "current_capital": 10000.0, "intraday_drawdown_pct": 0.0, "total_drawdown_pct": 0.0}}, "strategy_conflict": {"conflict_detected": false, "winning_strategy": "faz2_integrity_strategy", "losing_strategy": null, "resolution_reason": "no_conflict", "conflict_count": 0, "strategy_conflict_warning": null}, "capital_rebalance": {"allocation_drift": 0.0, "strategy_performance_delta": 63.4526, "risk_adjusted_return": 2.5, "events": [{"strategy_id": "faz2_integrity_strategy", "old_strategy_weight": 1.0, "new_strategy_weight": 1.0, "target_strategy_weight": 1.0, "capital_shift": 0.0, "throttle_signal": false, "allocation_drift": 0.0, "strategy_performance_delta": 63.4526, "risk_adjusted_return": 2.5, "cadence_window_blocked": true, "minutes_since_last_rebalance": 0.0, "max_weight_shift_applied": false, "max_capital_shift_applied": false}], "governance_summary": {"cadence_window_minutes": 30, "max_weight_shift_per_cycle": 0.12, "max_capital_shift_pct": 0.2, "drift_threshold": 0.08, "cadence_blocked_strategies": 1, "weight_shift_capped_strategies": 0, "capital_shift_capped_strategies": 0}, "allocation_adjustment_notice": "rebalance_cadence_hold aktif: 1 strategy pencere i\\u00e7inde"}, "hedge_suggestion": {"hedge_symbol": null, "hedge_size": 0.0, "hedge_direction": null, "risk_reduction_score": 0.0, "correlation_basis": "insufficient_exposure", "recommended_action": "no_hedge_needed"}, "risk_engine": {"risk_decision": "ALLOW", "size_multiplier": 1.0, "adjusted_notional_usdt": 40.0, "adjusted_leverage": 3, "reason_codes": [], "warnings": [], "exposure_snapshot": {"wallet_usdt_balance": 10000.0, "open_exposure_usdt": 0, "pending_exposure_usdt": 0, "symbol_exposure_usdt": 0, "cluster_exposure_usdt": 0, "cluster_id": "majors", "proposed_notional_usdt": 40.0, "projected_total_exposure_usdt": 40.0, "projected_symbol_exposure_usdt": 40.0, "projected_cluster_exposure_usdt": 40.0}, "execution_quality": {"score": 100.0, "severity": "normal", "recommendation": "ALLOW", "components": {"stale_ratio": 0.0, "spread_ratio": 0.0, "slippage_ratio": 0.0, "latency_ratio": 0.0, "depth_penalty": 0.0, "partial_fill_rate": 0.0, "reject_rate": 0.0}, "metrics": {"snapshot_age_ms": 0.0, "spread_bps": 0.0, "slippage_pct": 0.0, "execution_latency_ms": 0.0, "orderbook_depth_score": 1.0, "partial_fill_rate": 0.0, "reject_rate": 0.0}}, "execution_quality_trend": {"ema_score": 100.0, "sample_count": 2, "warning_count": 0, "partial_fill_count": 0, "reject_count": 0, "warning_rate": 0.0, "partial_fill_rate": 0.0, "reject_rate": 0.0, "updated_at": "2026-03-19T07:35:21.805568+00:00"}, "cooldown_state": {"global": {"active": false, "remaining_seconds": 0, "expires_at": null, "reason": null}, "symbol": {"active": false, "remaining_seconds": 0, "expires_at": null, "reason": null}, "strategy": {"active": false, "remaining_seconds": 0, "expires_at": null, "reason": null}}, "kill_switch_active": false, "daily_loss": {"daily_loss_usdt": 0, "daily_loss_pct": 0.0}, "consecutive_losses": 0, "metrics": {"trade_risk_pct": 0.4, "projected_total_exposure_pct": 0.4, "projected_symbol_exposure_pct": 0.4, "projected_cluster_exposure_pct": 0.4, "snapshot_age_ms": 0.0, "spread_bps": 0.0, "execution_latency_ms": 0.0}}}	[]	["stop_loss_missing_warning"]	\N	\N	\N	\N	\N		2026-03-19 07:35:21.810268+00	2026-03-19 07:35:21.81027+00	0.0067	ALLOW	ALLOW	L1	OPEN_POSITION	\N	0.001	f	\N	\N	\N	cae9268a0f15d9768bf84680f5221a90c47f4a34ce6ca68e23f49eb39ede8ba8
0c7b03f1-da69-4e79-8ff9-95e4c048675d	3f01b548-f272-4c42-95fa-80d7734e9578	manual	evt-0b942488	RELEASED	3166ce93-18eb-44c3-9ff1-1cbfde5b663a	acda0d4b69f3fb1407c2c9c4ed366f27cf5cb6010b989231811d720971d2528e	ASSISTED	f	BTCUSDT	futures	buy	40	{"symbol": "BTCUSDT", "quote_asset": "USDT", "market_type": "futures", "side": "buy", "order_type": "market", "margin_mode": "isolated", "leverage": 3, "position_size_mode": "fixed_notional", "position_size_value": 40.0, "take_profit_mode": "none", "take_profit_value": 0.0, "stop_loss_mode": "none", "stop_loss_value": 0.0, "execution_mode": "manual", "strategy_binding": "faz2_integrity_strategy", "holding_profile": "intraday", "source_type": "manual", "source_ref_id": "evt-0b942488", "scanner_signal_snapshot": {"signal_id": "evt-0b942488", "timestamp": "2026-03-19T12:45:10Z"}, "exchange": "binance", "environment": "testnet", "account_label": "default", "exchange_connection_id": null, "venue_context": {"exchange": "binance", "market_type": "futures", "environment": "testnet", "account_label": "default", "exchange_connection_id": null, "allowed": false, "venue_state": "no_assigned_venues", "capability_match": false, "reason_codes": ["assignment_required"]}, "leverage_requested": 3, "leverage_recommended": 5, "leverage_applied": 3, "leverage_policy_mode": "hybrid_user_override", "leverage_clamp_reasons": [], "meta_strategy_summary": {"strategy_id": "faz2_integrity_strategy", "symbol": "BTCUSDT", "meta_engine_decision": "ALLOW", "allocation_source": "weight_based", "strategy_allocation_reason": "normal_allocation", "strategy_weight": 1.0, "state": "ACTIVE", "requested_notional": 40.0, "adjusted_notional": 40.0, "remaining_capital": 10000.0, "max_capital": 10000.0, "expected_return": 3.9, "realized_return": 2.5, "signal_decay": 0.0, "execution_quality_score": 75.0}, "portfolio_risk_impact": {"risk_score": 0.0067, "risk_flags": [], "decision": "ALLOW", "cluster_id": "L1", "current_portfolio_leverage": 0.004, "symbol_exposure_pct": 0.4, "cluster_exposure_pct": 0.4, "strategy_exposure_pct": 0.4, "single_trade_risk_pct": 0.4, "portfolio_state": {"base_capital": 10000.0, "current_capital": 10000.0, "intraday_drawdown_pct": 0.0, "total_drawdown_pct": 0.0}}, "strategy_conflict": {"conflict_detected": false, "winning_strategy": "faz2_integrity_strategy", "losing_strategy": null, "resolution_reason": "no_conflict", "conflict_count": 0, "strategy_conflict_warning": null}, "capital_rebalance": {"allocation_drift": 0.0, "strategy_performance_delta": 63.4526, "risk_adjusted_return": 2.5, "events": [{"strategy_id": "faz2_integrity_strategy", "old_strategy_weight": 1.0, "new_strategy_weight": 1.0, "target_strategy_weight": 1.0, "capital_shift": 0.0, "throttle_signal": false, "allocation_drift": 0.0, "strategy_performance_delta": 63.4526, "risk_adjusted_return": 2.5, "cadence_window_blocked": true, "minutes_since_last_rebalance": 0.0, "max_weight_shift_applied": false, "max_capital_shift_applied": false}], "governance_summary": {"cadence_window_minutes": 30, "max_weight_shift_per_cycle": 0.12, "max_capital_shift_pct": 0.2, "drift_threshold": 0.08, "cadence_blocked_strategies": 1, "weight_shift_capped_strategies": 0, "capital_shift_capped_strategies": 0}, "allocation_adjustment_notice": "rebalance_cadence_hold aktif: 1 strategy pencere i\\u00e7inde"}, "hedge_suggestion": {"hedge_symbol": null, "hedge_size": 0.0, "hedge_direction": null, "risk_reduction_score": 0.0, "correlation_basis": "insufficient_exposure", "recommended_action": "no_hedge_needed"}, "risk_engine": {"risk_decision": "ALLOW", "size_multiplier": 1.0, "adjusted_notional_usdt": 40.0, "adjusted_leverage": 3, "reason_codes": [], "warnings": [], "exposure_snapshot": {"wallet_usdt_balance": 10000.0, "open_exposure_usdt": 0, "pending_exposure_usdt": 0, "symbol_exposure_usdt": 0, "cluster_exposure_usdt": 0, "cluster_id": "majors", "proposed_notional_usdt": 40.0, "projected_total_exposure_usdt": 40.0, "projected_symbol_exposure_usdt": 40.0, "projected_cluster_exposure_usdt": 40.0}, "execution_quality": {"score": 100.0, "severity": "normal", "recommendation": "ALLOW", "components": {"stale_ratio": 0.0, "spread_ratio": 0.0, "slippage_ratio": 0.0, "latency_ratio": 0.0, "depth_penalty": 0.0, "partial_fill_rate": 0.0, "reject_rate": 0.0}, "metrics": {"snapshot_age_ms": 0.0, "spread_bps": 0.0, "slippage_pct": 0.0, "execution_latency_ms": 0.0, "orderbook_depth_score": 1.0, "partial_fill_rate": 0.0, "reject_rate": 0.0}}, "execution_quality_trend": {"ema_score": 100.0, "sample_count": 1, "warning_count": 0, "partial_fill_count": 0, "reject_count": 0, "warning_rate": 0.0, "partial_fill_rate": 0.0, "reject_rate": 0.0, "updated_at": "2026-03-19T07:35:54.130814+00:00"}, "cooldown_state": {"global": {"active": false, "remaining_seconds": 0, "expires_at": null, "reason": null}, "symbol": {"active": false, "remaining_seconds": 0, "expires_at": null, "reason": null}, "strategy": {"active": false, "remaining_seconds": 0, "expires_at": null, "reason": null}}, "kill_switch_active": false, "daily_loss": {"daily_loss_usdt": 0, "daily_loss_pct": 0.0}, "consecutive_losses": 0, "metrics": {"trade_risk_pct": 0.4, "projected_total_exposure_pct": 0.4, "projected_symbol_exposure_pct": 0.4, "projected_cluster_exposure_pct": 0.4, "snapshot_age_ms": 0.0, "spread_bps": 0.0, "execution_latency_ms": 0.0}}}	[]	["stop_loss_missing_warning"]	2026-03-19 07:35:54.170513+00	2026-03-19 07:35:54.178761+00	2026-03-19 07:35:54.187393+00	\N	f4441738-fced-4ad6-92b8-4fb45afeeb51	faz2_same_payload_test	2026-03-19 07:35:54.144009+00	2026-03-19 07:35:54.188261+00	0.0067	ALLOW	ALLOW	L1	OPEN_POSITION	6e275418-6445-4412-a4b9-72e36eaa8181	0.001	f	\N	\N	\N	9b9aee8cd12db804ceae6f026d8fd44f13cd5b9d80a8e0fe4d1ad087d0d7fd86
f142e6db-d723-4600-84df-2a3bd40390f3	059dab08-b67a-43a5-ba71-e0721d317f78	manual	evt-concurrent-d9785978	RELEASED	ba5c9913-273e-4c7e-8ec1-45924f7380e6	9984f6f5d678477ca90914ca0febbc1dfc5c0a1423b84c7f2e569e1a8300b389	ASSISTED	f	BTCUSDT	futures	buy	40	{"symbol": "BTCUSDT", "quote_asset": "USDT", "market_type": "futures", "side": "buy", "order_type": "market", "margin_mode": "isolated", "leverage": 3, "position_size_mode": "fixed_notional", "position_size_value": 40.0, "take_profit_mode": "none", "take_profit_value": 0, "stop_loss_mode": "none", "stop_loss_value": 0, "execution_mode": "manual", "strategy_binding": "faz2_integrity_strategy", "holding_profile": "intraday", "source_type": "manual", "source_ref_id": "evt-concurrent-d9785978", "scanner_signal_snapshot": {"signal_id": "evt-concurrent-d9785978", "timestamp": "2026-03-19T12:45:10Z"}, "exchange": "binance", "environment": "testnet", "account_label": "default", "exchange_connection_id": null, "venue_context": {"exchange": "binance", "market_type": "futures", "environment": "testnet", "account_label": "default", "exchange_connection_id": null, "allowed": false, "venue_state": "no_assigned_venues", "capability_match": false, "reason_codes": ["assignment_required"]}, "leverage_requested": 3, "leverage_recommended": 5, "leverage_applied": 3, "leverage_policy_mode": "hybrid_user_override", "leverage_clamp_reasons": [], "meta_strategy_summary": {"strategy_id": "faz2_integrity_strategy", "symbol": "BTCUSDT", "meta_engine_decision": "ALLOW", "allocation_source": "weight_based", "strategy_allocation_reason": "normal_allocation", "strategy_weight": 1.0, "state": "ACTIVE", "requested_notional": 40.0, "adjusted_notional": 40.0, "remaining_capital": 10000.0, "max_capital": 10000.0, "expected_return": 3.9, "realized_return": 2.5, "signal_decay": 0.0, "execution_quality_score": 75.0}, "portfolio_risk_impact": {"risk_score": 0.0067, "risk_flags": [], "decision": "ALLOW", "cluster_id": "L1", "current_portfolio_leverage": 0.004, "symbol_exposure_pct": 0.4, "cluster_exposure_pct": 0.4, "strategy_exposure_pct": 0.4, "single_trade_risk_pct": 0.4, "portfolio_state": {"base_capital": 10000.0, "current_capital": 10000.0, "intraday_drawdown_pct": 0.0, "total_drawdown_pct": 0.0}}, "strategy_conflict": {"conflict_detected": false, "winning_strategy": "faz2_integrity_strategy", "losing_strategy": null, "resolution_reason": "no_conflict", "conflict_count": 0, "strategy_conflict_warning": null}, "capital_rebalance": {"allocation_drift": 0.0, "strategy_performance_delta": 63.4526, "risk_adjusted_return": 2.5, "events": [{"strategy_id": "faz2_integrity_strategy", "old_strategy_weight": 1.0, "new_strategy_weight": 1.0, "target_strategy_weight": 1.0, "capital_shift": 0.0, "throttle_signal": false, "allocation_drift": 0.0, "strategy_performance_delta": 63.4526, "risk_adjusted_return": 2.5, "cadence_window_blocked": true, "minutes_since_last_rebalance": 0.0, "max_weight_shift_applied": false, "max_capital_shift_applied": false}], "governance_summary": {"cadence_window_minutes": 30, "max_weight_shift_per_cycle": 0.12, "max_capital_shift_pct": 0.2, "drift_threshold": 0.08, "cadence_blocked_strategies": 1, "weight_shift_capped_strategies": 0, "capital_shift_capped_strategies": 0}, "allocation_adjustment_notice": "rebalance_cadence_hold aktif: 1 strategy pencere i\\u00e7inde"}, "hedge_suggestion": {"hedge_symbol": null, "hedge_size": 0.0, "hedge_direction": null, "risk_reduction_score": 0.0, "correlation_basis": "insufficient_exposure", "recommended_action": "no_hedge_needed"}, "risk_engine": {"risk_decision": "ALLOW", "size_multiplier": 1.0, "adjusted_notional_usdt": 40.0, "adjusted_leverage": 3, "reason_codes": [], "warnings": [], "exposure_snapshot": {"wallet_usdt_balance": 10000.0, "open_exposure_usdt": 0, "pending_exposure_usdt": 0, "symbol_exposure_usdt": 0, "cluster_exposure_usdt": 0, "cluster_id": "majors", "proposed_notional_usdt": 40.0, "projected_total_exposure_usdt": 40.0, "projected_symbol_exposure_usdt": 40.0, "projected_cluster_exposure_usdt": 40.0}, "execution_quality": {"score": 100.0, "severity": "normal", "recommendation": "ALLOW", "components": {"stale_ratio": 0.0, "spread_ratio": 0.0, "slippage_ratio": 0.0, "latency_ratio": 0.0, "depth_penalty": 0.0, "partial_fill_rate": 0.0, "reject_rate": 0.0}, "metrics": {"snapshot_age_ms": 0.0, "spread_bps": 0.0, "slippage_pct": 0.0, "execution_latency_ms": 0.0, "orderbook_depth_score": 1.0, "partial_fill_rate": 0.0, "reject_rate": 0.0}}, "execution_quality_trend": {"ema_score": 100.0, "sample_count": 3, "warning_count": 0, "partial_fill_count": 0, "reject_count": 0, "warning_rate": 0.0, "partial_fill_rate": 0.0, "reject_rate": 0.0, "updated_at": "2026-03-19T07:36:21.078936+00:00"}, "cooldown_state": {"global": {"active": false, "remaining_seconds": 0, "expires_at": null, "reason": null}, "symbol": {"active": false, "remaining_seconds": 0, "expires_at": null, "reason": null}, "strategy": {"active": false, "remaining_seconds": 0, "expires_at": null, "reason": null}}, "kill_switch_active": false, "daily_loss": {"daily_loss_usdt": 0, "daily_loss_pct": 0.0}, "consecutive_losses": 0, "metrics": {"trade_risk_pct": 0.4, "projected_total_exposure_pct": 0.4, "projected_symbol_exposure_pct": 0.4, "projected_cluster_exposure_pct": 0.4, "snapshot_age_ms": 0.0, "spread_bps": 0.0, "execution_latency_ms": 0.0}}}	[]	["stop_loss_missing_warning"]	2026-03-19 07:36:21.096972+00	2026-03-19 07:36:21.102665+00	2026-03-19 07:36:21.107494+00	\N	4ae95fbf-c1af-4cff-aed3-c5fba3a4838c	faz2_concurrent_test	2026-03-19 07:36:21.083141+00	2026-03-19 07:36:21.10796+00	0.0067	ALLOW	ALLOW	L1	OPEN_POSITION	2e0b4e67-5556-4acf-a0ee-053ed87f8e9a	0.001	f	\N	\N	\N	5d87fae6200ddca73d2675c8242aa1830b6a524feccb9c3a6a79048b945ee62a
\.


--
-- Data for Name: user_indicator_saved_queries; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.user_indicator_saved_queries (id, user_id, name, exchange, market_type, timeframe, query_expression, symbol_universe, result_limit, created_at, updated_at, filter_snapshot, schema_version) FROM stdin;
\.


--
-- Data for Name: user_indicator_watchlist; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.user_indicator_watchlist (id, user_id, exchange, market_type, symbol, note, created_at, context_snapshot) FROM stdin;
\.


--
-- Data for Name: user_learning_simulation_suggestions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.user_learning_simulation_suggestions (id, user_id, symbol, strategy_id, family, recommendation_type, simulation_payload, note, status, created_at, reviewed_at, reviewed_by) FROM stdin;
\.


--
-- Data for Name: user_mfa_backup_codes; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.user_mfa_backup_codes (id, user_id, code_hash, used_at, created_at) FROM stdin;
\.


--
-- Data for Name: user_mfa_preferences; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.user_mfa_preferences (id, user_id, is_enabled, enabled_methods, totp_secret, totp_verified, email_otp_verified, updated_at, created_at) FROM stdin;
eba8e580-9bef-426e-bc70-186d274dd2ca	9ca118ab-d054-415a-92e0-023e9e08fe22	f	[]	\N	f	f	2026-03-19 07:11:30.179683+00	2026-03-19 07:11:30.179688+00
911e290d-8e28-4cfc-af87-933470b676bb	c89bb203-b2e8-4230-ba9a-a01e603ae93e	f	[]	\N	f	f	2026-03-19 07:11:32.008302+00	2026-03-19 07:11:32.008304+00
\.


--
-- Data for Name: user_onboarding_profiles; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.user_onboarding_profiles (id, user_id, full_name, phone, email_verified, verification_code, verification_expires_at, verification_requested_at, password_reset_token_hash, password_reset_expires_at, password_reset_requested_at, created_at, updated_at) FROM stdin;
66a6a74f-1577-4e82-a309-a083e28f1c9e	c89bb203-b2e8-4230-ba9a-a01e603ae93e	\N	\N	f	\N	\N	\N	\N	\N	\N	2026-03-19 07:11:30.793133+00	2026-03-19 07:11:30.793135+00
\.


--
-- Data for Name: user_risk_settings; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.user_risk_settings (id, user_id, allocation_pct, trade_risk_pct, daily_loss_limit_pct, compounding_enabled, base_capital, updated_at) FROM stdin;
\.


--
-- Data for Name: user_scanner_automation_configs; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.user_scanner_automation_configs (id, user_id, auto_enabled, interval_seconds, max_results, symbol_source, symbol_selection_mode, selected_symbols, last_run_id, last_run_status, last_run_error, last_run_at, created_at, updated_at, last_actionable_count) FROM stdin;
\.


--
-- Data for Name: user_scanner_automation_profiles; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.user_scanner_automation_profiles (id, user_id, name, auto_enabled, is_active, interval_seconds, max_results, symbol_source, symbol_selection_mode, selected_symbols, last_run_id, last_run_status, last_actionable_count, last_run_error, last_run_at, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: user_scanner_results; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.user_scanner_results (id, run_id, user_id, symbol, strategy_code, signal, confidence, signal_score, reason_codes, payload, generated_at) FROM stdin;
\.


--
-- Data for Name: user_scanner_symbol_selections; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.user_scanner_symbol_selections (id, user_id, scanner_id, selected_symbols, symbol_source, symbol_selection_mode, saved_at, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: user_signal_modes; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.user_signal_modes (id, user_id, mode, updated_at) FROM stdin;
\.


--
-- Data for Name: user_venue_assignments; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.user_venue_assignments (id, user_id, exchange_code, spot_allowed, futures_allowed, testnet_allowed, live_allowed, updated_at) FROM stdin;
286d28cb-1956-42ff-bdc4-c81cafd42376	c89bb203-b2e8-4230-ba9a-a01e603ae93e	binance	t	t	t	f	2026-03-19 07:11:31.601786+00
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.users (id, email, password_hash, role, is_active, created_at, updated_at, approval_status, approval_requested_at, approved_at, disabled_at) FROM stdin;
9ca118ab-d054-415a-92e0-023e9e08fe22	admin@platform.local	$2b$12$Ijbg4ZzLGxxMsqEiK6nB4ueRyd9m2uzEdSXJ77pyFK5vvt2T6zQkS	SUPER_ADMIN	t	2026-03-19 06:49:08.711124+00	2026-03-19 06:49:08.711126+00	approved	2026-03-19 06:49:08.710181+00	2026-03-19 06:49:08.710186+00	\N
c89bb203-b2e8-4230-ba9a-a01e603ae93e	testuser1773706589@example.com	$2b$12$xZ1ClYCTvlFgYuexvwhMO.nX6Ki/KQ.vKgDra9WNUBKZv3WACz6TC	USER	t	2026-03-19 07:11:30.791542+00	2026-03-19 07:11:31.593023+00	approved	2026-03-19 07:11:30.790753+00	2026-03-19 07:11:31.590906+00	\N
94fa99c0-f373-4f00-95a8-7677ef165fa9	faz2-user-d9d756ed4f@example.com	$2b$12$lkXhvNrEdnrgENSWfLP19uIx.7YIRMGboziiiyxpM3pz5kk/aAIXS	USER	t	2026-03-19 07:35:14.716881+00	2026-03-19 07:35:14.716882+00	approved	2026-03-19 07:35:14.716878+00	\N	\N
252daae4-dc1f-4add-85e8-b83c6aed6eaf	faz2-admin-24f06766c5@example.com	$2b$12$iUggNxkLwBZjTAjr2cYgnuLOuKtiqKe6el1KQvNJ4mz8jA8IQxvga	ADMIN	t	2026-03-19 07:35:14.959289+00	2026-03-19 07:35:14.95929+00	approved	2026-03-19 07:35:14.959284+00	\N	\N
c5fa2cfb-138f-4ba2-8836-b0aebadc2e9b	faz2-user-8561fe10af@example.com	$2b$12$7E8yOlnIp1U43UMiYol8R.Xo5O/gThNiJwN83eie.4L5/NwzFTDVC	USER	t	2026-03-19 07:35:21.541793+00	2026-03-19 07:35:21.541794+00	approved	2026-03-19 07:35:21.54179+00	\N	\N
b0641426-502f-4607-b089-fceac88e98b9	faz2-admin-d448f5258a@example.com	$2b$12$igytlbpjPt5tQoa2RzWmv.wKv0jbOS1UaE6oSvjZgEGxu6ZgiaQDK	ADMIN	t	2026-03-19 07:35:21.783168+00	2026-03-19 07:35:21.783169+00	approved	2026-03-19 07:35:21.783165+00	\N	\N
3f01b548-f272-4c42-95fa-80d7734e9578	faz2-user-d45400e0e0@example.com	$2b$12$A/dTNX.OO1MBAwjP8vgS7OAnhEEP..ysbP/jNY6DCMROujPO71b4C	USER	t	2026-03-19 07:35:43.934769+00	2026-03-19 07:35:43.93477+00	approved	2026-03-19 07:35:43.934765+00	\N	\N
f4441738-fced-4ad6-92b8-4fb45afeeb51	faz2-admin-0614f86130@example.com	$2b$12$Dk9GJkhGM1PuvutTuP0UCuRdGsKUXgsTlu8Fxz05kc5RtZo9mvtLO	ADMIN	t	2026-03-19 07:35:44.176458+00	2026-03-19 07:35:44.176459+00	approved	2026-03-19 07:35:44.176454+00	\N	\N
059dab08-b67a-43a5-ba71-e0721d317f78	faz2-user-36958654d9@example.com	$2b$12$qYadbZ7vXR1zwbpZGi6N3.sQShBxJ5ZH4RmhapIsqupxip3GfOlFi	USER	t	2026-03-19 07:36:20.815914+00	2026-03-19 07:36:20.815915+00	approved	2026-03-19 07:36:20.815911+00	\N	\N
4ae95fbf-c1af-4cff-aed3-c5fba3a4838c	faz2-admin-9838280bdf@example.com	$2b$12$vcx.pjaJaGpQeegYoXwF.u7sMQH/FhWw1TwEmZ5rfeIinQ03wfZze	ADMIN	t	2026-03-19 07:36:21.05708+00	2026-03-19 07:36:21.057081+00	approved	2026-03-19 07:36:21.057076+00	\N	\N
\.


--
-- Data for Name: weekly_report_archives; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.weekly_report_archives (report_id, report_type, period_start, period_end, generated_at, timezone, filename, storage_path, size_bytes, sha256, status, trigger_source, generated_by, created_at, updated_at) FROM stdin;
\.


--
-- Name: test_table_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.test_table_id_seq', 6, true);


--
-- Name: admin_control admin_control_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_control
    ADD CONSTRAINT admin_control_pkey PRIMARY KEY (id);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: alert_channel_configs alert_channel_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_channel_configs
    ADD CONSTRAINT alert_channel_configs_pkey PRIMARY KEY (id);


--
-- Name: alert_policies alert_policies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_policies
    ADD CONSTRAINT alert_policies_pkey PRIMARY KEY (id);


--
-- Name: allowed_markets allowed_markets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.allowed_markets
    ADD CONSTRAINT allowed_markets_pkey PRIMARY KEY (id);


--
-- Name: audit_logs audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);


--
-- Name: auth_mfa_challenges auth_mfa_challenges_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_mfa_challenges
    ADD CONSTRAINT auth_mfa_challenges_pkey PRIMARY KEY (id);


--
-- Name: backtest_result_cards backtest_result_cards_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_result_cards
    ADD CONSTRAINT backtest_result_cards_pkey PRIMARY KEY (id);


--
-- Name: bot_profiles bot_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_profiles
    ADD CONSTRAINT bot_profiles_pkey PRIMARY KEY (id);


--
-- Name: brand_settings brand_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.brand_settings
    ADD CONSTRAINT brand_settings_pkey PRIMARY KEY (id);


--
-- Name: canonical_strategy_registry canonical_strategy_registry_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.canonical_strategy_registry
    ADD CONSTRAINT canonical_strategy_registry_pkey PRIMARY KEY (strategy_id);


--
-- Name: decision_trace_cold decision_trace_cold_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.decision_trace_cold
    ADD CONSTRAINT decision_trace_cold_pkey PRIMARY KEY (archive_id);


--
-- Name: decision_trace_hot decision_trace_hot_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.decision_trace_hot
    ADD CONSTRAINT decision_trace_hot_pkey PRIMARY KEY (trace_id);


--
-- Name: exchange_capabilities exchange_capabilities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exchange_capabilities
    ADD CONSTRAINT exchange_capabilities_pkey PRIMARY KEY (id);


--
-- Name: exchange_registry exchange_registry_exchange_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exchange_registry
    ADD CONSTRAINT exchange_registry_exchange_code_key UNIQUE (exchange_code);


--
-- Name: exchange_registry exchange_registry_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exchange_registry
    ADD CONSTRAINT exchange_registry_pkey PRIMARY KEY (id);


--
-- Name: execution_correction_events execution_correction_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.execution_correction_events
    ADD CONSTRAINT execution_correction_events_pkey PRIMARY KEY (id);


--
-- Name: execution_events execution_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.execution_events
    ADD CONSTRAINT execution_events_pkey PRIMARY KEY (id);


--
-- Name: execution_intent_events execution_intent_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.execution_intent_events
    ADD CONSTRAINT execution_intent_events_pkey PRIMARY KEY (id);


--
-- Name: execution_intents execution_intents_intent_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.execution_intents
    ADD CONSTRAINT execution_intents_intent_hash_key UNIQUE (intent_hash);


--
-- Name: execution_intents execution_intents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.execution_intents
    ADD CONSTRAINT execution_intents_pkey PRIMARY KEY (intent_id);


--
-- Name: execution_lifecycle_events execution_lifecycle_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.execution_lifecycle_events
    ADD CONSTRAINT execution_lifecycle_events_pkey PRIMARY KEY (id);


--
-- Name: execution_metrics execution_metrics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.execution_metrics
    ADD CONSTRAINT execution_metrics_pkey PRIMARY KEY (id);


--
-- Name: execution_policies execution_policies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.execution_policies
    ADD CONSTRAINT execution_policies_pkey PRIMARY KEY (id);


--
-- Name: execution_policies execution_policies_strategy_type_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.execution_policies
    ADD CONSTRAINT execution_policies_strategy_type_key UNIQUE (strategy_type);


--
-- Name: execution_state_transitions execution_state_transitions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.execution_state_transitions
    ADD CONSTRAINT execution_state_transitions_pkey PRIMARY KEY (id);


--
-- Name: external_provider_credentials external_provider_credentials_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.external_provider_credentials
    ADD CONSTRAINT external_provider_credentials_pkey PRIMARY KEY (provider);


--
-- Name: failed_events failed_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.failed_events
    ADD CONSTRAINT failed_events_pkey PRIMARY KEY (id);


--
-- Name: family_outcome_memory family_outcome_memory_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.family_outcome_memory
    ADD CONSTRAINT family_outcome_memory_pkey PRIMARY KEY (id);


--
-- Name: hardening_checklist_runs hardening_checklist_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hardening_checklist_runs
    ADD CONSTRAINT hardening_checklist_runs_pkey PRIMARY KEY (id);


--
-- Name: indicator_computation_cache indicator_computation_cache_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.indicator_computation_cache
    ADD CONSTRAINT indicator_computation_cache_pkey PRIMARY KEY (id);


--
-- Name: learning_decision_events learning_decision_events_pending_signal_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.learning_decision_events
    ADD CONSTRAINT learning_decision_events_pending_signal_id_key UNIQUE (pending_signal_id);


--
-- Name: learning_decision_events learning_decision_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.learning_decision_events
    ADD CONSTRAINT learning_decision_events_pkey PRIMARY KEY (id);


--
-- Name: learning_decision_events learning_decision_events_scanner_result_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.learning_decision_events
    ADD CONSTRAINT learning_decision_events_scanner_result_id_key UNIQUE (scanner_result_id);


--
-- Name: learning_recommendations learning_recommendations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.learning_recommendations
    ADD CONSTRAINT learning_recommendations_pkey PRIMARY KEY (id);


--
-- Name: live_activation_config live_activation_config_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.live_activation_config
    ADD CONSTRAINT live_activation_config_pkey PRIMARY KEY (id);


--
-- Name: manual_override_log manual_override_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manual_override_log
    ADD CONSTRAINT manual_override_log_pkey PRIMARY KEY (override_id);


--
-- Name: paper_positions paper_positions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.paper_positions
    ADD CONSTRAINT paper_positions_pkey PRIMARY KEY (id);


--
-- Name: pending_signals pending_signals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pending_signals
    ADD CONSTRAINT pending_signals_pkey PRIMARY KEY (id);


--
-- Name: permission_drift_events permission_drift_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.permission_drift_events
    ADD CONSTRAINT permission_drift_events_pkey PRIMARY KEY (id);


--
-- Name: portfolio_exposure_snapshot portfolio_exposure_snapshot_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.portfolio_exposure_snapshot
    ADD CONSTRAINT portfolio_exposure_snapshot_pkey PRIMARY KEY (id);


--
-- Name: position_ledger_events position_ledger_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.position_ledger_events
    ADD CONSTRAINT position_ledger_events_pkey PRIMARY KEY (id);


--
-- Name: positions positions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.positions
    ADD CONSTRAINT positions_pkey PRIMARY KEY (position_id);


--
-- Name: regime_snapshots regime_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.regime_snapshots
    ADD CONSTRAINT regime_snapshots_pkey PRIMARY KEY (regime_snapshot_id);


--
-- Name: release_gate_overrides release_gate_overrides_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.release_gate_overrides
    ADD CONSTRAINT release_gate_overrides_pkey PRIMARY KEY (id);


--
-- Name: replay_equity_points replay_equity_points_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.replay_equity_points
    ADD CONSTRAINT replay_equity_points_pkey PRIMARY KEY (id);


--
-- Name: replay_executions replay_executions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.replay_executions
    ADD CONSTRAINT replay_executions_pkey PRIMARY KEY (id);


--
-- Name: replay_runs replay_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.replay_runs
    ADD CONSTRAINT replay_runs_pkey PRIMARY KEY (id);


--
-- Name: risk_clusters risk_clusters_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_clusters
    ADD CONSTRAINT risk_clusters_pkey PRIMARY KEY (cluster_id);


--
-- Name: risk_exposure_groups risk_exposure_groups_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_exposure_groups
    ADD CONSTRAINT risk_exposure_groups_name_key UNIQUE (name);


--
-- Name: risk_exposure_groups risk_exposure_groups_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_exposure_groups
    ADD CONSTRAINT risk_exposure_groups_pkey PRIMARY KEY (id);


--
-- Name: risk_orchestrator_policies risk_orchestrator_policies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_orchestrator_policies
    ADD CONSTRAINT risk_orchestrator_policies_pkey PRIMARY KEY (id);


--
-- Name: risk_policies risk_policies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_policies
    ADD CONSTRAINT risk_policies_pkey PRIMARY KEY (id);


--
-- Name: risk_policy_audit_events risk_policy_audit_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_policy_audit_events
    ADD CONSTRAINT risk_policy_audit_events_pkey PRIMARY KEY (id);


--
-- Name: runtime_scan_candidates runtime_scan_candidates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.runtime_scan_candidates
    ADD CONSTRAINT runtime_scan_candidates_pkey PRIMARY KEY (id);


--
-- Name: scanner_fallback_events scanner_fallback_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scanner_fallback_events
    ADD CONSTRAINT scanner_fallback_events_pkey PRIMARY KEY (id);


--
-- Name: scanner_performance_snapshots scanner_performance_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scanner_performance_snapshots
    ADD CONSTRAINT scanner_performance_snapshots_pkey PRIMARY KEY (id);


--
-- Name: signal_events signal_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.signal_events
    ADD CONSTRAINT signal_events_pkey PRIMARY KEY (id);


--
-- Name: state_rebuild_logs state_rebuild_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.state_rebuild_logs
    ADD CONSTRAINT state_rebuild_logs_pkey PRIMARY KEY (id);


--
-- Name: strategy_allocations strategy_allocations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_allocations
    ADD CONSTRAINT strategy_allocations_pkey PRIMARY KEY (strategy_id);


--
-- Name: strategy_definitions strategy_definitions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_definitions
    ADD CONSTRAINT strategy_definitions_pkey PRIMARY KEY (strategy_id);


--
-- Name: strategy_family_gates strategy_family_gates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_family_gates
    ADD CONSTRAINT strategy_family_gates_pkey PRIMARY KEY (family);


--
-- Name: strategy_observability_events strategy_observability_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_observability_events
    ADD CONSTRAINT strategy_observability_events_pkey PRIMARY KEY (id);


--
-- Name: strategy_outcome_memory strategy_outcome_memory_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_outcome_memory
    ADD CONSTRAINT strategy_outcome_memory_pkey PRIMARY KEY (id);


--
-- Name: strategy_regime_bindings strategy_regime_bindings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_regime_bindings
    ADD CONSTRAINT strategy_regime_bindings_pkey PRIMARY KEY (binding_id);


--
-- Name: strategy_templates strategy_templates_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_templates
    ADD CONSTRAINT strategy_templates_name_key UNIQUE (name);


--
-- Name: strategy_templates strategy_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_templates
    ADD CONSTRAINT strategy_templates_pkey PRIMARY KEY (id);


--
-- Name: strategy_versions strategy_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_versions
    ADD CONSTRAINT strategy_versions_pkey PRIMARY KEY (version_id);


--
-- Name: symbol_selection_watchlists symbol_selection_watchlists_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.symbol_selection_watchlists
    ADD CONSTRAINT symbol_selection_watchlists_pkey PRIMARY KEY (id);


--
-- Name: system_alerts system_alerts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_alerts
    ADD CONSTRAINT system_alerts_pkey PRIMARY KEY (id);


--
-- Name: test_table test_table_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.test_table
    ADD CONSTRAINT test_table_pkey PRIMARY KEY (id);


--
-- Name: testnet_execution_logs testnet_execution_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.testnet_execution_logs
    ADD CONSTRAINT testnet_execution_logs_pkey PRIMARY KEY (id);


--
-- Name: execution_intents unique_intent; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.execution_intents
    ADD CONSTRAINT unique_intent UNIQUE (intent_id);


--
-- Name: user_execution_intents unique_user_execution_intent_idempotency_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_execution_intents
    ADD CONSTRAINT unique_user_execution_intent_idempotency_key UNIQUE (idempotency_key);


--
-- Name: universe_rollout_state universe_rollout_state_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.universe_rollout_state
    ADD CONSTRAINT universe_rollout_state_pkey PRIMARY KEY (id);


--
-- Name: indicator_computation_cache uq_indicator_computation_cache_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.indicator_computation_cache
    ADD CONSTRAINT uq_indicator_computation_cache_key UNIQUE (cache_key);


--
-- Name: strategy_versions uq_strategy_versions_strategy_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_versions
    ADD CONSTRAINT uq_strategy_versions_strategy_version UNIQUE (strategy_id, version_number);


--
-- Name: user_indicator_watchlist uq_user_indicator_watchlist_symbol; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_indicator_watchlist
    ADD CONSTRAINT uq_user_indicator_watchlist_symbol UNIQUE (user_id, exchange, market_type, symbol);


--
-- Name: user_scanner_symbol_selections uq_user_scanner_symbol_selection; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_scanner_symbol_selections
    ADD CONSTRAINT uq_user_scanner_symbol_selection UNIQUE (user_id, scanner_id);


--
-- Name: user_decision_traces user_decision_traces_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_decision_traces
    ADD CONSTRAINT user_decision_traces_pkey PRIMARY KEY (id);


--
-- Name: user_exchange_connections user_exchange_connections_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_exchange_connections
    ADD CONSTRAINT user_exchange_connections_pkey PRIMARY KEY (id);


--
-- Name: user_exchange_settings user_exchange_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_exchange_settings
    ADD CONSTRAINT user_exchange_settings_pkey PRIMARY KEY (id);


--
-- Name: user_exchange_settings user_exchange_settings_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_exchange_settings
    ADD CONSTRAINT user_exchange_settings_user_id_key UNIQUE (user_id);


--
-- Name: user_execution_intents user_execution_intents_intent_token_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_execution_intents
    ADD CONSTRAINT user_execution_intents_intent_token_key UNIQUE (intent_token);


--
-- Name: user_execution_intents user_execution_intents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_execution_intents
    ADD CONSTRAINT user_execution_intents_pkey PRIMARY KEY (id);


--
-- Name: user_indicator_saved_queries user_indicator_saved_queries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_indicator_saved_queries
    ADD CONSTRAINT user_indicator_saved_queries_pkey PRIMARY KEY (id);


--
-- Name: user_indicator_watchlist user_indicator_watchlist_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_indicator_watchlist
    ADD CONSTRAINT user_indicator_watchlist_pkey PRIMARY KEY (id);


--
-- Name: user_learning_simulation_suggestions user_learning_simulation_suggestions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_learning_simulation_suggestions
    ADD CONSTRAINT user_learning_simulation_suggestions_pkey PRIMARY KEY (id);


--
-- Name: user_mfa_backup_codes user_mfa_backup_codes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_mfa_backup_codes
    ADD CONSTRAINT user_mfa_backup_codes_pkey PRIMARY KEY (id);


--
-- Name: user_mfa_preferences user_mfa_preferences_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_mfa_preferences
    ADD CONSTRAINT user_mfa_preferences_pkey PRIMARY KEY (id);


--
-- Name: user_onboarding_profiles user_onboarding_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_onboarding_profiles
    ADD CONSTRAINT user_onboarding_profiles_pkey PRIMARY KEY (id);


--
-- Name: user_risk_settings user_risk_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_risk_settings
    ADD CONSTRAINT user_risk_settings_pkey PRIMARY KEY (id);


--
-- Name: user_risk_settings user_risk_settings_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_risk_settings
    ADD CONSTRAINT user_risk_settings_user_id_key UNIQUE (user_id);


--
-- Name: user_scanner_automation_configs user_scanner_automation_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_scanner_automation_configs
    ADD CONSTRAINT user_scanner_automation_configs_pkey PRIMARY KEY (id);


--
-- Name: user_scanner_automation_configs user_scanner_automation_configs_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_scanner_automation_configs
    ADD CONSTRAINT user_scanner_automation_configs_user_id_key UNIQUE (user_id);


--
-- Name: user_scanner_automation_profiles user_scanner_automation_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_scanner_automation_profiles
    ADD CONSTRAINT user_scanner_automation_profiles_pkey PRIMARY KEY (id);


--
-- Name: user_scanner_results user_scanner_results_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_scanner_results
    ADD CONSTRAINT user_scanner_results_pkey PRIMARY KEY (id);


--
-- Name: user_scanner_symbol_selections user_scanner_symbol_selections_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_scanner_symbol_selections
    ADD CONSTRAINT user_scanner_symbol_selections_pkey PRIMARY KEY (id);


--
-- Name: user_signal_modes user_signal_modes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_signal_modes
    ADD CONSTRAINT user_signal_modes_pkey PRIMARY KEY (id);


--
-- Name: user_signal_modes user_signal_modes_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_signal_modes
    ADD CONSTRAINT user_signal_modes_user_id_key UNIQUE (user_id);


--
-- Name: user_venue_assignments user_venue_assignments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_venue_assignments
    ADD CONSTRAINT user_venue_assignments_pkey PRIMARY KEY (id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: weekly_report_archives weekly_report_archives_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.weekly_report_archives
    ADD CONSTRAINT weekly_report_archives_pkey PRIMARY KEY (report_id);


--
-- Name: ix_allowed_markets_exchange_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_allowed_markets_exchange_code ON public.allowed_markets USING btree (exchange_code);


--
-- Name: ix_audit_logs_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_action ON public.audit_logs USING btree (action);


--
-- Name: ix_auth_mfa_challenges_challenge_token_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_auth_mfa_challenges_challenge_token_hash ON public.auth_mfa_challenges USING btree (challenge_token_hash);


--
-- Name: ix_auth_mfa_challenges_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_auth_mfa_challenges_expires_at ON public.auth_mfa_challenges USING btree (expires_at);


--
-- Name: ix_auth_mfa_challenges_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_auth_mfa_challenges_user_id ON public.auth_mfa_challenges USING btree (user_id);


--
-- Name: ix_bot_profiles_is_deleted; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_bot_profiles_is_deleted ON public.bot_profiles USING btree (is_deleted);


--
-- Name: ix_bot_profiles_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_bot_profiles_user_id ON public.bot_profiles USING btree (user_id);


--
-- Name: ix_canonical_strategy_registry_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_canonical_strategy_registry_enabled ON public.canonical_strategy_registry USING btree (is_enabled);


--
-- Name: ix_canonical_strategy_registry_family; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_canonical_strategy_registry_family ON public.canonical_strategy_registry USING btree (strategy_family);


--
-- Name: ix_decision_trace_cold_context_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_decision_trace_cold_context_hash ON public.decision_trace_cold USING btree (context_hash);


--
-- Name: ix_decision_trace_cold_correlation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_decision_trace_cold_correlation_id ON public.decision_trace_cold USING btree (correlation_id);


--
-- Name: ix_decision_trace_cold_decision_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_decision_trace_cold_decision_hash ON public.decision_trace_cold USING btree (decision_hash);


--
-- Name: ix_decision_trace_cold_strategy_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_decision_trace_cold_strategy_version_id ON public.decision_trace_cold USING btree (strategy_version_id);


--
-- Name: ix_decision_trace_hot_context_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_decision_trace_hot_context_hash ON public.decision_trace_hot USING btree (context_hash);


--
-- Name: ix_decision_trace_hot_correlation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_decision_trace_hot_correlation_id ON public.decision_trace_hot USING btree (correlation_id);


--
-- Name: ix_decision_trace_hot_decision_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_decision_trace_hot_decision_hash ON public.decision_trace_hot USING btree (decision_hash);


--
-- Name: ix_decision_trace_hot_strategy_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_decision_trace_hot_strategy_version_id ON public.decision_trace_hot USING btree (strategy_version_id);


--
-- Name: ix_exchange_capabilities_exchange_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_exchange_capabilities_exchange_code ON public.exchange_capabilities USING btree (exchange_code);


--
-- Name: ix_exchange_registry_exchange_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_exchange_registry_exchange_code ON public.exchange_registry USING btree (exchange_code);


--
-- Name: ix_execution_correction_events_execution_metric_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_execution_correction_events_execution_metric_id ON public.execution_correction_events USING btree (execution_metric_id);


--
-- Name: ix_execution_correction_events_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_execution_correction_events_user_id ON public.execution_correction_events USING btree (user_id);


--
-- Name: ix_execution_events_bot_profile_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_execution_events_bot_profile_id ON public.execution_events USING btree (bot_profile_id);


--
-- Name: ix_execution_intent_events_event_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_execution_intent_events_event_type ON public.execution_intent_events USING btree (event_type);


--
-- Name: ix_execution_intent_events_intent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_execution_intent_events_intent_id ON public.execution_intent_events USING btree (intent_id);


--
-- Name: ix_execution_intents_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_execution_intents_account_id ON public.execution_intents USING btree (account_id);


--
-- Name: ix_execution_intents_context_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_execution_intents_context_hash ON public.execution_intents USING btree (context_hash);


--
-- Name: ix_execution_intents_correlation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_execution_intents_correlation_id ON public.execution_intents USING btree (correlation_id);


--
-- Name: ix_execution_intents_decision_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_execution_intents_decision_hash ON public.execution_intents USING btree (decision_hash);


--
-- Name: ix_execution_intents_intent_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_execution_intents_intent_hash ON public.execution_intents USING btree (intent_hash);


--
-- Name: ix_execution_intents_strategy_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_execution_intents_strategy_id ON public.execution_intents USING btree (strategy_id);


--
-- Name: ix_execution_intents_strategy_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_execution_intents_strategy_version_id ON public.execution_intents USING btree (strategy_version_id);


--
-- Name: ix_execution_lifecycle_events_execution_metric_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_execution_lifecycle_events_execution_metric_id ON public.execution_lifecycle_events USING btree (execution_metric_id);


--
-- Name: ix_execution_lifecycle_events_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_execution_lifecycle_events_user_id ON public.execution_lifecycle_events USING btree (user_id);


--
-- Name: ix_execution_metrics_exchange_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_execution_metrics_exchange_order_id ON public.execution_metrics USING btree (exchange_order_id);


--
-- Name: ix_execution_metrics_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_execution_metrics_order_id ON public.execution_metrics USING btree (order_id);


--
-- Name: ix_execution_metrics_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_execution_metrics_user_id ON public.execution_metrics USING btree (user_id);


--
-- Name: ix_execution_state_transitions_execution_event_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_execution_state_transitions_execution_event_id ON public.execution_state_transitions USING btree (execution_event_id);


--
-- Name: ix_execution_state_transitions_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_execution_state_transitions_state ON public.execution_state_transitions USING btree (state);


--
-- Name: ix_family_outcome_memory_family; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_family_outcome_memory_family ON public.family_outcome_memory USING btree (family);


--
-- Name: ix_indicator_computation_cache_bar_close_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_indicator_computation_cache_bar_close_time ON public.indicator_computation_cache USING btree (bar_close_time);


--
-- Name: ix_indicator_computation_cache_cache_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_indicator_computation_cache_cache_key ON public.indicator_computation_cache USING btree (cache_key);


--
-- Name: ix_indicator_computation_cache_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_indicator_computation_cache_expires_at ON public.indicator_computation_cache USING btree (expires_at);


--
-- Name: ix_indicator_computation_cache_indicator_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_indicator_computation_cache_indicator_name ON public.indicator_computation_cache USING btree (indicator_name);


--
-- Name: ix_indicator_computation_cache_params_version; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_indicator_computation_cache_params_version ON public.indicator_computation_cache USING btree (params_version);


--
-- Name: ix_indicator_computation_cache_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_indicator_computation_cache_symbol ON public.indicator_computation_cache USING btree (symbol);


--
-- Name: ix_indicator_computation_cache_timeframe; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_indicator_computation_cache_timeframe ON public.indicator_computation_cache USING btree (timeframe);


--
-- Name: ix_learning_decision_events_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_learning_decision_events_created_at ON public.learning_decision_events USING btree (created_at);


--
-- Name: ix_learning_decision_events_decision; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_learning_decision_events_decision ON public.learning_decision_events USING btree (decision);


--
-- Name: ix_learning_decision_events_outcome_label; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_learning_decision_events_outcome_label ON public.learning_decision_events USING btree (outcome_label);


--
-- Name: ix_learning_decision_events_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_learning_decision_events_symbol ON public.learning_decision_events USING btree (symbol);


--
-- Name: ix_learning_recommendations_family; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_learning_recommendations_family ON public.learning_recommendations USING btree (family);


--
-- Name: ix_learning_recommendations_strategy_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_learning_recommendations_strategy_id ON public.learning_recommendations USING btree (strategy_id);


--
-- Name: ix_learning_recommendations_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_learning_recommendations_type ON public.learning_recommendations USING btree (recommendation_type);


--
-- Name: ix_manual_override_log_action_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_manual_override_log_action_type ON public.manual_override_log USING btree (action_type);


--
-- Name: ix_manual_override_log_admin_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_manual_override_log_admin_id ON public.manual_override_log USING btree (admin_id);


--
-- Name: ix_manual_override_log_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_manual_override_log_timestamp ON public.manual_override_log USING btree ("timestamp");


--
-- Name: ix_paper_positions_bot_profile_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_paper_positions_bot_profile_id ON public.paper_positions USING btree (bot_profile_id);


--
-- Name: ix_paper_positions_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_paper_positions_symbol ON public.paper_positions USING btree (symbol);


--
-- Name: ix_paper_positions_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_paper_positions_user_id ON public.paper_positions USING btree (user_id);


--
-- Name: ix_pending_signals_bot_profile_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pending_signals_bot_profile_id ON public.pending_signals USING btree (bot_profile_id);


--
-- Name: ix_pending_signals_created_order_intent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pending_signals_created_order_intent_id ON public.pending_signals USING btree (created_order_intent_id);


--
-- Name: ix_pending_signals_current_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pending_signals_current_state ON public.pending_signals USING btree (current_state);


--
-- Name: ix_pending_signals_exchange_connection_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pending_signals_exchange_connection_id ON public.pending_signals USING btree (exchange_connection_id);


--
-- Name: ix_pending_signals_order_position_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pending_signals_order_position_id ON public.pending_signals USING btree (order_position_id);


--
-- Name: ix_pending_signals_risk_policy_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pending_signals_risk_policy_id ON public.pending_signals USING btree (risk_policy_id);


--
-- Name: ix_pending_signals_signal_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pending_signals_signal_id ON public.pending_signals USING btree (signal_id);


--
-- Name: ix_pending_signals_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pending_signals_status ON public.pending_signals USING btree (status);


--
-- Name: ix_pending_signals_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pending_signals_symbol ON public.pending_signals USING btree (symbol);


--
-- Name: ix_pending_signals_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pending_signals_user_id ON public.pending_signals USING btree (user_id);


--
-- Name: ix_permission_drift_events_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_permission_drift_events_user_id ON public.permission_drift_events USING btree (user_id);


--
-- Name: ix_portfolio_exposure_snapshot_cluster_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_portfolio_exposure_snapshot_cluster_id ON public.portfolio_exposure_snapshot USING btree (cluster_id);


--
-- Name: ix_portfolio_exposure_snapshot_strategy_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_portfolio_exposure_snapshot_strategy_id ON public.portfolio_exposure_snapshot USING btree (strategy_id);


--
-- Name: ix_portfolio_exposure_snapshot_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_portfolio_exposure_snapshot_symbol ON public.portfolio_exposure_snapshot USING btree (symbol);


--
-- Name: ix_portfolio_exposure_snapshot_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_portfolio_exposure_snapshot_timestamp ON public.portfolio_exposure_snapshot USING btree ("timestamp");


--
-- Name: ix_portfolio_exposure_snapshot_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_portfolio_exposure_snapshot_user_id ON public.portfolio_exposure_snapshot USING btree (user_id);


--
-- Name: ix_position_ledger_events_position_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_position_ledger_events_position_id ON public.position_ledger_events USING btree (position_id);


--
-- Name: ix_positions_cluster_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_positions_cluster_id ON public.positions USING btree (cluster_id);


--
-- Name: ix_positions_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_positions_status ON public.positions USING btree (status);


--
-- Name: ix_positions_strategy_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_positions_strategy_id ON public.positions USING btree (strategy_id);


--
-- Name: ix_positions_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_positions_symbol ON public.positions USING btree (symbol);


--
-- Name: ix_positions_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_positions_user_id ON public.positions USING btree (user_id);


--
-- Name: ix_regime_snapshots_regime_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_regime_snapshots_regime_hash ON public.regime_snapshots USING btree (regime_hash);


--
-- Name: ix_regime_snapshots_regime_label; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_regime_snapshots_regime_label ON public.regime_snapshots USING btree (regime_label);


--
-- Name: ix_regime_snapshots_strategy_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_regime_snapshots_strategy_version_id ON public.regime_snapshots USING btree (strategy_version_id);


--
-- Name: ix_regime_snapshots_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_regime_snapshots_symbol ON public.regime_snapshots USING btree (symbol);


--
-- Name: ix_regime_snapshots_timeframe; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_regime_snapshots_timeframe ON public.regime_snapshots USING btree (timeframe);


--
-- Name: ix_regime_snapshots_timestamp_utc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_regime_snapshots_timestamp_utc ON public.regime_snapshots USING btree (timestamp_utc);


--
-- Name: ix_release_gate_overrides_admin_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_release_gate_overrides_admin_user_id ON public.release_gate_overrides USING btree (admin_user_id);


--
-- Name: ix_replay_equity_points_replay_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_replay_equity_points_replay_run_id ON public.replay_equity_points USING btree (replay_run_id);


--
-- Name: ix_replay_equity_points_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_replay_equity_points_user_id ON public.replay_equity_points USING btree (user_id);


--
-- Name: ix_replay_executions_replay_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_replay_executions_replay_run_id ON public.replay_executions USING btree (replay_run_id);


--
-- Name: ix_replay_executions_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_replay_executions_user_id ON public.replay_executions USING btree (user_id);


--
-- Name: ix_replay_runs_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_replay_runs_user_id ON public.replay_runs USING btree (user_id);


--
-- Name: ix_risk_policies_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_risk_policies_user_id ON public.risk_policies USING btree (user_id);


--
-- Name: ix_risk_policy_audit_events_replay_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_risk_policy_audit_events_replay_run_id ON public.risk_policy_audit_events USING btree (replay_run_id);


--
-- Name: ix_risk_policy_audit_events_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_risk_policy_audit_events_user_id ON public.risk_policy_audit_events USING btree (user_id);


--
-- Name: ix_runtime_scan_candidates_decision; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_runtime_scan_candidates_decision ON public.runtime_scan_candidates USING btree (decision);


--
-- Name: ix_runtime_scan_candidates_market_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_runtime_scan_candidates_market_type ON public.runtime_scan_candidates USING btree (market_type);


--
-- Name: ix_runtime_scan_candidates_scan_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_runtime_scan_candidates_scan_timestamp ON public.runtime_scan_candidates USING btree (scan_timestamp);


--
-- Name: ix_runtime_scan_candidates_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_runtime_scan_candidates_symbol ON public.runtime_scan_candidates USING btree (symbol);


--
-- Name: ix_scanner_fallback_events_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scanner_fallback_events_created_at ON public.scanner_fallback_events USING btree (created_at);


--
-- Name: ix_scanner_fallback_events_event_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scanner_fallback_events_event_type ON public.scanner_fallback_events USING btree (event_type);


--
-- Name: ix_scanner_fallback_events_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scanner_fallback_events_run_id ON public.scanner_fallback_events USING btree (run_id);


--
-- Name: ix_scanner_performance_snapshots_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scanner_performance_snapshots_created_at ON public.scanner_performance_snapshots USING btree (created_at);


--
-- Name: ix_scanner_performance_snapshots_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scanner_performance_snapshots_run_id ON public.scanner_performance_snapshots USING btree (run_id);


--
-- Name: ix_scanner_performance_snapshots_stage; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scanner_performance_snapshots_stage ON public.scanner_performance_snapshots USING btree (stage);


--
-- Name: ix_scanner_performance_snapshots_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scanner_performance_snapshots_user_id ON public.scanner_performance_snapshots USING btree (user_id);


--
-- Name: ix_signal_events_bot_profile_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_signal_events_bot_profile_id ON public.signal_events USING btree (bot_profile_id);


--
-- Name: ix_signal_events_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_signal_events_user_id ON public.signal_events USING btree (user_id);


--
-- Name: ix_strategy_allocations_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_allocations_state ON public.strategy_allocations USING btree (state);


--
-- Name: ix_strategy_definitions_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_strategy_definitions_code ON public.strategy_definitions USING btree (code);


--
-- Name: ix_strategy_definitions_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_definitions_created_by ON public.strategy_definitions USING btree (created_by);


--
-- Name: ix_strategy_definitions_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_definitions_name ON public.strategy_definitions USING btree (name);


--
-- Name: ix_strategy_observability_events_audit_log_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_observability_events_audit_log_id ON public.strategy_observability_events USING btree (audit_log_id);


--
-- Name: ix_strategy_observability_events_bot_profile_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_observability_events_bot_profile_id ON public.strategy_observability_events USING btree (bot_profile_id);


--
-- Name: ix_strategy_observability_events_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_observability_events_created_at ON public.strategy_observability_events USING btree (created_at);


--
-- Name: ix_strategy_observability_events_event_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_observability_events_event_type ON public.strategy_observability_events USING btree (event_type);


--
-- Name: ix_strategy_observability_events_market_regime; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_observability_events_market_regime ON public.strategy_observability_events USING btree (market_regime);


--
-- Name: ix_strategy_observability_events_rejection_reason; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_observability_events_rejection_reason ON public.strategy_observability_events USING btree (rejection_reason);


--
-- Name: ix_strategy_observability_events_selection_cycle_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_observability_events_selection_cycle_id ON public.strategy_observability_events USING btree (selection_cycle_id);


--
-- Name: ix_strategy_observability_events_strategy_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_observability_events_strategy_id ON public.strategy_observability_events USING btree (strategy_id);


--
-- Name: ix_strategy_observability_events_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_observability_events_symbol ON public.strategy_observability_events USING btree (symbol);


--
-- Name: ix_strategy_observability_events_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_observability_events_user_id ON public.strategy_observability_events USING btree (user_id);


--
-- Name: ix_strategy_outcome_memory_strategy_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_outcome_memory_strategy_id ON public.strategy_outcome_memory USING btree (strategy_id);


--
-- Name: ix_strategy_regime_bindings_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_regime_bindings_created_by ON public.strategy_regime_bindings USING btree (created_by);


--
-- Name: ix_strategy_regime_bindings_strategy_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_regime_bindings_strategy_version_id ON public.strategy_regime_bindings USING btree (strategy_version_id);


--
-- Name: ix_strategy_templates_strategy_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_templates_strategy_type ON public.strategy_templates USING btree (strategy_type);


--
-- Name: ix_strategy_versions_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_versions_created_by ON public.strategy_versions USING btree (created_by);


--
-- Name: ix_strategy_versions_strategy_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_versions_strategy_id ON public.strategy_versions USING btree (strategy_id);


--
-- Name: ix_strategy_versions_version_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_strategy_versions_version_hash ON public.strategy_versions USING btree (version_hash);


--
-- Name: ix_symbol_selection_watchlists_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_symbol_selection_watchlists_name ON public.symbol_selection_watchlists USING btree (name);


--
-- Name: ix_symbol_selection_watchlists_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_symbol_selection_watchlists_source ON public.symbol_selection_watchlists USING btree (source);


--
-- Name: ix_symbol_selection_watchlists_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_symbol_selection_watchlists_user_id ON public.symbol_selection_watchlists USING btree (user_id);


--
-- Name: ix_system_alerts_alert_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_system_alerts_alert_type ON public.system_alerts USING btree (alert_type);


--
-- Name: ix_system_alerts_entity_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_system_alerts_entity_key ON public.system_alerts USING btree (entity_key);


--
-- Name: ix_system_alerts_fingerprint; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_system_alerts_fingerprint ON public.system_alerts USING btree (fingerprint);


--
-- Name: ix_testnet_execution_logs_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_testnet_execution_logs_user_id ON public.testnet_execution_logs USING btree (user_id);


--
-- Name: ix_user_decision_traces_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_decision_traces_created_at ON public.user_decision_traces USING btree (created_at);


--
-- Name: ix_user_decision_traces_decision; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_decision_traces_decision ON public.user_decision_traces USING btree (decision_status);


--
-- Name: ix_user_decision_traces_entity_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_decision_traces_entity_id ON public.user_decision_traces USING btree (entity_id);


--
-- Name: ix_user_decision_traces_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_decision_traces_expires_at ON public.user_decision_traces USING btree (expires_at);


--
-- Name: ix_user_decision_traces_scope; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_decision_traces_scope ON public.user_decision_traces USING btree (trace_scope);


--
-- Name: ix_user_decision_traces_strategy; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_decision_traces_strategy ON public.user_decision_traces USING btree (strategy_code);


--
-- Name: ix_user_decision_traces_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_decision_traces_user_id ON public.user_decision_traces USING btree (user_id);


--
-- Name: ix_user_exchange_connections_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_exchange_connections_user_id ON public.user_exchange_connections USING btree (user_id);


--
-- Name: ix_user_exchange_settings_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_user_exchange_settings_user_id ON public.user_exchange_settings USING btree (user_id);


--
-- Name: ix_user_execution_intents_intent_token; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_execution_intents_intent_token ON public.user_execution_intents USING btree (intent_token);


--
-- Name: ix_user_execution_intents_intent_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_execution_intents_intent_type ON public.user_execution_intents USING btree (intent_type);


--
-- Name: ix_user_execution_intents_position_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_execution_intents_position_id ON public.user_execution_intents USING btree (position_id);


--
-- Name: ix_user_execution_intents_preview_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_execution_intents_preview_hash ON public.user_execution_intents USING btree (preview_hash);


--
-- Name: ix_user_execution_intents_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_execution_intents_status ON public.user_execution_intents USING btree (status);


--
-- Name: ix_user_execution_intents_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_execution_intents_symbol ON public.user_execution_intents USING btree (symbol);


--
-- Name: ix_user_execution_intents_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_execution_intents_user_id ON public.user_execution_intents USING btree (user_id);


--
-- Name: ix_user_indicator_saved_queries_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_indicator_saved_queries_user_id ON public.user_indicator_saved_queries USING btree (user_id);


--
-- Name: ix_user_indicator_watchlist_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_indicator_watchlist_symbol ON public.user_indicator_watchlist USING btree (symbol);


--
-- Name: ix_user_indicator_watchlist_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_indicator_watchlist_user_id ON public.user_indicator_watchlist USING btree (user_id);


--
-- Name: ix_user_learning_simulation_suggestions_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_learning_simulation_suggestions_created_at ON public.user_learning_simulation_suggestions USING btree (created_at);


--
-- Name: ix_user_learning_simulation_suggestions_family; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_learning_simulation_suggestions_family ON public.user_learning_simulation_suggestions USING btree (family);


--
-- Name: ix_user_learning_simulation_suggestions_recommendation_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_learning_simulation_suggestions_recommendation_type ON public.user_learning_simulation_suggestions USING btree (recommendation_type);


--
-- Name: ix_user_learning_simulation_suggestions_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_learning_simulation_suggestions_status ON public.user_learning_simulation_suggestions USING btree (status);


--
-- Name: ix_user_learning_simulation_suggestions_strategy_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_learning_simulation_suggestions_strategy_id ON public.user_learning_simulation_suggestions USING btree (strategy_id);


--
-- Name: ix_user_learning_simulation_suggestions_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_learning_simulation_suggestions_symbol ON public.user_learning_simulation_suggestions USING btree (symbol);


--
-- Name: ix_user_learning_simulation_suggestions_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_learning_simulation_suggestions_user_id ON public.user_learning_simulation_suggestions USING btree (user_id);


--
-- Name: ix_user_mfa_backup_codes_code_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_mfa_backup_codes_code_hash ON public.user_mfa_backup_codes USING btree (code_hash);


--
-- Name: ix_user_mfa_backup_codes_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_mfa_backup_codes_user_id ON public.user_mfa_backup_codes USING btree (user_id);


--
-- Name: ix_user_mfa_preferences_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_user_mfa_preferences_user_id ON public.user_mfa_preferences USING btree (user_id);


--
-- Name: ix_user_onboarding_profiles_password_reset_token_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_onboarding_profiles_password_reset_token_hash ON public.user_onboarding_profiles USING btree (password_reset_token_hash);


--
-- Name: ix_user_onboarding_profiles_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_user_onboarding_profiles_user_id ON public.user_onboarding_profiles USING btree (user_id);


--
-- Name: ix_user_risk_settings_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_user_risk_settings_user_id ON public.user_risk_settings USING btree (user_id);


--
-- Name: ix_user_scanner_automation_configs_auto_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_scanner_automation_configs_auto_enabled ON public.user_scanner_automation_configs USING btree (auto_enabled);


--
-- Name: ix_user_scanner_automation_configs_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_scanner_automation_configs_user_id ON public.user_scanner_automation_configs USING btree (user_id);


--
-- Name: ix_user_scanner_automation_profiles_auto_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_scanner_automation_profiles_auto_enabled ON public.user_scanner_automation_profiles USING btree (auto_enabled);


--
-- Name: ix_user_scanner_automation_profiles_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_scanner_automation_profiles_name ON public.user_scanner_automation_profiles USING btree (name);


--
-- Name: ix_user_scanner_automation_profiles_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_scanner_automation_profiles_user_id ON public.user_scanner_automation_profiles USING btree (user_id);


--
-- Name: ix_user_scanner_results_generated_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_scanner_results_generated_at ON public.user_scanner_results USING btree (generated_at);


--
-- Name: ix_user_scanner_results_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_scanner_results_run_id ON public.user_scanner_results USING btree (run_id);


--
-- Name: ix_user_scanner_results_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_scanner_results_symbol ON public.user_scanner_results USING btree (symbol);


--
-- Name: ix_user_scanner_results_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_scanner_results_user_id ON public.user_scanner_results USING btree (user_id);


--
-- Name: ix_user_scanner_symbol_selections_saved_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_scanner_symbol_selections_saved_at ON public.user_scanner_symbol_selections USING btree (saved_at);


--
-- Name: ix_user_scanner_symbol_selections_scanner_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_scanner_symbol_selections_scanner_id ON public.user_scanner_symbol_selections USING btree (scanner_id);


--
-- Name: ix_user_scanner_symbol_selections_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_scanner_symbol_selections_user_id ON public.user_scanner_symbol_selections USING btree (user_id);


--
-- Name: ix_user_signal_modes_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_signal_modes_user_id ON public.user_signal_modes USING btree (user_id);


--
-- Name: ix_user_venue_assignments_exchange_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_venue_assignments_exchange_code ON public.user_venue_assignments USING btree (exchange_code);


--
-- Name: ix_user_venue_assignments_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_venue_assignments_user_id ON public.user_venue_assignments USING btree (user_id);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: ix_weekly_report_archives_generated_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_weekly_report_archives_generated_at ON public.weekly_report_archives USING btree (generated_at);


--
-- Name: ix_weekly_report_archives_report_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_weekly_report_archives_report_type ON public.weekly_report_archives USING btree (report_type);


--
-- Name: ix_weekly_report_archives_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_weekly_report_archives_status ON public.weekly_report_archives USING btree (status);


--
-- Name: ix_weekly_report_archives_trigger_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_weekly_report_archives_trigger_source ON public.weekly_report_archives USING btree (trigger_source);


--
-- Name: auth_mfa_challenges auth_mfa_challenges_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_mfa_challenges
    ADD CONSTRAINT auth_mfa_challenges_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: bot_profiles bot_profiles_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_profiles
    ADD CONSTRAINT bot_profiles_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: brand_settings brand_settings_updated_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.brand_settings
    ADD CONSTRAINT brand_settings_updated_by_user_id_fkey FOREIGN KEY (updated_by_user_id) REFERENCES public.users(id);


--
-- Name: decision_trace_cold decision_trace_cold_strategy_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.decision_trace_cold
    ADD CONSTRAINT decision_trace_cold_strategy_version_id_fkey FOREIGN KEY (strategy_version_id) REFERENCES public.strategy_versions(version_id);


--
-- Name: decision_trace_hot decision_trace_hot_strategy_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.decision_trace_hot
    ADD CONSTRAINT decision_trace_hot_strategy_version_id_fkey FOREIGN KEY (strategy_version_id) REFERENCES public.strategy_versions(version_id);


--
-- Name: execution_correction_events execution_correction_events_execution_metric_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.execution_correction_events
    ADD CONSTRAINT execution_correction_events_execution_metric_id_fkey FOREIGN KEY (execution_metric_id) REFERENCES public.execution_metrics(id);


--
-- Name: execution_correction_events execution_correction_events_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.execution_correction_events
    ADD CONSTRAINT execution_correction_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: execution_events execution_events_bot_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.execution_events
    ADD CONSTRAINT execution_events_bot_profile_id_fkey FOREIGN KEY (bot_profile_id) REFERENCES public.bot_profiles(id);


--
-- Name: execution_intent_events execution_intent_events_intent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.execution_intent_events
    ADD CONSTRAINT execution_intent_events_intent_id_fkey FOREIGN KEY (intent_id) REFERENCES public.execution_intents(intent_id);


--
-- Name: execution_intents execution_intents_strategy_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.execution_intents
    ADD CONSTRAINT execution_intents_strategy_id_fkey FOREIGN KEY (strategy_id) REFERENCES public.strategy_definitions(strategy_id);


--
-- Name: execution_intents execution_intents_strategy_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.execution_intents
    ADD CONSTRAINT execution_intents_strategy_version_id_fkey FOREIGN KEY (strategy_version_id) REFERENCES public.strategy_versions(version_id);


--
-- Name: execution_lifecycle_events execution_lifecycle_events_execution_metric_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.execution_lifecycle_events
    ADD CONSTRAINT execution_lifecycle_events_execution_metric_id_fkey FOREIGN KEY (execution_metric_id) REFERENCES public.execution_metrics(id);


--
-- Name: execution_lifecycle_events execution_lifecycle_events_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.execution_lifecycle_events
    ADD CONSTRAINT execution_lifecycle_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: execution_metrics execution_metrics_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.execution_metrics
    ADD CONSTRAINT execution_metrics_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: pending_signals fk_ps_exc_conn; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pending_signals
    ADD CONSTRAINT fk_ps_exc_conn FOREIGN KEY (exchange_connection_id) REFERENCES public.user_exchange_connections(id);


--
-- Name: pending_signals fk_ps_order_intent; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pending_signals
    ADD CONSTRAINT fk_ps_order_intent FOREIGN KEY (created_order_intent_id) REFERENCES public.user_execution_intents(id);


--
-- Name: pending_signals fk_ps_risk_policy; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pending_signals
    ADD CONSTRAINT fk_ps_risk_policy FOREIGN KEY (risk_policy_id) REFERENCES public.risk_policies(id);


--
-- Name: learning_decision_events learning_decision_events_pending_signal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.learning_decision_events
    ADD CONSTRAINT learning_decision_events_pending_signal_id_fkey FOREIGN KEY (pending_signal_id) REFERENCES public.pending_signals(id);


--
-- Name: learning_decision_events learning_decision_events_scanner_result_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.learning_decision_events
    ADD CONSTRAINT learning_decision_events_scanner_result_id_fkey FOREIGN KEY (scanner_result_id) REFERENCES public.user_scanner_results(id);


--
-- Name: learning_decision_events learning_decision_events_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.learning_decision_events
    ADD CONSTRAINT learning_decision_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: manual_override_log manual_override_log_admin_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manual_override_log
    ADD CONSTRAINT manual_override_log_admin_id_fkey FOREIGN KEY (admin_id) REFERENCES public.users(id);


--
-- Name: paper_positions paper_positions_bot_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.paper_positions
    ADD CONSTRAINT paper_positions_bot_profile_id_fkey FOREIGN KEY (bot_profile_id) REFERENCES public.bot_profiles(id);


--
-- Name: paper_positions paper_positions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.paper_positions
    ADD CONSTRAINT paper_positions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: pending_signals pending_signals_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pending_signals
    ADD CONSTRAINT pending_signals_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: permission_drift_events permission_drift_events_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.permission_drift_events
    ADD CONSTRAINT permission_drift_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: portfolio_exposure_snapshot portfolio_exposure_snapshot_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.portfolio_exposure_snapshot
    ADD CONSTRAINT portfolio_exposure_snapshot_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: position_ledger_events position_ledger_events_position_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.position_ledger_events
    ADD CONSTRAINT position_ledger_events_position_id_fkey FOREIGN KEY (position_id) REFERENCES public.paper_positions(id);


--
-- Name: positions positions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.positions
    ADD CONSTRAINT positions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: regime_snapshots regime_snapshots_strategy_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.regime_snapshots
    ADD CONSTRAINT regime_snapshots_strategy_version_id_fkey FOREIGN KEY (strategy_version_id) REFERENCES public.strategy_versions(version_id);


--
-- Name: release_gate_overrides release_gate_overrides_admin_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.release_gate_overrides
    ADD CONSTRAINT release_gate_overrides_admin_user_id_fkey FOREIGN KEY (admin_user_id) REFERENCES public.users(id);


--
-- Name: replay_equity_points replay_equity_points_replay_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.replay_equity_points
    ADD CONSTRAINT replay_equity_points_replay_run_id_fkey FOREIGN KEY (replay_run_id) REFERENCES public.replay_runs(id);


--
-- Name: replay_equity_points replay_equity_points_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.replay_equity_points
    ADD CONSTRAINT replay_equity_points_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: replay_executions replay_executions_replay_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.replay_executions
    ADD CONSTRAINT replay_executions_replay_run_id_fkey FOREIGN KEY (replay_run_id) REFERENCES public.replay_runs(id);


--
-- Name: replay_executions replay_executions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.replay_executions
    ADD CONSTRAINT replay_executions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: replay_runs replay_runs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.replay_runs
    ADD CONSTRAINT replay_runs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: risk_policies risk_policies_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_policies
    ADD CONSTRAINT risk_policies_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: risk_policy_audit_events risk_policy_audit_events_replay_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_policy_audit_events
    ADD CONSTRAINT risk_policy_audit_events_replay_run_id_fkey FOREIGN KEY (replay_run_id) REFERENCES public.replay_runs(id);


--
-- Name: risk_policy_audit_events risk_policy_audit_events_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_policy_audit_events
    ADD CONSTRAINT risk_policy_audit_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: scanner_performance_snapshots scanner_performance_snapshots_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scanner_performance_snapshots
    ADD CONSTRAINT scanner_performance_snapshots_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: signal_events signal_events_bot_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.signal_events
    ADD CONSTRAINT signal_events_bot_profile_id_fkey FOREIGN KEY (bot_profile_id) REFERENCES public.bot_profiles(id);


--
-- Name: signal_events signal_events_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.signal_events
    ADD CONSTRAINT signal_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: strategy_definitions strategy_definitions_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_definitions
    ADD CONSTRAINT strategy_definitions_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: strategy_observability_events strategy_observability_events_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_observability_events
    ADD CONSTRAINT strategy_observability_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: strategy_regime_bindings strategy_regime_bindings_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_regime_bindings
    ADD CONSTRAINT strategy_regime_bindings_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: strategy_regime_bindings strategy_regime_bindings_strategy_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_regime_bindings
    ADD CONSTRAINT strategy_regime_bindings_strategy_version_id_fkey FOREIGN KEY (strategy_version_id) REFERENCES public.strategy_versions(version_id);


--
-- Name: strategy_templates strategy_templates_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_templates
    ADD CONSTRAINT strategy_templates_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: strategy_versions strategy_versions_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_versions
    ADD CONSTRAINT strategy_versions_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: strategy_versions strategy_versions_strategy_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_versions
    ADD CONSTRAINT strategy_versions_strategy_id_fkey FOREIGN KEY (strategy_id) REFERENCES public.strategy_definitions(strategy_id);


--
-- Name: symbol_selection_watchlists symbol_selection_watchlists_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.symbol_selection_watchlists
    ADD CONSTRAINT symbol_selection_watchlists_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: testnet_execution_logs testnet_execution_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.testnet_execution_logs
    ADD CONSTRAINT testnet_execution_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: universe_rollout_state universe_rollout_state_approved_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.universe_rollout_state
    ADD CONSTRAINT universe_rollout_state_approved_by_fkey FOREIGN KEY (approved_by) REFERENCES public.users(id);


--
-- Name: user_decision_traces user_decision_traces_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_decision_traces
    ADD CONSTRAINT user_decision_traces_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: user_exchange_connections user_exchange_connections_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_exchange_connections
    ADD CONSTRAINT user_exchange_connections_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: user_exchange_settings user_exchange_settings_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_exchange_settings
    ADD CONSTRAINT user_exchange_settings_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: user_execution_intents user_execution_intents_admin_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_execution_intents
    ADD CONSTRAINT user_execution_intents_admin_user_id_fkey FOREIGN KEY (admin_user_id) REFERENCES public.users(id);


--
-- Name: user_execution_intents user_execution_intents_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_execution_intents
    ADD CONSTRAINT user_execution_intents_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: user_indicator_saved_queries user_indicator_saved_queries_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_indicator_saved_queries
    ADD CONSTRAINT user_indicator_saved_queries_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: user_indicator_watchlist user_indicator_watchlist_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_indicator_watchlist
    ADD CONSTRAINT user_indicator_watchlist_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: user_learning_simulation_suggestions user_learning_simulation_suggestions_reviewed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_learning_simulation_suggestions
    ADD CONSTRAINT user_learning_simulation_suggestions_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES public.users(id);


--
-- Name: user_learning_simulation_suggestions user_learning_simulation_suggestions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_learning_simulation_suggestions
    ADD CONSTRAINT user_learning_simulation_suggestions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: user_mfa_backup_codes user_mfa_backup_codes_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_mfa_backup_codes
    ADD CONSTRAINT user_mfa_backup_codes_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: user_mfa_preferences user_mfa_preferences_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_mfa_preferences
    ADD CONSTRAINT user_mfa_preferences_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: user_onboarding_profiles user_onboarding_profiles_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_onboarding_profiles
    ADD CONSTRAINT user_onboarding_profiles_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: user_risk_settings user_risk_settings_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_risk_settings
    ADD CONSTRAINT user_risk_settings_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: user_scanner_automation_configs user_scanner_automation_configs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_scanner_automation_configs
    ADD CONSTRAINT user_scanner_automation_configs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: user_scanner_automation_profiles user_scanner_automation_profiles_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_scanner_automation_profiles
    ADD CONSTRAINT user_scanner_automation_profiles_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: user_scanner_results user_scanner_results_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_scanner_results
    ADD CONSTRAINT user_scanner_results_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: user_scanner_symbol_selections user_scanner_symbol_selections_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_scanner_symbol_selections
    ADD CONSTRAINT user_scanner_symbol_selections_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: user_signal_modes user_signal_modes_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_signal_modes
    ADD CONSTRAINT user_signal_modes_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: user_venue_assignments user_venue_assignments_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_venue_assignments
    ADD CONSTRAINT user_venue_assignments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- PostgreSQL database dump complete
--

\unrestrict ny1qrhqgbrB7JhIHeLwNKQaw1iHzhabw0ATmv7WTe77HNpWWyiCKhEA8BtmZ5sM

