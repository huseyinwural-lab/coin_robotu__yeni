import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { MetricCard } from "@/components/MetricCard";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

export const HardeningChecklistPage = () => {
  const [checklist, setChecklist] = useState(null);
  const [trend, setTrend] = useState(null);

  const loadLatest = useCallback(async () => {
    try {
      const [latestRes, trendRes] = await Promise.all([
        apiClient.get("/admin-phase3/hardening-checklist/latest"),
        apiClient.get("/admin-phase3/hardening-checklist/trend"),
      ]);
      setChecklist(latestRes.data);
      setTrend(trendRes.data);
    } catch (error) {
      if (error?.response?.status !== 404) {
        toast.error(error?.response?.data?.detail || "Checklist verisi alınamadı");
      }
    }
  }, []);

  useEffect(() => {
    loadLatest();
  }, [loadLatest]);

  const runChecklist = async () => {
    try {
      await apiClient.post("/admin-phase3/hardening-checklist/run");
      await loadLatest();
      toast.success("Hardening checklist çalıştırıldı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Checklist çalıştırılamadı");
    }
  };

  return (
    <section className="space-y-4" data-testid="hardening-checklist-page">
      <header className="border border-blue-900 bg-slate-900 p-4" data-testid="hardening-checklist-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-blue-300" data-testid="hardening-checklist-title">Hardening Checklist</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="hardening-checklist-description">
          Kritik kapı mantığı aktif: kritik kontrollerden biri fail ise skor 60 altına kilitlenir.
        </p>
        <Button className="mt-3 bg-blue-600 text-white hover:bg-blue-700" onClick={runChecklist} data-testid="hardening-checklist-run-button">
          Checklist Çalıştır
        </Button>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" data-testid="hardening-checklist-metrics-grid">
        <MetricCard label="Score" value={checklist?.score ?? "-"} tone="blue" testId="hardening-metric-score" />
        <MetricCard label="Readiness" value={checklist?.readiness_status ?? "-"} tone={checklist?.readiness_status === "ready" ? "blue" : "red"} testId="hardening-metric-readiness" />
        <MetricCard label="Critical Blocked" value={String(checklist?.critical_blocked ?? "-")} tone="red" testId="hardening-metric-critical-blocked" />
        <MetricCard label="Last Run" value={checklist?.created_at ? new Date(checklist.created_at).toLocaleString() : "-"} tone="orange" testId="hardening-metric-last-run" />
      </div>

      <div className="grid gap-3 md:grid-cols-3" data-testid="hardening-checklist-trend-grid">
        <MetricCard label="Avg Score (Last 5)" value={trend?.average_score_last_5 ?? "-"} tone="blue" testId="hardening-trend-avg-score" />
        <MetricCard label="Critical Alarm" value={String(trend?.critical_alarm ?? false)} tone={trend?.critical_alarm ? "red" : "blue"} testId="hardening-trend-critical" />
        <MetricCard label="Trend Alarm" value={String(trend?.trend_alarm ?? false)} tone={trend?.trend_alarm ? "red" : "blue"} testId="hardening-trend-score" />
      </div>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="hardening-alerts-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="hardening-alerts-label">Active Alerts</p>
        <div className="mt-2 flex flex-wrap gap-2" data-testid="hardening-alerts-list">
          {(trend?.active_alerts || []).length ? (
            trend.active_alerts.map((alert) => (
              <span key={alert} className="border border-red-500 px-2 py-1 text-xs text-red-300" data-testid={`hardening-alert-${alert}`}>
                {alert}
              </span>
            ))
          ) : (
            <span className="text-xs text-slate-500" data-testid="hardening-alert-none">No active alert</span>
          )}
        </div>
      </div>

      <div className="border border-slate-800 bg-slate-900" data-testid="hardening-trend-table-wrapper">
        <Table data-testid="hardening-trend-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="hardening-trend-head-time">Run Time</TableHead>
              <TableHead data-testid="hardening-trend-head-score">Score</TableHead>
              <TableHead data-testid="hardening-trend-head-critical">Critical</TableHead>
              <TableHead data-testid="hardening-trend-head-readiness">Readiness</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(trend?.recent_runs || []).map((run) => (
              <TableRow key={run.id} data-testid={`hardening-trend-row-${run.id}`}>
                <TableCell className="font-mono text-xs" data-testid={`hardening-trend-time-${run.id}`}>{new Date(run.created_at).toLocaleString()}</TableCell>
                <TableCell data-testid={`hardening-trend-score-${run.id}`}>{run.score}</TableCell>
                <TableCell data-testid={`hardening-trend-critical-${run.id}`}>{String(run.critical_blocked)}</TableCell>
                <TableCell data-testid={`hardening-trend-readiness-${run.id}`}>{run.readiness_status}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="border border-slate-800 bg-slate-900" data-testid="hardening-checklist-table-wrapper">
        <Table data-testid="hardening-checklist-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="hardening-head-label">Kontrol</TableHead>
              <TableHead data-testid="hardening-head-critical">Critical</TableHead>
              <TableHead data-testid="hardening-head-status">Status</TableHead>
              <TableHead data-testid="hardening-head-value">Value</TableHead>
              <TableHead data-testid="hardening-head-threshold">Threshold</TableHead>
              <TableHead data-testid="hardening-head-note">Note</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(checklist?.checklist_items || []).map((item) => (
              <TableRow key={item.key} data-testid={`hardening-row-${item.key}`}>
                <TableCell data-testid={`hardening-label-${item.key}`}>{item.label}</TableCell>
                <TableCell data-testid={`hardening-critical-${item.key}`}>{String(item.critical)}</TableCell>
                <TableCell data-testid={`hardening-status-${item.key}`}>{item.status}</TableCell>
                <TableCell className="max-w-xs truncate font-mono text-xs" data-testid={`hardening-value-${item.key}`}>{JSON.stringify(item.value)}</TableCell>
                <TableCell data-testid={`hardening-threshold-${item.key}`}>{item.threshold}</TableCell>
                <TableCell className="max-w-xs truncate text-xs" data-testid={`hardening-note-${item.key}`}>{item.note}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </section>
  );
};
