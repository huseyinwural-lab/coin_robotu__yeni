--
-- PostgreSQL database dump
--

\restrict CuZhmt5gD1xVLsBU1A9IvgzBN7J0FbLkMgYhOD1vuhzUt9sD8LWpWKqf9RnqbJw

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
    take_profit_price double precision
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
20260318_0052
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
\.


--
-- Data for Name: brand_settings; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.brand_settings (id, app_name, logo_filename, logo_mime_type, logo_blob, logo_storage_note, metadata_json, updated_by_user_id, updated_at, created_at) FROM stdin;
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
global	binance	futures_testnet	t	f	[]	0.1	1	6	150	f	f	f	f	2026-03-19 06:49:08.74668+00
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
\.


--
-- Data for Name: position_ledger_events; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.position_ledger_events (id, position_id, event_type, payload, created_at) FROM stdin;
\.


--
-- Data for Name: positions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.positions (position_id, user_id, symbol, size, entry_price, current_price, unrealized_pnl, leverage, strategy_id, cluster_id, status, created_at, updated_at) FROM stdin;
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
\.


--
-- Data for Name: strategy_allocations; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.strategy_allocations (strategy_id, capital_weight, max_capital, current_capital, confidence_score, performance_score, state, expected_return, realized_return, signal_decay, execution_quality_score, updated_at) FROM stdin;
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
trend	t	5	5	1	2	t	t	f	2026-03-19 06:49:08.767585+00	2026-03-19 06:49:08.767587+00
breakout	t	4	4	1	2	t	t	f	2026-03-19 06:49:08.767588+00	2026-03-19 06:49:08.767589+00
pullback	t	4	4	1	2	t	t	f	2026-03-19 06:49:08.767589+00	2026-03-19 06:49:08.76759+00
reversal	t	3	3	1	1.5	t	t	t	2026-03-19 06:49:08.76759+00	2026-03-19 06:49:08.767591+00
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
\.


--
-- Data for Name: test_table; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.test_table (id, marker) FROM stdin;
3	backup_test
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
\.


--
-- Data for Name: user_execution_intents; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.user_execution_intents (id, user_id, source_type, source_ref_id, status, intent_token, preview_hash, queue_mode, approval_required, symbol, market_type, side, notional, normalized_order_payload, reject_reason_codes, risk_flags, submitted_at, approved_at, released_at, cancelled_at, admin_user_id, admin_note, created_at, updated_at, risk_score, gate_decision, meta_engine_decision, cluster_id, intent_type, position_id, size, reduce_only, price, stop_price, take_profit_price) FROM stdin;
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
-- Data for Name: user_mfa_preferences; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.user_mfa_preferences (id, user_id, is_enabled, enabled_methods, totp_secret, totp_verified, email_otp_verified, updated_at, created_at) FROM stdin;
\.


--
-- Data for Name: user_onboarding_profiles; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.user_onboarding_profiles (id, user_id, full_name, phone, email_verified, verification_code, verification_expires_at, verification_requested_at, password_reset_token_hash, password_reset_expires_at, password_reset_requested_at, created_at, updated_at) FROM stdin;
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
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.users (id, email, password_hash, role, is_active, created_at, updated_at, approval_status, approval_requested_at, approved_at, disabled_at) FROM stdin;
9ca118ab-d054-415a-92e0-023e9e08fe22	admin@platform.local	$2b$12$Ijbg4ZzLGxxMsqEiK6nB4ueRyd9m2uzEdSXJ77pyFK5vvt2T6zQkS	SUPER_ADMIN	t	2026-03-19 06:49:08.711124+00	2026-03-19 06:49:08.711126+00	approved	2026-03-19 06:49:08.710181+00	2026-03-19 06:49:08.710186+00	\N
\.


--
-- Data for Name: weekly_report_archives; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.weekly_report_archives (report_id, report_type, period_start, period_end, generated_at, timezone, filename, storage_path, size_bytes, sha256, status, trigger_source, generated_by, created_at, updated_at) FROM stdin;
\.


--
-- Name: test_table_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.test_table_id_seq', 3, true);


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

\unrestrict CuZhmt5gD1xVLsBU1A9IvgzBN7J0FbLkMgYhOD1vuhzUt9sD8LWpWKqf9RnqbJw

