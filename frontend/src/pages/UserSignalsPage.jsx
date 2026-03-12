import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const UserSignalsPage = () => {
  const navigate = useNavigate();
  const [signals, setSignals] = useState([]);
  const [portfolio, setPortfolio] = useState(null);
  const [trades, setTrades] = useState([]);
  const [busyId, setBusyId] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [compactMode, setCompactMode] = useState(false);
  const [selectedSignalId, setSelectedSignalId] = useState("");
  const [signalTrace, setSignalTrace] = useState(null);
  const [strategyExplain, setStrategyExplain] = useState(null);
  const [explainLoadingId, setExplainLoadingId] = useState("");

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

  const openExecuteFromSignal = (signal) => {
    const side = signal.status === "pending" ? "buy" : "buy";
    navigate(`/user/execute?source=signal&symbol=${encodeURIComponent(signal.symbol)}&side=${encodeURIComponent(side)}&market_type=spot&preset=spot_basic`);
  };

  const applyPresetFromSignal = (signal) => {
    navigate(`/user/execute?source=signal&symbol=${encodeURIComponent(signal.symbol)}&side=buy&market_type=spot&preset=spot_basic`);
  };

  const buildIntentPayload = (signal) => ({
    source_type: "signal",
    source_ref_id: signal.signal_id,
    market_type: "spot",
    symbol: signal.symbol,
    side: "buy",
    order_type: "market",
    position_size_mode: "fixed_notional",
    position_size_value: 30,
    take_profit_mode: "percent",
    take_profit_value: 2,
    stop_loss_mode: "percent",
    stop_loss_value: 1,
    execution_mode: "signal_follow",
  });

  const previewIntentFromSignal = async (signal) => {
    try {
      const { data } = await apiClient.post("/user/execution/intent/preview", buildIntentPayload(signal));
      toast.success(`Preview: ${data.validation_status}`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Preview başarısız");
    }
  };

  const followSignalToQueue = async (signal) => {
    try {
      const { data } = await apiClient.post("/user/execution/intent/preview", buildIntentPayload(signal));
      if (data.validation_status !== "valid") {
        toast.error("Signal policy tarafından reddedildi");
        return;
      }
      await apiClient.post("/user/execution/intent/submit", {
        intent_token: data.intent_token,
        preview_hash: data.preview_hash,
      });
      toast.success("Follow Signal kuyruğa eklendi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Follow signal başarısız");
    }
  };

  const openSignalExplain = async (signal) => {
    setSelectedSignalId(signal.id);
    setExplainLoadingId(signal.id);
    try {
      const [traceRes, strategyRes] = await Promise.all([
        apiClient.get(`/user/signals/${signal.id}/decision-trace`),
        apiClient.get(`/user/strategies/${encodeURIComponent(signal.strategy_code)}/explain`, { params: { lookback_days: 30 } }),
      ]);
      setSignalTrace(traceRes.data || null);
      setStrategyExplain(strategyRes.data || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Signal açıklaması yüklenemedi");
    } finally {
      setExplainLoadingId("");
    }
  };

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

      <aside className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="user-signals-explain-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-signals-explain-panel-title">Why this signal?</p>
        {!selectedSignalId && (
          <p className="mt-2 text-sm text-slate-400" data-testid="user-signals-explain-empty-state">Bir sinyal seçerek açıklama panelini açın.</p>
        )}
        {Boolean(selectedSignalId && explainLoadingId === selectedSignalId) && (
          <p className="mt-2 text-sm text-slate-300" data-testid="user-signals-explain-loading-state">Açıklama yükleniyor...</p>
        )}
        {Boolean(selectedSignalId && signalTrace?.latest_trace) && (
          <div className="mt-3 grid gap-3 lg:grid-cols-2" data-testid="user-signals-explain-content">
            <div className="border border-slate-800 p-3" data-testid="user-signals-latest-trace-card">
              <p className="text-xs text-slate-500" data-testid="user-signals-latest-trace-status">Decision: {signalTrace.latest_trace.decision_status}</p>
              <p className="text-xs text-slate-500" data-testid="user-signals-latest-trace-type">Type: {signalTrace.latest_trace.trace_type}</p>
              <div className="mt-2 space-y-2" data-testid="user-signals-reason-details-list">
                {(signalTrace.latest_trace.reason_details || []).map((reason) => (
                  <article key={reason.code} className="border border-slate-800 p-2" data-testid={`user-signals-reason-item-${reason.code}`}>
                    <p className="text-sm font-semibold" data-testid={`user-signals-reason-title-${reason.code}`}>{reason.title}</p>
                    <p className="text-xs text-slate-400" data-testid={`user-signals-reason-description-${reason.code}`}>{reason.description}</p>
                  </article>
                ))}
              </div>
            </div>

            <div className="border border-slate-800 p-3" data-testid="user-signals-strategy-explain-card">
              <p className="text-xs text-slate-500" data-testid="user-signals-strategy-code">Strategy: {strategyExplain?.strategy_code || "-"}</p>
              <p className="text-xs text-slate-500" data-testid="user-signals-strategy-trace-count">Trace Count: {strategyExplain?.trace_count ?? 0}</p>
              <div className="mt-2 space-y-2" data-testid="user-signals-strategy-top-reasons">
                {(strategyExplain?.top_reason_codes || []).slice(0, 3).map((reason) => (
                  <article key={reason.code} className="border border-slate-800 p-2" data-testid={`user-signals-strategy-reason-${reason.code}`}>
                    <p className="text-sm" data-testid={`user-signals-strategy-reason-title-${reason.code}`}>{reason.title} · {reason.count}</p>
                    <p className="text-xs text-slate-400" data-testid={`user-signals-strategy-reason-desc-${reason.code}`}>{reason.description}</p>
                  </article>
                ))}
              </div>
            </div>
          </div>
        )}
      </aside>

      <div className="col-span-12 grid gap-3 md:hidden" data-testid="user-signals-mobile-cards">
        {signals.map((signal) => (
          <article key={signal.id} className="rounded border border-slate-800 bg-slate-900 p-3" data-testid={`user-signals-mobile-card-${signal.id}`}>
            <p className="text-sm font-semibold" data-testid={`user-signals-mobile-symbol-${signal.id}`}>{signal.symbol}</p>
            <p className="text-xs text-slate-500" data-testid={`user-signals-mobile-status-${signal.id}`}>{signal.status}</p>
            <p className="text-xs text-slate-500" data-testid={`user-signals-mobile-strategy-${signal.id}`}>{signal.strategy_code}</p>
            <div className="mt-2 flex flex-wrap gap-2" data-testid={`user-signals-mobile-actions-${signal.id}`}>
              <Button variant="outline" onClick={() => openSignalExplain(signal)} data-testid={`user-signals-mobile-why-button-${signal.id}`}>Why this signal?</Button>
              {signal.status === "pending" && (
                <>
                  <Button className="bg-emerald-500 text-black hover:bg-emerald-400" disabled={busyId === signal.id} onClick={() => decideSignal(signal.id, "approve")} data-testid={`user-signals-mobile-approve-${signal.id}`}>Approve</Button>
                  <Button variant="outline" disabled={busyId === signal.id} onClick={() => decideSignal(signal.id, "reject")} data-testid={`user-signals-mobile-reject-${signal.id}`}>Reject</Button>
                  <Button variant="outline" onClick={() => openExecuteFromSignal(signal)} data-testid={`user-signals-mobile-open-execute-${signal.id}`}>Execute</Button>
                  <Button variant="outline" onClick={() => applyPresetFromSignal(signal)} data-testid={`user-signals-mobile-apply-preset-${signal.id}`}>Apply Preset</Button>
                  <Button variant="outline" onClick={() => previewIntentFromSignal(signal)} data-testid={`user-signals-mobile-preview-intent-${signal.id}`}>Preview Intent</Button>
                  <Button variant="outline" onClick={() => followSignalToQueue(signal)} data-testid={`user-signals-mobile-follow-signal-${signal.id}`}>Follow Signal</Button>
                </>
              )}
              {signal.status !== "pending" && (
                <span className="text-xs text-slate-400" data-testid={`user-signals-mobile-final-status-${signal.id}`}>{signal.status}</span>
              )}
            </div>
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
              <tr key={signal.id} className="border-t border-slate-800" data-testid={`user-signals-table-row-${signal.id}`}>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-signals-table-symbol-${signal.id}`}>{signal.symbol}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-signals-table-strategy-${signal.id}`}>{signal.strategy_code}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-signals-table-confidence-${signal.id}`}>{signal.confidence}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-signals-table-status-${signal.id}`}>{signal.status}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-signals-table-time-${signal.id}`}>{new Date(signal.created_at).toLocaleString()}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"}>
                  <div className="flex flex-wrap gap-2" data-testid={`user-signals-actions-${signal.id}`}>
                    <Button variant="outline" onClick={() => openSignalExplain(signal)} data-testid={`user-signals-why-button-${signal.id}`}>Why this signal?</Button>
                    {signal.status === "pending" ? (
                      <>
                        <Button className="bg-emerald-500 text-black hover:bg-emerald-400" disabled={busyId === signal.id} onClick={() => decideSignal(signal.id, "approve")} data-testid={`user-signals-approve-button-${signal.id}`}>Approve</Button>
                        <Button variant="outline" disabled={busyId === signal.id} onClick={() => decideSignal(signal.id, "reject")} data-testid={`user-signals-reject-button-${signal.id}`}>Reject</Button>
                        <Button variant="outline" onClick={() => openExecuteFromSignal(signal)} data-testid={`user-signals-open-execute-button-${signal.id}`}>Open in Execute</Button>
                        <Button variant="outline" onClick={() => applyPresetFromSignal(signal)} data-testid={`user-signals-apply-preset-button-${signal.id}`}>Apply Preset</Button>
                        <Button variant="outline" onClick={() => previewIntentFromSignal(signal)} data-testid={`user-signals-preview-intent-button-${signal.id}`}>Preview Intent</Button>
                        <Button variant="outline" onClick={() => followSignalToQueue(signal)} data-testid={`user-signals-follow-signal-button-${signal.id}`}>Follow Signal</Button>
                      </>
                    ) : (
                      <span className="text-xs text-slate-400" data-testid={`user-signals-final-status-text-${signal.id}`}>{signal.status}</span>
                    )}
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