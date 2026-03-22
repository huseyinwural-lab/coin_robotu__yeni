import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";

const WEIGHT_TOLERANCE = 0.0001;
const DOUBLE_CONFIRM_PRIMARY = "CONFIRM";
const DOUBLE_CONFIRM_SECONDARY = "STATE CHANGE";

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
  capital_weight: String(item.capital_weight ?? "0"),
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

const stateReasonInlineText = (row) => {
  if (row?.is_drift_override) return "Manual change overridden by drift rule";
  if (row?.state_reason_code === "AUTO_DISABLED_BY_DRIFT") return "Drift rule: auto disabled";
  if (row?.state_reason_code === "AUTO_THROTTLED_BY_DRIFT") return "Drift rule: auto throttled";
  return "Manual / stable";
};

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
  const [createPayload, setCreatePayload] = useState({
    strategy_id: "",
    capital_weight: "0",
    max_capital: "0",
    current_capital: "0",
    state: "ACTIVE",
  });
  const [isCreating, setIsCreating] = useState(false);
  const [globalActionError, setGlobalActionError] = useState("");
  const [driftOverrideNotice, setDriftOverrideNotice] = useState("");
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
      setRebalanceSuggestion(null);
      setWhatIfResult(null);
      setLastUpdatedAt(new Date().toISOString());
    } catch (error) {
      const message = error?.response?.data?.detail || "Strategy allocation verisi yüklenemedi";
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
    const timer = window.setInterval(() => setRequestAgeTick(Date.now()), 60000);
    return () => window.clearInterval(timer);
  }, []);

  const stateStats = useMemo(() => {
    const total = rows.length;
    const throttled = rows.filter((item) => item.state === "THROTTLED").length;
    const disabled = rows.filter((item) => item.state === "DISABLED").length;
    return { total, throttled, disabled };
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

  const isStateChanged = (strategyId) => {
    const current = rows.find((item) => item.strategy_id === strategyId);
    const draft = drafts[strategyId] || {};
    return current && String(current.state || "") !== String(draft.state || "");
  };

  const getRowErrors = (strategyId) => {
    const draft = drafts[strategyId] || {};
    const baseValidation = validateDraft(draft);
    const errors = [...baseValidation.errors];

    if (!weightIsBalanced) errors.push("Toplam weight = 1 olmalı");
    if (hasOverAllocation) errors.push("Capital limit aşılıyor");
    if (isStateChanged(strategyId)) {
      if ((draft.confirm_primary || "").toUpperCase().trim() !== DOUBLE_CONFIRM_PRIMARY) {
        errors.push("confirm_primary = CONFIRM olmalı");
      }
      if ((draft.confirm_secondary || "").toUpperCase().trim() !== DOUBLE_CONFIRM_SECONDARY) {
        errors.push("confirm_secondary = STATE CHANGE olmalı");
      }
    }

    return errors;
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

  const saveStrategy = async (strategyId) => {
    if (isOpsReadOnly) {
      toast.error("ops role read-only");
      return;
    }
    const note = ensureReasonNote();
    if (!note) return;

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
        await load();
        return;
      }
      toast.success(`Allocation güncellendi: ${strategyId}`);
      setRevisionConflict(null);
      if (data?.is_drift_override) {
        const notice = `Manual change overridden by drift rule (${data?.state_reason_code || "AUTO"})`;
        setDriftOverrideNotice(notice);
        toast.warning(notice);
      } else {
        setDriftOverrideNotice("");
      }
      await load();
    } catch (error) {
      handleConflictError(error, "Allocation güncellenemedi");
    }
  };

  const normalizeWeights = async () => {
    if (isOpsReadOnly) {
      toast.error("ops role read-only");
      return;
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
      await load();
    } catch (error) {
      handleConflictError(error, "Normalize işlemi başarısız");
    } finally {
      setIsNormalizing(false);
    }
  };

  const createStrategy = async () => {
    if (isOpsReadOnly) {
      toast.error("ops role read-only");
      return;
    }
    const note = ensureReasonNote();
    if (!note) return;

    setIsCreating(true);
    setGlobalActionError("");
    const strategyId = String(createPayload.strategy_id || "").trim();
    if (!strategyId) {
      setIsCreating(false);
      toast.error("strategy_id zorunlu");
      return;
    }

    const validation = validateDraft(createPayload);
    if (validation.hasError) {
      setIsCreating(false);
      toast.error(validation.errors[0] || "Create form geçersiz");
      return;
    }

    try {
      const { data } = await apiClient.post("/admin/strategy-allocation", {
        strategy_id: strategyId,
        capital_weight: Number(createPayload.capital_weight),
        max_capital: Number(createPayload.max_capital),
        current_capital: Number(createPayload.current_capital),
        state: createPayload.state,
        reason_note: note,
      });
      if (data?.status === "pending_approval") {
        toast.success(data?.message || `Create onaya gönderildi: ${strategyId}`);
        await load();
        return;
      }
      toast.success(`Strategy eklendi: ${strategyId}`);
      setCreatePayload({ strategy_id: "", capital_weight: "0", max_capital: "0", current_capital: "0", state: "ACTIVE" });
      await load();
    } catch (error) {
      const message = error?.response?.data?.detail || "Strategy eklenemedi";
      setGlobalActionError(message);
      toast.error(message);
    } finally {
      setIsCreating(false);
    }
  };

  const deleteStrategy = async (strategyId) => {
    if (isOpsReadOnly) {
      toast.error("ops role read-only");
      return;
    }
    const note = ensureReasonNote();
    if (!note) return;

    const ok = window.confirm(`${strategyId} silinsin mi? (auto-normalize açık)`);
    if (!ok) return;

    const sourceRow = rows.find((row) => row.strategy_id === strategyId);
    const expectedRevision = Number(drafts[strategyId]?.expected_revision || sourceRow?.revision_id || 1);

    setGlobalActionError("");
    try {
      const { data } = await apiClient.delete(`/admin/strategy-allocation/${encodeURIComponent(strategyId)}`, {
        params: { auto_normalize: true, reason_note: note, expected_revision: expectedRevision },
      });
      if (data?.status === "pending_approval") {
        toast.success(data?.message || `Delete onaya gönderildi: ${strategyId}`);
        await load();
        return;
      }
      toast.success(`Strategy silindi: ${strategyId}`);
      setRevisionConflict(null);
      await load();
    } catch (error) {
      handleConflictError(error, "Strategy silinemedi");
    }
  };

  const toggleThrottle = async (strategyId) => {
    if (isOpsReadOnly) {
      toast.error("ops role read-only");
      return;
    }
    const note = ensureReasonNote();
    if (!note) return;

    const first = window.confirm(`${strategyId} için throttle toggle başlatılsın mı?`);
    if (!first) return;
    const second = window.confirm("İkinci onay: state değişimi uygulanacak. Devam?");
    if (!second) return;

    const sourceRow = rows.find((row) => row.strategy_id === strategyId);
    const expectedRevision = Number(drafts[strategyId]?.expected_revision || sourceRow?.revision_id || 1);

    try {
      const { data } = await apiClient.post(`/admin/strategy-allocation/${encodeURIComponent(strategyId)}/throttle-toggle`, {
        expected_revision: expectedRevision,
        confirm_primary: DOUBLE_CONFIRM_PRIMARY,
        confirm_secondary: DOUBLE_CONFIRM_SECONDARY,
        reason_note: note,
      });
      if (data?.status === "pending_approval") {
        toast.success(data?.message || `Throttle isteği onaya gönderildi: ${strategyId}`);
        await load();
        return;
      }
      toast.success(`Throttle toggle tamamlandı: ${strategyId}`);
      setRevisionConflict(null);
      await load();
    } catch (error) {
      handleConflictError(error, "Throttle toggle başarısız");
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

  const submitSnapshotRestore = async () => {
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

    setRestoreModal((prev) => ({ ...prev, isSubmitting: true }));
    try {
      const { data } = await apiClient.post(`/admin/strategy-allocation/snapshots/${encodeURIComponent(snapshotId)}/restore`, {
        reason_note: note,
        expected_revisions: buildExpectedRevisionMap(),
      });
      toast.success(data?.message || `Restore tamamlandı: ${snapshotId}`);
      setRestoreModal({ open: false, snapshot: null, reason: "", isSubmitting: false });
      setRevisionConflict(null);
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
    setIsRunningWhatIf(true);
    try {
      const { data } = await apiClient.post("/admin/strategy-allocation/what-if-simulation", {
        strategy_ids: selectedStrategyIds,
      });
      setWhatIfResult(data || null);
      toast.success(data?.message || "What-if simulation hazır");
    } catch (error) {
      const message = error?.response?.data?.detail || "What-if simulation başarısız";
      toast.error(message);
      setGlobalActionError(message);
    } finally {
      setIsRunningWhatIf(false);
    }
  };

  const submitBulkUpdate = async () => {
    if (isOpsReadOnly) {
      toast.error("ops role read-only");
      return;
    }
    const note = ensureReasonNote();
    if (!note) return;

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
        await load();
        return;
      }
      toast.success(`Bulk update tamamlandı (${selectedStrategyIds.length} strategy)`);
      setRevisionConflict(null);
      const enforcedRows = data?.enforced_reduce_rows || [];
      if (enforcedRows.length > 0) {
        toast.warning(`Critical drawdown auto-reduce uygulandı (${enforcedRows.length} strategy)`);
      }
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
            <p className="mt-2 text-sm text-slate-400" data-testid="admin-strategy-allocation-description">Capital usage, confidence, throttle/disability kontrol paneli.</p>
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
          <Button className="mt-2" variant="outline" onClick={load} data-testid="admin-strategy-allocation-revision-conflict-reload-button">
            En güncel halini yükle
          </Button>
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
        <h3 className="text-base font-semibold" data-testid="admin-strategy-allocation-phase6-title">Phase 6 · Snapshot + Export + What-if</h3>
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
          <Button variant="outline" onClick={runWhatIfSimulation} disabled={isRunningWhatIf} data-testid="admin-strategy-allocation-run-whatif-button">
            {isRunningWhatIf ? "What-if çalışıyor..." : "What-if Simulation"}
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
            <p className="text-xs text-slate-300" data-testid="admin-strategy-allocation-phase6-whatif-preview-title">What-if Preview (read-only)</p>
            {!whatIfResult && <p className="mt-1 text-xs text-slate-500" data-testid="admin-strategy-allocation-phase6-whatif-empty">No data yet</p>}
            {whatIfResult && (
              <div className="mt-1 space-y-1" data-testid="admin-strategy-allocation-phase6-whatif-meta">
                <p className="text-xs" data-testid="admin-strategy-allocation-phase6-whatif-readonly">read_only={String(whatIfResult.read_only)}</p>
                <p className="text-xs" data-testid="admin-strategy-allocation-phase6-whatif-return-delta">
                  portfolio return Δ={whatIfResult.projected_portfolio_return_delta_pct}
                </p>
                <p className="text-xs" data-testid="admin-strategy-allocation-phase6-whatif-risk-delta">
                  portfolio risk Δ={whatIfResult.projected_portfolio_risk_delta_pct}
                </p>
                <p className="text-xs" data-testid="admin-strategy-allocation-phase6-whatif-selection">
                  selection_count={whatIfResult.selection_count}
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-allocation-create-panel">
        <h3 className="text-base font-semibold" data-testid="admin-strategy-allocation-create-title">Strategy Ekle</h3>
        <div className="mt-2 grid gap-2 md:grid-cols-6" data-testid="admin-strategy-allocation-create-grid">
          <Input
            placeholder="strategy_id"
            value={createPayload.strategy_id}
            onChange={(event) => setCreatePayload((prev) => ({ ...prev, strategy_id: event.target.value }))}
            data-testid="admin-strategy-allocation-create-strategy-id-input"
          />
          <Input
            type="number"
            min="0"
            max="1"
            step="0.0001"
            placeholder="weight"
            value={createPayload.capital_weight}
            onChange={(event) => setCreatePayload((prev) => ({ ...prev, capital_weight: event.target.value }))}
            data-testid="admin-strategy-allocation-create-weight-input"
          />
          <Input
            type="number"
            min="0"
            step="0.01"
            placeholder="max capital"
            value={createPayload.max_capital}
            onChange={(event) => setCreatePayload((prev) => ({ ...prev, max_capital: event.target.value }))}
            data-testid="admin-strategy-allocation-create-max-capital-input"
          />
          <Input
            type="number"
            min="0"
            step="0.01"
            placeholder="current capital"
            value={createPayload.current_capital}
            onChange={(event) => setCreatePayload((prev) => ({ ...prev, current_capital: event.target.value }))}
            data-testid="admin-strategy-allocation-create-current-capital-input"
          />
          <select
            className="w-full border border-slate-700 bg-slate-950 px-2 py-1"
            value={createPayload.state}
            onChange={(event) => setCreatePayload((prev) => ({ ...prev, state: event.target.value }))}
            data-testid="admin-strategy-allocation-create-state-select"
          >
            <option value="ACTIVE">ACTIVE</option>
            <option value="THROTTLED">THROTTLED</option>
            <option value="DISABLED">DISABLED</option>
          </select>
          <Button onClick={createStrategy} disabled={isCreating || isOpsReadOnly} data-testid="admin-strategy-allocation-create-button">
            {isCreating ? "Ekleniyor..." : "Strategy Ekle"}
          </Button>
        </div>
      </div>

      <div className="col-span-12 grid gap-3 md:grid-cols-3" data-testid="admin-strategy-allocation-summary-grid">
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-strategy-allocation-summary-total">
          <p className="text-xs text-slate-500">Toplam Strategy</p>
          <p className="text-xl font-semibold">{stateStats.total}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-strategy-allocation-summary-throttled">
          <p className="text-xs text-slate-500">THROTTLED</p>
          <p className="text-xl font-semibold text-amber-400">{stateStats.throttled}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-strategy-allocation-summary-disabled">
          <p className="text-xs text-slate-500">DISABLED</p>
          <p className="text-xl font-semibold text-rose-400">{stateStats.disabled}</p>
        </article>
      </div>

      {whatIfResult && (
        <div className="col-span-12 border border-cyan-500/40 bg-cyan-950/20 p-3 text-sm text-cyan-100" data-testid="admin-strategy-allocation-whatif-preview-warning-banner">
          Simulation preview only: Bu değerler tabloya yansıtılan önizlemedir, otomatik commit yapılmaz.
        </div>
      )}

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
              <th className="px-3 py-2">What-if Compare (Preview)</th>
              <th className="px-3 py-2">Action</th>
            </tr>
          </thead>
          <tbody data-testid="admin-strategy-allocation-table-body">
            {rows.map((item) => {
              const draft = drafts[item.strategy_id] || {};
              const rowErrors = getRowErrors(item.strategy_id);
              const stateChanged = isStateChanged(item.strategy_id);
              const simulationRow = whatIfByStrategy[item.strategy_id];
              return (
                <tr
                  key={item.strategy_id}
                  className={`border-t border-slate-800 ${simulationRow ? "bg-cyan-950/10" : ""}`}
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
                  <td className="px-3 py-2"><Input value={draft.capital_weight ?? ""} type="number" min="0" max="1" step="0.0001" onChange={(event) => updateDraft(item.strategy_id, "capital_weight", event.target.value)} data-testid={`admin-strategy-allocation-weight-input-${item.strategy_id}`} /></td>
                  <td className="px-3 py-2"><Input value={draft.max_capital ?? ""} type="number" min="0" step="0.01" onChange={(event) => updateDraft(item.strategy_id, "max_capital", event.target.value)} data-testid={`admin-strategy-allocation-max-capital-input-${item.strategy_id}`} /></td>
                  <td className="px-3 py-2"><Input value={draft.current_capital ?? ""} type="number" min="0" step="0.01" onChange={(event) => updateDraft(item.strategy_id, "current_capital", event.target.value)} data-testid={`admin-strategy-allocation-current-capital-input-${item.strategy_id}`} /></td>
                  <td className="px-3 py-2">
                    <select className="w-full border border-slate-700 bg-slate-950 px-2 py-1" value={draft.state || "ACTIVE"} onChange={(event) => updateDraft(item.strategy_id, "state", event.target.value)} data-testid={`admin-strategy-allocation-state-select-${item.strategy_id}`}>
                      <option value="ACTIVE">ACTIVE</option>
                      <option value="THROTTLED">THROTTLED</option>
                      <option value="DISABLED">DISABLED</option>
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
                    {!simulationRow && <span className="text-xs text-slate-500">No data yet</span>}
                    {simulationRow && (
                      <div className="text-xs" data-testid={`admin-strategy-allocation-whatif-cell-content-${item.strategy_id}`}>
                        <p data-testid={`admin-strategy-allocation-whatif-weight-${item.strategy_id}`}>
                          w: {simulationRow.current_weight} → {simulationRow.suggested_weight}
                        </p>
                        <p data-testid={`admin-strategy-allocation-whatif-weight-delta-${item.strategy_id}`}>
                          weight Δ {simulationRow.weight_delta}
                        </p>
                        <p data-testid={`admin-strategy-allocation-whatif-return-${item.strategy_id}`}>
                          return Δ {simulationRow.projected_return_delta_pct}
                        </p>
                        <p data-testid={`admin-strategy-allocation-whatif-risk-${item.strategy_id}`}>
                          risk Δ {simulationRow.projected_risk_delta_pct}
                        </p>
                        <p className="text-[10px] text-cyan-200" data-testid={`admin-strategy-allocation-whatif-preview-note-${item.strategy_id}`}>
                          preview_only=true
                        </p>
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-2" data-testid={`admin-strategy-allocation-actions-${item.strategy_id}`}>
                      <Button variant="outline" onClick={() => saveStrategy(item.strategy_id)} disabled={rowErrors.length > 0 || isOpsReadOnly} data-testid={`admin-strategy-allocation-save-button-${item.strategy_id}`}>Kaydet</Button>
                      <Button variant="outline" onClick={() => toggleThrottle(item.strategy_id)} disabled={isOpsReadOnly} data-testid={`admin-strategy-allocation-throttle-toggle-button-${item.strategy_id}`}>Throttle Toggle</Button>
                      <Button variant="outline" onClick={() => deleteStrategy(item.strategy_id)} disabled={isOpsReadOnly} data-testid={`admin-strategy-allocation-delete-button-${item.strategy_id}`}>Sil</Button>
                    </div>
                    {stateChanged && (
                      <div className="mt-2 grid gap-1" data-testid={`admin-strategy-allocation-double-confirm-panel-${item.strategy_id}`}>
                        <Input
                          placeholder="confirm_primary: CONFIRM"
                          value={draft.confirm_primary || ""}
                          onChange={(event) => updateDraft(item.strategy_id, "confirm_primary", event.target.value)}
                          data-testid={`admin-strategy-allocation-confirm-primary-input-${item.strategy_id}`}
                        />
                        <Input
                          placeholder="confirm_secondary: STATE CHANGE"
                          value={draft.confirm_secondary || ""}
                          onChange={(event) => updateDraft(item.strategy_id, "confirm_secondary", event.target.value)}
                          data-testid={`admin-strategy-allocation-confirm-secondary-input-${item.strategy_id}`}
                        />
                      </div>
                    )}
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
