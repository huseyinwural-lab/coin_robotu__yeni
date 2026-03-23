import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";

const STATUS_OPTIONS = ["all", "QUEUED", "APPROVED", "RELEASED", "REJECTED", "CANCELLED"];
const RISK_OPTIONS = ["all", "high", "med", "low"];
const TYPE_OPTIONS = ["all", "OPEN_POSITION", "CLOSE_POSITION", "PARTIAL_CLOSE", "REVERSE_POSITION", "MOVE_STOP", "MOVE_TAKE_PROFIT"];

const extractErrorMessage = (error, fallbackText) => {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const joined = detail
      .map((item) => (typeof item === "string" ? item : item?.msg || item?.message || JSON.stringify(item)))
      .filter(Boolean)
      .join(" | ");
    if (joined) return joined;
  }
  if (detail && typeof detail === "object") {
    return detail.message || detail.msg || detail.reason_code || JSON.stringify(detail);
  }
  return fallbackText;
};

const formatDate = (value) => (value ? new Date(value).toLocaleString() : "-");

export const AdminExecutionQueuePage = () => {
  const { user } = useAuth();
  const isSuperAdmin = String(user?.role || "") === "super_admin";

  const [queueRows, setQueueRows] = useState([]);
  const [queueSnapshot, setQueueSnapshot] = useState(null);
  const [rejectionSummary, setRejectionSummary] = useState([]);
  const [rejectionTrend, setRejectionTrend] = useState([]);
  const [rejectionGuidance, setRejectionGuidance] = useState([]);
  const [observability, setObservability] = useState(null);
  const [queueControlState, setQueueControlState] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [lastLoadedAt, setLastLoadedAt] = useState(null);
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);

  const [statusFilter, setStatusFilter] = useState("QUEUED");
  const [riskFilter, setRiskFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [sortBy, setSortBy] = useState("created_at");
  const [sortDir, setSortDir] = useState("desc");

  const [selectedIntentId, setSelectedIntentId] = useState("");
  const [selectedDetail, setSelectedDetail] = useState(null);
  const [selectedHistory, setSelectedHistory] = useState([]);
  const [decisionReason, setDecisionReason] = useState("");
  const [overrideEnabled, setOverrideEnabled] = useState(false);
  const [decisionLoading, setDecisionLoading] = useState(false);
  const [readAckState, setReadAckState] = useState({});
  const [manualEditPatch, setManualEditPatch] = useState({});
  const [manualEditReason, setManualEditReason] = useState("");

  const [selectedBulkIds, setSelectedBulkIds] = useState([]);
  const [bulkReason, setBulkReason] = useState("");
  const [bulkReadAcknowledged, setBulkReadAcknowledged] = useState(false);
  const [bulkDoubleConfirm, setBulkDoubleConfirm] = useState(false);
  const [bulkLoading, setBulkLoading] = useState(false);

  const [queueControlReason, setQueueControlReason] = useState("");
  const [queueControlLoading, setQueueControlLoading] = useState(false);

  const selectedRow = useMemo(
    () => queueRows.find((item) => item.id === selectedIntentId) || null,
    [queueRows, selectedIntentId],
  );

  const currentReadAck = useMemo(() => {
    if (!selectedIntentId || !selectedDetail?.detail_version) return { ack: false, highRiskConfirm: false, version: "" };
    const entry = readAckState[selectedIntentId];
    if (!entry || entry.version !== selectedDetail.detail_version) {
      return { ack: false, highRiskConfirm: false, version: selectedDetail.detail_version };
    }
    return entry;
  }, [readAckState, selectedDetail, selectedIntentId]);

  const summary = useMemo(() => {
    const statusCounts = queueRows.reduce((acc, row) => {
      const key = row.status || "UNKNOWN";
      acc[key] = (acc[key] || 0) + 1;
      return acc;
    }, {});
    return {
      total: queueRows.length,
      queued: statusCounts.QUEUED || 0,
      rejected: statusCounts.REJECTED || 0,
      released: statusCounts.RELEASED || 0,
      highRisk: queueRows.filter((row) => row.risk_payload?.is_high_risk).length,
    };
  }, [queueRows]);

  const staleSeconds = useMemo(() => {
    if (!lastLoadedAt) return 0;
    return Math.max(Math.floor((Date.now() - lastLoadedAt) / 1000), 0);
  }, [lastLoadedAt]);

  const staleDataDetected = staleSeconds >= 20;

  const selectedBulkRows = useMemo(
    () => queueRows.filter((row) => selectedBulkIds.includes(row.id)),
    [queueRows, selectedBulkIds],
  );

  const bulkHasHighRisk = useMemo(
    () => selectedBulkRows.some((row) => row.risk_payload?.is_high_risk),
    [selectedBulkRows],
  );

  const load = useCallback(async () => {
    setIsLoading(true);
    setLoadError("");
    try {
      const params = {
        status_filter: statusFilter,
        risk_filter: riskFilter,
        type_filter: typeFilter,
        sort_by: sortBy,
        sort_dir: sortDir,
        limit: 200,
      };
      if (searchQuery.trim()) params.search = searchQuery.trim();

      const [queueRes, summaryRes, controlRes, observabilityRes] = await Promise.all([
        apiClient.get("/admin/execution-queue", { params }),
        apiClient.get("/admin/execution-queue/rejection-summary", { params: { limit: 1000 } }),
        apiClient.get("/admin/execution-queue/control/state"),
        apiClient.get("/admin/execution-queue/observability"),
      ]);

      setQueueRows(queueRes.data || []);
      setQueueSnapshot(summaryRes.data?.queue || null);
      setRejectionSummary(summaryRes.data?.rejection_reason_distribution || []);
      setRejectionTrend(summaryRes.data?.trend || []);
      setRejectionGuidance(summaryRes.data?.guidance || []);
      setQueueControlState(controlRes.data || null);
      setObservability(observabilityRes.data || null);
      setLastLoadedAt(Date.now());
    } catch (error) {
      const message = extractErrorMessage(error, "Execution queue verisi yüklenemedi");
      setLoadError(message);
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  }, [riskFilter, searchQuery, sortBy, sortDir, statusFilter, typeFilter]);

  const loadIntentDetail = useCallback(async (intentId) => {
    try {
      const [detailRes, historyRes] = await Promise.all([
        apiClient.get(`/admin/execution-queue/${intentId}/detail`),
        apiClient.get(`/admin/execution-queue/${intentId}/history`, { params: { limit: 200 } }),
      ]);
      setSelectedDetail(detailRes.data || null);
      setSelectedHistory(historyRes.data || []);
    } catch (error) {
      toast.error(extractErrorMessage(error, "Intent detayları yüklenemedi"));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!autoRefreshEnabled) return undefined;
    const timer = setInterval(() => {
      load();
      if (selectedIntentId) {
        loadIntentDetail(selectedIntentId);
      }
    }, 12000);
    return () => clearInterval(timer);
  }, [autoRefreshEnabled, load, loadIntentDetail, selectedIntentId]);

  const openDetail = async (intentId) => {
    setSelectedIntentId(intentId);
    setDecisionReason("");
    setOverrideEnabled(false);
    setManualEditPatch({});
    setManualEditReason("");
    await loadIntentDetail(intentId);
  };

  const closeDetail = () => {
    setSelectedIntentId("");
    setSelectedDetail(null);
    setSelectedHistory([]);
    setDecisionReason("");
    setOverrideEnabled(false);
  };

  const updateReadAckState = (nextPatch) => {
    if (!selectedIntentId || !selectedDetail?.detail_version) return;
    setReadAckState((prev) => ({
      ...prev,
      [selectedIntentId]: {
        version: selectedDetail.detail_version,
        ack: nextPatch.ack ?? currentReadAck.ack,
        highRiskConfirm: nextPatch.highRiskConfirm ?? currentReadAck.highRiskConfirm,
      },
    }));
  };

  const executeDecision = async (action) => {
    if (!selectedIntentId) return;
    setDecisionLoading(true);
    try {
      const payload = {
        reason: decisionReason,
        read_acknowledged: currentReadAck.ack,
        detail_version: selectedDetail?.detail_version,
        double_confirmation: currentReadAck.highRiskConfirm,
        override_execute: overrideEnabled,
      };
      await apiClient.post(`/admin/execution-queue/${selectedIntentId}/${action}`, payload);
      toast.success(`Intent ${action} tamamlandı`);
      await Promise.all([load(), loadIntentDetail(selectedIntentId)]);
    } catch (error) {
      toast.error(extractErrorMessage(error, `Intent ${action} başarısız`));
    } finally {
      setDecisionLoading(false);
    }
  };

  const retryIntent = async (intentId) => {
    const reason = window.prompt("Retry nedeni (zorunlu):", "retry_from_admin_queue");
    if (!reason || reason.trim().length < 3) {
      toast.error("Retry reason zorunlu");
      return;
    }
    try {
      await apiClient.post(`/admin/execution-queue/${intentId}/retry`, { reason: reason.trim() });
      toast.success("Intent retry edildi");
      await load();
    } catch (error) {
      toast.error(extractErrorMessage(error, "Retry başarısız"));
    }
  };

  const applyManualEdit = async () => {
    if (!selectedIntentId) return;
    if (!manualEditReason || manualEditReason.trim().length < 3) {
      toast.error("Manual edit reason zorunlu");
      return;
    }
    try {
      await apiClient.patch(`/admin/execution-queue/${selectedIntentId}/edit`, {
        ...manualEditPatch,
        reason: manualEditReason,
      });
      toast.success("Intent düzenlendi ve re-validate edildi");
      await Promise.all([load(), loadIntentDetail(selectedIntentId)]);
    } catch (error) {
      toast.error(extractErrorMessage(error, "Manual edit başarısız"));
    }
  };

  const runBulkAction = async (action) => {
    if (!selectedBulkIds.length) {
      toast.error("Bulk işlem için intent seçin");
      return;
    }
    if (!bulkReason || bulkReason.trim().length < 3) {
      toast.error("Bulk reason zorunlu");
      return;
    }
    if (bulkHasHighRisk && !bulkDoubleConfirm) {
      toast.error("High-risk bulk seçimde ek toplu onay zorunlu");
      return;
    }

    setBulkLoading(true);
    try {
      const { data } = await apiClient.post("/admin/execution-queue/bulk-decision", {
        intent_ids: selectedBulkIds,
        action,
        reason: bulkReason,
        read_acknowledged: bulkReadAcknowledged,
        double_confirmation: bulkDoubleConfirm,
      });
      toast.success(`Bulk ${action}: processed=${data.processed_count} failed=${data.failed_count}`);
      setSelectedBulkIds([]);
      await load();
    } catch (error) {
      toast.error(extractErrorMessage(error, `Bulk ${action} başarısız`));
    } finally {
      setBulkLoading(false);
    }
  };

  const runQueueControl = async (action) => {
    if (!queueControlReason || queueControlReason.trim().length < 3) {
      toast.error("Queue control reason zorunlu");
      return;
    }
    setQueueControlLoading(true);
    try {
      const { data } = await apiClient.post(`/admin/execution-queue/control/${action}`, {
        reason: queueControlReason,
      });
      setQueueControlState(data || null);
      toast.success(`Queue ${action} tamamlandı`);
      await load();
    } catch (error) {
      toast.error(extractErrorMessage(error, `Queue ${action} başarısız`));
    } finally {
      setQueueControlLoading(false);
    }
  };

  const toggleBulkSelection = (intentId) => {
    setSelectedBulkIds((prev) => (prev.includes(intentId) ? prev.filter((id) => id !== intentId) : [...prev, intentId]));
  };

  const allVisibleSelected = queueRows.length > 0 && queueRows.every((row) => selectedBulkIds.includes(row.id));

  if (isLoading) {
    return <LoadingSkeleton rows={8} testId="admin-execution-queue-loading-skeleton" />;
  }

  return (
    <section className="space-y-5" data-testid="execution-decision-gate-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="execution-decision-gate-header">
        <div className="flex flex-wrap items-start justify-between gap-3" data-testid="execution-decision-gate-header-row">
          <div data-testid="execution-decision-gate-header-left">
            <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="execution-decision-gate-title">
              Execution Approval + Control Center
            </h2>
            <p className="mt-2 text-sm text-slate-300" data-testid="execution-decision-gate-description">
              Bu ekran go / no-go kapısıdır. Detay + reason + risk onayı olmadan karar verilemez.
            </p>
            <p className="mt-2 text-xs text-slate-400" data-testid="execution-decision-gate-meta">
              role={user?.role || "unknown"} · queue_paused={String(Boolean(queueControlState?.paused))}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2" data-testid="execution-decision-gate-header-actions">
            <Button variant="outline" onClick={() => setAutoRefreshEnabled((prev) => !prev)} data-testid="execution-auto-refresh-toggle-button">
              Auto Refresh: {autoRefreshEnabled ? "Açık" : "Kapalı"}
            </Button>
            <Button onClick={load} data-testid="execution-refresh-button">Yenile</Button>
          </div>
        </div>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6" data-testid="execution-summary-grid">
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="execution-summary-total">
          <p className="text-xs text-slate-400">Total</p>
          <p className="text-xl font-semibold" data-testid="execution-summary-total-value">{summary.total}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="execution-summary-queued">
          <p className="text-xs text-slate-400">Queued</p>
          <p className="text-xl font-semibold" data-testid="execution-summary-queued-value">{summary.queued}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="execution-summary-high-risk">
          <p className="text-xs text-slate-400">High Risk</p>
          <p className="text-xl font-semibold text-rose-300" data-testid="execution-summary-high-risk-value">{summary.highRisk}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="execution-summary-rejected">
          <p className="text-xs text-slate-400">Rejected</p>
          <p className="text-xl font-semibold" data-testid="execution-summary-rejected-value">{summary.rejected}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="execution-summary-latency">
          <p className="text-xs text-slate-400">Approval Avg (sn)</p>
          <p className="text-xl font-semibold" data-testid="execution-summary-latency-value">
            {Number(observability?.metrics?.approval_latency_seconds?.avg || 0).toFixed(2)}
          </p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="execution-summary-stale">
          <p className="text-xs text-slate-400">Stale Indicator</p>
          <p className={`text-xl font-semibold ${staleDataDetected ? "text-rose-300" : "text-emerald-300"}`} data-testid="execution-summary-stale-value">
            {staleDataDetected ? `STALE (${staleSeconds}s)` : `GÜNCEL (${staleSeconds}s)`}
          </p>
        </article>
      </div>

      {loadError && (
        <div className="border border-amber-500/40 bg-amber-900/20 p-3 text-sm text-amber-100" data-testid="execution-warning-alert">
          Son yenilemede hata: {loadError}
        </div>
      )}

      <section className="border border-slate-800 bg-slate-900 p-4" data-testid="execution-filter-panel">
        <div className="grid gap-2 md:grid-cols-6" data-testid="execution-filter-grid">
          <input
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="symbol / user / intent id"
            className="h-9 rounded border border-slate-700 bg-slate-950 px-2 text-sm"
            data-testid="execution-search-input"
          />
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} className="h-9 rounded border border-slate-700 bg-slate-950 px-2 text-sm" data-testid="execution-status-filter-select">
            {STATUS_OPTIONS.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <select value={riskFilter} onChange={(event) => setRiskFilter(event.target.value)} className="h-9 rounded border border-slate-700 bg-slate-950 px-2 text-sm" data-testid="execution-risk-filter-select">
            {RISK_OPTIONS.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)} className="h-9 rounded border border-slate-700 bg-slate-950 px-2 text-sm" data-testid="execution-type-filter-select">
            {TYPE_OPTIONS.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <select value={sortBy} onChange={(event) => setSortBy(event.target.value)} className="h-9 rounded border border-slate-700 bg-slate-950 px-2 text-sm" data-testid="execution-sort-by-select">
            <option value="created_at">created_at</option>
            <option value="updated_at">updated_at</option>
            <option value="notional">notional</option>
            <option value="size">size</option>
            <option value="risk_score">risk_score</option>
          </select>
          <select value={sortDir} onChange={(event) => setSortDir(event.target.value)} className="h-9 rounded border border-slate-700 bg-slate-950 px-2 text-sm" data-testid="execution-sort-dir-select">
            <option value="desc">desc</option>
            <option value="asc">asc</option>
          </select>
        </div>
      </section>

      <section className="border border-slate-800 bg-slate-900 p-4" data-testid="execution-bulk-panel">
        <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="execution-bulk-title">Bulk Operations (max 20)</p>
        <div className="mt-3 grid gap-2 md:grid-cols-5" data-testid="execution-bulk-grid">
          <input
            value={bulkReason}
            onChange={(event) => setBulkReason(event.target.value)}
            className="h-9 rounded border border-slate-700 bg-slate-950 px-2 text-sm md:col-span-2"
            placeholder="bulk reason"
            data-testid="execution-bulk-reason-input"
          />
          <label className="flex items-center gap-2 text-xs text-slate-300" data-testid="execution-bulk-read-ack-label">
            <input type="checkbox" checked={bulkReadAcknowledged} onChange={(event) => setBulkReadAcknowledged(event.target.checked)} data-testid="execution-bulk-read-ack-checkbox" />
            detay okundu
          </label>
          <label className="flex items-center gap-2 text-xs text-rose-200" data-testid="execution-bulk-high-risk-ack-label">
            <input type="checkbox" checked={bulkDoubleConfirm} onChange={(event) => setBulkDoubleConfirm(event.target.checked)} data-testid="execution-bulk-high-risk-confirm-checkbox" />
            high-risk toplu onay
          </label>
          <p className="text-xs text-slate-400" data-testid="execution-bulk-selection-count">selection={selectedBulkIds.length}</p>
        </div>
        <div className="mt-3 flex flex-wrap gap-2" data-testid="execution-bulk-actions-row">
          <Button onClick={() => runBulkAction("approve")} disabled={bulkLoading} data-testid="execution-bulk-approve-button">Bulk Approve</Button>
          <Button variant="outline" onClick={() => runBulkAction("reject")} disabled={bulkLoading} data-testid="execution-bulk-reject-button">Bulk Reject</Button>
          <Button variant="outline" onClick={() => runBulkAction("cancel")} disabled={bulkLoading} data-testid="execution-bulk-cancel-button">Bulk Cancel</Button>
        </div>
        {bulkHasHighRisk && <p className="mt-2 text-xs text-rose-300" data-testid="execution-bulk-high-risk-warning">Seçimde high-risk intent var; ek toplu onay zorunlu.</p>}
      </section>

      {isSuperAdmin && (
        <section className="border border-slate-800 bg-slate-900 p-4" data-testid="execution-queue-control-panel">
          <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="execution-queue-control-title">Queue Control (super_admin)</p>
          <div className="mt-3 grid gap-2 md:grid-cols-4" data-testid="execution-queue-control-grid">
            <input
              value={queueControlReason}
              onChange={(event) => setQueueControlReason(event.target.value)}
              className="h-9 rounded border border-slate-700 bg-slate-950 px-2 text-sm md:col-span-2"
              placeholder="queue control reason"
              data-testid="execution-queue-control-reason-input"
            />
            <Button variant="outline" onClick={() => runQueueControl("pause")} disabled={queueControlLoading} data-testid="execution-queue-pause-button">Pause Queue</Button>
            <Button variant="outline" onClick={() => runQueueControl("resume")} disabled={queueControlLoading} data-testid="execution-queue-resume-button">Resume Queue</Button>
          </div>
          <div className="mt-2 flex items-center justify-between" data-testid="execution-queue-control-footer-row">
            <p className="text-xs text-slate-400" data-testid="execution-queue-control-state-text">
              paused={String(Boolean(queueControlState?.paused))} · by={queueControlState?.paused_by || "-"} · reason={queueControlState?.paused_reason || "-"}
            </p>
            <Button variant="outline" onClick={() => runQueueControl("clear")} disabled={queueControlLoading} data-testid="execution-queue-clear-button">Clear Queue</Button>
          </div>
        </section>
      )}

      <section className="border border-slate-800 bg-slate-900 p-4" data-testid="execution-reject-analytics-panel">
        <div className="grid gap-3 md:grid-cols-3" data-testid="execution-reject-analytics-grid">
          <div data-testid="execution-reject-distribution-block">
            <p className="text-xs uppercase tracking-widest text-slate-400">Reject Distribution</p>
            <div className="mt-2 space-y-1" data-testid="execution-reject-distribution-list">
              {rejectionSummary.slice(0, 8).map((item, idx) => (
                <p key={`${item.reason_code}-${idx}`} className="text-xs" data-testid={`execution-reject-distribution-item-${idx}`}>
                  {item.reason_code}: {item.count}
                </p>
              ))}
            </div>
          </div>
          <div data-testid="execution-reject-trend-block">
            <p className="text-xs uppercase tracking-widest text-slate-400">Reject Trend</p>
            <div className="mt-2 space-y-1" data-testid="execution-reject-trend-list">
              {rejectionTrend.slice(-7).map((item, idx) => (
                <p key={`${item.date}-${idx}`} className="text-xs" data-testid={`execution-reject-trend-item-${idx}`}>
                  {item.date}: {item.count}
                </p>
              ))}
            </div>
          </div>
          <div data-testid="execution-reject-guidance-block">
            <p className="text-xs uppercase tracking-widest text-slate-400">Fix Guidance</p>
            <div className="mt-2 space-y-1" data-testid="execution-reject-guidance-list">
              {rejectionGuidance.slice(0, 6).map((item, idx) => (
                <p key={`${item.reason_code}-${idx}`} className="text-xs" data-testid={`execution-reject-guidance-item-${idx}`}>
                  {item.reason_code}: {item.guidance}
                </p>
              ))}
            </div>
          </div>
        </div>
      </section>

      <div className="overflow-x-auto border border-slate-800 bg-slate-900" data-testid="execution-queue-table-wrapper">
        <table className="min-w-full text-sm" data-testid="execution-queue-table" aria-label="Execution queue table">
          <thead className="sticky top-0 z-20 bg-slate-800 text-left" data-testid="execution-queue-table-head">
            <tr>
              <th className="px-3 py-2">
                <input
                  type="checkbox"
                  checked={allVisibleSelected}
                  onChange={() => setSelectedBulkIds(allVisibleSelected ? [] : queueRows.map((row) => row.id).slice(0, 20))}
                  data-testid="execution-select-all-checkbox"
                />
              </th>
              <th className="px-3 py-2">Intent</th>
              <th className="px-3 py-2">Symbol</th>
              <th className="px-3 py-2">Notional</th>
              <th className="px-3 py-2">Risk</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Operational</th>
              <th className="px-3 py-2">Created</th>
              <th className="px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody data-testid="execution-queue-table-body">
            {queueRows.map((row) => {
              const highRisk = Boolean(row.risk_payload?.is_high_risk);
              return (
                <tr key={row.id} className={`border-t border-slate-800 ${highRisk ? "bg-rose-950/20" : ""}`} data-testid={`execution-queue-row-${row.id}`}>
                  <td className="px-3 py-2" data-testid={`execution-queue-row-select-${row.id}`}>
                    <input type="checkbox" checked={selectedBulkIds.includes(row.id)} onChange={() => toggleBulkSelection(row.id)} data-testid={`execution-queue-select-checkbox-${row.id}`} />
                  </td>
                  <td className="px-3 py-2" data-testid={`execution-queue-row-intent-${row.id}`}>{row.id}</td>
                  <td className="px-3 py-2" data-testid={`execution-queue-row-symbol-${row.id}`}>{row.symbol}</td>
                  <td className="px-3 py-2" data-testid={`execution-queue-row-notional-${row.id}`}>{Number(row.notional || 0).toFixed(2)}</td>
                  <td className="px-3 py-2" data-testid={`execution-queue-row-risk-${row.id}`} title={row.risk_payload?.tooltip || ""}>
                    <span className={`rounded px-2 py-1 text-xs font-semibold ${highRisk ? "bg-rose-500 text-white" : row.risk_payload?.severity === "med" ? "bg-amber-400 text-black" : "bg-emerald-400 text-black"}`} data-testid={`execution-queue-risk-severity-${row.id}`}>
                      {row.risk_payload?.severity || "low"}
                    </span>
                  </td>
                  <td className="px-3 py-2" data-testid={`execution-queue-row-status-${row.id}`}>{row.status}</td>
                  <td className="px-3 py-2" data-testid={`execution-queue-row-operational-${row.id}`}>{row.operational_status || "retryable"}</td>
                  <td className="px-3 py-2" data-testid={`execution-queue-row-created-${row.id}`}>{formatDate(row.created_at)}</td>
                  <td className="px-3 py-2" data-testid={`execution-queue-row-actions-${row.id}`}>
                    <div className="flex flex-wrap gap-2">
                      <Button size="sm" variant="outline" onClick={() => openDetail(row.id)} data-testid={`execution-open-detail-button-${row.id}`}>Detay</Button>
                      {row.status === "REJECTED" && (
                        <Button size="sm" variant="outline" onClick={() => retryIntent(row.id)} data-testid={`execution-retry-button-${row.id}`}>Retry</Button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
            {queueRows.length === 0 && (
              <tr data-testid="execution-queue-empty-row">
                <td colSpan={9} className="px-3 py-6 text-center text-sm text-slate-400" data-testid="execution-queue-empty-text">
                  Bu filtrede kayıt bulunamadı.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {selectedIntentId && (
        <section className="border border-emerald-600/40 bg-slate-950 p-4" data-testid="execution-intent-detail-drawer">
          <div className="flex items-center justify-between" data-testid="execution-intent-detail-header-row">
            <h3 className="text-lg font-semibold" data-testid="execution-intent-detail-title">Intent Detail: {selectedIntentId}</h3>
            <Button variant="outline" onClick={closeDetail} data-testid="execution-intent-detail-close-button">Kapat</Button>
          </div>

          <div className="mt-3 grid gap-3 lg:grid-cols-2" data-testid="execution-intent-detail-grid">
            <article className="rounded border border-slate-700 p-3" data-testid="execution-intent-detail-order-preview">
              <p className="text-xs uppercase tracking-widest text-slate-400">Order Preview</p>
              <pre className="mt-2 overflow-auto text-xs" data-testid="execution-intent-detail-order-preview-json">{JSON.stringify(selectedDetail?.order_preview || {}, null, 2)}</pre>
            </article>
            <article className="rounded border border-slate-700 p-3" data-testid="execution-intent-detail-normalized-payload">
              <p className="text-xs uppercase tracking-widest text-slate-400">Normalized Payload</p>
              <pre className="mt-2 overflow-auto text-xs" data-testid="execution-intent-detail-normalized-payload-json">{JSON.stringify(selectedDetail?.normalized_payload || {}, null, 2)}</pre>
            </article>
            <article className="rounded border border-slate-700 p-3" data-testid="execution-intent-detail-risk-payload">
              <p className="text-xs uppercase tracking-widest text-slate-400">Risk Flags & Breakdown</p>
              <pre className="mt-2 overflow-auto text-xs" data-testid="execution-intent-detail-risk-payload-json">{JSON.stringify(selectedDetail?.risk_payload || {}, null, 2)}</pre>
            </article>
            <article className="rounded border border-slate-700 p-3" data-testid="execution-intent-detail-expected-impact">
              <p className="text-xs uppercase tracking-widest text-slate-400">Expected Impact</p>
              <pre className="mt-2 overflow-auto text-xs" data-testid="execution-intent-detail-expected-impact-json">{JSON.stringify(selectedDetail?.expected_impact || {}, null, 2)}</pre>
            </article>
          </div>

          <article className="mt-3 rounded border border-slate-700 p-3" data-testid="execution-intent-history-panel">
            <p className="text-xs uppercase tracking-widest text-slate-400">Action History</p>
            <div className="mt-2 max-h-40 space-y-1 overflow-auto" data-testid="execution-intent-history-list">
              {selectedHistory.map((item, idx) => (
                <p key={`${item.id}-${idx}`} className="text-xs" data-testid={`execution-intent-history-item-${idx}`}>
                  {formatDate(item.created_at)} · {item.action} · {item.actor_role || "system"} · reason={item.reason || "-"}
                </p>
              ))}
            </div>
          </article>

          <article className="mt-3 rounded border border-slate-700 p-3" data-testid="execution-intent-manual-edit-panel">
            <p className="text-xs uppercase tracking-widest text-slate-400">Manual Edit + Re-validation</p>
            <div className="mt-2 grid gap-2 md:grid-cols-3" data-testid="execution-intent-manual-edit-grid">
              {["notional", "size", "price", "stop_price", "take_profit_price"].map((field) => (
                <input
                  key={field}
                  type="number"
                  placeholder={field}
                  value={manualEditPatch[field] ?? ""}
                  onChange={(event) => setManualEditPatch((prev) => ({ ...prev, [field]: event.target.value === "" ? undefined : Number(event.target.value) }))}
                  className="h-9 rounded border border-slate-700 bg-slate-900 px-2 text-sm"
                  data-testid={`execution-intent-manual-edit-input-${field}`}
                />
              ))}
            </div>
            <div className="mt-2 flex flex-wrap gap-2" data-testid="execution-intent-manual-edit-actions-row">
              <input
                value={manualEditReason}
                onChange={(event) => setManualEditReason(event.target.value)}
                className="h-9 flex-1 rounded border border-slate-700 bg-slate-900 px-2 text-sm"
                placeholder="manual edit reason"
                data-testid="execution-intent-manual-edit-reason-input"
              />
              <Button variant="outline" onClick={applyManualEdit} data-testid="execution-intent-manual-edit-save-button">Save + Revalidate</Button>
            </div>
          </article>

          <article className="mt-3 rounded border border-slate-700 p-3" data-testid="execution-intent-decision-panel">
            <p className="text-xs uppercase tracking-widest text-slate-400">Decision Enforcement</p>
            <div className="mt-2 grid gap-2 md:grid-cols-2" data-testid="execution-intent-decision-grid">
              <input
                value={decisionReason}
                onChange={(event) => setDecisionReason(event.target.value)}
                className="h-9 rounded border border-slate-700 bg-slate-900 px-2 text-sm"
                placeholder="decision reason (zorunlu)"
                data-testid="execution-intent-decision-reason-input"
              />
              <label className="flex items-center gap-2 text-xs text-slate-300" data-testid="execution-intent-decision-read-ack-label">
                <input
                  type="checkbox"
                  checked={currentReadAck.ack}
                  onChange={(event) => updateReadAckState({ ack: event.target.checked })}
                  data-testid="execution-intent-decision-read-ack-checkbox"
                />
                Okudum (intent bazlı, içerik değişirse sıfırlanır)
              </label>
              <label className="flex items-center gap-2 text-xs text-rose-200" data-testid="execution-intent-decision-high-risk-confirm-label">
                <input
                  type="checkbox"
                  checked={currentReadAck.highRiskConfirm}
                  onChange={(event) => updateReadAckState({ highRiskConfirm: event.target.checked })}
                  data-testid="execution-intent-decision-high-risk-confirm-checkbox"
                />
                High-risk double confirmation
              </label>
              <label className="flex items-center gap-2 text-xs text-amber-200" data-testid="execution-intent-decision-override-label">
                <input
                  type="checkbox"
                  checked={overrideEnabled}
                  onChange={(event) => setOverrideEnabled(event.target.checked)}
                  disabled={!isSuperAdmin}
                  data-testid="execution-intent-decision-override-checkbox"
                />
                Override / force execute (sadece super_admin)
              </label>
            </div>

            <div className="mt-3 flex flex-wrap gap-2" data-testid="execution-intent-decision-actions-row">
              <Button
                className="bg-emerald-500 text-black hover:bg-emerald-400"
                onClick={() => executeDecision("approve")}
                disabled={
                  decisionLoading
                  || decisionReason.trim().length < 3
                  || !currentReadAck.ack
                  || (selectedDetail?.risk_payload?.is_high_risk && !currentReadAck.highRiskConfirm)
                  || (overrideEnabled && !isSuperAdmin)
                }
                data-testid="execution-intent-approve-button"
              >
                Approve + Execute
              </Button>
              <Button
                variant="outline"
                onClick={() => executeDecision("reject")}
                disabled={decisionLoading || decisionReason.trim().length < 3 || !currentReadAck.ack}
                data-testid="execution-intent-reject-button"
              >
                Reject
              </Button>
              <Button
                variant="outline"
                onClick={() => executeDecision("cancel")}
                disabled={decisionLoading || decisionReason.trim().length < 3}
                data-testid="execution-intent-cancel-button"
              >
                Cancel Intent
              </Button>
            </div>
          </article>
        </section>
      )}
    </section>
  );
};