import { useEffect, useState } from "react";

import { MetricCard } from "@/components/MetricCard";
import { apiClient } from "@/lib/api";

export const UserDashboardPage = () => {
  const [summary, setSummary] = useState(null);
  const [qualityScore, setQualityScore] = useState("-");
  const [portfolio, setPortfolio] = useState(null);
  const [signals, setSignals] = useState([]);

  useEffect(() => {
    const fetchSummary = async () => {
      const { data } = await apiClient.get("/dashboard/summary");
      setSummary(data);

      const [portfolioRes, signalsRes] = await Promise.all([
        apiClient.get("/user/portfolio"),
        apiClient.get("/user/signals", { params: { limit: 50 } }),
      ]);
      setPortfolio(portfolioRes.data);
      setSignals(signalsRes.data || []);

      try {
        const qualityRes = await apiClient.get("/phase4/execution-quality/latest");
        setQualityScore(qualityRes.data.execution_quality_score);
      } catch (_) {
        setQualityScore("-");
      }
    };
    fetchSummary();
  }, []);

  const pendingCount = signals.filter((item) => item.status === "pending").length;

  return (
    <section className="space-y-4" data-testid="user-dashboard-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="user-dashboard-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-dashboard-title">User Dashboard</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-dashboard-description">
          Assisted queue, portföy görünümü ve kişisel risk metrikleri.
        </p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5" data-testid="user-dashboard-metrics-grid">
        <MetricCard label="Bot Sayısı" value={summary?.metrics?.bots ?? "-"} testId="user-metric-bots" />
        <MetricCard label="Aktif Bot" value={summary?.metrics?.running_bots ?? "-"} testId="user-metric-active-bots" />
        <MetricCard label="Risk Policy" value={summary?.metrics?.risk_policies ?? "-"} testId="user-metric-risk-policies" />
        <MetricCard label="Open Positions" value={portfolio?.open_positions_count ?? "-"} tone="orange" testId="user-metric-open-positions" />
        <MetricCard label="Pending Signals" value={pendingCount} tone="orange" testId="user-metric-pending-signals" />
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="user-dashboard-portfolio-summary-grid">
        <MetricCard label="Current Capital" value={portfolio?.current_capital ?? "-"} tone="blue" testId="user-metric-current-capital" />
        <MetricCard label="Available Balance" value={portfolio?.available_balance ?? "-"} tone="orange" testId="user-metric-available-balance" />
        <MetricCard label="Execution Quality" value={qualityScore} tone="orange" testId="user-metric-execution-quality" />
      </div>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-dashboard-heartbeat-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-heartbeat-label">Redis Heartbeat</p>
        <p className="mt-2 font-mono text-sm text-slate-100" data-testid="user-heartbeat-value">{summary?.heartbeat ?? "-"}</p>
      </div>
    </section>
  );
};
