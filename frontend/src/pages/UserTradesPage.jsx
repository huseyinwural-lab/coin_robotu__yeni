import { useEffect, useState } from "react";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const UserTradesPage = () => {
  const [trades, setTrades] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [compactMode, setCompactMode] = useState(false);

  useEffect(() => {
    const load = async () => {
      setIsLoading(true);
      const { data } = await apiClient.get("/user/trades", { params: { limit: 120 } });
      setTrades(data || []);
      setIsLoading(false);
    };
    load();
  }, []);

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

      <div className="col-span-12 grid gap-3 md:hidden" data-testid="user-trades-mobile-cards" aria-label="Mobil trade kartları">
        {trades.map((row) => (
          <article key={`${row.source}-${row.trade_id}`} className="rounded border border-slate-800 bg-slate-900 p-3" data-testid="user-trades-mobile-card">
            <p className="text-xs text-slate-500" data-testid="user-trades-mobile-symbol">{row.symbol}</p>
            <p className="text-sm" data-testid="user-trades-mobile-side">{row.side} · {row.status}</p>
            <p className="text-xs text-slate-400" data-testid="user-trades-mobile-qty">Qty: {row.quantity}</p>
            <p className="text-xs text-slate-400" data-testid="user-trades-mobile-entry">Entry: {row.entry_price}</p>
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
            </tr>
          </thead>
          <tbody data-testid="user-trades-table-body">
            {trades.map((row) => (
              <tr key={`${row.source}-${row.trade_id}`} className="border-t border-slate-800" data-testid="user-trades-table-row">
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="user-trades-row-source">{row.source}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="user-trades-row-symbol">{row.symbol}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="user-trades-row-side">{row.side}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="user-trades-row-status">{row.status}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="user-trades-row-quantity">{row.quantity}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="user-trades-row-entry">{row.entry_price}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="user-trades-row-realized-pnl">{row.realized_pnl ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
};