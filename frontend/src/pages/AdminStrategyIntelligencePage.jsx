import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { ActiveOverridesTable } from "@/components/strategy-intelligence/ActiveOverridesTable";
import { ActionConfirmationModal } from "@/components/strategy-intelligence/ActionConfirmationModal";
import { ApprovalQueuePanel } from "@/components/strategy-intelligence/ApprovalQueuePanel";
import { AuditSummaryPanel } from "@/components/strategy-intelligence/AuditSummaryPanel";
import { BatchSimulationPanel } from "@/components/strategy-intelligence/BatchSimulationPanel";
import { BeforeAfterImpactCard } from "@/components/strategy-intelligence/BeforeAfterImpactCard";
import { ConflictActionPanel } from "@/components/strategy-intelligence/ConflictActionPanel";
import { HedgeActionPanel } from "@/components/strategy-intelligence/HedgeActionPanel";
import { OverrideForm } from "@/components/strategy-intelligence/OverrideForm";
import { RebalanceActionPanel } from "@/components/strategy-intelligence/RebalanceActionPanel";
import { RoleVisibilityPanel } from "@/components/strategy-intelligence/RoleVisibilityPanel";
import { SimulationGuardPanel } from "@/components/strategy-intelligence/SimulationGuardPanel";
import { SimulationHistoryPanel } from "@/components/strategy-intelligence/SimulationHistoryPanel";
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
  const canRequestDecision = role === "admin";
  const canApproveExecute = role === "super_admin";

  const [isLoading, setIsLoading] = useState(true);
  const [dashboard, setDashboard] = useState(null);
  const [manualOverrides, setManualOverrides] = useState([]);
  const [activeOverrides, setActiveOverrides] = useState([]);
  const [decisionRequests, setDecisionRequests] = useState([]);
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
  const [isDecisionRequestingType, setIsDecisionRequestingType] = useState("");
  const [decisionActionRequestId, setDecisionActionRequestId] = useState("");
  const [revokingId, setRevokingId] = useState("");
  const [batchResult, setBatchResult] = useState(null);
  const [decisionReviewNote, setDecisionReviewNote] = useState("governance_review_note");
  const [decisionPreviewById, setDecisionPreviewById] = useState({});
  const [comparingRunId, setComparingRunId] = useState("");
  const [simulationCompareResult, setSimulationCompareResult] = useState(null);

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
      const [dashRes, overridesRes, activeRes, decisionsRes, historyRes] = await Promise.all([
        apiClient.get("/admin/strategy-intelligence"),
        apiClient.get("/admin/manual-overrides"),
        apiClient.get("/admin/active-overrides"),
        apiClient.get("/admin/decision-requests"),
        apiClient.get("/admin/risk-simulation/history", { params: { limit: 40 } }),
      ]);
      setDashboard(dashRes.data || null);
      setManualOverrides(overridesRes.data || []);
      setActiveOverrides(activeRes.data || []);
      setDecisionRequests(decisionsRes.data?.items || []);
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
  const rebalanceEvents = useMemo(() => dashboard?.capital_rebalance_events || [], [dashboard]);
  const hedgeSuggestions = useMemo(() => dashboard?.hedge_suggestions || [], [dashboard]);
  const impactSummary = useMemo(
    () => ({
      projected_risk_score: simulationResult?.projected_risk_score ?? 0,
      projected_gate_decision: simulationResult?.projected_gate_decision ?? "ALLOW",
      projected_pnl: simulationResult?.projected_pnl ?? 0,
      projected_drawdown: simulationResult?.projected_drawdown ?? 0,
      projected_exposure: simulationResult?.projected_exposure ?? 0,
      projected_var: simulationResult?.projected_var ?? 0,
      projected_liquidity_impact: simulationResult?.projected_liquidity_impact ?? 0,
      confidence_adjusted_risk_score: simulationResult?.confidence_adjusted_risk_score ?? 0,
      risk_delta: simulationResult?.risk_delta ?? 0,
      decision_delta: simulationResult?.decision_delta ?? "UNCHANGED",
    }),
    [simulationResult]
  );

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
      setSimulationCompareResult(null);
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

  const createDecisionRequest = async ({ requestType, targetType, targetId, reasonNote, impactContext = {} }) => {
    if (!canRequestDecision) {
      toast.error("Decision request sadece admin oluşturabilir");
      return;
    }
    if (!simulationResult?.simulation_id) {
      toast.error("Decision request için önce simulation çalıştırın");
      return;
    }
    if (String(reasonNote || "").trim().length < 8) {
      toast.error("reason_note minimum 8 karakter olmalı");
      return;
    }

    const endpointMap = {
      conflict_resolve: "/admin/decision-requests/conflict-resolve",
      hedge_apply: "/admin/decision-requests/hedge-apply",
      rebalance_change: "/admin/decision-requests/rebalance-change",
    };
    const endpoint = endpointMap[requestType];
    if (!endpoint) {
      toast.error("Geçersiz decision request type");
      return;
    }

    setIsDecisionRequestingType(requestType);
    try {
      const payload = {
        target_type: targetType,
        target_id: targetId,
        reason_note: reasonNote,
        simulation_run_id: simulationResult.simulation_id,
        impact_summary: {
          ...impactSummary,
          ...impactContext,
        },
      };
      const { data } = await apiClient.post(endpoint, payload);
      toast.success(`Request oluşturuldu: ${data?.request_id || "-"}`);
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Decision request oluşturulamadı");
    } finally {
      setIsDecisionRequestingType("");
    }
  };

  const previewDecisionRequest = async (requestId) => {
    setDecisionActionRequestId(requestId);
    try {
      const { data } = await apiClient.get(`/admin/decision-requests/${requestId}/preview`);
      setDecisionPreviewById((prev) => ({
        ...prev,
        [requestId]: data,
      }));
      toast.success("Preview token alındı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Preview alınamadı");
    } finally {
      setDecisionActionRequestId("");
    }
  };

  const approveDecisionRequest = async (requestId) => {
    if (!canApproveExecute) {
      toast.error("Approve sadece super_admin");
      return;
    }
    const note = String(decisionReviewNote || "").trim();
    if (note.length < 8) {
      toast.error("review note minimum 8 karakter olmalı");
      return;
    }

    setDecisionActionRequestId(requestId);
    try {
      await apiClient.post(`/admin/decision-requests/${requestId}/approve`, { reason_note: note });
      toast.success("Request onaylandı");
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Approve başarısız");
    } finally {
      setDecisionActionRequestId("");
    }
  };

  const rejectDecisionRequest = async (requestId) => {
    if (!canApproveExecute) {
      toast.error("Reject sadece super_admin");
      return;
    }
    const note = String(decisionReviewNote || "").trim();
    if (note.length < 8) {
      toast.error("review note minimum 8 karakter olmalı");
      return;
    }

    setDecisionActionRequestId(requestId);
    try {
      await apiClient.post(`/admin/decision-requests/${requestId}/reject`, { reason_note: note });
      toast.success("Request reddedildi");
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Reject başarısız");
    } finally {
      setDecisionActionRequestId("");
    }
  };

  const executeDecisionRequest = async (requestRow) => {
    if (!canApproveExecute) {
      toast.error("Execute sadece super_admin");
      return;
    }
    const note = String(decisionReviewNote || "").trim();
    if (note.length < 8) {
      toast.error("review note minimum 8 karakter olmalı");
      return;
    }

    const requestId = requestRow?.request_id;
    if (!requestId) {
      toast.error("Geçersiz request");
      return;
    }

    setDecisionActionRequestId(requestId);
    try {
      let previewToken = requestRow?.preview_token || decisionPreviewById?.[requestId]?.preview_token || "";
      if (!previewToken) {
        const previewRes = await apiClient.get(`/admin/decision-requests/${requestId}/preview`);
        previewToken = String(previewRes?.data?.preview_token || "");
        setDecisionPreviewById((prev) => ({
          ...prev,
          [requestId]: previewRes?.data,
        }));
      }
      if (!previewToken) {
        toast.error("Execute için preview_token alınamadı");
        return;
      }

      await apiClient.post(`/admin/decision-requests/${requestId}/execute`, {
        reason_note: note,
        preview_token: previewToken,
      });
      toast.success("Request execute edildi");
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Execute başarısız");
    } finally {
      setDecisionActionRequestId("");
    }
  };

  const compareSimulationRun = async (runId) => {
    setComparingRunId(runId);
    try {
      const { data } = await apiClient.get(`/admin/simulation-runs/${runId}/compare-current`);
      setSimulationCompareResult(data || null);
      toast.success("History replay compare hazır");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Compare başarısız");
    } finally {
      setComparingRunId("");
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
      <RoleVisibilityPanel
        role={role}
        canApplyOverride={canApplyOverride}
        canRequestDecision={canRequestDecision}
        canApproveExecute={canApproveExecute}
      />

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
        <BatchSimulationPanel
          canSimulate={canSimulate}
          isRunning={isRunningBatchSimulation}
          batchResult={batchResult}
          onRun={submitBatchSimulation}
        />
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

      <ConflictActionPanel
        conflicts={conflicts}
        canRequestDecision={canRequestDecision}
        isSubmitting={isDecisionRequestingType === "conflict_resolve"}
        onRequest={createDecisionRequest}
      />

      <HedgeActionPanel
        hedgeSuggestions={hedgeSuggestions}
        canRequestDecision={canRequestDecision}
        isSubmitting={isDecisionRequestingType === "hedge_apply"}
        onRequest={createDecisionRequest}
      />

      <RebalanceActionPanel
        rebalanceEvents={rebalanceEvents}
        canRequestDecision={canRequestDecision}
        isSubmitting={isDecisionRequestingType === "rebalance_change"}
        onRequest={createDecisionRequest}
      />

      <div className="col-span-12" data-testid="strategy-intelligence-active-overrides-wrapper">
        <ActiveOverridesTable
          rows={activeOverrides}
          canRevoke={canApplyOverride}
          revokingId={revokingId}
          onRevoke={revokeOverride}
        />
      </div>

      <ApprovalQueuePanel
        items={decisionRequests}
        role={role}
        reviewNote={decisionReviewNote}
        onReviewNoteChange={setDecisionReviewNote}
        actionLoadingId={decisionActionRequestId}
        onPreview={previewDecisionRequest}
        onApprove={approveDecisionRequest}
        onReject={rejectDecisionRequest}
        onExecute={executeDecisionRequest}
        previewById={decisionPreviewById}
      />

      <SimulationHistoryPanel
        rows={simulationHistory}
        comparingRunId={comparingRunId}
        compareResult={simulationCompareResult}
        onCompare={compareSimulationRun}
      />

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
