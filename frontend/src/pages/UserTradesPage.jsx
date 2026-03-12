import { useEffect, useState } from "react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const UserTradesPage = () => {
  const [trades, setTrades] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [compactMode, setCompactMode] = useState(false);
  const [selectedTradeId, setSelectedTradeId] = useState("");
  const [tradeTrace, setTradeTrace] = useState(null);
  const [traceLoading, setTraceLoading] = useState(false);

  useEffect(() => {
    const load = async () => {
      setIsLoading(true);
      const { data } = await apiClient.get("/user/trades", { params: { limit: 120 } });
      setTrades(data || []);
      setIsLoading(false);
    };
    load();
  }, []);

  const openTradeTrace = async (trade) => {
    setSelectedTradeId(trade.trade_id);
    setTraceLoading(true);
    try {
      const { data } = await apiClient.get(`/user/trades/${trade.trade_id}/decision-trace`);
      setTradeTrace(data || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Trade decision trace yüklenemedi");
    } finally {
      setTraceLoading(false);
    }
  };

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

      <aside className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="user-trades-trace-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-trades-trace-panel-title">Decision Trace</p>
        {!selectedTradeId && <p className="mt-2 text-sm text-slate-400" data-testid="user-trades-trace-empty">Bir trade seçerek trace detayını açın.</p>}
        {Boolean(selectedTradeId && traceLoading) && <p className="mt-2 text-sm text-slate-300" data-testid="user-trades-trace-loading">Trace yükleniyor...</p>}
        {Boolean(selectedTradeId && tradeTrace?.latest_trace) && (
          <div className="mt-3 grid gap-2" data-testid="user-trades-trace-content">
            <p className="text-xs text-slate-500" data-testid="user-trades-trace-status">Decision: {tradeTrace.latest_trace.decision_status}</p>
            <p className="text-xs text-slate-500" data-testid="user-trades-trace-type">Type: {tradeTrace.latest_trace.trace_type}</p>
            <p className="text-xs text-slate-500" data-testid="user-trades-trace-meta-decision">Meta: {tradeTrace.latest_trace.meta_engine_decision || "-"}</p>
            <p className="text-xs text-slate-500" data-testid="user-trades-trace-allocation-reason">Allocation Reason: {tradeTrace.latest_trace.strategy_allocation_reason || "-"}</p>
            <div className="space-y-2" data-testid="user-trades-trace-reason-list">
              {(tradeTrace.latest_trace.reason_details || []).map((reason) => (
                <article key={reason.code} className="border border-slate-800 p-2" data-testid={`user-trades-trace-reason-${reason.code}`}>
                  <p className="text-sm" data-testid={`user-trades-trace-reason-title-${reason.code}`}>{reason.title}</p>
                  <p className="text-xs text-slate-400" data-testid={`user-trades-trace-reason-desc-${reason.code}`}>{reason.description}</p>
                </article>
              ))}
            </div>
          </div>
        )}
      </aside>

      <div className="col-span-12 grid gap-3 md:hidden" data-testid="user-trades-mobile-cards" aria-label="Mobil trade kartları">
        {trades.map((row) => (
          <article key={`${row.source}-${row.trade_id}`} className="rounded border border-slate-800 bg-slate-900 p-3" data-testid={`user-trades-mobile-card-${row.trade_id}`}>
            <p className="text-xs text-slate-500" data-testid={`user-trades-mobile-symbol-${row.trade_id}`}>{row.symbol}</p>
            <p className="text-sm" data-testid={`user-trades-mobile-side-${row.trade_id}`}>{row.side} · {row.status}</p>
            <p className="text-xs text-slate-400" data-testid={`user-trades-mobile-qty-${row.trade_id}`}>Qty: {row.quantity}</p>
            <p className="text-xs text-slate-400" data-testid={`user-trades-mobile-entry-${row.trade_id}`}>Entry: {row.entry_price}</p>
            <p className="text-xs text-slate-400" data-testid={`user-trades-mobile-weight-${row.trade_id}`}>weight: {row.strategy_weight ?? "-"}</p>
            <p className="text-xs text-slate-400" data-testid={`user-trades-mobile-allocation-${row.trade_id}`}>allocation: {row.allocation_source ?? "-"}</p>
            <p className="text-xs text-slate-400" data-testid={`user-trades-mobile-meta-${row.trade_id}`}>meta: {row.meta_engine_decision ?? "-"}</p>
            <Button className="mt-2" variant="outline" onClick={() => openTradeTrace(row)} data-testid={`user-trades-mobile-trace-button-${row.trade_id}`}>Decision Trace</Button>
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
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="user-trades-head-trace">Trace</th>
            </tr>
          </thead>
          <tbody data-testid="user-trades-table-body">
            {trades.map((row) => (
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
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"}>
                  <Button variant="outline" onClick={() => openTradeTrace(row)} data-testid={`user-trades-trace-button-${row.trade_id}`}>Decision Trace</Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
};