import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { MetricCard } from "@/components/MetricCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

export const ExecutionStatesPage = () => {
  const [summary, setSummary] = useState(null);
  const [transitions, setTransitions] = useState([]);
  const [retryBudget, setRetryBudget] = useState(2);

  const loadData = useCallback(async () => {
    try {
      const [{ data: summaryData }, { data: transitionData }] = await Promise.all([
        apiClient.get("/admin-phase3/hardening-summary"),
        apiClient.get("/admin-phase3/execution-state-transitions"),
      ]);
      setSummary(summaryData);
      setTransitions(transitionData);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Execution state verisi alınamadı");
    }
  }, []);

  useEffect(() => {
    loadData();
    const timer = setInterval(loadData, 5000);
    return () => clearInterval(timer);
  }, [loadData]);

  const simulateStateFlow = async (outcome = "filled") => {
    try {
      await apiClient.post(
        `/admin-phase3/execution-state-transitions/simulate?strategy_type=breakout&symbol=BTCUSDT&side=long&outcome=${outcome}&retry_budget=${retryBudget}`,
      );
      toast.success(`Execution state simülasyonu üretildi: ${outcome}`);
      loadData();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "State simülasyonu başarısız");
    }
  };

  return (
    <section className="space-y-4" data-testid="execution-states-page">
      <header className="border border-blue-900 bg-slate-900 p-4" data-testid="execution-states-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-blue-300" data-testid="execution-states-title">Execution State Machine</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="execution-states-description">State geçiş zinciri ve hardening çekirdek metrikleri.</p>
        <div className="mt-3 flex flex-wrap gap-2" data-testid="execution-states-simulate-group">
          <Input
            type="number"
            min={0}
            max={5}
            value={retryBudget}
            onChange={(event) => setRetryBudget(event.target.value)}
            className="w-28"
            data-testid="execution-states-retry-budget-input"
          />
          <Button className="bg-blue-600 text-white hover:bg-blue-700" onClick={() => simulateStateFlow("filled")} data-testid="execution-states-simulate-filled-button">
            Simulate Filled
          </Button>
          <Button className="bg-emerald-600 text-white hover:bg-emerald-700" onClick={() => simulateStateFlow("partial")} data-testid="execution-states-simulate-partial-button">
            Simulate Partial
          </Button>
          <Button className="bg-orange-500 text-black hover:bg-orange-600" onClick={() => simulateStateFlow("timeout")} data-testid="execution-states-simulate-timeout-button">
            Simulate Timeout
          </Button>
          <Button className="bg-red-600 text-white hover:bg-red-700" onClick={() => simulateStateFlow("rejected")} data-testid="execution-states-simulate-rejected-button">
            Simulate Rejected
          </Button>
          <Button className="bg-zinc-800 text-white hover:bg-zinc-700" onClick={() => simulateStateFlow("failed")} data-testid="execution-states-simulate-failed-button">
            Simulate Failed
          </Button>
        </div>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" data-testid="execution-states-metrics-grid">
        <MetricCard label="Idempotency /5m" value={summary?.idempotency_keys_5m ?? "-"} tone="blue" testId="execution-states-idempotency" />
        <MetricCard label="Duplicate Blocked /5m" value={summary?.duplicate_signals_blocked_5m ?? "-"} tone="orange" testId="execution-states-duplicates" />
        <MetricCard label="Transitions /5m" value={summary?.execution_transitions_5m ?? "-"} tone="blue" testId="execution-states-transitions" />
        <MetricCard label="Failed Pending" value={summary?.failed_events_pending ?? "-"} tone="red" testId="execution-states-failed" />
      </div>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="execution-states-rebuild-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="execution-states-rebuild-label">Last Rebuild</p>
        <p className="mt-2 font-mono text-sm" data-testid="execution-states-rebuild-status">Status: {summary?.last_state_rebuild_status ?? "-"}</p>
        <p className="mt-1 font-mono text-xs" data-testid="execution-states-rebuild-time">At: {summary?.last_state_rebuild_at ? new Date(summary.last_state_rebuild_at).toLocaleString() : "-"}</p>
      </div>

      <div className="border border-slate-800 bg-slate-900" data-testid="execution-states-table-wrapper">
        <Table data-testid="execution-states-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="state-table-head-event">Execution Event</TableHead>
              <TableHead data-testid="state-table-head-sequence">Seq</TableHead>
              <TableHead data-testid="state-table-head-state">State</TableHead>
              <TableHead data-testid="state-table-head-details">Details</TableHead>
              <TableHead data-testid="state-table-head-time">Time</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {transitions.map((item) => (
              <TableRow key={item.id} data-testid={`state-row-${item.id}`}>
                <TableCell className="font-mono text-xs" data-testid={`state-event-${item.id}`}>{item.execution_event_id}</TableCell>
                <TableCell data-testid={`state-sequence-${item.id}`}>{item.sequence}</TableCell>
                <TableCell data-testid={`state-value-${item.id}`}>{item.state}</TableCell>
                <TableCell className="max-w-sm truncate text-xs" data-testid={`state-details-${item.id}`}>{JSON.stringify(item.details)}</TableCell>
                <TableCell className="font-mono text-xs" data-testid={`state-time-${item.id}`}>{new Date(item.occurred_at).toLocaleString()}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </section>
  );
};
