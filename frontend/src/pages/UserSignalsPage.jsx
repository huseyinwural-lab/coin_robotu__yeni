import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const UserSignalsPage = () => {
  const [signals, setSignals] = useState([]);
  const [portfolio, setPortfolio] = useState(null);
  const [trades, setTrades] = useState([]);
  const [busyId, setBusyId] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [compactMode, setCompactMode] = useState(false);

  const load = async () => {
    setIsLoading(true);
    const [signalsRes, portfolioRes, tradesRes] = await Promise.all([
      apiClient.get("/user/signals", { params: { limit: 120 } }),
      apiClient.get("/user/portfolio"),
      apiClient.get("/user/trades", { params: { limit: 120 } }),
    ]);
    setSignals(signalsRes.data || []);
    setPortfolio(portfolioRes.data);
    setTrades(tradesRes.data || []);
    setIsLoading(false);
  };

  useEffect(() => {
    load();
  }, []);

  const pendingSignals = useMemo(() => signals.filter((item) => item.status === "pending"), [signals]);

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

  if (isLoading) {
    return <LoadingSkeleton rows={6} testId="user-signals-loading-skeleton" />;
  }

  return (
    <section className="grid grid-cols-12 gap-4" data-testid="user-signals-page">
      <header className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="user-signals-header">
        <div className="flex flex-wrap items-center justify-between gap-3" data-testid="user-signals-header-controls">
          <div>
            <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-signals-title">Signals</h2>
            <p className="mt-2 text-sm text-slate-400" data-testid="user-signals-description">ASSISTED queue + responsive card/table layout + compact mode.</p>
          </div>
          <Button type="button" variant="outline" onClick={() => setCompactMode((previous) => !previous)} data-testid="user-signals-compact-mode-toggle" aria-label="Compact mode aç/kapat">
            {compactMode ? "Compact: ON" : "Compact: OFF"}
          </Button>
        </div>
      </header>

      <div className="col-span-12 grid grid-cols-12 gap-3" data-testid="user-signals-metrics-grid">
        <div className="col-span-6 md:col-span-3 border border-slate-800 bg-slate-900 p-3" data-testid="user-signals-pending-count-card"><p className="text-xs text-slate-500">Pending</p><p className="text-xl font-semibold text-orange-400" data-testid="user-signals-pending-count-value">{pendingSignals.length}</p></div>
        <div className="col-span-6 md:col-span-3 border border-slate-800 bg-slate-900 p-3" data-testid="user-signals-open-positions-card"><p className="text-xs text-slate-500">Open Positions</p><p className="text-xl font-semibold" data-testid="user-signals-open-positions-value">{portfolio?.open_positions_count ?? "-"}</p></div>
        <div className="col-span-6 md:col-span-3 border border-slate-800 bg-slate-900 p-3" data-testid="user-signals-open-notional-card"><p className="text-xs text-slate-500">Open Notional</p><p className="text-xl font-semibold" data-testid="user-signals-open-notional-value">{portfolio?.open_notional ?? "-"}</p></div>
        <div className="col-span-6 md:col-span-3 border border-slate-800 bg-slate-900 p-3" data-testid="user-signals-trades-count-card"><p className="text-xs text-slate-500">Trades</p><p className="text-xl font-semibold" data-testid="user-signals-trades-count-value">{trades.length}</p></div>
      </div>

      <div className="col-span-12 grid gap-3 md:hidden" data-testid="user-signals-mobile-cards">
        {signals.map((signal) => (
          <article key={signal.id} className="rounded border border-slate-800 bg-slate-900 p-3" data-testid="user-signals-mobile-card">
            <p className="text-sm font-semibold" data-testid="user-signals-mobile-symbol">{signal.symbol}</p>
            <p className="text-xs text-slate-500" data-testid="user-signals-mobile-status">{signal.status}</p>
            <p className="text-xs text-slate-500" data-testid="user-signals-mobile-strategy">{signal.strategy_code}</p>
            {signal.status === "pending" && (
              <div className="mt-2 flex gap-2" data-testid="user-signals-mobile-actions">
                <Button className="bg-emerald-500 text-black hover:bg-emerald-400" disabled={busyId === signal.id} onClick={() => decideSignal(signal.id, "approve")} data-testid="user-signals-mobile-approve">Approve</Button>
                <Button variant="outline" disabled={busyId === signal.id} onClick={() => decideSignal(signal.id, "reject")} data-testid="user-signals-mobile-reject">Reject</Button>
              </div>
            )}
          </article>
        ))}
      </div>

      <div className="col-span-12 hidden overflow-x-auto border border-slate-800 bg-slate-900 md:block" data-testid="user-signals-table-wrapper">
        <table className="min-w-full text-sm" data-testid="user-signals-table" aria-label="Signals tablosu">
          <thead className="bg-slate-800 text-left" data-testid="user-signals-table-head">
            <tr>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"}>Symbol</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"}>Strategy</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"}>Confidence</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"}>Status</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"}>Time</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"}>Actions</th>
            </tr>
          </thead>
          <tbody data-testid="user-signals-table-body">
            {signals.map((signal) => (
              <tr key={signal.id} className="border-t border-slate-800" data-testid="user-signals-table-row">
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"}>{signal.symbol}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"}>{signal.strategy_code}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"}>{signal.confidence}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"}>{signal.status}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"}>{new Date(signal.created_at).toLocaleString()}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"}>
                  {signal.status === "pending" ? (
                    <div className="flex gap-2">
                      <Button className="bg-emerald-500 text-black hover:bg-emerald-400" disabled={busyId === signal.id} onClick={() => decideSignal(signal.id, "approve")} data-testid="user-signals-approve-button">Approve</Button>
                      <Button variant="outline" disabled={busyId === signal.id} onClick={() => decideSignal(signal.id, "reject")} data-testid="user-signals-reject-button">Reject</Button>
                    </div>
                  ) : (
                    <span className="text-xs text-slate-400" data-testid="user-signals-final-status-text">{signal.status}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
};