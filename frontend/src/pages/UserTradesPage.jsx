import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Link } from "react-router-dom";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const UserTradesPage = () => {
  const [trades, setTrades] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [compactMode, setCompactMode] = useState(false);
  const [filters, setFilters] = useState({ symbol: "", status: "all", strategy: "", side: "all", date_range: "7d" });
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [openOrders, setOpenOrders] = useState([]);
  const [pendingOrders, setPendingOrders] = useState([]);

  useEffect(() => {
    const load = async () => {
      setIsLoading(true);
      try {
        const [tradesRes, openRes, pendingRes] = await Promise.all([
          apiClient.get("/user/trades", { params: { limit: 200 } }),
          apiClient.get("/user/trades/open-orders", { params: { limit: 80 } }),
          apiClient.get("/user/trades/pending-orders", { params: { limit: 80 } }),
        ]);
        setTrades(tradesRes.data || []);
        setOpenOrders(openRes.data || []);
        setPendingOrders(pendingRes.data || []);
      } catch (error) {
        toast.error(error?.response?.data?.detail || "Trades yüklenemedi");
      } finally {
        setIsLoading(false);
      }
    };
    load();
  }, []);

  const openTradeDetail = async (trade) => {
    setDetailLoading(true);
    try {
      const { data } = await apiClient.get(`/user/trades/${trade.trade_id}`);
      setDetail(data || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Trade detail yüklenemedi");
    } finally {
      setDetailLoading(false);
    }
  };

  const formatTradeTime = (value) => {
    if (!value) return "-";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return "-";
    return parsed.toLocaleString("tr-TR");
  };

  const filteredTrades = useMemo(
    () =>
      (trades || []).filter((row) => {
        const symbolOk = !filters.symbol || String(row.symbol || "").toUpperCase().includes(filters.symbol.toUpperCase());
        const statusOk = filters.status === "all" || String(row.status || "").toUpperCase() === filters.status.toUpperCase();
        const strategyOk = !filters.strategy || String(row.strategy || "").toLowerCase().includes(filters.strategy.toLowerCase());
        const sideOk = filters.side === "all" || String(row.side || "").toLowerCase() === filters.side;
        return symbolOk && statusOk && strategyOk && sideOk;
      }),
    [filters, trades],
  );

  const pnlBreakdown = useMemo(() => {
    const realized = filteredTrades.reduce((sum, row) => sum + Number(row.realized_pnl || 0), 0);
    const unrealized = filteredTrades.reduce((sum, row) => sum + Number(row.unrealized_pnl || 0), 0);
    const bySymbol = {};
    const byStrategy = {};
    for (const row of filteredTrades) {
      bySymbol[row.symbol] = (bySymbol[row.symbol] || 0) + Number(row.realized_pnl || 0);
      byStrategy[row.strategy || "unknown"] = (byStrategy[row.strategy || "unknown"] || 0) + Number(row.realized_pnl || 0);
    }
    return { realized, unrealized, total: realized + unrealized, bySymbol, byStrategy, tradeCount: filteredTrades.length };
  }, [filteredTrades]);

  if (isLoading) {
    return <LoadingSkeleton rows={6} testId="user-trades-loading-skeleton" />;
  }

  return (
    <section className="grid grid-cols-12 gap-4" data-testid="user-trades-page">
      <header className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="user-trades-header">
        <div className="flex flex-wrap items-center justify-between gap-3" data-testid="user-trades-header-controls">
          <div>
            <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-trades-title">Trades</h2>
            <p className="mt-2 text-sm text-slate-400" data-testid="user-trades-description">Mobilde kart görünümü, desktop’ta compact table modu.</p>
          </div>
          <Button
            type="button"
            variant="outline"
            onClick={() => setCompactMode((previous) => !previous)}
            data-testid="user-trades-compact-mode-toggle"
            aria-label="Compact mode aç/kapat"
          >
            {compactMode ? "Compact: ON" : "Compact: OFF"}
          </Button>
        </div>
      </header>

      <div className="col-span-12 grid gap-3 md:grid-cols-5" data-testid="user-trades-filter-grid">
        <input value={filters.symbol} onChange={(event) => setFilters((prev) => ({ ...prev, symbol: event.target.value }))} placeholder="symbol" className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-trades-filter-symbol-input" />
        <input value={filters.strategy} onChange={(event) => setFilters((prev) => ({ ...prev, strategy: event.target.value }))} placeholder="strategy" className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-trades-filter-strategy-input" />
        <select value={filters.status} onChange={(event) => setFilters((prev) => ({ ...prev, status: event.target.value }))} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-trades-filter-status-select"><option value="all">all status</option><option value="OPEN">OPEN</option><option value="CLOSED">CLOSED</option><option value="PENDING">PENDING</option><option value="CANCELLED">CANCELLED</option><option value="REJECTED">REJECTED</option></select>
        <select value={filters.side} onChange={(event) => setFilters((prev) => ({ ...prev, side: event.target.value }))} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-trades-filter-side-select"><option value="all">all side</option><option value="buy">buy</option><option value="sell">sell</option></select>
        <select value={filters.date_range} onChange={(event) => setFilters((prev) => ({ ...prev, date_range: event.target.value }))} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-trades-filter-date-select"><option value="24h">24h</option><option value="7d">7d</option><option value="30d">30d</option></select>
      </div>

      <div className="col-span-12 rounded border border-slate-800 bg-slate-900 p-4" data-testid="user-trades-pnl-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500">PnL Analysis</p>
        <div className="mt-3 h-48 rounded border border-slate-700 bg-slate-950 p-3 text-sm text-slate-300" data-testid="user-trades-pnl-chart">cumulative pnl: {pnlBreakdown.total.toFixed(4)} | realized={pnlBreakdown.realized.toFixed(4)} | unrealized={pnlBreakdown.unrealized.toFixed(4)}</div>
        <div className="mt-3 grid gap-3 md:grid-cols-6" data-testid="user-trades-pnl-breakdown-grid">
          <div className="border border-slate-700 p-3" data-testid="user-trades-total-pnl-card">total pnl: {pnlBreakdown.total.toFixed(4)}</div>
          <div className="border border-slate-700 p-3" data-testid="user-trades-realized-pnl-card">realized pnl: {pnlBreakdown.realized.toFixed(4)}</div>
          <div className="border border-slate-700 p-3" data-testid="user-trades-trade-count-card">trade count: {pnlBreakdown.tradeCount}</div>
          <div className="border border-slate-700 p-3" data-testid="user-trades-best-symbol-card">best symbol: {Object.entries(pnlBreakdown.bySymbol).sort((a,b)=>b[1]-a[1])[0]?.[0] || '-'}</div>
          <div className="border border-slate-700 p-3" data-testid="user-trades-worst-symbol-card">worst symbol: {Object.entries(pnlBreakdown.bySymbol).sort((a,b)=>a[1]-b[1])[0]?.[0] || '-'}</div>
          <div className="border border-slate-700 p-3" data-testid="user-trades-top-strategy-card">top strategy: {Object.entries(pnlBreakdown.byStrategy).sort((a,b)=>b[1]-a[1])[0]?.[0] || '-'}</div>
        </div>
      </div>

      <div className="col-span-12 grid gap-4 lg:grid-cols-2" data-testid="user-trades-open-pending-grid">
        <article className="border border-slate-800 bg-slate-900 p-4" data-testid="user-trades-open-orders-panel">
          <h3 className="text-base font-semibold">Open Orders</h3>
          <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-xs text-slate-300">{JSON.stringify(openOrders, null, 2)}</pre>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-4" data-testid="user-trades-pending-orders-panel">
          <h3 className="text-base font-semibold">Pending Orders</h3>
          <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-xs text-slate-300">{JSON.stringify(pendingOrders, null, 2)}</pre>
        </article>
      </div>

      <aside className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="user-trades-detail-side-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500">Trade Detail / Replay</p>
        {!detail && <p className="mt-2 text-sm text-slate-400" data-testid="user-trades-detail-empty">Bir trade seçerek lifecycle detayını açın.</p>}
        {detailLoading && <p className="mt-2 text-sm text-slate-300" data-testid="user-trades-detail-loading">Trade detail yükleniyor...</p>}
        {detail && <Link to={`/user/trades/${detail.trade.trade_id}`} className="mt-3 inline-flex underline text-cyan-300" data-testid="user-trades-open-detail-page-link">Open full detail page</Link>}
      </aside>

      <div className="col-span-12 grid gap-3 md:hidden" data-testid="user-trades-mobile-cards" aria-label="Mobil trade kartları">
        {filteredTrades.map((row) => (
          <article key={`${row.source}-${row.trade_id}`} className="rounded border border-slate-800 bg-slate-900 p-3" data-testid={`user-trades-mobile-card-${row.trade_id}`}>
            <p className="text-xs text-slate-500" data-testid={`user-trades-mobile-symbol-${row.trade_id}`}>{row.symbol}</p>
            <p className="text-sm" data-testid={`user-trades-mobile-side-${row.trade_id}`}>{row.side} · {row.status}</p>
            <p className="text-xs text-slate-400" data-testid={`user-trades-mobile-qty-${row.trade_id}`}>Qty: {row.quantity}</p>
            <p className="text-xs text-slate-400" data-testid={`user-trades-mobile-entry-${row.trade_id}`}>Entry: {row.entry_price}</p>
            <p className="text-xs text-slate-400" data-testid={`user-trades-mobile-weight-${row.trade_id}`}>weight: {row.strategy_weight ?? "-"}</p>
            <p className="text-xs text-slate-400" data-testid={`user-trades-mobile-allocation-${row.trade_id}`}>allocation: {row.allocation_source ?? "-"}</p>
            <p className="text-xs text-slate-400" data-testid={`user-trades-mobile-meta-${row.trade_id}`}>meta: {row.meta_engine_decision ?? "-"}</p>
            <p className="text-xs text-slate-400" data-testid={`user-trades-mobile-opened-at-${row.trade_id}`}>Opened: {formatTradeTime(row.opened_at)}</p>
            <p className="text-xs text-slate-400" data-testid={`user-trades-mobile-closed-at-${row.trade_id}`}>Closed: {formatTradeTime(row.closed_at)}</p>
            <div className="mt-2 flex items-center gap-2">
              <span className={`rounded px-2 py-1 text-[11px] ${row.reconciliation_status === 'OK' ? 'bg-emerald-800 text-emerald-200' : row.reconciliation_status === 'PENDING' ? 'bg-amber-800 text-amber-200' : 'bg-rose-800 text-rose-200'}`} data-testid={`user-trades-mobile-reconciliation-${row.trade_id}`}>{row.reconciliation_status}</span>
              <Button variant="outline" onClick={() => openTradeDetail(row)} data-testid={`user-trades-mobile-detail-button-${row.trade_id}`}>Trade Detail</Button>
            </div>
          </article>
        ))}
      </div>

      <div className="col-span-12 hidden overflow-x-auto border border-slate-800 bg-slate-900 md:block" data-testid="user-trades-table-wrapper">
        <table className="min-w-full text-sm" data-testid="user-trades-table" aria-label="Trade tablosu">
          <thead className="bg-slate-800 text-left" data-testid="user-trades-table-head">
            <tr>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="user-trades-head-source">Source</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="user-trades-head-symbol">Symbol</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="user-trades-head-side">Side</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="user-trades-head-status">Status</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="user-trades-head-qty">Qty</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="user-trades-head-entry">Entry</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="user-trades-head-pnl">Realized PnL</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="user-trades-head-weight">Weight</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="user-trades-head-allocation">Allocation</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="user-trades-head-meta">Meta</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="user-trades-head-opened-at">Opened At</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="user-trades-head-closed-at">Closed At</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="user-trades-head-trace">Trace</th>
            </tr>
          </thead>
          <tbody data-testid="user-trades-table-body">
            {filteredTrades.map((row) => (
              <tr key={`${row.source}-${row.trade_id}`} className="border-t border-slate-800" data-testid={`user-trades-table-row-${row.trade_id}`}>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-trades-row-source-${row.trade_id}`}>{row.source}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-trades-row-symbol-${row.trade_id}`}>{row.symbol}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-trades-row-side-${row.trade_id}`}>{row.side}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-trades-row-status-${row.trade_id}`}>{row.status}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-trades-row-quantity-${row.trade_id}`}>{row.quantity}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-trades-row-entry-${row.trade_id}`}>{row.entry_price}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-trades-row-realized-pnl-${row.trade_id}`}>{row.realized_pnl ?? "-"}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-trades-row-weight-${row.trade_id}`}>{row.strategy_weight ?? "-"}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-trades-row-allocation-${row.trade_id}`}>{row.allocation_source ?? "-"}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-trades-row-meta-${row.trade_id}`}>{row.meta_engine_decision ?? "-"}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-trades-row-opened-at-${row.trade_id}`}>{formatTradeTime(row.opened_at)}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-trades-row-closed-at-${row.trade_id}`}>{formatTradeTime(row.closed_at)}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`rounded px-2 py-1 text-[11px] ${row.reconciliation_status === 'OK' ? 'bg-emerald-800 text-emerald-200' : row.reconciliation_status === 'PENDING' ? 'bg-amber-800 text-amber-200' : 'bg-rose-800 text-rose-200'}`} data-testid={`user-trades-reconciliation-badge-${row.trade_id}`}>{row.reconciliation_status}</span>
                    <Button variant="outline" onClick={() => openTradeDetail(row)} data-testid={`user-trades-detail-button-${row.trade_id}`}>Trade Detail</Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
};