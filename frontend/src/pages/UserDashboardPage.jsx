import { useEffect, useMemo, useState } from "react";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { MetricCard } from "@/components/MetricCard";
import { ResponsiveMiniLineChart } from "@/components/ResponsiveMiniLineChart";
import { apiClient } from "@/lib/api";

export const UserDashboardPage = () => {
  const [dashboard, setDashboard] = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  const [performance, setPerformance] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      setIsLoading(true);
      const [dashboardRes, portfolioRes, performanceRes] = await Promise.all([
        apiClient.get("/user/dashboard"),
        apiClient.get("/user/portfolio"),
        apiClient.get("/user/performance"),
      ]);
      setDashboard(dashboardRes.data);
      setPortfolio(portfolioRes.data);
      setPerformance(performanceRes.data);
      setIsLoading(false);
    };
    load();
  }, []);

  const chartData = useMemo(
    () => [
      { metric: "Capital", value: dashboard?.current_capital ?? 0 },
      { metric: "Balance", value: dashboard?.available_balance ?? 0 },
      { metric: "PnL", value: portfolio?.closed_pnl ?? 0 },
      { metric: "Win", value: performance?.win_rate ?? 0 },
    ],
    [dashboard, performance, portfolio],
  );

  if (isLoading) {
    return <LoadingSkeleton rows={6} testId="user-dashboard-loading-skeleton" />;
  }

  return (
    <section className="grid grid-cols-12 gap-4" data-testid="user-dashboard-page">
      <header className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="user-dashboard-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-dashboard-title">User Dashboard</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-dashboard-description">
          Responsive ve erişilebilir özet görünümü. Assisted kuyruk, portföy ve performans tek ekranda.
        </p>
      </header>

      <div className="col-span-12 grid grid-cols-12 gap-3" data-testid="user-dashboard-metrics-grid" aria-label="Dashboard metrikleri">
        <div className="col-span-6 md:col-span-4 xl:col-span-2"><MetricCard label="Bot" value={dashboard?.bot_count ?? "-"} testId="user-dashboard-metric-bot-count" /></div>
        <div className="col-span-6 md:col-span-4 xl:col-span-2"><MetricCard label="Running" value={dashboard?.running_bot_count ?? "-"} testId="user-dashboard-metric-running-bot-count" /></div>
        <div className="col-span-6 md:col-span-4 xl:col-span-2"><MetricCard label="Risk Policy" value={dashboard?.risk_policy_count ?? "-"} testId="user-dashboard-metric-risk-policy-count" /></div>
        <div className="col-span-6 md:col-span-4 xl:col-span-2"><MetricCard label="Open Positions" value={dashboard?.open_positions_count ?? "-"} tone="orange" testId="user-dashboard-metric-open-positions" /></div>
        <div className="col-span-6 md:col-span-4 xl:col-span-2"><MetricCard label="Pending" value={dashboard?.pending_signals_count ?? "-"} tone="orange" testId="user-dashboard-metric-pending-signals" /></div>
        <div className="col-span-6 md:col-span-4 xl:col-span-2"><MetricCard label="Heartbeat" value={dashboard?.heartbeat ?? "-"} tone="blue" testId="user-dashboard-metric-heartbeat" /></div>
      </div>

      <div className="col-span-12 lg:col-span-8" data-testid="user-dashboard-chart-col">
        <ResponsiveMiniLineChart
          data={chartData}
          xKey="metric"
          yKey="value"
          title="Dashboard Snapshot"
          testId="user-dashboard-responsive-chart"
        />
      </div>

      <div className="col-span-12 lg:col-span-4 rounded border border-slate-800 bg-slate-900 p-4" data-testid="user-dashboard-summary-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-dashboard-summary-title">Quick Summary</p>
        <p className="mt-2 text-sm" data-testid="user-dashboard-current-capital">Current Capital: {dashboard?.current_capital ?? "-"}</p>
        <p className="mt-1 text-sm" data-testid="user-dashboard-available-balance">Available Balance: {dashboard?.available_balance ?? "-"}</p>
        <p className="mt-1 text-sm" data-testid="user-dashboard-closed-pnl">Closed PnL: {portfolio?.closed_pnl ?? "-"}</p>
        <p className="mt-1 text-sm" data-testid="user-dashboard-win-rate">Win Rate: {performance?.win_rate ?? "-"}</p>
      </div>
    </section>
  );
};