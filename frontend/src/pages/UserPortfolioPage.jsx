import { useEffect, useState } from "react";

import { MetricCard } from "@/components/MetricCard";
import { apiClient } from "@/lib/api";

export const UserPortfolioPage = () => {
  const [portfolio, setPortfolio] = useState(null);
  const [performance, setPerformance] = useState(null);

  useEffect(() => {
    const load = async () => {
      const [portfolioRes, performanceRes] = await Promise.all([
        apiClient.get("/user/portfolio"),
        apiClient.get("/user/performance"),
      ]);
      setPortfolio(portfolioRes.data);
      setPerformance(performanceRes.data);
    };
    load();
  }, []);

  return (
    <section className="space-y-4" data-testid="user-portfolio-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="user-portfolio-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-portfolio-title">Portfolio</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-portfolio-description">
          Güncel ana para, açık notional ve performans metriklerini kullanıcı scope’unda izleyin.
        </p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5" data-testid="user-portfolio-summary-grid">
        <MetricCard label="Current Capital" value={portfolio?.current_capital ?? "-"} tone="orange" testId="user-portfolio-current-capital" />
        <MetricCard label="Available Balance" value={portfolio?.available_balance ?? "-"} tone="blue" testId="user-portfolio-available-balance" />
        <MetricCard label="Open Notional" value={portfolio?.open_notional ?? "-"} tone="orange" testId="user-portfolio-open-notional" />
        <MetricCard label="Open Positions" value={portfolio?.open_positions_count ?? "-"} tone="blue" testId="user-portfolio-open-count" />
        <MetricCard label="Closed PnL" value={portfolio?.closed_pnl ?? "-"} tone="orange" testId="user-portfolio-closed-pnl" />
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" data-testid="user-portfolio-performance-grid">
        <MetricCard label="Win Rate" value={performance?.win_rate ?? "-"} tone="blue" testId="user-performance-win-rate" />
        <MetricCard label="ROI %" value={performance?.roi_pct ?? "-"} tone="orange" testId="user-performance-roi" />
        <MetricCard label="Profit Factor" value={performance?.profit_factor ?? "-"} tone="blue" testId="user-performance-profit-factor" />
        <MetricCard label="Execution Quality" value={performance?.avg_execution_quality ?? "-"} tone="orange" testId="user-performance-execution-quality" />
      </div>
    </section>
  );
};