import { useEffect, useState } from "react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { ProdConfigRemediationModal } from "@/components/ProdConfigRemediationModal";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const ExecutionPoliciesPage = () => {
  const [payload, setPayload] = useState(null);
  const [remediationState, setRemediationState] = useState(null);
  const [isRemediationOpen, setIsRemediationOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      setIsLoading(true);
      try {
        const [{ data: policyData }, { data: remediationData }] = await Promise.all([
          apiClient.get("/admin/execution-policies"),
          apiClient.get("/admin/system/remediate-config"),
        ]);
        setPayload(policyData);
        setRemediationState(remediationData);
      } catch (error) {
        toast.error(error?.response?.data?.detail || "Execution policy verisi alınamadı");
      } finally {
        setIsLoading(false);
      }
    };
    load();
  }, []);

  if (isLoading) {
    return <LoadingSkeleton rows={7} testId="execution-policies-loading-skeleton" />;
  }

  const registry = payload?.registry || {};
  const engineConfig = payload?.engine_config || {};
  const observability = payload?.observability_metrics || {};
  const decisionLog = payload?.policy_decision_log || [];
  const topReasonCodes = observability?.top_reason_codes || [];
  const criticalViolations = observability?.recent_critical_violations || [];
  const policyVersions = payload?.policy_versions || [];
  const strategyHealth = payload?.strategy_health || [];
  const releaseGate = payload?.release_gate || {};
  const remediationRecommendations = payload?.remediation_recommendations || [];
  const environmentOverrides = payload?.environment_overrides || [];
  const safeModeStates = payload?.safe_mode_states || [];
  const severityDistribution = observability?.violation_aggregations?.["24h"]?.severity_distribution || {};
  const violations = payload?.recent_policy_violations || [];

  return (
    <section className="space-y-4" data-testid="execution-policies-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="execution-policies-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-emerald-300" data-testid="execution-policies-title">Execution Policy View</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="execution-policies-description">
          Symbol leverage cap, margin mode policy, TP/SL constraints ve son policy ihlalleri.
        </p>
      </header>

      <div className="rounded border border-red-700/70 bg-slate-900 p-4" data-testid="execution-policies-remediation-panel">
        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="execution-policies-remediation-header">
          <p className="text-xs uppercase tracking-widest text-red-300" data-testid="execution-policies-remediation-title">System Config · Release Gate Remediation</p>
          <Button
            className="bg-red-600 text-white hover:bg-red-700"
            onClick={() => setIsRemediationOpen(true)}
            data-testid="execution-policies-open-remediation-button"
          >
            Blokajı Çöz
          </Button>
        </div>

        <div className="mt-3 grid gap-2 text-xs text-slate-200 md:grid-cols-2" data-testid="execution-policies-remediation-status-grid">
          <p data-testid="execution-policies-remediation-release-gate-status">release_gate_status: {remediationState?.release_gate_status || "-"}</p>
          <p data-testid="execution-policies-remediation-preflight-status">preflight_status: {remediationState?.preflight_status || "-"}</p>
          <p data-testid="execution-policies-remediation-secret-status">secret_readiness_status: {remediationState?.secret_readiness_status || "-"}</p>
          <p data-testid="execution-policies-remediation-final-decision">final_release_gate_decision: {remediationState?.final_release_gate_decision || "-"}</p>
        </div>

        <div className="mt-2 space-y-1" data-testid="execution-policies-remediation-reasons-list">
          {(remediationState?.release_gate_reason_codes || []).map((item, index) => (
            <p key={`${item}-${index}`} className="font-mono text-xs text-red-200" data-testid={`execution-policies-remediation-reason-${index}`}>{item}</p>
          ))}
          {(remediationState?.release_gate_reason_codes || []).length === 0 && (
            <p className="text-xs text-slate-400" data-testid="execution-policies-remediation-reasons-empty">Aktif reason_code yok.</p>
          )}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2" data-testid="execution-policies-grid">
        <div className="rounded border border-emerald-900/70 bg-slate-900 p-4" data-testid="execution-policies-observability-card">
          <p className="text-xs uppercase tracking-widest text-emerald-300" data-testid="execution-policies-observability-title">Policy Engine Observability</p>
          <div className="mt-3 grid gap-2 text-xs text-slate-200 md:grid-cols-2" data-testid="execution-policies-observability-metrics">
            <p data-testid="execution-policies-rollout-mode">rollout_mode: {engineConfig?.rollout_mode || "shadow"}</p>
            <p data-testid="execution-policies-log-count">decision_log_count: {observability?.decision_log_count ?? 0}</p>
            <p data-testid="execution-policies-violation-count">violation_count: {observability?.violation_count ?? 0}</p>
            <p data-testid="execution-policies-risk-breach-count">risk_breach_count: {observability?.risk_breach_metrics?.breach_count ?? 0}</p>
            <p data-testid="execution-policies-execution-stage-violation-count">execution_stage_violation_count: {observability?.execution_stage_violation_count ?? 0}</p>
            <p data-testid="execution-policies-post-trade-violation-count">post_trade_violation_count: {observability?.post_trade_violation_count ?? 0}</p>
            <p data-testid="execution-policies-failsafe-hard-block-count">failsafe_hard_block_count: {observability?.failsafe_hard_block_count ?? 0}</p>
            <p data-testid="execution-policies-pretrade-total">pre_trade_total: {observability?.pre_post_ratio?.pre_trade_total ?? 0}</p>
            <p data-testid="execution-policies-posttrade-total">post_trade_total: {observability?.pre_post_ratio?.post_trade_total ?? 0}</p>
          </div>

          <div className="mt-3 space-y-2" data-testid="execution-policies-stage-rates">
            {Object.entries(observability?.stage_decision_rates || {}).length === 0 && (
              <p className="text-xs text-slate-400" data-testid="execution-policies-stage-rates-empty">Stage karar oranı verisi yok.</p>
            )}
            {Object.entries(observability?.stage_decision_rates || {}).map(([stage, values]) => (
              <article key={stage} className="rounded border border-slate-800 p-2" data-testid={`execution-policies-stage-rate-${stage}`}>
                <p className="text-xs uppercase tracking-wider text-slate-300" data-testid={`execution-policies-stage-rate-title-${stage}`}>{stage}</p>
                <p className="text-[11px] text-slate-400" data-testid={`execution-policies-stage-rate-allow-${stage}`}>allow_rate: {values?.allow_rate ?? 0}</p>
                <p className="text-[11px] text-slate-400" data-testid={`execution-policies-stage-rate-block-${stage}`}>block_rate: {values?.block_rate ?? 0}</p>
              </article>
            ))}
          </div>

          <div className="mt-3" data-testid="execution-policies-top-reason-codes">
            <p className="text-xs uppercase tracking-wider text-slate-400" data-testid="execution-policies-top-reason-codes-title">Top Reason Codes</p>
            {topReasonCodes.length === 0 && <p className="text-[11px] text-slate-500" data-testid="execution-policies-top-reason-codes-empty">Veri yok.</p>}
            {topReasonCodes.slice(0, 5).map((item, idx) => (
              <p key={`${item.reason_code}-${idx}`} className="text-[11px] text-slate-300" data-testid={`execution-policies-top-reason-code-${idx}`}>
                {item.reason_code}: {item.count}
              </p>
            ))}
          </div>

          <div className="mt-3" data-testid="execution-policies-severity-distribution">
            <p className="text-xs uppercase tracking-wider text-slate-400" data-testid="execution-policies-severity-distribution-title">Severity Distribution (24h)</p>
            {Object.keys(severityDistribution).length === 0 && <p className="text-[11px] text-slate-500" data-testid="execution-policies-severity-distribution-empty">Veri yok.</p>}
            {Object.entries(severityDistribution).map(([key, value], idx) => (
              <p key={`${key}-${idx}`} className="text-[11px] text-slate-300" data-testid={`execution-policies-severity-distribution-row-${idx}`}>{key}: {value}</p>
            ))}
          </div>
        </div>

        <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="execution-policies-registry-card">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="execution-policies-registry-title">Registry</p>
          <pre className="mt-3 overflow-x-auto text-xs text-slate-200" data-testid="execution-policies-registry-json">{JSON.stringify(registry, null, 2)}</pre>
        </div>

        <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="execution-policies-violations-card">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="execution-policies-violations-title">Recent Violations</p>
          <div className="mt-3 space-y-3" data-testid="execution-policies-violations-list">
            {violations.length === 0 && <p className="text-sm text-slate-400" data-testid="execution-policies-violations-empty">Policy ihlali kaydı yok.</p>}
            {violations.map((item) => (
              <article key={`${item.entity_id}-${item.created_at}`} className="rounded border border-slate-800 p-3" data-testid="execution-policies-violation-row">
                <p className="text-xs text-slate-400" data-testid="execution-policies-violation-entity">intent: {item.entity_id}</p>
                <p className="mt-1 text-xs text-slate-400" data-testid="execution-policies-violation-time">{new Date(item.created_at).toLocaleString()}</p>
                <pre className="mt-2 overflow-x-auto text-[11px] text-slate-200" data-testid="execution-policies-violation-details">{JSON.stringify(item.details, null, 2)}</pre>
              </article>
            ))}
          </div>
        </div>
      </div>

      <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="execution-policies-decision-log-card">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="execution-policies-decision-log-title">Policy Decision Log</p>
        <div className="mt-3 space-y-2" data-testid="execution-policies-decision-log-list">
          {decisionLog.length === 0 && <p className="text-sm text-slate-400" data-testid="execution-policies-decision-log-empty">Policy decision log kaydı yok.</p>}
          {decisionLog.slice(0, 12).map((item, index) => (
            <article key={`${item.id}-${index}`} className="rounded border border-slate-800 p-3" data-testid={`execution-policies-decision-log-row-${index}`}>
              <p className="text-xs text-slate-300" data-testid={`execution-policies-decision-log-stage-${index}`}>{item.stage} · {item.enforced_action}</p>
              <p className="text-[11px] text-slate-400" data-testid={`execution-policies-decision-log-reason-${index}`}>reason_code: {item.reason_code || "-"}</p>
              <p className="text-[11px] text-slate-400" data-testid={`execution-policies-decision-log-time-${index}`}>{item.created_at ? new Date(item.created_at).toLocaleString() : "-"}</p>
            </article>
          ))}
        </div>
      </div>

      <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="execution-policies-critical-violations-card">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="execution-policies-critical-violations-title">Recent Critical Violations</p>
        <div className="mt-3 space-y-2" data-testid="execution-policies-critical-violations-list">
          {criticalViolations.length === 0 && <p className="text-sm text-slate-400" data-testid="execution-policies-critical-violations-empty">Critical violation yok.</p>}
          {criticalViolations.slice(0, 8).map((item, idx) => (
            <article key={`${item.violation_id}-${idx}`} className="rounded border border-slate-800 p-3" data-testid={`execution-policies-critical-violation-row-${idx}`}>
              <p className="text-xs text-slate-300" data-testid={`execution-policies-critical-violation-reason-${idx}`}>{item.reason_code} · {item.stage}</p>
              <p className="text-[11px] text-slate-400" data-testid={`execution-policies-critical-violation-rule-${idx}`}>rule: {item.triggered_rule || "-"}</p>
              <p className="text-[11px] text-slate-500" data-testid={`execution-policies-critical-violation-time-${idx}`}>{item.created_at ? new Date(item.created_at).toLocaleString() : "-"}</p>
            </article>
          ))}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3" data-testid="execution-policies-governance-grid">
        <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="execution-policies-policy-versions-card">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="execution-policies-policy-versions-title">Policy Versions</p>
          {policyVersions.length === 0 && <p className="mt-2 text-sm text-slate-400" data-testid="execution-policies-policy-versions-empty">Version kaydı yok.</p>}
          <div className="mt-2 space-y-2" data-testid="execution-policies-policy-versions-list">
            {policyVersions.slice(0, 10).map((item, idx) => (
              <article key={`${item.version_id}-${idx}`} className="rounded border border-slate-800 p-2" data-testid={`execution-policies-policy-version-row-${idx}`}>
                <p className="text-xs text-slate-200" data-testid={`execution-policies-policy-version-code-${idx}`}>{item.policy_code}</p>
                <p className="text-[11px] text-slate-400" data-testid={`execution-policies-policy-version-state-${idx}`}>{item.state} · {item.approval_status}</p>
              </article>
            ))}
          </div>
        </div>

        <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="execution-policies-strategy-health-card">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="execution-policies-strategy-health-title">Strategy Health</p>
          {strategyHealth.length === 0 && <p className="mt-2 text-sm text-slate-400" data-testid="execution-policies-strategy-health-empty">Strategy health verisi yok.</p>}
          <div className="mt-2 space-y-2" data-testid="execution-policies-strategy-health-list">
            {strategyHealth.slice(0, 10).map((item, idx) => (
              <article key={`${item.strategy_id}-${idx}`} className="rounded border border-slate-800 p-2" data-testid={`execution-policies-strategy-health-row-${idx}`}>
                <p className="text-xs text-slate-200" data-testid={`execution-policies-strategy-health-id-${idx}`}>{item.strategy_id}</p>
                <p className="text-[11px] text-slate-400" data-testid={`execution-policies-strategy-health-state-${idx}`}>{item.state} · risk={item.risk_class}</p>
                <p className="text-[11px] text-slate-500" data-testid={`execution-policies-strategy-health-violations-${idx}`}>violations={item.violation_count}</p>
              </article>
            ))}
          </div>
        </div>

        <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="execution-policies-release-gate-card">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="execution-policies-release-gate-title">Release Gate</p>
          <p className="mt-2 text-sm text-slate-200" data-testid="execution-policies-release-gate-status">status: {releaseGate?.status || "UNKNOWN"}</p>
          <p className="text-[11px] text-slate-400" data-testid="execution-policies-release-gate-summary">critical: {releaseGate?.summary?.critical_violation_count ?? 0} · failsafe: {releaseGate?.summary?.failsafe_hard_block_count ?? 0}</p>
          <div className="mt-2" data-testid="execution-policies-release-gate-recommendations">
            <p className="text-[11px] uppercase tracking-wider text-slate-400" data-testid="execution-policies-release-gate-recommendations-title">Recommended Actions</p>
            {(releaseGate?.recommended_actions || []).slice(0, 5).map((item, idx) => (
              <p key={`${idx}-${item}`} className="text-[11px] text-slate-300" data-testid={`execution-policies-release-gate-recommendation-${idx}`}>- {item}</p>
            ))}
          </div>
        </div>
      </div>

      <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="execution-policies-remediation-card">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="execution-policies-remediation-title">Remediation Recommendations</p>
        {remediationRecommendations.length === 0 && <p className="mt-2 text-sm text-slate-400" data-testid="execution-policies-remediation-empty">Öneri yok.</p>}
        <div className="mt-2 space-y-2" data-testid="execution-policies-remediation-list">
          {remediationRecommendations.slice(0, 10).map((item, idx) => (
            <article key={`${item.recommendation_id}-${idx}`} className="rounded border border-slate-800 p-2" data-testid={`execution-policies-remediation-row-${idx}`}>
              <p className="text-xs text-slate-200" data-testid={`execution-policies-remediation-type-${idx}`}>{item.recommendation_type} · {item.status}</p>
              <p className="text-[11px] text-slate-400" data-testid={`execution-policies-remediation-reason-${idx}`}>{item.reason_code || "-"}</p>
              <p className="text-[11px] text-slate-500" data-testid={`execution-policies-remediation-summary-${idx}`}>{item.summary}</p>
            </article>
          ))}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2" data-testid="execution-policies-environment-safe-mode-grid">
        <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="execution-policies-environment-overrides-card">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="execution-policies-environment-overrides-title">Environment Overrides</p>
          {environmentOverrides.length === 0 && <p className="mt-2 text-sm text-slate-400" data-testid="execution-policies-environment-overrides-empty">Override tanımı yok.</p>}
          <div className="mt-2 space-y-2" data-testid="execution-policies-environment-overrides-list">
            {environmentOverrides.slice(0, 10).map((item, idx) => (
              <article key={`${item.override_id}-${idx}`} className="rounded border border-slate-800 p-2" data-testid={`execution-policies-environment-override-row-${idx}`}>
                <p className="text-xs text-slate-200" data-testid={`execution-policies-environment-override-env-${idx}`}>{item.environment} · {item.scope_type}</p>
                <p className="text-[11px] text-slate-400" data-testid={`execution-policies-environment-override-scope-${idx}`}>{item.scope_value} · priority={item.priority}</p>
              </article>
            ))}
          </div>
        </div>

        <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="execution-policies-safe-mode-card">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="execution-policies-safe-mode-title">Safe Mode Visibility</p>
          {safeModeStates.length === 0 && <p className="mt-2 text-sm text-slate-400" data-testid="execution-policies-safe-mode-empty">Safe mode kaydı yok.</p>}
          <div className="mt-2 space-y-2" data-testid="execution-policies-safe-mode-list">
            {safeModeStates.slice(0, 10).map((item, idx) => (
              <article key={`${item.safe_mode_id}-${idx}`} className="rounded border border-slate-800 p-2" data-testid={`execution-policies-safe-mode-row-${idx}`}>
                <p className="text-xs text-slate-200" data-testid={`execution-policies-safe-mode-state-${idx}`}>{item.environment} · {item.scope_type} · {item.is_active ? "ACTIVE" : "INACTIVE"}</p>
                <p className="text-[11px] text-slate-400" data-testid={`execution-policies-safe-mode-reason-${idx}`}>{item.trigger_reason}</p>
                <p className="text-[11px] text-slate-500" data-testid={`execution-policies-safe-mode-time-${idx}`}>{item.activated_at ? new Date(item.activated_at).toLocaleString() : "-"}</p>
              </article>
            ))}
          </div>
        </div>
      </div>

      <ProdConfigRemediationModal
        open={isRemediationOpen}
        onOpenChange={setIsRemediationOpen}
        remediationState={remediationState}
        onSaved={(nextState) => setRemediationState(nextState)}
        testIdPrefix="execution-policies"
      />
    </section>
  );
};