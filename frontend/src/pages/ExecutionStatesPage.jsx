import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { apiClient, FRONTEND_BACKEND_URL } from "@/lib/api";
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
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

const SOURCE_OPTIONS = ["all", "production", "paper", "simulation", "replay"];
const STATUS_OPTIONS = ["all", "filled", "timeout", "rejected", "failed", "cancelled", "submitted", "pending"];
const DEFAULT_STATE_STEPS = [
  "created",
  "submitted",
  "acknowledged",
  "partially_filled",
  "timeout",
  "retry_1",
  "fallback_submitted",
  "filled",
  "rejected",
  "failed",
  "cancelled",
];

const readFilter = (sp, key, fallback = "") => sp.get(key) || fallback;

export const ExecutionStatesPage = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isSuperAdmin = String(user?.role || "") === "super_admin";
  const backendUrl = FRONTEND_BACKEND_URL;
  const [searchParams, setSearchParams] = useSearchParams();
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState({});
  const [stateCounters, setStateCounters] = useState({});
  const [selectedEventId, setSelectedEventId] = useState("");
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [refreshMs, setRefreshMs] = useState(10000);
  const [simulateResult, setSimulateResult] = useState(null);
  const [batchScenarios, setBatchScenarios] = useState("BTCUSDT,long,filled\nETHUSDT,short,timeout");
  const [manualCorrelationId, setManualCorrelationId] = useState("");
  const [manualReason, setManualReason] = useState("");
  const [manualPhrase, setManualPhrase] = useState("");
  const [manualToState, setManualToState] = useState("cancelled");
  const [exportScopeType, setExportScopeType] = useState("correlation_id");
  const [exportScopeValue, setExportScopeValue] = useState("");
  const [compareEnabled, setCompareEnabled] = useState(readFilter(searchParams, "compare", "false") === "true");
  const [compareScopeType, setCompareScopeType] = useState(readFilter(searchParams, "compare_scope_type", "correlation_id"));
  const [compareScopeValue, setCompareScopeValue] = useState(readFilter(searchParams, "compare_scope_value"));
  const [compareTimeFrom, setCompareTimeFrom] = useState(readFilter(searchParams, "compare_time_from"));
  const [compareTimeTo, setCompareTimeTo] = useState(readFilter(searchParams, "compare_time_to"));
  const [exportPreview, setExportPreview] = useState({ events: 0, failures: 0, transitions: 0 });
  const [compareExportPreview, setCompareExportPreview] = useState(null);
  const [diffSnapshot, setDiffSnapshot] = useState(null);
  const [diffPreviewLoading, setDiffPreviewLoading] = useState(false);
  const [playbookPreview, setPlaybookPreview] = useState(null);
  const [playbookPreviewLoading, setPlaybookPreviewLoading] = useState(false);
  const [playbookApplyLoading, setPlaybookApplyLoading] = useState(false);
  const [playbookConfirmChecked, setPlaybookConfirmChecked] = useState(false);
  const [playbookReason, setPlaybookReason] = useState("");
  const [playbookRunId, setPlaybookRunId] = useState("");
  const [playbookExecutionState, setPlaybookExecutionState] = useState("preview");
  const [playbookRunDetail, setPlaybookRunDetail] = useState(null);
  const [playbookRunDetailLoading, setPlaybookRunDetailLoading] = useState(false);
  const [playbookApproveLoading, setPlaybookApproveLoading] = useState(false);
  const [playbookExecuteLoading, setPlaybookExecuteLoading] = useState(false);
  const [playbookRollbackLoading, setPlaybookRollbackLoading] = useState(false);
  const [playbookRetryLoading, setPlaybookRetryLoading] = useState(false);
  const [playbookApplyDialogOpen, setPlaybookApplyDialogOpen] = useState(false);
  const [playbookExecuteDialogOpen, setPlaybookExecuteDialogOpen] = useState(false);
  const [playbookPreflight, setPlaybookPreflight] = useState(null);
  const [playbookPreflightLoading, setPlaybookPreflightLoading] = useState(false);
  const [playbookPreflightError, setPlaybookPreflightError] = useState("");
  const [lastExportSnapshot, setLastExportSnapshot] = useState(null);
  const [selectedDiagramState, setSelectedDiagramState] = useState("");
  const [showFullDiffNotes, setShowFullDiffNotes] = useState(false);
  const [showFullDiffActions, setShowFullDiffActions] = useState(false);
  const [snapshotHistory, setSnapshotHistory] = useState([]);

  const filters = useMemo(
    () => ({
      search: readFilter(searchParams, "search"),
      state: readFilter(searchParams, "state", "all"),
      status: readFilter(searchParams, "status", "all"),
      source_type: readFilter(searchParams, "source_type", "all"),
      symbol: readFilter(searchParams, "symbol"),
      strategy: readFilter(searchParams, "strategy"),
      correlation_id: readFilter(searchParams, "correlation_id"),
      order_id: readFilter(searchParams, "order_id"),
      time_from: readFilter(searchParams, "time_from"),
      time_to: readFilter(searchParams, "time_to"),
    }),
    [searchParams]
  );

  const updateFilter = (key, value) => {
    const next = new URLSearchParams(searchParams);
    if (!value || value === "all") {
      next.delete(key);
    } else {
      next.set(key, value);
    }
    setSearchParams(next, { replace: true });
  };

  const buildControlParams = useCallback(() => {
    const params = new URLSearchParams();
    params.set("limit", "500");
    Object.entries(filters).forEach(([key, value]) => {
      if (!value || value === "all") return;
      params.set(key, value);
    });
    return params;
  }, [filters]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = buildControlParams();
      const { data } = await apiClient.get(`/admin-phase3/execution-state-transitions/control?${params.toString()}`);
      setRows(data?.rows || []);
      setSummary(data?.summary_counts || {});
      setStateCounters(data?.state_counters || {});
      try {
        const historyRes = await apiClient.get("/admin-phase3/incident-snapshots/history", { params: { limit: 5 } });
        setSnapshotHistory(historyRes?.data?.items || []);
      } catch {
        setSnapshotHistory([]);
      }
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Execution states yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, [buildControlParams]);

  const loadDetail = useCallback(async (eventId) => {
    if (!eventId) return;
    try {
      const { data } = await apiClient.get(`/admin-phase3/execution-state-transitions/${encodeURIComponent(eventId)}/detail`);
      setSelectedEventId(eventId);
      setDetail(data);
      setManualCorrelationId(data?.execution_event?.correlation_id || "");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Event detail alınamadı");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const id = setInterval(load, refreshMs);
    return () => clearInterval(id);
  }, [refreshMs, load]);

  useEffect(() => {
    if (!compareEnabled || !diffSnapshot?.diff) {
      return;
    }
    loadPlaybookPreflight({ silent: true });
  }, [compareEnabled, diffSnapshot?.diff]);

  const handleSimulate = async (outcome) => {
    try {
      const { data } = await apiClient.post(
        `/admin-phase3/execution-state-transitions/simulate?strategy_type=breakout&symbol=${encodeURIComponent(
          filters.symbol || "BTCUSDT"
        )}&side=long&outcome=${outcome}&source_type=simulation&environment=simulation`
      );
      setSimulateResult(data);
      toast.success("Simulation oluşturuldu");
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Simulation başarısız");
    }
  };

  const handleBatchSimulate = async () => {
    const scenarios = batchScenarios
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const [symbol, side, outcome] = line.split(",").map((x) => x.trim());
        return { symbol, side, outcome, strategy_type: "breakout", source_type: "simulation", environment: "simulation" };
      });
    if (!scenarios.length) {
      toast.error("Batch scenario boş olamaz");
      return;
    }
    try {
      const { data } = await apiClient.post("/admin-phase3/execution-state-transitions/simulate-batch", { scenarios });
      toast.success(`Batch simulation tamamlandı (${data?.created || 0})`);
      setSimulateResult(data?.records?.[0] || null);
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Batch simulation başarısız");
    }
  };

  const runManualAction = async (actionType) => {
    if (!selectedEventId) {
      toast.error("Önce bir execution event seçin");
      return;
    }
    if (!manualCorrelationId.trim()) {
      toast.error("Correlation ID zorunlu");
      return;
    }
    if (!manualReason.trim()) {
      toast.error("reason zorunlu");
      return;
    }
    try {
      await apiClient.post(`/admin-phase3/execution-state-transitions/${encodeURIComponent(selectedEventId)}/manual-action`, {
        action_type: actionType,
        reason_note: manualReason.trim(),
        correlation_id: manualCorrelationId.trim(),
        confirmation_phrase: manualPhrase.trim() || null,
        payload: actionType === "force_state_change" ? { to_state: manualToState } : {},
      });
      toast.success(`Manual action başarılı: ${actionType}`);
      await load();
      await loadDetail(selectedEventId);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Manual action başarısız");
    }
  };

  const resolveExportErrorMessage = async (error) => {
    const fallback = "Export hatası: Incident snapshot export başarısız";

    const mapCompareValidation = (detail) => {
      const text = String(detail || "");
      if (text.includes("Primary and compare snapshots cannot be identical")) {
        return "Karşılaştırma hatası: Aynı snapshot seçilemez";
      }
      if (text.includes("compare scope is required when compare is enabled")) {
        return "Karşılaştırma hatası: Compare Snapshot alanları zorunlu";
      }
      return null;
    };

    if (error?.message && String(error.message).startsWith("Export hatası:")) {
      return String(error.message);
    }
    const directDetail = error?.response?.data?.detail;
    if (directDetail) {
      const mapped = mapCompareValidation(directDetail);
      if (mapped) {
        return mapped;
      }
      return `Export hatası: ${directDetail}`;
    }

    const blobLike = error?.response?.data;
    if (blobLike && typeof blobLike.text === "function") {
      try {
        const rawText = await blobLike.text();
        if (!rawText) return fallback;
        try {
          const parsed = JSON.parse(rawText);
          const parsedDetail = parsed?.detail || parsed?.message;
          if (parsedDetail) {
            const mapped = mapCompareValidation(parsedDetail);
            if (mapped) {
              return mapped;
            }
            return `Export hatası: ${parsedDetail}`;
          }
        } catch {
          return `Export hatası: ${rawText}`;
        }
      } catch {
        return fallback;
      }
    }
    return fallback;
  };

  const buildSnapshotRequestBody = useCallback(({ silent = false } = {}) => {
    const body = {
      search: filters.search || null,
      state: filters.state !== "all" ? filters.state : null,
      status: filters.status !== "all" ? filters.status : null,
      source_type: filters.source_type !== "all" ? filters.source_type : null,
      symbol: filters.symbol || null,
      strategy: filters.strategy || null,
      order_id: filters.order_id || null,
      correlation_id: null,
      execution_event_id: null,
      time_from: null,
      time_to: null,
      compare_correlation_id: null,
      compare_execution_event_id: null,
      compare_time_from: null,
      compare_time_to: null,
      compare_enabled: compareEnabled,
    };

    const fail = (message) => {
      if (!silent) {
        throw new Error(`Export hatası: ${message}`);
      }
      return null;
    };

    if (exportScopeType === "correlation_id") {
      const value = exportScopeValue.trim() || filters.correlation_id || "";
      if (!value) return fail("Correlation ID zorunlu");
      body.correlation_id = value;
    } else if (exportScopeType === "execution_event_id") {
      const value = exportScopeValue.trim() || selectedEventId || "";
      if (!value) return fail("Execution Event ID zorunlu");
      body.execution_event_id = value;
    } else {
      if (!filters.time_from || !filters.time_to) return fail("Time Range için Time From ve Time To zorunlu");
      body.time_from = filters.time_from;
      body.time_to = filters.time_to;
    }

    if (compareEnabled) {
      if (compareScopeType === "correlation_id") {
        if (!compareScopeValue.trim()) return fail("Compare Snapshot için Correlation ID zorunlu");
        body.compare_correlation_id = compareScopeValue.trim();
      } else if (compareScopeType === "execution_event_id") {
        if (!compareScopeValue.trim()) return fail("Compare Snapshot için Execution Event ID zorunlu");
        body.compare_execution_event_id = compareScopeValue.trim();
      } else {
        if (!compareTimeFrom || !compareTimeTo) return fail("Compare Snapshot için Time From ve Time To zorunlu");
        body.compare_time_from = compareTimeFrom;
        body.compare_time_to = compareTimeTo;
      }
    }
    return body;
  }, [
    compareEnabled,
    compareScopeType,
    compareScopeValue,
    compareTimeFrom,
    compareTimeTo,
    exportScopeType,
    exportScopeValue,
    filters,
    selectedEventId,
  ]);

  const loadDiffPreview = useCallback(async ({ showError = false } = {}) => {
    const body = buildSnapshotRequestBody({ silent: !showError });
    if (!body) {
      setDiffSnapshot(null);
      setExportPreview({ events: 0, failures: 0, transitions: 0 });
      setCompareExportPreview(null);
      return;
    }

    setDiffPreviewLoading(true);
    try {
      const previewParams = {
        scope_type: exportScopeType,
        scope_value: body.correlation_id || body.execution_event_id || null,
        time_from: body.time_from,
        time_to: body.time_to,
        compare_scope_type: compareEnabled ? compareScopeType : null,
        compare_scope_value: compareEnabled ? body.compare_correlation_id || body.compare_execution_event_id || null : null,
        compare_time_from: compareEnabled ? body.compare_time_from : null,
        compare_time_to: compareEnabled ? body.compare_time_to : null,
      };
      const previewRes = await apiClient.get("/admin-phase3/incident-snapshots/preview", { params: previewParams });
      setExportPreview(previewRes.data?.preview || { events: 0, failures: 0, transitions: 0 });
      setCompareExportPreview(previewRes.data?.compare_preview || null);

      if (!compareEnabled) {
        setDiffSnapshot(null);
        setPlaybookPreview(null);
        setPlaybookRunId("");
        setPlaybookExecutionState("preview");
        setPlaybookRunDetail(null);
        return;
      }

      const { data } = await apiClient.post("/admin-phase3/incident-snapshots/diff", body);
      const snapshot = data?.state_snapshot || null;
      setDiffSnapshot(snapshot);
      setShowFullDiffNotes(false);
      setShowFullDiffActions(false);
      setPlaybookPreview(null);
      setPlaybookRunId("");
      setPlaybookExecutionState("preview");
      setPlaybookRunDetail(null);
      setPlaybookConfirmChecked(false);
    } catch (error) {
      setDiffSnapshot(null);
      setPlaybookPreview(null);
      setPlaybookRunId("");
      setPlaybookExecutionState("preview");
      setPlaybookRunDetail(null);
      setCompareExportPreview(null);
      if (showError) {
        const detail = String(error?.response?.data?.detail || "");
        if (detail.includes("Primary and compare snapshots cannot be identical")) {
          toast.error("Karşılaştırma hatası: Aynı snapshot seçilemez");
        } else if (detail.includes("compare scope is required when compare is enabled")) {
          toast.error("Karşılaştırma hatası: Compare Snapshot alanları zorunlu");
        } else {
          toast.error(error?.response?.data?.detail || "Diff preview alınamadı");
        }
      }
    } finally {
      setDiffPreviewLoading(false);
    }
  }, [
    buildSnapshotRequestBody,
    compareEnabled,
    compareScopeType,
    exportScopeType,
  ]);

  const loadPlaybookPreflight = async ({ silent = false } = {}) => {
    setPlaybookPreflightLoading(true);
    try {
      const { data } = await apiClient.get("/admin-phase3/incident-snapshots/playbook/preflight");
      setPlaybookPreflight(data || null);
      setPlaybookPreflightError("");
      return data;
    } catch (error) {
      setPlaybookPreflight(null);
      const detail = error?.response?.data?.detail || "Playbook preflight alınamadı";
      setPlaybookPreflightError(detail);
      if (!silent) {
        toast.error(detail);
      }
      return null;
    } finally {
      setPlaybookPreflightLoading(false);
    }
  };

  const loadPlaybookRunDetail = useCallback(async (runIdParam = playbookRunId, { silent = true } = {}) => {
    const targetRunId = String(runIdParam || "").trim();
    if (!targetRunId) {
      setPlaybookRunDetail(null);
      return null;
    }
    setPlaybookRunDetailLoading(true);
    try {
      const { data } = await apiClient.get(`/admin-phase3/incident-snapshots/playbook/runs/${encodeURIComponent(targetRunId)}`);
      const runPayload = data?.playbook_run || null;
      setPlaybookRunDetail(runPayload);
      if (runPayload?.execution_state) {
        setPlaybookExecutionState(runPayload.execution_state);
      }
      return runPayload;
    } catch (error) {
      setPlaybookRunDetail(null);
      if (!silent) {
        toast.error(error?.response?.data?.detail || "Playbook run detail alınamadı");
      }
      return null;
    } finally {
      setPlaybookRunDetailLoading(false);
    }
  }, [playbookRunId]);

  useEffect(() => {
    if (!playbookRunId) {
      setPlaybookRunDetail(null);
      return;
    }
    loadPlaybookRunDetail(playbookRunId, { silent: true });
  }, [playbookRunId, loadPlaybookRunDetail]);

  const previewDiffPlaybook = async () => {
    if (!playbookPreflightActionAllowed) {
      const latest = await loadPlaybookPreflight({ silent: true });
      const latestState = String(latest?.overall_state || "").toLowerCase();
      const latestAllowed = Boolean(latest) && latestState !== "error" && latestState !== "blocked";
      if (!latestAllowed) {
        toast.error(playbookPreflightBlockReason || "Preflight check hazır değil");
        return;
      }
    }
    if (!diffSnapshot?.diff) {
      toast.error("Önce diff preview oluşturulmalı");
      return;
    }
    setPlaybookPreviewLoading(true);
    try {
      const { data } = await apiClient.post("/admin-phase3/incident-snapshots/playbook/preview", {
        recommended_actions: diffSnapshot?.diff?.recommended_actions_full || diffSnapshot?.diff?.recommended_actions || [],
        anomaly_notes: diffSnapshot?.diff?.anomaly_notes_full || diffSnapshot?.diff?.anomaly_notes || [],
        scope: {
          export_scope_type: exportScopeType,
          export_scope_value: exportScopeValue,
          compare_enabled: compareEnabled,
          compare_scope_type: compareScopeType,
        },
      });
      setPlaybookPreview({
        preview_token: data?.preview_token,
        ...(data?.preview || {}),
      });
      setPlaybookRunId(data?.playbook_run_id || "");
      setPlaybookExecutionState(data?.execution_state || "preview");
      setPlaybookConfirmChecked(false);
      if (data?.playbook_run_id) {
        await loadPlaybookRunDetail(data.playbook_run_id, { silent: true });
      }
      toast.success("One-click playbook preview hazır");
    } catch (error) {
      setPlaybookPreview(null);
      toast.error(error?.response?.data?.detail || "Playbook preview alınamadı");
    } finally {
      setPlaybookPreviewLoading(false);
    }
  };

  const applyDiffPlaybook = async () => {
    if (!isSuperAdmin) {
      toast.error("Super admin required");
      return;
    }
    if (!playbookPreflightActionAllowed) {
      toast.error(playbookPreflightBlockReason || "Preflight check blocked");
      return;
    }
    const previewToken = playbookPreview?.preview_token;
    if (!previewToken) {
      toast.error("Önce playbook preview alınmalı");
      return;
    }
    if (!playbookConfirmChecked) {
      toast.error("Playbook apply için confirm zorunlu");
      return;
    }
    if (playbookReason.trim().length < 3) {
      toast.error("Playbook reason en az 3 karakter olmalı");
      return;
    }
    setPlaybookApplyLoading(true);
    try {
      const { data } = await apiClient.post("/admin-phase3/incident-snapshots/playbook/apply", {
        preview_token: previewToken,
        confirm: true,
        reason: playbookReason.trim(),
      });
      toast.success(data?.message || "Playbook apply tamamlandı (non-destructive)");
      setPlaybookRunId(data?.result?.playbook_run_id || playbookRunId);
      setPlaybookExecutionState(data?.result?.execution_state || "planned");
      setPlaybookReason("");
      setPlaybookConfirmChecked(false);
      await loadPlaybookPreflight({ silent: true });
      await loadPlaybookRunDetail(data?.result?.playbook_run_id || playbookRunId, { silent: true });
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Playbook apply başarısız");
    } finally {
      setPlaybookApplyLoading(false);
    }
  };

  const approveDiffPlaybook = async () => {
    if (!playbookPreflightActionAllowed) {
      toast.error(playbookPreflightBlockReason || "Preflight check blocked");
      return;
    }
    if (!isSuperAdmin) {
      toast.error("Super admin required");
      return;
    }
    if (!playbookRunId) {
      toast.error("Önce playbook preview/apply çalıştırılmalı");
      return;
    }
    if (playbookReason.trim().length < 3) {
      toast.error("Approve reason en az 3 karakter olmalı");
      return;
    }
    setPlaybookApproveLoading(true);
    try {
      const { data } = await apiClient.post("/admin-phase3/incident-snapshots/playbook/approve", {
        playbook_run_id: playbookRunId,
        confirm: true,
        reason: playbookReason.trim(),
      });
      setPlaybookExecutionState(data?.execution_state || "approved");
      toast.success("Playbook approved");
      await loadPlaybookPreflight({ silent: true });
      await loadPlaybookRunDetail(playbookRunId, { silent: true });
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Playbook approve başarısız");
    } finally {
      setPlaybookApproveLoading(false);
    }
  };

  const executeDiffPlaybook = async () => {
    if (!isSuperAdmin) {
      toast.error("Super admin required");
      return;
    }
    if (!playbookPreflightActionAllowed) {
      toast.error(playbookPreflightBlockReason || "Preflight check blocked");
      return;
    }
    if (!playbookRunId) {
      toast.error("Önce playbook preview/apply/approve tamamlanmalı");
      return;
    }
    if (playbookReason.trim().length < 3) {
      toast.error("Execute reason en az 3 karakter olmalı");
      return;
    }
    setPlaybookExecuteLoading(true);
    try {
      const { data } = await apiClient.post("/admin-phase3/incident-snapshots/playbook/execute", {
        playbook_run_id: playbookRunId,
        confirm: true,
        reason: playbookReason.trim(),
      });
      const nextState = data?.execution_state || "executed";
      setPlaybookExecutionState(nextState);
      if (nextState === "failed") {
        toast.error(data?.failure_reason || data?.message || "Playbook step failure oluştu");
      } else {
        toast.success(data?.message || "Playbook execute tamamlandı");
      }
      await loadPlaybookPreflight({ silent: true });
      await loadPlaybookRunDetail(playbookRunId, { silent: true });
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Playbook execute başarısız");
    } finally {
      setPlaybookExecuteLoading(false);
    }
  };

  const rollbackDiffPlaybook = async () => {
    if (!playbookPreflightActionAllowed) {
      toast.error(playbookPreflightBlockReason || "Preflight ERROR: rollback kilitli");
      return;
    }
    if (!isSuperAdmin) {
      toast.error("Rollback sadece super_admin için açık");
      return;
    }
    if (!playbookRunId) {
      toast.error("Rollback için playbook run gerekli");
      return;
    }
    if (playbookExecutionState !== "executed") {
      toast.error("Rollback sadece executed state'te açılır");
      return;
    }
    if (playbookReason.trim().length < 3) {
      toast.error("Rollback reason en az 3 karakter olmalı");
      return;
    }
    setPlaybookRollbackLoading(true);
    try {
      const { data } = await apiClient.post("/admin-phase3/incident-snapshots/playbook/rollback", {
        playbook_run_id: playbookRunId,
        confirm: true,
        reason: playbookReason.trim(),
      });
      setPlaybookExecutionState(data?.execution_state || "rollback_executed");
      await loadPlaybookRunDetail(playbookRunId, { silent: true });
      toast.success(data?.message || "Rollback tamamlandı");
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Rollback başarısız");
    } finally {
      setPlaybookRollbackLoading(false);
    }
  };

  const retryFailedPlaybook = async () => {
    if (!playbookPreflightActionAllowed) {
      toast.error(playbookPreflightBlockReason || "Preflight ERROR: retry kilitli");
      return;
    }
    if (!isSuperAdmin) {
      toast.error("Retry sadece super_admin için açık");
      return;
    }
    if (!playbookRunId) {
      toast.error("Retry için failed playbook run gerekli");
      return;
    }
    if (playbookExecutionState !== "failed") {
      toast.error("Retry sadece failed state'te açılır");
      return;
    }
    if (playbookReason.trim().length < 3) {
      toast.error("Retry reason en az 3 karakter olmalı");
      return;
    }
    setPlaybookRetryLoading(true);
    try {
      const { data } = await apiClient.post("/admin-phase3/incident-snapshots/playbook/retry", {
        original_playbook_run_id: playbookRunId,
        confirm: true,
        reason: playbookReason.trim(),
      });
      const nextRunId = data?.retry_playbook_run_id || "";
      setPlaybookRunId(nextRunId);
      setPlaybookExecutionState(data?.execution_state || "approved");
      await loadPlaybookRunDetail(nextRunId, { silent: true });
      toast.success(data?.message || "Retry run oluşturuldu");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Retry oluşturulamadı");
    } finally {
      setPlaybookRetryLoading(false);
    }
  };

  const exportIncidentSnapshot = async () => {
    try {
      const body = buildSnapshotRequestBody({ silent: false });
      if (compareEnabled) {
        await loadDiffPreview({ showError: true });
      }

      const accessToken = window.localStorage.getItem("token");
      const response = await fetch(`${backendUrl}/api/admin-phase3/incident-snapshots/export`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
        body: JSON.stringify(body),
      });

      if (response.status >= 400) {
        let detail = "Incident snapshot export başarısız";
        try {
          await apiClient.post("/admin-phase3/incident-snapshots/export", body);
        } catch (probeError) {
          const probeDetail = probeError?.response?.data?.detail;
          if (probeDetail) {
            detail = probeDetail;
          }
        }

        if (detail === "Incident snapshot export başarısız") {
          const rawBuffer = await response.arrayBuffer();
          const rawText = new TextDecoder("utf-8").decode(rawBuffer || new ArrayBuffer(0));
          if (rawText) {
            try {
              const parsed = JSON.parse(rawText);
              detail = parsed?.detail || parsed?.message || rawText;
            } catch {
              detail = rawText;
            }
          }
        }
        throw new Error(`Export hatası: ${detail}`);
      }

      const snapshotAt = response.headers.get("x-incident-snapshot-at");
      const snapshotId = response.headers.get("x-incident-snapshot-id");
      const snapshotHash = response.headers.get("x-incident-snapshot-hash");
      const rowCount = Number(response.headers.get("x-incident-snapshot-row-count") || 0);
      const filtersRaw = response.headers.get("x-incident-snapshot-filters");
      let parsedFilters = {};
      if (filtersRaw) {
        try {
          parsedFilters = JSON.parse(filtersRaw);
        } catch {
          parsedFilters = {};
        }
      }
      setLastExportSnapshot({
        timestamp: snapshotAt,
        snapshot_id: snapshotId,
        snapshot_hash: snapshotHash,
        row_count: rowCount,
        filters: parsedFilters,
      });

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `incident_snapshot_${exportScopeType}.zip`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      toast.success("Incident snapshot zip indirildi");
    } catch (error) {
      const message = await resolveExportErrorMessage(error);
      toast.error(message);
    }
  };

  useEffect(() => {
    const timer = setTimeout(() => {
      loadDiffPreview({ showError: false });
    }, 400);
    return () => clearTimeout(timer);
  }, [loadDiffPreview]);

  useEffect(() => {
    const next = new URLSearchParams(searchParams);
    if (compareEnabled) {
      next.set("compare", "true");
      next.set("compare_scope_type", compareScopeType);
      if (compareScopeType === "time_range") {
        if (compareTimeFrom) next.set("compare_time_from", compareTimeFrom);
        else next.delete("compare_time_from");
        if (compareTimeTo) next.set("compare_time_to", compareTimeTo);
        else next.delete("compare_time_to");
        next.delete("compare_scope_value");
      } else {
        if (compareScopeValue) next.set("compare_scope_value", compareScopeValue);
        else next.delete("compare_scope_value");
        next.delete("compare_time_from");
        next.delete("compare_time_to");
      }
    } else {
      next.delete("compare");
      next.delete("compare_scope_type");
      next.delete("compare_scope_value");
      next.delete("compare_time_from");
      next.delete("compare_time_to");
    }

    if (next.toString() !== searchParams.toString()) {
      setSearchParams(next, { replace: true });
    }
  }, [
    compareEnabled,
    compareScopeType,
    compareScopeValue,
    compareTimeFrom,
    compareTimeTo,
    searchParams,
    setSearchParams,
  ]);

  const uniqueStates = useMemo(() => {
    const set = new Set(rows.map((row) => row.state).filter(Boolean));
    return ["all", ...Array.from(set)];
  }, [rows]);

  const statePath = useMemo(() => (detail?.full_state_path?.length ? detail.full_state_path : []), [detail?.full_state_path]);
  const diagramSteps = useMemo(() => {
    const dynamic = statePath.filter((item) => !DEFAULT_STATE_STEPS.includes(item));
    return [...DEFAULT_STATE_STEPS, ...dynamic];
  }, [statePath]);

  const transitionStatsByState = useMemo(() => {
    const stats = {};
    (detail?.transitions || []).forEach((transition) => {
      const toState = String(transition?.state || "unknown");
      const latency = Number(transition?.latency_ms || 0);
      const current = stats[toState] || { transition_count: 0, failure_count: 0, timeout_count: 0, latencies: [] };
      current.transition_count += 1;
      if (toState === "failed" || toState === "rejected") {
        current.failure_count += 1;
      }
      if (toState === "timeout") {
        current.timeout_count += 1;
      }
      if (!Number.isNaN(latency) && latency > 0) {
        current.latencies.push(latency);
      }
      stats[toState] = current;
    });

    Object.keys(stats).forEach((stateName) => {
      const latencies = stats[stateName].latencies || [];
      const avg = latencies.length ? latencies.reduce((acc, item) => acc + item, 0) / latencies.length : 0;
      stats[stateName].avg_latency_ms = Number(avg.toFixed(4));
      delete stats[stateName].latencies;
    });
    return stats;
  }, [detail?.transitions]);

  useEffect(() => {
    if (!detail) {
      setSelectedDiagramState("");
      return;
    }
    setSelectedDiagramState(detail?.execution_event?.state || statePath[statePath.length - 1] || "");
  }, [detail, statePath]);

  const diffData = diffSnapshot?.diff || null;
  const anomalyNotesFull = diffData?.anomaly_notes_full || diffData?.anomaly_notes || [];
  const anomalyNotesCompact = diffData?.anomaly_notes || [];
  const anomalyNotesDisplay = showFullDiffNotes ? anomalyNotesFull : anomalyNotesCompact;
  const recommendedActionsFull = diffData?.recommended_actions_full || diffData?.recommended_actions || [];
  const recommendedActionsCompact = diffData?.recommended_actions || [];
  const recommendedActionsDisplay = showFullDiffActions ? recommendedActionsFull : recommendedActionsCompact;
  const longDiffCollapsed = Boolean(diffData?.long_diff_collapsed);
  const beforeAfter = diffData?.before_after || {};
  const eventsBefore = Number(beforeAfter?.events?.before ?? 0);
  const eventsAfter = Number(beforeAfter?.events?.after ?? 0);
  const failedBefore = Number(beforeAfter?.failed_events?.before ?? 0);
  const failedAfter = Number(beforeAfter?.failed_events?.after ?? 0);
  const deadBefore = Number(beforeAfter?.dead_letter?.before ?? 0);
  const deadAfter = Number(beforeAfter?.dead_letter?.after ?? 0);
  const manualBefore = Number(beforeAfter?.manual_actions?.before ?? 0);
  const manualAfter = Number(beforeAfter?.manual_actions?.after ?? 0);
  const eventsPct = Number(beforeAfter?.events?.percentage ?? 0);
  const manualPct = Number(beforeAfter?.manual_actions?.percentage ?? 0);

  const failedPct = Number(diffData?.percentage_change?.failed_events || 0);
  const deadPct = Number(diffData?.percentage_change?.dead_letter || 0);
  const failedDelta = Number(diffData?.counts?.failed_events_delta || 0);
  const deadDelta = Number(diffData?.counts?.dead_letter_delta || 0);
  const manualDelta = Number(diffData?.counts?.manual_actions_delta || 0);
  const compareReady = !compareEnabled || (
    compareScopeType === "time_range"
      ? Boolean(compareTimeFrom && compareTimeTo)
      : Boolean(compareScopeValue.trim())
  );
  const playbookPreflightState = String(playbookPreflight?.overall_state || "").toLowerCase();
  const playbookPreflightUiStatus = String(playbookPreflight?.overall_ui_status || "UNKNOWN").toUpperCase();
  const playbookPreflightIsError = !playbookPreflight || playbookPreflightState === "error" || playbookPreflightState === "blocked";
  const playbookPreflightActionAllowed = !playbookPreflightIsError;
  const playbookPreflightBlockReason = playbookPreflightError || (playbookPreflightIsError ? "Preflight ERROR: kritik sorun var" : "");
  const playbookCanApprove = ["preview", "planned"].includes(String(playbookExecutionState || ""));
  const playbookCanRollback = String(playbookExecutionState || "") === "executed";
  const playbookCanRetry = String(playbookExecutionState || "") === "failed";
  const playbookStepIndex = Number(playbookRunDetail?.step_index || 0);
  const playbookTotalSteps = Number(playbookRunDetail?.total_steps || playbookPreview?.steps?.length || 0);
  const playbookProgressPct = playbookTotalSteps > 0 ? Math.min(100, Math.round((playbookStepIndex / playbookTotalSteps) * 100)) : 0;
  const playbookFailureReason = playbookRunDetail?.failure_reason || "";
  const playbookStepsView = playbookRunDetail?.steps || playbookPreview?.steps || [];

  const resolveRecommendedActionMeta = (item) => {
    const actionName = String(item?.action || "").toLowerCase();
    const correlationId = (filters.correlation_id || exportScopeValue || "").trim();
    if (actionName === "retry_policy_tune") {
      return {
        label: "View Failures",
        path: `/admin/execution/failures?correlation_id=${encodeURIComponent(correlationId)}&reason=high_failure`,
      };
    }
    if (actionName === "guardrail_hardening") {
      return {
        label: "View Idempotency",
        path: `/admin/execution/idempotency?correlation_id=${encodeURIComponent(correlationId)}&reason=dead_letter_rise`,
      };
    }
    if (actionName === "runbook_review") {
      return {
        label: "View Trace",
        path: `/admin/execution/trace?correlation_id=${encodeURIComponent(correlationId)}&reason=manual_intervention`,
      };
    }
    return { label: null, path: null };
  };

  const formatActionTitle = (actionName) => {
    const map = {
      retry_policy_tune: "Retry policy tune",
      guardrail_hardening: "Guardrail hardening",
      runbook_review: "Runbook review",
      keep_current_policy: "Keep current policy",
    };
    return map[String(actionName || "").toLowerCase()] || String(actionName || "").replaceAll("_", " ");
  };

  const openRecommendedAction = (item) => {
    const actionMeta = resolveRecommendedActionMeta(item);
    if (!actionMeta.path) {
      return;
    }
    navigate(actionMeta.path);
  };

  return (
    <section className="space-y-4" data-testid="execution-control-states-page">
      <div className="grid gap-3 md:grid-cols-6" data-testid="execution-control-states-filters">
        <div>
          <Label>Search</Label>
          <Input value={filters.search} onChange={(e) => updateFilter("search", e.target.value)} placeholder="event/correlation/symbol/order" data-testid="execution-control-states-search-input" />
        </div>
        <div>
          <Label>State</Label>
          <Select value={filters.state || "all"} onValueChange={(v) => updateFilter("state", v)}>
            <SelectTrigger data-testid="execution-control-states-state-select"><SelectValue /></SelectTrigger>
            <SelectContent>{uniqueStates.map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div>
          <Label>Status</Label>
          <Select value={filters.status || "all"} onValueChange={(v) => updateFilter("status", v)}>
            <SelectTrigger data-testid="execution-control-states-status-select"><SelectValue /></SelectTrigger>
            <SelectContent>{STATUS_OPTIONS.map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div>
          <Label>Source Type</Label>
          <Select value={filters.source_type || "all"} onValueChange={(v) => updateFilter("source_type", v)}>
            <SelectTrigger data-testid="execution-control-states-source-select"><SelectValue /></SelectTrigger>
            <SelectContent>{SOURCE_OPTIONS.map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div>
          <Label>Symbol</Label>
          <Input value={filters.symbol} onChange={(e) => updateFilter("symbol", e.target.value)} data-testid="execution-control-states-symbol-input" />
        </div>
        <div>
          <Label>Strategy</Label>
          <Input value={filters.strategy} onChange={(e) => updateFilter("strategy", e.target.value)} data-testid="execution-control-states-strategy-input" />
        </div>
        <div>
          <Label>Correlation ID</Label>
          <Input value={filters.correlation_id} onChange={(e) => updateFilter("correlation_id", e.target.value)} placeholder="enter correlation id" data-testid="execution-control-states-correlation-input" />
        </div>
        <div>
          <Label>Order ID</Label>
          <Input value={filters.order_id} onChange={(e) => updateFilter("order_id", e.target.value)} data-testid="execution-control-states-order-id-input" />
        </div>
        <div>
          <Label>Time From (ISO)</Label>
          <Input value={filters.time_from} onChange={(e) => updateFilter("time_from", e.target.value)} placeholder="2026-03-22T00:00:00+00:00" data-testid="execution-control-states-time-from-input" />
        </div>
        <div>
          <Label>Time To (ISO)</Label>
          <Input value={filters.time_to} onChange={(e) => updateFilter("time_to", e.target.value)} placeholder="2026-03-22T23:59:59+00:00" data-testid="execution-control-states-time-to-input" />
        </div>
        <div>
          <Label>Refresh</Label>
          <Select value={String(refreshMs)} onValueChange={(v) => setRefreshMs(Number(v))}>
            <SelectTrigger data-testid="execution-control-states-refresh-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="5000">5s</SelectItem>
              <SelectItem value="10000">10s</SelectItem>
              <SelectItem value="20000">20s</SelectItem>
              <SelectItem value="30000">30s</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-end gap-2">
          <Button onClick={load} data-testid="execution-control-states-refresh-button">Yenile</Button>
          <Button variant="outline" onClick={() => setSearchParams(new URLSearchParams(), { replace: true })} data-testid="execution-control-states-clear-filters-button">Temizle</Button>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-4" data-testid="execution-control-states-summary-grid">
        {Object.entries(stateCounters).map(([key, value]) => (
          <article key={key} className="border border-slate-800 bg-slate-900 p-2" data-testid={`execution-control-states-counter-${key}`}>
            <p className="text-xs text-slate-400">{key}</p>
            <p className="text-lg font-semibold">{value}</p>
          </article>
        ))}
      </div>

      <div className="flex flex-wrap gap-2" data-testid="execution-control-simulation-actions">
        <Button variant="outline" onClick={() => handleSimulate("filled")} data-testid="execution-control-simulate-filled-button">Simulate Filled</Button>
        <Button variant="outline" onClick={() => handleSimulate("timeout")} data-testid="execution-control-simulate-timeout-button">Simulate Timeout</Button>
        <Button variant="outline" onClick={() => handleSimulate("partial")} data-testid="execution-control-simulate-partial-button">Simulate Partial</Button>
        <Button variant="outline" onClick={handleBatchSimulate} data-testid="execution-control-simulate-batch-button">Batch Simulate</Button>
      </div>

      <textarea
        className="min-h-[70px] w-full rounded border border-slate-800 bg-slate-950 p-2 text-xs"
        value={batchScenarios}
        onChange={(e) => setBatchScenarios(e.target.value)}
        data-testid="execution-control-simulate-batch-textarea"
      />

      {simulateResult && (
        <div className="rounded border border-cyan-700 bg-cyan-950/20 p-3 text-xs" data-testid="execution-control-simulation-result-panel">
          final_state={simulateResult.final_state} · retry_budget_used={simulateResult.retry_budget_used} · partial_fill_ratio={simulateResult.partial_fill_ratio}
          <p className="mt-1">state_path={(simulateResult.state_path || []).join(" -> ")}</p>
          <p>correlation_id={simulateResult.correlation_id}</p>
        </div>
      )}

      <div className="overflow-x-auto border border-slate-800 bg-slate-900" data-testid="execution-control-states-table-wrapper">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>event</TableHead>
              <TableHead>state</TableHead>
              <TableHead>source</TableHead>
              <TableHead>correlation</TableHead>
              <TableHead>occurred_at</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow
                key={row.id}
                onClick={() => loadDetail(row.execution_event_id)}
                className="cursor-pointer"
                data-testid={`execution-control-state-row-${row.id}`}
              >
                <TableCell>{row.execution_event_id}</TableCell>
                <TableCell>{row.state}</TableCell>
                <TableCell>{row.source_type}/{row.environment}</TableCell>
                <TableCell>{row.correlation_id || "-"}</TableCell>
                <TableCell>{new Date(row.occurred_at).toLocaleString()}</TableCell>
              </TableRow>
            ))}
            {!rows.length && !loading && (
              <TableRow><TableCell colSpan={5}>Kayıt yok</TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {detail && (
        <div className="rounded border border-slate-700 bg-slate-950 p-3" data-testid="execution-control-state-detail-drawer">
          <p className="text-sm font-semibold">Active={detail.current_state} · Previous={detail.previous_state || "-"}</p>
          <p className="text-xs text-slate-400">path={(detail.full_state_path || []).join(" -> ")}</p>
          <p className="text-xs text-slate-400">transition_count={detail.transition_count} · dwell_time={detail.dwell_time_seconds}s</p>
          <p className="text-xs text-slate-400">event_id={selectedEventId} · correlation={detail.execution_event?.correlation_id || "-"}</p>

          <div className="mt-3 rounded border border-slate-800 bg-black/20 p-2" data-testid="execution-control-state-diagram-panel">
            <p className="text-xs text-slate-300" data-testid="execution-control-state-diagram-title">State Diagram (interactive)</p>
            <div className="mt-2 grid gap-3 lg:grid-cols-[2fr,1fr]" data-testid="execution-control-state-diagram-content-grid">
              <div className="flex flex-wrap gap-1" data-testid="execution-control-state-diagram-node-list">
                {diagramSteps.map((step, index) => {
                  const active = step === detail.current_state;
                  const visited = statePath.includes(step);
                  const selected = step === selectedDiagramState;
                  const inPath = statePath.includes(step);
                  const stats = transitionStatsByState[step] || { transition_count: 0, failure_count: 0, timeout_count: 0, avg_latency_ms: 0 };
                  return (
                    <button
                      key={step}
                      type="button"
                      onClick={() => setSelectedDiagramState(step)}
                      title={`transition_count=${stats.transition_count}`}
                      className={`rounded border px-2 py-1 text-[11px] transition-colors ${active ? "border-cyan-400 text-cyan-200" : visited ? "border-emerald-500/60 text-emerald-200" : "border-slate-700 text-slate-400"} ${selected ? "ring-1 ring-amber-400" : ""} ${inPath ? "animate-pulse" : ""}`}
                      style={inPath ? { animationDelay: `${index * 80}ms` } : undefined}
                      data-testid={`execution-control-state-diagram-node-${step}`}
                    >
                      <span>{step}</span>
                      <span className="ml-2 text-[10px] opacity-80" data-testid={`execution-control-state-diagram-node-transition-count-${step}`}>t:{stats.transition_count}</span>
                      <span className="ml-1 text-[10px] opacity-80" data-testid={`execution-control-state-diagram-node-failure-count-${step}`}>f:{stats.failure_count}</span>
                      <span className="ml-1 text-[10px] opacity-80" data-testid={`execution-control-state-diagram-node-timeout-count-${step}`}>to:{stats.timeout_count}</span>
                    </button>
                  );
                })}
              </div>

              <div className="rounded border border-slate-700 bg-slate-950 p-2 text-xs" data-testid="execution-control-state-diagram-detail-panel">
                <p className="font-semibold" data-testid="execution-control-state-diagram-detail-title">state detail: {selectedDiagramState || "-"}</p>
                <p data-testid="execution-control-state-diagram-detail-current-highlight">current_highlight: {String(selectedDiagramState === detail.current_state)}</p>
                <p data-testid="execution-control-state-diagram-detail-transition-count">transition_count: {transitionStatsByState[selectedDiagramState]?.transition_count ?? 0}</p>
                <p data-testid="execution-control-state-diagram-detail-failure-count">failure_count: {transitionStatsByState[selectedDiagramState]?.failure_count ?? 0}</p>
                <p data-testid="execution-control-state-diagram-detail-timeout-count">timeout_count: {transitionStatsByState[selectedDiagramState]?.timeout_count ?? 0}</p>
                <p data-testid="execution-control-state-diagram-detail-latency">avg_latency_ms: {transitionStatsByState[selectedDiagramState]?.avg_latency_ms ?? 0}</p>
              </div>
            </div>
          </div>

          <div className="mt-3 grid gap-2 md:grid-cols-4" data-testid="execution-control-manual-intervention-panel">
            <Input placeholder="Correlation ID" value={manualCorrelationId} onChange={(e) => setManualCorrelationId(e.target.value)} data-testid="execution-control-manual-correlation-input" />
            <Input placeholder="reason" value={manualReason} onChange={(e) => setManualReason(e.target.value)} data-testid="execution-control-manual-reason-input" />
            <Input placeholder="confirmation phrase (prod)" value={manualPhrase} onChange={(e) => setManualPhrase(e.target.value)} data-testid="execution-control-manual-confirmation-input" />
            <Input placeholder="force to_state" value={manualToState} onChange={(e) => setManualToState(e.target.value)} data-testid="execution-control-manual-to-state-input" />
          </div>
          <div className="mt-2 flex flex-wrap gap-2" data-testid="execution-control-manual-intervention-actions">
            <Button size="sm" variant="outline" onClick={() => runManualAction("force_state_change")} data-testid="execution-control-manual-force-state-button">Force State</Button>
            <Button size="sm" variant="outline" onClick={() => runManualAction("cancel_execution")} data-testid="execution-control-manual-cancel-button">Cancel Execution</Button>
            <Button size="sm" variant="outline" onClick={() => runManualAction("reprocess")} data-testid="execution-control-manual-reprocess-button">Reprocess</Button>
          </div>
        </div>
      )}

      <div className="rounded border border-slate-700 bg-slate-950 p-3" data-testid="execution-control-incident-export-panel">
        <p className="text-sm font-semibold">Incident Snapshot Export</p>
        <p className="text-xs text-slate-400" data-testid="execution-control-incident-export-preview-text">
          {diffPreviewLoading
            ? "Export preview hazırlanıyor..."
            : compareEnabled && compareExportPreview
              ? `Primary ~ ${exportPreview.events || 0} events, ${exportPreview.failures || 0} failures | Compare ~ ${compareExportPreview.events || 0} events, ${compareExportPreview.failures || 0} failures`
              : `~ ${exportPreview.events || 0} events, ${exportPreview.failures || 0} failures export edilecek`}
        </p>

        {lastExportSnapshot && (
          <div className="mt-2 rounded border border-slate-700 bg-slate-950 p-2 text-xs" data-testid="execution-control-incident-last-export-panel">
            <p data-testid="execution-control-incident-last-export-timestamp">Export snapshot at: {lastExportSnapshot.timestamp || "-"}</p>
            <p data-testid="execution-control-incident-last-export-id">snapshot_id: {lastExportSnapshot.snapshot_id || "-"}</p>
            <p data-testid="execution-control-incident-last-export-hash">snapshot_hash: {lastExportSnapshot.snapshot_hash || "-"}</p>
            <p data-testid="execution-control-incident-last-export-row-count">row_count: {lastExportSnapshot.row_count ?? 0}</p>
            <p data-testid="execution-control-incident-last-export-filters">filters: {JSON.stringify(lastExportSnapshot.filters || {})}</p>
          </div>
        )}

        <div className="mt-2 rounded border border-slate-700 bg-slate-950 p-2 text-xs" data-testid="execution-control-incident-history-panel">
          <p className="font-semibold" data-testid="execution-control-incident-history-title">Execution History Quick Access (last 5)</p>
          <div className="mt-2 flex flex-wrap gap-2" data-testid="execution-control-incident-history-list">
            {snapshotHistory.map((item, index) => (
              <Button
                key={item.audit_id || index}
                size="sm"
                variant="outline"
                onClick={() => {
                  const identifiers = item.scope_identifiers || {};
                  const corr = identifiers.correlation_id || "";
                  setExportScopeType(item.scope_type || "correlation_id");
                  setExportScopeValue(corr || identifiers.execution_event_id || "");
                  if (item.compare_scope_type) {
                    setCompareEnabled(true);
                    setCompareScopeType(item.compare_scope_type);
                    setCompareScopeValue(item.compare_scope_identifiers?.correlation_id || item.compare_scope_identifiers?.execution_event_id || "");
                  }
                }}
                data-testid={`execution-control-incident-history-item-${index}`}
              >
                #{index + 1} {item.scope_type || "scope"} · {item.row_count ?? 0}
              </Button>
            ))}
            {!snapshotHistory.length && <p data-testid="execution-control-incident-history-empty">history yok</p>}
          </div>
        </div>

        <div className="mt-3 space-y-3" data-testid="execution-control-incident-compare-panel">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setCompareEnabled((prev) => !prev)}
            data-testid="execution-control-incident-compare-toggle-button"
          >
            Compare Snapshot {compareEnabled ? "ON" : "OFF"}
          </Button>

          <div className="grid gap-3 lg:grid-cols-2" data-testid="execution-control-incident-snapshot-cards-grid">
            <div className="rounded border border-slate-700 bg-black/30 p-3" data-testid="execution-control-incident-primary-snapshot-card">
              <p className="text-xs font-semibold text-slate-300" data-testid="execution-control-incident-primary-snapshot-label">Primary Snapshot</p>
              <div className="mt-2 grid gap-2 md:grid-cols-2" data-testid="execution-control-incident-primary-fields">
                <div>
                  <Label>Scope Type</Label>
                  <Select value={exportScopeType} onValueChange={setExportScopeType}>
                    <SelectTrigger data-testid="execution-control-incident-export-scope-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="correlation_id">Correlation ID</SelectItem>
                      <SelectItem value="execution_event_id">Execution Event ID</SelectItem>
                      <SelectItem value="time_range">Time Range</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {exportScopeType === "time_range" ? (
                  <>
                    <div>
                      <Label>Time From (ISO)</Label>
                      <Input value={filters.time_from} onChange={(e) => updateFilter("time_from", e.target.value)} placeholder="2026-03-22T00:00:00+00:00" data-testid="execution-control-incident-primary-time-from-input" />
                    </div>
                    <div>
                      <Label>Time To (ISO)</Label>
                      <Input value={filters.time_to} onChange={(e) => updateFilter("time_to", e.target.value)} placeholder="2026-03-22T23:59:59+00:00" data-testid="execution-control-incident-primary-time-to-input" />
                    </div>
                  </>
                ) : (
                  <div>
                    <Label>{exportScopeType === "correlation_id" ? "Correlation ID" : "Execution Event ID"}</Label>
                    <Input
                      value={exportScopeValue}
                      onChange={(e) => setExportScopeValue(e.target.value)}
                      placeholder={exportScopeType === "correlation_id" ? "enter correlation id" : "enter execution event id"}
                      data-testid="execution-control-incident-export-scope-value-input"
                    />
                  </div>
                )}
              </div>
            </div>

            {compareEnabled && (
              <div className="rounded border border-slate-700 bg-black/30 p-3" data-testid="execution-control-incident-compare-snapshot-card">
                <p className="text-xs font-semibold text-slate-300" data-testid="execution-control-incident-compare-snapshot-label">Compare Snapshot</p>
                <div className="mt-2 grid gap-2 md:grid-cols-2" data-testid="execution-control-incident-compare-fields">
                  <div>
                    <Label>Scope Type</Label>
                    <Select value={compareScopeType} onValueChange={setCompareScopeType}>
                      <SelectTrigger data-testid="execution-control-incident-compare-scope-select"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="correlation_id">Correlation ID</SelectItem>
                        <SelectItem value="execution_event_id">Execution Event ID</SelectItem>
                        <SelectItem value="time_range">Time Range</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  {compareScopeType === "time_range" ? (
                    <>
                      <div>
                        <Label>Time From (ISO)</Label>
                        <Input value={compareTimeFrom} onChange={(e) => setCompareTimeFrom(e.target.value)} placeholder="2026-03-22T00:00:00+00:00" data-testid="execution-control-incident-compare-time-from-input" />
                      </div>
                      <div>
                        <Label>Time To (ISO)</Label>
                        <Input value={compareTimeTo} onChange={(e) => setCompareTimeTo(e.target.value)} placeholder="2026-03-22T23:59:59+00:00" data-testid="execution-control-incident-compare-time-to-input" />
                      </div>
                    </>
                  ) : (
                    <div>
                      <Label>{compareScopeType === "correlation_id" ? "Correlation ID" : "Execution Event ID"}</Label>
                      <Input value={compareScopeValue} onChange={(e) => setCompareScopeValue(e.target.value)} placeholder="enter compare scope value" data-testid="execution-control-incident-compare-scope-value-input" />
                    </div>
                  )}
                </div>
                {!compareReady && (
                  <p className="mt-2 text-xs text-red-400" data-testid="execution-control-incident-compare-required-text">
                    Compare ON iken Compare Snapshot alanları zorunludur.
                  </p>
                )}
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center justify-end gap-2" data-testid="execution-control-incident-export-actions-row">
            <Button onClick={exportIncidentSnapshot} disabled={!compareReady} data-testid="execution-control-incident-export-button">Export Snapshot ZIP</Button>
          </div>
        </div>

        {compareEnabled && diffData && (
          <div className="mt-3 rounded border border-slate-700 bg-black/30 p-3" data-testid="execution-control-diff-summary-panel">
            <p className="text-sm font-semibold" data-testid="execution-control-diff-summary-title">Diff Panel</p>

            <div className="mt-2 rounded border border-slate-700 bg-slate-950 p-2" data-testid="execution-control-diff-section-summary">
              <p className="text-xs font-semibold text-slate-300">1) Summary</p>
              <div className="mt-2 grid gap-2 md:grid-cols-2 text-xs" data-testid="execution-control-diff-before-after-grid">
                <p data-testid="execution-control-diff-events-before-after">EVENTS: {eventsBefore} → {eventsAfter} ({eventsPct >= 0 ? "+" : ""}{eventsPct}%)</p>
                <p data-testid="execution-control-diff-failed-before-after">FAILED EVENTS: {failedBefore} → {failedAfter} ({failedPct >= 0 ? "+" : ""}{failedPct}%) 🔴</p>
                <p data-testid="execution-control-diff-dead-before-after">DEAD LETTER: {deadBefore} → {deadAfter} ({deadPct >= 0 ? "+" : ""}{deadPct}%) ⚠️</p>
                <p data-testid="execution-control-diff-manual-before-after">MANUAL ACTIONS: {manualBefore} → {manualAfter} ({manualPct >= 0 ? "+" : ""}{manualPct}%) ✅</p>
              </div>
            </div>

            <div className="mt-2 rounded border border-slate-700 bg-slate-950 p-2" data-testid="execution-control-diff-section-anomalies">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs font-semibold text-slate-300">2) Anomalies</p>
                {longDiffCollapsed && (
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-6"
                    onClick={() => setShowFullDiffNotes((prev) => !prev)}
                    data-testid="execution-control-diff-anomaly-toggle-button"
                  >
                    {showFullDiffNotes ? "Collapse" : "Expand"}
                  </Button>
                )}
              </div>
              <p className="mt-1 text-[11px] text-slate-400" data-testid="execution-control-diff-anomaly-groups">
                groups={JSON.stringify(diffData?.anomaly_groups || {})}
              </p>
              <div className="mt-2 space-y-1 text-xs" data-testid="execution-control-diff-anomaly-notes-list">
                {anomalyNotesDisplay.map((note, idx) => (
                  <p key={`${note}-${idx}`} data-testid={`execution-control-diff-anomaly-note-${idx}`}>{note}</p>
                ))}
                {!anomalyNotesDisplay.length && <p data-testid="execution-control-diff-anomaly-empty-text">no anomaly note</p>}
              </div>
            </div>

            <div className="mt-2 rounded border border-slate-700 bg-slate-950 p-2" data-testid="execution-control-diff-section-recommended-actions">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs font-semibold text-slate-300">3) Recommended Actions</p>
                {longDiffCollapsed && (
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-6"
                    onClick={() => setShowFullDiffActions((prev) => !prev)}
                    data-testid="execution-control-diff-recommended-toggle-button"
                  >
                    {showFullDiffActions ? "Collapse" : "Expand"}
                  </Button>
                )}
              </div>
              <div className="mt-2 space-y-2 text-xs" data-testid="execution-control-diff-recommended-actions-list">
                {recommendedActionsDisplay.map((item, idx) => {
                  const severity = String(item?.severity || "info").toUpperCase();
                  const actionMeta = resolveRecommendedActionMeta(item);
                  const actionTitle = formatActionTitle(item?.action);
                  const severityStyle = severity === "CRITICAL"
                    ? "border-red-500 bg-red-950/40 text-red-300"
                    : severity === "WARNING"
                      ? "border-amber-500 bg-amber-950/40 text-amber-300"
                      : "border-emerald-500 bg-emerald-950/40 text-emerald-300";
                  const icon = severity === "CRITICAL" ? "🔴" : severity === "WARNING" ? "⚠️" : "✅";
                  return (
                    <div key={`${item.action}-${idx}`} className={`rounded border p-2 ${severityStyle}`} data-testid={`execution-control-diff-recommended-action-${idx}`}>
                      <p className="font-semibold" data-testid={`execution-control-diff-recommended-action-text-${idx}`}>
                        {icon} [{severity}] {actionTitle}
                      </p>
                      <p className="mt-1 text-[11px]" data-testid={`execution-control-diff-recommended-action-reason-${idx}`}>
                        → {item.reason}
                      </p>
                      {actionMeta.path ? (
                        <Button
                          size="sm"
                          variant="outline"
                          className="mt-2 h-7 border-current bg-transparent"
                          onClick={() => openRecommendedAction(item)}
                          data-testid={`execution-control-diff-recommended-action-link-${idx}`}
                        >
                          {actionMeta.label}
                        </Button>
                      ) : (
                        <p className="mt-1 text-[11px]" data-testid={`execution-control-diff-recommended-action-no-link-${idx}`}>
                          no action
                        </p>
                      )}
                    </div>
                  );
                })}
                {!recommendedActionsDisplay.length && <p data-testid="execution-control-diff-recommended-actions-empty">✅ [INFO] keep current policy (no action)</p>}
              </div>
            </div>

            <div className="mt-4 border border-slate-700 bg-slate-950 p-3 text-xs" data-testid="execution-control-diff-playbook-panel">
              <p className="font-semibold" data-testid="execution-control-diff-playbook-title">One-click Playbook (Preview + Confirm)</p>
              <p data-testid="execution-control-diff-playbook-note">Safe execution state flow: preview → approved → executing → executed/failed → rollback_available → rollback_executed</p>

              <div className="mt-2 rounded border border-slate-700 bg-black/40 p-2" data-testid="execution-control-diff-playbook-preflight-panel">
                <div className="flex flex-wrap items-center justify-between gap-2" data-testid="execution-control-diff-playbook-preflight-header-row">
                  <p className="font-semibold" data-testid="execution-control-diff-playbook-preflight-title">Operational Preflight</p>
                  <div className="flex items-center gap-2" data-testid="execution-control-diff-playbook-preflight-actions-row">
                    <span
                      className={`rounded border px-2 py-0.5 text-[11px] ${playbookPreflightUiStatus === "OK" ? "border-emerald-600 bg-emerald-950/40 text-emerald-300" : playbookPreflightUiStatus === "WARNING" ? "border-amber-600 bg-amber-950/40 text-amber-300" : "border-red-600 bg-red-950/40 text-red-300"}`}
                      data-testid="execution-control-diff-playbook-preflight-overall-state"
                    >
                      {playbookPreflightLoading ? "CHECKING" : playbookPreflightUiStatus}
                    </span>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 border-slate-500 bg-transparent"
                      onClick={() => loadPlaybookPreflight({ silent: false })}
                      disabled={playbookPreflightLoading}
                      data-testid="execution-control-diff-playbook-preflight-refresh-button"
                    >
                      Refresh Preflight
                    </Button>
                  </div>
                </div>

                <p className="mt-2 text-[11px] text-slate-300" data-testid="execution-control-diff-playbook-preflight-block-reason">
                  {playbookPreflightActionAllowed ? "Preflight OK/WARNING: aksiyon kapısı açık." : (playbookPreflightBlockReason || "Preflight sonucu bekleniyor")}
                </p>

                <p className="mt-1 text-[11px] text-slate-300" data-testid="execution-control-diff-playbook-preflight-score">
                  preflight_score: {playbookPreflight?.preflight_score ?? "-"} | queue_depth: {playbookPreflight?.queue_job_metrics?.queue_depth ?? "-"} | failed_backlog: {playbookPreflight?.queue_job_metrics?.failed_backlog ?? "-"}
                </p>

                <div className="mt-2 grid gap-2 md:grid-cols-2" data-testid="execution-control-diff-playbook-preflight-checks-grid">
                  {(playbookPreflight?.checks || []).map((item, idx) => {
                    const statusLabel = String(item?.ui_status || item?.status || "UNKNOWN").toUpperCase();
                    const tone = statusLabel === "OK"
                      ? "border-emerald-700 bg-emerald-950/20"
                      : statusLabel === "WARNING"
                        ? "border-amber-700 bg-amber-950/20"
                        : "border-red-700 bg-red-950/20";
                    return (
                      <div
                        key={`${item?.key || "check"}-${idx}`}
                        className={`rounded border p-2 ${tone}`}
                        data-testid={`execution-control-diff-playbook-preflight-check-${idx}`}
                      >
                        <p className="font-medium" data-testid={`execution-control-diff-playbook-preflight-check-title-${idx}`}>{item?.label || item?.key || "check"}</p>
                        <p data-testid={`execution-control-diff-playbook-preflight-check-status-${idx}`}>status: {statusLabel}</p>
                        <p className="text-[11px] text-slate-300" data-testid={`execution-control-diff-playbook-preflight-check-detail-${idx}`}>{item?.detail || "-"}</p>
                      </div>
                    );
                  })}
                </div>

                <div className="mt-2 grid gap-2 md:grid-cols-2" data-testid="execution-control-diff-playbook-preflight-meta-grid">
                  <p data-testid="execution-control-diff-playbook-preflight-migration">
                    migration: {playbookPreflight?.migration?.current || "-"} / required {playbookPreflight?.migration?.required || "-"}
                  </p>
                  <p data-testid="execution-control-diff-playbook-preflight-integrations">
                    integrations: Slack {playbookPreflight?.integration_modes?.slack || "-"} · Binance {playbookPreflight?.integration_modes?.binance || "-"}
                  </p>
                </div>
              </div>

              <div className="mt-2 flex flex-wrap gap-2" data-testid="execution-control-diff-playbook-buttons-row">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={previewDiffPlaybook}
                  disabled={playbookPreviewLoading || !diffData || !playbookPreflightActionAllowed}
                  data-testid="execution-control-diff-playbook-preview-button"
                >
                  Playbook Preview
                </Button>
                <Button
                  size="sm"
                  onClick={() => setPlaybookApplyDialogOpen(true)}
                  disabled={playbookApplyLoading || !isSuperAdmin || !playbookPreview?.preview_token || !playbookConfirmChecked || playbookReason.trim().length < 3 || !playbookPreflightActionAllowed}
                  title={!isSuperAdmin ? "Super admin required" : !playbookPreview?.preview_token ? "Önce preview alınmalı" : !playbookConfirmChecked ? "Confirm zorunlu" : playbookReason.trim().length < 3 ? "Reason en az 3 karakter" : ""}
                  data-testid="execution-control-diff-playbook-apply-button"
                >
                  Plan Apply (opsiyonel)
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={approveDiffPlaybook}
                  disabled={playbookApproveLoading || !isSuperAdmin || !playbookRunId || !playbookCanApprove || playbookReason.trim().length < 3 || !playbookPreflightActionAllowed}
                  title={!isSuperAdmin ? "Super admin required" : !playbookCanApprove ? "Approve için preview/planned state gerekli" : ""}
                  data-testid="execution-control-diff-playbook-approve-button"
                >
                  Approve
                </Button>
                <Button
                  size="sm"
                  onClick={() => setPlaybookExecuteDialogOpen(true)}
                  disabled={playbookExecuteLoading || !isSuperAdmin || !playbookRunId || playbookExecutionState !== "approved" || playbookReason.trim().length < 3 || !playbookPreflightActionAllowed}
                  title={!isSuperAdmin ? "Super admin required" : playbookExecutionState !== "approved" ? "Execute için playbook approved olmalı" : ""}
                  data-testid="execution-control-diff-playbook-execute-button"
                >
                  Execute
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={rollbackDiffPlaybook}
                  disabled={playbookRollbackLoading || !playbookCanRollback || playbookReason.trim().length < 3 || !playbookPreflightActionAllowed}
                  data-testid="execution-control-diff-playbook-rollback-button"
                >
                  Rollback
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={retryFailedPlaybook}
                  disabled={playbookRetryLoading || !playbookCanRetry || playbookReason.trim().length < 3 || !playbookPreflightActionAllowed}
                  data-testid="execution-control-diff-playbook-retry-button"
                >
                  Retry Failed
                </Button>
              </div>

              <p className="mt-2" data-testid="execution-control-diff-playbook-preview-token">
                preview_token: {playbookPreview?.preview_token || "-"}
              </p>
              <p data-testid="execution-control-diff-playbook-run-id">playbook_run_id: {playbookRunId || "-"}</p>
              <p data-testid="execution-control-diff-playbook-state">execution_state: {playbookExecutionState || "-"}</p>
              <p data-testid="execution-control-diff-playbook-severity">
                highest_severity: {playbookPreview?.highest_severity || "-"}
              </p>

              <div className="mt-2" data-testid="execution-control-diff-playbook-progress-panel">
                <div className="flex items-center justify-between text-[11px]" data-testid="execution-control-diff-playbook-progress-header-row">
                  <p data-testid="execution-control-diff-playbook-progress-text">progress: {playbookStepIndex}/{playbookTotalSteps}</p>
                  <p data-testid="execution-control-diff-playbook-progress-percent">{playbookProgressPct}%</p>
                </div>
                <div className="mt-1 h-2 w-full overflow-hidden rounded bg-slate-800" data-testid="execution-control-diff-playbook-progress-track">
                  <div
                    className={`h-full ${playbookExecutionState === "failed" ? "bg-red-500" : "bg-emerald-500"}`}
                    style={{ width: `${playbookProgressPct}%` }}
                    data-testid="execution-control-diff-playbook-progress-bar"
                  />
                </div>
                {playbookFailureReason ? (
                  <p className="mt-1 text-red-300" data-testid="execution-control-diff-playbook-failure-reason">
                    failure_reason: {playbookFailureReason}
                  </p>
                ) : null}
              </div>

              <div className="mt-2 grid gap-1" data-testid="execution-control-diff-playbook-steps-list">
                {playbookStepsView.map((step, idx) => {
                  const stepNumber = Number(step?.step || idx + 1);
                  const currentState = String(playbookExecutionState || "");
                  const isFailedStep = currentState === "failed" && stepNumber === playbookStepIndex;
                  const isExecutedStep = playbookStepIndex >= stepNumber && ["executed", "rollback_available", "rollback_executed"].includes(currentState);
                  const statusLabel = isFailedStep
                    ? "FAILED"
                    : isExecutedStep
                      ? "DONE"
                      : currentState === "executing" && stepNumber === playbookStepIndex
                        ? "RUNNING"
                        : "PENDING";
                  const tone = statusLabel === "FAILED"
                    ? "border-red-600 bg-red-950/30"
                    : statusLabel === "DONE"
                      ? "border-emerald-600 bg-emerald-950/20"
                      : statusLabel === "RUNNING"
                        ? "border-amber-600 bg-amber-950/20"
                        : "border-slate-700 bg-slate-900/40";
                  return (
                    <div key={`${step?.action || "step"}-${stepNumber}`} className={`rounded border px-2 py-1 ${tone}`} data-testid={`execution-control-diff-playbook-step-${idx}`}>
                      <p data-testid={`execution-control-diff-playbook-step-title-${idx}`}>#{stepNumber} {step?.action || "unknown"}</p>
                      <p className="text-[11px]" data-testid={`execution-control-diff-playbook-step-status-${idx}`}>status: {statusLabel}</p>
                    </div>
                  );
                })}
                {!playbookStepsView.length && <p data-testid="execution-control-diff-playbook-steps-empty">step list yok</p>}
              </div>

              <p className="mt-1 text-[11px] text-slate-300" data-testid="execution-control-diff-playbook-retry-semantics">
                retry_semantics: new_run_with_parent_reference = {playbookRunDetail?.parent_run_id ? "true" : "false"}
              </p>

              <p className="mt-1 text-[11px] text-slate-300" data-testid="execution-control-diff-playbook-detail-loading">
                run_detail_loading: {String(playbookRunDetailLoading)}
              </p>

              <Input
                value={playbookReason}
                onChange={(event) => setPlaybookReason(event.target.value)}
                placeholder="playbook apply reason"
                data-testid="execution-control-diff-playbook-reason-input"
              />

              <label className="mt-2 flex items-center gap-2" data-testid="execution-control-diff-playbook-confirm-row">
                <input
                  type="checkbox"
                  checked={playbookConfirmChecked}
                  onChange={(event) => setPlaybookConfirmChecked(event.target.checked)}
                  data-testid="execution-control-diff-playbook-confirm-checkbox"
                />
                <span>Preview adımlarını kontrol ettim, apply için onaylıyorum.</span>
              </label>
            </div>
          </div>
        )}

        <Dialog open={playbookApplyDialogOpen} onOpenChange={setPlaybookApplyDialogOpen}>
          <DialogContent data-testid="execution-control-diff-playbook-apply-dialog">
            <DialogHeader>
              <DialogTitle data-testid="execution-control-diff-playbook-apply-dialog-title">Playbook Plan Apply Onayı</DialogTitle>
              <DialogDescription data-testid="execution-control-diff-playbook-apply-dialog-description">
                Bu işlem playbook’u planned state’e geçirir.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setPlaybookApplyDialogOpen(false)} data-testid="execution-control-diff-playbook-apply-dialog-cancel-button">Vazgeç</Button>
              <Button
                onClick={async () => {
                  await applyDiffPlaybook();
                  setPlaybookApplyDialogOpen(false);
                }}
                disabled={!isSuperAdmin}
                title={!isSuperAdmin ? "Super admin required" : ""}
                data-testid="execution-control-diff-playbook-apply-dialog-confirm-button"
              >
                Onayla
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={playbookExecuteDialogOpen} onOpenChange={setPlaybookExecuteDialogOpen}>
          <DialogContent data-testid="execution-control-diff-playbook-execute-dialog">
            <DialogHeader>
              <DialogTitle data-testid="execution-control-diff-playbook-execute-dialog-title">Playbook Execute Onayı</DialogTitle>
              <DialogDescription data-testid="execution-control-diff-playbook-execute-dialog-description">
                Execute sadece approved playbook için çalışır. Devam edilsin mi?
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setPlaybookExecuteDialogOpen(false)} data-testid="execution-control-diff-playbook-execute-dialog-cancel-button">Vazgeç</Button>
              <Button
                onClick={async () => {
                  await executeDiffPlaybook();
                  setPlaybookExecuteDialogOpen(false);
                }}
                disabled={!isSuperAdmin}
                title={!isSuperAdmin ? "Super admin required" : ""}
                data-testid="execution-control-diff-playbook-execute-dialog-confirm-button"
              >
                Execute
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </section>
  );
};
