import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { MetricCard } from "@/components/MetricCard";
import { apiClient } from "@/lib/api";

export const MonitoringPage = () => {
  const [metrics, setMetrics] = useState(null);

  const fetchMonitoring = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/pipeline/monitoring");
      setMetrics(data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Monitoring verisi alınamadı");
    }
  }, []);

  useEffect(() => {
    fetchMonitoring();
    const timer = setInterval(fetchMonitoring, 5000);
    return () => clearInterval(timer);
  }, [fetchMonitoring]);

  return (
    <section className="space-y-4" data-testid="monitoring-page">
      <header className="border border-blue-900 bg-slate-900 p-4" data-testid="monitoring-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-blue-300" data-testid="monitoring-title">Pipeline Monitoring</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="monitoring-description">Websocket, signal rate, paper trade ve latency durumu.</p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5" data-testid="monitoring-metrics-grid">
        <MetricCard label="WS Status" value={metrics?.websocket_status || "-"} tone="blue" testId="monitoring-ws-status" />
        <MetricCard label="Signal / 5m" value={metrics?.signal_rate_last_5m ?? "-"} testId="monitoring-signal-rate" />
        <MetricCard label="Paper Trade / 5m" value={metrics?.paper_trades_last_5m ?? "-"} tone="orange" testId="monitoring-paper-trades" />
        <MetricCard label="Open Positions" value={metrics?.open_positions ?? "-"} testId="monitoring-open-positions" />
        <MetricCard label="Latency ms" value={metrics?.latency_ms ?? "-"} tone="blue" testId="monitoring-latency" />
      </div>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="monitoring-details-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="monitoring-heartbeat-label">Heartbeat</p>
        <p className="mt-2 font-mono text-sm" data-testid="monitoring-heartbeat-value">{metrics?.heartbeat || "-"}</p>
        <p className="mt-2 font-mono text-xs text-slate-400" data-testid="monitoring-queue-depth">Queue Depth: {metrics?.queue_depth ?? "-"}</p>
        <p className="mt-1 font-mono text-xs text-slate-400" data-testid="monitoring-running-bots">Running Bots: {metrics?.active_bots_running ?? "-"}</p>
      </div>
    </section>
  );
};