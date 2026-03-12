import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const UserSignalsPage = () => {
  const [signals, setSignals] = useState([]);
  const [portfolio, setPortfolio] = useState(null);
  const [trades, setTrades] = useState([]);
  const [busyId, setBusyId] = useState("");

  const load = async () => {
    const [signalsRes, portfolioRes, tradesRes] = await Promise.all([
      apiClient.get("/user/signals", { params: { limit: 120 } }),
      apiClient.get("/user/portfolio"),
      apiClient.get("/user/trades", { params: { limit: 120 } }),
    ]);
    setSignals(signalsRes.data || []);
    setPortfolio(portfolioRes.data);
    setTrades(tradesRes.data || []);
  };

  useEffect(() => {
    load();
  }, []);

  const pendingSignals = useMemo(
    () => signals.filter((item) => item.status === "pending"),
    [signals],
  );

  const decideSignal = async (signalId, action) => {
    setBusyId(signalId);
    try {
      await apiClient.post(`/user/signal/${signalId}/${action}`, { note: `${action}_from_ui` });
      await load();
      toast.success(action === "approve" ? "Signal approve edildi" : "Signal reject edildi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Signal kararı kaydedilemedi");
    } finally {
      setBusyId("");
    }
  };

  return (
    <section className="space-y-4" data-testid="user-signals-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="user-signals-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-signals-title">Signals</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-signals-description">
          ASSISTED queue: approve/reject sonrası order, portfolio ve trade geçmişi güncellenir.
        </p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" data-testid="user-signals-metrics-grid">
        <div className="border border-slate-800 bg-slate-900 p-3" data-testid="user-signals-pending-count-card">
          <p className="text-xs text-slate-500" data-testid="user-signals-pending-count-label">Pending Signals</p>
          <p className="text-xl font-semibold text-orange-400" data-testid="user-signals-pending-count-value">{pendingSignals.length}</p>
        </div>
        <div className="border border-slate-800 bg-slate-900 p-3" data-testid="user-signals-open-positions-card">
          <p className="text-xs text-slate-500" data-testid="user-signals-open-positions-label">Open Positions</p>
          <p className="text-xl font-semibold" data-testid="user-signals-open-positions-value">{portfolio?.open_positions_count ?? "-"}</p>
        </div>
        <div className="border border-slate-800 bg-slate-900 p-3" data-testid="user-signals-open-notional-card">
          <p className="text-xs text-slate-500" data-testid="user-signals-open-notional-label">Open Notional</p>
          <p className="text-xl font-semibold" data-testid="user-signals-open-notional-value">{portfolio?.open_notional ?? "-"}</p>
        </div>
        <div className="border border-slate-800 bg-slate-900 p-3" data-testid="user-signals-trades-count-card">
          <p className="text-xs text-slate-500" data-testid="user-signals-trades-count-label">Trades Count</p>
          <p className="text-xl font-semibold" data-testid="user-signals-trades-count-value">{trades.length}</p>
        </div>
      </div>

      <div className="overflow-x-auto border border-slate-800 bg-slate-900" data-testid="user-signals-table-wrapper">
        <table className="min-w-full text-sm" data-testid="user-signals-table">
          <thead className="bg-slate-800 text-left" data-testid="user-signals-table-head">
            <tr>
              <th className="px-3 py-2" data-testid="user-signals-head-symbol">Symbol</th>
              <th className="px-3 py-2" data-testid="user-signals-head-strategy">Strategy</th>
              <th className="px-3 py-2" data-testid="user-signals-head-confidence">Confidence</th>
              <th className="px-3 py-2" data-testid="user-signals-head-status">Status</th>
              <th className="px-3 py-2" data-testid="user-signals-head-created-at">Time</th>
              <th className="px-3 py-2" data-testid="user-signals-head-actions">Actions</th>
            </tr>
          </thead>
          <tbody data-testid="user-signals-table-body">
            {signals.map((signal) => (
              <tr key={signal.id} className="border-t border-slate-800" data-testid="user-signals-table-row">
                <td className="px-3 py-2" data-testid="user-signals-row-symbol">{signal.symbol}</td>
                <td className="px-3 py-2" data-testid="user-signals-row-strategy">{signal.strategy_code}</td>
                <td className="px-3 py-2" data-testid="user-signals-row-confidence">{signal.confidence}</td>
                <td className="px-3 py-2" data-testid="user-signals-row-status">{signal.status}</td>
                <td className="px-3 py-2" data-testid="user-signals-row-created-at">{new Date(signal.created_at).toLocaleString()}</td>
                <td className="px-3 py-2" data-testid="user-signals-row-actions">
                  {signal.status === "pending" ? (
                    <div className="flex gap-2" data-testid="user-signals-pending-actions-group">
                      <Button
                        className="bg-emerald-500 text-black hover:bg-emerald-400"
                        disabled={busyId === signal.id}
                        onClick={() => decideSignal(signal.id, "approve")}
                        data-testid="user-signals-approve-button"
                      >
                        Approve
                      </Button>
                      <Button
                        variant="outline"
                        disabled={busyId === signal.id}
                        onClick={() => decideSignal(signal.id, "reject")}
                        data-testid="user-signals-reject-button"
                      >
                        Reject
                      </Button>
                    </div>
                  ) : (
                    <span className="text-xs text-slate-400" data-testid="user-signals-final-status-text">{signal.status}</span>
                  )}
                </td>
              </tr>
            ))}
            {signals.length === 0 && (
              <tr data-testid="user-signals-empty-row">
                <td colSpan={6} className="px-3 py-8 text-center text-slate-400" data-testid="user-signals-empty-state">
                  Henüz sinyal bulunmuyor. Scanner sayfasından run başlatın.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
};