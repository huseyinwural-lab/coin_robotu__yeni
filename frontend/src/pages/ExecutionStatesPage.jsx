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

  const exportIncidentSnapshot = async () => {
    try {
      const body = {
        search: filters.search || null,
        state: filters.state !== "all" ? filters.state : null,
        status: filters.status !== "all" ? filters.status : null,
        source_type: filters.source_type !== "all" ? filters.source_type : null,
        symbol: filters.symbol || null,
        strategy: filters.strategy || null,
        order_id: filters.order_id || null,
        time_from: filters.time_from || null,
        time_to: filters.time_to || null,
      };

      if (exportScopeType === "correlation_id") {
        body.correlation_id = exportScopeValue.trim() || filters.correlation_id || null;
      } else if (exportScopeType === "execution_event_id") {
        body.execution_event_id = exportScopeValue.trim() || selectedEventId || null;
      } else {
        body.time_from = filters.time_from || null;
        body.time_to = filters.time_to || null;
      }

      const response = await apiClient.post("/admin-phase3/incident-snapshots/export", body, { responseType: "blob" });
      const blob = new Blob([response.data], { type: "application/zip" });
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
      toast.error(error?.response?.data?.detail || "Incident snapshot export başarısız");
    }
  };

  const uniqueStates = useMemo(() => {
    const set = new Set(rows.map((row) => row.state).filter(Boolean));
    return ["all", ...Array.from(set)];
  }, [rows]);

  const statePath = detail?.full_state_path?.length ? detail.full_state_path : [];
  const diagramSteps = useMemo(() => {
    const dynamic = statePath.filter((item) => !DEFAULT_STATE_STEPS.includes(item));
    return [...DEFAULT_STATE_STEPS, ...dynamic];
  }, [statePath]);

  return (
    <section className="space-y-4" data-testid="execution-control-states-page">
      <div className="grid gap-3 md:grid-cols-6" data-testid="execution-control-states-filters">
        <div>
          <Label>search</Label>
          <Input value={filters.search} onChange={(e) => updateFilter("search", e.target.value)} placeholder="event/correlation/symbol/order" data-testid="execution-control-states-search-input" />
        </div>
        <div>
          <Label>state</Label>
          <Select value={filters.state || "all"} onValueChange={(v) => updateFilter("state", v)}>
            <SelectTrigger data-testid="execution-control-states-state-select"><SelectValue /></SelectTrigger>
            <SelectContent>{uniqueStates.map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div>
          <Label>status</Label>
          <Select value={filters.status || "all"} onValueChange={(v) => updateFilter("status", v)}>
            <SelectTrigger data-testid="execution-control-states-status-select"><SelectValue /></SelectTrigger>
            <SelectContent>{STATUS_OPTIONS.map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div>
          <Label>source_type</Label>
          <Select value={filters.source_type || "all"} onValueChange={(v) => updateFilter("source_type", v)}>
            <SelectTrigger data-testid="execution-control-states-source-select"><SelectValue /></SelectTrigger>
            <SelectContent>{SOURCE_OPTIONS.map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div>
          <Label>symbol</Label>
          <Input value={filters.symbol} onChange={(e) => updateFilter("symbol", e.target.value)} data-testid="execution-control-states-symbol-input" />
        </div>
        <div>
          <Label>strategy</Label>
          <Input value={filters.strategy} onChange={(e) => updateFilter("strategy", e.target.value)} data-testid="execution-control-states-strategy-input" />
        </div>
        <div>
          <Label>correlation_id</Label>
          <Input value={filters.correlation_id} onChange={(e) => updateFilter("correlation_id", e.target.value)} data-testid="execution-control-states-correlation-input" />
        </div>
        <div>
          <Label>order_id</Label>
          <Input value={filters.order_id} onChange={(e) => updateFilter("order_id", e.target.value)} data-testid="execution-control-states-order-id-input" />
        </div>
        <div>
          <Label>time_from (ISO)</Label>
          <Input value={filters.time_from} onChange={(e) => updateFilter("time_from", e.target.value)} placeholder="2026-03-22T00:00:00+00:00" data-testid="execution-control-states-time-from-input" />
        </div>
        <div>
          <Label>time_to (ISO)</Label>
          <Input value={filters.time_to} onChange={(e) => updateFilter("time_to", e.target.value)} placeholder="2026-03-22T23:59:59+00:00" data-testid="execution-control-states-time-to-input" />
        </div>
        <div>
          <Label>refresh</Label>
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
        <p className="text-sm font-semibold">Incident Snapshot Export (zip)</p>
        <div className="mt-2 grid gap-2 md:grid-cols-3">
          <Select value={exportScopeType} onValueChange={setExportScopeType}>
            <SelectTrigger data-testid="execution-control-incident-export-scope-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="correlation_id">correlation_id</SelectItem>
              <SelectItem value="execution_event_id">execution_event_id</SelectItem>
              <SelectItem value="time_range">time_range</SelectItem>
            </SelectContent>
          </Select>
          <Input value={exportScopeValue} onChange={(e) => setExportScopeValue(e.target.value)} placeholder="scope value" data-testid="execution-control-incident-export-scope-value-input" />
          <Button onClick={exportIncidentSnapshot} data-testid="execution-control-incident-export-button">Incident Snapshot Export</Button>
        </div>
      </div>
    </section>
  );
};
