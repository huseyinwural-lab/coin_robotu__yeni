import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { ActiveOverridesTable } from "@/components/strategy-intelligence/ActiveOverridesTable";
import { ActionConfirmationModal } from "@/components/strategy-intelligence/ActionConfirmationModal";
import { AuditSummaryPanel } from "@/components/strategy-intelligence/AuditSummaryPanel";
import { BatchSimulationPanel } from "@/components/strategy-intelligence/BatchSimulationPanel";
import { BeforeAfterImpactCard } from "@/components/strategy-intelligence/BeforeAfterImpactCard";
import { ConflictActionPanel } from "@/components/strategy-intelligence/ConflictActionPanel";
import { DataPortabilityPanel } from "@/components/strategy-intelligence/DataPortabilityPanel";
import { GovernanceBoardPanel } from "@/components/strategy-intelligence/GovernanceBoardPanel";
import { HedgeActionPanel } from "@/components/strategy-intelligence/HedgeActionPanel";
import { MatrixBatchSimulationPanel } from "@/components/strategy-intelligence/MatrixBatchSimulationPanel";
import { OverrideForm } from "@/components/strategy-intelligence/OverrideForm";
import { PresetScenarioPanel } from "@/components/strategy-intelligence/PresetScenarioPanel";
import { RecommendationStackPanel } from "@/components/strategy-intelligence/RecommendationStackPanel";
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

const DEFAULT_HISTORY_FILTERS = {
  run_id: "",
  status_filter: "",
  request_mode: "",
  severity_band: "",
  request_type: "",
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
  const [queueOwnerInput, setQueueOwnerInput] = useState("ops");
  const [selectedQueueIds, setSelectedQueueIds] = useState([]);
  const [decisionPreviewById, setDecisionPreviewById] = useState({});
  const [comparingRunId, setComparingRunId] = useState("");
  const [simulationCompareResult, setSimulationCompareResult] = useState(null);
  const [presetOptions, setPresetOptions] = useState([]);
  const [selectedPreset, setSelectedPreset] = useState("");
  const [presetCustomizeOpen, setPresetCustomizeOpen] = useState(false);
  const [presetOverrides, setPresetOverrides] = useState({});
  const [historyFilters, setHistoryFilters] = useState(DEFAULT_HISTORY_FILTERS);
  const [appliedHistoryFilters, setAppliedHistoryFilters] = useState(DEFAULT_HISTORY_FILTERS);
  const [escalationCenterData, setEscalationCenterData] = useState({ active_breaches: [], acknowledged: [], resolved: [] });
  const [escalationTab, setEscalationTab] = useState("active");
  const [escalationOwnerInput, setEscalationOwnerInput] = useState("ops");
  const [escalationAckReason, setEscalationAckReason] = useState("sla_breach_acknowledged");
  const [escalationResolveReason, setEscalationResolveReason] = useState("sla_breach_resolved");
  const [escalationActionId, setEscalationActionId] = useState("");
  const [matrixConfig, setMatrixConfig] = useState({
    symbols_text: "BTCUSDT,ETHUSDT",
    strategy_bindings_text: "spot_pullback_v1,trend_follow_v1",
    side: "buy",
    base_notional: "100",
  });
  const [isRunningMatrixBatch, setIsRunningMatrixBatch] = useState(false);
  const [matrixBatchResult, setMatrixBatchResult] = useState(null);
  const [exportDataset, setExportDataset] = useState("decision_requests");
  const [isExportingData, setIsExportingData] = useState(false);
  const [importJsonFile, setImportJsonFile] = useState(null);
  const [isImportingData, setIsImportingData] = useState(false);

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
      const historyParams = {
        limit: 40,
        ...(appliedHistoryFilters.run_id ? { run_id: appliedHistoryFilters.run_id } : {}),
        ...(appliedHistoryFilters.status_filter ? { status_filter: appliedHistoryFilters.status_filter } : {}),
        ...(appliedHistoryFilters.request_mode ? { request_mode: appliedHistoryFilters.request_mode } : {}),
        ...(appliedHistoryFilters.severity_band ? { severity_band: appliedHistoryFilters.severity_band } : {}),
        ...(appliedHistoryFilters.request_type ? { request_type: appliedHistoryFilters.request_type } : {}),
      };
      const [dashRes, overridesRes, activeRes, decisionsRes, historyRes, escalationRes] = await Promise.all([
        apiClient.get("/admin/strategy-intelligence"),
        apiClient.get("/admin/manual-overrides"),
        apiClient.get("/admin/active-overrides"),
        apiClient.get("/admin/decision-requests"),
        apiClient.get("/admin/risk-simulation/history", { params: historyParams }),
        apiClient.get("/admin/escalation-center"),
      ]);
      setDashboard(dashRes.data || null);
      setManualOverrides(overridesRes.data || []);
      setActiveOverrides(activeRes.data || []);
      setDecisionRequests(decisionsRes.data?.items || []);
      setSelectedQueueIds([]);
      setSimulationHistory(historyRes.data?.items || []);
      setEscalationCenterData(escalationRes.data || { active_breaches: [], acknowledged: [], resolved: [] });
      setLastUpdatedAt(new Date().toISOString());
    } catch (error) {
      const message = error?.response?.data?.detail || "Strategy intelligence verisi yüklenemedi";
      setLoadError(message);
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  }, [appliedHistoryFilters]);

  const loadPresets = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/admin/risk-simulation/presets");
      setPresetOptions(data?.items || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Preset listesi alınamadı");
      setPresetOptions([]);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    loadPresets();
  }, [loadPresets]);

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
      exposure_change: simulationResult?.exposure_change ?? 0,
      var_change: simulationResult?.var_change ?? 0,
      liquidity_impact: simulationResult?.liquidity_impact ?? 0,
      confidence_adjusted_risk_score: simulationResult?.confidence_adjusted_risk_score ?? 0,
      risk_delta: simulationResult?.risk_delta ?? 0,
      decision_delta: simulationResult?.decision_delta ?? "UNCHANGED",
      decision_summary: simulationResult?.decision_summary ?? {},
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

  const runPresetSimulation = async ({ customized }) => {
    if (!canSimulate) {
      toast.error("Bu rol preset simulation çalıştıramaz");
      return;
    }
    if (!simulationForm.user_id.trim()) {
      toast.error("Preset simulation için user_id zorunlu");
      return;
    }
    if (!selectedPreset) {
      toast.error("Önce preset seçin");
      return;
    }

    const numericOverrides = Object.entries(presetOverrides || {}).reduce((acc, [key, value]) => {
      if (value === "" || value === null || value === undefined) return acc;
      const parsed = Number(value);
      acc[key] = Number.isFinite(parsed) ? parsed : value;
      return acc;
    }, {});

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
        preset_scenario: selectedPreset,
        preset_overrides: customized ? numericOverrides : {},
      };
      const { data } = await apiClient.post("/admin/risk-simulation", payload);
      setSimulationResult(data || null);
      setBatchResult(null);
      setSimulationCompareResult(null);
      toast.success(customized ? "Preset (customize) simulation tamamlandı" : "Preset simulation tamamlandı");
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Preset simulation başarısız");
    } finally {
      setIsRunningSimulation(false);
    }
  };

  const updatePresetOverride = (key, value) => {
    setPresetOverrides((prev) => ({
      ...prev,
      [key]: value,
    }));
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
      const numericOverrides = Object.entries(presetOverrides || {}).reduce((acc, [key, value]) => {
        if (value === "" || value === null || value === undefined) return acc;
        const parsed = Number(value);
        acc[key] = Number.isFinite(parsed) ? parsed : value;
        return acc;
      }, {});

      const { data } = await apiClient.post("/admin/risk-simulation/batch", {
        user_id: simulationForm.user_id,
        symbols,
        intent_payload: {
          side: simulationForm.side,
          notional: Number(simulationForm.notional),
          strategy_binding: simulationForm.strategy_binding,
          volatility_pct: Number(simulationForm.volatility_pct),
        },
        preset_scenario: selectedPreset || null,
        preset_overrides: selectedPreset ? numericOverrides : {},
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

  const openLinkedApprovalFromOverride = async (requestId) => {
    if (!requestId) return;
    setSelectedQueueIds([requestId]);
    await previewDecisionRequest(requestId);
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

  const toggleQueueSelection = (requestId) => {
    setSelectedQueueIds((prev) => {
      if (prev.includes(requestId)) return prev.filter((item) => item !== requestId);
      return [...prev, requestId];
    });
  };

  const toggleQueueSelectAll = () => {
    if (selectedQueueIds.length === decisionRequests.length) {
      setSelectedQueueIds([]);
      return;
    }
    setSelectedQueueIds(decisionRequests.map((item) => item.request_id));
  };

  const assignQueueOwner = async (requestIds) => {
    const owner = String(queueOwnerInput || "").trim();
    if (owner.length < 2) {
      toast.error("assigned_to minimum 2 karakter");
      return;
    }
    const targetIds = (requestIds || []).filter(Boolean).slice(0, 25);
    if (targetIds.length === 0) {
      toast.error("Önce en az 1 kayıt seçin");
      return;
    }

    setDecisionActionRequestId(targetIds[0]);
    try {
      await Promise.all(
        targetIds.map((requestId) =>
          apiClient.post(`/admin/decision-requests/${requestId}/assign-owner`, { assigned_to: owner })
        )
      );
      toast.success(`Owner atandı (${targetIds.length} kayıt)`);
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Owner assign başarısız");
    } finally {
      setDecisionActionRequestId("");
    }
  };

  const ackQueueRequest = async (requestId) => {
    const note = String(decisionReviewNote || "").trim();
    if (note.length < 8) {
      toast.error("ack note minimum 8 karakter");
      return;
    }
    setDecisionActionRequestId(requestId);
    try {
      await apiClient.post(`/admin/decision-requests/${requestId}/ack`, { reason_note: note });
      toast.success("Request ack edildi");
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Ack başarısız");
    } finally {
      setDecisionActionRequestId("");
    }
  };

  const bulkQueueAction = async (action) => {
    if (role !== "super_admin") {
      toast.error("Bulk action sadece super_admin");
      return;
    }
    if (selectedQueueIds.length === 0) {
      toast.error("Bulk için kayıt seçin");
      return;
    }
    if (selectedQueueIds.length > 25) {
      toast.error("Bulk limit max 25");
      return;
    }

    const note = String(decisionReviewNote || "").trim();
    if (note.length < 8) {
      toast.error("review note minimum 8 karakter");
      return;
    }

    setDecisionActionRequestId(selectedQueueIds[0]);
    try {
      const { data } = await apiClient.post("/admin/decision-requests/bulk-action", {
        action,
        request_ids: selectedQueueIds,
        reason_note: note,
      });
      toast.success(`Bulk ${action}: ${data?.processed || 0} kayıt`);
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Bulk action başarısız");
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

  const revertDecisionRequest = async (requestRow, reasonInput) => {
    if (!requestRow?.request_id) {
      toast.error("Geçersiz request");
      return;
    }
    if (!["admin", "super_admin"].includes(role)) {
      toast.error("Revert için admin veya super_admin gerekli");
      return;
    }
    const note = String(reasonInput || "").trim();
    if (note.length < 8) {
      toast.error("revert reason minimum 8 karakter olmalı");
      return;
    }

    setDecisionActionRequestId(requestRow.request_id);
    try {
      const { data } = await apiClient.post(`/admin/decision-requests/${requestRow.request_id}/revert`, {
        reason_note: note,
      });
      if (data?.status === "pending") {
        toast.success("Revert isteği onaya gönderildi");
      } else {
        toast.success("Revert işlemi tamamlandı");
      }
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Revert başarısız");
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

  const updateHistoryFilter = (key, value) => {
    setHistoryFilters((prev) => ({
      ...prev,
      [key]: value,
    }));
  };

  const applyHistoryFilters = () => {
    setAppliedHistoryFilters({ ...historyFilters });
  };

  const resetHistoryFilters = () => {
    setHistoryFilters(DEFAULT_HISTORY_FILTERS);
    setAppliedHistoryFilters(DEFAULT_HISTORY_FILTERS);
  };

  const updateMatrixConfig = (key, value) => {
    setMatrixConfig((prev) => ({
      ...prev,
      [key]: value,
    }));
  };

  const runMatrixBatchSimulation = async () => {
    if (!simulationForm.user_id.trim()) {
      toast.error("Matrix simulation için user_id zorunlu");
      return;
    }
    const symbols = String(matrixConfig.symbols_text || "")
      .split(",")
      .map((item) => item.trim().toUpperCase())
      .filter(Boolean);
    const strategyBindings = String(matrixConfig.strategy_bindings_text || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    if (symbols.length === 0 || strategyBindings.length === 0) {
      toast.error("symbols ve strategy listesi zorunlu");
      return;
    }

    setIsRunningMatrixBatch(true);
    try {
      const { data } = await apiClient.post("/admin/risk-simulation/matrix-batch", {
        user_id: simulationForm.user_id,
        symbols,
        strategy_bindings: strategyBindings,
        side: matrixConfig.side,
        base_notional: Number(matrixConfig.base_notional || 0),
        volatility_pct: Number(simulationForm.volatility_pct || 0),
        preset_scenario: selectedPreset || null,
        preset_overrides: selectedPreset ? presetOverrides : {},
      });
      setMatrixBatchResult(data || null);
      toast.success(`Matrix batch tamamlandı (${data?.total_runs || 0} kombinasyon)`);
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Matrix batch başarısız");
    } finally {
      setIsRunningMatrixBatch(false);
    }
  };

  const acknowledgeEscalation = async (item) => {
    if (!["admin", "super_admin"].includes(role)) {
      toast.error("Ack sadece admin/super_admin");
      return;
    }
    const reason = String(escalationAckReason || "").trim();
    if (reason.length < 8) {
      toast.error("ack reason minimum 8 karakter");
      return;
    }
    const owner = String(escalationOwnerInput || "").trim();
    if (owner.length < 2) {
      toast.error("current_owner minimum 2 karakter");
      return;
    }
    setEscalationActionId(item.escalation_id);
    try {
      await apiClient.post(`/admin/escalation-center/${item.escalation_id}/ack`, {
        escalation_reason: reason,
        current_owner: owner,
      });
      toast.success("Escalation ack edildi");
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Escalation ack başarısız");
    } finally {
      setEscalationActionId("");
    }
  };

  const assignEscalationOwner = async (item) => {
    const owner = String(escalationOwnerInput || "").trim();
    const reason = String(escalationAckReason || "").trim();
    if (owner.length < 2) {
      toast.error("current_owner minimum 2 karakter");
      return;
    }
    if (reason.length < 8) {
      toast.error("assign reason minimum 8 karakter");
      return;
    }

    setEscalationActionId(item.escalation_id);
    try {
      await apiClient.post(`/admin/escalation-center/${item.escalation_id}/assign-owner`, {
        current_owner: owner,
        escalation_reason: reason,
      });
      toast.success("Escalation owner atandı");
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Escalation owner assign başarısız");
    } finally {
      setEscalationActionId("");
    }
  };

  const resolveEscalation = async (item) => {
    if (role !== "super_admin") {
      toast.error("Resolve sadece super_admin");
      return;
    }
    const reason = String(escalationResolveReason || "").trim();
    if (reason.length < 8) {
      toast.error("resolve reason minimum 8 karakter");
      return;
    }
    setEscalationActionId(item.escalation_id);
    try {
      await apiClient.post(`/admin/escalation-center/${item.escalation_id}/resolve`, {
        escalation_reason: reason,
      });
      toast.success("Escalation resolved");
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Escalation resolve başarısız");
    } finally {
      setEscalationActionId("");
    }
  };

  const exportStrategyIntelligenceData = async (format) => {
    setIsExportingData(true);
    try {
      const response = await apiClient.get("/admin/strategy-intelligence/export", {
        params: { export_format: format, dataset: exportDataset },
        responseType: format === "csv" ? "text" : "json",
      });

      const payload = format === "csv" ? response.data : JSON.stringify(response.data, null, 2);
      const mime = format === "csv" ? "text/csv;charset=utf-8;" : "application/json;charset=utf-8;";
      const blob = new Blob([payload], { type: mime });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `strategy_intelligence_${exportDataset}.${format}`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
      toast.success(`${format.toUpperCase()} export hazır`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Export başarısız");
    } finally {
      setIsExportingData(false);
    }
  };

  const onImportJsonFileChange = (event) => {
    const file = event?.target?.files?.[0] || null;
    setImportJsonFile(file);
  };

  const importStrategyIntelligenceJson = async () => {
    if (role !== "super_admin") {
      toast.error("Import sadece super_admin");
      return;
    }
    if (!importJsonFile) {
      toast.error("Önce JSON dosyası seçin");
      return;
    }

    setIsImportingData(true);
    try {
      const text = await importJsonFile.text();
      const parsed = JSON.parse(text);
      const { data } = await apiClient.post("/admin/strategy-intelligence/import-json", parsed);
      toast.success(`Import tamam: simulation=${data?.imported_simulation_runs || 0}, decision=${data?.imported_decision_requests || 0}`);
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Import başarısız");
    } finally {
      setIsImportingData(false);
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
        <PresetScenarioPanel
          canSimulate={canSimulate}
          presets={presetOptions}
          selectedPreset={selectedPreset}
          onSelectPreset={(value) => {
            setSelectedPreset(value);
            setPresetOverrides({});
          }}
          isRunning={isRunningSimulation}
          onRunPreset={() => runPresetSimulation({ customized: false })}
          isCustomizeOpen={presetCustomizeOpen}
          onToggleCustomize={() => setPresetCustomizeOpen((prev) => !prev)}
          presetOverrides={presetOverrides}
          onOverrideChange={updatePresetOverride}
          onCustomizeRun={() => runPresetSimulation({ customized: true })}
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
          onOpenLinkedApproval={openLinkedApprovalFromOverride}
        />
      </div>

      <GovernanceBoardPanel
        role={role}
        queueItems={decisionRequests}
        escalationData={escalationCenterData}
        selectedQueueIds={selectedQueueIds}
        onToggleQueueSelect={toggleQueueSelection}
        onToggleQueueSelectAll={toggleQueueSelectAll}
        queueReviewNote={decisionReviewNote}
        onQueueReviewNoteChange={setDecisionReviewNote}
        queueOwner={queueOwnerInput}
        onQueueOwnerChange={setQueueOwnerInput}
        onQueueAssignOwner={assignQueueOwner}
        onQueueAck={ackQueueRequest}
        onQueuePreview={previewDecisionRequest}
        onQueueApprove={approveDecisionRequest}
        onQueueReject={rejectDecisionRequest}
        onQueueExecute={executeDecisionRequest}
        onQueueRevert={revertDecisionRequest}
        onQueueBulkAction={bulkQueueAction}
        queueActionLoadingId={decisionActionRequestId}
        previewById={decisionPreviewById}
        escalationTab={escalationTab}
        onEscalationTabChange={setEscalationTab}
        escalationOwner={escalationOwnerInput}
        onEscalationOwnerChange={setEscalationOwnerInput}
        escalationAckReason={escalationAckReason}
        onEscalationAckReasonChange={setEscalationAckReason}
        escalationResolveReason={escalationResolveReason}
        onEscalationResolveReasonChange={setEscalationResolveReason}
        onEscalationAssignOwner={assignEscalationOwner}
        onEscalationAck={acknowledgeEscalation}
        onEscalationResolve={resolveEscalation}
        escalationActionLoadingId={escalationActionId}
        onRefresh={load}
      />

      <RecommendationStackPanel items={decisionRequests} />

      <MatrixBatchSimulationPanel
        canSimulate={canSimulate}
        config={matrixConfig}
        onConfigChange={updateMatrixConfig}
        isRunning={isRunningMatrixBatch}
        onRun={runMatrixBatchSimulation}
        result={matrixBatchResult}
      />

      <DataPortabilityPanel
        role={role}
        exportDataset={exportDataset}
        onExportDatasetChange={setExportDataset}
        onExport={exportStrategyIntelligenceData}
        onImportFileChange={onImportJsonFileChange}
        onImportJson={importStrategyIntelligenceJson}
        isExporting={isExportingData}
        isImporting={isImportingData}
        importFileName={importJsonFile?.name || ""}
      />

      <SimulationHistoryPanel
        rows={simulationHistory}
        comparingRunId={comparingRunId}
        compareResult={simulationCompareResult}
        onCompare={compareSimulationRun}
        filters={historyFilters}
        onFilterChange={updateHistoryFilter}
        onApplyFilters={applyHistoryFilters}
        onResetFilters={resetHistoryFilters}
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
