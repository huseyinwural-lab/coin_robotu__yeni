import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { ActiveOverridesTable } from "@/components/strategy-intelligence/ActiveOverridesTable";
import { ActionConfirmationModal } from "@/components/strategy-intelligence/ActionConfirmationModal";
import { AuditSummaryPanel } from "@/components/strategy-intelligence/AuditSummaryPanel";
import { BeforeAfterImpactCard } from "@/components/strategy-intelligence/BeforeAfterImpactCard";
import { OverrideForm } from "@/components/strategy-intelligence/OverrideForm";
import { SimulationGuardPanel } from "@/components/strategy-intelligence/SimulationGuardPanel";
import { StrategyIntelligencePageContainer } from "@/components/strategy-intelligence/StrategyIntelligencePageContainer";
import { useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";

const DEFAULT_FORM = {
  user_id: "",
  symbol: "BTCUSDT",
  side: "buy",
  notional: 100,
  strategy_binding: "spot_pullback_v1",
  volatility_pct: 3,
  override_action_type: "",
  override_reason: "",
  override_target_id: "",
  override_ttl_minutes: "60",
  override_expires_at: "",
};

export const AdminStrategyIntelligencePage = () => {
  const { user } = useAuth();
  const role = String(user?.role || "");
  const canSimulate = ["super_admin", "admin", "ops", "viewer", "risk_manager", "operator"].includes(role);
  const canApplyOverride = ["super_admin", "admin"].includes(role);

  const [isLoading, setIsLoading] = useState(true);
  const [dashboard, setDashboard] = useState(null);
  const [manualOverrides, setManualOverrides] = useState([]);
  const [activeOverrides, setActiveOverrides] = useState([]);
  const [approvalRequests, setApprovalRequests] = useState([]);
  const [simulationHistory, setSimulationHistory] = useState([]);
  const [loadError, setLoadError] = useState("");
  const [lastUpdatedAt, setLastUpdatedAt] = useState("");

  const [simulationForm, setSimulationForm] = useState(DEFAULT_FORM);
  const [simulationResult, setSimulationResult] = useState(null);
  const [simulationSymbolSource, setSimulationSymbolSource] = useState("crypto");
  const [simulationSymbolMode, setSimulationSymbolMode] = useState("all_market_symbols");
  const [simulationSelectedSymbols, setSimulationSelectedSymbols] = useState(["BTCUSDT"]);

  const [isRunningSimulation, setIsRunningSimulation] = useState(false);
  const [isRunningBatchSimulation, setIsRunningBatchSimulation] = useState(false);
  const [isApplyingOverride, setIsApplyingOverride] = useState(false);
  const [isApprovingRequest, setIsApprovingRequest] = useState("");
  const [revokingId, setRevokingId] = useState("");
  const [batchResult, setBatchResult] = useState(null);
  const [approvalReviewNote, setApprovalReviewNote] = useState("phase_next_step_review");

  const [confirmOpen, setConfirmOpen] = useState(false);

  useEffect(() => {
    if ((simulationSelectedSymbols || []).length === 0) return;
    setSimulationForm((prev) => ({ ...prev, symbol: simulationSelectedSymbols[0] }));
  }, [simulationSelectedSymbols]);

  useEffect(() => {
    if (!user?.id) return;
    setSimulationForm((prev) => (prev.user_id ? prev : { ...prev, user_id: String(user.id) }));
  }, [user?.id]);

  const load = useCallback(async () => {
    setIsLoading(true);
    setLoadError("");
    try {
      const [dashRes, overridesRes, activeRes, approvalsRes, historyRes] = await Promise.all([
        apiClient.get("/admin/strategy-intelligence"),
        apiClient.get("/admin/manual-overrides"),
        apiClient.get("/admin/active-overrides"),
        apiClient.get("/admin/override-approval-requests"),
        apiClient.get("/admin/risk-simulation/history", { params: { limit: 40 } }),
      ]);
      setDashboard(dashRes.data || null);
      setManualOverrides(overridesRes.data || []);
      setActiveOverrides(activeRes.data || []);
      setApprovalRequests(approvalsRes.data?.items || []);
      setSimulationHistory(historyRes.data?.items || []);
      setLastUpdatedAt(new Date().toISOString());
    } catch (error) {
      const message = error?.response?.data?.detail || "Strategy intelligence verisi yüklenemedi";
      setLoadError(message);
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const conflicts = useMemo(() => dashboard?.strategy_conflicts || [], [dashboard]);
  const hedgeSuggestions = useMemo(() => dashboard?.hedge_suggestions || [], [dashboard]);

  const submitSimulation = async () => {
    if (!simulationForm.user_id.trim()) {
      toast.error("Simulation için user_id zorunlu");
      return;
    }
    setIsRunningSimulation(true);
    try {
      const payload = {
        user_id: simulationForm.user_id,
        intent_payload: {
          symbol: simulationForm.symbol,
          side: simulationForm.side,
          notional: Number(simulationForm.notional),
          strategy_binding: simulationForm.strategy_binding,
          volatility_pct: Number(simulationForm.volatility_pct),
          position_size_value: Number(simulationForm.notional),
        },
        apply_override: false,
      };
      const { data } = await apiClient.post("/admin/risk-simulation", payload);
      setSimulationResult(data || null);
      setBatchResult(null);
      toast.success("Simulation tamamlandı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Simulation başarısız");
    } finally {
      setIsRunningSimulation(false);
    }
  };

  const submitBatchSimulation = async () => {
    if (!simulationForm.user_id.trim()) {
      toast.error("Batch simulation için user_id zorunlu");
      return;
    }
    const symbols = (simulationSelectedSymbols || []).map((item) => String(item || "").toUpperCase()).filter(Boolean);
    if (symbols.length === 0) {
      toast.error("Batch simulation için en az 1 symbol seçin");
      return;
    }

    setIsRunningBatchSimulation(true);
    try {
      const { data } = await apiClient.post("/admin/risk-simulation/batch", {
        user_id: simulationForm.user_id,
        symbols,
        intent_payload: {
          side: simulationForm.side,
          notional: Number(simulationForm.notional),
          strategy_binding: simulationForm.strategy_binding,
          volatility_pct: Number(simulationForm.volatility_pct),
        },
      });
      setBatchResult(data || null);
      toast.success(`Batch simulation tamamlandı (${data?.total_symbols || symbols.length} symbol)`);
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Batch simulation başarısız");
    } finally {
      setIsRunningBatchSimulation(false);
    }
  };

  const requestApplyOverride = () => {
    if (!simulationResult?.simulation_id) {
      toast.error("Apply öncesi simulation zorunlu");
      return;
    }
    if (String(simulationForm.override_reason || "").trim().length < 12) {
      toast.error("Reason minimum 12 karakter olmalı");
      return;
    }
    if (!simulationForm.override_expires_at && Number(simulationForm.override_ttl_minutes || 0) <= 0) {
      toast.error("Expiry zorunlu (expires_at veya ttl_minutes)");
      return;
    }
    setConfirmOpen(true);
  };

  const confirmApplyOverride = async () => {
    setIsApplyingOverride(true);
    try {
      const payload = {
        scope: "strategy_intelligence",
        target_type: "user",
        target_id: simulationForm.override_target_id || simulationForm.user_id,
        action_type: simulationForm.override_action_type,
        reason: simulationForm.override_reason,
        simulation_id: simulationResult?.simulation_id,
        expires_at: simulationForm.override_expires_at ? new Date(simulationForm.override_expires_at).toISOString() : null,
        ttl_minutes: simulationForm.override_expires_at ? null : Number(simulationForm.override_ttl_minutes || 0),
        confirmation_id: `confirm_${Date.now()}`,
        previous_state: simulationResult?.before_state || {},
        next_state: simulationResult?.after_state || {},
        impact_preview: {
          projected_risk_score: simulationResult?.projected_risk_score,
          projected_gate_decision: simulationResult?.projected_gate_decision,
          risk_delta: simulationResult?.risk_delta,
          decision_delta: simulationResult?.decision_delta,
          projected_pnl: simulationResult?.projected_pnl,
          projected_drawdown: simulationResult?.projected_drawdown,
        },
        payload: {
          source: "strategy_intelligence_decision_engine",
          user_id: simulationForm.user_id,
          symbol: simulationForm.symbol,
        },
      };
      const { data } = await apiClient.post("/admin/manual-overrides", payload);
      if (data?.status === "pending_approval") {
        toast.success(data?.message || "Override isteği onaya gönderildi");
      } else {
        toast.success(data?.message || "Override uygulandı ve audit log’a yazıldı");
      }
      setConfirmOpen(false);
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Override apply başarısız");
    } finally {
      setIsApplyingOverride(false);
    }
  };

  const revokeOverride = async (row) => {
    if (!canApplyOverride) {
      toast.error("Bu rol revoke yetkisine sahip değil");
      return;
    }
    const reason = window.prompt("Revoke reason (min 12 karakter):", "manual_revoke_for_safety");
    if (!reason || reason.trim().length < 12) {
      toast.error("Revoke reason minimum 12 karakter olmalı");
      return;
    }

    setRevokingId(row.override_id);
    try {
      await apiClient.post(`/admin/manual-overrides/${row.override_id}/revoke`, { reason });
      toast.success("Override revoke edildi");
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Override revoke başarısız");
    } finally {
      setRevokingId("");
    }
  };

  const approveRequest = async (requestId, action) => {
    if (role !== "super_admin") {
      toast.error("Approval kararı sadece super_admin");
      return;
    }
    const note = String(approvalReviewNote || "").trim();
    if (note.length < 8) {
      toast.error("review note minimum 8 karakter olmalı");
      return;
    }

    setIsApprovingRequest(requestId);
    try {
      const endpoint = action === "approve" ? "approve" : "reject";
      const { data } = await apiClient.post(`/admin/override-approval-requests/${requestId}/${endpoint}`, {
        reason_note: note,
      });
      toast.success(data?.message || `Request ${action}`);
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Approval işlemi başarısız");
    } finally {
      setIsApprovingRequest("");
    }
  };

  if (isLoading) {
    return <LoadingSkeleton rows={10} testId="strategy-intelligence-loading-skeleton" />;
  }

  if (!dashboard) {
    return (
      <section className="space-y-4" data-testid="strategy-intelligence-broken-state">
        <div className="border border-rose-500/40 bg-rose-900/20 p-4" data-testid="strategy-intelligence-broken-alert">
          <p className="text-sm font-semibold text-rose-200" data-testid="strategy-intelligence-broken-title">Strategy intelligence verisi alınamadı</p>
          <p className="mt-1 text-sm text-rose-100" data-testid="strategy-intelligence-broken-message">{loadError || "Servis geçici olarak yanıt vermiyor."}</p>
        </div>
      </section>
    );
  }

  return (
    <StrategyIntelligencePageContainer
      role={role}
      lastUpdatedAt={lastUpdatedAt}
      dashboard={dashboard}
      loadError={loadError}
      onRefresh={load}
    >
      <div className="col-span-12 border border-slate-800 bg-slate-900 p-3" data-testid="strategy-intelligence-role-visibility-panel">
        <p className="text-xs text-slate-300" data-testid="strategy-intelligence-role-visibility-text">
          {canApplyOverride
            ? role === "admin"
              ? "admin: simulate + confirm + request (approval-gated)"
              : "super_admin: simulate + confirm + apply/revoke + approve-execute"
            : "ops/viewer: read-only + simulation; kritik aksiyonlar kapalı"}
        </p>
      </div>

      <div className="col-span-12 lg:col-span-7 space-y-4" data-testid="strategy-intelligence-left-column">
        <SimulationGuardPanel
          form={simulationForm}
          setForm={setSimulationForm}
          canSimulate={canSimulate}
          isRunning={isRunningSimulation}
          onRun={submitSimulation}
          symbolSource={simulationSymbolSource}
          onSymbolSource={setSimulationSymbolSource}
          symbolMode={simulationSymbolMode}
          onSymbolMode={setSimulationSymbolMode}
          selectedSymbols={simulationSelectedSymbols}
          onSelectedSymbols={setSimulationSelectedSymbols}
        />
        <div className="border border-slate-800 bg-slate-900 p-4" data-testid="strategy-intelligence-batch-simulation-panel">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="strategy-intelligence-batch-simulation-title">Batch Simulation (selected symbols)</p>
          <button
            type="button"
            onClick={submitBatchSimulation}
            disabled={!canSimulate || isRunningBatchSimulation}
            className="mt-2 rounded border border-black bg-black px-3 py-1 text-sm text-orange-300 disabled:opacity-50"
            data-testid="strategy-intelligence-run-batch-simulation-button"
          >
            {isRunningBatchSimulation ? "Batch simulation..." : "Run Batch Simulation"}
          </button>
          {batchResult && (
            <div className="mt-2 space-y-1 text-xs" data-testid="strategy-intelligence-batch-simulation-result">
              <p data-testid="strategy-intelligence-batch-simulation-summary">summary={JSON.stringify(batchResult.summary || {})}</p>
              {(batchResult.items || []).slice(0, 8).map((item, index) => (
                <p key={`${item.simulation_id}-${index}`} data-testid={`strategy-intelligence-batch-simulation-item-${index}`}>
                  {item.symbol} · risk={item.projected_risk_score} · adj_risk={item.confidence_adjusted_risk_score} · delta={item.risk_delta}
                </p>
              ))}
            </div>
          )}
        </div>
        <BeforeAfterImpactCard simulationResult={simulationResult} />
      </div>

      <div className="col-span-12 lg:col-span-5 space-y-4" data-testid="strategy-intelligence-right-column">
        <OverrideForm
          form={simulationForm}
          setForm={setSimulationForm}
          canApply={canApplyOverride}
          simulationReady={Boolean(simulationResult?.simulation_id)}
          onRequestApply={requestApplyOverride}
          isSubmitting={isApplyingOverride}
        />
        <AuditSummaryPanel manualOverrides={manualOverrides} activeOverrides={activeOverrides} />
      </div>

      <div className="col-span-12 lg:col-span-6 border border-slate-800 bg-slate-900 p-4" data-testid="strategy-intelligence-conflicts-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="strategy-intelligence-conflicts-title">Strategy Conflicts</p>
        <div className="mt-2 space-y-2" data-testid="strategy-intelligence-conflicts-list">
          {conflicts.slice(0, 8).map((item, index) => (
            <article key={`${item.winning_strategy}-${index}`} className="border border-slate-800 p-2" data-testid={`strategy-intelligence-conflict-item-${index}`}>
              <p className="text-sm" data-testid={`strategy-intelligence-conflict-winner-${index}`}>winner: {item.winning_strategy || "-"}</p>
              <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-conflict-loser-${index}`}>loser: {item.losing_strategy || "-"}</p>
              <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-conflict-reason-${index}`}>reason: {item.resolution_reason}</p>
            </article>
          ))}
          {conflicts.length === 0 && <p className="text-sm text-slate-400" data-testid="strategy-intelligence-conflicts-empty">Aktif strategy conflict bulunmuyor.</p>}
        </div>
      </div>

      <div className="col-span-12 lg:col-span-6 border border-slate-800 bg-slate-900 p-4" data-testid="strategy-intelligence-hedge-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="strategy-intelligence-hedge-title">Hedge Suggestions</p>
        <div className="mt-2 space-y-2" data-testid="strategy-intelligence-hedge-list">
          {hedgeSuggestions.slice(0, 8).map((item, index) => (
            <article key={`${item.hedge_symbol || "none"}-${index}`} className="border border-slate-800 p-2" data-testid={`strategy-intelligence-hedge-item-${index}`}>
              <p className="text-sm" data-testid={`strategy-intelligence-hedge-symbol-${index}`}>symbol: {item.hedge_symbol || "none"}</p>
              <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-hedge-size-${index}`}>size: {item.hedge_size}</p>
              <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-hedge-direction-${index}`}>direction: {item.hedge_direction || "-"}</p>
            </article>
          ))}
          {hedgeSuggestions.length === 0 && <p className="text-sm text-slate-400" data-testid="strategy-intelligence-hedge-empty">Aktif hedge önerisi bulunmuyor.</p>}
        </div>
      </div>

      <div className="col-span-12" data-testid="strategy-intelligence-active-overrides-wrapper">
        <ActiveOverridesTable
          rows={activeOverrides}
          canRevoke={canApplyOverride}
          revokingId={revokingId}
          onRevoke={revokeOverride}
        />
      </div>

      <div className="col-span-12 lg:col-span-6 border border-slate-800 bg-slate-900 p-4" data-testid="strategy-intelligence-approval-requests-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="strategy-intelligence-approval-requests-title">Override Approval Requests</p>
        <input
          type="text"
          className="mt-2 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-sm"
          value={approvalReviewNote}
          onChange={(event) => setApprovalReviewNote(event.target.value)}
          data-testid="strategy-intelligence-approval-review-note-input"
        />
        <div className="mt-2 space-y-2" data-testid="strategy-intelligence-approval-requests-list">
          {approvalRequests.slice(0, 12).map((item, index) => (
            <article key={item.request_id} className="border border-slate-800 p-2" data-testid={`strategy-intelligence-approval-request-item-${index}`}>
              <p className="text-sm" data-testid={`strategy-intelligence-approval-request-main-${index}`}>
                {item.request_id} · status={item.status} · requested_by={item.requested_by}
              </p>
              <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-approval-request-reason-${index}`}>{item.reason_note}</p>
              {role === "super_admin" && item.status === "pending" && (
                <div className="mt-2 flex gap-2" data-testid={`strategy-intelligence-approval-request-actions-${index}`}>
                  <button
                    type="button"
                    onClick={() => approveRequest(item.request_id, "approve")}
                    disabled={isApprovingRequest === item.request_id}
                    className="rounded border border-emerald-600 px-2 py-1 text-xs text-emerald-300"
                    data-testid={`strategy-intelligence-approval-request-approve-button-${index}`}
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    onClick={() => approveRequest(item.request_id, "reject")}
                    disabled={isApprovingRequest === item.request_id}
                    className="rounded border border-rose-600 px-2 py-1 text-xs text-rose-300"
                    data-testid={`strategy-intelligence-approval-request-reject-button-${index}`}
                  >
                    Reject
                  </button>
                </div>
              )}
            </article>
          ))}
          {approvalRequests.length === 0 && <p className="text-sm text-slate-400" data-testid="strategy-intelligence-approval-requests-empty">No data yet</p>}
        </div>
      </div>

      <div className="col-span-12 lg:col-span-6 border border-slate-800 bg-slate-900 p-4" data-testid="strategy-intelligence-simulation-history-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="strategy-intelligence-simulation-history-title">Simulation History</p>
        <div className="mt-2 space-y-2" data-testid="strategy-intelligence-simulation-history-list">
          {simulationHistory.slice(0, 12).map((item, index) => (
            <article key={item.run_id} className="border border-slate-800 p-2" data-testid={`strategy-intelligence-simulation-history-item-${index}`}>
              <p className="text-sm" data-testid={`strategy-intelligence-simulation-history-main-${index}`}>
                {item.run_id} · mode={item.request_mode} · status={item.status}
              </p>
              <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-simulation-history-symbols-${index}`}>
                symbols={(item.symbols || []).join(", ") || "-"}
              </p>
              <p className="text-xs text-slate-500" data-testid={`strategy-intelligence-simulation-history-hash-${index}`}>
                hash={item.summary_hash}
              </p>
            </article>
          ))}
          {simulationHistory.length === 0 && <p className="text-sm text-slate-400" data-testid="strategy-intelligence-simulation-history-empty">No data yet</p>}
        </div>
      </div>

      <ActionConfirmationModal
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        onConfirm={confirmApplyOverride}
        isSubmitting={isApplyingOverride}
        title="Override Apply Confirmation"
        description="Apply öncesi simulation impact preview zorunlu doğrulama"
        details={[
          { label: "target", value: simulationForm.override_target_id || simulationForm.user_id || "-" },
          { label: "reason", value: simulationForm.override_reason || "-" },
          { label: "expires", value: simulationForm.override_expires_at || `${simulationForm.override_ttl_minutes || 0}m` },
          { label: "risk_delta", value: simulationResult?.risk_delta ?? "-" },
          { label: "decision_delta", value: simulationResult?.decision_delta ?? "-" },
        ]}
      />
    </StrategyIntelligencePageContainer>
  );
};
