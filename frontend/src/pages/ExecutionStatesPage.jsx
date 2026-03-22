import { useEffect, useMemo, useState } from "react";
import { apiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { toast } from "sonner";

const SOURCE_OPTIONS = ["all", "production", "paper", "simulation", "replay"];
const REFRESH_OPTIONS = [5000, 10000, 20000, 30000];

export const ExecutionStatesPage = () => {
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState({});
  const [stateCounters, setStateCounters] = useState({});
  const [selectedEventId, setSelectedEventId] = useState("");
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [sourceType, setSourceType] = useState("all");
  const [stateFilter, setStateFilter] = useState("all");
  const [refreshMs, setRefreshMs] = useState(5000);
  const [simulateResult, setSimulateResult] = useState(null);
  const [batchScenarios, setBatchScenarios] = useState("BTCUSDT,long,filled\nETHUSDT,short,timeout");
  const [manualCorrelationId, setManualCorrelationId] = useState("");
  const [manualReason, setManualReason] = useState("");
  const [manualPhrase, setManualPhrase] = useState("");
  const [manualToState, setManualToState] = useState("cancelled");

  const load = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("limit", "300");
      if (search.trim()) params.set("search", search.trim());
      if (sourceType !== "all") params.set("source_type", sourceType);
      if (stateFilter !== "all") params.set("state", stateFilter);
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
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Event detail alınamadı");
    }
  };

  useEffect(() => {
    load();
    const id = setInterval(load, refreshMs);
    return () => clearInterval(id);
  }, [refreshMs, sourceType, stateFilter]);

  const handleSimulate = async (outcome) => {
    try {
      const { data } = await apiClient.post(
        `/admin-phase3/execution-state-transitions/simulate?strategy_type=breakout&symbol=BTCUSDT&side=long&outcome=${outcome}&source_type=simulation&environment=simulation`
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

  const uniqueStates = useMemo(() => {
    const set = new Set(rows.map((row) => row.state).filter(Boolean));
    return ["all", ...Array.from(set)];
  }, [rows]);

  return (
    <section className="space-y-4" data-testid="execution-control-states-page">
      <div className="flex flex-wrap items-end gap-3" data-testid="execution-control-states-filters">
        <div>
          <Label>Search</Label>
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="event_id / correlation / symbol" data-testid="execution-control-states-search-input" />
        </div>
        <div>
          <Label>Source</Label>
          <Select value={sourceType} onValueChange={setSourceType}>
            <SelectTrigger data-testid="execution-control-states-source-select"><SelectValue /></SelectTrigger>
            <SelectContent>{SOURCE_OPTIONS.map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div>
          <Label>State</Label>
          <Select value={stateFilter} onValueChange={setStateFilter}>
            <SelectTrigger data-testid="execution-control-states-state-select"><SelectValue /></SelectTrigger>
            <SelectContent>{uniqueStates.map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div>
          <Label>Refresh</Label>
          <Select value={String(refreshMs)} onValueChange={(v) => setRefreshMs(Number(v))}>
            <SelectTrigger data-testid="execution-control-states-refresh-select"><SelectValue /></SelectTrigger>
            <SelectContent>{REFRESH_OPTIONS.map((ms) => <SelectItem key={ms} value={String(ms)}>{ms / 1000}s</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <Button onClick={load} data-testid="execution-control-states-refresh-button">Yenile</Button>
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
                <TableCell>{row.source_type}</TableCell>
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
          <p className="text-xs text-slate-400">event_id={selectedEventId}</p>

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
    </section>
  );
};
