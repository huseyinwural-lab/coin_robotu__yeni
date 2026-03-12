import { useEffect, useState } from "react";

import { apiClient } from "@/lib/api";

export const UserTradesPage = () => {
  const [trades, setTrades] = useState([]);

  useEffect(() => {
    const load = async () => {
      const { data } = await apiClient.get("/user/trades", { params: { limit: 100 } });
      setTrades(data || []);
    };
    load();
  }, []);

  return (
    <section className="space-y-4" data-testid="user-trades-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="user-trades-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-trades-title">Trades</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-trades-description">
          Approve edilen sinyallerin trade geçmişi ve execution kaynakları.
        </p>
      </header>

      <div className="overflow-x-auto border border-slate-800 bg-slate-900" data-testid="user-trades-table-wrapper">
        <table className="min-w-full text-sm" data-testid="user-trades-table">
          <thead className="bg-slate-800 text-left" data-testid="user-trades-table-head">
            <tr>
              <th className="px-3 py-2" data-testid="user-trades-head-source">Source</th>
              <th className="px-3 py-2" data-testid="user-trades-head-symbol">Symbol</th>
              <th className="px-3 py-2" data-testid="user-trades-head-side">Side</th>
              <th className="px-3 py-2" data-testid="user-trades-head-status">Status</th>
              <th className="px-3 py-2" data-testid="user-trades-head-qty">Qty</th>
              <th className="px-3 py-2" data-testid="user-trades-head-entry">Entry</th>
              <th className="px-3 py-2" data-testid="user-trades-head-pnl">Realized PnL</th>
            </tr>
          </thead>
          <tbody data-testid="user-trades-table-body">
            {trades.map((row) => (
              <tr key={`${row.source}-${row.trade_id}`} className="border-t border-slate-800" data-testid="user-trades-table-row">
                <td className="px-3 py-2" data-testid="user-trades-row-source">{row.source}</td>
                <td className="px-3 py-2" data-testid="user-trades-row-symbol">{row.symbol}</td>
                <td className="px-3 py-2" data-testid="user-trades-row-side">{row.side}</td>
                <td className="px-3 py-2" data-testid="user-trades-row-status">{row.status}</td>
                <td className="px-3 py-2" data-testid="user-trades-row-quantity">{row.quantity}</td>
                <td className="px-3 py-2" data-testid="user-trades-row-entry">{row.entry_price}</td>
                <td className="px-3 py-2" data-testid="user-trades-row-realized-pnl">{row.realized_pnl ?? "-"}</td>
              </tr>
            ))}
            {trades.length === 0 && (
              <tr data-testid="user-trades-empty-row">
                <td colSpan={7} className="px-3 py-8 text-center text-slate-400" data-testid="user-trades-empty-state">
                  Henüz trade kaydı bulunmuyor.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
};