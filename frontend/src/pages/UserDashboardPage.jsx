import { useEffect, useState } from "react";

import { MetricCard } from "@/components/MetricCard";
import { apiClient } from "@/lib/api";

export const UserDashboardPage = () => {
  const [summary, setSummary] = useState(null);
  const [qualityScore, setQualityScore] = useState("-");

  useEffect(() => {
    const fetchSummary = async () => {
      const { data } = await apiClient.get("/dashboard/summary");
      setSummary(data);

      try {
        const qualityRes = await apiClient.get("/phase4/execution-quality/latest");
        setQualityScore(qualityRes.data.execution_quality_score);
      } catch (_) {
        setQualityScore("-");
      }
    };
    fetchSummary();
  }, []);

  return (
    <section className="space-y-4" data-testid="user-dashboard-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="user-dashboard-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-dashboard-title">User Dashboard Shell</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-dashboard-description">
          Varsayılan execution modu MOCK. Timeframe 15m ve trend doğrulaması 1h.
        </p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5" data-testid="user-dashboard-metrics-grid">
        <MetricCard label="Bot Sayısı" value={summary?.metrics?.bots ?? "-"} testId="user-metric-bots" />
        <MetricCard label="Aktif Bot" value={summary?.metrics?.running_bots ?? "-"} testId="user-metric-active-bots" />
        <MetricCard label="Risk Policy" value={summary?.metrics?.risk_policies ?? "-"} testId="user-metric-risk-policies" />
        <MetricCard label="Open Positions" value={summary?.metrics?.open_positions ?? "-"} tone="orange" testId="user-metric-templates" />
        <MetricCard label="Execution Quality" value={qualityScore} tone="orange" testId="user-metric-execution-quality" />
      </div>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-dashboard-heartbeat-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-heartbeat-label">Redis Heartbeat</p>
        <p className="mt-2 font-mono text-sm text-slate-100" data-testid="user-heartbeat-value">{summary?.heartbeat ?? "-"}</p>
      </div>
    </section>
  );
};
