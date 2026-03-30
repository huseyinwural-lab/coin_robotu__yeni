import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

const monoBox = "overflow-x-auto bg-slate-50 p-2 text-[11px] text-slate-700";

export const UserExecutionPage = () => {
  const [positions, setPositions] = useState([]);
  const [intents, setIntents] = useState([]);
  const [trades, setTrades] = useState([]);
  const [quality, setQuality] = useState(null);
  const [strategyPerformance, setStrategyPerformance] = useState({ items: [] });
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ symbol: "", status: "all", date_range: "24h" });

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const [positionsRes, intentsRes, tradesRes, qualityRes, strategyPerfRes] = await Promise.all([
          apiClient.get("/user/execution/positions", { params: { include_closed: false } }),
          apiClient.get("/user/execution/intents", { params: { limit: 30 } }),
          apiClient.get("/user/live/trades", { params: { window: filters.date_range, limit: 30 } }),
          apiClient.get("/user/live/execution-quality", { params: { window: filters.date_range } }),
          apiClient.get("/user/live/strategy-performance", { params: { window: filters.date_range } }),
        ]);
        setPositions(positionsRes.data || []);
        setIntents(intentsRes.data || []);
        setTrades(tradesRes.data?.items || []);
        setQuality(qualityRes.data || null);
        setStrategyPerformance(strategyPerfRes.data || { items: [] });
      } catch (error) {
        toast.error(error?.response?.data?.detail || "Execution view yüklenemedi");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [filters.date_range]);

  const filteredTrades = (trades || []).filter((row) => {
    const symbolOk = !filters.symbol || String(row.symbol || "").toUpperCase().includes(filters.symbol.toUpperCase());
    const statusOk = filters.status === "all" || String(row.status || row.final_status || "").toLowerCase() === filters.status;
    return symbolOk && statusOk;
  });

  const executionSummary = {
    slippage_summary: {
      avg: quality?.avg_slippage ?? 0,
      sample_count: quality?.sample_count ?? 0,
    },
    latency_summary: {
      avg: quality?.avg_latency ?? 0,
    },
    fill_rate: quality?.fill_rate ?? 0,
    reject_count: quality?.reject_count ?? 0,
    cancel_count: quality?.cancel_count ?? 0,
    retry_count: quality?.retry_count ?? 0,
    quality_score: quality?.own_execution_quality_score ?? 0,
    preview_vs_actual: quality?.preview_vs_actual || {},
  };

  return (
    <section className="space-y-4" data-testid="user-execution-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="user-execution-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-execution-title">Execution View</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-execution-description">Open positions, pending orders, order history ve execution guard görünürlüğü tek ekranda.</p>
      </header>

      <div className="grid gap-3 md:grid-cols-3" data-testid="user-execution-filter-grid">
        <input value={filters.symbol} onChange={(event) => setFilters((prev) => ({ ...prev, symbol: event.target.value }))} placeholder="symbol" className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-execution-filter-symbol-input" />
        <select value={filters.status} onChange={(event) => setFilters((prev) => ({ ...prev, status: event.target.value }))} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-execution-filter-status-select"><option value="all">all status</option><option value="filled">filled</option><option value="rejected">rejected</option><option value="canceled">canceled</option></select>
        <select value={filters.date_range} onChange={(event) => setFilters((prev) => ({ ...prev, date_range: event.target.value }))} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-execution-filter-date-range-select"><option value="1h">1h</option><option value="6h">6h</option><option value="24h">24h</option></select>
      </div>

      <div className="grid gap-3 md:grid-cols-4" data-testid="user-execution-kpi-grid">
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="user-execution-kpi-open-positions"><p className="text-xs text-slate-400">open positions</p><p className="text-xl font-bold">{positions.length}</p></article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="user-execution-kpi-pending-orders"><p className="text-xs text-slate-400">pending orders</p><p className="text-xl font-bold">{intents.length}</p></article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="user-execution-kpi-trade-history"><p className="text-xs text-slate-400">history rows</p><p className="text-xl font-bold">{trades.length}</p></article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="user-execution-kpi-quality"><p className="text-xs text-slate-400">quality</p><p className="text-xl font-bold">{quality?.own_execution_quality_score ?? 0}</p></article>
      </div>

      <div className="grid gap-4 xl:grid-cols-12" data-testid="user-execution-main-grid">
        <div className="space-y-4 xl:col-span-6">
          <article className="border border-slate-800 bg-slate-900 p-4" data-testid="user-execution-positions-panel">
            <h3 className="text-base font-semibold" data-testid="user-execution-positions-title">Open Positions</h3>
            <div className="mt-3 overflow-x-auto">
              <table className="min-w-full text-sm" data-testid="user-execution-positions-table">
                <thead><tr className="text-left text-slate-400"><th>Symbol</th><th>Size</th><th>Entry</th><th>Current</th><th>UPnL</th><th>Action</th></tr></thead>
                <tbody>
                  {positions.map((row) => (
                    <tr key={row.position_id} className="border-t border-slate-800" data-testid={`user-execution-position-row-${row.position_id}`}>
                      <td>{row.symbol}</td><td>{row.size}</td><td>{row.entry_price}</td><td>{row.current_price}</td><td>{row.unrealized_pnl}</td><td>{row.recommended_action}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>

          <article className="border border-slate-800 bg-slate-900 p-4" data-testid="user-execution-orders-panel">
            <h3 className="text-base font-semibold" data-testid="user-execution-orders-title">Pending Orders / Execution Queue</h3>
            <div className="mt-3 overflow-x-auto">
              <table className="min-w-full text-sm" data-testid="user-execution-orders-table">
                <thead><tr className="text-left text-slate-400"><th>Intent</th><th>Symbol</th><th>Status</th><th>Gate</th><th>Meta</th><th>Risk</th></tr></thead>
                <tbody>
                  {intents.map((row) => (
                    <tr key={row.id} className="border-t border-slate-800" data-testid={`user-execution-order-row-${row.id}`}>
                      <td className="font-mono">{row.intent_type}</td><td>{row.symbol}</td><td>{row.status}</td><td>{row.gate_decision}</td><td>{row.meta_engine_decision}</td><td>{row.risk_score}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        </div>

        <div className="space-y-4 xl:col-span-6">
          <article className="border border-slate-800 bg-slate-900 p-4" data-testid="user-execution-history-panel">
            <h3 className="text-base font-semibold" data-testid="user-execution-history-title">Order History</h3>
            <div className="mt-2 flex flex-wrap gap-2" data-testid="user-execution-history-actions">
              <Button type="button" variant="outline" onClick={() => {
                const blob = new Blob([JSON.stringify(filteredTrades, null, 2)], { type: 'application/json' });
                const url = window.URL.createObjectURL(blob); const link=document.createElement('a'); link.href=url; link.download='trade-history.json'; link.click(); window.URL.revokeObjectURL(url);
              }} data-testid="user-execution-export-json-button">Export JSON</Button>
              <Button type="button" variant="outline" onClick={() => {
                const lines=['time,symbol,side,size,pnl']; filteredTrades.forEach((row) => lines.push(`${row.timestamp || ''},${row.symbol || ''},${row.side || ''},${row.size || ''},${row.pnl || ''}`));
                const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
                const url = window.URL.createObjectURL(blob); const link=document.createElement('a'); link.href=url; link.download='trade-history.csv'; link.click(); window.URL.revokeObjectURL(url);
              }} data-testid="user-execution-export-csv-button">Export CSV</Button>
            </div>
            <div className="mt-3 overflow-x-auto">
              <table className="min-w-full text-sm" data-testid="user-execution-history-table">
                <thead><tr className="text-left text-slate-400"><th>Time</th><th>Symbol</th><th>Side</th><th>Size</th><th>PNL</th></tr></thead>
                <tbody>
                  {filteredTrades.map((row, idx) => (
                    <tr key={`${row.trade_id}-${idx}`} className="border-t border-slate-800" data-testid={`user-execution-history-row-${idx}`}>
                      <td>{String(row.timestamp || "-")}</td><td>{row.symbol}</td><td>{row.side}</td><td>{row.size}</td><td>{row.pnl}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>

          <article className="border border-slate-800 bg-slate-900 p-4" data-testid="user-execution-quality-panel">
            <h3 className="text-base font-semibold" data-testid="user-execution-quality-title">Execution Status</h3>
            <div className="mt-3 grid gap-3 md:grid-cols-2" data-testid="user-execution-quality-summary-grid">
              <div className="border border-slate-700 p-3 text-sm" data-testid="user-execution-slippage-summary-card">slippage avg: {executionSummary.slippage_summary.avg}</div>
              <div className="border border-slate-700 p-3 text-sm" data-testid="user-execution-latency-summary-card">latency avg: {executionSummary.latency_summary.avg}</div>
              <div className="border border-slate-700 p-3 text-sm" data-testid="user-execution-fill-rate-card">fill rate: {executionSummary.fill_rate}</div>
              <div className="border border-slate-700 p-3 text-sm" data-testid="user-execution-quality-score-card">quality score: {executionSummary.quality_score}</div>
              <div className="border border-slate-700 p-3 text-sm" data-testid="user-execution-reject-count-card">reject count: {executionSummary.reject_count}</div>
              <div className="border border-slate-700 p-3 text-sm" data-testid="user-execution-cancel-count-card">cancel count: {executionSummary.cancel_count}</div>
              <div className="border border-slate-700 p-3 text-sm" data-testid="user-execution-retry-count-card">retry count: {executionSummary.retry_count}</div>
              <div className="border border-slate-700 p-3 text-sm" data-testid="user-execution-preview-vs-actual-card">preview vs actual: {JSON.stringify(executionSummary.preview_vs_actual)}</div>
            </div>
            <pre className={`${monoBox} mt-3`} data-testid="user-execution-quality-json">{JSON.stringify(quality || {}, null, 2)}</pre>
          </article>

          <article className="border border-slate-800 bg-slate-900 p-4" data-testid="user-execution-strategy-parity-panel">
            <h3 className="text-base font-semibold" data-testid="user-execution-strategy-parity-title">Backtest ↔ Live Strategy Parity</h3>
            <pre className={`${monoBox} mt-3`} data-testid="user-execution-strategy-parity-json">{JSON.stringify((strategyPerformance?.items || []).slice(0, 8), null, 2)}</pre>
          </article>
        </div>
      </div>

      {loading && <p className="text-xs text-slate-500" data-testid="user-execution-loading-state">loading...</p>}
    </section>
  );
};
