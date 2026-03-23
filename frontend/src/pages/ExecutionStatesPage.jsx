import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { apiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
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
  const backendUrl = String(process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
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
  const [diffSnapshot, setDiffSnapshot] = useState(null);
  const [diffPreviewLoading, setDiffPreviewLoading] = useState(false);

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

  const buildControlParams = () => {
    const params = new URLSearchParams();
    params.set("limit", "500");
    Object.entries(filters).forEach(([key, value]) => {
      if (!value || value === "all") return;
      params.set(key, value);
    });
    return params;
  };

  const load = async () => {
    setLoading(true);
    try {
      const params = buildControlParams();
      const { data } = await apiClient.get(`/admin-phase3/execution-state-transitions/control?${params.toString()}`);
      setRows(data?.rows || []);
      setSummary(data?.summary_counts || {});
      setStateCounters(data?.state_counters || {});
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Execution states yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  const loadDetail = async (eventId) => {
    if (!eventId) return;
    try {
      const { data } = await apiClient.get(`/admin-phase3/execution-state-transitions/${encodeURIComponent(eventId)}/detail`);
      setSelectedEventId(eventId);
      setDetail(data);
      setManualCorrelationId(data?.execution_event?.correlation_id || "");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Event detail alınamadı");
    }
  };

  useEffect(() => {
    load();
  }, [searchParams]);

  useEffect(() => {
    const id = setInterval(load, refreshMs);
    return () => clearInterval(id);
  }, [refreshMs, searchParams]);

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
      toast.error("correlation_id zorunlu");
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
    if (error?.message && String(error.message).startsWith("Export hatası:")) {
      return String(error.message);
    }
    const directDetail = error?.response?.data?.detail;
    if (directDetail) {
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

  const buildSnapshotRequestBody = ({ silent = false } = {}) => {
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
      if (compareScopeType !== exportScopeType) {
        return fail("incompatible_scope: primary ve compare scope type aynı olmalı");
      }
      if (compareScopeType === "correlation_id") {
        if (!compareScopeValue.trim()) return fail("Compare Correlation ID zorunlu");
        body.compare_correlation_id = compareScopeValue.trim();
      } else if (compareScopeType === "execution_event_id") {
        if (!compareScopeValue.trim()) return fail("Compare Execution Event ID zorunlu");
        body.compare_execution_event_id = compareScopeValue.trim();
      } else {
        if (!compareTimeFrom || !compareTimeTo) return fail("Compare Time Range için Time From ve Time To zorunlu");
        body.compare_time_from = compareTimeFrom;
        body.compare_time_to = compareTimeTo;
      }
    }
    return body;
  };

  const loadDiffPreview = async ({ showError = false } = {}) => {
    const body = buildSnapshotRequestBody({ silent: !showError });
    if (!body) {
      setDiffSnapshot(null);
      setExportPreview({ events: 0, failures: 0, transitions: 0 });
      return;
    }

    setDiffPreviewLoading(true);
    try {
      const { data } = await apiClient.post("/admin-phase3/incident-snapshots/diff", body);
      const snapshot = data?.state_snapshot || null;
      setDiffSnapshot(snapshot);
      setExportPreview(snapshot?.preview || { events: 0, failures: 0, transitions: 0 });
    } catch (error) {
      setDiffSnapshot(null);
      if (showError) {
        toast.error(error?.response?.data?.detail || "Diff preview alınamadı");
      }
    } finally {
      setDiffPreviewLoading(false);
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
  }, [
    filters.search,
    filters.state,
    filters.status,
    filters.source_type,
    filters.symbol,
    filters.strategy,
    filters.correlation_id,
    filters.order_id,
    filters.time_from,
    filters.time_to,
    exportScopeType,
    exportScopeValue,
    compareEnabled,
    compareScopeType,
    compareScopeValue,
    compareTimeFrom,
    compareTimeTo,
    selectedEventId,
  ]);

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

  const statePath = detail?.full_state_path?.length ? detail.full_state_path : [];
  const diagramSteps = useMemo(() => {
    const dynamic = statePath.filter((item) => !DEFAULT_STATE_STEPS.includes(item));
    return [...DEFAULT_STATE_STEPS, ...dynamic];
  }, [statePath]);

  const diffData = diffSnapshot?.diff || null;
  const failedPct = Number(diffData?.percentage_change?.failed_events || 0);
  const deadPct = Number(diffData?.percentage_change?.dead_letter || 0);
  const failedDelta = Number(diffData?.counts?.failed_events_delta || 0);
  const deadDelta = Number(diffData?.counts?.dead_letter_delta || 0);
  const manualDelta = Number(diffData?.counts?.manual_actions_delta || 0);

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
            <p className="text-xs text-slate-300">State Diagram (read-only)</p>
            <div className="mt-2 flex flex-wrap gap-1">
              {diagramSteps.map((step) => {
                const active = step === detail.current_state;
                const visited = statePath.includes(step);
                return (
                  <span
                    key={step}
                    className={`rounded border px-2 py-1 text-[11px] ${active ? "border-cyan-400 text-cyan-200" : visited ? "border-emerald-500/60 text-emerald-200" : "border-slate-700 text-slate-400"}`}
                    data-testid={`execution-control-state-diagram-node-${step}`}
                  >
                    {step}
                  </span>
                );
              })}
            </div>
          </div>

          <div className="mt-3 grid gap-2 md:grid-cols-4" data-testid="execution-control-manual-intervention-panel">
            <Input placeholder="correlation_id" value={manualCorrelationId} onChange={(e) => setManualCorrelationId(e.target.value)} data-testid="execution-control-manual-correlation-input" />
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
            : `~ ${exportPreview.events || 0} events, ${exportPreview.failures || 0} failures export edilecek`}
        </p>

        <div className="mt-2 grid gap-2 md:grid-cols-3">
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
          <div>
            <Label>Scope Value</Label>
            <Input
              value={exportScopeValue}
              onChange={(e) => setExportScopeValue(e.target.value)}
              placeholder={exportScopeType === "correlation_id" ? "enter correlation id" : "enter scope value"}
              disabled={exportScopeType === "time_range"}
              data-testid="execution-control-incident-export-scope-value-input"
            />
          </div>
          <div className="flex items-end">
            <Button onClick={exportIncidentSnapshot} data-testid="execution-control-incident-export-button">Export Snapshot ZIP</Button>
          </div>
        </div>

        <div className="mt-3 space-y-2" data-testid="execution-control-incident-compare-panel">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setCompareEnabled((prev) => !prev)}
            data-testid="execution-control-incident-compare-toggle-button"
          >
            Compare Snapshot {compareEnabled ? "ON" : "OFF"}
          </Button>

          {compareEnabled && (
            <div className="grid gap-2 md:grid-cols-3" data-testid="execution-control-incident-compare-fields">
              <div>
                <Label>Compare Scope Type</Label>
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
                    <Label>Compare Time From (ISO)</Label>
                    <Input value={compareTimeFrom} onChange={(e) => setCompareTimeFrom(e.target.value)} placeholder="2026-03-22T00:00:00+00:00" data-testid="execution-control-incident-compare-time-from-input" />
                  </div>
                  <div>
                    <Label>Compare Time To (ISO)</Label>
                    <Input value={compareTimeTo} onChange={(e) => setCompareTimeTo(e.target.value)} placeholder="2026-03-22T23:59:59+00:00" data-testid="execution-control-incident-compare-time-to-input" />
                  </div>
                </>
              ) : (
                <div>
                  <Label>Compare Scope Value</Label>
                  <Input value={compareScopeValue} onChange={(e) => setCompareScopeValue(e.target.value)} placeholder="enter compare scope value" data-testid="execution-control-incident-compare-scope-value-input" />
                </div>
              )}
            </div>
          )}
        </div>

        {compareEnabled && diffData && (
          <div className="mt-3 rounded border border-slate-700 bg-black/30 p-3" data-testid="execution-control-diff-summary-panel">
            <p className="text-sm font-semibold">Diff Summary</p>
            <div className="mt-2 grid gap-2 md:grid-cols-3 text-sm">
              <div className={failedDelta > 0 && failedPct > 50 ? "text-red-400" : failedDelta < 0 ? "text-emerald-400" : "text-slate-300"} data-testid="execution-control-diff-failed-events-summary">
                FAILED EVENTS: {failedDelta >= 0 ? "+" : ""}{failedPct}% {failedDelta > 0 ? "↑" : failedDelta < 0 ? "↓" : "="} {failedDelta > 0 && failedPct > 50 ? "(CRITICAL)" : failedDelta < 0 ? "(IMPROVED)" : ""}
              </div>
              <div className={deadDelta > 0 && deadPct > 30 ? "text-amber-400" : deadDelta < 0 ? "text-emerald-400" : "text-slate-300"} data-testid="execution-control-diff-dead-letter-summary">
                DEAD LETTER: {deadDelta >= 0 ? "+" : ""}{deadPct}% {deadDelta > 0 ? "↑" : deadDelta < 0 ? "↓" : "="}
              </div>
              <div className={manualDelta > 0 ? "text-amber-300" : manualDelta < 0 ? "text-emerald-400" : "text-slate-300"} data-testid="execution-control-diff-manual-actions-summary">
                MANUAL ACTIONS: {manualDelta >= 0 ? "+" : ""}{manualDelta} {manualDelta > 0 ? "↑" : manualDelta < 0 ? "↓" : "="} {manualDelta < 0 ? "(IMPROVED)" : ""}
              </div>
            </div>
            <div className="mt-2 space-y-1 text-xs" data-testid="execution-control-diff-anomaly-notes-list">
              {(diffData?.anomaly_notes || []).map((note, idx) => (
                <p key={`${note}-${idx}`} data-testid={`execution-control-diff-anomaly-note-${idx}`}>{note}</p>
              ))}
              {!diffData?.anomaly_notes?.length && <p>no anomaly note</p>}
            </div>
          </div>
        )}
      </div>
    </section>
  );
};
