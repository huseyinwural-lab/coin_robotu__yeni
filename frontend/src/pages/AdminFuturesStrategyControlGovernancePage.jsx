import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { DecisionModal } from "@/components/DecisionModal";
import { apiClient } from "@/lib/api";

const TAB_ITEMS = [
  { key: "overview", label: "Overview" },
  { key: "universe_control", label: "Universe Control" },
  { key: "rollout", label: "Rollout" },
  { key: "strategy_governance", label: "Strategy Governance" },
  { key: "capital_governance", label: "Capital Governance" },
  { key: "drift_action_center", label: "Drift Action Center" },
  { key: "audit_history", label: "Audit / History" },
];

const ACTIONS = [
  { key: "enable", label: "Enable" },
  { key: "throttle", label: "Throttle" },
  { key: "pause", label: "Pause" },
  { key: "resume", label: "Resume" },
  { key: "disable", label: "Disable", destructive: true, confirmPhrase: "DISABLE STRATEGY" },
  { key: "decommission", label: "Decommission", destructive: true, confirmPhrase: "DECOMMISSION STRATEGY" },
];

const BULK_CONFIRM_MAP = {
  pause: "BULK PAUSE",
  resume: "BULK RESUME",
  throttle: "BULK THROTTLE",
};

const ROLLOUT_CONFIRM_MAP = {
  promote_shadow: "PROMOTE SHADOW",
  rollout: "APPLY ROLLOUT",
  rollback: "ROLLBACK LAST ACTION",
};

const DRIFT_CONFIRM_MAP = {
  ignore: "IGNORE DRIFT ALERT",
  disable_strategy: "DISABLE VIA DRIFT",
};

const DRIFT_ENDPOINT_MAP = {
  ack: "ack",
  mute: "mute",
  ignore: "ignore",
  disable_strategy: "disable-strategy",
  retrain: "retrain",
};

const MONITOR_REFRESH_INTERVAL_MS = 8000;
const MONITOR_ACTIVE_WINDOW_MS = 5 * 60 * 1000;

const toNumericValue = (value, fallback = 0) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const toSignedDelta = (value) => {
  const normalized = toNumericValue(value, 0);
  return `${normalized >= 0 ? "+" : ""}${normalized.toFixed(2)}`;
};

const classifyBulkResult = (row) => {
  const status = String(row?.status || "").toLowerCase();
  if (["success", "dry_run"].includes(status)) return "success";
  if (status === "skipped") return "skipped";
  return "failed";
};

const buildSnapshotSummary = (snapshot) => {
  if (!snapshot) return "n/a";
  return [
    `control=${snapshot.control_state || "-"}`,
    `lifecycle=${snapshot.lifecycle_state || "-"}`,
    `throttle=${snapshot.throttle_level || "-"}`,
    `rollout=${snapshot.rollout_mode || "-"}/${snapshot.rollout_percentage ?? "-"}%`,
  ].join(" · ");
};

export const AdminFuturesStrategyControlGovernancePage = () => {
  const [activeTab, setActiveTab] = useState("strategy_governance");
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [overviewPayload, setOverviewPayload] = useState(null);
  const [capitalPayload, setCapitalPayload] = useState({ budget: null, usage: null, drift: null, globalRisk: null });

  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailPayload, setDetailPayload] = useState(null);

  const [actionModal, setActionModal] = useState({ open: false, action: null, strategy: null });
  const [actionReason, setActionReason] = useState("");
  const [actionConfirm, setActionConfirm] = useState("");
  const [throttleLevel, setThrottleLevel] = useState("L1");
  const [dryRun, setDryRun] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [selectedStrategyIds, setSelectedStrategyIds] = useState([]);
  const [bulkAction, setBulkAction] = useState("pause");
  const [bulkReason, setBulkReason] = useState("");
  const [bulkConfirm, setBulkConfirm] = useState("");
  const [bulkThrottleLevel, setBulkThrottleLevel] = useState("L1");
  const [bulkSubmitting, setBulkSubmitting] = useState(false);
  const [bulkResult, setBulkResult] = useState(null);
  const [bulkBreakdownExpanded, setBulkBreakdownExpanded] = useState(false);

  const [rolloutStrategyId, setRolloutStrategyId] = useState("");
  const [rolloutOperation, setRolloutOperation] = useState("rollout");
  const [rolloutReason, setRolloutReason] = useState("");
  const [rolloutConfirm, setRolloutConfirm] = useState("");
  const [rolloutPercentage, setRolloutPercentage] = useState(10);
  const [rolloutSubmitting, setRolloutSubmitting] = useState(false);
  const [rolloutPrecheck, setRolloutPrecheck] = useState(null);
  const [rolloutResult, setRolloutResult] = useState(null);

  const [driftAlerts, setDriftAlerts] = useState([]);
  const [driftLoading, setDriftLoading] = useState(false);
  const [driftMuteDuration, setDriftMuteDuration] = useState(1);
  const [driftSubmitting, setDriftSubmitting] = useState(false);
  const [driftResult, setDriftResult] = useState(null);
  const [decisionModal, setDecisionModal] = useState({
    open: false,
    mode: "",
    actionType: "",
    strategyId: "",
    title: "",
    confirmRequired: false,
    confirmPlaceholder: "",
    params: {},
    defaultReason: "",
    payload: null,
  });

  const [feedbackStrategyId, setFeedbackStrategyId] = useState("");
  const [feedbackDriftAlertId, setFeedbackDriftAlertId] = useState("");
  const [feedbackLabel, setFeedbackLabel] = useState("false_reject");
  const [feedbackTaxonomy, setFeedbackTaxonomy] = useState("threshold_too_strict");
  const [feedbackReason, setFeedbackReason] = useState("");
  const [feedbackSampleLink, setFeedbackSampleLink] = useState("");
  const [feedbackSliceSymbol, setFeedbackSliceSymbol] = useState("");
  const [feedbackSliceWindow, setFeedbackSliceWindow] = useState("24h");
  const [feedbackSliceSeverity, setFeedbackSliceSeverity] = useState("MEDIUM");
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);
  const [feedbackItems, setFeedbackItems] = useState([]);
  const [feedbackVersion, setFeedbackVersion] = useState(0);

  const [modelUpdateReason, setModelUpdateReason] = useState("");
  const [modelUpdateSubmitting, setModelUpdateSubmitting] = useState(false);
  const [modelUpdateStatus, setModelUpdateStatus] = useState(null);

  const [exportFormat, setExportFormat] = useState("json");
  const [exporting, setExporting] = useState(false);
  const [exportSummary, setExportSummary] = useState(null);

  const [rollbackSnapshots, setRollbackSnapshots] = useState([]);
  const [rollbackSnapshotsLoading, setRollbackSnapshotsLoading] = useState(false);
  const [selectedSnapshotTraceId, setSelectedSnapshotTraceId] = useState("");
  const [rollbackRequestReason, setRollbackRequestReason] = useState("");
  const [rollbackRequestSubmitting, setRollbackRequestSubmitting] = useState(false);

  const [approvalRequests, setApprovalRequests] = useState([]);
  const [approvalLoading, setApprovalLoading] = useState(false);
  const [approvalDecisionReason, setApprovalDecisionReason] = useState("");
  const [approvalSubmitting, setApprovalSubmitting] = useState(false);

  const [policySuggestionSummary, setPolicySuggestionSummary] = useState(null);

  const [lastActionResult, setLastActionResult] = useState(null);
  const [postActionMonitor, setPostActionMonitor] = useState({
    active: false,
    phase: "idle",
    actionType: "",
    actionLabel: "",
    strategyId: "",
    traceId: "",
    startedAt: null,
    expiresAt: null,
    baselineBefore: null,
    baselineAfter: null,
    currentSnapshot: null,
    lastRefreshedAt: null,
    message: "",
  });

  const actionMeta = useMemo(() => ACTIONS.find((item) => item.key === actionModal.action) || null, [actionModal.action]);
  const strategies = useMemo(() => overviewPayload?.strategies || [], [overviewPayload]);
  const selectedRolloutStrategy = useMemo(
    () => strategies.find((item) => item.strategy_id === rolloutStrategyId) || null,
    [rolloutStrategyId, strategies],
  );
  const decisionRiskSnapshot = useMemo(
    () => strategies.find((item) => item.strategy_id === decisionModal.strategyId) || null,
    [decisionModal.strategyId, strategies],
  );

  const strategyCount = strategies.length;
  const disabledCount = strategies.filter((row) => row.lifecycle_state === "DISABLED").length;
  const throttledCount = strategies.filter((row) => row.throttle_level !== "NONE").length;
  const driftCount = strategies.reduce((acc, row) => acc + Number(row.drift_count || 0), 0);
  const bulkResultRows = useMemo(() => {
    if (!Array.isArray(bulkResult?.results)) return [];
    return bulkResult.results;
  }, [bulkResult]);
  const bulkResultBuckets = useMemo(() => {
    const buckets = { success: [], failed: [], skipped: [] };
    bulkResultRows.forEach((row) => {
      const bucket = classifyBulkResult(row);
      buckets[bucket].push(row);
    });
    return buckets;
  }, [bulkResultRows]);
  const postActionBaseline = useMemo(
    () => postActionMonitor?.baselineBefore || postActionMonitor?.baselineAfter || null,
    [postActionMonitor?.baselineAfter, postActionMonitor?.baselineBefore],
  );
  const postActionDeltas = useMemo(() => {
    const baseline = postActionBaseline || {};
    const current = postActionMonitor?.currentSnapshot || {};
    return {
      health: toNumericValue(current?.health_score, 0) - toNumericValue(baseline?.health_score, 0),
      error: toNumericValue(current?.error_rate_pct, 0) - toNumericValue(baseline?.error_rate_pct, 0),
      risk: toNumericValue(current?.risk_score, 0) - toNumericValue(baseline?.risk_score, 0),
    };
  }, [postActionBaseline, postActionMonitor?.currentSnapshot]);
  const postActionRemainingSeconds = useMemo(() => {
    if (!postActionMonitor?.active || !postActionMonitor?.expiresAt) return 0;
    const remainingMs = Math.max(0, Number(postActionMonitor.expiresAt) - Date.now());
    return Math.floor(remainingMs / 1000);
  }, [postActionMonitor?.active, postActionMonitor?.expiresAt, postActionMonitor?.lastRefreshedAt]);

  const loadOverview = useCallback(async () => {
    const response = await apiClient.get("/admin/futures/strategy-control/overview");
    const data = response.data || null;
    setOverviewPayload(data);
    const firstId = data?.strategies?.[0]?.strategy_id || "";
    setRolloutStrategyId((prev) => prev || firstId);
    setFeedbackStrategyId((prev) => prev || firstId);
    return data;
  }, []);

  const loadCapital = useCallback(async () => {
    const [budgetRes, usageRes, driftRes, riskRes] = await Promise.all([
      apiClient.get("/admin/futures/capital-budget"),
      apiClient.get("/admin/futures/capital-usage"),
      apiClient.get("/admin/futures/capital-drift"),
      apiClient.get("/admin/futures/global-risk"),
    ]);
    setCapitalPayload({
      budget: budgetRes.data || null,
      usage: usageRes.data || null,
      drift: driftRes.data || null,
      globalRisk: riskRes.data || null,
    });
  }, []);

  const loadDriftAlerts = useCallback(async () => {
    setDriftLoading(true);
    try {
      const { data } = await apiClient.get("/admin/futures/strategy-control/drift-alerts");
      setDriftAlerts(data?.items || []);
    } finally {
      setDriftLoading(false);
    }
  }, []);

  const loadFeedbackForStrategy = useCallback(async (strategyId) => {
    if (!strategyId) {
      setFeedbackItems([]);
      setFeedbackVersion(0);
      return;
    }
    const { data } = await apiClient.get(`/admin/futures/strategy/${strategyId}/feedback`);
    setFeedbackItems(data?.items || []);
    setFeedbackVersion(data?.dataset_version || 0);
  }, []);

  const loadModelUpdateStatus = useCallback(async (strategyId) => {
    if (!strategyId) {
      setModelUpdateStatus(null);
      return;
    }
    const { data } = await apiClient.get(`/admin/futures/strategy/${strategyId}/model-update-status`);
    setModelUpdateStatus(data || null);
  }, []);

  const loadRollbackSnapshots = useCallback(async (strategyId) => {
    if (!strategyId) {
      setRollbackSnapshots([]);
      return;
    }
    setRollbackSnapshotsLoading(true);
    try {
      const { data } = await apiClient.get(`/admin/futures/strategy/${strategyId}/rollback-snapshots`);
      const items = data?.items || [];
      setRollbackSnapshots(items);
      setSelectedSnapshotTraceId((prev) => prev || items[0]?.snapshot_trace_id || "");
    } finally {
      setRollbackSnapshotsLoading(false);
    }
  }, []);

  const loadApprovalRequests = useCallback(async () => {
    setApprovalLoading(true);
    try {
      const { data } = await apiClient.get("/admin/futures/strategy/approval-requests");
      setApprovalRequests(data?.items || []);
    } finally {
      setApprovalLoading(false);
    }
  }, []);

  const loadPolicySuggestions = useCallback(async () => {
    const { data } = await apiClient.get("/admin/futures/strategy-control/policy-suggestions");
    setPolicySuggestionSummary(data?.summary || null);
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setErrorMessage("");
    try {
      const [overviewData] = await Promise.all([loadOverview(), loadCapital(), loadDriftAlerts()]);
      const selectedId = feedbackStrategyId || overviewData?.strategies?.[0]?.strategy_id || "";
      await Promise.all([loadApprovalRequests(), loadPolicySuggestions()]);
      if (selectedId) {
        await Promise.all([loadFeedbackForStrategy(selectedId), loadModelUpdateStatus(selectedId), loadRollbackSnapshots(selectedId)]);
      }
    } catch (error) {
      const message = error?.response?.data?.detail || "Strategy Control verisi alınamadı";
      setErrorMessage(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [feedbackStrategyId, loadApprovalRequests, loadCapital, loadDriftAlerts, loadFeedbackForStrategy, loadModelUpdateStatus, loadOverview, loadPolicySuggestions, loadRollbackSnapshots]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    if (!feedbackStrategyId) return;
    loadFeedbackForStrategy(feedbackStrategyId);
    loadModelUpdateStatus(feedbackStrategyId);
    loadRollbackSnapshots(feedbackStrategyId);
  }, [feedbackStrategyId, loadFeedbackForStrategy, loadModelUpdateStatus, loadRollbackSnapshots]);

  useEffect(() => {
    const status = modelUpdateStatus?.current_job?.status;
    if (!feedbackStrategyId || !status || !["queued", "running"].includes(status)) return;
    const timer = window.setInterval(() => {
      loadModelUpdateStatus(feedbackStrategyId);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [feedbackStrategyId, loadModelUpdateStatus, modelUpdateStatus]);

  useEffect(() => {
    if (!feedbackStrategyId) return;
    const matched = driftAlerts.find((item) => item.strategy_id === feedbackStrategyId);
    const currentValid = driftAlerts.some(
      (item) => item.strategy_id === feedbackStrategyId && item.alert_id === feedbackDriftAlertId,
    );
    if (!currentValid) {
      setFeedbackDriftAlertId(matched?.alert_id || "");
    }
  }, [driftAlerts, feedbackDriftAlertId, feedbackStrategyId]);

  useEffect(() => {
    if (bulkResult) {
      setBulkBreakdownExpanded(false);
    }
  }, [bulkResult]);

  const activatePostActionMonitor = useCallback(({ actionType, actionLabel, strategyId, result }) => {
    const decisionContext = result?.decision_context || result?.approval_request?.decision_context || {};
    const beforeSnapshot = result?.before_state || decisionContext?.before_after_summary?.before || null;
    const afterSnapshot = result?.after_state || result?.state_snapshot || decisionContext?.before_after_summary?.after || null;
    const targetStrategyId = String(
      strategyId || result?.state_snapshot?.strategy_id || result?.approval_request?.strategy_id || "",
    ).trim();
    if (!targetStrategyId || !afterSnapshot) return;

    const now = Date.now();
    setPostActionMonitor({
      active: true,
      phase: "active",
      actionType: actionType || "critical_action",
      actionLabel: actionLabel || actionType || "critical_action",
      strategyId: targetStrategyId,
      traceId: result?.trace_id || "",
      startedAt: now,
      expiresAt: now + MONITOR_ACTIVE_WINDOW_MS,
      baselineBefore: beforeSnapshot,
      baselineAfter: afterSnapshot,
      currentSnapshot: afterSnapshot,
      lastRefreshedAt: now,
      message: result?.message || "",
    });
  }, []);

  useEffect(() => {
    if (!postActionMonitor?.active || !postActionMonitor?.strategyId) return;

    const refreshMonitor = async () => {
      const now = Date.now();
      if (now >= Number(postActionMonitor.expiresAt || 0)) {
        setPostActionMonitor((prev) => ({
          ...prev,
          active: false,
          phase: "passive",
          lastRefreshedAt: now,
        }));
        return;
      }

      try {
        const overviewData = await loadOverview();
        const liveRow = (overviewData?.strategies || []).find(
          (row) => String(row?.strategy_id || "") === String(postActionMonitor.strategyId),
        );
        if (!liveRow) return;
        setPostActionMonitor((prev) => ({
          ...prev,
          currentSnapshot: liveRow,
          lastRefreshedAt: Date.now(),
        }));
      } catch (_error) {
        // Monitor refresh best-effort
      }
    };

    refreshMonitor();
    const timer = window.setInterval(refreshMonitor, MONITOR_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [loadOverview, postActionMonitor?.active, postActionMonitor?.expiresAt, postActionMonitor?.strategyId]);

  const openDetail = async (strategyId) => {
    setDetailOpen(true);
    setDetailLoading(true);
    try {
      const [detailRes, auditRes] = await Promise.all([
        apiClient.get(`/admin/futures/strategy/${strategyId}/detail`),
        apiClient.get(`/admin/futures/strategy/${strategyId}/audit-history`),
      ]);
      setDetailPayload({
        ...(detailRes.data || {}),
        audit_items: (auditRes.data || {}).items || [],
      });
    } catch (error) {
      const message = error?.response?.data?.detail || "Strategy detail alınamadı";
      toast.error(message);
      setDetailPayload(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const openActionModal = (action, strategy) => {
    if (action === "disable" || action === "decommission") {
      const isDisable = action === "disable";
      openDecisionModal({
        mode: isDisable ? "row_action_disable" : "row_action_decommission",
        actionType: action,
        strategyId: strategy?.strategy_id,
        title: isDisable ? "Disable Decision" : "Decommission Decision",
        confirmRequired: true,
        confirmPlaceholder: isDisable
          ? "Onay ifadesi: DISABLE STRATEGY"
          : "Onay ifadesi: DECOMMISSION STRATEGY",
        defaultReason: isDisable
          ? `manual_disable_${strategy?.strategy_id || "strategy"}`
          : `manual_decommission_${strategy?.strategy_id || "strategy"}`,
        params: {},
        payload: { action, strategy },
      });
      return;
    }
    setActionModal({ open: true, action, strategy });
    setActionReason("");
    setActionConfirm("");
    setThrottleLevel("L1");
    setDryRun(false);
  };

  const openDecisionModal = (config) => {
    setDecisionModal({
      open: true,
      mode: config.mode || "",
      actionType: config.actionType || "",
      strategyId: config.strategyId || "",
      title: config.title || "Decision",
      confirmRequired: Boolean(config.confirmRequired),
      confirmPlaceholder: config.confirmPlaceholder || "",
      params: config.params || {},
      defaultReason: config.defaultReason || "",
      payload: config.payload || null,
    });
  };

  const requestImpactPreview = async ({ actionType, strategyId, params }) => {
    const { data } = await apiClient.post(`/admin/futures/strategy/${strategyId}/impact-preview`, {
      action_type: actionType,
      params: params || {},
    });
    return data || null;
  };

  const submitAction = async (decisionInput = null) => {
    const strategy = decisionInput?.strategy || actionModal.strategy;
    const actionKey = decisionInput?.action || actionMeta?.key;
    const activeAction = ACTIONS.find((item) => item.key === actionKey) || null;
    if (!strategy || !activeAction) return;

    const reasonValue = String(decisionInput?.reason || actionReason || "").trim();
    const confirmValue = String(decisionInput?.confirmPhrase || actionConfirm || "").trim();
    const previewToken = String(decisionInput?.previewToken || "").trim();

    if (reasonValue.length < 3) {
      toast.error("Reason zorunlu (min 3 karakter)");
      return;
    }
    if (activeAction.confirmPhrase && confirmValue.toUpperCase() !== activeAction.confirmPhrase) {
      toast.error(`Onay ifadesi eşleşmeli: ${activeAction.confirmPhrase}`);
      return;
    }

    setSubmitting(true);
    try {
      const body = {
        reason: reasonValue,
        confirm_phrase: confirmValue || null,
        throttle_level: activeAction.key === "throttle" ? throttleLevel : null,
        preview_token: previewToken || null,
        dry_run: dryRun,
      };
      const { data } = await apiClient.post(`/admin/futures/strategy/${strategy.strategy_id}/${activeAction.key}`, body);
      setLastActionResult(data || null);
      if (data?.status === "rejected") {
        toast.error(data?.message || "Aksiyon reddedildi");
      } else {
        toast.success(data?.message || "Aksiyon uygulandı");
      }
      if (data?.status !== "rejected" && ["disable", "decommission"].includes(activeAction.key)) {
        activatePostActionMonitor({
          actionType: activeAction.key,
          actionLabel: activeAction.label,
          strategyId: strategy?.strategy_id,
          result: data,
        });
      }
      await loadOverview();
      setActionModal({ open: false, action: null, strategy: null });
    } catch (error) {
      const message = error?.response?.data?.detail || "Aksiyon uygulanamadı";
      toast.error(message);
    } finally {
      setSubmitting(false);
    }
  };

  const toggleStrategySelect = (strategyId) => {
    setSelectedStrategyIds((prev) => (prev.includes(strategyId) ? prev.filter((id) => id !== strategyId) : [...prev, strategyId]));
  };

  const submitBulkAction = async () => {
    if (selectedStrategyIds.length === 0) {
      toast.error("Bulk için en az bir strategy seçmelisiniz");
      return;
    }
    if (bulkReason.trim().length < 3) {
      toast.error("Bulk reason zorunlu");
      return;
    }
    const expected = BULK_CONFIRM_MAP[bulkAction];
    if (bulkConfirm.trim().toUpperCase() !== expected) {
      toast.error(`Bulk confirm ifadesi eşleşmeli: ${expected}`);
      return;
    }

    setBulkSubmitting(true);
    try {
      const { data } = await apiClient.post("/admin/futures/strategy/bulk-action", {
        reason: bulkReason.trim(),
        confirm_phrase: bulkConfirm.trim(),
        strategy_ids: selectedStrategyIds,
        action: bulkAction,
        throttle_level: bulkAction === "throttle" ? bulkThrottleLevel : null,
        dry_run: false,
      });
      setBulkResult(data || null);
      setLastActionResult(data || null);
      if (data?.status === "rejected") toast.error(data?.message || "Bulk action reddedildi");
      else toast.success(data?.message || "Bulk action uygulandı");
      await loadOverview();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Bulk action başarısız");
    } finally {
      setBulkSubmitting(false);
    }
  };

  const loadRolloutPrecheck = async () => {
    if (!rolloutStrategyId) return;
    try {
      const { data } = await apiClient.get(`/admin/futures/strategy/${rolloutStrategyId}/rollout-precheck`);
      setRolloutPrecheck(data?.precheck || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Rollout pre-check alınamadı");
    }
  };

  const submitRolloutOperation = async (decisionInput = null) => {
    if (!rolloutStrategyId) {
      toast.error("Rollout için strategy seçin");
      return;
    }
    const reasonValue = String(decisionInput?.reason || rolloutReason || "").trim();
    const confirmValue = String(decisionInput?.confirmPhrase || rolloutConfirm || "").trim();
    const previewToken = String(decisionInput?.previewToken || "").trim();

    if (reasonValue.length < 3) {
      toast.error("Rollout reason zorunlu");
      return;
    }
    const expected = ROLLOUT_CONFIRM_MAP[rolloutOperation];
    if (confirmValue.toUpperCase() !== expected) {
      toast.error(`Onay ifadesi eşleşmeli: ${expected}`);
      return;
    }

    setRolloutSubmitting(true);
    try {
      let url = "";
      let body = { reason: reasonValue, confirm_phrase: confirmValue, preview_token: previewToken || null, dry_run: false };
      if (rolloutOperation === "promote_shadow") {
        url = `/admin/futures/strategy/${rolloutStrategyId}/promote-shadow`;
      } else if (rolloutOperation === "rollout") {
        url = `/admin/futures/strategy/${rolloutStrategyId}/rollout`;
        body = { ...body, rollout_percentage: Number(rolloutPercentage || 10) };
      } else {
        url = `/admin/futures/strategy/${rolloutStrategyId}/rollback`;
      }

      const { data } = await apiClient.post(url, body);
      setRolloutResult(data || null);
      setLastActionResult(data || null);
      if (data?.status === "rejected") toast.error(data?.message || "Rollout aksiyonu reddedildi");
      else if (data?.status === "auto_rollback") toast.error(data?.message || "Auto rollback tetiklendi");
      else toast.success(data?.message || "Rollout aksiyonu tamamlandı");

      if (data?.status !== "rejected" && ["rollout", "rollback"].includes(rolloutOperation)) {
        activatePostActionMonitor({
          actionType: rolloutOperation,
          actionLabel: `rollout_${rolloutOperation}`,
          strategyId: rolloutStrategyId,
          result: data,
        });
      }

      await loadOverview();
      await loadRolloutPrecheck();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Rollout aksiyonu başarısız");
    } finally {
      setRolloutSubmitting(false);
    }
  };

  const openDriftActionModal = (action, alert, options = {}) => {
    const reasonPrefill = String(options?.reasonPrefill || "").trim();
    openDecisionModal({
      mode: "drift",
      actionType: action,
      strategyId: alert?.strategy_id,
      title: `Drift Action · ${action}`,
      confirmRequired: Boolean(DRIFT_CONFIRM_MAP[action]),
      confirmPlaceholder: DRIFT_CONFIRM_MAP[action] ? `Onay ifadesi: ${DRIFT_CONFIRM_MAP[action]}` : "",
      defaultReason: reasonPrefill || `drift_${action}_${alert?.strategy_id || "strategy"}`,
      params: {
        alert_id: alert?.alert_id,
        mute_duration_hours: action === "mute" ? Number(driftMuteDuration) : null,
      },
      payload: { alert },
    });
  };

  const openDriftDeepLink = (alert) => {
    const targetTab = alert?.deep_link?.target_tab || "strategy_governance";
    const strategyId = alert?.strategy_id;
    setActiveTab(targetTab);
    if (strategyId) {
      setRolloutStrategyId(strategyId);
      setSelectedStrategyIds([strategyId]);
      setFeedbackStrategyId(strategyId);
      setFeedbackDriftAlertId(alert?.alert_id || "");
    }
    toast.success(`Deep-link açıldı: ${targetTab}`);
  };

  const openPolicyApplyHook = ({ source, ruleText = "", alert = null }) => {
    const normalizedRule = String(ruleText || "").trim();
    if (alert) {
      const recommended = String(alert?.recommended_action?.type || "ACK").toUpperCase();
      const actionMap = {
        ACK: "ack",
        MUTE: "mute",
        DISABLE: "disable_strategy",
        RETRAIN: "retrain",
      };
      const actionType = actionMap[recommended] || "ack";
      openDriftActionModal(actionType, alert, {
        reasonPrefill: `policy_apply_${source || "drift"}_${alert?.strategy_id || "strategy"} · ${normalizedRule || "policy_suggestion"}`,
      });
      return;
    }

    const targetStrategyId = feedbackStrategyId || rolloutStrategyId || strategies?.[0]?.strategy_id || "";
    if (!targetStrategyId) {
      toast.error("Policy Apply Hook için hedef strategy bulunamadı");
      return;
    }

    const lowered = normalizedRule.toLowerCase();
    let thresholdDelta = 0;
    if (lowered.includes("strict")) thresholdDelta = -0.02;
    if (lowered.includes("loose")) thresholdDelta = 0.02;

    openDecisionModal({
      mode: "threshold_placeholder",
      actionType: "threshold_change",
      strategyId: targetStrategyId,
      title: "Policy Apply Hook",
      confirmRequired: false,
      confirmPlaceholder: "",
      defaultReason: `policy_apply_${targetStrategyId} · ${normalizedRule || "rule_based_suggestion"}`,
      params: {
        threshold_delta: thresholdDelta,
        target_strategy: targetStrategyId,
        policy_rule: normalizedRule || "rule_based_suggestion",
      },
      payload: { source: source || "policy_panel" },
    });
  };

  const submitDriftAction = async (decisionInput = null) => {
    const action = decisionInput?.action;
    const alert = decisionInput?.alert;
    if (!action || !alert) return;
    const reasonValue = String(decisionInput?.reason || "").trim();
    const confirmValue = String(decisionInput?.confirmPhrase || "").trim();
    const previewToken = String(decisionInput?.previewToken || "").trim();

    if (reasonValue.length < 3) {
      toast.error("Drift aksiyonu için reason zorunlu");
      return;
    }
    const requiredConfirm = DRIFT_CONFIRM_MAP[action];
    if (requiredConfirm && confirmValue.toUpperCase() !== requiredConfirm) {
      toast.error(`Onay ifadesi eşleşmeli: ${requiredConfirm}`);
      return;
    }

    const endpointSuffix = DRIFT_ENDPOINT_MAP[action];
    if (!endpointSuffix) return;

    setDriftSubmitting(true);
    try {
      const { data } = await apiClient.post(
        `/admin/futures/drift-alert/${alert.alert_id}/${endpointSuffix}`,
        {
          reason: reasonValue,
          confirm_phrase: confirmValue || null,
          mute_duration_hours: action === "mute" ? Number(driftMuteDuration) : null,
          preview_token: previewToken || null,
          dry_run: false,
        },
      );

      setDriftResult(data || null);
      setLastActionResult(data || null);
      if (data?.status === "rejected") toast.error(data?.message || "Drift aksiyonu reddedildi");
      else toast.success(data?.message || "Drift aksiyonu uygulandı");

      if (data?.status !== "rejected" && action === "disable_strategy") {
        activatePostActionMonitor({
          actionType: "drift_disable_strategy",
          actionLabel: "drift_disable_strategy",
          strategyId: alert?.strategy_id,
          result: data,
        });
      }

      await Promise.all([loadDriftAlerts(), loadOverview()]);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Drift aksiyonu başarısız");
    } finally {
      setDriftSubmitting(false);
    }
  };

  const submitFeedbackLabel = async () => {
    if (!feedbackStrategyId) {
      toast.error("Feedback için strategy seçin");
      return;
    }
    if (!feedbackDriftAlertId) {
      toast.error("Feedback için drift context seçin");
      return;
    }
    if (feedbackReason.trim().length < 3) {
      toast.error("Feedback reason zorunlu");
      return;
    }

    setFeedbackSubmitting(true);
    try {
      const { data } = await apiClient.post(`/admin/futures/strategy/${feedbackStrategyId}/feedback-label`, {
        reason: feedbackReason.trim(),
        drift_alert_id: feedbackDriftAlertId,
        corrected_label: feedbackLabel,
        reason_taxonomy: feedbackTaxonomy,
        sample_link: feedbackSampleLink.trim() || null,
        related_data_slice: {
          symbol: feedbackSliceSymbol.trim() || null,
          time_window: feedbackSliceWindow,
          severity: feedbackSliceSeverity,
        },
        dry_run: false,
      });
      setLastActionResult(data || null);
      toast.success(data?.message || "Feedback kaydedildi");
      setFeedbackReason("");
      setFeedbackSampleLink("");
      await Promise.all([loadFeedbackForStrategy(feedbackStrategyId), loadOverview(), loadPolicySuggestions()]);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Feedback kaydı başarısız");
    } finally {
      setFeedbackSubmitting(false);
    }
  };

  const triggerModelUpdate = async () => {
    if (!feedbackStrategyId) {
      toast.error("Model update için strategy seçin");
      return;
    }
    if (modelUpdateReason.trim().length < 3) {
      toast.error("Model update reason zorunlu");
      return;
    }
    setModelUpdateSubmitting(true);
    try {
      const { data } = await apiClient.post(`/admin/futures/strategy/${feedbackStrategyId}/trigger-model-update`, {
        reason: modelUpdateReason.trim(),
        dataset_version: Number(feedbackVersion || 0),
        dry_run: false,
      });
      setLastActionResult(data || null);
      toast.success(data?.message || "Model update queued");
      await loadModelUpdateStatus(feedbackStrategyId);
    } catch (error) {
      const message = error?.response?.data?.message || error?.response?.data?.detail || "Model update tetiklenemedi";
      toast.error(message);
    } finally {
      setModelUpdateSubmitting(false);
    }
  };

  const exportTimeline = async () => {
    if (!feedbackStrategyId) {
      toast.error("Export için strategy seçin");
      return;
    }
    setExporting(true);
    try {
      if (exportFormat === "json") {
        const { data } = await apiClient.get(`/admin/futures/strategy/${feedbackStrategyId}/timeline-export`, { params: { format: "json" } });
        setExportSummary(data?.state_snapshot || null);
        const blob = new Blob([JSON.stringify(data?.items || [], null, 2)], { type: "application/json" });
        const url = window.URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `${feedbackStrategyId}_timeline.json`;
        anchor.click();
        window.URL.revokeObjectURL(url);
      } else {
        const response = await apiClient.get(`/admin/futures/strategy/${feedbackStrategyId}/timeline-export`, {
          params: { format: "csv" },
          responseType: "blob",
        });
        const url = window.URL.createObjectURL(response.data);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `${feedbackStrategyId}_timeline.csv`;
        anchor.click();
        window.URL.revokeObjectURL(url);
        setExportSummary({ strategy_id: feedbackStrategyId, format: "csv" });
      }
      toast.success("Timeline export hazırlandı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Timeline export başarısız");
    } finally {
      setExporting(false);
    }
  };

  const submitRollbackRequest = async (decisionInput = null) => {
    if (!feedbackStrategyId || !selectedSnapshotTraceId) {
      toast.error("Rollback request için strategy ve snapshot seçin");
      return;
    }
    const reasonValue = String(decisionInput?.reason || rollbackRequestReason || "").trim();
    if (reasonValue.length < 3) {
      toast.error("Rollback request reason zorunlu");
      return;
    }
    setRollbackRequestSubmitting(true);
    try {
      const { data } = await apiClient.post(`/admin/futures/strategy/${feedbackStrategyId}/rollback-request`, {
        reason: reasonValue,
        snapshot_trace_id: selectedSnapshotTraceId,
      });
      setLastActionResult(data || null);
      toast.success(data?.message || "Rollback request oluşturuldu");
      setRollbackRequestReason("");
      await loadApprovalRequests();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Rollback request başarısız");
    } finally {
      setRollbackRequestSubmitting(false);
    }
  };

  const submitApprovalDecision = async (requestId, decision) => {
    if (approvalDecisionReason.trim().length < 3) {
      toast.error("Approval decision reason zorunlu");
      return;
    }
    setApprovalSubmitting(true);
    try {
      const endpoint = decision === "approve" ? "approve" : "reject";
      const { data } = await apiClient.post(`/admin/futures/strategy/approval-requests/${requestId}/${endpoint}`, {
        reason: approvalDecisionReason.trim(),
      });
      setLastActionResult(data || null);
      toast.success(data?.message || "Approval kararı kaydedildi");

      const targetRequest = approvalRequests.find((item) => String(item?.request_id || "") === String(requestId));
      if (decision === "approve" && data?.status !== "rejected") {
        activatePostActionMonitor({
          actionType: "approval_approve",
          actionLabel: "approval_approve",
          strategyId: data?.state_snapshot?.strategy_id || targetRequest?.strategy_id,
          result: data,
        });
      }

      await Promise.all([loadApprovalRequests(), loadOverview(), loadRollbackSnapshots(feedbackStrategyId)]);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Approval kararı başarısız");
    } finally {
      setApprovalSubmitting(false);
    }
  };

  return (
    <section className="space-y-4" data-testid="strategy-control-governance-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="strategy-control-governance-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-black" data-testid="strategy-control-governance-title">
          Strategy Control + Governance System
        </h2>
        <p className="mt-2 text-sm text-black/80" data-testid="strategy-control-governance-description">
          Faz-2 kapsamı: rollout/shadow kontrolü, güvenli bulk operasyon (pause/resume/throttle) ve tek-adım rollback.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3 border border-black/30 bg-orange-100 p-4" data-testid="strategy-control-governance-toolbar">
        <Button className="border border-black bg-black text-orange-400 hover:bg-zinc-800" onClick={loadAll} data-testid="strategy-control-governance-refresh-button">
          Yenile
        </Button>
        <p className="text-sm text-black" data-testid="strategy-control-governance-loading-text">loading: {String(loading)}</p>
        <p className="text-sm text-black" data-testid="strategy-control-governance-phase-scope-text">scope: {overviewPayload?.phase_scope || "phase_2_rollout_bulk_rollback"}</p>
      </div>

      {loading && <div className="border border-black/25 bg-orange-50 p-4 text-sm" data-testid="strategy-control-governance-loading-state">Strategy Control paneli yükleniyor...</div>}
      {!loading && Boolean(errorMessage) && (
        <div className="border border-red-700 bg-red-100 p-4 text-sm text-red-900" data-testid="strategy-control-governance-error-state">
          Hata: {errorMessage}
        </div>
      )}

      {!loading && !errorMessage && (
        <>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4" data-testid="strategy-control-governance-summary-grid">
            <MetricCard testId="strategy-control-summary-strategy-count" title="Strategies" value={strategyCount} />
            <MetricCard testId="strategy-control-summary-disabled" title="Disabled" value={disabledCount} />
            <MetricCard testId="strategy-control-summary-throttled" title="Throttled" value={throttledCount} />
            <MetricCard testId="strategy-control-summary-drift" title="Drift Alerts" value={driftCount} />
          </div>

          <Tabs value={activeTab} onValueChange={setActiveTab} data-testid="strategy-control-governance-tabs-root">
            <TabsList className="h-auto flex-wrap justify-start gap-1 bg-orange-200 p-1" data-testid="strategy-control-governance-tabs-list">
              {TAB_ITEMS.map((tab) => (
                <TabsTrigger key={tab.key} value={tab.key} className="border border-black/20 data-[state=active]:bg-black data-[state=active]:text-orange-300" data-testid={`strategy-control-tab-trigger-${tab.key}`}>
                  {tab.label}
                </TabsTrigger>
              ))}
            </TabsList>

            <TabsContent value="overview" data-testid="strategy-control-tab-overview">
              <StrategyTable rows={strategies} onOpenDetail={openDetail} onRunAction={openActionModal} compact selectedStrategyIds={selectedStrategyIds} onToggleStrategy={null} />
            </TabsContent>

            <TabsContent value="universe_control" data-testid="strategy-control-tab-universe-control">
              <PlaceholderPanel testId="strategy-control-universe-control-placeholder" title="Universe Control" reason="Bu iterasyonda odak rollout/bulk/rollback; universe kapsamı değişmedi." />
            </TabsContent>

            <TabsContent value="rollout" data-testid="strategy-control-tab-rollout">
              <div className="space-y-3 border border-black/25 bg-orange-100 p-4" data-testid="strategy-control-rollout-panel">
                <h3 className="text-base font-semibold" data-testid="strategy-control-rollout-title">Rollout / Shadow Control</h3>

                <div className="grid gap-3 md:grid-cols-2" data-testid="strategy-control-rollout-controls-grid">
                  <div className="space-y-2" data-testid="strategy-control-rollout-strategy-selector-block">
                    <p className="text-xs" data-testid="strategy-control-rollout-strategy-selector-label">Strategy</p>
                    <select className="h-10 rounded border border-black/40 bg-white px-3 text-sm" value={rolloutStrategyId} onChange={(e) => setRolloutStrategyId(e.target.value)} data-testid="strategy-control-rollout-strategy-select">
                      {strategies.map((row) => (
                        <option key={row.strategy_id} value={row.strategy_id}>{row.strategy_id}</option>
                      ))}
                    </select>
                    <Button size="sm" variant="outline" onClick={loadRolloutPrecheck} data-testid="strategy-control-rollout-precheck-button">Pre-check Çalıştır</Button>
                  </div>

                  <div className="space-y-2" data-testid="strategy-control-rollout-operation-block">
                    <p className="text-xs" data-testid="strategy-control-rollout-operation-label">Operation</p>
                    <select className="h-10 rounded border border-black/40 bg-white px-3 text-sm" value={rolloutOperation} onChange={(e) => setRolloutOperation(e.target.value)} data-testid="strategy-control-rollout-operation-select">
                      <option value="promote_shadow">Promote Shadow</option>
                      <option value="rollout">Apply Rollout %</option>
                      <option value="rollback">Rollback Last Action</option>
                    </select>
                    {rolloutOperation === "rollout" && (
                      <select className="h-10 rounded border border-black/40 bg-white px-3 text-sm" value={rolloutPercentage} onChange={(e) => setRolloutPercentage(Number(e.target.value))} data-testid="strategy-control-rollout-percentage-select">
                        <option value={10}>10%</option>
                        <option value={25}>25%</option>
                        <option value={50}>50%</option>
                        <option value={100}>100%</option>
                      </select>
                    )}
                  </div>
                </div>

                <Textarea value={rolloutReason} onChange={(e) => setRolloutReason(e.target.value)} placeholder="Rollout nedeni" className="border-black/40" data-testid="strategy-control-rollout-reason-input" />
                <Input value={rolloutConfirm} onChange={(e) => setRolloutConfirm(e.target.value)} placeholder={`Onay ifadesi: ${ROLLOUT_CONFIRM_MAP[rolloutOperation]}`} className="border-black/40" data-testid="strategy-control-rollout-confirm-input" />
                <Button
                  onClick={() =>
                    openDecisionModal({
                      mode: "rollout",
                      actionType: rolloutOperation,
                      strategyId: rolloutStrategyId,
                      title: `Rollout Decision · ${rolloutOperation}`,
                      confirmRequired: true,
                      confirmPlaceholder: `Onay ifadesi: ${ROLLOUT_CONFIRM_MAP[rolloutOperation]}`,
                      defaultReason: rolloutReason || `rollout_${rolloutOperation}_${rolloutStrategyId}`,
                      params: {
                        rollout_percentage: rolloutOperation === "rollout" ? Number(rolloutPercentage) : null,
                        operation: rolloutOperation,
                      },
                    })
                  }
                  disabled={rolloutSubmitting}
                  className="border border-black bg-black text-orange-300"
                  data-testid="strategy-control-rollout-submit-button"
                >
                  {rolloutSubmitting ? "Çalışıyor..." : "Rollout Aksiyonunu Uygula"}
                </Button>
                <Button
                  variant="outline"
                  onClick={() =>
                    openDecisionModal({
                      mode: "threshold_placeholder",
                      actionType: "threshold_change",
                      strategyId: rolloutStrategyId,
                      title: "Threshold Edit (Placeholder)",
                      confirmRequired: false,
                      defaultReason: `threshold_placeholder_${rolloutStrategyId}`,
                      params: { threshold_delta: 0.0 },
                    })
                  }
                  data-testid="strategy-control-threshold-placeholder-open-button"
                >
                  Threshold Edit (Placeholder)
                </Button>

                {selectedRolloutStrategy && (
                  <div className="rounded border border-black/20 bg-orange-50 p-2" data-testid="strategy-control-rollout-selected-state-card">
                    <p className="text-xs" data-testid="strategy-control-rollout-selected-state-strategy">strategy={selectedRolloutStrategy.strategy_id}</p>
                    <p className="text-xs" data-testid="strategy-control-rollout-selected-state-mode">mode={selectedRolloutStrategy.rollout_mode} percentage={selectedRolloutStrategy.rollout_percentage}%</p>
                    <p className="text-xs" data-testid="strategy-control-rollout-selected-state-health">health={selectedRolloutStrategy.health_score} error_rate={selectedRolloutStrategy.error_rate_pct}%</p>
                  </div>
                )}

                {rolloutPrecheck && (
                  <div className="rounded border border-black/20 bg-orange-50 p-3" data-testid="strategy-control-rollout-precheck-result-card">
                    <p className="text-xs font-semibold" data-testid="strategy-control-rollout-precheck-status">precheck_status={rolloutPrecheck.status}</p>
                    <p className="text-xs" data-testid="strategy-control-rollout-precheck-health">health_ok={String(rolloutPrecheck?.checks?.health?.ok)}</p>
                    <p className="text-xs" data-testid="strategy-control-rollout-precheck-error">recent_error_ok={String(rolloutPrecheck?.checks?.recent_error?.ok)}</p>
                    <p className="text-xs" data-testid="strategy-control-rollout-precheck-drift">drift_ok={String(rolloutPrecheck?.checks?.drift?.ok)}</p>
                    <p className="text-xs" data-testid="strategy-control-rollout-precheck-checklist">checklist_ok={String(rolloutPrecheck?.checks?.checklist?.ok)}</p>
                  </div>
                )}

                {rolloutResult && (
                  <div className="rounded border border-black/20 bg-orange-50 p-3" data-testid="strategy-control-rollout-result-card">
                    <p className="text-xs" data-testid="strategy-control-rollout-result-status">status={rolloutResult.status}</p>
                    <p className="text-xs" data-testid="strategy-control-rollout-result-trace">trace_id={rolloutResult.trace_id}</p>
                    <p className="text-xs" data-testid="strategy-control-rollout-result-message">message={rolloutResult.message}</p>
                    {rolloutResult?.auto_rollback?.triggered && (
                      <p className="text-xs text-red-900" data-testid="strategy-control-rollout-result-auto-rollback-info">
                        auto_rollback_reason={(rolloutResult?.auto_rollback?.reason || []).join(";")} · thresholds=health&lt;50,error&gt;3%
                      </p>
                    )}
                  </div>
                )}
              </div>
            </TabsContent>

            <TabsContent value="strategy_governance" data-testid="strategy-control-tab-strategy-governance">
              <div className="mb-3 space-y-2 rounded border border-black/25 bg-orange-100 p-4" data-testid="strategy-control-bulk-panel">
                <h3 className="text-base font-semibold" data-testid="strategy-control-bulk-title">Bulk Operation (safe scope)</h3>
                <p className="text-xs" data-testid="strategy-control-bulk-scope-note">Kapsam bilinçli sınırlı: pause / resume / throttle. Disable/Decommission bulk yok.</p>
                <div className="grid gap-2 md:grid-cols-2" data-testid="strategy-control-bulk-controls-grid">
                  <select className="h-10 rounded border border-black/40 bg-white px-3 text-sm" value={bulkAction} onChange={(e) => setBulkAction(e.target.value)} data-testid="strategy-control-bulk-action-select">
                    <option value="pause">pause</option>
                    <option value="resume">resume</option>
                    <option value="throttle">throttle</option>
                  </select>
                  {bulkAction === "throttle" && (
                    <select className="h-10 rounded border border-black/40 bg-white px-3 text-sm" value={bulkThrottleLevel} onChange={(e) => setBulkThrottleLevel(e.target.value)} data-testid="strategy-control-bulk-throttle-level-select">
                      <option value="L1">L1</option>
                      <option value="L2">L2</option>
                      <option value="L3">L3</option>
                    </select>
                  )}
                </div>
                <Textarea value={bulkReason} onChange={(e) => setBulkReason(e.target.value)} placeholder="Bulk action nedeni" className="border-black/40" data-testid="strategy-control-bulk-reason-input" />
                <Input value={bulkConfirm} onChange={(e) => setBulkConfirm(e.target.value)} placeholder={`Onay ifadesi: ${BULK_CONFIRM_MAP[bulkAction]}`} className="border-black/40" data-testid="strategy-control-bulk-confirm-input" />
                <Button onClick={submitBulkAction} disabled={bulkSubmitting} className="border border-black bg-black text-orange-300" data-testid="strategy-control-bulk-submit-button">
                  {bulkSubmitting ? "Bulk çalışıyor..." : "Bulk Action Uygula"}
                </Button>
                {bulkResult && (
                  <div className="rounded border border-black/20 bg-orange-50 p-2" data-testid="strategy-control-bulk-result-breakdown-panel">
                    <p className="text-xs" data-testid="strategy-control-bulk-result-text">{bulkResult.message}</p>
                    <p className="text-xs" data-testid="strategy-control-bulk-result-summary">
                      success={bulkResult?.state_snapshot?.success_count ?? 0} · failed={bulkResult?.state_snapshot?.rejected_count ?? 0} · skipped={bulkResult?.state_snapshot?.skipped_count ?? 0}
                    </p>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setBulkBreakdownExpanded((prev) => !prev)}
                      className="mt-2"
                      data-testid="strategy-control-bulk-breakdown-toggle-button"
                    >
                      {bulkBreakdownExpanded ? "Bulk Sonuç Detayını Gizle" : "Bulk Sonuç Detayını Aç"}
                    </Button>

                    {bulkBreakdownExpanded && (
                      <div className="mt-2 space-y-2" data-testid="strategy-control-bulk-breakdown-expanded">
                        <BulkBreakdownSection bucketKey="success" rows={bulkResultBuckets.success} />
                        <BulkBreakdownSection bucketKey="failed" rows={bulkResultBuckets.failed} />
                        <BulkBreakdownSection bucketKey="skipped" rows={bulkResultBuckets.skipped} />
                      </div>
                    )}
                  </div>
                )}
              </div>

              <StrategyTable rows={strategies} onOpenDetail={openDetail} onRunAction={openActionModal} selectedStrategyIds={selectedStrategyIds} onToggleStrategy={toggleStrategySelect} />
            </TabsContent>

            <TabsContent value="capital_governance" data-testid="strategy-control-tab-capital-governance">
              <div className="grid gap-3 md:grid-cols-2" data-testid="strategy-control-capital-summary-grid">
                <MetricCard testId="strategy-control-capital-equity" title="Portfolio Equity" value={capitalPayload?.budget?.portfolio_capital_registry?.portfolio_equity ?? 0} />
                <MetricCard testId="strategy-control-capital-risk-state" title="Global Risk" value={`${capitalPayload?.globalRisk?.risk_state || "NORMAL"} (${capitalPayload?.globalRisk?.global_risk_score ?? 0})`} />
              </div>
              <div className="mt-3 border border-black/25 bg-orange-100 p-4" data-testid="strategy-control-capital-drift-panel">
                <h3 className="text-base font-semibold" data-testid="strategy-control-capital-drift-title">Capital Drift Events</h3>
                {(capitalPayload?.drift?.capital_drift_events || []).length === 0 && <p className="mt-2 text-sm" data-testid="strategy-control-capital-drift-empty">No data yet: aktif capital drift eventi bulunmuyor.</p>}
                {(capitalPayload?.drift?.capital_drift_events || []).map((item, index) => (
                  <p key={`${item?.strategy_id}-${index}`} className="mt-1 text-xs" data-testid={`strategy-control-capital-drift-item-${index}`}>
                    {item?.strategy_id}: severity={item?.drift_severity} reason={(item?.reasons || []).join(",")}
                  </p>
                ))}
              </div>
            </TabsContent>

            <TabsContent value="drift_action_center" data-testid="strategy-control-tab-drift-action-center">
              <div className="space-y-3 border border-black/25 bg-orange-100 p-4" data-testid="strategy-control-drift-action-center-panel">
                <h3 className="text-base font-semibold" data-testid="strategy-control-drift-action-center-title">Drift Action Center</h3>
                <p className="mt-1 text-xs" data-testid="strategy-control-drift-action-center-reason">Ack/Mute/Ignore/Disable/Retrain aksiyonları reason + trace + state_snapshot + audit ile aktiftir.</p>

                {driftLoading && <p className="text-sm" data-testid="strategy-control-drift-loading">Drift alarmları yükleniyor...</p>}
                {!driftLoading && driftAlerts.length === 0 && <p className="text-sm" data-testid="strategy-control-drift-empty">No data yet: aktif drift alarmı bulunmuyor.</p>}

                {driftAlerts.map((alert, index) => (
                  <div key={alert.alert_id} className="rounded border border-black/20 bg-orange-50 p-3" data-testid={`strategy-control-drift-alert-card-${index}`}>
                    <p className="text-xs font-semibold" data-testid={`strategy-control-drift-alert-strategy-${index}`}>{alert.strategy_id}</p>
                    <p className="text-xs" data-testid={`strategy-control-drift-alert-status-${index}`}>status={alert.status} severity={alert.severity}</p>
                    <p className="text-xs" data-testid={`strategy-control-drift-alert-reasons-${index}`}>reasons={(alert.trigger_reason || []).join(",") || "n/a"}</p>
                    <p className="text-xs font-semibold" data-testid={`strategy-control-drift-alert-recommended-${index}`}>
                      Recommended={alert?.recommended_action?.type || "ACK"} ({alert?.recommended_action?.confidence || 0}%) · {alert?.recommended_action?.reason || "n/a"}
                    </p>
                    <p className="text-xs" data-testid={`strategy-control-drift-alert-mute-${index}`}>muted_until={alert.muted_until || "-"}</p>
                    <div className="mt-2 flex flex-wrap gap-2" data-testid={`strategy-control-drift-alert-actions-${index}`}>
                      <Button size="sm" variant="outline" onClick={() => openDriftActionModal("ack", alert)} data-testid={`strategy-control-drift-ack-button-${index}`}>Ack</Button>
                      <Button size="sm" variant="outline" onClick={() => openDriftActionModal("mute", alert)} data-testid={`strategy-control-drift-mute-button-${index}`}>Mute</Button>
                      <Button size="sm" variant="outline" onClick={() => openDriftActionModal("ignore", alert)} data-testid={`strategy-control-drift-ignore-button-${index}`}>Ignore</Button>
                      <Button size="sm" variant="outline" className="border-red-800 text-red-900" onClick={() => openDriftActionModal("disable_strategy", alert)} data-testid={`strategy-control-drift-disable-button-${index}`}>Disable Strategy</Button>
                      <Button size="sm" variant="outline" onClick={() => openDriftActionModal("retrain", alert)} data-testid={`strategy-control-drift-retrain-button-${index}`}>Retrain</Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="border-black bg-black text-orange-300"
                        onClick={() => {
                          const recommended = String(alert?.recommended_action?.type || "ACK").toUpperCase();
                          const actionMap = {
                            ACK: "ack",
                            MUTE: "mute",
                            DISABLE: "disable_strategy",
                            RETRAIN: "retrain",
                          };
                          const actionType = actionMap[recommended] || "ack";
                          const recommendationReason = String(alert?.recommended_action?.reason || "").trim();
                          const suggestedReason = recommendationReason
                            ? `recommended_${recommended.toLowerCase()} · ${recommendationReason}`
                            : `recommended_${recommended.toLowerCase()}_${alert?.strategy_id || "strategy"}`;
                          openDriftActionModal(actionType, alert, { reasonPrefill: suggestedReason });
                        }}
                        data-testid={`strategy-control-drift-apply-recommended-button-${index}`}
                      >
                        Apply Recommended
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          openPolicyApplyHook({
                            source: "drift_card",
                            ruleText: alert?.recommended_action?.reason || "drift_policy_suggestion",
                            alert,
                          })
                        }
                        data-testid={`strategy-control-drift-apply-via-policy-button-${index}`}
                      >
                        Apply via Policy
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => openDriftDeepLink(alert)} data-testid={`strategy-control-drift-open-policy-button-${index}`}>Open Policy</Button>
                    </div>
                  </div>
                ))}

                {driftResult && (
                  <div className="rounded border border-black/20 bg-orange-50 p-3" data-testid="strategy-control-drift-result-card">
                    <p className="text-xs" data-testid="strategy-control-drift-result-status">status={driftResult.status}</p>
                    <p className="text-xs" data-testid="strategy-control-drift-result-trace">trace_id={driftResult.trace_id}</p>
                    <p className="text-xs" data-testid="strategy-control-drift-result-message">message={driftResult.message}</p>
                    <p className="text-xs" data-testid="strategy-control-drift-result-deep-link">deep_link_tab={driftResult?.deep_link?.target_tab || "-"}</p>
                  </div>
                )}
              </div>
            </TabsContent>

            <TabsContent value="audit_history" data-testid="strategy-control-tab-audit-history">
              <div className="space-y-3" data-testid="strategy-control-audit-history-panel">
                <div className="border border-black/25 bg-orange-100 p-4" data-testid="strategy-control-audit-history-last-action-panel">
                  <h3 className="text-base font-semibold" data-testid="strategy-control-audit-history-title">Last Action Result</h3>
                  {!lastActionResult && <p className="mt-2 text-sm" data-testid="strategy-control-audit-history-empty">No data yet: bu oturumda henüz aksiyon çalıştırılmadı.</p>}
                  {lastActionResult && (
                    <div className="mt-2 rounded border border-black/20 bg-orange-50 p-3" data-testid="strategy-control-audit-history-last-action-card">
                      <p className="text-xs" data-testid="strategy-control-audit-history-last-action-status">status={lastActionResult.status}</p>
                      <p className="text-xs" data-testid="strategy-control-audit-history-last-action-trace">trace_id={lastActionResult.trace_id}</p>
                      <p className="text-xs" data-testid="strategy-control-audit-history-last-action-message">message={lastActionResult.message}</p>
                    </div>
                  )}
                </div>

                <div className="border border-black/25 bg-orange-100 p-4" data-testid="strategy-control-post-action-monitor-panel">
                  <h3 className="text-base font-semibold" data-testid="strategy-control-post-action-monitor-title">Last Action Impact</h3>
                  {!postActionMonitor?.strategyId && (
                    <p className="mt-2 text-xs" data-testid="strategy-control-post-action-monitor-empty">
                      No data yet: rollout/disable/rollback/drift-disable/approval-approve sonrası izleme burada görünür.
                    </p>
                  )}
                  {postActionMonitor?.strategyId && (
                    <div className="mt-2 rounded border border-black/20 bg-orange-50 p-3" data-testid="strategy-control-post-action-monitor-card">
                      <p className="text-xs" data-testid="strategy-control-post-action-monitor-phase">
                        phase={postActionMonitor.active ? "active" : "passive"} · remaining={postActionRemainingSeconds}s
                      </p>
                      <p className="text-xs" data-testid="strategy-control-post-action-monitor-action">
                        action={postActionMonitor.actionLabel || postActionMonitor.actionType} · strategy={postActionMonitor.strategyId}
                      </p>
                      <p className="text-xs" data-testid="strategy-control-post-action-monitor-trace">trace_id={postActionMonitor.traceId || "-"}</p>
                      <p className="text-xs" data-testid="strategy-control-post-action-monitor-refresh-at">
                        refreshed_at={postActionMonitor?.lastRefreshedAt ? new Date(postActionMonitor.lastRefreshedAt).toISOString() : "-"}
                      </p>
                      <div className="mt-2 grid gap-2 md:grid-cols-3" data-testid="strategy-control-post-action-monitor-delta-grid">
                        <p className="text-xs" data-testid="strategy-control-post-action-monitor-health-delta">health_delta={toSignedDelta(postActionDeltas.health)}</p>
                        <p className="text-xs" data-testid="strategy-control-post-action-monitor-error-delta">error_delta={toSignedDelta(postActionDeltas.error)}</p>
                        <p className="text-xs" data-testid="strategy-control-post-action-monitor-risk-delta">risk_delta={toSignedDelta(postActionDeltas.risk)}</p>
                      </div>
                      <p className="mt-2 text-xs" data-testid="strategy-control-post-action-monitor-before-summary">
                        before={buildSnapshotSummary(postActionMonitor?.baselineBefore)}
                      </p>
                      <p className="text-xs" data-testid="strategy-control-post-action-monitor-after-summary">
                        after_at_action={buildSnapshotSummary(postActionMonitor?.baselineAfter)}
                      </p>
                      <p className="text-xs" data-testid="strategy-control-post-action-monitor-current-summary">
                        current={buildSnapshotSummary(postActionMonitor?.currentSnapshot)}
                      </p>
                    </div>
                  )}
                </div>

                <div className="border border-black/25 bg-orange-100 p-4" data-testid="strategy-control-feedback-loop-panel">
                  <h3 className="text-base font-semibold" data-testid="strategy-control-feedback-loop-title">Feedback Loop (False Allow/Reject Correction)</h3>
                  <div className="mt-2 grid gap-2 md:grid-cols-2" data-testid="strategy-control-feedback-loop-selectors-grid">
                    <select className="h-10 rounded border border-black/40 bg-white px-3 text-sm" value={feedbackStrategyId} onChange={(e) => setFeedbackStrategyId(e.target.value)} data-testid="strategy-control-feedback-strategy-select">
                      {strategies.map((row) => (
                        <option key={row.strategy_id} value={row.strategy_id}>{row.strategy_id}</option>
                      ))}
                    </select>
                    <select className="h-10 rounded border border-black/40 bg-white px-3 text-sm" value={feedbackDriftAlertId} onChange={(e) => setFeedbackDriftAlertId(e.target.value)} data-testid="strategy-control-feedback-drift-alert-select">
                      {(driftAlerts.filter((item) => item.strategy_id === feedbackStrategyId)).map((item) => (
                        <option key={item.alert_id} value={item.alert_id}>{item.alert_id}</option>
                      ))}
                    </select>
                    <select className="h-10 rounded border border-black/40 bg-white px-3 text-sm" value={feedbackLabel} onChange={(e) => setFeedbackLabel(e.target.value)} data-testid="strategy-control-feedback-label-select">
                      <option value="false_allow">false_allow</option>
                      <option value="false_reject">false_reject</option>
                      <option value="correct">correct</option>
                    </select>
                    <select className="h-10 rounded border border-black/40 bg-white px-3 text-sm" value={feedbackTaxonomy} onChange={(e) => setFeedbackTaxonomy(e.target.value)} data-testid="strategy-control-feedback-taxonomy-select">
                      <option value="threshold_too_strict">threshold_too_strict</option>
                      <option value="threshold_too_loose">threshold_too_loose</option>
                      <option value="feature_drift">feature_drift</option>
                      <option value="data_quality">data_quality</option>
                    </select>
                  </div>

                  <Textarea value={feedbackReason} onChange={(e) => setFeedbackReason(e.target.value)} placeholder="Correction reason" className="mt-2 border-black/40" data-testid="strategy-control-feedback-reason-input" />
                  <Input value={feedbackSampleLink} onChange={(e) => setFeedbackSampleLink(e.target.value)} placeholder="Sample link (opsiyonel)" className="mt-2 border-black/40" data-testid="strategy-control-feedback-sample-link-input" />

                  <div className="mt-2 grid gap-2 md:grid-cols-3" data-testid="strategy-control-feedback-slice-grid">
                    <Input value={feedbackSliceSymbol} onChange={(e) => setFeedbackSliceSymbol(e.target.value)} placeholder="Slice symbol" className="border-black/40" data-testid="strategy-control-feedback-slice-symbol-input" />
                    <select className="h-10 rounded border border-black/40 bg-white px-3 text-sm" value={feedbackSliceWindow} onChange={(e) => setFeedbackSliceWindow(e.target.value)} data-testid="strategy-control-feedback-slice-window-select">
                      <option value="1h">1h</option>
                      <option value="24h">24h</option>
                      <option value="7d">7d</option>
                    </select>
                    <select className="h-10 rounded border border-black/40 bg-white px-3 text-sm" value={feedbackSliceSeverity} onChange={(e) => setFeedbackSliceSeverity(e.target.value)} data-testid="strategy-control-feedback-slice-severity-select">
                      <option value="LOW">LOW</option>
                      <option value="MEDIUM">MEDIUM</option>
                      <option value="HIGH">HIGH</option>
                    </select>
                  </div>

                  <div className="mt-2 flex flex-wrap items-center gap-2" data-testid="strategy-control-feedback-actions-row">
                    <Button onClick={submitFeedbackLabel} disabled={feedbackSubmitting} className="border border-black bg-black text-orange-300" data-testid="strategy-control-feedback-submit-button">
                      {feedbackSubmitting ? "Kaydediliyor..." : "Feedback Kaydet"}
                    </Button>
                    <p className="text-xs" data-testid="strategy-control-feedback-version-text">dataset_version={feedbackVersion}</p>
                  </div>

                  <div className="mt-2 rounded border border-black/20 bg-orange-50 p-2" data-testid="strategy-control-feedback-list-panel">
                    <p className="text-xs font-semibold" data-testid="strategy-control-feedback-list-title">Feedback Log (immutable)</p>
                    {feedbackItems.length === 0 && <p className="text-xs" data-testid="strategy-control-feedback-list-empty">No data yet: bu strategy için feedback yok.</p>}
                    {feedbackItems.slice(0, 8).map((item, index) => (
                      <p key={item.entry_id} className="text-xs" data-testid={`strategy-control-feedback-list-item-${index}`}>
                        v{item.dataset_version} · {item.corrected_label} · taxonomy={item.reason_taxonomy} · drift={item.drift_alert_id}
                      </p>
                    ))}
                  </div>
                </div>

                <div className="border border-black/25 bg-orange-100 p-4" data-testid="strategy-control-model-update-panel">
                  <h3 className="text-base font-semibold" data-testid="strategy-control-model-update-title">Model Update Trigger</h3>
                  <Input value={modelUpdateReason} onChange={(e) => setModelUpdateReason(e.target.value)} placeholder="Model update reason" className="mt-2 border-black/40" data-testid="strategy-control-model-update-reason-input" />
                  <div className="mt-2 flex flex-wrap items-center gap-2" data-testid="strategy-control-model-update-actions-row">
                    <Button onClick={triggerModelUpdate} disabled={modelUpdateSubmitting} className="border border-black bg-black text-orange-300" data-testid="strategy-control-model-update-trigger-button">
                      {modelUpdateSubmitting ? "Tetikleniyor..." : "Model Update Trigger"}
                    </Button>
                    <Button variant="outline" onClick={() => loadModelUpdateStatus(feedbackStrategyId)} data-testid="strategy-control-model-update-refresh-button">Status Yenile</Button>
                  </div>
                  <div className="mt-2 rounded border border-black/20 bg-orange-50 p-2" data-testid="strategy-control-model-update-status-card">
                    <p className="text-xs" data-testid="strategy-control-model-update-status-current">current_status={modelUpdateStatus?.current_job?.status || "none"}</p>
                    <p className="text-xs" data-testid="strategy-control-model-update-status-job-id">job_id={modelUpdateStatus?.current_job?.job_id || "-"}</p>
                    <p className="text-xs" data-testid="strategy-control-model-update-status-history-count">history_count={(modelUpdateStatus?.history || []).length}</p>
                  </div>
                </div>

                <div className="border border-black/25 bg-orange-100 p-4" data-testid="strategy-control-export-panel">
                  <h3 className="text-base font-semibold" data-testid="strategy-control-export-title">Timeline Export (Drift + Action + Feedback)</h3>
                  <div className="mt-2 flex flex-wrap items-center gap-2" data-testid="strategy-control-export-actions-row">
                    <select className="h-10 rounded border border-black/40 bg-white px-3 text-sm" value={exportFormat} onChange={(e) => setExportFormat(e.target.value)} data-testid="strategy-control-export-format-select">
                      <option value="json">JSON</option>
                      <option value="csv">CSV</option>
                    </select>
                    <Button onClick={exportTimeline} disabled={exporting} className="border border-black bg-black text-orange-300" data-testid="strategy-control-export-download-button">
                      {exporting ? "Hazırlanıyor..." : "Export İndir"}
                    </Button>
                  </div>
                  {exportSummary && <p className="mt-2 text-xs" data-testid="strategy-control-export-summary-text">export_summary={JSON.stringify(exportSummary)}</p>}
                </div>

                <div className="border border-black/25 bg-orange-100 p-4" data-testid="strategy-control-rollback-snapshot-panel">
                  <h3 className="text-base font-semibold" data-testid="strategy-control-rollback-snapshot-title">Snapshot Rollback (Request Mode)</h3>
                  <p className="text-xs" data-testid="strategy-control-rollback-snapshot-note">Tek strategy scope, bulk rollback yok. Request 24h içinde expire olur.</p>
                  {rollbackSnapshotsLoading && <p className="text-xs" data-testid="strategy-control-rollback-snapshot-loading">Snapshotlar yükleniyor...</p>}
                  {!rollbackSnapshotsLoading && rollbackSnapshots.length === 0 && <p className="text-xs" data-testid="strategy-control-rollback-snapshot-empty">No data yet: rollback snapshot bulunmuyor.</p>}
                  {!rollbackSnapshotsLoading && rollbackSnapshots.length > 0 && (
                    <div className="mt-2 space-y-1" data-testid="strategy-control-rollback-snapshot-list">
                      {rollbackSnapshots.slice(0, 8).map((item, index) => (
                        <label key={item.snapshot_trace_id} className="flex items-start gap-2 text-xs" data-testid={`strategy-control-rollback-snapshot-item-${index}`}>
                          <input type="radio" name="rollback_snapshot" value={item.snapshot_trace_id} checked={selectedSnapshotTraceId === item.snapshot_trace_id} onChange={(e) => setSelectedSnapshotTraceId(e.target.value)} data-testid={`strategy-control-rollback-snapshot-radio-${index}`} />
                          <span>
                            {item.timestamp} · {item.action_type} · trace={item.snapshot_trace_id}
                            <br />
                            diff={JSON.stringify(item.diff_preview)}
                          </span>
                        </label>
                      ))}
                    </div>
                  )}
                  <Textarea value={rollbackRequestReason} onChange={(e) => setRollbackRequestReason(e.target.value)} placeholder="Rollback request reason" className="mt-2 border-black/40" data-testid="strategy-control-rollback-request-reason-input" />
                  <Button
                    onClick={() =>
                      openDecisionModal({
                        mode: "rollback_request",
                        actionType: "rollback",
                        strategyId: feedbackStrategyId,
                        title: "Rollback Request Decision",
                        confirmRequired: false,
                        defaultReason: rollbackRequestReason || `rollback_request_${feedbackStrategyId}`,
                        params: { snapshot_trace_id: selectedSnapshotTraceId },
                      })
                    }
                    disabled={rollbackRequestSubmitting}
                    className="mt-2 border border-black bg-black text-orange-300"
                    data-testid="strategy-control-rollback-request-submit-button"
                  >
                    {rollbackRequestSubmitting ? "Oluşturuluyor..." : "Rollback Request Oluştur"}
                  </Button>
                </div>

                <div className="border border-black/25 bg-orange-100 p-4" data-testid="strategy-control-approval-workflow-panel">
                  <h3 className="text-base font-semibold" data-testid="strategy-control-approval-workflow-title">Approval Workflow (requester → super_admin)</h3>
                  <Input value={approvalDecisionReason} onChange={(e) => setApprovalDecisionReason(e.target.value)} placeholder="Approval decision reason" className="mt-2 border-black/40" data-testid="strategy-control-approval-decision-reason-input" />
                  {approvalLoading && <p className="text-xs" data-testid="strategy-control-approval-loading">Approval requestler yükleniyor...</p>}
                  {!approvalLoading && approvalRequests.length === 0 && <p className="text-xs" data-testid="strategy-control-approval-empty">No data yet: approval request yok.</p>}
                  {!approvalLoading && approvalRequests.length > 0 && (
                    <div className="mt-2 space-y-2" data-testid="strategy-control-approval-list">
                      {approvalRequests.slice(0, 12).map((item, index) => (
                        <div key={item.request_id} className="rounded border border-black/20 bg-orange-50 p-2" data-testid={`strategy-control-approval-item-${index}`}>
                          <p className="text-xs" data-testid={`strategy-control-approval-item-head-${index}`}>
                            {item.request_id} · status={item.status} · strategy={item.strategy_id}
                          </p>
                          <p className="text-xs" data-testid={`strategy-control-approval-item-preview-${index}`}>
                            preview={JSON.stringify(item.preview || {})}
                          </p>
                          <p className="text-xs" data-testid={`strategy-control-approval-item-impact-preview-${index}`}>
                            impact_preview={JSON.stringify(item?.decision_context?.preview || {})}
                          </p>
                          <p className="text-xs" data-testid={`strategy-control-approval-item-risk-${index}`}>
                            risk={JSON.stringify(item?.decision_context?.risk || {})}
                          </p>
                          <p className="text-xs" data-testid={`strategy-control-approval-item-recommendation-${index}`}>
                            recommendation={JSON.stringify(item?.decision_context?.recommendation || {})}
                          </p>
                          <p className="text-xs" data-testid={`strategy-control-approval-item-expire-${index}`}>expires_at={item.expires_at}</p>
                          {item.status === "pending" && (
                            <div className="mt-1 flex gap-2" data-testid={`strategy-control-approval-item-actions-${index}`}>
                              <Button size="sm" onClick={() => submitApprovalDecision(item.request_id, "approve")} disabled={approvalSubmitting} data-testid={`strategy-control-approval-approve-button-${index}`}>Approve</Button>
                              <Button size="sm" variant="outline" onClick={() => submitApprovalDecision(item.request_id, "reject")} disabled={approvalSubmitting} data-testid={`strategy-control-approval-reject-button-${index}`}>Reject</Button>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="border border-black/25 bg-orange-100 p-4" data-testid="strategy-control-policy-suggestions-panel">
                  <h3 className="text-base font-semibold" data-testid="strategy-control-policy-suggestions-title">Policy Adjustment Suggestions (rule-based)</h3>
                  <Button variant="outline" onClick={loadPolicySuggestions} data-testid="strategy-control-policy-suggestions-refresh-button">Önerileri Yenile</Button>
                  {!policySuggestionSummary && <p className="mt-2 text-xs" data-testid="strategy-control-policy-suggestions-empty">No data yet: feedback pattern özeti hazır değil.</p>}
                  {policySuggestionSummary && (
                    <div className="mt-2 rounded border border-black/20 bg-orange-50 p-2" data-testid="strategy-control-policy-suggestions-summary-card">
                      <p className="text-xs" data-testid="strategy-control-policy-suggestions-24h">taxonomy_24h={JSON.stringify(policySuggestionSummary.taxonomy_24h || {})}</p>
                      <p className="text-xs" data-testid="strategy-control-policy-suggestions-7d">taxonomy_7d={JSON.stringify(policySuggestionSummary.taxonomy_7d || {})}</p>
                      <p className="text-xs" data-testid="strategy-control-policy-suggestions-rules">rules={(policySuggestionSummary.rules || []).join(" | ") || "n/a"}</p>
                      <div className="mt-2 space-y-2" data-testid="strategy-control-policy-suggestions-rules-list">
                        {(policySuggestionSummary.rules || []).length === 0 && (
                          <p className="text-xs" data-testid="strategy-control-policy-suggestions-rule-empty">No data yet: uygulanabilir rule bulunmuyor.</p>
                        )}
                        {(policySuggestionSummary.rules || []).map((rule, index) => (
                          <div key={`${rule}-${index}`} className="rounded border border-black/20 bg-white p-2" data-testid={`strategy-control-policy-suggestions-rule-item-${index}`}>
                            <p className="text-xs" data-testid={`strategy-control-policy-suggestions-rule-text-${index}`}>{rule}</p>
                            <Button
                              size="sm"
                              variant="outline"
                              className="mt-1"
                              onClick={() => openPolicyApplyHook({ source: "policy_panel", ruleText: rule })}
                              data-testid={`strategy-control-policy-suggestions-apply-fix-button-${index}`}
                            >
                              Apply Fix
                            </Button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </TabsContent>
          </Tabs>
        </>
      )}

      <Dialog open={actionModal.open} onOpenChange={(open) => setActionModal((prev) => ({ ...prev, open }))}>
        <DialogContent className="border border-black/40 bg-orange-50" data-testid="strategy-control-action-dialog">
          <DialogHeader>
            <DialogTitle data-testid="strategy-control-action-dialog-title">{actionMeta?.label || "Action"} · {actionModal.strategy?.strategy_id || "-"}</DialogTitle>
            <DialogDescription data-testid="strategy-control-action-dialog-description">Reason + confirm + audit zorunludur. Disable/Decommission ekstra güvenlik kontrolü içerir.</DialogDescription>
          </DialogHeader>
          <Textarea value={actionReason} onChange={(e) => setActionReason(e.target.value)} placeholder="Neden bu aksiyonu alıyorsunuz?" className="border-black/40" data-testid="strategy-control-action-dialog-reason-input" />
          {actionMeta?.key === "throttle" && (
            <select value={throttleLevel} onChange={(e) => setThrottleLevel(e.target.value)} className="h-10 rounded border border-black/40 bg-white px-3 text-sm" data-testid="strategy-control-action-dialog-throttle-level-select">
              <option value="L1">L1</option>
              <option value="L2">L2</option>
              <option value="L3">L3</option>
            </select>
          )}
          {actionMeta?.confirmPhrase && <Input value={actionConfirm} onChange={(e) => setActionConfirm(e.target.value)} placeholder={`Onay ifadesi: ${actionMeta.confirmPhrase}`} className="border-black/40" data-testid="strategy-control-action-dialog-confirm-input" />}
          <label className="flex items-center gap-2 text-xs" data-testid="strategy-control-action-dialog-dry-run-label">
            <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} data-testid="strategy-control-action-dialog-dry-run-checkbox" />
            dry-run (state yazmadan önizleme)
          </label>
          <DialogFooter>
            <Button variant="outline" onClick={() => setActionModal({ open: false, action: null, strategy: null })} data-testid="strategy-control-action-dialog-cancel-button">Vazgeç</Button>
            <Button onClick={submitAction} disabled={submitting} className="border border-black bg-black text-orange-300" data-testid="strategy-control-action-dialog-submit-button">
              {submitting ? "Uygulanıyor..." : "Aksiyonu Uygula"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <DecisionModal
        open={decisionModal.open}
        onOpenChange={(open) => setDecisionModal((prev) => ({ ...prev, open }))}
        title={decisionModal.title}
        actionType={decisionModal.actionType}
        strategyId={decisionModal.strategyId}
        defaultReason={decisionModal.defaultReason}
        confirmPlaceholder={decisionModal.confirmPlaceholder}
        confirmRequired={decisionModal.confirmRequired}
        riskSnapshot={decisionRiskSnapshot}
        params={decisionModal.params}
        requirePreview={true}
        showThresholdPlaceholder={decisionModal.actionType === "threshold_change"}
        extraContent={
          decisionModal.mode === "drift" && decisionModal.actionType === "mute" ? (
            <select
              value={driftMuteDuration}
              onChange={(e) => setDriftMuteDuration(Number(e.target.value))}
              className="h-10 rounded border border-black/40 bg-white px-3 text-sm"
              data-testid="decision-modal-drift-mute-duration-select"
            >
              <option value={1}>1h</option>
              <option value={24}>24h</option>
              <option value={168}>7d</option>
            </select>
          ) : null
        }
        onRequestPreview={requestImpactPreview}
        onConfirm={async ({ reason, confirmPhrase, previewToken }) => {
          if (decisionModal.mode === "rollout") {
            await submitRolloutOperation({ reason, confirmPhrase, previewToken });
            return;
          }
          if (decisionModal.mode === "drift") {
            await submitDriftAction({
              action: decisionModal.actionType,
              alert: decisionModal.payload?.alert,
              reason,
              confirmPhrase,
              previewToken,
            });
            return;
          }
          if (decisionModal.mode === "rollback_request") {
            await submitRollbackRequest({ reason, previewToken });
            return;
          }
          if (decisionModal.mode === "row_action_disable") {
            await submitAction({
              action: "disable",
              strategy: decisionModal.payload?.strategy,
              reason,
              confirmPhrase,
              previewToken,
            });
            return;
          }
          if (decisionModal.mode === "row_action_decommission") {
            await submitAction({
              action: "decommission",
              strategy: decisionModal.payload?.strategy,
              reason,
              confirmPhrase,
              previewToken,
            });
            return;
          }
          if (decisionModal.mode === "threshold_placeholder") {
            toast.success("Threshold edit hook hazırlandı; gerçek patch sonraki turda açılacak.");
          }
        }}
      />

      <Sheet open={detailOpen} onOpenChange={setDetailOpen}>
        <SheetContent side="right" className="w-[92vw] max-w-2xl overflow-y-auto border-l border-black bg-orange-50" data-testid="strategy-control-detail-drawer">
          <SheetHeader>
            <SheetTitle data-testid="strategy-control-detail-drawer-title">Strategy Detail</SheetTitle>
            <SheetDescription data-testid="strategy-control-detail-drawer-description">Trade list / execution log / export Faz-2 içinde placeholder olarak sunulur.</SheetDescription>
          </SheetHeader>
          {detailLoading && <p className="mt-4 text-sm" data-testid="strategy-control-detail-loading">Detail yükleniyor...</p>}
          {!detailLoading && !detailPayload && <p className="mt-4 text-sm" data-testid="strategy-control-detail-empty">No data yet: strategy detay verisi alınamadı.</p>}
          {!detailLoading && detailPayload && (
            <div className="mt-4 space-y-4" data-testid="strategy-control-detail-content">
              <InfoCard testId="strategy-control-detail-summary-card" lines={[
                `strategy=${detailPayload?.strategy?.strategy_id}`,
                `state=${detailPayload?.strategy?.control_state} lifecycle=${detailPayload?.strategy?.lifecycle_state}`,
                `rollout_mode=${detailPayload?.strategy?.rollout_mode} rollout_percentage=${detailPayload?.strategy?.rollout_percentage}%`,
              ]} />
              <InfoCard testId="strategy-control-detail-trade-list-panel" title="Trade List" lines={[detailPayload?.trade_list?.reason || "No data yet"]} />
              <InfoCard testId="strategy-control-detail-execution-log-panel" title="Execution Log" lines={[detailPayload?.execution_history?.reason || "No data yet"]} />
              <InfoCard testId="strategy-control-detail-transition-history-panel" title="Transition History" lines={(detailPayload?.transition_history || []).map((item) => `${item?.from || "NONE"}→${item?.to || "NONE"} reason=${item?.reason || "-"}`)} emptyText="No data yet: geçiş geçmişi bulunmuyor." />
              <InfoCard testId="strategy-control-detail-audit-history-panel" title="Audit History" lines={(detailPayload?.audit_items || []).map((item) => `${item?.created_at || "-"} · ${item?.action || "-"} · severity=${item?.severity || "-"}`)} emptyText="No data yet: strategy için audit kaydı bulunmuyor." />
            </div>
          )}
        </SheetContent>
      </Sheet>
    </section>
  );
};

const MetricCard = ({ testId, title, value }) => (
  <div className="border border-black/25 bg-orange-100 p-3" data-testid={`${testId}-card`}>
    <p className="text-xs uppercase" data-testid={`${testId}-title`}>{title}</p>
    <p className="text-xl font-bold" data-testid={`${testId}-value`}>{value}</p>
  </div>
);

const PlaceholderPanel = ({ testId, title, reason }) => (
  <div className="border border-black/25 bg-orange-100 p-4" data-testid={testId}>
    <h3 className="text-base font-semibold" data-testid={`${testId}-title`}>{title}</h3>
    <p className="mt-1 text-sm" data-testid={`${testId}-reason`}>No data yet: {reason}</p>
  </div>
);

const InfoCard = ({ testId, title, lines = [], emptyText }) => (
  <div className="rounded border border-black/20 bg-orange-100 p-3" data-testid={testId}>
    {title && <h4 className="text-sm font-semibold" data-testid={`${testId}-title`}>{title}</h4>}
    {lines.length === 0 && <p className="text-xs" data-testid={`${testId}-empty`}>{emptyText || "No data yet"}</p>}
    {lines.map((line, idx) => (
      <p key={`${testId}-${idx}`} className="text-xs" data-testid={`${testId}-line-${idx}`}>{line}</p>
    ))}
  </div>
);

const BulkBreakdownSection = ({ bucketKey, rows = [] }) => {
  const labelMap = {
    success: "Success",
    failed: "Failed",
    skipped: "Skipped",
  };

  return (
    <div className="rounded border border-black/20 bg-white p-2" data-testid={`strategy-control-bulk-breakdown-section-${bucketKey}`}>
      <p className="text-xs font-semibold" data-testid={`strategy-control-bulk-breakdown-section-title-${bucketKey}`}>
        {labelMap[bucketKey] || bucketKey} ({rows.length})
      </p>
      {rows.length === 0 && (
        <p className="text-xs" data-testid={`strategy-control-bulk-breakdown-empty-${bucketKey}`}>
          No data yet
        </p>
      )}
      {rows.map((row, index) => (
        <div
          key={`${bucketKey}-${row?.strategy_id || index}-${index}`}
          className={`mt-1 rounded border p-2 text-xs ${bucketKey === "failed" ? "border-red-500 bg-red-50 text-red-900" : "border-black/20 bg-orange-50"}`}
          data-testid={`strategy-control-bulk-breakdown-row-${bucketKey}-${index}`}
        >
          <p data-testid={`strategy-control-bulk-breakdown-row-strategy-${bucketKey}-${index}`}>
            strategy={row?.strategy_id || "-"} · status={row?.status || "-"}
          </p>
          <p data-testid={`strategy-control-bulk-breakdown-row-message-${bucketKey}-${index}`}>
            message={row?.message || "-"}
          </p>
          <p data-testid={`strategy-control-bulk-breakdown-row-action-ref-${bucketKey}-${index}`}>
            action_ref={row?.action_ref || row?.trace_id || "-"}
          </p>
        </div>
      ))}
    </div>
  );
};

const StrategyTable = ({ rows, onOpenDetail, onRunAction, compact = false, selectedStrategyIds, onToggleStrategy }) => (
  <div className="border border-black/25 bg-orange-100" data-testid={compact ? "strategy-control-table-compact" : "strategy-control-table-full"}>
    <div className="border-b border-black/20 px-4 py-3" data-testid={compact ? "strategy-control-table-compact-header" : "strategy-control-table-full-header"}>
      <h3 className="text-base font-semibold" data-testid={compact ? "strategy-control-table-compact-title" : "strategy-control-table-full-title"}>Strategy Lifecycle Control</h3>
    </div>
    <Table data-testid={compact ? "strategy-control-table-compact-table" : "strategy-control-table-full-table"}>
      <TableHeader>
        <TableRow>
          {onToggleStrategy && <TableHead data-testid="strategy-control-table-head-select">Select</TableHead>}
          <TableHead data-testid="strategy-control-table-head-strategy">Strategy</TableHead>
          <TableHead data-testid="strategy-control-table-head-state">State</TableHead>
          <TableHead data-testid="strategy-control-table-head-shadow-live">Shadow/Live</TableHead>
          <TableHead data-testid="strategy-control-table-head-rollout">Rollout</TableHead>
          <TableHead data-testid="strategy-control-table-head-health">Health</TableHead>
          <TableHead data-testid="strategy-control-table-head-risk">Risk</TableHead>
          <TableHead data-testid="strategy-control-table-head-error">Error%</TableHead>
          <TableHead data-testid="strategy-control-table-head-actions">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row, index) => (
          <TableRow key={row.strategy_id} data-testid={`strategy-control-table-row-${index}`}>
            {onToggleStrategy && (
              <TableCell data-testid={`strategy-control-table-select-${index}`}>
                <input type="checkbox" checked={selectedStrategyIds.includes(row.strategy_id)} onChange={() => onToggleStrategy(row.strategy_id)} data-testid={`strategy-control-table-select-checkbox-${index}`} />
              </TableCell>
            )}
            <TableCell data-testid={`strategy-control-table-strategy-${index}`}>{row.strategy_id}</TableCell>
            <TableCell data-testid={`strategy-control-table-state-${index}`}>{row.control_state} / {row.throttle_level}</TableCell>
            <TableCell data-testid={`strategy-control-table-shadow-live-${index}`}>{row.shadow_live_state}</TableCell>
            <TableCell data-testid={`strategy-control-table-rollout-${index}`}>{row.rollout_mode} / {row.rollout_percentage}%</TableCell>
            <TableCell data-testid={`strategy-control-table-health-${index}`}>{row.health_score}</TableCell>
            <TableCell data-testid={`strategy-control-table-risk-${index}`}>
              {row.risk_level === "LOW" && <span className="rounded bg-emerald-200 px-2 py-0.5 text-xs">🟢 LOW ({row.risk_score})</span>}
              {row.risk_level === "MED" && <span className="rounded bg-amber-200 px-2 py-0.5 text-xs">🟡 MED ({row.risk_score})</span>}
              {row.risk_level === "HIGH" && <span className="rounded bg-red-200 px-2 py-0.5 text-xs">🔴 HIGH ({row.risk_score})</span>}
            </TableCell>
            <TableCell data-testid={`strategy-control-table-error-${index}`}>{row.error_rate_pct}</TableCell>
            <TableCell data-testid={`strategy-control-table-actions-${index}`}>
              <div className="flex flex-wrap gap-1">
                <Button size="sm" variant="outline" onClick={() => onOpenDetail(row.strategy_id)} data-testid={`strategy-control-open-detail-button-${index}`}>Detail</Button>
                {ACTIONS.map((action) => (
                  <Button key={`${row.strategy_id}-${action.key}`} size="sm" variant="outline" onClick={() => onRunAction(action.key, row)} className={action.destructive ? "border-red-800 text-red-900" : ""} data-testid={`strategy-control-action-${action.key}-button-${index}`}>{action.label}</Button>
                ))}
              </div>
            </TableCell>
          </TableRow>
        ))}
        {rows.length === 0 && (
          <TableRow data-testid="strategy-control-table-empty-row">
            <TableCell colSpan={onToggleStrategy ? 9 : 8} className="text-center text-sm" data-testid="strategy-control-table-empty-text">No data yet: strategy kayıtları henüz oluşmadı veya geçici olarak alınamadı.</TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  </div>
);
