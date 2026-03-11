import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { MetricCard } from "@/components/MetricCard";
import { apiClient } from "@/lib/api";

export const MonitoringPage = () => {
  const [metrics, setMetrics] = useState(null);
  const [driftDays, setDriftDays] = useState(7);
  const [drift, setDrift] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchMonitoring = useCallback(async () => {
    try {
      const [{ data: monitoringData }, { data: driftData }] = await Promise.all([
        apiClient.get("/pipeline/monitoring"),
        apiClient.get(`/phase4/admin/permission-drift-trend?days=${driftDays}`),
      ]);
      setMetrics(monitoringData);
      setDrift(driftData);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Monitoring verisi alınamadı");
    } finally {
      setIsLoading(false);
    }
  }, [driftDays]);

  useEffect(() => {
    fetchMonitoring();
    const timer = setInterval(fetchMonitoring, 5000);
    return () => clearInterval(timer);
  }, [fetchMonitoring]);

  const points = drift?.points || [];
  const maxCount = Math.max(...points.map((point) => point.event_count), 1);
  const linePoints = points
    .map((point, index) => {
      const x = (index / Math.max(points.length - 1, 1)) * 100;
      const y = 100 - (point.event_count / maxCount) * 100;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <section className="space-y-4" data-testid="monitoring-page">
      <header className="border border-blue-900 bg-slate-900 p-4" data-testid="monitoring-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-blue-300" data-testid="monitoring-title">Pipeline Monitoring</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="monitoring-description">Websocket, signal rate, paper trade ve latency durumu.</p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-8" data-testid="monitoring-metrics-grid">
        <MetricCard label="WS Status" value={isLoading ? "loading" : (metrics?.websocket_status || "-")} tone="blue" testId="monitoring-ws-status" />
        <MetricCard label="Signal / 5m" value={isLoading ? "loading" : (metrics?.signal_rate_last_5m ?? "-")} testId="monitoring-signal-rate" />
        <MetricCard label="Paper Trade / 5m" value={isLoading ? "loading" : (metrics?.paper_trades_last_5m ?? "-")} tone="orange" testId="monitoring-paper-trades" />
        <MetricCard label="Open Positions" value={isLoading ? "loading" : (metrics?.open_positions ?? "-")} testId="monitoring-open-positions" />
        <MetricCard label="Latency ms" value={isLoading ? "loading" : (metrics?.latency_ms ?? "-")} tone="blue" testId="monitoring-latency" />
        <MetricCard label="Transitions / 5m" value={isLoading ? "loading" : (metrics?.execution_transitions_5m ?? "-")} tone="orange" testId="monitoring-transitions" />
        <MetricCard label="Release Gate" value={isLoading ? "loading" : (metrics?.release_gate_status ?? "-")} tone={metrics?.release_gate_status === "PASS" ? "blue" : metrics?.release_gate_status === "WARNING" ? "orange" : "red"} testId="monitoring-release-gate" />
        <MetricCard label="Gate Checked" value={isLoading ? "loading" : (metrics?.release_gate_last_checked ?? "-")} tone="blue" testId="monitoring-release-gate-checked" />
      </div>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="monitoring-details-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="monitoring-heartbeat-label">Heartbeat</p>
        <p className="mt-2 font-mono text-sm" data-testid="monitoring-heartbeat-value">{metrics?.heartbeat || "-"}</p>
        <p className="mt-2 font-mono text-xs text-slate-400" data-testid="monitoring-queue-depth">Queue Depth: {metrics?.queue_depth ?? "-"}</p>
        <p className="mt-1 font-mono text-xs text-slate-400" data-testid="monitoring-running-bots">Running Bots: {metrics?.active_bots_running ?? "-"}</p>
        <p className="mt-1 font-mono text-xs text-slate-400" data-testid="monitoring-reconnects">WS Reconnect /5m: {metrics?.websocket_reconnects_5m ?? "-"}</p>
        <p className="mt-1 font-mono text-xs text-slate-400" data-testid="monitoring-idempotency">Idempotency Keys /5m: {metrics?.idempotency_keys_5m ?? "-"}</p>
        <p className="mt-1 font-mono text-xs text-slate-400" data-testid="monitoring-duplicates">Duplicate Blocked /5m: {metrics?.duplicate_signals_blocked_5m ?? "-"}</p>
        <p className="mt-1 font-mono text-xs text-slate-400" data-testid="monitoring-correlation-rejections">Correlation Rejections /5m: {metrics?.correlation_rejections_5m ?? "-"}</p>
        <p className="mt-1 font-mono text-xs text-slate-400" data-testid="monitoring-failed-pending">Failed Events Pending: {metrics?.failed_events_pending ?? "-"}</p>
        <p className="mt-1 font-mono text-xs text-slate-400" data-testid="monitoring-failed-dead">Failed Events Dead: {metrics?.failed_events_dead ?? "-"}</p>
      </div>

      <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="monitoring-permission-drift-panel">
        <div className="flex flex-wrap items-center justify-between gap-3" data-testid="monitoring-permission-drift-header">
          <div>
            <p className="text-xs uppercase tracking-widest text-blue-300" data-testid="monitoring-permission-drift-kicker">Exchange Monitoring</p>
            <h3 className="text-lg font-semibold text-slate-100" data-testid="monitoring-permission-drift-title">Permission Drift Trend</h3>
          </div>
          <div className="flex gap-2" data-testid="monitoring-permission-drift-toggle-group">
            <button
              className={`border px-3 py-1 text-xs ${driftDays === 7 ? "border-blue-400 bg-blue-700 text-white" : "border-slate-700 text-slate-300"}`}
              onClick={() => setDriftDays(7)}
              data-testid="monitoring-permission-drift-7d-button"
            >
              7 Gün
            </button>
            <button
              className={`border px-3 py-1 text-xs ${driftDays === 30 ? "border-blue-400 bg-blue-700 text-white" : "border-slate-700 text-slate-300"}`}
              onClick={() => setDriftDays(30)}
              data-testid="monitoring-permission-drift-30d-button"
            >
              30 Gün
            </button>
          </div>
        </div>

        <div className="grid gap-2 sm:grid-cols-3" data-testid="monitoring-permission-drift-summary-grid">
          <MetricCard label="Affected Users" value={drift?.affected_user_count ?? "-"} tone="blue" testId="monitoring-permission-drift-affected-users" />
          <MetricCard label="Critical Drift" value={drift?.critical_drift_count ?? "-"} tone="red" testId="monitoring-permission-drift-critical-count" />
          <MetricCard label="Latest Event" value={drift?.latest_timestamp || "-"} tone="orange" testId="monitoring-permission-drift-latest-timestamp" />
        </div>

        <div className="border border-slate-800 bg-slate-950 p-3" data-testid="monitoring-permission-drift-chart-wrapper">
          <svg viewBox="0 0 100 100" className="h-40 w-full" data-testid="monitoring-permission-drift-line-chart">
            <polyline fill="none" stroke="#60a5fa" strokeWidth="2" points={linePoints || "0,100 100,100"} />
          </svg>
          <div className="mt-2 flex flex-wrap gap-2" data-testid="monitoring-permission-drift-chart-labels">
            {points.slice(-6).map((point) => (
              <span key={point.date} className="rounded border border-slate-700 px-2 py-1 font-mono text-xs text-slate-400" data-testid={`monitoring-permission-drift-point-${point.date}`}>
                {point.date}: {point.event_count}
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};