import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { MetricCard } from "@/components/MetricCard";
import { ResponsiveMiniLineChart } from "@/components/ResponsiveMiniLineChart";
import { apiClient } from "@/lib/api";
import { UserReportsPage } from "@/pages/UserReportsPage";

export const UserPortfolioPage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [portfolio, setPortfolio] = useState(null);
  const [performance, setPerformance] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const activeTab = searchParams.get("tab") || "overview";

  useEffect(() => {
    const load = async () => {
      setIsLoading(true);
      const [portfolioRes, performanceRes] = await Promise.all([
        apiClient.get("/user/portfolio"),
        apiClient.get("/user/performance"),
      ]);
      setPortfolio(portfolioRes.data);
      setPerformance(performanceRes.data);
      setIsLoading(false);
    };
    load();
  }, []);

  const chartData = useMemo(
    () => [
      { metric: "Open", value: portfolio?.open_notional ?? 0 },
      { metric: "Avail", value: portfolio?.available_balance ?? 0 },
      { metric: "ClosedPnl", value: portfolio?.closed_pnl ?? 0 },
      { metric: "ROI", value: performance?.roi_pct ?? 0 },
    ],
    [performance, portfolio],
  );

  const hideMockWallet = String(portfolio?.execution_mode || "").toLowerCase() === "mocked";

  if (isLoading) {
    return <LoadingSkeleton rows={5} testId="user-portfolio-loading-skeleton" />;
  }

  return (
    <section className="grid grid-cols-12 gap-4" data-testid="user-portfolio-page">
      <header className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="user-portfolio-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-portfolio-title">Portfolio</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-portfolio-description">
          12 kolon responsive düzen: mobilde taşmadan, desktop’ta yoğun veri görünümü.
        </p>
      </header>

      <div className="col-span-12 grid grid-cols-12 gap-3" data-testid="user-portfolio-summary-grid">
        <div className="col-span-12 grid gap-2" data-testid="user-portfolio-wallet-stack">
          <div data-testid="user-portfolio-total-wallet-balance-card">
            <MetricCard label="Toplam Cüzdan Bakiyesi" value={portfolio?.total_wallet_balance ?? 0} tone="orange" testId="user-portfolio-total-wallet-balance" />
          </div>
          <div data-testid="user-portfolio-spot-wallet-balance-card">
            <MetricCard label="Spot Bakiyesi" value={portfolio?.spot_wallet_balance ?? 0} tone="blue" testId="user-portfolio-spot-wallet-balance" />
          </div>
          <div data-testid="user-portfolio-futures-wallet-balance-card">
            <MetricCard label="Futures Bakiyesi" value={portfolio?.futures_wallet_balance ?? 0} tone="orange" testId="user-portfolio-futures-wallet-balance" />
          </div>
        </div>

        {hideMockWallet && (
          <p className="col-span-12 text-xs text-amber-300" data-testid="user-portfolio-mock-wallet-hidden-note">
            Live cüzdan bağlı değil. Test/paper bakiye metrikleri gizlendi.
          </p>
        )}
        <div className="col-span-12 flex flex-wrap gap-2" data-testid="user-portfolio-tab-group">
          {[
            ["overview", "Overview"],
            ["pnl", "PnL"],
            ["reports", "Reports"],
          ].map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setSearchParams({ tab: value })}
              className={`rounded border px-3 py-2 text-sm ${activeTab === value ? "border-emerald-400 bg-emerald-400/20 text-emerald-200" : "border-slate-700 bg-slate-900 text-slate-300"}`}
              data-testid={`user-portfolio-tab-${value}`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="col-span-6 md:col-span-4 xl:col-span-2"><MetricCard label="Capital" value={hideMockWallet ? "-" : (portfolio?.current_capital ?? "-")} tone="orange" testId="user-portfolio-current-capital" /></div>
        <div className="col-span-6 md:col-span-4 xl:col-span-2"><MetricCard label="Balance" value={hideMockWallet ? "-" : (portfolio?.available_balance ?? "-")} tone="blue" testId="user-portfolio-available-balance" /></div>
        <div className="col-span-6 md:col-span-4 xl:col-span-2"><MetricCard label="Open Notional" value={hideMockWallet ? "-" : (portfolio?.open_notional ?? "-")} tone="orange" testId="user-portfolio-open-notional" /></div>
        <div className="col-span-6 md:col-span-4 xl:col-span-2"><MetricCard label="Open Pos" value={hideMockWallet ? "-" : (portfolio?.open_positions_count ?? "-")} tone="blue" testId="user-portfolio-open-count" /></div>
        <div className="col-span-6 md:col-span-4 xl:col-span-2"><MetricCard label="Closed PnL" value={hideMockWallet ? "-" : (portfolio?.closed_pnl ?? "-")} tone="orange" testId="user-portfolio-closed-pnl" /></div>
        <div className="col-span-6 md:col-span-4 xl:col-span-2"><MetricCard label="Compounding" value={hideMockWallet ? "-" : (portfolio?.compounding_enabled ? "ON" : "OFF")} tone="blue" testId="user-portfolio-compounding" /></div>
      </div>

      {activeTab !== "reports" && <div className="col-span-12 lg:col-span-8" data-testid="user-portfolio-chart-col">
        <ResponsiveMiniLineChart data={chartData} xKey="metric" yKey="value" title="Portfolio Curve" testId="user-portfolio-responsive-chart" />
      </div>}

      {activeTab !== "reports" && <div className="col-span-12 lg:col-span-4 grid grid-cols-12 gap-3" data-testid="user-portfolio-performance-grid">
        <div className="col-span-6 lg:col-span-12"><MetricCard label="Win Rate" value={performance?.win_rate ?? "-"} tone="blue" testId="user-performance-win-rate" /></div>
        <div className="col-span-6 lg:col-span-12"><MetricCard label="ROI %" value={performance?.roi_pct ?? "-"} tone="orange" testId="user-performance-roi" /></div>
        <div className="col-span-6 lg:col-span-12"><MetricCard label="Profit Factor" value={performance?.profit_factor ?? "-"} tone="blue" testId="user-performance-profit-factor" /></div>
        <div className="col-span-6 lg:col-span-12"><MetricCard label="Exec Quality" value={performance?.avg_execution_quality ?? "-"} tone="orange" testId="user-performance-execution-quality" /></div>
      </div>}

      {activeTab === "reports" && (
        <div className="col-span-12" data-testid="user-portfolio-reports-embedded-panel">
          <UserReportsPage embedded />
        </div>
      )}
    </section>
  );
};