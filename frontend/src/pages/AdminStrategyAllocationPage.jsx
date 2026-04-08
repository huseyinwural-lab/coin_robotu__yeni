import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";

const WEIGHT_TOLERANCE = 0.0001;
const DEFAULT_STARTUP_WEIGHT = "0.0833333";

const toNumber = (value) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : NaN;
};

const formatMoney = (value) => {
  const amount = Number.isFinite(Number(value)) ? Number(value) : 0;
  return amount.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

const createDraftFromRow = (item) => ({
  expected_revision: Number(item.revision_id || 1),
  capital_weight: String(item.capital_weight ?? DEFAULT_STARTUP_WEIGHT),
  max_capital: String(item.max_capital ?? "0"),
  current_capital: String(item.current_capital ?? "0"),
  state: item.state || "ACTIVE",
  confirm_primary: "",
  confirm_secondary: "",
});

const validateDraft = (draft) => {
  const errors = [];
  const weight = toNumber(draft.capital_weight);
  const maxCapital = toNumber(draft.max_capital);
  const currentCapital = toNumber(draft.current_capital);

  if (!Number.isFinite(weight)) errors.push("Weight sayısal olmalı");
  if (!Number.isFinite(maxCapital)) errors.push("Max capital sayısal olmalı");
  if (!Number.isFinite(currentCapital)) errors.push("Current capital sayısal olmalı");

  if (Number.isFinite(weight) && (weight < 0 || weight > 1)) errors.push("Weight 0 ile 1 arasında olmalı");
  if (Number.isFinite(maxCapital) && maxCapital < 0) errors.push("Max capital negatif olamaz");
  if (Number.isFinite(currentCapital) && currentCapital < 0) errors.push("Current capital negatif olamaz");
  if (Number.isFinite(maxCapital) && Number.isFinite(currentCapital) && currentCapital > maxCapital) {
    errors.push("Current capital max capital değerini aşamaz");
  }

  return {
    errors,
    hasError: errors.length > 0,
  };
};

const stateReasonBadgeClass = (code) => {
  const normalized = String(code || "").toUpperCase();
  if (normalized === "AUTO_DISABLED_BY_DRIFT") return "border border-rose-500/60 bg-rose-950/50 text-rose-200";
  if (normalized === "AUTO_THROTTLED_BY_DRIFT") return "border border-amber-500/60 bg-amber-950/50 text-amber-200";
  return "border border-slate-700 bg-slate-950 text-slate-300";
};

const stateReasonInlineText = () => "Manual / advisory";

const confidenceBand = (confidenceValue) => {
  const raw = Number(confidenceValue);
  const pct = Number.isFinite(raw) ? (raw <= 1 ? raw * 100 : raw) : 0;
  if (pct >= 75) return "HIGH";
  if (pct >= 50) return "MED";
  return "LOW";
};

const confidenceBandClass = (band) => {
  if (band === "HIGH") return "border border-emerald-500/60 text-emerald-300";
  if (band === "LOW") return "border border-rose-500/60 text-rose-300";
  return "border border-amber-500/60 text-amber-300";
};

const wsBadgeClass = (status) => {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "connected") return "border-emerald-500/60 bg-emerald-900/30 text-emerald-200";
  if (normalized === "connecting") return "border-cyan-500/60 bg-cyan-900/30 text-cyan-200";
  if (normalized === "degraded") return "border-amber-500/60 bg-amber-900/30 text-amber-200";
  return "border-rose-500/60 bg-rose-900/30 text-rose-200";
};

const formatRequestAge = (createdAt, nowMs) => {
  const createdMs = new Date(createdAt).getTime();
  if (!Number.isFinite(createdMs)) return "-";
  const diffMs = Math.max(0, nowMs - createdMs);
  const totalMinutes = Math.floor(diffMs / 60000);
  if (totalMinutes < 60) return `${totalMinutes}m`;

  const totalHours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (totalHours < 24) return `${totalHours}h ${minutes}m`;

  const days = Math.floor(totalHours / 24);
  const hours = totalHours % 24;
  return `${days}d ${hours}h`;
};

const getApiDetailMessage = (error, fallbackMessage) => {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail === "object") return detail.message || fallbackMessage;
  return fallbackMessage;
};

const getRevisionConflictDetail = (error) => {
  if (error?.response?.status !== 409) return null;
  const detail = error?.response?.data?.detail;
  if (detail && typeof detail === "object") return detail;
  return {
    code: "REVISION_CONFLICT",
    message: typeof detail === "string" ? detail : "Veri güncel değil. Lütfen en güncel halini yükleyin.",
    conflicts: [],
  };
};

const approvalStatusLabel = (item) => {
  const status = String(item?.status || "").toLowerCase();
  if (status === "requires_review" || String(item?.stale_state || "").toUpperCase() === "STALE") {
    return "REQUIRES_REVIEW";
  }
  return String(item?.status || "-").toUpperCase();
};

export const AdminStrategyAllocationPage = () => {
  const { user } = useAuth();
  const [rows, setRows] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [backendSummary, setBackendSummary] = useState(null);
  const [stateHistory, setStateHistory] = useState([]);
  const [selectedStrategyIds, setSelectedStrategyIds] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [isNormalizing, setIsNormalizing] = useState(false);
  const [isBulkSubmitting, setIsBulkSubmitting] = useState(false);
  const [bulkAutoNormalize, setBulkAutoNormalize] = useState(false);
  const [isGeneratingRebalance, setIsGeneratingRebalance] = useState(false);
  const [rebalanceSuggestion, setRebalanceSuggestion] = useState(null);
  const [globalActionError, setGlobalActionError] = useState("");
  const [driftOverrideNotice, setDriftOverrideNotice] = useState("");
  const [editingStrategyIds, setEditingStrategyIds] = useState([]);
  const [reasonNote, setReasonNote] = useState("");
  const [approvalReviewNote, setApprovalReviewNote] = useState("phase5_review");
  const [approvalRequests, setApprovalRequests] = useState([]);
  const [snapshots, setSnapshots] = useState([]);
  const [isCreatingSnapshot, setIsCreatingSnapshot] = useState(false);
  const [restoreModal, setRestoreModal] = useState({ open: false, snapshot: null, reason: "", isSubmitting: false });
  const [isRunningWhatIf, setIsRunningWhatIf] = useState(false);
  const [whatIfResult, setWhatIfResult] = useState(null);
  const [requestAgeTick, setRequestAgeTick] = useState(Date.now());
  const [lastUpdatedAt, setLastUpdatedAt] = useState("");
  const [revisionConflict, setRevisionConflict] = useState(null);
  const [exportRelatedRequestId, setExportRelatedRequestId] = useState("");
  const [exportSnapshotId, setExportSnapshotId] = useState("");
  const [healthSnapshot, setHealthSnapshot] = useState(null);
  const [isHealthLoading, setIsHealthLoading] = useState(false);
  const [wsConnectionStatus, setWsConnectionStatus] = useState("connecting");
  const [wsRetryCount, setWsRetryCount] = useState(0);
  const [wsLastMessageAt, setWsLastMessageAt] = useState("");
  const [wsErrorMessage, setWsErrorMessage] = useState("");
  const [selectedExplainStrategyId, setSelectedExplainStrategyId] = useState("");
  const [explainabilityData, setExplainabilityData] = useState(null);
  const [isExplainabilityLoading, setIsExplainabilityLoading] = useState(false);
  const [pendingRetryAction, setPendingRetryAction] = useState(null);

  const wsRef = useRef(null);
  const wsReconnectTimerRef = useRef(null);
  const wsBackoffMsRef = useRef(1200);
  const wsManualCloseRef = useRef(false);

  const role = String(user?.role || "");
  const isOpsReadOnly = role === "ops";
  const isSuperAdmin = role === "super_admin";

  const buildExpectedRevisionMap = () => {
    const map = {};
    rows.forEach((row) => {
      const draft = drafts[row.strategy_id] || {};
      map[row.strategy_id] = Number(draft.expected_revision || row.revision_id || 1);
    });
    return map;
  };

  const applyRevisionConflictsToDrafts = (conflicts = []) => {
    const safeConflicts = Array.isArray(conflicts) ? conflicts : [];
    if (safeConflicts.length === 0) return;
    setDrafts((prev) => {
      const next = { ...prev };
      safeConflicts.forEach((item) => {
        const strategyId = String(item?.strategy_id || "").trim();
        const currentRevision = Number(item?.current_revision || 0);
        if (!strategyId || currentRevision <= 0) return;
        const sourceRow = rows.find((row) => row.strategy_id === strategyId);
        next[strategyId] = {
          ...(next[strategyId] || createDraftFromRow(sourceRow || { strategy_id: strategyId, revision_id: 1 })),
          expected_revision: currentRevision,
        };
      });
      return next;
    });
  };

  const loadHealthSnapshot = async ({ silent = false } = {}) => {
    if (!silent) setIsHealthLoading(true);
    try {
      const { data } = await apiClient.get("/admin/strategy-allocation/health");
      setHealthSnapshot(data || null);
      if (!wsLastMessageAt) {
        setWsLastMessageAt(new Date().toISOString());
      }
    } catch (error) {
      const message = getApiDetailMessage(error, "Health verisi alınamadı");
      if (!silent) {
        setGlobalActionError(message);
      }
    } finally {
      if (!silent) setIsHealthLoading(false);
    }
  };

  const loadExplainability = async (strategyId, { silent = false } = {}) => {
    const key = String(strategyId || "").trim();
    if (!key) {
      setExplainabilityData(null);
      return;
    }
    if (!silent) setIsExplainabilityLoading(true);
    try {
      const { data } = await apiClient.get(`/admin/strategy-allocation/explainability/${encodeURIComponent(key)}`, {
        params: { lookback_hours: 24, limit: 8 },
      });
      setExplainabilityData(data || null);
    } catch (error) {
      const message = getApiDetailMessage(error, "Explainability alınamadı");
      if (!silent) {
        toast.error(message);
      }
    } finally {
      if (!silent) setIsExplainabilityLoading(false);
    }
  };

  const closeRealtimeSocket = () => {
    if (wsReconnectTimerRef.current) {
      window.clearTimeout(wsReconnectTimerRef.current);
      wsReconnectTimerRef.current = null;
    }
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch (_) {
        // noop
      }
      wsRef.current = null;
    }
  };

  const connectRealtimeSocket = () => {
    const headerToken = String(apiClient?.defaults?.headers?.common?.Authorization || "").replace(/^Bearer\s+/i, "").trim();
    const token = headerToken || window.localStorage.getItem("access_token");
    if (!token) {
      setWsConnectionStatus("disconnected");
      setWsErrorMessage("access_token_missing");
      return;
    }

    const base = process.env.REACT_APP_BACKEND_URL || window.location.origin;
    const wsBase = base.replace(/^http/i, "ws").replace(/\/$/, "");
    const params = new URLSearchParams();
    params.set("token", token);
    params.set("interval", "5");
    if (selectedExplainStrategyId) {
      params.set("strategy_id", selectedExplainStrategyId);
    }

    setWsConnectionStatus("connecting");
    setWsErrorMessage("");
    const socket = new window.WebSocket(`${wsBase}/api/admin/strategy-allocation/ws/stream?${params.toString()}`);
    wsRef.current = socket;

    socket.onopen = () => {
      wsBackoffMsRef.current = 1200;
      setWsConnectionStatus("connected");
      setWsErrorMessage("");
    };

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data || "{}");
        if (payload?.type === "snapshot") {
          if (payload?.health) setHealthSnapshot(payload.health);
          if (payload?.explainability) setExplainabilityData(payload.explainability);
          setWsLastMessageAt(new Date().toISOString());
          setWsConnectionStatus("connected");
          return;
        }
        if (payload?.type === "error") {
          setWsConnectionStatus("degraded");
          setWsErrorMessage(payload?.message || payload?.code || "ws_error");
        }
      } catch (_) {
        setWsConnectionStatus("degraded");
      }
    };

    socket.onerror = () => {
      setWsConnectionStatus("degraded");
      setWsErrorMessage("ws_connection_error");
    };

    socket.onclose = () => {
      if (wsManualCloseRef.current) return;
      setWsConnectionStatus("disconnected");
      setWsRetryCount((prev) => prev + 1);
      const nextDelay = Math.min(wsBackoffMsRef.current * 1.8, 15000);
      wsBackoffMsRef.current = nextDelay;
      wsReconnectTimerRef.current = window.setTimeout(() => {
        connectRealtimeSocket();
      }, Math.floor(nextDelay));
    };
  };

  const showRevisionConflict = (detail) => {
    const message = detail?.message || "Veri güncel değil. Lütfen en güncel halini yükleyin.";
    setRevisionConflict({
      message,
      conflicts: Array.isArray(detail?.conflicts) ? detail.conflicts : [],
      action_type: detail?.action_type || "unknown",
    });
    setGlobalActionError(message);
    toast.error(message);
  };

  const handleConflictError = (error, fallbackMessage) => {
    const conflictDetail = getRevisionConflictDetail(error);
    if (conflictDetail) {
      showRevisionConflict(conflictDetail);
      return true;
    }
    const message = getApiDetailMessage(error, fallbackMessage);
    setGlobalActionError(message);
    toast.error(message);
    return false;
  };

  const resolveRevisionConflictAndRetry = async () => {
    const conflicts = revisionConflict?.conflicts || [];
    if (conflicts.length === 0) {
      await load();
      return;
    }

    applyRevisionConflictsToDrafts(conflicts);
    setRevisionConflict(null);
    setGlobalActionError("");
    toast.success("Çakışan revision değerleri güncellendi");

    const action = pendingRetryAction;
    if (!action?.type) return;

    if (action.type === "save" && action.strategyId) {
      await saveStrategy(action.strategyId, { fromRetry: true });
      return;
    }
    if (action.type === "bulk") {
      await submitBulkUpdate({ fromRetry: true });
      return;
    }
    if (action.type === "normalize") {
      await normalizeWeights({ fromRetry: true });
      return;
    }
    if (action.type === "restore") {
      await submitSnapshotRestore({ fromRetry: true });
    }
  };

  const load = async () => {
    setIsLoading(true);
    setLoadError("");
    setGlobalActionError("");
    setRevisionConflict(null);
    try {
      const [rowsResp, summaryResp, historyResp, approvalResp, snapshotsResp] = await Promise.all([
        apiClient.get("/admin/strategy-allocation"),
        apiClient.get("/admin/strategy-allocation/summary"),
        apiClient.get("/admin/strategy-allocation/state-history", { params: { limit: 40 } }),
        apiClient.get("/admin/strategy-allocation/approval-requests"),
        apiClient.get("/admin/strategy-allocation/snapshots"),
      ]);

      const rowsData = rowsResp?.data || [];
      setRows(rowsData);
      setBackendSummary(summaryResp?.data || null);
      setStateHistory(historyResp?.data?.rows || []);
      setApprovalRequests(approvalResp?.data?.rows || []);
      setSnapshots(snapshotsResp?.data?.rows || []);
      const initialDrafts = {};
      rowsData.forEach((item) => {
        initialDrafts[item.strategy_id] = {
          ...createDraftFromRow(item),
        };
      });
      setDrafts(initialDrafts);
      setSelectedStrategyIds((prev) => prev.filter((id) => rowsData.some((row) => row.strategy_id === id)));
      setEditingStrategyIds([]);
      setRebalanceSuggestion(null);
      setWhatIfResult(null);
      setPendingRetryAction(null);
      setSelectedExplainStrategyId((prev) => {
        if (prev && rowsData.some((row) => row.strategy_id === prev)) return prev;
        return rowsData[0]?.strategy_id || "";
      });
      setLastUpdatedAt(new Date().toISOString());
      await loadHealthSnapshot({ silent: true });
    } catch (error) {
      const detail = error?.response?.data?.detail;
      const message =
        typeof detail === "string"
          ? detail
          : (detail?.message || "Strategy allocation verisi yüklenemedi");
      setLoadError(message);
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!selectedExplainStrategyId) return;
    loadExplainability(selectedExplainStrategyId, { silent: true });
  }, [selectedExplainStrategyId]);

  useEffect(() => {
    wsManualCloseRef.current = false;
    closeRealtimeSocket();
    connectRealtimeSocket();
    return () => {
      wsManualCloseRef.current = true;
      closeRealtimeSocket();
    };
  }, [selectedExplainStrategyId]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (wsConnectionStatus !== "connected") {
        loadHealthSnapshot({ silent: true });
      }
    }, 20000);
    return () => window.clearInterval(timer);
  }, [wsConnectionStatus]);

  useEffect(() => {
    const timer = window.setInterval(() => setRequestAgeTick(Date.now()), 60000);
    return () => window.clearInterval(timer);
  }, []);

  const stateStats = useMemo(() => {
    const total = rows.length;
    const active = rows.filter((item) => item.state === "ACTIVE").length;
    const passive = rows.filter((item) => item.state === "DISABLED").length;
    return { total, active, passive };
  }, [rows]);

  const draftRows = useMemo(
    () => rows.map((row) => ({ strategy_id: row.strategy_id, ...(drafts[row.strategy_id] || createDraftFromRow(row)) })),
    [drafts, rows],
  );

  const capitalSnapshot = useMemo(() => {
    const totalWeight = draftRows.reduce((acc, row) => acc + (toNumber(row.capital_weight) || 0), 0);
    const totalCapital = draftRows.reduce((acc, row) => acc + (toNumber(row.max_capital) || 0), 0);
    const usedCapital = draftRows.reduce((acc, row) => acc + (toNumber(row.current_capital) || 0), 0);
    const overAllocatedRows = draftRows.filter((row) => {
      const maxCapital = toNumber(row.max_capital);
      const currentCapital = toNumber(row.current_capital);
      return Number.isFinite(maxCapital) && Number.isFinite(currentCapital) && currentCapital > maxCapital;
    });

    return {
      totalWeight: Number(totalWeight.toFixed(6)),
      weightDelta: Number((totalWeight - 1).toFixed(6)),
      totalCapital,
      usedCapital,
      availableCapital: Math.max(totalCapital - usedCapital, 0),
      overAllocatedRows,
    };
  }, [draftRows]);

  const weightIsBalanced = Math.abs(capitalSnapshot.weightDelta) <= WEIGHT_TOLERANCE;
  const hasOverAllocation = capitalSnapshot.overAllocatedRows.length > 0;
  const whatIfByStrategy = useMemo(() => {
    const map = {};
    (whatIfResult?.rows || []).forEach((row) => {
      map[row.strategy_id] = row;
    });
    return map;
  }, [whatIfResult]);

  const healthCore = healthSnapshot?.health || {};
  const healthDebug = healthSnapshot?.debug || {};
  const scannerFreshness = healthCore?.scanner_freshness || {};
  const exchangeConnectivity = healthCore?.exchange_connectivity || {};
  const traceSpineRows = explainabilityData?.trace_spine || [];

  const updateDraft = (strategyId, key, value) => {
    setGlobalActionError("");
    setRevisionConflict(null);
    setDrafts((prev) => ({
      ...prev,
      [strategyId]: {
        ...(prev[strategyId] || {}),
        [key]: value,
      },
    }));
  };

  const getRowErrors = (strategyId) => {
    const draft = drafts[strategyId] || {};
    const baseValidation = validateDraft(draft);
    const errors = [...baseValidation.errors];

    if (!weightIsBalanced) errors.push("Toplam weight = 1 olmalı");
    if (hasOverAllocation) errors.push("Capital limit aşılıyor");

    return errors;
  };

  const isEditing = (strategyId) => editingStrategyIds.includes(strategyId);

  const startEdit = (strategyId) => {
    const sourceRow = rows.find((row) => row.strategy_id === strategyId);
    if (sourceRow) {
      setDrafts((prev) => ({
        ...prev,
        [strategyId]: {
          ...createDraftFromRow(sourceRow),
        },
      }));
    }
    setEditingStrategyIds((prev) => (prev.includes(strategyId) ? prev : [...prev, strategyId]));
  };

  const cancelEdit = (strategyId) => {
    const sourceRow = rows.find((row) => row.strategy_id === strategyId);
    if (sourceRow) {
      setDrafts((prev) => ({
        ...prev,
        [strategyId]: {
          ...createDraftFromRow(sourceRow),
        },
      }));
    }
    setEditingStrategyIds((prev) => prev.filter((id) => id !== strategyId));
  };

  const ensureReasonNote = () => {
    const note = String(reasonNote || "").trim();
    if (!note) {
      const message = "reason note zorunlu";
      setGlobalActionError(message);
      toast.error(message);
      return null;
    }
    return note;
  };

  const saveStrategy = async (strategyId, options = {}) => {
    if (isOpsReadOnly) {
      toast.error("ops role read-only");
      return;
    }
    if (!options.fromRetry) {
      setPendingRetryAction({ type: "save", strategyId });
    }
    const note = String(reasonNote || "").trim() || `allocation_save_${strategyId}`;

    const draft = drafts[strategyId] || {};
    const sourceRow = rows.find((row) => row.strategy_id === strategyId);
    const rowErrors = getRowErrors(strategyId);
    if (rowErrors.length > 0) {
      const firstError = rowErrors[0] || "Form geçersiz";
      toast.error(firstError);
      setGlobalActionError(firstError);
      return;
    }

    try {
      const { data } = await apiClient.put(`/admin/strategy-allocation/${encodeURIComponent(strategyId)}`, {
        expected_revision: Number(draft.expected_revision || sourceRow?.revision_id || 1),
        capital_weight: Number(draft.capital_weight),
        max_capital: Number(draft.max_capital),
        current_capital: Number(draft.current_capital),
        state: draft.state,
        reason_note: note,
        confirm_primary: draft.confirm_primary || undefined,
        confirm_secondary: draft.confirm_secondary || undefined,
      });
      if (data?.status === "pending_approval") {
        toast.success(data?.message || `Update onaya gönderildi: ${strategyId}`);
        setPendingRetryAction(null);
        await load();
        return;
      }
      toast.success(`Allocation güncellendi: ${strategyId}`);
      setEditingStrategyIds((prev) => prev.filter((id) => id !== strategyId));
      setRevisionConflict(null);
      if (data?.is_drift_override) {
        const notice = `Manual change overridden by drift rule (${data?.state_reason_code || "AUTO"})`;
        setDriftOverrideNotice(notice);
        toast.warning(notice);
      } else {
        setDriftOverrideNotice("");
      }
      setPendingRetryAction(null);
      await load();
    } catch (error) {
      handleConflictError(error, "Allocation güncellenemedi");
    }
  };

  const normalizeWeights = async (options = {}) => {
    if (isOpsReadOnly) {
      toast.error("ops role read-only");
      return;
    }
    if (!options.fromRetry) {
      setPendingRetryAction({ type: "normalize" });
    }
    const note = ensureReasonNote();
    if (!note) return;

    setIsNormalizing(true);
    setGlobalActionError("");
    try {
      const { data } = await apiClient.post("/admin/strategy-allocation/normalize", {
        reason_note: note,
        expected_revisions: buildExpectedRevisionMap(),
      });
      toast.success(data?.message || "Weight normalize tamamlandı");
      setRevisionConflict(null);
      setPendingRetryAction(null);
      await load();
    } catch (error) {
      handleConflictError(error, "Normalize işlemi başarısız");
    } finally {
      setIsNormalizing(false);
    }
  };

  const toggleSelection = (strategyId) => {
    setSelectedStrategyIds((prev) => {
      if (prev.includes(strategyId)) return prev.filter((id) => id !== strategyId);
      return [...prev, strategyId];
    });
  };

  const applyDrawdownSuggestionsToForm = () => {
    const candidates = backendSummary?.drawdown_candidates || [];
    if (candidates.length === 0) {
      toast.info("Drawdown reduce önerisi bulunmuyor");
      return;
    }

    setDrafts((prev) => {
      const next = { ...prev };
      candidates.forEach((candidate) => {
        const strategyId = candidate.strategy_id;
        if (!next[strategyId]) return;
        next[strategyId] = {
          ...next[strategyId],
          current_capital: String(candidate.suggested_reduced_capital),
        };
      });
      return next;
    });
    toast.success("Drawdown reduce önerileri forma uygulandı (otomatik kaydetme yok)");
  };

  const generateRebalanceSuggestion = async () => {
    setIsGeneratingRebalance(true);
    try {
      const { data } = await apiClient.post("/admin/strategy-allocation/rebalance-suggestions", {
        strategy_ids: selectedStrategyIds,
      });
      setRebalanceSuggestion(data || null);
      toast.success(data?.message || "Rebalance önerisi hazır");
    } catch (error) {
      const message = error?.response?.data?.detail || "Rebalance önerisi üretilemedi";
      toast.error(message);
      setGlobalActionError(message);
    } finally {
      setIsGeneratingRebalance(false);
    }
  };

  const applyRebalanceSuggestionToDraft = () => {
    const suggestions = rebalanceSuggestion?.suggestions || [];
    if (selectedStrategyIds.length === 0) {
      toast.info("Önce strategy seçin. Seçim yoksa sadece önizleme gösterilir.");
      return;
    }
    if (suggestions.length === 0) {
      toast.info("Uygulanacak öneri bulunmuyor");
      return;
    }

    const selectedSet = new Set(selectedStrategyIds);
    setDrafts((prev) => {
      const next = { ...prev };
      suggestions.forEach((row) => {
        if (!selectedSet.has(row.strategy_id) || !next[row.strategy_id]) return;
        next[row.strategy_id] = {
          ...next[row.strategy_id],
          capital_weight: String(row.suggested_weight),
        };
      });
      return next;
    });
    toast.success("Rebalance önerisi seçili strategy draft alanlarına uygulandı (save yok)");
  };

  const createSnapshot = async () => {
    if (isOpsReadOnly) {
      toast.error("ops role read-only");
      return;
    }
    const note = ensureReasonNote();
    if (!note) return;

    setIsCreatingSnapshot(true);
    try {
      const { data } = await apiClient.post("/admin/strategy-allocation/snapshots", { reason_note: note });
      toast.success(data?.message || "Snapshot oluşturuldu");
      await load();
    } catch (error) {
      const message = error?.response?.data?.detail || "Snapshot oluşturulamadı";
      setGlobalActionError(message);
      toast.error(message);
    } finally {
      setIsCreatingSnapshot(false);
    }
  };

  const openRestoreModal = (snapshot) => {
    setRestoreModal({
      open: true,
      snapshot,
      reason: String(reasonNote || "").trim() || `restore_${snapshot?.snapshot_id || "snapshot"}`,
      isSubmitting: false,
    });
  };

  const closeRestoreModal = () => {
    if (restoreModal.isSubmitting) return;
    setRestoreModal({ open: false, snapshot: null, reason: "", isSubmitting: false });
  };

  const submitSnapshotRestore = async (options = {}) => {
    if (isOpsReadOnly) {
      toast.error("ops role read-only");
      return;
    }
    const snapshotId = restoreModal?.snapshot?.snapshot_id;
    if (!snapshotId) {
      toast.error("snapshot_id bulunamadı");
      return;
    }

    const note = String(restoreModal.reason || "").trim();
    if (!note) {
      toast.error("restore reason zorunlu");
      return;
    }

    if (!options.fromRetry) {
      setPendingRetryAction({ type: "restore", snapshotId });
    }

    setRestoreModal((prev) => ({ ...prev, isSubmitting: true }));
    try {
      const { data } = await apiClient.post(`/admin/strategy-allocation/snapshots/${encodeURIComponent(snapshotId)}/restore`, {
        reason_note: note,
        expected_revisions: buildExpectedRevisionMap(),
      });
      toast.success(data?.message || `Restore tamamlandı: ${snapshotId}`);
      setRestoreModal({ open: false, snapshot: null, reason: "", isSubmitting: false });
      setRevisionConflict(null);
      setPendingRetryAction(null);
      await load();
    } catch (error) {
      handleConflictError(error, "Snapshot restore başarısız");
      setRestoreModal((prev) => ({ ...prev, isSubmitting: false }));
    }
  };

  const exportAllocation = async (format) => {
    try {
      const params = new URLSearchParams();
      params.set("format", format);
      const note = String(reasonNote || "").trim();
      if (note) params.set("reason_note", note);
      const relatedRequestId = String(exportRelatedRequestId || "").trim();
      if (relatedRequestId) params.set("related_request_id", relatedRequestId);
      const snapshotId = String(exportSnapshotId || "").trim();
      if (snapshotId) params.set("snapshot_id", snapshotId);
      if (selectedStrategyIds.length > 0) params.set("selected_strategy_ids", selectedStrategyIds.join(","));

      const response = await apiClient.get(`/admin/strategy-allocation/export?${params.toString()}`, {
        responseType: "blob",
      });
      const blob = new Blob([response.data], { type: format === "csv" ? "text/csv" : "application/json" });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = format === "csv" ? "strategy_allocation_export.csv" : "strategy_allocation_export.json";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      const filterText = selectedStrategyIds.length > 0 ? ` · filter=${selectedStrategyIds.length} strategy` : "";
      const traceId = response?.headers?.["x-export-trace-id"];
      toast.success(`${format.toUpperCase()} export hazır${filterText}${traceId ? ` · trace=${traceId}` : ""}`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Export başarısız");
    }
  };

  const runWhatIfSimulation = async () => {
    toast.info("Pure Live modunda what-if simulation kaldırıldı.");
  };

  const submitBulkUpdate = async (options = {}) => {
    if (isOpsReadOnly) {
      toast.error("ops role read-only");
      return;
    }
    const note = ensureReasonNote();
    if (!note) return;

    if (!options.fromRetry) {
      setPendingRetryAction({ type: "bulk" });
    }

    if (selectedStrategyIds.length === 0) {
      toast.error("Bulk update için en az bir strategy seçin");
      return;
    }

    const invalid = selectedStrategyIds.find((strategyId) => getRowErrors(strategyId).length > 0);
    if (invalid) {
      const firstError = getRowErrors(invalid)[0] || "Seçili satırlarda validasyon hatası var";
      setGlobalActionError(firstError);
      toast.error(firstError);
      return;
    }

    setIsBulkSubmitting(true);
    setGlobalActionError("");
    try {
      const { data } = await apiClient.post("/admin/strategy-allocation/bulk-update", {
        updates: selectedStrategyIds.map((strategyId) => {
          const draft = drafts[strategyId] || {};
          const sourceRow = rows.find((row) => row.strategy_id === strategyId);
          return {
            strategy_id: strategyId,
            expected_revision: Number(draft.expected_revision || sourceRow?.revision_id || 1),
            capital_weight: Number(draft.capital_weight),
            max_capital: Number(draft.max_capital),
            current_capital: Number(draft.current_capital),
            state: draft.state,
            confirm_primary: draft.confirm_primary || undefined,
            confirm_secondary: draft.confirm_secondary || undefined,
          };
        }),
        auto_normalize: bulkAutoNormalize,
        reason_note: note,
      });
      if (data?.status === "pending_approval") {
        toast.success(data?.message || "Bulk update onaya gönderildi");
        setPendingRetryAction(null);
        await load();
        return;
      }
      toast.success(`Bulk update tamamlandı (${selectedStrategyIds.length} strategy)`);
      setRevisionConflict(null);
      const enforcedRows = data?.enforced_reduce_rows || [];
      if (enforcedRows.length > 0) {
        toast.warning(`Critical drawdown auto-reduce uygulandı (${enforcedRows.length} strategy)`);
      }
      setPendingRetryAction(null);
      await load();
    } catch (error) {
      handleConflictError(error, "Bulk update başarısız");
    } finally {
      setIsBulkSubmitting(false);
    }
  };

  const approveRequest = async (requestId) => {
    if (!isSuperAdmin) {
      toast.error("super_admin_only");
      return;
    }
    const reviewNote = String(approvalReviewNote || "").trim();
    if (!reviewNote) {
      toast.error("approval review note zorunlu");
      return;
    }

    try {
      const { data } = await apiClient.post(`/admin/strategy-allocation/approval-requests/${requestId}/approve`, {
        reason_note: reviewNote,
      });
      toast.success(data?.message || `Request approved: ${requestId}`);
      setRevisionConflict(null);
      await load();
    } catch (error) {
      handleConflictError(error, "Approval approve başarısız");
    }
  };

  const rejectRequest = async (requestId) => {
    if (!isSuperAdmin) {
      toast.error("super_admin_only");
      return;
    }
    const reviewNote = String(approvalReviewNote || "").trim();
    if (!reviewNote) {
      toast.error("approval review note zorunlu");
      return;
    }

    try {
      const { data } = await apiClient.post(`/admin/strategy-allocation/approval-requests/${requestId}/reject`, {
        reason_note: reviewNote,
      });
      toast.success(data?.message || `Request rejected: ${requestId}`);
      await load();
    } catch (error) {
      toast.error(getApiDetailMessage(error, "Approval reject başarısız"));
    }
  };

  const revertApprovalRequest = async (item) => {
    if (!item?.request_id) {
      toast.error("Geçersiz request");
      return;
    }
    if (isOpsReadOnly) {
      toast.error("ops role read-only");
      return;
    }
    const defaultReason = `revert_${item.request_id}`;
    const input = window.prompt("Revert reason (min 8 karakter)", defaultReason);
    if (input === null) return;
    const reason = String(input || "").trim();
    if (reason.length < 8) {
      toast.error("revert reason minimum 8 karakter olmalı");
      return;
    }

    try {
      const { data } = await apiClient.post(`/admin/strategy-allocation/approval-requests/${item.request_id}/revert`, {
        reason_note: reason,
      });
      if (String(data?.status || "").toLowerCase().includes("pending")) {
        toast.success(data?.message || "Revert isteği onaya gönderildi");
      } else {
        toast.success(data?.message || "Revert tamamlandı");
      }
      await load();
    } catch (error) {
      toast.error(getApiDetailMessage(error, "Revert başarısız"));
    }
  };

  if (isLoading) {
    return <LoadingSkeleton rows={8} testId="admin-strategy-allocation-loading-skeleton" />;
  }

  if (loadError && rows.length === 0) {
    return (
      <section className="space-y-4" data-testid="admin-strategy-allocation-broken-state">
        <div className="border border-rose-500/40 bg-rose-900/20 p-4" data-testid="admin-strategy-allocation-broken-alert">
          <p className="text-sm font-semibold text-rose-200" data-testid="admin-strategy-allocation-broken-title">Strategy allocation verisi alınamadı</p>
          <p className="mt-1 text-sm text-rose-100" data-testid="admin-strategy-allocation-broken-message">{loadError}</p>
          <Button className="mt-3" onClick={load} data-testid="admin-strategy-allocation-broken-retry-button">Tekrar Dene</Button>
        </div>
      </section>
    );
  }

  return (
    <section className="grid grid-cols-12 gap-4" data-testid="admin-strategy-allocation-page">
      <header className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-allocation-header">
        <div className="flex flex-wrap items-start justify-between gap-3" data-testid="admin-strategy-allocation-header-row">
          <div data-testid="admin-strategy-allocation-header-left">
            <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="admin-strategy-allocation-title">Strategy Allocation Dashboard</h2>
            <p className="mt-2 text-sm text-slate-400" data-testid="admin-strategy-allocation-description">Capital usage, confidence, aktif/pasif kontrol paneli (12 hazır strateji).</p>
            <p className="mt-1 text-xs text-slate-500" data-testid="admin-strategy-allocation-last-updated">Son güncelleme: {lastUpdatedAt ? new Date(lastUpdatedAt).toLocaleString() : "-"}</p>
          </div>
          <Button onClick={load} data-testid="admin-strategy-allocation-refresh-button">Yenile</Button>
        </div>
      </header>

      {loadError && (
        <div className="col-span-12 border border-amber-500/40 bg-amber-950/20 p-3 text-sm text-amber-200" data-testid="admin-strategy-allocation-warning-alert">
          Son yenileme sırasında hata oluştu: {loadError}
        </div>
      )}

      {globalActionError && (
        <div className="col-span-12 border border-rose-500/40 bg-rose-950/20 p-3 text-sm text-rose-200" data-testid="admin-strategy-allocation-action-error-alert">
          İşlem hatası: {globalActionError}
        </div>
      )}

      {revisionConflict && (
        <div className="col-span-12 border border-amber-500/40 bg-amber-950/20 p-3 text-sm text-amber-100" data-testid="admin-strategy-allocation-revision-conflict-banner">
          <p data-testid="admin-strategy-allocation-revision-conflict-message">{revisionConflict.message}</p>
          {(revisionConflict.conflicts || []).slice(0, 3).map((conflict, index) => (
            <p key={`${conflict.strategy_id || "unknown"}-${index}`} className="mt-1 text-xs text-amber-200" data-testid={`admin-strategy-allocation-revision-conflict-item-${index}`}>
              {conflict.strategy_id || "unknown"}: beklenen={String(conflict.expected_revision)} · güncel={String(conflict.current_revision)}
            </p>
          ))}
          <div className="mt-2 flex flex-wrap gap-2" data-testid="admin-strategy-allocation-revision-conflict-actions">
            <Button
              variant="outline"
              onClick={() => applyRevisionConflictsToDrafts(revisionConflict.conflicts || [])}
              data-testid="admin-strategy-allocation-revision-conflict-apply-button"
            >
              Revision güncellemelerini uygula
            </Button>
            <Button
              variant="outline"
              onClick={resolveRevisionConflictAndRetry}
              data-testid="admin-strategy-allocation-revision-conflict-retry-button"
            >
              Uygula + son işlemi tekrar dene
            </Button>
            <Button className="" variant="outline" onClick={load} data-testid="admin-strategy-allocation-revision-conflict-reload-button">
              En güncel halini yükle
            </Button>
          </div>
        </div>
      )}

      {driftOverrideNotice && (
        <div className="col-span-12 border border-amber-500/40 bg-amber-950/20 p-3 text-sm text-amber-100" data-testid="admin-strategy-allocation-drift-override-banner">
          {driftOverrideNotice}
        </div>
      )}

      <div className="col-span-12 border border-slate-800 bg-slate-900 p-3" data-testid="admin-strategy-allocation-governance-note-panel">
        <p className="text-xs text-slate-300" data-testid="admin-strategy-allocation-role-text">role={role || "unknown"}</p>
        {isOpsReadOnly && (
          <p className="text-xs text-amber-300" data-testid="admin-strategy-allocation-ops-readonly-text">ops role read-only: write işlemleri devre dışı.</p>
        )}
        {role === "admin" && (
          <p className="text-xs text-cyan-300" data-testid="admin-strategy-allocation-admin-request-only-text">admin request-only: write işlemleri approval kuyruğuna gider.</p>
        )}
        <Input
          className="mt-2"
          placeholder="Reason note (tüm write aksiyonları için zorunlu)"
          value={reasonNote}
          onChange={(event) => setReasonNote(event.target.value)}
          data-testid="admin-strategy-allocation-reason-note-input"
        />
      </div>

      <div className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-allocation-health-panel">
        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="admin-strategy-allocation-health-header-row">
          <div>
            <h3 className="text-base font-semibold" data-testid="admin-strategy-allocation-health-title">Health (Sistem Sağlığı)</h3>
            <p className="text-xs text-slate-400" data-testid="admin-strategy-allocation-health-subtitle">API latency, DB pool, queue depth, error rate, exchange bağlantısı, scanner freshness</p>
          </div>
          <div className="flex flex-wrap items-center gap-2" data-testid="admin-strategy-allocation-health-actions">
            <span className={`inline-flex rounded-full border px-2 py-1 text-xs font-semibold ${wsBadgeClass(wsConnectionStatus)}`} data-testid="admin-strategy-allocation-ws-health-badge">
              WS: {wsConnectionStatus.toUpperCase()}
            </span>
            <Button variant="outline" onClick={() => loadHealthSnapshot()} data-testid="admin-strategy-allocation-health-refresh-button">
              {isHealthLoading ? "Health yenileniyor..." : "Health Yenile"}
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                wsManualCloseRef.current = true;
                closeRealtimeSocket();
                wsManualCloseRef.current = false;
                connectRealtimeSocket();
              }}
              data-testid="admin-strategy-allocation-ws-reconnect-button"
            >
              WS Yeniden Bağlan
            </Button>
          </div>
        </div>

        <div className="mt-3 grid gap-3 md:grid-cols-3" data-testid="admin-strategy-allocation-health-grid">
          <article className="rounded border border-slate-800 bg-slate-950 p-3" data-testid="admin-strategy-allocation-health-latency-card">
            <p className="text-xs text-slate-400" data-testid="admin-strategy-allocation-health-latency-label">API Latency</p>
            <p className="text-lg font-semibold" data-testid="admin-strategy-allocation-health-latency-value">{Number(healthCore?.api_latency_ms || 0).toFixed(2)} ms</p>
          </article>
          <article className="rounded border border-slate-800 bg-slate-950 p-3" data-testid="admin-strategy-allocation-health-queue-card">
            <p className="text-xs text-slate-400" data-testid="admin-strategy-allocation-health-queue-label">Queue Depth</p>
            <p className="text-lg font-semibold" data-testid="admin-strategy-allocation-health-queue-value">{Number(healthCore?.queue_depth || 0)}</p>
          </article>
          <article className="rounded border border-slate-800 bg-slate-950 p-3" data-testid="admin-strategy-allocation-health-error-card">
            <p className="text-xs text-slate-400" data-testid="admin-strategy-allocation-health-error-label">Error Rate (5m)</p>
            <p className="text-lg font-semibold" data-testid="admin-strategy-allocation-health-error-value">{Number(healthCore?.error_rate_5m || 0).toFixed(4)}</p>
          </article>
          <article className="rounded border border-slate-800 bg-slate-950 p-3" data-testid="admin-strategy-allocation-health-dbpool-card">
            <p className="text-xs text-slate-400" data-testid="admin-strategy-allocation-health-dbpool-label">DB Pool</p>
            <p className="text-sm" data-testid="admin-strategy-allocation-health-dbpool-value">
              size={Number(healthCore?.db_pool?.configured_pool_size || 0)} · overflow={Number(healthCore?.db_pool?.configured_max_overflow || 0)}
            </p>
            <p className="text-[11px] text-slate-400" data-testid="admin-strategy-allocation-health-db-runtime-value">
              reachable={String(Boolean(healthCore?.db_pool?.runtime?.reachable))} · initialized={String(Boolean(healthCore?.db_pool?.runtime?.initialized))}
            </p>
          </article>
          <article className="rounded border border-slate-800 bg-slate-950 p-3" data-testid="admin-strategy-allocation-health-exchange-card">
            <p className="text-xs text-slate-400" data-testid="admin-strategy-allocation-health-exchange-label">Exchange Connectivity</p>
            <p className="text-sm" data-testid="admin-strategy-allocation-health-exchange-value">
              status={String(exchangeConnectivity?.status || "unknown")} · spot={String(Boolean(exchangeConnectivity?.spot_connected))} · futures={String(Boolean(exchangeConnectivity?.futures_connected))}
            </p>
          </article>
          <article className="rounded border border-slate-800 bg-slate-950 p-3" data-testid="admin-strategy-allocation-health-freshness-card">
            <p className="text-xs text-slate-400" data-testid="admin-strategy-allocation-health-freshness-label">Scanner Freshness</p>
            <p className="text-sm" data-testid="admin-strategy-allocation-health-freshness-value">
              status={String(scannerFreshness?.status || "unknown")} · age={scannerFreshness?.seconds_since_last_scan ?? "-"}s
            </p>
            <p className="text-[11px] text-slate-400" data-testid="admin-strategy-allocation-health-freshness-ts-value">
              last={scannerFreshness?.last_generated_at || "-"}
            </p>
          </article>
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-slate-400" data-testid="admin-strategy-allocation-health-meta-row">
          <span data-testid="admin-strategy-allocation-ws-retry-count">ws_retry={wsRetryCount}</span>
          <span data-testid="admin-strategy-allocation-ws-last-message">ws_last_message={wsLastMessageAt || "-"}</span>
          <span data-testid="admin-strategy-allocation-health-status">health_status={String(healthSnapshot?.status || "unknown")}</span>
          {wsErrorMessage && <span className="text-amber-300" data-testid="admin-strategy-allocation-ws-error-message">ws_error={wsErrorMessage}</span>}
        </div>

        <div className="mt-3 rounded border border-slate-800 bg-slate-950 p-3" data-testid="admin-strategy-allocation-explainability-panel">
          <div className="flex flex-wrap items-center justify-between gap-2" data-testid="admin-strategy-allocation-explainability-header-row">
            <h4 className="text-sm font-semibold" data-testid="admin-strategy-allocation-explainability-title">Explainability + Trace Spine</h4>
            <div className="flex items-center gap-2" data-testid="admin-strategy-allocation-explainability-actions">
              <select
                value={selectedExplainStrategyId}
                onChange={(event) => setSelectedExplainStrategyId(event.target.value)}
                className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs"
                data-testid="admin-strategy-allocation-explainability-strategy-select"
              >
                {rows.map((item) => (
                  <option key={item.strategy_id} value={item.strategy_id}>{item.strategy_id}</option>
                ))}
              </select>
              <Button
                variant="outline"
                onClick={() => loadExplainability(selectedExplainStrategyId)}
                data-testid="admin-strategy-allocation-explainability-refresh-button"
              >
                {isExplainabilityLoading ? "Explainability yükleniyor..." : "Explainability Yenile"}
              </Button>
            </div>
          </div>

          <div className="mt-2 grid gap-2 md:grid-cols-2" data-testid="admin-strategy-allocation-explainability-summary-grid">
            <p className="text-xs text-slate-300" data-testid="admin-strategy-allocation-explainability-signal-count">signal_count={Number(explainabilityData?.signal_count || 0)}</p>
            <p className="text-xs text-slate-300" data-testid="admin-strategy-allocation-explainability-risk-block-count">risk_blocked_count={Number(explainabilityData?.risk_blocked_count || 0)}</p>
          </div>

          <div className="mt-2 max-h-40 overflow-y-auto rounded border border-slate-800 p-2" data-testid="admin-strategy-allocation-explainability-top-reasons-list">
            {(explainabilityData?.top_reason_codes || []).length === 0 && (
              <p className="text-xs text-slate-500" data-testid="admin-strategy-allocation-explainability-top-reasons-empty">No reason data</p>
            )}
            {(explainabilityData?.top_reason_codes || []).map((item, index) => (
              <p key={`${item.code}-${index}`} className="text-xs text-slate-300" data-testid={`admin-strategy-allocation-explainability-top-reason-${index}`}>
                {item.code} · count={item.count}
              </p>
            ))}
          </div>

          <div className="mt-2 max-h-56 overflow-y-auto rounded border border-slate-800 p-2" data-testid="admin-strategy-allocation-trace-spine-list">
            {traceSpineRows.length === 0 && (
              <p className="text-xs text-slate-500" data-testid="admin-strategy-allocation-trace-spine-empty">Trace spine verisi yok.</p>
            )}
            {traceSpineRows.map((row, index) => (
              <div key={`${row.trade_id || row.signal_id || index}-${index}`} className="mb-1 rounded border border-slate-800 bg-slate-900 p-2" data-testid={`admin-strategy-allocation-trace-spine-item-${index}`}>
                <p className="text-xs text-cyan-200" data-testid={`admin-strategy-allocation-trace-spine-item-main-${index}`}>
                  {row.symbol || "-"} · {row.status || "-"}
                </p>
                <p className="text-[11px] text-slate-300" data-testid={`admin-strategy-allocation-trace-spine-item-chain-${index}`}>
                  signal={row.signal_id || "-"} → decision={row.decision_card_id || "-"} → intent={row.intent_id || "-"} → trade={row.trade_id || "-"} → exec={row.execution_trace_id || "-"}
                </p>
                <p className="text-[10px] text-slate-500" data-testid={`admin-strategy-allocation-trace-spine-item-run-${index}`}>
                  scan_run={row.scan_run_id || "-"} · created_at={row.created_at || "-"}
                </p>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-2 rounded border border-slate-800 bg-slate-950 p-2" data-testid="admin-strategy-allocation-debug-events-panel">
          <p className="text-xs font-semibold text-slate-300" data-testid="admin-strategy-allocation-debug-events-title">Realtime Debug Events</p>
          <div className="mt-1 max-h-28 overflow-y-auto" data-testid="admin-strategy-allocation-debug-events-list">
            {(healthDebug?.recent_allocation_events || []).length === 0 && (
              <p className="text-xs text-slate-500" data-testid="admin-strategy-allocation-debug-events-empty">No data yet</p>
            )}
            {(healthDebug?.recent_allocation_events || []).map((event, index) => (
              <p key={`${event.trace_id || index}-${index}`} className="text-xs text-slate-300" data-testid={`admin-strategy-allocation-debug-event-${index}`}>
                {event.timestamp || "-"} · {event.action_type || "-"} · admin={event.admin_id || "-"} · trace={event.trace_id || "-"}
              </p>
            ))}
          </div>
        </div>
      </div>

      <div className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-allocation-safety-layer-panel">
        <div className="flex flex-wrap items-center gap-2" data-testid="admin-strategy-allocation-safety-layer-actions">
          <Button onClick={normalizeWeights} disabled={isNormalizing || isOpsReadOnly} data-testid="admin-strategy-allocation-normalize-button">
            {isNormalizing ? "Normalizing..." : "Auto Normalize (Weight=1)"}
          </Button>
          <Button onClick={submitBulkUpdate} disabled={isBulkSubmitting || selectedStrategyIds.length === 0 || isOpsReadOnly} data-testid="admin-strategy-allocation-bulk-save-button">
            {isBulkSubmitting ? "Bulk kaydediliyor..." : `Seçilenleri Toplu Kaydet (${selectedStrategyIds.length})`}
          </Button>
          <Button onClick={generateRebalanceSuggestion} disabled={isGeneratingRebalance} data-testid="admin-strategy-allocation-generate-rebalance-button">
            {isGeneratingRebalance ? "Öneri üretiliyor..." : "Rebalance Önerisi Üret"}
          </Button>
          <Button
            variant="outline"
            onClick={applyRebalanceSuggestionToDraft}
            disabled={!rebalanceSuggestion || selectedStrategyIds.length === 0}
            data-testid="admin-strategy-allocation-apply-rebalance-button"
          >
            Öneriyi Seçili Draft’a Uygula
          </Button>
          <label className="inline-flex items-center gap-2 text-xs text-slate-300" data-testid="admin-strategy-allocation-bulk-auto-normalize-label">
            <input
              type="checkbox"
              checked={bulkAutoNormalize}
              onChange={(event) => setBulkAutoNormalize(event.target.checked)}
              data-testid="admin-strategy-allocation-bulk-auto-normalize-checkbox"
            />
            Bulk sonrası auto-normalize
          </label>
        </div>

        <div className="mt-3 grid gap-3 md:grid-cols-4" data-testid="admin-strategy-allocation-capital-governance-grid">
          <article className="border border-slate-800 bg-slate-950 p-3" data-testid="admin-strategy-allocation-governance-total-weight-card">
            <p className="text-xs text-slate-400">Toplam Weight</p>
            <p className={`text-xl font-semibold ${weightIsBalanced ? "text-emerald-400" : "text-rose-400"}`} data-testid="admin-strategy-allocation-governance-total-weight-value">
              {capitalSnapshot.totalWeight.toFixed(6)}
            </p>
          </article>
          <article className="border border-slate-800 bg-slate-950 p-3" data-testid="admin-strategy-allocation-governance-total-capital-card">
            <p className="text-xs text-slate-400">Total Capital</p>
            <p className="text-xl font-semibold" data-testid="admin-strategy-allocation-governance-total-capital-value">{formatMoney(capitalSnapshot.totalCapital)}</p>
          </article>
          <article className="border border-slate-800 bg-slate-950 p-3" data-testid="admin-strategy-allocation-governance-used-capital-card">
            <p className="text-xs text-slate-400">Used Capital</p>
            <p className="text-xl font-semibold text-amber-400" data-testid="admin-strategy-allocation-governance-used-capital-value">{formatMoney(capitalSnapshot.usedCapital)}</p>
          </article>
          <article className="border border-slate-800 bg-slate-950 p-3" data-testid="admin-strategy-allocation-governance-available-capital-card">
            <p className="text-xs text-slate-400">Available Capital</p>
            <p className="text-xl font-semibold text-cyan-300" data-testid="admin-strategy-allocation-governance-available-capital-value">{formatMoney(capitalSnapshot.availableCapital)}</p>
          </article>
        </div>

        {!weightIsBalanced && (
          <div className="mt-3 border border-rose-500/40 bg-rose-950/20 p-3 text-sm text-rose-200" data-testid="admin-strategy-allocation-weight-warning-alert">
            Toplam weight 1 olmalı. Delta: {capitalSnapshot.weightDelta.toFixed(6)}
          </div>
        )}
        {hasOverAllocation && (
          <div className="mt-3 border border-rose-500/40 bg-rose-950/20 p-3 text-sm text-rose-200" data-testid="admin-strategy-allocation-over-allocation-warning-alert">
            Over-allocation tespit edildi: {capitalSnapshot.overAllocatedRows.map((row) => row.strategy_id).join(", ")}
          </div>
        )}

        {backendSummary && (
          <div className="mt-2 space-y-2" data-testid="admin-strategy-allocation-risk-binding-panel">
            <p className="text-xs text-slate-400" data-testid="admin-strategy-allocation-backend-summary-text">
              Backend snapshot → weight={backendSummary.total_weight} · used={backendSummary.used_capital} · available={backendSummary.available_capital} · over_allocated={backendSummary.over_allocated_count}
            </p>
            <p className="text-xs text-slate-300" data-testid="admin-strategy-allocation-risk-exposure-line">
              Exposure={backendSummary.total_exposure_ratio_pct}% · warning threshold={backendSummary.exposure_warning_threshold_pct}%
            </p>
            {backendSummary.exposure_warning_state === "WARNING" && (
              <div className="border border-amber-500/40 bg-amber-950/20 p-2 text-xs text-amber-100" data-testid="admin-strategy-allocation-risk-exposure-warning">
                Exposure warning: used/total capital oranı {backendSummary.exposure_warning_threshold_pct}% üstünde.
              </div>
            )}

            <div className="rounded border border-slate-800 bg-slate-950 p-2" data-testid="admin-strategy-allocation-drawdown-candidates-panel">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs text-slate-300" data-testid="admin-strategy-allocation-drawdown-candidates-title">
                  Drawdown candidates (threshold {backendSummary.drawdown_threshold_pct}% / enforce {backendSummary.drawdown_enforce_threshold_pct}%)
                </p>
                <Button size="sm" variant="outline" onClick={applyDrawdownSuggestionsToForm} data-testid="admin-strategy-allocation-apply-drawdown-suggestion-button">
                  Önerilen Reduce’u Forma Uygula
                </Button>
              </div>
              <div className="mt-2 space-y-1" data-testid="admin-strategy-allocation-drawdown-candidates-list">
                {(backendSummary.drawdown_candidates || []).length === 0 && (
                  <p className="text-xs text-slate-500" data-testid="admin-strategy-allocation-drawdown-candidates-empty">No data yet</p>
                )}
                {(backendSummary.drawdown_candidates || []).map((candidate, index) => (
                  <p key={`${candidate.strategy_id}-${index}`} className="text-xs text-slate-300" data-testid={`admin-strategy-allocation-drawdown-candidate-${index}`}>
                    {candidate.strategy_id} · drawdown={candidate.drawdown_pct}% · suggested={candidate.suggested_reduced_capital}
                    {candidate.enforced_required ? " · CRITICAL" : " · suggestion"}
                  </p>
                ))}
              </div>
            </div>

            <div className="rounded border border-slate-800 bg-slate-950 p-2" data-testid="admin-strategy-allocation-rebalance-preview-panel">
              <p className="text-xs text-slate-300" data-testid="admin-strategy-allocation-rebalance-preview-title">
                Rule-based Rebalance Suggestion (confidence/performance/decay)
              </p>
              {!rebalanceSuggestion && (
                <p className="mt-1 text-xs text-slate-500" data-testid="admin-strategy-allocation-rebalance-preview-empty">No data yet</p>
              )}
              {rebalanceSuggestion && (
                <div className="mt-1 space-y-1" data-testid="admin-strategy-allocation-rebalance-preview-list">
                  <p className="text-xs text-slate-400" data-testid="admin-strategy-allocation-rebalance-preview-meta">
                    trace={rebalanceSuggestion.trace_id} · selection_count={rebalanceSuggestion.selection_count} · budget={rebalanceSuggestion.applied_budget}
                  </p>
                  {(rebalanceSuggestion.suggestions || []).map((row, index) => (
                    <div key={`${row.strategy_id}-${index}`} className="flex flex-wrap items-center gap-2 text-xs text-slate-300" data-testid={`admin-strategy-allocation-rebalance-preview-row-${index}`}>
                      <span data-testid={`admin-strategy-allocation-rebalance-preview-row-strategy-${index}`}>{row.strategy_id}</span>
                      <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${confidenceBandClass(confidenceBand(row.confidence))}`} data-testid={`admin-strategy-allocation-rebalance-confidence-band-${index}`}>
                        {confidenceBand(row.confidence)}
                      </span>
                      <span data-testid={`admin-strategy-allocation-rebalance-preview-row-values-${index}`}>
                        {row.current_weight} → {row.suggested_weight} (Δ {row.delta})
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-allocation-phase6-panel">
        <h3 className="text-base font-semibold" data-testid="admin-strategy-allocation-phase6-title">Phase 6 · Snapshot + Export</h3>
        <div className="mt-2 flex flex-wrap gap-2" data-testid="admin-strategy-allocation-phase6-actions">
          <Button onClick={createSnapshot} disabled={isCreatingSnapshot || isOpsReadOnly} data-testid="admin-strategy-allocation-create-snapshot-button">
            {isCreatingSnapshot ? "Snapshot alınıyor..." : "Snapshot Al"}
          </Button>
          <Button variant="outline" onClick={() => exportAllocation("json")} data-testid="admin-strategy-allocation-export-json-button">
            JSON Export
          </Button>
          <Button variant="outline" onClick={() => exportAllocation("csv")} data-testid="admin-strategy-allocation-export-csv-button">
            CSV Export
          </Button>
          <Button variant="outline" onClick={runWhatIfSimulation} data-testid="admin-strategy-allocation-run-whatif-button">
            Simulation Kaldırıldı
          </Button>
        </div>

        <div className="mt-2 grid gap-2 md:grid-cols-3" data-testid="admin-strategy-allocation-export-metadata-input-grid">
          <Input
            placeholder="Export related_request_id (opsiyonel)"
            value={exportRelatedRequestId}
            onChange={(event) => setExportRelatedRequestId(event.target.value)}
            data-testid="admin-strategy-allocation-export-related-request-input"
          />
          <Input
            placeholder="Export snapshot_id (opsiyonel)"
            value={exportSnapshotId}
            onChange={(event) => setExportSnapshotId(event.target.value)}
            data-testid="admin-strategy-allocation-export-snapshot-id-input"
          />
          <p className="text-xs text-slate-500" data-testid="admin-strategy-allocation-export-filter-note">
            Export filtresi: {selectedStrategyIds.length > 0 ? `${selectedStrategyIds.length} strategy seçili` : "tümü"}
          </p>
        </div>

        <div className="mt-3 grid gap-3 md:grid-cols-2" data-testid="admin-strategy-allocation-phase6-grid">
          <div className="rounded border border-slate-800 bg-slate-950 p-2" data-testid="admin-strategy-allocation-phase6-snapshot-list-panel">
            <p className="text-xs text-slate-300" data-testid="admin-strategy-allocation-phase6-snapshot-list-title">Snapshots</p>
            {(snapshots || []).length === 0 && (
              <p className="mt-1 text-xs text-slate-500" data-testid="admin-strategy-allocation-phase6-snapshot-empty">No data yet</p>
            )}
            {(snapshots || []).slice(0, 5).map((snapshot, index) => (
              <div key={`${snapshot.snapshot_id}-${index}`} className="mt-1 rounded border border-slate-800 bg-slate-900 p-2 text-xs" data-testid={`admin-strategy-allocation-phase6-snapshot-item-${index}`}>
                <p data-testid={`admin-strategy-allocation-phase6-snapshot-item-id-${index}`}>{snapshot.snapshot_id}</p>
                <p className="text-slate-400" data-testid={`admin-strategy-allocation-phase6-snapshot-item-metadata-${index}`}>
                  {new Date(snapshot.created_at).toLocaleString()} · by={snapshot.created_by} · reason={snapshot.reason_note || "-"}
                </p>
                <p className="text-slate-400" data-testid={`admin-strategy-allocation-phase6-snapshot-item-stats-${index}`}>
                  count={snapshot.strategy_count} · weight={snapshot.total_weight} · used={snapshot.used_capital}
                </p>
                <div className="mt-1 flex items-center gap-2" data-testid={`admin-strategy-allocation-phase6-snapshot-item-actions-${index}`}>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => openRestoreModal(snapshot)}
                    disabled={isOpsReadOnly}
                    data-testid={`admin-strategy-allocation-phase6-snapshot-restore-button-${index}`}
                  >
                    {isSuperAdmin ? "Restore Now" : "Restore Request"}
                  </Button>
                  {snapshot.restored_at && (
                    <span className="text-[10px] text-emerald-300" data-testid={`admin-strategy-allocation-phase6-snapshot-restored-tag-${index}`}>
                      restored_at={new Date(snapshot.restored_at).toLocaleString()}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>

          <div className="rounded border border-slate-800 bg-slate-950 p-2" data-testid="admin-strategy-allocation-phase6-whatif-preview-panel">
            <p className="text-xs text-slate-300" data-testid="admin-strategy-allocation-phase6-whatif-preview-title">Simulation Paneli Kaldırıldı</p>
            <p className="mt-1 text-xs text-slate-500" data-testid="admin-strategy-allocation-phase6-whatif-empty">Pure Live politikasında simulation endpointleri 410 döner.</p>
          </div>
        </div>
      </div>

      <div className="col-span-12 grid gap-3 md:grid-cols-3" data-testid="admin-strategy-allocation-summary-grid">
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-strategy-allocation-summary-total">
          <p className="text-xs text-slate-500">Toplam Strategy</p>
          <p className="text-xl font-semibold">{stateStats.total}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-strategy-allocation-summary-active">
          <p className="text-xs text-slate-500">AKTİF</p>
          <p className="text-xl font-semibold text-emerald-400">{stateStats.active}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-strategy-allocation-summary-passive">
          <p className="text-xs text-slate-500">PASİF</p>
          <p className="text-xl font-semibold text-rose-400">{stateStats.passive}</p>
        </article>
      </div>

      <div className="col-span-12 overflow-x-auto border border-slate-800 bg-slate-900" data-testid="admin-strategy-allocation-table-wrapper">
        <table className="min-w-full text-sm" data-testid="admin-strategy-allocation-table">
          <thead className="bg-slate-800 text-left" data-testid="admin-strategy-allocation-table-head">
            <tr>
              <th className="px-3 py-2">Select</th>
              <th className="px-3 py-2">Strategy</th>
              <th className="px-3 py-2">Weight</th>
              <th className="px-3 py-2">Max Capital</th>
              <th className="px-3 py-2">Current Capital</th>
              <th className="px-3 py-2">State</th>
              <th className="px-3 py-2">Exposure %</th>
              <th className="px-3 py-2">Drawdown %</th>
              <th className="px-3 py-2">Confidence</th>
              <th className="px-3 py-2">Performance</th>
              <th className="px-3 py-2">Signal Decay</th>
              <th className="px-3 py-2">Execution Quality</th>
              <th className="px-3 py-2">Compare</th>
              <th className="px-3 py-2">Action</th>
            </tr>
          </thead>
          <tbody data-testid="admin-strategy-allocation-table-body">
            {rows.map((item) => {
              const draft = drafts[item.strategy_id] || {};
              const rowErrors = getRowErrors(item.strategy_id);
              return (
                <tr
                  key={item.strategy_id}
                  className="border-t border-slate-800"
                  data-testid={`admin-strategy-allocation-row-${item.strategy_id}`}
                >
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={selectedStrategyIds.includes(item.strategy_id)}
                      onChange={() => toggleSelection(item.strategy_id)}
                      data-testid={`admin-strategy-allocation-row-select-checkbox-${item.strategy_id}`}
                    />
                  </td>
                  <td className="px-3 py-2" data-testid={`admin-strategy-allocation-strategy-${item.strategy_id}`}>
                    <p>{item.strategy_id}</p>
                    <p className="text-[10px] text-slate-500" data-testid={`admin-strategy-allocation-revision-${item.strategy_id}`}>
                      revision={item.revision_id}
                    </p>
                  </td>
                  <td className="px-3 py-2"><Input value={draft.capital_weight ?? ""} type="number" min="0" max="1" step="0.0001" onChange={(event) => updateDraft(item.strategy_id, "capital_weight", event.target.value)} data-testid={`admin-strategy-allocation-weight-input-${item.strategy_id}`} disabled={!isEditing(item.strategy_id) || isOpsReadOnly} /></td>
                  <td className="px-3 py-2"><Input value={draft.max_capital ?? ""} type="number" min="0" step="0.01" onChange={(event) => updateDraft(item.strategy_id, "max_capital", event.target.value)} data-testid={`admin-strategy-allocation-max-capital-input-${item.strategy_id}`} disabled={!isEditing(item.strategy_id) || isOpsReadOnly} /></td>
                  <td className="px-3 py-2"><Input value={draft.current_capital ?? ""} type="number" min="0" step="0.01" onChange={(event) => updateDraft(item.strategy_id, "current_capital", event.target.value)} data-testid={`admin-strategy-allocation-current-capital-input-${item.strategy_id}`} disabled={!isEditing(item.strategy_id) || isOpsReadOnly} /></td>
                  <td className="px-3 py-2">
                    <select className="w-full border border-slate-700 bg-slate-950 px-2 py-1" value={draft.state || "ACTIVE"} onChange={(event) => updateDraft(item.strategy_id, "state", event.target.value)} data-testid={`admin-strategy-allocation-state-select-${item.strategy_id}`} disabled={!isEditing(item.strategy_id) || isOpsReadOnly}>
                      <option value="ACTIVE">AKTİF</option>
                      <option value="DISABLED">PASİF</option>
                    </select>
                    <div className="mt-1 flex flex-wrap items-center gap-1" data-testid={`admin-strategy-allocation-state-reason-row-${item.strategy_id}`}>
                      <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${stateReasonBadgeClass(item.state_reason_code)}`} data-testid={`admin-strategy-allocation-state-reason-badge-${item.strategy_id}`}>
                        {item.state_reason_code || "MANUAL_STATE"}
                      </span>
                      <span className="text-[10px] text-slate-300" data-testid={`admin-strategy-allocation-state-reason-inline-${item.strategy_id}`}>
                        {stateReasonInlineText(item)}
                      </span>
                      <TooltipProvider delayDuration={0}>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="cursor-help text-[10px] text-cyan-300" data-testid={`admin-strategy-allocation-state-reason-tooltip-trigger-${item.strategy_id}`}>why?</span>
                          </TooltipTrigger>
                          <TooltipContent side="top" className="max-w-[320px]" data-testid={`admin-strategy-allocation-state-reason-tooltip-${item.strategy_id}`}>
                            <p>{item.state_reason_detail || "No reason"}</p>
                            <p className="mt-1">{item.trend_5d_line || "5g trend unavailable"}</p>
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </div>
                  </td>
                  <td className="px-3 py-2" data-testid={`admin-strategy-allocation-exposure-ratio-${item.strategy_id}`}>{item.exposure_ratio_pct}</td>
                  <td className="px-3 py-2" data-testid={`admin-strategy-allocation-drawdown-pct-${item.strategy_id}`}>{item.drawdown_pct}</td>
                  <td className="px-3 py-2" data-testid={`admin-strategy-allocation-confidence-${item.strategy_id}`}>{item.confidence_score}</td>
                  <td className="px-3 py-2" data-testid={`admin-strategy-allocation-performance-${item.strategy_id}`}>{item.performance_score}</td>
                  <td className="px-3 py-2" data-testid={`admin-strategy-allocation-signal-decay-${item.strategy_id}`}>{item.signal_decay}</td>
                  <td className="px-3 py-2" data-testid={`admin-strategy-allocation-execution-quality-${item.strategy_id}`}>{item.execution_quality_score}</td>
                  <td className="px-3 py-2" data-testid={`admin-strategy-allocation-whatif-cell-${item.strategy_id}`}>
                    <span className="text-xs text-slate-500">Removed in Pure Live</span>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-2" data-testid={`admin-strategy-allocation-actions-${item.strategy_id}`}>
                      {!isEditing(item.strategy_id) ? (
                        <Button variant="outline" onClick={() => startEdit(item.strategy_id)} disabled={isOpsReadOnly} data-testid={`admin-strategy-allocation-edit-button-${item.strategy_id}`}>Düzenle</Button>
                      ) : (
                        <Button variant="outline" onClick={() => cancelEdit(item.strategy_id)} disabled={isOpsReadOnly} data-testid={`admin-strategy-allocation-cancel-button-${item.strategy_id}`}>İptal</Button>
                      )}
                      <Button variant="outline" onClick={() => saveStrategy(item.strategy_id)} disabled={!isEditing(item.strategy_id) || isOpsReadOnly} data-testid={`admin-strategy-allocation-save-button-${item.strategy_id}`}>Kaydet</Button>
                    </div>
                    {rowErrors.length > 0 && (
                      <p className="mt-1 text-xs text-rose-300" data-testid={`admin-strategy-allocation-row-error-${item.strategy_id}`}>{rowErrors[0]}</p>
                    )}
                  </td>
                </tr>
              );
            })}
            {rows.length === 0 && (
              <tr className="border-t border-slate-800" data-testid="admin-strategy-allocation-empty-row">
                <td colSpan={14} className="px-3 py-4 text-center text-sm text-slate-400" data-testid="admin-strategy-allocation-empty-text">Strategy allocation kaydı bulunamadı.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-allocation-approval-panel">
        <h3 className="text-base font-semibold" data-testid="admin-strategy-allocation-approval-title">Approval Requests</h3>
        <Input
          className="mt-2"
          placeholder="Approval review note (super_admin approve/reject)"
          value={approvalReviewNote}
          onChange={(event) => setApprovalReviewNote(event.target.value)}
          data-testid="admin-strategy-allocation-approval-review-note-input"
        />
        <div className="mt-2 space-y-1" data-testid="admin-strategy-allocation-approval-list">
          {approvalRequests.length === 0 && (
            <p className="text-sm text-slate-400" data-testid="admin-strategy-allocation-approval-empty">No data yet</p>
          )}
          {approvalRequests.map((item, index) => (
            <div key={`${item.request_id}-${index}`} className="rounded border border-slate-800 bg-slate-950 p-2 text-xs" data-testid={`admin-strategy-allocation-approval-item-${index}`}>
              <p data-testid={`admin-strategy-allocation-approval-item-main-${index}`}>
                {item.request_id} · {item.action_type} ({item.request_type || "-"}) ·
                <span className="ml-1 rounded border border-slate-700 px-1 py-0.5 text-[10px]" data-testid={`admin-strategy-allocation-approval-item-status-${index}`}>
                  {approvalStatusLabel(item)}
                </span>
              </p>
              <p data-testid={`admin-strategy-allocation-approval-item-reason-${index}`}>
                requested_by={item.requested_by} ({item.requested_role || "-"}) · reason={item.reason_note}
                <span className="ml-2 rounded border border-slate-700 px-1 py-0.5 text-[10px]" data-testid={`admin-strategy-allocation-approval-item-age-${index}`}>
                  {formatRequestAge(item.created_at, requestAgeTick)}
                </span>
              </p>
              <p data-testid={`admin-strategy-allocation-approval-item-target-${index}`}>
                target={item.target_type || "-"}:{item.target_id || "-"} · revision_count={item.revision_context?.expected_revision_count || 0}
              </p>
              <p className="text-[11px] text-cyan-200" data-testid={`admin-strategy-allocation-approval-item-why-${index}`}>
                Why? {item.explanation_summary || item.decision_factors?.why_this_action || "-"}
              </p>
              <p className="text-[11px] text-slate-400" data-testid={`admin-strategy-allocation-approval-item-expected-${index}`}>
                expected={item.decision_factors?.expected_outcome || "-"}
              </p>
              <p data-testid={`admin-strategy-allocation-approval-item-expiry-${index}`}>
                expires_at={item.expires_at}
              </p>
              {item.source_request_id && (
                <p className="text-[11px] text-amber-300" data-testid={`admin-strategy-allocation-approval-item-source-${index}`}>
                  source_request_id={item.source_request_id}
                </p>
              )}
              {item.linked_revert_request_id && (
                <p className="text-[11px] text-emerald-300" data-testid={`admin-strategy-allocation-approval-item-revert-link-${index}`}>
                  linked_revert_request_id={item.linked_revert_request_id}
                </p>
              )}
              {approvalStatusLabel(item) === "REQUIRES_REVIEW" && (
                <p className="mt-1 text-[11px] text-amber-300" data-testid={`admin-strategy-allocation-approval-item-stale-${index}`}>
                  stale_state={item.stale_state || "STALE"} · conflicts={(item.stale_conflicts || []).length}
                </p>
              )}
              {isSuperAdmin && item.status === "pending" && (
                <div className="mt-1 flex gap-2" data-testid={`admin-strategy-allocation-approval-item-actions-${index}`}>
                  <Button size="sm" variant="outline" onClick={() => approveRequest(item.request_id)} data-testid={`admin-strategy-allocation-approval-approve-button-${index}`}>
                    Approve
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => rejectRequest(item.request_id)} data-testid={`admin-strategy-allocation-approval-reject-button-${index}`}>
                    Reject
                  </Button>
                </div>
              )}
              {!isOpsReadOnly && item.status === "approved" && item.action_type !== "revert_apply" && !item.reverted_at && (
                <div className="mt-1" data-testid={`admin-strategy-allocation-approval-item-revert-actions-${index}`}>
                  <Button size="sm" variant="outline" onClick={() => revertApprovalRequest(item)} data-testid={`admin-strategy-allocation-approval-revert-button-${index}`}>
                    {isSuperAdmin ? "Revert Now" : "Revert Request"}
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {restoreModal.open && (
        <div className="col-span-12 border border-cyan-500/40 bg-slate-950 p-4" data-testid="admin-strategy-allocation-restore-modal">
          <p className="text-sm font-semibold text-cyan-200" data-testid="admin-strategy-allocation-restore-modal-title">
            Snapshot Restore Confirm
          </p>
          <p className="mt-1 text-xs text-slate-300" data-testid="admin-strategy-allocation-restore-modal-snapshot-id">
            snapshot_id={restoreModal.snapshot?.snapshot_id || "-"}
          </p>
          <p className="mt-1 text-xs text-slate-400" data-testid="admin-strategy-allocation-restore-modal-approval-info">
            {isSuperAdmin
              ? "super_admin: Restore Now (approve + execute)"
              : "admin: Restore Request (approval kuyruğuna gider)"}
          </p>
          <Input
            className="mt-2"
            placeholder="Restore reason note"
            value={restoreModal.reason}
            onChange={(event) => setRestoreModal((prev) => ({ ...prev, reason: event.target.value }))}
            data-testid="admin-strategy-allocation-restore-modal-reason-input"
          />
          <div className="mt-2 flex gap-2" data-testid="admin-strategy-allocation-restore-modal-actions">
            <Button
              onClick={submitSnapshotRestore}
              disabled={restoreModal.isSubmitting || isOpsReadOnly}
              data-testid="admin-strategy-allocation-restore-modal-confirm-button"
            >
              {restoreModal.isSubmitting ? "Restore çalışıyor..." : isSuperAdmin ? "Restore Now" : "Restore Request"}
            </Button>
            <Button
              variant="outline"
              onClick={closeRestoreModal}
              disabled={restoreModal.isSubmitting}
              data-testid="admin-strategy-allocation-restore-modal-cancel-button"
            >
              Vazgeç
            </Button>
          </div>
        </div>
      )}

      <div className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-allocation-state-history-panel">
        <h3 className="text-base font-semibold" data-testid="admin-strategy-allocation-state-history-title">State History Log</h3>
        <div className="mt-2 space-y-1" data-testid="admin-strategy-allocation-state-history-list">
          {stateHistory.length === 0 && (
            <p className="text-sm text-slate-400" data-testid="admin-strategy-allocation-state-history-empty">No data yet</p>
          )}
          {stateHistory.map((item, index) => (
            <div key={`${item.trace_id}-${index}`} className="rounded border border-slate-800 bg-slate-950 p-2 text-xs" data-testid={`admin-strategy-allocation-state-history-item-${index}`}>
              <p data-testid={`admin-strategy-allocation-state-history-item-main-${index}`}>
                [{new Date(item.timestamp).toLocaleString()}] {item.strategy_id} · {item.action_type}
              </p>
              <p data-testid={`admin-strategy-allocation-state-history-item-transition-${index}`}>
                {item.previous_state || "-"} → {item.new_state || "-"} · admin={item.admin_id}
              </p>
              <p data-testid={`admin-strategy-allocation-state-history-item-reason-${index}`}>
                reason={item.reason_code || "-"} · detail={item.reason_detail || "-"}
              </p>
              <p data-testid={`admin-strategy-allocation-state-history-item-trace-${index}`}>trace={item.trace_id}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};
