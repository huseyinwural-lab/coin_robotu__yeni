import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";

const windowOptions = ["24h", "7d", "30d"];

const EMPTY_REJECTION_FILTERS = {
  strategy_id: "",
  symbol: "",
  reason: "",
};

const normalizeIds = (ids) => [...new Set((ids || []).map((item) => String(item || "").trim()).filter(Boolean))].sort();

const safeJsonParse = (rawValue, fallback) => {
  try {
    const parsed = JSON.parse(rawValue);
    if (parsed && typeof parsed === "object") {
      return parsed;
    }
    return fallback;
  } catch {
    return fallback;
  }
};

export const AdminStrategyObservabilityPage = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const role = String(user?.role || "");
  const isSuperAdmin = role === "super_admin";
  const canSimulate = ["admin", "super_admin"].includes(role);

  const [windowRange, setWindowRange] = useState("24h");
  const [topN, setTopN] = useState(10);
  const [loading, setLoading] = useState(false);

  const [topSignals, setTopSignals] = useState([]);
  const [selectedSignalIds, setSelectedSignalIds] = useState([]);
  const [governanceReasons, setGovernanceReasons] = useState({});
  const [governanceActionLoading, setGovernanceActionLoading] = useState({});
  const [selectedSimulation, setSelectedSimulation] = useState({
    previewToken: "",
    signalIds: [],
    items: [],
  });

  const [bulkSimulation, setBulkSimulation] = useState({
    previewToken: "",
    items: [],
  });
  const [bulkExecutePreview, setBulkExecutePreview] = useState({
    previewToken: "",
    items: [],
  });
  const [bulkExecuteReason, setBulkExecuteReason] = useState("");
  const [bulkExecuteConfirmChecked, setBulkExecuteConfirmChecked] = useState(false);

  const [executeDialogOpen, setExecuteDialogOpen] = useState(false);
  const [executeReason, setExecuteReason] = useState("");
  const [executeConfirmChecked, setExecuteConfirmChecked] = useState(false);

  const [rejection, setRejection] = useState(null);
  const [rejectionReasons, setRejectionReasons] = useState([]);
  const [rejectionFilterDraft, setRejectionFilterDraft] = useState(EMPTY_REJECTION_FILTERS);
  const [appliedRejectionFilters, setAppliedRejectionFilters] = useState(EMPTY_REJECTION_FILTERS);
  const [rejectionDetailsLoading, setRejectionDetailsLoading] = useState(false);
  const [rejectionDetails, setRejectionDetails] = useState([]);

  const [scoreMetrics, setScoreMetrics] = useState(null);
  const [scoreConfig, setScoreConfig] = useState(null);
  const [scoreThreshold, setScoreThreshold] = useState("0.65");
  const [baseWeight, setBaseWeight] = useState("0.55");
  const [trendWeight, setTrendWeight] = useState("0.25");
  const [volumeWeight, setVolumeWeight] = useState("0.20");
  const [strategyOverridesJson, setStrategyOverridesJson] = useState("{}");
  const [scoreConfigReason, setScoreConfigReason] = useState("");
  const [autoTuningEnabled, setAutoTuningEnabled] = useState(false);
  const [autoTuningReason, setAutoTuningReason] = useState("");
  const [scorePreview, setScorePreview] = useState(null);
  const [scorePreviewStrategyId, setScorePreviewStrategyId] = useState("");
  const [scoreOverrideSignalId, setScoreOverrideSignalId] = useState("");
  const [scoreOverrideDelta, setScoreOverrideDelta] = useState("0.05");
  const [scoreOverrideReason, setScoreOverrideReason] = useState("");

  const [report, setReport] = useState(null);
  const [riskCapital, setRiskCapital] = useState(null);
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(false);
  const [autoRefreshSeconds, setAutoRefreshSeconds] = useState(30);
  const [exportStrategyId, setExportStrategyId] = useState("");

  const [riskLimitsDraft, setRiskLimitsDraft] = useState({
    max_open_risk_pct: "",
    max_daily_loss_pct: "",
    max_portfolio_drawdown_pct: "",
    max_strategy_drawdown_pct: "",
    max_positions_per_strategy: "",
    max_sector_exposure_pct: "",
    max_correlated_positions: "",
  });
  const [riskLimitsPreview, setRiskLimitsPreview] = useState(null);
  const [riskLimitsReason, setRiskLimitsReason] = useState("");
  const [riskLimitsConfirmChecked, setRiskLimitsConfirmChecked] = useState(false);
  const [riskLimitsApplyDialogOpen, setRiskLimitsApplyDialogOpen] = useState(false);

  const [exposureOverrideStrategyId, setExposureOverrideStrategyId] = useState("");
  const [exposureOverrideCapPct, setExposureOverrideCapPct] = useState("20");
  const [exposureOverridePreview, setExposureOverridePreview] = useState(null);
  const [exposureOverrideReason, setExposureOverrideReason] = useState("");
  const [exposureOverrideConfirmChecked, setExposureOverrideConfirmChecked] = useState(false);
  const [exposureApplyDialogOpen, setExposureApplyDialogOpen] = useState(false);

  const [riskAlertLinkLoading, setRiskAlertLinkLoading] = useState(false);
  const [riskAlertLinkDetail, setRiskAlertLinkDetail] = useState(null);

  const [timelineLoading, setTimelineLoading] = useState(false);
  const [timelineSummary, setTimelineSummary] = useState(null);
  const [timelineItems, setTimelineItems] = useState([]);
  const [timelineKpiCards, setTimelineKpiCards] = useState(null);
  const [lastExportSnapshot, setLastExportSnapshot] = useState(null);
  const [scoreOverrideDialogOpen, setScoreOverrideDialogOpen] = useState(false);

  const [auditLimit, setAuditLimit] = useState(50);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditItems, setAuditItems] = useState([]);

  const [actionFeedback, setActionFeedback] = useState({
    state: "idle",
    title: "",
    message: "",
    at: "",
  });

  const [explainabilityOpen, setExplainabilityOpen] = useState(false);
  const [explainabilityLoading, setExplainabilityLoading] = useState(false);
  const [explainabilityData, setExplainabilityData] = useState(null);

  const safeTopN = useMemo(() => Math.min(Math.max(Number(topN) || 10, 1), 50), [topN]);
  const normalizedSelectedSignalIds = useMemo(() => normalizeIds(selectedSignalIds), [selectedSignalIds]);
  const normalizedSelectedSimulationIds = useMemo(() => normalizeIds(selectedSimulation.signalIds), [selectedSimulation.signalIds]);
  const topSignalsById = useMemo(
    () =>
      Object.fromEntries(
        (topSignals || []).map((item) => [String(item.signal_id || ""), item])
      ),
    [topSignals]
  );

  const selectedMatchSimulation = useMemo(() => {
    if (!selectedSimulation.previewToken) {
      return false;
    }
    return normalizedSelectedSignalIds.join("|") === normalizedSelectedSimulationIds.join("|");
  }, [normalizedSelectedSignalIds, normalizedSelectedSimulationIds, selectedSimulation.previewToken]);

  const selectedSignalsApproved = normalizedSelectedSignalIds.every(
    (signalId) => String(topSignalsById?.[signalId]?.governance_status || "pending") === "approved"
  );
  const canExecuteSelectedSignals = isSuperAdmin && normalizedSelectedSignalIds.length > 0 && selectedMatchSimulation && selectedSignalsApproved;
  const timelineChainSummary = useMemo(() => {
    const map = {};
    for (const item of timelineItems || []) {
      const chainId = String(item.chain_id || item.chain_ref || "").trim();
      if (!chainId) {
        continue;
      }
      map[chainId] = (map[chainId] || 0) + 1;
    }
    return Object.entries(map)
      .map(([chainId, count]) => ({ chainId, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 20);
  }, [timelineItems]);
  const allSignalsSelected = topSignals.length > 0 && selectedSignalIds.length === topSignals.length;

  const regimeRows = useMemo(() => {
    const distribution = scoreMetrics?.market_regime_distribution || {};
    return Object.entries(distribution).sort((a, b) => b[1] - a[1]);
  }, [scoreMetrics]);

  const setFeedbackLoading = useCallback((title, message) => {
    setActionFeedback({
      state: "loading",
      title,
      message,
      at: new Date().toISOString(),
    });
  }, []);

  const setFeedbackSuccess = useCallback((title, message) => {
    setActionFeedback({
      state: "success",
      title,
      message,
      at: new Date().toISOString(),
    });
  }, []);

  const setFeedbackError = useCallback((title, message) => {
    setActionFeedback({
      state: "error",
      title,
      message,
      at: new Date().toISOString(),
    });
  }, []);

  const loadAuditLog = useCallback(async () => {
    setAuditLoading(true);
    try {
      const { data } = await apiClient.get("/admin/strategy/audit-log", { params: { limit: auditLimit } });
      setAuditItems(data?.items || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Audit log alınamadı");
      setAuditItems([]);
    } finally {
      setAuditLoading(false);
    }
  }, [auditLimit]);

  const loadRejectionReasons = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/admin/strategy/rejection-analytics/reasons", { params: { window: windowRange } });
      setRejectionReasons(data?.reasons || []);
    } catch {
      setRejectionReasons([]);
    }
  }, [windowRange]);

  const loadRejectionDetails = useCallback(async () => {
    setRejectionDetailsLoading(true);
    try {
      const params = {
        window: windowRange,
        ...(appliedRejectionFilters.strategy_id ? { strategy_id: appliedRejectionFilters.strategy_id } : {}),
        ...(appliedRejectionFilters.symbol ? { symbol: appliedRejectionFilters.symbol } : {}),
        ...(appliedRejectionFilters.reason ? { reason: appliedRejectionFilters.reason } : {}),
      };
      const { data } = await apiClient.get("/admin/strategy/rejection-analytics/details", { params });
      setRejectionDetails(data?.items || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Rejection detayları alınamadı");
      setRejectionDetails([]);
    } finally {
      setRejectionDetailsLoading(false);
    }
  }, [appliedRejectionFilters.reason, appliedRejectionFilters.strategy_id, appliedRejectionFilters.symbol, windowRange]);

  const syncScoreForm = useCallback((configPayload) => {
    setScoreConfig(configPayload);
    setScoreThreshold(String(configPayload?.threshold ?? 0.65));
    setBaseWeight(String(configPayload?.factor_weights?.base_score ?? 0.55));
    setTrendWeight(String(configPayload?.factor_weights?.trend_strength ?? 0.25));
    setVolumeWeight(String(configPayload?.factor_weights?.relative_volume ?? 0.2));
    setStrategyOverridesJson(JSON.stringify(configPayload?.per_strategy || {}, null, 2));
    setAutoTuningEnabled(Boolean(configPayload?.auto_tuning_enabled));
  }, []);

  const syncRiskForm = useCallback((snapshot) => {
    const limits = snapshot?.limits || {};
    setRiskLimitsDraft({
      max_open_risk_pct: String(limits?.max_open_risk_pct ?? ""),
      max_daily_loss_pct: String(limits?.max_daily_loss_pct ?? ""),
      max_portfolio_drawdown_pct: String(limits?.max_portfolio_drawdown_pct ?? ""),
      max_strategy_drawdown_pct: String(limits?.max_strategy_drawdown_pct ?? ""),
      max_positions_per_strategy: String(limits?.max_positions_per_strategy ?? ""),
      max_sector_exposure_pct: String(limits?.max_sector_exposure_pct ?? ""),
      max_correlated_positions: String(limits?.max_correlated_positions ?? ""),
    });
    const allocation = snapshot?.allocation || {};
    const firstStrategy = Object.keys(allocation)[0] || "";
    if (firstStrategy && !exposureOverrideStrategyId) {
      setExposureOverrideStrategyId(firstStrategy);
    }
  }, [exposureOverrideStrategyId]);

  const loadActionImpactTimeline = useCallback(async () => {
    setTimelineLoading(true);
    try {
      const { data } = await apiClient.get("/admin/strategy/action-impact-timeline", {
        params: {
          window: windowRange,
          strategy_id: exportStrategyId || null,
          limit: 120,
        },
      });
      setTimelineSummary(data?.summary || null);
      setTimelineItems(data?.items || []);
      setTimelineKpiCards(data?.kpi_cards || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Action impact timeline alınamadı");
      setTimelineSummary(null);
      setTimelineItems([]);
      setTimelineKpiCards(null);
    } finally {
      setTimelineLoading(false);
    }
  }, [exportStrategyId, windowRange]);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const results = await Promise.allSettled([
        apiClient.get("/admin/strategy/top-signals", { params: { window: windowRange, top_n: safeTopN } }),
        apiClient.get("/admin/strategy/rejection-analytics", { params: { window: windowRange } }),
        apiClient.get("/admin/strategy/score-metrics", { params: { window: windowRange } }),
        apiClient.get("/admin/strategy/report", { params: { window: windowRange } }),
        apiClient.get("/admin/strategy/risk-capital/status", { params: { include_alerts: true } }),
        apiClient.get("/admin/strategy/score-config"),
      ]);

      const [topRes, rejectionRes, scoreRes, reportRes, riskCapitalRes, scoreConfigRes] = results;

      if (topRes.status === "fulfilled") {
        const nextTopSignals = topRes.value?.data?.items || [];
        setTopSignals(nextTopSignals);
        const availableIds = new Set(nextTopSignals.map((item) => String(item.signal_id || "")).filter(Boolean));
        setSelectedSignalIds((prev) => prev.filter((id) => availableIds.has(id)));
      } else {
        throw topRes.reason;
      }

      if (rejectionRes.status === "fulfilled") {
        setRejection(rejectionRes.value?.data || null);
      }
      if (scoreRes.status === "fulfilled") {
        setScoreMetrics(scoreRes.value?.data || null);
      }
      if (reportRes.status === "fulfilled") {
        const reportPayload = reportRes.value?.data || null;
        setReport(reportPayload);
        const firstActiveStrategy = reportPayload?.active_spot_strategies?.[0];
        if (!exportStrategyId && firstActiveStrategy) {
          setExportStrategyId(firstActiveStrategy);
        }
      }
      if (riskCapitalRes.status === "fulfilled") {
        const riskPayload = riskCapitalRes.value?.data || null;
        setRiskCapital(riskPayload);
        syncRiskForm(riskPayload);
      }
      if (scoreConfigRes.status === "fulfilled") {
        syncScoreForm(scoreConfigRes.value?.data?.config || null);
      }
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Strategy observability verisi alınamadı");
    } finally {
      setLoading(false);
    }
  }, [exportStrategyId, safeTopN, syncRiskForm, syncScoreForm, windowRange]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    loadRejectionReasons();
  }, [loadRejectionReasons]);

  useEffect(() => {
    loadRejectionDetails();
  }, [loadRejectionDetails]);

  useEffect(() => {
    loadAuditLog();
  }, [loadAuditLog]);

  useEffect(() => {
    loadActionImpactTimeline();
  }, [loadActionImpactTimeline]);

  useEffect(() => {
    const modalOpen = executeDialogOpen || scoreOverrideDialogOpen || riskLimitsApplyDialogOpen || exposureApplyDialogOpen;
    if (!autoRefreshEnabled || modalOpen) {
      return undefined;
    }
    const intervalMs = Math.max(Number(autoRefreshSeconds) || 30, 10) * 1000;
    const timer = window.setInterval(() => {
      loadData();
      loadRejectionDetails();
      loadAuditLog();
      loadActionImpactTimeline();
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [
    autoRefreshEnabled,
    autoRefreshSeconds,
    executeDialogOpen,
    exposureApplyDialogOpen,
    loadActionImpactTimeline,
    loadAuditLog,
    loadData,
    loadRejectionDetails,
    riskLimitsApplyDialogOpen,
    scoreOverrideDialogOpen,
  ]);

  const updateSelectedSignal = (signalId, checked) => {
    setSelectedSignalIds((prev) => {
      if (checked) {
        return normalizeIds([...prev, signalId]);
      }
      return prev.filter((item) => item !== signalId);
    });
  };

  const toggleSelectAllSignals = (checked) => {
    if (checked) {
      setSelectedSignalIds(normalizeIds(topSignals.map((item) => item.signal_id)));
      return;
    }
    setSelectedSignalIds([]);
  };

  const openExplainability = async (signalId) => {
    setExplainabilityOpen(true);
    setExplainabilityLoading(true);
    setExplainabilityData(null);
    try {
      const { data } = await apiClient.get(`/admin/strategy/signals/${signalId}/explainability`);
      setExplainabilityData(data || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Explainability detayı alınamadı");
    } finally {
      setExplainabilityLoading(false);
    }
  };

  const approveSignal = async (signalId) => {
    if (!isSuperAdmin) {
      toast.error("Approve sadece super_admin için açık");
      return;
    }
    setGovernanceActionLoading((prev) => ({ ...prev, [signalId]: true }));
    try {
      await apiClient.post("/admin/strategy/signals/approve", {
        signal_id: signalId,
        reason: governanceReasons[signalId] || "approved_by_operator",
        metadata: { source: "top_signals_table" },
      });
      toast.success("Signal approved");
      await Promise.all([loadData(), loadAuditLog(), loadActionImpactTimeline()]);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Signal approve başarısız");
    } finally {
      setGovernanceActionLoading((prev) => ({ ...prev, [signalId]: false }));
    }
  };

  const rejectSignal = async (signalId) => {
    if (!isSuperAdmin) {
      toast.error("Reject sadece super_admin için açık");
      return;
    }
    const reason = String(governanceReasons[signalId] || "").trim();
    if (reason.length < 3) {
      toast.error("Reject reason en az 3 karakter olmalı");
      return;
    }
    setGovernanceActionLoading((prev) => ({ ...prev, [signalId]: true }));
    try {
      await apiClient.post("/admin/strategy/signals/reject", {
        signal_id: signalId,
        reason,
        metadata: { source: "top_signals_table" },
      });
      toast.success("Signal rejected");
      await Promise.all([loadData(), loadAuditLog(), loadActionImpactTimeline()]);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Signal reject başarısız");
    } finally {
      setGovernanceActionLoading((prev) => ({ ...prev, [signalId]: false }));
    }
  };

  const simulateSelectedSignals = async () => {
    if (!canSimulate) {
      toast.error("Bu rol simulate çalıştıramaz");
      return;
    }
    if (normalizedSelectedSignalIds.length === 0) {
      toast.error("Önce en az bir sinyal seçin");
      return;
    }
    setFeedbackLoading("Seçili Simülasyon", "Seçili sinyaller simüle ediliyor");
    try {
      const { data } = await apiClient.post("/admin/strategy/top-signals/simulate", {
        signal_ids: normalizedSelectedSignalIds,
      });
      setSelectedSimulation({
        previewToken: data?.preview_token || "",
        signalIds: normalizeIds(normalizedSelectedSignalIds),
        items: data?.items || [],
      });
      setFeedbackSuccess("Seçili Simülasyon", `Simülasyon hazır. preview_token: ${data?.preview_token || "-"}`);
      toast.success("Seçili sinyaller için simülasyon tamamlandı");
    } catch (error) {
      const message = error?.response?.data?.detail || "Simülasyon başarısız";
      setFeedbackError("Seçili Simülasyon", message);
      toast.error(message);
    }
  };

  const executeSelectedSignals = async () => {
    if (!canExecuteSelectedSignals) {
      toast.error("Execute için önce aynı seçimi simüle etmelisiniz");
      return;
    }
    if (String(executeReason || "").trim().length < 3) {
      toast.error("Execute reason en az 3 karakter olmalı");
      return;
    }
    if (!executeConfirmChecked) {
      toast.error("Execute onay kutusunu işaretleyin");
      return;
    }
    setFeedbackLoading("Seçili Execute", "Seçili sinyaller execute ediliyor");
    try {
      const { data } = await apiClient.post("/admin/strategy/top-signals/execute", {
        signal_ids: normalizedSelectedSignalIds,
        preview_token: selectedSimulation.previewToken,
        confirm: true,
        reason: executeReason.trim(),
      });
      setFeedbackSuccess("Seçili Execute", `Execute tamamlandı. executed_count: ${data?.executed_count ?? 0}`);
      toast.success("Seçili sinyaller execute edildi");
      setExecuteDialogOpen(false);
      setExecuteReason("");
      setExecuteConfirmChecked(false);
      setSelectedSimulation({ previewToken: "", signalIds: [], items: [] });
      await Promise.all([loadData(), loadAuditLog()]);
    } catch (error) {
      const message = error?.response?.data?.detail || "Execute başarısız";
      setFeedbackError("Seçili Execute", message);
      toast.error(message);
    }
  };

  const runBulkSimulation = async () => {
    if (!canSimulate) {
      toast.error("Bu rol bulk simulate çalıştıramaz");
      return;
    }
    setFeedbackLoading("Bulk Simülasyon", "Top sinyaller için bulk simülasyon hazırlanıyor");
    try {
      const { data } = await apiClient.post("/admin/strategy/top-signals/bulk-simulate", {
        window: windowRange,
        top_n: safeTopN,
      });
      setBulkSimulation({
        previewToken: data?.preview_token || "",
        items: data?.items || [],
      });
      setFeedbackSuccess("Bulk Simülasyon", `Bulk simülasyon hazır. preview_token: ${data?.preview_token || "-"}`);
      toast.success("Bulk simülasyon tamamlandı");
    } catch (error) {
      const message = error?.response?.data?.detail || "Bulk simülasyon başarısız";
      setFeedbackError("Bulk Simülasyon", message);
      toast.error(message);
    }
  };

  const runBulkExecutePreview = async () => {
    if (!isSuperAdmin) {
      toast.error("Bulk execute preview sadece super_admin için açık");
      return;
    }
    setFeedbackLoading("Bulk Execute Preview", "Bulk execute preview hazırlanıyor");
    try {
      const { data } = await apiClient.post("/admin/strategy/top-signals/bulk-execute", {
        mode: "preview",
        window: windowRange,
        top_n: safeTopN,
      });
      setBulkExecutePreview({
        previewToken: data?.preview_token || "",
        items: data?.items || [],
      });
      setBulkExecuteReason("");
      setBulkExecuteConfirmChecked(false);
      setFeedbackSuccess("Bulk Execute Preview", `Preview hazır. preview_token: ${data?.preview_token || "-"}`);
      toast.success("Bulk execute preview hazır");
    } catch (error) {
      const message = error?.response?.data?.detail || "Bulk execute preview başarısız";
      setFeedbackError("Bulk Execute Preview", message);
      toast.error(message);
    }
  };

  const runBulkExecuteConfirm = async () => {
    if (!isSuperAdmin) {
      toast.error("Bulk execute confirm sadece super_admin için açık");
      return;
    }
    if (!bulkExecutePreview.previewToken) {
      toast.error("Önce bulk execute preview alınmalı");
      return;
    }
    if (String(bulkExecuteReason || "").trim().length < 3) {
      toast.error("Reason en az 3 karakter olmalı");
      return;
    }
    if (!bulkExecuteConfirmChecked) {
      toast.error("Bulk execute onay kutusunu işaretleyin");
      return;
    }
    setFeedbackLoading("Bulk Execute Confirm", "Bulk execute confirm çalışıyor");
    try {
      const { data } = await apiClient.post("/admin/strategy/top-signals/bulk-execute", {
        mode: "confirm",
        preview_token: bulkExecutePreview.previewToken,
        confirm: true,
        reason: bulkExecuteReason.trim(),
      });
      setFeedbackSuccess("Bulk Execute Confirm", `Bulk execute tamamlandı. executed_count: ${data?.executed_count ?? 0}`);
      toast.success("Bulk execute tamamlandı");
      setBulkExecutePreview({ previewToken: "", items: [] });
      setBulkExecuteReason("");
      setBulkExecuteConfirmChecked(false);
      await Promise.all([loadData(), loadAuditLog()]);
    } catch (error) {
      const message = error?.response?.data?.detail || "Bulk execute confirm başarısız";
      setFeedbackError("Bulk Execute Confirm", message);
      toast.error(message);
    }
  };

  const runScorePreview = async () => {
    const threshold = Number(scoreThreshold);
    const factorWeights = {
      base_score: Number(baseWeight),
      trend_strength: Number(trendWeight),
      relative_volume: Number(volumeWeight),
    };
    setFeedbackLoading("Score Preview", "Score tuning preview hazırlanıyor");
    try {
      const { data } = await apiClient.post("/admin/strategy/score-preview", {
        threshold,
        factor_weights: factorWeights,
        top_n: safeTopN,
        strategy_id: scorePreviewStrategyId || null,
      });
      setScorePreview(data?.state_snapshot || null);
      setFeedbackSuccess("Score Preview", "Score preview hazır");
      toast.success("Score preview hazır");
    } catch (error) {
      const message = error?.response?.data?.detail || "Score preview başarısız";
      setFeedbackError("Score Preview", message);
      toast.error(message);
    }
  };

  const applyScoreConfig = async () => {
    if (!isSuperAdmin) {
      toast.error("Score config apply sadece super_admin için açık");
      return;
    }
    if (String(scoreConfigReason || "").trim().length < 3) {
      toast.error("Score config reason en az 3 karakter olmalı");
      return;
    }

    const threshold = Number(scoreThreshold);
    const factorWeights = {
      base_score: Number(baseWeight),
      trend_strength: Number(trendWeight),
      relative_volume: Number(volumeWeight),
    };
    const perStrategy = safeJsonParse(strategyOverridesJson, null);
    if (!perStrategy) {
      toast.error("per_strategy JSON formatı geçersiz");
      return;
    }

    setFeedbackLoading("Score Config Apply", "Score config uygulanıyor");
    try {
      const { data } = await apiClient.put("/admin/strategy/score-config", {
        threshold,
        factor_weights: factorWeights,
        per_strategy: perStrategy,
        reason: scoreConfigReason.trim(),
      });
      syncScoreForm(data?.config || null);
      setScoreConfigReason("");
      setFeedbackSuccess("Score Config Apply", "Score config güncellendi");
      toast.success("Score config apply tamamlandı");
      await Promise.all([loadData(), loadAuditLog()]);
    } catch (error) {
      const message = error?.response?.data?.detail || "Score config apply başarısız";
      setFeedbackError("Score Config Apply", message);
      toast.error(message);
    }
  };

  const applyAutoTuningToggle = async () => {
    if (!isSuperAdmin) {
      toast.error("Auto tuning toggle sadece super_admin için açık");
      return;
    }
    if (String(autoTuningReason || "").trim().length < 3) {
      toast.error("Auto tuning reason en az 3 karakter olmalı");
      return;
    }
    setFeedbackLoading("Auto Tuning Toggle", "Auto tuning ayarı güncelleniyor");
    try {
      await apiClient.post("/admin/strategy/score-auto-tuning/toggle", {
        enabled: Boolean(autoTuningEnabled),
        reason: autoTuningReason.trim(),
      });
      setAutoTuningReason("");
      setFeedbackSuccess("Auto Tuning Toggle", `Auto tuning: ${autoTuningEnabled ? "ON" : "OFF"}`);
      toast.success("Auto tuning güncellendi");
      await Promise.all([loadData(), loadAuditLog()]);
    } catch (error) {
      const message = error?.response?.data?.detail || "Auto tuning güncellenemedi";
      setFeedbackError("Auto Tuning Toggle", message);
      toast.error(message);
    }
  };

  const applyScoreOverride = async () => {
    if (!isSuperAdmin) {
      toast.error("Score override sadece super_admin için açık");
      return false;
    }
    if (!String(scoreOverrideSignalId || "").trim()) {
      toast.error("Override için signal seçin");
      return false;
    }
    if (String(scoreOverrideReason || "").trim().length < 3) {
      toast.error("Override reason en az 3 karakter olmalı");
      return false;
    }
    setFeedbackLoading("Score Override", "Score override uygulanıyor");
    try {
      await apiClient.post("/admin/strategy/score-override", {
        signal_id: scoreOverrideSignalId,
        override_delta: Number(scoreOverrideDelta),
        reason: scoreOverrideReason.trim(),
      });
      setFeedbackSuccess("Score Override", "Score override başarıyla uygulandı");
      toast.success("Score override uygulandı");
      setScoreOverrideReason("");
      await Promise.all([loadData(), loadAuditLog()]);
      return true;
    } catch (error) {
      const message = error?.response?.data?.detail || "Score override başarısız";
      setFeedbackError("Score Override", message);
      toast.error(message);
      return false;
    }
  };

  const previewRiskLimits = async () => {
    setFeedbackLoading("Risk Limits Preview", "Risk limit değişiklikleri preview hesaplanıyor");
    try {
      const payload = {
        max_open_risk_pct: Number(riskLimitsDraft.max_open_risk_pct),
        max_daily_loss_pct: Number(riskLimitsDraft.max_daily_loss_pct),
        max_portfolio_drawdown_pct: Number(riskLimitsDraft.max_portfolio_drawdown_pct),
        max_strategy_drawdown_pct: Number(riskLimitsDraft.max_strategy_drawdown_pct),
        max_positions_per_strategy: Number(riskLimitsDraft.max_positions_per_strategy),
        max_sector_exposure_pct: Number(riskLimitsDraft.max_sector_exposure_pct),
        max_correlated_positions: Number(riskLimitsDraft.max_correlated_positions),
      };
      const { data } = await apiClient.post("/admin/strategy/risk-capital/limits/preview", payload);
      setRiskLimitsPreview(data || null);
      setRiskLimitsConfirmChecked(false);
      setFeedbackSuccess("Risk Limits Preview", `Preview hazır. token: ${data?.preview_token || "-"}`);
      toast.success("Risk limits preview hazır");
    } catch (error) {
      const message = error?.response?.data?.detail || "Risk limits preview başarısız";
      setFeedbackError("Risk Limits Preview", message);
      toast.error(message);
    }
  };

  const applyRiskLimits = async () => {
    if (!isSuperAdmin) {
      toast.error("Risk limits apply sadece super_admin için açık");
      return false;
    }
    if (!riskLimitsPreview?.preview_token) {
      toast.error("Önce risk limits preview alınmalı");
      return false;
    }
    if (!riskLimitsConfirmChecked) {
      toast.error("Risk limits apply için confirm zorunlu");
      return false;
    }
    if (riskLimitsReason.trim().length < 3) {
      toast.error("Risk limits reason en az 3 karakter olmalı");
      return false;
    }
    setFeedbackLoading("Risk Limits Apply", "Risk limits uygulanıyor");
    try {
      await apiClient.post("/admin/strategy/risk-capital/limits/apply", {
        preview_token: riskLimitsPreview.preview_token,
        confirm: true,
        reason: riskLimitsReason.trim(),
      });
      setFeedbackSuccess("Risk Limits Apply", "Risk limits başarıyla uygulandı");
      toast.success("Risk limits uygulandı");
      setRiskLimitsReason("");
      setRiskLimitsConfirmChecked(false);
      setRiskLimitsPreview(null);
      await Promise.all([loadData(), loadAuditLog(), loadActionImpactTimeline()]);
      return true;
    } catch (error) {
      const message = error?.response?.data?.detail || "Risk limits apply başarısız";
      setFeedbackError("Risk Limits Apply", message);
      toast.error(message);
      return false;
    }
  };

  const previewExposureOverride = async () => {
    if (!exposureOverrideStrategyId) {
      toast.error("Exposure override için strategy seçin");
      return;
    }
    setFeedbackLoading("Exposure Override Preview", "Exposure override preview hazırlanıyor");
    try {
      const { data } = await apiClient.post("/admin/strategy/risk-capital/exposure-override/preview", {
        strategy_id: exposureOverrideStrategyId,
        override_cap_pct: Number(exposureOverrideCapPct),
      });
      setExposureOverridePreview(data || null);
      setExposureOverrideConfirmChecked(false);
      setFeedbackSuccess("Exposure Override Preview", `Preview hazır. token: ${data?.preview_token || "-"}`);
      toast.success("Exposure override preview hazır");
    } catch (error) {
      const message = error?.response?.data?.detail || "Exposure override preview başarısız";
      setFeedbackError("Exposure Override Preview", message);
      toast.error(message);
    }
  };

  const applyExposureOverride = async () => {
    if (!isSuperAdmin) {
      toast.error("Exposure override apply sadece super_admin için açık");
      return false;
    }
    if (!exposureOverridePreview?.preview_token) {
      toast.error("Önce exposure override preview alınmalı");
      return false;
    }
    if (!exposureOverrideConfirmChecked) {
      toast.error("Exposure override apply için confirm zorunlu");
      return false;
    }
    if (exposureOverrideReason.trim().length < 3) {
      toast.error("Exposure override reason en az 3 karakter olmalı");
      return false;
    }
    setFeedbackLoading("Exposure Override Apply", "Exposure override uygulanıyor");
    try {
      await apiClient.post("/admin/strategy/risk-capital/exposure-override/apply", {
        preview_token: exposureOverridePreview.preview_token,
        confirm: true,
        reason: exposureOverrideReason.trim(),
      });
      setFeedbackSuccess("Exposure Override Apply", "Exposure override başarıyla uygulandı");
      toast.success("Exposure override uygulandı");
      setExposureOverrideReason("");
      setExposureOverrideConfirmChecked(false);
      setExposureOverridePreview(null);
      await Promise.all([loadData(), loadAuditLog(), loadActionImpactTimeline()]);
      return true;
    } catch (error) {
      const message = error?.response?.data?.detail || "Exposure override apply başarısız";
      setFeedbackError("Exposure Override Apply", message);
      toast.error(message);
      return false;
    }
  };

  const loadRiskAlertLink = async (alertId) => {
    if (!alertId) {
      return;
    }
    setRiskAlertLinkLoading(true);
    try {
      const { data } = await apiClient.get(`/admin/strategy/risk-capital/alerts/${alertId}/breach-link`);
      setRiskAlertLinkDetail(data || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Alert-breach link detayı alınamadı");
      setRiskAlertLinkDetail(null);
    } finally {
      setRiskAlertLinkLoading(false);
    }
  };

  const exportObservability = async (exportFormat) => {
    const params = {
      export_format: exportFormat,
      window: windowRange,
      strategy_id: exportStrategyId || null,
      top_n: 1200,
    };
    try {
      if (exportFormat === "json") {
        const { data } = await apiClient.get("/admin/strategy/observability/export", { params });
        setLastExportSnapshot({
          timestamp: data?.snapshot_timestamp || data?.filters?.snapshot_timestamp || null,
          row_count: data?.row_count ?? data?.count ?? 0,
          filters: data?.filters || params,
          export_type: "json",
        });
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json;charset=utf-8" });
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = `observability_${exportStrategyId || "all"}_${windowRange}.json`;
        document.body.append(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(link.href);
      } else {
        const response = await apiClient.get("/admin/strategy/observability/export", {
          params,
          responseType: "blob",
        });
        const contentDisposition = response.headers?.["content-disposition"] || "";
        const snapshotTimestamp = response.headers?.["x-snapshot-timestamp"] || null;
        const rowCount = Number(response.headers?.["x-row-count"] || 0);
        setLastExportSnapshot({
          timestamp: snapshotTimestamp,
          row_count: rowCount,
          filters: params,
          export_type: "csv",
        });
        const fileNameMatch = /filename="([^"]+)"/.exec(contentDisposition);
        const filename = fileNameMatch?.[1] || `observability_${exportStrategyId || "all"}_${windowRange}.csv`;
        const link = document.createElement("a");
        link.href = URL.createObjectURL(response.data);
        link.download = filename;
        document.body.append(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(link.href);
      }
      toast.success(`${exportFormat.toUpperCase()} export hazırlandı`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || `${exportFormat.toUpperCase()} export başarısız`);
    }
  };

  const applyRejectionFilters = () => {
    setAppliedRejectionFilters(rejectionFilterDraft);
  };

  const resetRejectionFilters = () => {
    setRejectionFilterDraft(EMPTY_REJECTION_FILTERS);
    setAppliedRejectionFilters(EMPTY_REJECTION_FILTERS);
  };

  const applyRejectionCardFilter = (reasonToken) => {
    const next = {
      ...rejectionFilterDraft,
      reason: reasonToken,
    };
    setRejectionFilterDraft(next);
    setAppliedRejectionFilters(next);
  };

  const feedbackClass =
    actionFeedback.state === "error"
      ? "border-red-700 bg-red-100"
      : actionFeedback.state === "success"
        ? "border-emerald-700 bg-emerald-100"
        : "border-amber-700 bg-amber-100";

  return (
    <section className="space-y-4" data-testid="admin-strategy-observability-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="admin-strategy-observability-header">
        <div className="flex flex-wrap items-center gap-2" data-testid="admin-strategy-observability-role-row">
          <h2 className="text-4xl font-black uppercase tracking-tight text-black" data-testid="admin-strategy-observability-title">
            Signal Control + Explainability
          </h2>
          <Badge className="border border-black bg-black text-orange-300" data-testid="admin-strategy-observability-role-badge">
            role: {role || "unknown"}
          </Badge>
          <Badge className="border border-black bg-white text-black" data-testid="admin-strategy-observability-permission-badge">
            {isSuperAdmin ? "super_admin: execute/apply/override" : "admin: view/simulate"}
          </Badge>
        </div>
        <p className="mt-2 text-sm text-black/80" data-testid="admin-strategy-observability-description">
          Simulation-before-execution, reason zorunluluğu ve audit görünürlüğü aktif.
        </p>
      </header>

      <div className="grid gap-2 border border-black/30 bg-orange-100 p-4 md:grid-cols-4" data-testid="admin-strategy-observability-controls">
        <select
          className="border border-black/40 bg-white px-3 py-2 text-sm"
          value={windowRange}
          onChange={(event) => setWindowRange(event.target.value)}
          data-testid="strategy-observability-window-select"
        >
          {windowOptions.map((windowValue) => (
            <option key={windowValue} value={windowValue} data-testid={`strategy-observability-window-option-${windowValue}`}>
              {windowValue}
            </option>
          ))}
        </select>

        <Input
          type="number"
          min={1}
          max={50}
          value={topN}
          onChange={(event) => setTopN(Math.min(Math.max(Number(event.target.value) || 10, 1), 50))}
          data-testid="strategy-observability-topn-input"
        />

        <Button
          className="border border-black bg-black text-orange-300 hover:bg-zinc-800"
          onClick={loadData}
          data-testid="strategy-observability-refresh-button"
        >
          Yenile
        </Button>

        <p className="self-center text-sm text-black" data-testid="strategy-observability-loading-text">
          loading: {String(loading)}
        </p>
      </div>

      <div className="grid gap-2 border border-black/30 bg-orange-100 p-4 md:grid-cols-6" data-testid="strategy-observability-p1-controls-panel">
        <div className="flex items-center gap-2" data-testid="strategy-observability-auto-refresh-row">
          <Switch
            checked={autoRefreshEnabled}
            onCheckedChange={(checked) => setAutoRefreshEnabled(Boolean(checked))}
            data-testid="strategy-observability-auto-refresh-switch"
          />
          <span className="text-xs">Auto Refresh</span>
        </div>
        <Input
          type="number"
          min={10}
          max={180}
          value={autoRefreshSeconds}
          onChange={(event) => setAutoRefreshSeconds(Math.min(Math.max(Number(event.target.value) || 30, 10), 180))}
          data-testid="strategy-observability-auto-refresh-seconds-input"
        />
        <Input
          value={exportStrategyId}
          onChange={(event) => setExportStrategyId(event.target.value)}
          placeholder="export strategy_id (opsiyonel)"
          data-testid="strategy-observability-export-strategy-input"
        />
        <Button
          variant="outline"
          className="border-black bg-white text-black"
          onClick={() => exportObservability("csv")}
          data-testid="strategy-observability-export-csv-button"
        >
          CSV Export
        </Button>
        <Button
          variant="outline"
          className="border-black bg-white text-black"
          onClick={() => exportObservability("json")}
          data-testid="strategy-observability-export-json-button"
        >
          JSON Export
        </Button>
        <Button
          className="border border-black bg-black text-orange-300 hover:bg-zinc-800"
          onClick={() => {
            const targetStrategy = exportStrategyId || report?.active_spot_strategies?.[0];
            if (!targetStrategy) {
              toast.error("Detay sayfası için strategy seçin");
              return;
            }
            navigate(`/admin/strategy/observability/${targetStrategy}`);
          }}
          data-testid="strategy-observability-open-detail-page-button"
        >
          Report Detail Aç
        </Button>
      </div>

      {lastExportSnapshot && (
        <div className="border border-black/30 bg-orange-100 p-3 text-xs" data-testid="strategy-observability-last-export-snapshot-panel">
          <p data-testid="strategy-observability-last-export-snapshot-title" className="font-semibold">Export snapshot at: {lastExportSnapshot.timestamp || "-"}</p>
          <p data-testid="strategy-observability-last-export-row-count">row_count: {lastExportSnapshot.row_count ?? 0}</p>
          <p data-testid="strategy-observability-last-export-filters">filters: {JSON.stringify(lastExportSnapshot.filters || {})}</p>
          <p data-testid="strategy-observability-last-export-type">export_type: {lastExportSnapshot.export_type || "-"}</p>
        </div>
      )}

      {actionFeedback.state !== "idle" && (
        <div className={`border p-3 text-sm ${feedbackClass}`} data-testid="strategy-observability-action-feedback-banner">
          <p className="font-semibold" data-testid="strategy-observability-action-feedback-title">{actionFeedback.title}</p>
          <p data-testid="strategy-observability-action-feedback-message">{actionFeedback.message}</p>
          <p className="text-xs" data-testid="strategy-observability-action-feedback-timestamp">
            {actionFeedback.at ? new Date(actionFeedback.at).toLocaleString() : "-"}
          </p>
        </div>
      )}

      <section className="border border-black/30 bg-orange-100" data-testid="top-signals-control-layer-panel">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-black/20 px-4 py-3" data-testid="top-signals-header-row">
          <div>
            <h3 className="text-lg font-bold" data-testid="top-signals-title">Top Signals Control Layer</h3>
            <p className="text-xs text-black/70" data-testid="top-signals-subtitle">
              count: {topSignals.length} · seçili: {selectedSignalIds.length}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2" data-testid="top-signals-controls-buttons-row">
            <Button
              variant="outline"
              className="border-black bg-white text-black"
              onClick={simulateSelectedSignals}
              disabled={!canSimulate || normalizedSelectedSignalIds.length === 0}
              data-testid="top-signals-simulate-selected-button"
            >
              Seçiliyi Simüle Et
            </Button>
            <Button
              className="border border-black bg-black text-orange-300 hover:bg-zinc-800"
              onClick={() => setExecuteDialogOpen(true)}
              disabled={!canExecuteSelectedSignals}
              title={
                !isSuperAdmin
                  ? "Sadece super_admin execute edebilir"
                  : normalizedSelectedSignalIds.length === 0
                    ? "Önce sinyal seçin"
                    : !selectedMatchSimulation
                      ? "Önce aynı sinyal seti için simulate yapın"
                      : !selectedSignalsApproved
                        ? "Execute için tüm seçili sinyaller approved olmalı"
                        : ""
              }
              data-testid="top-signals-execute-selected-button"
            >
              Seçiliyi Execute Et
            </Button>
            <Button
              variant="outline"
              className="border-black bg-white text-black"
              onClick={runBulkSimulation}
              disabled={!canSimulate}
              data-testid="top-signals-bulk-simulate-button"
            >
              Bulk Simulate Top N
            </Button>
            <Button
              variant="outline"
              className="border-black bg-white text-black"
              onClick={runBulkExecutePreview}
              disabled={!isSuperAdmin}
              data-testid="top-signals-bulk-execute-preview-button"
            >
              Bulk Execute Preview
            </Button>
          </div>
        </div>

        <div className="overflow-x-auto" data-testid="top-signals-table-scroll-area">
          <Table data-testid="top-signals-table">
            <TableHeader>
              <TableRow>
                <TableHead data-testid="top-signals-head-checkbox">
                  <Checkbox
                    checked={allSignalsSelected}
                    onCheckedChange={(checked) => toggleSelectAllSignals(Boolean(checked))}
                    data-testid="top-signals-select-all-checkbox"
                    aria-label="Tüm sinyalleri seç"
                  />
                </TableHead>
                <TableHead data-testid="top-signals-head-rank">Rank</TableHead>
                <TableHead data-testid="top-signals-head-symbol">Symbol</TableHead>
                <TableHead data-testid="top-signals-head-strategy">Strategy</TableHead>
                <TableHead data-testid="top-signals-head-regime">Regime</TableHead>
                <TableHead data-testid="top-signals-head-adjusted">Adjusted Score</TableHead>
                <TableHead data-testid="top-signals-head-base">Base Score</TableHead>
                <TableHead data-testid="top-signals-head-delta">Delta</TableHead>
                <TableHead data-testid="top-signals-head-time">Timestamp</TableHead>
                <TableHead data-testid="top-signals-head-actions">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {topSignals.map((item) => {
                const signalId = String(item.signal_id || "");
                const rowSelected = selectedSignalIds.includes(signalId);
                const rowSimulated = normalizedSelectedSimulationIds.includes(signalId);
                return (
                  <TableRow key={signalId} data-testid={`top-signals-row-${signalId}`}>
                    <TableCell data-testid={`top-signals-select-cell-${signalId}`}>
                      <Checkbox
                        checked={rowSelected}
                        onCheckedChange={(checked) => updateSelectedSignal(signalId, Boolean(checked))}
                        data-testid={`top-signals-select-checkbox-${signalId}`}
                        aria-label={`${signalId} sinyalini seç`}
                      />
                    </TableCell>
                    <TableCell data-testid={`top-signals-rank-${signalId}`}>{item.selection_rank ?? "-"}</TableCell>
                    <TableCell data-testid={`top-signals-symbol-${signalId}`}>{item.symbol}</TableCell>
                    <TableCell data-testid={`top-signals-strategy-${signalId}`}>{item.strategy_id}</TableCell>
                    <TableCell data-testid={`top-signals-regime-${signalId}`}>{item.market_regime}</TableCell>
                    <TableCell data-testid={`top-signals-adjusted-${signalId}`}>{item.adjusted_score}</TableCell>
                    <TableCell data-testid={`top-signals-base-${signalId}`}>{item.base_score}</TableCell>
                    <TableCell data-testid={`top-signals-delta-${signalId}`}>{item.score_delta}</TableCell>
                    <TableCell className="text-xs" data-testid={`top-signals-time-${signalId}`}>
                      {item.timestamp ? new Date(item.timestamp).toLocaleString() : "-"}
                    </TableCell>
                    <TableCell data-testid={`top-signals-actions-${signalId}`}>
                      <div className="flex flex-wrap items-center gap-2" data-testid={`top-signals-row-actions-group-${signalId}`}>
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-8 border-black bg-white text-black"
                          onClick={() => openExplainability(signalId)}
                          data-testid={`top-signals-explain-button-${signalId}`}
                        >
                          Explain
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-8 border-black bg-white text-black"
                          onClick={() => navigate(`/admin/strategy/observability/${item.strategy_id}`)}
                          data-testid={`top-signals-detail-button-${signalId}`}
                        >
                          Detail
                        </Button>
                        <Badge
                          className={
                            item.governance_status === "approved"
                              ? "border-emerald-700 bg-emerald-100 text-emerald-900"
                              : item.governance_status === "rejected"
                                ? "border-red-700 bg-red-100 text-red-900"
                                : item.governance_status === "executed"
                                  ? "border-blue-700 bg-blue-100 text-blue-900"
                                  : "border-slate-600 bg-slate-100 text-slate-800"
                          }
                          data-testid={`top-signals-governance-status-badge-${signalId}`}
                        >
                          {item.governance_status || "pending"}
                        </Badge>
                        <Input
                          value={governanceReasons[signalId] || ""}
                          onChange={(event) =>
                            setGovernanceReasons((prev) => ({
                              ...prev,
                              [signalId]: event.target.value,
                            }))
                          }
                          placeholder="reject reason"
                          className="h-8 w-48"
                          data-testid={`top-signals-governance-reason-input-${signalId}`}
                        />
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-8 border-black bg-white text-black"
                          onClick={() => approveSignal(signalId)}
                          disabled={!isSuperAdmin || governanceActionLoading[signalId]}
                          title={!isSuperAdmin ? "Sadece super_admin approve edebilir" : ""}
                          data-testid={`top-signals-approve-button-${signalId}`}
                        >
                          Approve
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-8 border-black bg-white text-black"
                          onClick={() => rejectSignal(signalId)}
                          disabled={!isSuperAdmin || governanceActionLoading[signalId] || String(governanceReasons[signalId] || "").trim().length < 3}
                          title={!isSuperAdmin ? "Sadece super_admin reject edebilir" : "Reject için reason en az 3 karakter"}
                          data-testid={`top-signals-reject-button-${signalId}`}
                        >
                          Reject
                        </Button>
                        <Badge
                          className={rowSimulated ? "border-emerald-700 bg-emerald-100 text-emerald-900" : "border-slate-600 bg-slate-100 text-slate-800"}
                          data-testid={`top-signals-simulation-status-badge-${signalId}`}
                        >
                          {rowSimulated ? "simulated" : "not_simulated"}
                        </Badge>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}

              {!loading && topSignals.length === 0 && (
                <TableRow data-testid="top-signals-empty-row">
                  <TableCell colSpan={10} className="text-center text-sm text-black/70" data-testid="top-signals-empty-text">
                    Bu zaman penceresinde executable signal yok.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>

        <div className="grid gap-3 border-t border-black/20 p-4 lg:grid-cols-2" data-testid="top-signals-preview-panels-grid">
          <div className="border border-black/25 bg-white p-3" data-testid="selected-simulation-preview-panel">
            <p className="text-sm font-semibold" data-testid="selected-simulation-preview-title">Seçili Simülasyon Sonucu</p>
            <p className="text-xs" data-testid="selected-simulation-preview-token">preview_token: {selectedSimulation.previewToken || "-"}</p>
            <p className="text-xs" data-testid="selected-simulation-preview-count">item_count: {selectedSimulation.items.length}</p>
          </div>
          <div className="border border-black/25 bg-white p-3" data-testid="bulk-simulation-preview-panel">
            <p className="text-sm font-semibold" data-testid="bulk-simulation-preview-title">Bulk Simülasyon Sonucu</p>
            <p className="text-xs" data-testid="bulk-simulation-preview-token">preview_token: {bulkSimulation.previewToken || "-"}</p>
            <p className="text-xs" data-testid="bulk-simulation-preview-count">item_count: {bulkSimulation.items.length}</p>
          </div>
        </div>

        <div className="border-t border-black/20 bg-white p-4" data-testid="bulk-execute-confirm-panel">
          <h4 className="font-semibold" data-testid="bulk-execute-confirm-title">Bulk Execute Confirm</h4>
          <p className="mt-1 text-xs text-black/70" data-testid="bulk-execute-confirm-description">
            Zorunlu: preview + confirm + reason.
          </p>
          <p className="mt-1 text-xs" data-testid="bulk-execute-preview-token">preview_token: {bulkExecutePreview.previewToken || "-"}</p>
          <p className="text-xs" data-testid="bulk-execute-preview-count">preview_items: {bulkExecutePreview.items.length}</p>
          <Textarea
            value={bulkExecuteReason}
            onChange={(event) => setBulkExecuteReason(event.target.value)}
            placeholder="Bulk execute reason"
            className="mt-2 border-black/40 bg-orange-50"
            data-testid="bulk-execute-reason-textarea"
          />
          <div className="mt-2 flex items-center gap-2" data-testid="bulk-execute-confirm-checkbox-row">
            <Checkbox
              checked={bulkExecuteConfirmChecked}
              onCheckedChange={(checked) => setBulkExecuteConfirmChecked(Boolean(checked))}
              data-testid="bulk-execute-confirm-checkbox"
            />
            <p className="text-xs" data-testid="bulk-execute-confirm-checkbox-label">
              Preview içeriğini kontrol ettim, bulk execute için onaylıyorum.
            </p>
          </div>
          <div className="mt-3">
            <Button
              className="border border-black bg-black text-orange-300 hover:bg-zinc-800"
              onClick={runBulkExecuteConfirm}
              disabled={!isSuperAdmin || !bulkExecutePreview.previewToken || !bulkExecuteConfirmChecked || bulkExecuteReason.trim().length < 3}
              data-testid="bulk-execute-confirm-button"
            >
              Bulk Execute Confirm
            </Button>
          </div>
        </div>
      </section>

      <section className="grid gap-3 lg:grid-cols-2" data-testid="strategy-observability-reporting-grid">
        <div className="border border-black/25 bg-orange-100 p-4" data-testid="score-metrics-panel">
          <h3 className="text-lg font-bold" data-testid="score-metrics-title">Score Metrics Snapshot</h3>
          <div className="mt-3 grid gap-2 text-sm" data-testid="score-metrics-values">
            <p data-testid="score-metrics-avg-base">avg_base_score: {scoreMetrics?.avg_base_score ?? 0}</p>
            <p data-testid="score-metrics-avg-adjusted">avg_adjusted_score: {scoreMetrics?.avg_adjusted_score ?? 0}</p>
            <p data-testid="score-metrics-avg-delta">avg_score_delta: {scoreMetrics?.avg_score_delta ?? 0}</p>
            <p data-testid="score-metrics-signals-per-strategy">
              signals_per_strategy: {JSON.stringify(scoreMetrics?.signals_per_strategy || {})}
            </p>
            <p data-testid="score-metrics-selected-per-strategy">
              selected_signals_per_strategy: {JSON.stringify(scoreMetrics?.selected_signals_per_strategy || {})}
            </p>
          </div>
          <div className="mt-4 space-y-2" data-testid="regime-distribution-bars">
            {regimeRows.map(([regime, count]) => {
              const maxCount = Math.max(...regimeRows.map((item) => item[1]), 1);
              const widthPct = Math.max((count / maxCount) * 100, 5);
              return (
                <div key={regime} className="space-y-1" data-testid={`regime-bar-row-${regime}`}>
                  <p className="text-xs font-semibold" data-testid={`regime-bar-label-${regime}`}>{regime}: {count}</p>
                  <div className="h-3 w-full border border-black/40 bg-white" data-testid={`regime-bar-container-${regime}`}>
                    <div className="h-full bg-black" style={{ width: `${widthPct}%` }} data-testid={`regime-bar-fill-${regime}`} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="border border-black/25 bg-orange-100 p-4" data-testid="strategy-report-panel">
          <h3 className="text-lg font-bold" data-testid="strategy-report-title">Strategy Observability Report</h3>
          <div className="mt-3 grid gap-2 text-sm" data-testid="strategy-report-values">
            <p data-testid="strategy-report-active-strategies">active_spot_strategies: {(report?.active_spot_strategies || []).join(", ") || "-"}</p>
            <p data-testid="strategy-report-signals-total">signals_total: {report?.signals_total ?? 0}</p>
            <p data-testid="strategy-report-signals-selected">signals_selected: {report?.signals_selected ?? 0}</p>
            <p data-testid="strategy-report-avg-adjusted">avg_adjusted_score: {report?.avg_adjusted_score ?? 0}</p>
            <p data-testid="strategy-report-avg-base">avg_base_score: {report?.avg_base_score ?? 0}</p>
            <p data-testid="strategy-report-score-delta">score_delta_avg: {report?.score_delta_avg ?? 0}</p>
            <p data-testid="strategy-report-profit-factor-by-strategy">
              strategy_profit_factor: {JSON.stringify(report?.strategy_profit_factor || {})}
            </p>
            <p data-testid="strategy-report-drawdown-by-strategy">
              strategy_drawdown: {JSON.stringify(report?.strategy_drawdown || {})}
            </p>
          </div>
          <div className="mt-3 flex flex-wrap gap-2" data-testid="strategy-report-strategy-actions-row">
            {(report?.active_spot_strategies || []).map((strategyCode) => (
              <Button
                key={strategyCode}
                size="sm"
                variant="outline"
                className="h-8 border-black bg-white text-black"
                onClick={() => {
                  setExportStrategyId(strategyCode);
                  navigate(`/admin/strategy/observability/${strategyCode}`);
                }}
                data-testid={`strategy-report-open-detail-button-${strategyCode}`}
              >
                {strategyCode} Detail
              </Button>
            ))}
          </div>
        </div>
      </section>

      <section className="border border-black/30 bg-orange-100 p-4" data-testid="score-tuning-control-layer-panel">
        <h3 className="text-lg font-bold" data-testid="score-tuning-control-layer-title">Score Tuning Control</h3>
        <p className="mt-1 text-xs text-black/70" data-testid="score-tuning-control-layer-description">
          Apply/override için reason zorunlu. Apply yetkisi sadece super_admin.
        </p>

        <div className="mt-3 grid gap-3 lg:grid-cols-2" data-testid="score-tuning-main-grid">
          <div className="space-y-3 border border-black/25 bg-white p-3" data-testid="score-config-edit-panel">
            <h4 className="font-semibold" data-testid="score-config-edit-title">Threshold + Factor Weights</h4>
            <Input
              type="number"
              step="0.01"
              min={0}
              max={1}
              value={scoreThreshold}
              onChange={(event) => setScoreThreshold(event.target.value)}
              data-testid="score-config-threshold-input"
            />
            <Input
              type="number"
              step="0.01"
              value={baseWeight}
              onChange={(event) => setBaseWeight(event.target.value)}
              data-testid="score-config-base-weight-input"
            />
            <Input
              type="number"
              step="0.01"
              value={trendWeight}
              onChange={(event) => setTrendWeight(event.target.value)}
              data-testid="score-config-trend-weight-input"
            />
            <Input
              type="number"
              step="0.01"
              value={volumeWeight}
              onChange={(event) => setVolumeWeight(event.target.value)}
              data-testid="score-config-volume-weight-input"
            />

            <Textarea
              value={strategyOverridesJson}
              onChange={(event) => setStrategyOverridesJson(event.target.value)}
              placeholder="per_strategy JSON"
              className="min-h-[120px] border-black/40 bg-orange-50"
              data-testid="score-config-per-strategy-json-textarea"
            />

            <Input
              value={scoreConfigReason}
              onChange={(event) => setScoreConfigReason(event.target.value)}
              placeholder="apply reason"
              data-testid="score-config-apply-reason-input"
            />

            <div className="flex flex-wrap gap-2" data-testid="score-config-action-buttons-row">
              <Button
                variant="outline"
                className="border-black bg-white text-black"
                onClick={runScorePreview}
                data-testid="score-config-preview-button"
              >
                Preview
              </Button>
              <Button
                className="border border-black bg-black text-orange-300 hover:bg-zinc-800"
                onClick={applyScoreConfig}
                disabled={!isSuperAdmin || scoreConfigReason.trim().length < 3}
                data-testid="score-config-apply-button"
              >
                Apply Config
              </Button>
            </div>
          </div>

          <div className="space-y-3 border border-black/25 bg-white p-3" data-testid="score-tuning-override-panel">
            <h4 className="font-semibold" data-testid="score-override-title">Manual Score Override</h4>

            <select
              className="h-10 w-full border border-black/40 px-3 text-sm"
              value={scoreOverrideSignalId}
              onChange={(event) => setScoreOverrideSignalId(event.target.value)}
              data-testid="score-override-signal-select"
            >
              <option value="" data-testid="score-override-signal-option-empty">signal seçin</option>
              {topSignals.map((item) => (
                <option key={item.signal_id} value={item.signal_id} data-testid={`score-override-signal-option-${item.signal_id}`}>
                  {item.symbol} · {item.strategy_id}
                </option>
              ))}
            </select>

            <Input
              type="number"
              min={-1}
              max={1}
              step="0.01"
              value={scoreOverrideDelta}
              onChange={(event) => setScoreOverrideDelta(event.target.value)}
              data-testid="score-override-delta-input"
            />

            <Input
              value={scoreOverrideReason}
              onChange={(event) => setScoreOverrideReason(event.target.value)}
              placeholder="override reason"
              data-testid="score-override-reason-input"
            />

            <Button
              className="border border-black bg-black text-orange-300 hover:bg-zinc-800"
              onClick={() => setScoreOverrideDialogOpen(true)}
              disabled={!isSuperAdmin || scoreOverrideReason.trim().length < 3 || !scoreOverrideSignalId}
              title={
                !isSuperAdmin
                  ? "Sadece super_admin override uygulayabilir"
                  : !scoreOverrideSignalId
                    ? "Önce signal seçin"
                    : scoreOverrideReason.trim().length < 3
                      ? "Reason en az 3 karakter olmalı"
                      : ""
              }
              data-testid="score-override-apply-button"
            >
              Apply Override
            </Button>

            <div className="space-y-2 border border-black/25 bg-orange-50 p-3" data-testid="score-auto-tuning-panel">
              <div className="flex items-center justify-between" data-testid="score-auto-tuning-switch-row">
                <p className="text-sm font-semibold" data-testid="score-auto-tuning-label">Auto Tuning</p>
                <Switch
                  checked={autoTuningEnabled}
                  onCheckedChange={(checked) => setAutoTuningEnabled(Boolean(checked))}
                  data-testid="score-auto-tuning-switch"
                />
              </div>
              <Input
                value={autoTuningReason}
                onChange={(event) => setAutoTuningReason(event.target.value)}
                placeholder="auto tuning reason"
                data-testid="score-auto-tuning-reason-input"
              />
              <Button
                variant="outline"
                className="border-black bg-white text-black"
                onClick={applyAutoTuningToggle}
                disabled={!isSuperAdmin || autoTuningReason.trim().length < 3}
                data-testid="score-auto-tuning-apply-button"
              >
                Auto Tuning Apply
              </Button>
              <p className="text-xs" data-testid="score-auto-tuning-current-state">current: {String(scoreConfig?.auto_tuning_enabled ?? false)}</p>
            </div>
          </div>
        </div>

        <div className="mt-3 border border-black/25 bg-white p-3" data-testid="score-preview-results-panel">
          <div className="mb-2 flex flex-wrap items-center gap-2" data-testid="score-preview-filter-row">
            <Input
              value={scorePreviewStrategyId}
              onChange={(event) => setScorePreviewStrategyId(event.target.value)}
              placeholder="preview strategy_id (opsiyonel)"
              className="max-w-xs"
              data-testid="score-preview-strategy-id-input"
            />
          </div>
          <p className="text-sm" data-testid="score-preview-before-selected">before_selected: {scorePreview?.before_selected ?? 0}</p>
          <p className="text-sm" data-testid="score-preview-after-selected">after_selected: {scorePreview?.after_selected ?? 0}</p>
          <p className="text-sm" data-testid="score-preview-selected-delta">selected_delta: {scorePreview?.selected_delta ?? 0}</p>
          <p className="text-xs" data-testid="score-preview-impact-count">impact_rows: {(scorePreview?.impact_rows || []).length}</p>
        </div>
      </section>

      <section className="border border-black/30 bg-orange-100 p-4" data-testid="rejection-analytics-drilldown-panel">
        <h3 className="text-lg font-bold" data-testid="rejection-analytics-title">Rejection Analytics Drill-down</h3>
        <div className="mt-3 grid gap-3 md:grid-cols-2 lg:grid-cols-4" data-testid="strategy-observability-rejection-cards-grid">
          <button
            type="button"
            className="border border-black/25 bg-white p-3 text-left"
            onClick={() => applyRejectionCardFilter("trend_strength_weak")}
            data-testid="rejection-trend-card-button"
          >
            <p className="text-xs uppercase">Rejected by Trend</p>
            <p className="text-2xl font-bold" data-testid="rejection-trend-value">{rejection?.signals_rejected_trend_strength ?? 0}</p>
          </button>
          <button
            type="button"
            className="border border-black/25 bg-white p-3 text-left"
            onClick={() => applyRejectionCardFilter("hostile")}
            data-testid="rejection-bias-card-button"
          >
            <p className="text-xs uppercase">Rejected by Market Bias</p>
            <p className="text-2xl font-bold" data-testid="rejection-bias-value">
              {rejection?.signals_rejected_market_bias ?? rejection?.signals_rejected_btc_regime ?? 0}
            </p>
          </button>
          <button
            type="button"
            className="border border-black/25 bg-white p-3 text-left"
            onClick={() => applyRejectionCardFilter("guard_active")}
            data-testid="rejection-stress-card-button"
          >
            <p className="text-xs uppercase">Rejected by Market Stress</p>
            <p className="text-2xl font-bold" data-testid="rejection-stress-value">
              {rejection?.signals_rejected_market_stress ?? rejection?.signals_rejected_freeze_guard ?? 0}
            </p>
          </button>
          <button
            type="button"
            className="border border-black/25 bg-white p-3 text-left"
            onClick={() => applyRejectionCardFilter("adjusted_score_below_threshold")}
            data-testid="rejection-threshold-card-button"
          >
            <p className="text-xs uppercase">Rejected by Threshold</p>
            <p className="text-2xl font-bold" data-testid="rejection-threshold-value">{rejection?.signals_rejected_threshold ?? 0}</p>
          </button>
        </div>

        <div className="mt-3 grid gap-2 border border-black/25 bg-white p-3 md:grid-cols-4" data-testid="rejection-filter-grid">
          <Input
            value={rejectionFilterDraft.strategy_id}
            onChange={(event) => setRejectionFilterDraft((prev) => ({ ...prev, strategy_id: event.target.value }))}
            placeholder="strategy_id"
            data-testid="rejection-filter-strategy-input"
          />
          <Input
            value={rejectionFilterDraft.symbol}
            onChange={(event) => setRejectionFilterDraft((prev) => ({ ...prev, symbol: event.target.value.toUpperCase() }))}
            placeholder="symbol"
            data-testid="rejection-filter-symbol-input"
          />
          <Input
            value={rejectionFilterDraft.reason}
            onChange={(event) => setRejectionFilterDraft((prev) => ({ ...prev, reason: event.target.value }))}
            placeholder="reason token"
            data-testid="rejection-filter-reason-input"
          />
          <div className="flex gap-2" data-testid="rejection-filter-buttons-row">
            <Button
              variant="outline"
              className="border-black bg-white text-black"
              onClick={applyRejectionFilters}
              data-testid="rejection-filter-apply-button"
            >
              Filtreyi Uygula
            </Button>
            <Button
              variant="outline"
              className="border-black bg-white text-black"
              onClick={resetRejectionFilters}
              data-testid="rejection-filter-reset-button"
            >
              Sıfırla
            </Button>
          </div>
        </div>

        <div className="mt-2 flex flex-wrap gap-2" data-testid="rejection-reasons-chip-row">
          {rejectionReasons.map((item, index) => (
            <button
              type="button"
              key={`${item.reason}-${index}`}
              className="rounded border border-black/30 bg-white px-2 py-1 text-xs"
              onClick={() => {
                const next = {
                  ...rejectionFilterDraft,
                  reason: item.reason,
                };
                setRejectionFilterDraft(next);
                setAppliedRejectionFilters(next);
              }}
              data-testid={`rejection-reason-chip-${index}`}
            >
              {item.reason} ({item.count})
            </button>
          ))}
        </div>

        <div className="mt-3 overflow-x-auto border border-black/25 bg-white" data-testid="rejection-details-table-wrapper">
          <Table data-testid="rejection-details-table">
            <TableHeader>
              <TableRow>
                <TableHead data-testid="rejection-details-head-symbol">Symbol</TableHead>
                <TableHead data-testid="rejection-details-head-strategy">Strategy</TableHead>
                <TableHead data-testid="rejection-details-head-reason">Reason</TableHead>
                <TableHead data-testid="rejection-details-head-time">Time</TableHead>
                <TableHead data-testid="rejection-details-head-actions">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rejectionDetails.map((item) => {
                const signalId = String(item.signal_id || "");
                return (
                  <TableRow key={`${signalId}-${item.created_at || ""}`} data-testid={`rejection-detail-row-${signalId}`}>
                    <TableCell data-testid={`rejection-detail-symbol-${signalId}`}>{item.symbol || "-"}</TableCell>
                    <TableCell data-testid={`rejection-detail-strategy-${signalId}`}>{item.strategy_id || "-"}</TableCell>
                    <TableCell data-testid={`rejection-detail-reason-${signalId}`}>{item.rejection_reason || "-"}</TableCell>
                    <TableCell className="text-xs" data-testid={`rejection-detail-time-${signalId}`}>
                      {item.created_at ? new Date(item.created_at).toLocaleString() : "-"}
                    </TableCell>
                    <TableCell data-testid={`rejection-detail-actions-${signalId}`}>
                      <div className="flex flex-wrap gap-2" data-testid={`rejection-detail-actions-group-${signalId}`}>
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-8 border-black bg-white text-black"
                          onClick={() => openExplainability(signalId)}
                          data-testid={`rejection-detail-explain-button-${signalId}`}
                        >
                          Explain
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-8 border-black bg-white text-black"
                          disabled={!canSimulate}
                          onClick={async () => {
                            setSelectedSignalIds([signalId]);
                            setFeedbackLoading("Rejection Simulate", "Seçili reject sinyali simüle ediliyor");
                            try {
                              const { data } = await apiClient.post("/admin/strategy/top-signals/simulate", {
                                signal_ids: [signalId],
                              });
                              setSelectedSimulation({
                                previewToken: data?.preview_token || "",
                                signalIds: [signalId],
                                items: data?.items || [],
                              });
                              setFeedbackSuccess("Rejection Simulate", `preview_token: ${data?.preview_token || "-"}`);
                              toast.success("Reject sinyali simüle edildi");
                            } catch (error) {
                              const message = error?.response?.data?.detail || "Rejection simulate başarısız";
                              setFeedbackError("Rejection Simulate", message);
                              toast.error(message);
                            }
                          }}
                          data-testid={`rejection-detail-simulate-button-${signalId}`}
                        >
                          Simulate
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
              {!rejectionDetailsLoading && rejectionDetails.length === 0 && (
                <TableRow data-testid="rejection-detail-empty-row">
                  <TableCell colSpan={5} className="text-center text-sm text-black/70" data-testid="rejection-detail-empty-text">
                    Filtreye uygun reject sinyali bulunamadı.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </section>

      <section className="border border-black/25 bg-orange-100 p-4" data-testid="risk-capital-status-panel">
        <h3 className="text-lg font-bold" data-testid="risk-capital-status-title">Risk & Capital Status Control Layer</h3>
        <p className="mt-1 text-xs text-black/70" data-testid="risk-capital-status-description">
          Risk limit değişikliği için preview zorunlu. Exposure override için reason + preview + confirm zorunlu.
        </p>

        <div className="mt-3 grid gap-2 text-sm md:grid-cols-2" data-testid="risk-capital-status-grid">
          <p data-testid="risk-capital-equity">equity: {riskCapital?.equity ?? 0}</p>
          <p data-testid="risk-capital-open-risk">open_risk_pct: {riskCapital?.open_risk_pct ?? 0}</p>
          <p data-testid="risk-capital-daily-loss">daily_loss: {riskCapital?.daily_loss?.daily_loss_amount ?? 0}</p>
          <p data-testid="risk-capital-portfolio-drawdown">portfolio_drawdown_pct: {riskCapital?.portfolio_drawdown_pct ?? 0}</p>
        </div>

        <div className="mt-3 grid gap-3 lg:grid-cols-2" data-testid="risk-capital-control-grid">
          <div className="space-y-2 border border-black/25 bg-white p-3" data-testid="risk-limits-edit-panel">
            <p className="font-semibold" data-testid="risk-limits-edit-title">Risk Limits Edit</p>
            <Input value={riskLimitsDraft.max_open_risk_pct} onChange={(event) => setRiskLimitsDraft((prev) => ({ ...prev, max_open_risk_pct: event.target.value }))} placeholder="max_open_risk_pct" data-testid="risk-limits-max-open-risk-input" />
            <Input value={riskLimitsDraft.max_daily_loss_pct} onChange={(event) => setRiskLimitsDraft((prev) => ({ ...prev, max_daily_loss_pct: event.target.value }))} placeholder="max_daily_loss_pct" data-testid="risk-limits-max-daily-loss-input" />
            <Input value={riskLimitsDraft.max_portfolio_drawdown_pct} onChange={(event) => setRiskLimitsDraft((prev) => ({ ...prev, max_portfolio_drawdown_pct: event.target.value }))} placeholder="max_portfolio_drawdown_pct" data-testid="risk-limits-max-portfolio-drawdown-input" />
            <Input value={riskLimitsDraft.max_strategy_drawdown_pct} onChange={(event) => setRiskLimitsDraft((prev) => ({ ...prev, max_strategy_drawdown_pct: event.target.value }))} placeholder="max_strategy_drawdown_pct" data-testid="risk-limits-max-strategy-drawdown-input" />
            <Input value={riskLimitsDraft.max_positions_per_strategy} onChange={(event) => setRiskLimitsDraft((prev) => ({ ...prev, max_positions_per_strategy: event.target.value }))} placeholder="max_positions_per_strategy" data-testid="risk-limits-max-positions-input" />
            <Input value={riskLimitsDraft.max_sector_exposure_pct} onChange={(event) => setRiskLimitsDraft((prev) => ({ ...prev, max_sector_exposure_pct: event.target.value }))} placeholder="max_sector_exposure_pct" data-testid="risk-limits-max-sector-exposure-input" />
            <Input value={riskLimitsDraft.max_correlated_positions} onChange={(event) => setRiskLimitsDraft((prev) => ({ ...prev, max_correlated_positions: event.target.value }))} placeholder="max_correlated_positions" data-testid="risk-limits-max-correlated-input" />

            <Button variant="outline" className="border-black bg-white text-black" onClick={previewRiskLimits} data-testid="risk-limits-preview-button">
              Risk Limits Preview
            </Button>

            <p className="text-xs" data-testid="risk-limits-preview-token">preview_token: {riskLimitsPreview?.preview_token || "-"}</p>
            <p className="text-xs" data-testid="risk-limits-preview-changed-fields">
              changed_fields: {(riskLimitsPreview?.state_snapshot?.changed_fields || []).join(", ") || "-"}
            </p>

            <Input
              value={riskLimitsReason}
              onChange={(event) => setRiskLimitsReason(event.target.value)}
              placeholder="risk limits apply reason"
              data-testid="risk-limits-apply-reason-input"
            />
            <div className="flex items-center gap-2" data-testid="risk-limits-confirm-row">
              <Checkbox
                checked={riskLimitsConfirmChecked}
                onCheckedChange={(checked) => setRiskLimitsConfirmChecked(Boolean(checked))}
                data-testid="risk-limits-apply-confirm-checkbox"
              />
              <span className="text-xs">Preview çıktısını kontrol ettim</span>
            </div>
            <Button
              className="border border-black bg-black text-orange-300 hover:bg-zinc-800"
              onClick={() => setRiskLimitsApplyDialogOpen(true)}
              disabled={!isSuperAdmin || !riskLimitsPreview?.preview_token || !riskLimitsConfirmChecked || riskLimitsReason.trim().length < 3}
              title={
                !isSuperAdmin
                  ? "Sadece super_admin risk limit apply yapabilir"
                  : !riskLimitsPreview?.preview_token
                    ? "Önce preview alınmalı"
                    : !riskLimitsConfirmChecked
                      ? "Önce confirm kutusu işaretlenmeli"
                      : riskLimitsReason.trim().length < 3
                        ? "Reason en az 3 karakter olmalı"
                        : ""
              }
              data-testid="risk-limits-apply-button"
            >
              Risk Limits Apply
            </Button>
          </div>

          <div className="space-y-2 border border-black/25 bg-white p-3" data-testid="risk-exposure-override-panel">
            <p className="font-semibold" data-testid="risk-exposure-override-title">Exposure Override</p>
            <select
              className="h-10 w-full border border-black/40 px-3 text-sm"
              value={exposureOverrideStrategyId}
              onChange={(event) => setExposureOverrideStrategyId(event.target.value)}
              data-testid="risk-exposure-override-strategy-select"
            >
              <option value="" data-testid="risk-exposure-override-strategy-option-empty">strategy seçin</option>
              {Object.keys(riskCapital?.allocation || {}).map((strategyCode) => (
                <option key={strategyCode} value={strategyCode} data-testid={`risk-exposure-override-strategy-option-${strategyCode}`}>
                  {strategyCode}
                </option>
              ))}
            </select>

            <Input
              type="number"
              min={0}
              max={100}
              step="0.1"
              value={exposureOverrideCapPct}
              onChange={(event) => setExposureOverrideCapPct(event.target.value)}
              data-testid="risk-exposure-override-cap-input"
            />

            <Button variant="outline" className="border-black bg-white text-black" onClick={previewExposureOverride} data-testid="risk-exposure-override-preview-button">
              Exposure Preview
            </Button>
            <p className="text-xs" data-testid="risk-exposure-override-preview-token">preview_token: {exposureOverridePreview?.preview_token || "-"}</p>

            <Input
              value={exposureOverrideReason}
              onChange={(event) => setExposureOverrideReason(event.target.value)}
              placeholder="exposure override reason"
              data-testid="risk-exposure-override-reason-input"
            />
            <div className="flex items-center gap-2" data-testid="risk-exposure-override-confirm-row">
              <Checkbox
                checked={exposureOverrideConfirmChecked}
                onCheckedChange={(checked) => setExposureOverrideConfirmChecked(Boolean(checked))}
                data-testid="risk-exposure-override-confirm-checkbox"
              />
              <span className="text-xs">Preview doğrulandı</span>
            </div>
            <Button
              className="border border-black bg-black text-orange-300 hover:bg-zinc-800"
              onClick={() => setExposureApplyDialogOpen(true)}
              disabled={!isSuperAdmin || !exposureOverridePreview?.preview_token || !exposureOverrideConfirmChecked || exposureOverrideReason.trim().length < 3}
              title={
                !isSuperAdmin
                  ? "Sadece super_admin exposure override apply yapabilir"
                  : !exposureOverridePreview?.preview_token
                    ? "Önce preview alınmalı"
                    : !exposureOverrideConfirmChecked
                      ? "Önce confirm kutusu işaretlenmeli"
                      : exposureOverrideReason.trim().length < 3
                        ? "Reason en az 3 karakter olmalı"
                        : ""
              }
              data-testid="risk-exposure-override-apply-button"
            >
              Exposure Override Apply
            </Button>
          </div>
        </div>

        <div className="mt-3 grid gap-3 lg:grid-cols-2" data-testid="risk-breaches-and-alerts-grid">
          <div className="border border-black/25 bg-white p-3" data-testid="risk-breaches-list-panel">
            <p className="font-semibold" data-testid="risk-breaches-list-title">Risk Breaches</p>
            <div className="mt-2 space-y-2" data-testid="risk-breaches-list-items">
              {(riskCapital?.breaches || []).map((item, index) => (
                <div key={`${item.breach_code}-${index}`} className="border border-black/20 p-2" data-testid={`risk-breach-item-${index}`}>
                  <p className="text-xs font-semibold" data-testid={`risk-breach-code-${index}`}>{item.breach_code}</p>
                  <p className="text-xs" data-testid={`risk-breach-values-${index}`}>
                    current: {item.current_value} / limit: {item.limit_value}
                  </p>
                  <p className="text-xs" data-testid={`risk-breach-status-${index}`}>breached: {String(item.is_breached)}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="border border-black/25 bg-white p-3" data-testid="risk-linked-alerts-panel">
            <p className="font-semibold" data-testid="risk-linked-alerts-title">Linked Alerts</p>
            <div className="mt-2 flex flex-wrap gap-2" data-testid="risk-linked-alerts-buttons-row">
              {(riskCapital?.linked_alerts || []).slice(0, 10).map((alert) => (
                <Button
                  key={alert.alert_id}
                  size="sm"
                  variant="outline"
                  className="h-8 border-black bg-white text-black"
                  onClick={() => loadRiskAlertLink(alert.alert_id)}
                  data-testid={`risk-linked-alert-open-button-${alert.alert_id}`}
                >
                  {alert.alert_type}
                </Button>
              ))}
            </div>

            <div className="mt-3 border border-black/20 bg-orange-50 p-2" data-testid="risk-linked-alert-detail-panel">
              <p className="text-xs font-semibold" data-testid="risk-linked-alert-detail-title">Alert Detail ↔ Risk Breach Link</p>
              <p className="text-xs" data-testid="risk-linked-alert-detail-loading">loading: {String(riskAlertLinkLoading)}</p>
              <p className="text-xs" data-testid="risk-linked-alert-detail-alert-id">alert_id: {riskAlertLinkDetail?.alert?.alert_id || "-"}</p>
              <p className="text-xs" data-testid="risk-linked-alert-detail-link-path">
                alert_detail_path: {riskAlertLinkDetail?.alert_detail_path || "-"}
              </p>
              <p className="text-xs" data-testid="risk-linked-alert-detail-breach-count">
                linked_breach_count: {(riskAlertLinkDetail?.linked_breaches || []).length}
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="border border-black/30 bg-orange-100 p-4" data-testid="action-impact-timeline-panel">
        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="action-impact-timeline-header-row">
          <h3 className="text-lg font-bold" data-testid="action-impact-timeline-title">Action Impact Timeline</h3>
          <div className="flex items-center gap-2" data-testid="action-impact-timeline-summary-row">
            <Badge className="border border-black bg-white text-black" data-testid="action-impact-timeline-total-badge">
              total: {timelineSummary?.total ?? 0}
            </Badge>
            <Badge className="border border-black bg-white text-black" data-testid="action-impact-timeline-manual-badge">
              manual: {timelineSummary?.manual_action_count ?? 0}
            </Badge>
            <Badge className="border border-black bg-white text-black" data-testid="action-impact-timeline-system-badge">
              system: {timelineSummary?.system_reaction_count ?? 0}
            </Badge>
            <Button
              size="sm"
              variant="outline"
              className="h-8 border-black bg-white text-black"
              onClick={loadActionImpactTimeline}
              data-testid="action-impact-timeline-refresh-button"
            >
              Timeline Yenile
            </Button>
          </div>
        </div>

        <div className="mt-3 grid gap-2 md:grid-cols-3" data-testid="action-impact-kpi-cards-grid">
          {[
            { key: "selected_signals", label: "Selected Signals" },
            { key: "rejected_signals", label: "Rejected Signals" },
            { key: "risk_breaches", label: "Risk Breaches" },
          ].map((card) => {
            const values = timelineKpiCards?.[card.key] || { before: 0, after: 0, delta: 0 };
            return (
              <div key={card.key} className="border border-black/25 bg-white p-2" data-testid={`action-impact-kpi-card-${card.key}`}>
                <p className="text-xs font-semibold" data-testid={`action-impact-kpi-card-title-${card.key}`}>{card.label}</p>
                <p className="text-xs" data-testid={`action-impact-kpi-card-before-${card.key}`}>before: {values.before ?? 0}</p>
                <p className="text-xs" data-testid={`action-impact-kpi-card-after-${card.key}`}>after: {values.after ?? 0}</p>
                <p className="text-xs" data-testid={`action-impact-kpi-card-delta-${card.key}`}>delta: {values.delta ?? 0}</p>
              </div>
            );
          })}
        </div>

        <div className="mt-3 border border-black/25 bg-white p-2" data-testid="action-impact-chain-summary-panel">
          <p className="text-xs font-semibold" data-testid="action-impact-chain-summary-title">Grouped Chain Summary</p>
          <div className="mt-2 flex flex-wrap gap-2" data-testid="action-impact-chain-summary-list">
            {timelineChainSummary.map((item, index) => (
              <Button
                key={`${item.chainId}-${index}`}
                size="sm"
                variant="outline"
                className="h-7 border-black bg-white text-black"
                onClick={() => navigate(`/admin/strategy/timeline/${encodeURIComponent(item.chainId)}`)}
                data-testid={`action-impact-chain-summary-button-${index}`}
              >
                {item.chainId} ({item.count})
              </Button>
            ))}
            {timelineChainSummary.length === 0 && <p className="text-xs" data-testid="action-impact-chain-summary-empty">chain yok</p>}
          </div>
        </div>

        <div className="mt-3 overflow-x-auto border border-black/25 bg-white" data-testid="action-impact-timeline-table-wrapper">
          <Table data-testid="action-impact-timeline-table">
            <TableHeader>
              <TableRow>
                <TableHead data-testid="action-impact-timeline-head-time">Time</TableHead>
                <TableHead data-testid="action-impact-timeline-head-type">Type</TableHead>
                <TableHead data-testid="action-impact-timeline-head-action">Action</TableHead>
                <TableHead data-testid="action-impact-timeline-head-strategy">Strategy</TableHead>
                <TableHead data-testid="action-impact-timeline-head-reason">Reason</TableHead>
                <TableHead data-testid="action-impact-timeline-head-chain">Chain Ref</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {timelineItems.map((item, index) => (
                <TableRow key={`${item.event_id}-${index}`} data-testid={`action-impact-timeline-row-${index}`}>
                  <TableCell className="text-xs" data-testid={`action-impact-timeline-time-${index}`}>
                    {item.timestamp ? new Date(item.timestamp).toLocaleString() : "-"}
                  </TableCell>
                  <TableCell data-testid={`action-impact-timeline-type-${index}`}>{item.event_type}</TableCell>
                  <TableCell data-testid={`action-impact-timeline-action-${index}`}>{item.action || "-"}</TableCell>
                  <TableCell data-testid={`action-impact-timeline-strategy-${index}`}>{item.strategy_id || "-"}</TableCell>
                  <TableCell data-testid={`action-impact-timeline-reason-${index}`}>{item.reason || "-"}</TableCell>
                  <TableCell data-testid={`action-impact-timeline-chain-${index}`}>
                    {item.chain_id ? (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7 border-black bg-white text-black"
                        onClick={() => navigate(`/admin/strategy/timeline/${encodeURIComponent(item.chain_id)}`)}
                        data-testid={`action-impact-timeline-chain-link-${index}`}
                      >
                        {item.chain_id}
                      </Button>
                    ) : (
                      item.chain_ref || "-"
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {!timelineLoading && timelineItems.length === 0 && (
                <TableRow data-testid="action-impact-timeline-empty-row">
                  <TableCell colSpan={6} className="text-center text-sm text-black/70" data-testid="action-impact-timeline-empty-text">
                    Timeline verisi bulunamadı.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </section>

      <section className="border border-black/30 bg-orange-100 p-4" data-testid="audit-log-panel">
        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="audit-log-header-row">
          <h3 className="text-lg font-bold" data-testid="audit-log-title">Audit Log + Action Feedback</h3>
          <div className="flex items-center gap-2" data-testid="audit-log-controls-row">
            <Input
              type="number"
              min={1}
              max={300}
              value={auditLimit}
              onChange={(event) => setAuditLimit(Math.min(Math.max(Number(event.target.value) || 50, 1), 300))}
              className="w-28"
              data-testid="audit-log-limit-input"
            />
            <Button
              variant="outline"
              className="border-black bg-white text-black"
              onClick={loadAuditLog}
              data-testid="audit-log-refresh-button"
            >
              Audit Yenile
            </Button>
          </div>
        </div>
        <p className="mt-1 text-xs text-black/70" data-testid="audit-log-role-note">
          Admin görebilir. Execute/apply/override işlemleri super_admin ile uygulanır.
        </p>
        <div className="mt-3 overflow-x-auto border border-black/25 bg-white" data-testid="audit-log-table-wrapper">
          <Table data-testid="audit-log-table">
            <TableHeader>
              <TableRow>
                <TableHead data-testid="audit-log-head-action">Action</TableHead>
                <TableHead data-testid="audit-log-head-role">Actor Role</TableHead>
                <TableHead data-testid="audit-log-head-reason">Reason</TableHead>
                <TableHead data-testid="audit-log-head-time">Time</TableHead>
                <TableHead data-testid="audit-log-head-entity">Entity</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {auditItems.map((item) => (
                <TableRow key={item.audit_id} data-testid={`audit-log-row-${item.audit_id}`}>
                  <TableCell data-testid={`audit-log-action-${item.audit_id}`}>{item.action}</TableCell>
                  <TableCell data-testid={`audit-log-role-${item.audit_id}`}>{item.actor_role || "-"}</TableCell>
                  <TableCell data-testid={`audit-log-reason-${item.audit_id}`}>{item.reason || "-"}</TableCell>
                  <TableCell className="text-xs" data-testid={`audit-log-time-${item.audit_id}`}>
                    {item.created_at ? new Date(item.created_at).toLocaleString() : "-"}
                  </TableCell>
                  <TableCell data-testid={`audit-log-entity-${item.audit_id}`}>
                    {item.entity_type}:{item.entity_id}
                  </TableCell>
                </TableRow>
              ))}
              {!auditLoading && auditItems.length === 0 && (
                <TableRow data-testid="audit-log-empty-row">
                  <TableCell colSpan={5} className="text-center text-sm text-black/70" data-testid="audit-log-empty-text">
                    Audit kaydı bulunamadı.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </section>

      <Dialog open={scoreOverrideDialogOpen} onOpenChange={setScoreOverrideDialogOpen}>
        <DialogContent data-testid="score-override-confirm-dialog">
          <DialogHeader>
            <DialogTitle data-testid="score-override-confirm-dialog-title">Manual Override Onayı</DialogTitle>
            <DialogDescription data-testid="score-override-confirm-dialog-description">
              Bu işlem skor kararını manuel etkiler. Onaylıyor musunuz?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setScoreOverrideDialogOpen(false)} data-testid="score-override-confirm-cancel-button">
              Vazgeç
            </Button>
            <Button
              onClick={async () => {
                const success = await applyScoreOverride();
                if (success) {
                  setScoreOverrideDialogOpen(false);
                }
              }}
              data-testid="score-override-confirm-apply-button"
            >
              Onayla
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={riskLimitsApplyDialogOpen} onOpenChange={setRiskLimitsApplyDialogOpen}>
        <DialogContent data-testid="risk-limits-confirm-dialog">
          <DialogHeader>
            <DialogTitle data-testid="risk-limits-confirm-dialog-title">Risk Limits Apply Onayı</DialogTitle>
            <DialogDescription data-testid="risk-limits-confirm-dialog-description">
              Risk limit değişikliği canlı kararları etkiler. Uygulamayı onaylıyor musunuz?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRiskLimitsApplyDialogOpen(false)} data-testid="risk-limits-confirm-cancel-button">
              Vazgeç
            </Button>
            <Button
              onClick={async () => {
                const success = await applyRiskLimits();
                if (success) {
                  setRiskLimitsApplyDialogOpen(false);
                }
              }}
              data-testid="risk-limits-confirm-apply-button"
            >
              Onayla
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={exposureApplyDialogOpen} onOpenChange={setExposureApplyDialogOpen}>
        <DialogContent data-testid="exposure-override-confirm-dialog">
          <DialogHeader>
            <DialogTitle data-testid="exposure-override-confirm-dialog-title">Exposure Override Onayı</DialogTitle>
            <DialogDescription data-testid="exposure-override-confirm-dialog-description">
              Exposure override işlemi risk dağılımını değiştirir. Onaylıyor musunuz?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setExposureApplyDialogOpen(false)} data-testid="exposure-override-confirm-cancel-button">
              Vazgeç
            </Button>
            <Button
              onClick={async () => {
                const success = await applyExposureOverride();
                if (success) {
                  setExposureApplyDialogOpen(false);
                }
              }}
              data-testid="exposure-override-confirm-apply-button"
            >
              Onayla
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={executeDialogOpen} onOpenChange={setExecuteDialogOpen}>
        <DialogContent data-testid="execute-selected-confirm-dialog">
          <DialogHeader>
            <DialogTitle data-testid="execute-selected-confirm-dialog-title">Seçili Sinyalleri Execute Et</DialogTitle>
            <DialogDescription data-testid="execute-selected-confirm-dialog-description">
              Bu aksiyon için aynı seçimin önce simüle edilmiş olması zorunludur.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2" data-testid="execute-selected-confirm-dialog-body">
            <p className="text-sm" data-testid="execute-selected-preview-token">
              preview_token: {selectedSimulation.previewToken || "-"}
            </p>
            <p className="text-sm" data-testid="execute-selected-signal-count">signal_count: {normalizedSelectedSignalIds.length}</p>
            <Textarea
              value={executeReason}
              onChange={(event) => setExecuteReason(event.target.value)}
              placeholder="execute reason"
              className="border-black/40 bg-orange-50"
              data-testid="execute-selected-reason-textarea"
            />
            <div className="flex items-center gap-2" data-testid="execute-selected-confirm-checkbox-row">
              <Checkbox
                checked={executeConfirmChecked}
                onCheckedChange={(checked) => setExecuteConfirmChecked(Boolean(checked))}
                data-testid="execute-selected-confirm-checkbox"
              />
              <p className="text-xs" data-testid="execute-selected-confirm-checkbox-label">
                Simulation çıktısını kontrol ettim, execute etmek için onaylıyorum.
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              className="border-black bg-white text-black"
              onClick={() => setExecuteDialogOpen(false)}
              data-testid="execute-selected-cancel-button"
            >
              Vazgeç
            </Button>
            <Button
              className="border border-black bg-black text-orange-300 hover:bg-zinc-800"
              onClick={executeSelectedSignals}
              disabled={!canExecuteSelectedSignals || !executeConfirmChecked || executeReason.trim().length < 3}
              data-testid="execute-selected-confirm-button"
            >
              Execute Confirm
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Sheet open={explainabilityOpen} onOpenChange={setExplainabilityOpen}>
        <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-2xl" data-testid="signal-explainability-sheet">
          <SheetHeader>
            <SheetTitle data-testid="signal-explainability-sheet-title">Signal Explainability</SheetTitle>
            <SheetDescription data-testid="signal-explainability-sheet-description">
              Score breakdown, contribution, decision path ve override geçmişi.
            </SheetDescription>
          </SheetHeader>

          {explainabilityLoading && <p className="mt-3 text-sm" data-testid="signal-explainability-loading-text">Yükleniyor...</p>}

          {!explainabilityLoading && explainabilityData && (
            <div className="mt-4 space-y-4" data-testid="signal-explainability-content">
              <div className="border border-black/25 bg-orange-50 p-3" data-testid="signal-explainability-signal-summary-panel">
                <p className="text-sm" data-testid="signal-explainability-signal-id">signal_id: {explainabilityData?.signal?.signal_id || "-"}</p>
                <p className="text-sm" data-testid="signal-explainability-symbol">symbol: {explainabilityData?.signal?.symbol || "-"}</p>
                <p className="text-sm" data-testid="signal-explainability-strategy">strategy_id: {explainabilityData?.signal?.strategy_id || "-"}</p>
                <p className="text-sm" data-testid="signal-explainability-final-decision">final_decision: {explainabilityData?.final_decision || "-"}</p>
              </div>

              <div className="border border-black/25 bg-white p-3" data-testid="signal-explainability-factor-weights-panel">
                <p className="text-sm font-semibold" data-testid="signal-explainability-factor-weights-title">Factor Weights</p>
                <p className="text-xs" data-testid="signal-explainability-factor-weights-json">
                  {JSON.stringify(explainabilityData?.factor_weights || {})}
                </p>
              </div>

              <div className="border border-black/25 bg-white p-3" data-testid="signal-explainability-contribution-panel">
                <p className="text-sm font-semibold" data-testid="signal-explainability-contribution-title">Contribution Map</p>
                <div className="mt-2 space-y-1" data-testid="signal-explainability-contribution-list">
                  {Object.entries(explainabilityData?.contribution_map || {}).map(([key, value]) => (
                    <p key={key} className="text-xs" data-testid={`signal-explainability-contribution-item-${key}`}>
                      {key}: {String(value)}
                    </p>
                  ))}
                </div>
              </div>

              <div className="border border-black/25 bg-white p-3" data-testid="signal-explainability-rule-hits-panel">
                <p className="text-sm font-semibold" data-testid="signal-explainability-rule-hits-title">Rule Hits</p>
                <p className="text-xs" data-testid="signal-explainability-rule-hits-json">
                  {JSON.stringify(explainabilityData?.triggered_rules || [])}
                </p>
              </div>

              <div className="border border-black/25 bg-white p-3" data-testid="signal-explainability-override-history-panel">
                <p className="text-sm font-semibold" data-testid="signal-explainability-override-history-title">Override History</p>
                <p className="text-xs" data-testid="signal-explainability-override-history-count">
                  count: {(explainabilityData?.override_history || []).length}
                </p>
                {(explainabilityData?.override_history || []).slice(0, 10).map((item, index) => (
                  <p key={`${item.created_at}-${index}`} className="text-xs" data-testid={`signal-explainability-override-history-item-${index}`}>
                    {item.created_at} · delta {item.override_delta} · reason {item.reason}
                  </p>
                ))}
              </div>

              <div className="border border-black/25 bg-white p-3" data-testid="signal-explainability-decision-log-panel">
                <p className="text-sm font-semibold" data-testid="signal-explainability-decision-log-title">Decision Log</p>
                {(explainabilityData?.decision_log || []).slice(0, 20).map((item, index) => (
                  <p key={`${item.audit_id}-${index}`} className="text-xs" data-testid={`signal-explainability-decision-log-item-${index}`}>
                    {item.created_at} · {item.action} · {item.reason || "-"}
                  </p>
                ))}
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </section>
  );
};
