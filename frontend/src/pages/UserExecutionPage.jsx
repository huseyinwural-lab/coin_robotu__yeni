import { useEffect, useState } from "react";
import { toast } from "sonner";

import { apiClient } from "@/lib/api";

const monoBox = "overflow-x-auto bg-slate-50 p-2 text-[11px] text-slate-700";

export const UserExecutionPage = () => {
  const [positions, setPositions] = useState([]);
  const [intents, setIntents] = useState([]);
  const [trades, setTrades] = useState([]);
  const [quality, setQuality] = useState(null);
  const [strategyPerformance, setStrategyPerformance] = useState({ items: [] });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const [positionsRes, intentsRes, tradesRes, qualityRes, strategyPerfRes] = await Promise.all([
          apiClient.get("/user/execution/positions", { params: { include_closed: false } }),
          apiClient.get("/user/execution/intents", { params: { limit: 30 } }),
          apiClient.get("/user/live/trades", { params: { window: "24h", limit: 30 } }),
          apiClient.get("/user/live/execution-quality", { params: { window: "24h" } }),
          apiClient.get("/user/live/strategy-performance", { params: { window: "24h" } }),
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
  }, []);

  return (
    <section className="space-y-4" data-testid="user-execution-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="user-execution-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-execution-title">Execution View</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-execution-description">Open positions, pending orders, order history ve execution guard görünürlüğü tek ekranda.</p>
      </header>

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
            <div className="mt-3 overflow-x-auto">
              <table className="min-w-full text-sm" data-testid="user-execution-history-table">
                <thead><tr className="text-left text-slate-400"><th>Time</th><th>Symbol</th><th>Side</th><th>Size</th><th>PNL</th></tr></thead>
                <tbody>
                  {trades.map((row, idx) => (
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
