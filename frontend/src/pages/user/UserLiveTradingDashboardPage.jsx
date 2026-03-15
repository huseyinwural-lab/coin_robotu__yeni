import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

const WINDOW_OPTIONS = ["1h", "6h", "24h"];

const MetricCard = ({ title, value, testId }) => (
  <article className="rounded border border-slate-700 bg-slate-900 p-3" data-testid={`${testId}-card`}>
    <p className="text-xs uppercase tracking-wider text-slate-400" data-testid={`${testId}-label`}>{title}</p>
    <p className="mt-1 text-lg font-bold text-emerald-300" data-testid={`${testId}-value`}>{value ?? "-"}</p>
  </article>
);

export default function UserLiveTradingDashboardPage() {
  const [windowSize, setWindowSize] = useState("1h");
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState(null);
  const [positions, setPositions] = useState(null);
  const [performance, setPerformance] = useState(null);
  const [risk, setRisk] = useState(null);
  const [execution, setExecution] = useState(null);
  const [strategies, setStrategies] = useState(null);
  const [trades, setTrades] = useState(null);
  const [dailyReport, setDailyReport] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const [
        summaryRes,
        positionsRes,
        performanceRes,
        riskRes,
        executionRes,
        strategiesRes,
        tradesRes,
        dailyRes,
      ] = await Promise.all([
        apiClient.get("/user/live/summary", { params: { window: windowSize } }),
        apiClient.get("/user/live/positions"),
        apiClient.get("/user/live/performance", { params: { window: windowSize } }),
        apiClient.get("/user/live/risk", { params: { window: windowSize } }),
        apiClient.get("/user/live/execution-quality", { params: { window: windowSize } }),
        apiClient.get("/user/live/strategies", { params: { window: windowSize } }),
        apiClient.get("/user/live/trades", { params: { window: windowSize } }),
        apiClient.get("/user/live/daily-report", { params: { window: windowSize } }),
      ]);

      setSummary(summaryRes.data || null);
      setPositions(positionsRes.data || null);
      setPerformance(performanceRes.data || null);
      setRisk(riskRes.data || null);
      setExecution(executionRes.data || null);
      setStrategies(strategiesRes.data || null);
      setTrades(tradesRes.data || null);
      setDailyReport(dailyRes.data || null);
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "User Live Trading verisi alınamadı");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [windowSize]);

  const exportDailyReport = async (format) => {
    try {
      const isCsv = format === "csv";
      const response = await apiClient.get("/user/live/daily-report/export", {
        params: { format, window: windowSize },
        responseType: isCsv ? "blob" : "json",
      });

      const blob = isCsv
        ? new Blob([response.data], { type: "text/csv" })
        : new Blob([JSON.stringify(response.data, null, 2)], { type: "application/json" });

      const blobUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = blobUrl;
      link.download = isCsv
        ? `user_live_daily_report_${dailyReport?.date || "latest"}.csv`
        : `user_live_daily_report_${dailyReport?.date || "latest"}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(blobUrl);
      toast.success(`User daily report ${format.toUpperCase()} hazır`);
    } catch {
      toast.error("User daily report export başarısız");
    }
  };

  const alerts = useMemo(() => summary?.alerts?.items || [], [summary]);

  return (
    <section className="space-y-4" data-testid="user-live-trading-dashboard-page">
      <header className="rounded border border-emerald-700/70 bg-emerald-950/20 p-4" data-testid="user-live-trading-dashboard-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-emerald-300" data-testid="user-live-trading-dashboard-title">
          Live Trading
        </h2>
        <p className="mt-2 text-sm text-slate-300" data-testid="user-live-trading-dashboard-description">
          Yalnızca size ait bot, pozisyon, performans, risk ve işlem kalitesini canlı izleyin.
        </p>
      </header>

      <div className="flex flex-wrap items-end gap-2" data-testid="user-live-trading-dashboard-toolbar">
        <label className="space-y-1" data-testid="user-live-trading-dashboard-window-field">
          <span className="text-xs text-slate-400">Window</span>
          <select
            value={windowSize}
            onChange={(event) => setWindowSize(event.target.value)}
            className="h-10 rounded border border-slate-700 bg-black px-2 text-sm"
            data-testid="user-live-trading-dashboard-window-select"
          >
            {WINDOW_OPTIONS.map((option) => (
              <option key={option} value={option} data-testid={`user-live-trading-dashboard-window-option-${option}`}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <Button type="button" variant="outline" onClick={load} data-testid="user-live-trading-dashboard-refresh-button">
          Yenile
        </Button>
        <Button type="button" variant="outline" onClick={() => exportDailyReport("json")} data-testid="user-live-trading-dashboard-export-json-button">
          Export JSON
        </Button>
        <Button type="button" variant="outline" onClick={() => exportDailyReport("csv")} data-testid="user-live-trading-dashboard-export-csv-button">
          Export CSV
        </Button>
      </div>

      <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6" data-testid="user-live-trading-kpi-grid">
        <MetricCard title="running bots" value={summary?.bots?.running_bots ?? 0} testId="user-live-kpi-running-bots" />
        <MetricCard title="paused bots" value={summary?.bots?.paused_bots ?? 0} testId="user-live-kpi-paused-bots" />
        <MetricCard title="open positions" value={summary?.open_positions?.positions_count ?? 0} testId="user-live-kpi-open-positions" />
        <MetricCard title="pnl today" value={performance?.pnl_today ?? 0} testId="user-live-kpi-pnl-today" />
        <MetricCard title="exposure %" value={risk?.own_portfolio_exposure ?? 0} testId="user-live-kpi-exposure" />
        <MetricCard title="exec quality" value={execution?.own_execution_quality_score ?? 0} testId="user-live-kpi-exec-quality" />
      </div>

      <div className="grid gap-3 lg:grid-cols-2" data-testid="user-live-trading-card-grid">
        <article className="rounded border border-slate-700 bg-slate-900 p-4" data-testid="user-live-bots-card">
          <h3 className="text-base font-semibold" data-testid="user-live-bots-title">Bots</h3>
          <div className="mt-3 grid gap-2 sm:grid-cols-3" data-testid="user-live-bots-metrics">
            <MetricCard title="running" value={summary?.bots?.running_bots ?? 0} testId="user-live-bots-running" />
            <MetricCard title="paused" value={summary?.bots?.paused_bots ?? 0} testId="user-live-bots-paused" />
            <MetricCard title="failed" value={summary?.bots?.failed_bots ?? 0} testId="user-live-bots-failed" />
          </div>
        </article>

        <article className="rounded border border-slate-700 bg-slate-900 p-4" data-testid="user-live-open-positions-card">
          <h3 className="text-base font-semibold" data-testid="user-live-open-positions-title">Open Positions</h3>
          <div className="mt-3 grid gap-2 sm:grid-cols-2" data-testid="user-live-open-positions-metrics">
            <MetricCard title="positions" value={positions?.positions_count ?? 0} testId="user-live-open-positions-count" />
            <MetricCard title="unrealized pnl" value={positions?.total_unrealized_pnl ?? 0} testId="user-live-open-positions-unrealized-pnl" />
          </div>
        </article>

        <article className="rounded border border-slate-700 bg-slate-900 p-4" data-testid="user-live-performance-card">
          <h3 className="text-base font-semibold" data-testid="user-live-performance-title">Performance</h3>
          <div className="mt-3 grid gap-2 sm:grid-cols-2" data-testid="user-live-performance-metrics">
            <MetricCard title="trades today" value={performance?.trades_today ?? 0} testId="user-live-performance-trades" />
            <MetricCard title="win rate" value={performance?.win_rate ?? 0} testId="user-live-performance-win-rate" />
            <MetricCard title="pnl today" value={performance?.pnl_today ?? 0} testId="user-live-performance-pnl" />
            <MetricCard title="avg hold min" value={performance?.avg_hold_time_minutes ?? 0} testId="user-live-performance-hold" />
          </div>
        </article>

        <article className="rounded border border-slate-700 bg-slate-900 p-4" data-testid="user-live-risk-card">
          <h3 className="text-base font-semibold" data-testid="user-live-risk-title">Risk</h3>
          <div className="mt-3 grid gap-2 sm:grid-cols-2" data-testid="user-live-risk-metrics">
            <MetricCard title="risk per trade" value={risk?.risk_per_trade_used ?? 0} testId="user-live-risk-per-trade" />
            <MetricCard title="exposure" value={risk?.own_portfolio_exposure ?? 0} testId="user-live-risk-exposure" />
            <MetricCard title="daily loss" value={risk?.own_daily_loss_pct ?? 0} testId="user-live-risk-daily-loss" />
            <MetricCard title="loss limit" value={risk?.daily_loss_limit_pct ?? 0} testId="user-live-risk-loss-limit" />
          </div>
        </article>

        <article className="rounded border border-slate-700 bg-slate-900 p-4" data-testid="user-live-execution-card">
          <h3 className="text-base font-semibold" data-testid="user-live-execution-title">Execution</h3>
          <div className="mt-3 grid gap-2 sm:grid-cols-2" data-testid="user-live-execution-metrics">
            <MetricCard title="quality score" value={execution?.own_execution_quality_score ?? 0} testId="user-live-execution-quality" />
            <MetricCard title="avg slippage" value={execution?.avg_slippage ?? 0} testId="user-live-execution-slippage" />
            <MetricCard title="avg latency" value={execution?.avg_latency ?? 0} testId="user-live-execution-latency" />
            <MetricCard title="reject rate" value={execution?.reject_rate ?? 0} testId="user-live-execution-reject-rate" />
          </div>
        </article>

        <article className="rounded border border-slate-700 bg-slate-900 p-4" data-testid="user-live-alerts-card">
          <h3 className="text-base font-semibold" data-testid="user-live-alerts-title">Alerts</h3>
          <div className="mt-3 space-y-2" data-testid="user-live-alerts-list">
            {alerts.length === 0 ? (
              <p className="text-sm text-emerald-300" data-testid="user-live-alerts-empty">Aktif uyarı yok</p>
            ) : (
              alerts.map((item, idx) => (
                <div key={`${item.code}-${idx}`} className="rounded border border-amber-700 bg-amber-950/30 p-2" data-testid={`user-live-alert-item-${idx}`}>
                  <p className="text-xs uppercase tracking-wide text-amber-300" data-testid={`user-live-alert-code-${idx}`}>{item.code}</p>
                  <p className="text-sm text-slate-100" data-testid={`user-live-alert-message-${idx}`}>{item.message}</p>
                </div>
              ))
            )}
          </div>
        </article>
      </div>

      <div className="grid gap-3 lg:grid-cols-2" data-testid="user-live-trading-tables-grid">
        <article className="rounded border border-slate-700 bg-slate-900 p-4" data-testid="user-live-strategies-panel">
          <h3 className="text-base font-semibold" data-testid="user-live-strategies-title">Strategies</h3>
          <div className="mt-3 overflow-x-auto" data-testid="user-live-strategies-table-wrapper">
            <table className="min-w-full text-sm" data-testid="user-live-strategies-table">
              <thead>
                <tr className="text-left text-slate-400">
                  <th className="py-1" data-testid="user-live-strategies-header-name">Strategy</th>
                  <th className="py-1" data-testid="user-live-strategies-header-trades">Trades</th>
                  <th className="py-1" data-testid="user-live-strategies-header-win">Win Rate</th>
                  <th className="py-1" data-testid="user-live-strategies-header-return">Avg Return</th>
                  <th className="py-1" data-testid="user-live-strategies-header-quality">Quality</th>
                </tr>
              </thead>
              <tbody>
                {(strategies?.items || []).slice(0, 8).map((row, idx) => (
                  <tr key={`${row.strategy_name}-${idx}`} className="border-t border-slate-800" data-testid={`user-live-strategies-row-${idx}`}>
                    <td data-testid={`user-live-strategies-name-${idx}`}>{row.strategy_name}</td>
                    <td data-testid={`user-live-strategies-trades-${idx}`}>{row.trades}</td>
                    <td data-testid={`user-live-strategies-win-${idx}`}>{row.win_rate}</td>
                    <td data-testid={`user-live-strategies-return-${idx}`}>{row.avg_return}</td>
                    <td data-testid={`user-live-strategies-quality-${idx}`}>{row.quality_score}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <article className="rounded border border-slate-700 bg-slate-900 p-4" data-testid="user-live-trades-panel">
          <h3 className="text-base font-semibold" data-testid="user-live-trades-title">Recent Trades</h3>
          <div className="mt-3 overflow-x-auto" data-testid="user-live-trades-table-wrapper">
            <table className="min-w-full text-sm" data-testid="user-live-trades-table">
              <thead>
                <tr className="text-left text-slate-400">
                  <th className="py-1" data-testid="user-live-trades-header-time">Time</th>
                  <th className="py-1" data-testid="user-live-trades-header-symbol">Symbol</th>
                  <th className="py-1" data-testid="user-live-trades-header-side">Side</th>
                  <th className="py-1" data-testid="user-live-trades-header-size">Size</th>
                  <th className="py-1" data-testid="user-live-trades-header-pnl">PNL</th>
                </tr>
              </thead>
              <tbody>
                {(trades?.items || []).slice(0, 10).map((row, idx) => (
                  <tr key={`${row.trade_id}-${idx}`} className="border-t border-slate-800" data-testid={`user-live-trades-row-${idx}`}>
                    <td data-testid={`user-live-trades-time-${idx}`}>{String(row.timestamp || "-")}</td>
                    <td data-testid={`user-live-trades-symbol-${idx}`}>{row.symbol}</td>
                    <td data-testid={`user-live-trades-side-${idx}`}>{row.side}</td>
                    <td data-testid={`user-live-trades-size-${idx}`}>{row.size}</td>
                    <td data-testid={`user-live-trades-pnl-${idx}`}>{row.pnl}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      </div>

      <article className="rounded border border-slate-700 bg-slate-900 p-4" data-testid="user-live-daily-report-panel">
        <h3 className="text-base font-semibold" data-testid="user-live-daily-report-title">Daily Report Snapshot</h3>
        <pre className="mt-3 overflow-x-auto whitespace-pre-wrap text-xs text-slate-300" data-testid="user-live-daily-report-json">
          {JSON.stringify(dailyReport || {}, null, 2)}
        </pre>
      </article>

      <p className="text-xs text-slate-500" data-testid="user-live-dashboard-loading-state">loading={String(loading)}</p>
    </section>
  );
}