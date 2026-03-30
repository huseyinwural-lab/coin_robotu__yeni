import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient, FRONTEND_BACKEND_URL, getSessionDeviceId } from "@/lib/api";

const WINDOW_OPTIONS = ["1h", "6h", "24h"];

const MetricCard = ({ title, value, testId }) => (
  <article className="rounded border border-slate-700 bg-slate-900 p-3" data-testid={`${testId}-card`}>
    <p className="text-xs uppercase tracking-wider text-slate-400" data-testid={`${testId}-label`}>{title}</p>
    <p className="mt-1 text-lg font-bold text-emerald-300" data-testid={`${testId}-value`}>{value ?? "-"}</p>
  </article>
);

const formatDate = (value) => {
  if (!value) return "-";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "-" : parsed.toLocaleString("tr-TR");
};

export default function UserLiveTradingDashboardPage() {
  const [windowSize, setWindowSize] = useState("1h");
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState(null);
  const [positions, setPositions] = useState({ positions: [] });
  const [performance, setPerformance] = useState(null);
  const [risk, setRisk] = useState(null);
  const [execution, setExecution] = useState(null);
  const [strategies, setStrategies] = useState({ items: [] });
  const [trades, setTrades] = useState({ items: [] });
  const [dailyReport, setDailyReport] = useState(null);
  const [decisionCards, setDecisionCards] = useState([]);
  const [queue, setQueue] = useState({ pending_orders: [], pending_decisions: [], queue_depth: 0 });
  const [streamState, setStreamState] = useState("connecting");
  const [strategyPerformance, setStrategyPerformance] = useState({ items: [] });

  const hydrate = useCallback((payload) => {
    setSummary(payload.summary || null);
    setPositions(payload.positions || { positions: [] });
    setStrategies(payload.strategies || { items: [] });
    setTrades(payload.trades || { items: [] });
    setQueue(payload.queue || { pending_orders: [], pending_decisions: [], queue_depth: 0 });
    setDecisionCards(payload.decision_cards || []);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [summaryRes, positionsRes, performanceRes, riskRes, executionRes, strategiesRes, tradesRes, dailyRes, queueRes, cardsRes, strategyPerfRes] = await Promise.all([
        apiClient.get("/user/live/summary", { params: { window: windowSize } }),
        apiClient.get("/user/live/positions"),
        apiClient.get("/user/live/performance", { params: { window: windowSize } }),
        apiClient.get("/user/live/risk", { params: { window: windowSize } }),
        apiClient.get("/user/live/execution-quality", { params: { window: windowSize } }),
        apiClient.get("/user/live/strategies", { params: { window: windowSize } }),
        apiClient.get("/user/live/trades", { params: { window: windowSize } }),
        apiClient.get("/user/live/daily-report", { params: { window: windowSize } }),
        apiClient.get("/user/live/queue", { params: { limit: 12 } }),
        apiClient.get("/user/decision-cards", { params: { limit: 8 } }),
        apiClient.get("/user/live/strategy-performance", { params: { window: "24h" } }),
      ]);

      setSummary(summaryRes.data || null);
      setPositions(positionsRes.data || { positions: [] });
      setPerformance(performanceRes.data || null);
      setRisk(riskRes.data || null);
      setExecution(executionRes.data || null);
      setStrategies(strategiesRes.data || { items: [] });
      setTrades(tradesRes.data || { items: [] });
      setDailyReport(dailyRes.data || null);
      setQueue(queueRes.data || { pending_orders: [], pending_decisions: [], queue_depth: 0 });
      setDecisionCards(cardsRes.data?.items || []);
      setStrategyPerformance(strategyPerfRes.data || { items: [] });
    } catch (error) {
      toast.error(error?.response?.data?.detail || "User dashboard verisi alınamadı");
    } finally {
      setLoading(false);
    }
  }, [windowSize]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const token = window.localStorage.getItem("token");
    if (!token || !FRONTEND_BACKEND_URL) return undefined;
    const base = FRONTEND_BACKEND_URL.replace(/\/$/, "");
    const wsUrl = base.startsWith("https://") ? `${base.replace("https://", "wss://")}/api/user/live/ws/stream` : `${base.replace("http://", "ws://")}/api/user/live/ws/stream`;
    let reconnectTimer = null;
    let socket = null;

    const connect = () => {
      const deviceId = getSessionDeviceId();
      socket = new WebSocket(`${wsUrl}?token=${encodeURIComponent(token)}&device_id=${encodeURIComponent(deviceId)}`);
      socket.onopen = () => setStreamState("connected");
      socket.onclose = () => {
        setStreamState("disconnected");
        reconnectTimer = window.setTimeout(connect, 2500);
      };
      socket.onerror = () => setStreamState("error");
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.event_type !== "user_live_snapshot") return;
          hydrate(payload);
        } catch {
          setStreamState("error");
        }
      };
    };

    connect();
    const heartbeat = window.setInterval(() => {
      if (socket && socket.readyState === WebSocket.OPEN) socket.send("ping");
    }, 15000);
    return () => {
      window.clearInterval(heartbeat);
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      if (socket) socket.close();
    };
  }, [hydrate]);

  const exportDailyReport = async (format) => {
    try {
      const isCsv = format === "csv";
      const response = await apiClient.get("/user/live/daily-report/export", {
        params: { format, window: windowSize },
        responseType: isCsv ? "blob" : "json",
      });
      const blob = isCsv ? new Blob([response.data], { type: "text/csv" }) : new Blob([JSON.stringify(response.data, null, 2)], { type: "application/json" });
      const blobUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = blobUrl;
      link.download = isCsv ? `user_live_daily_report_${dailyReport?.date || "latest"}.csv` : `user_live_daily_report_${dailyReport?.date || "latest"}.json`;
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
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-4xl font-black uppercase tracking-tight text-emerald-300" data-testid="user-live-trading-dashboard-title">Global Dashboard</h2>
            <p className="mt-2 text-sm text-slate-300" data-testid="user-live-trading-dashboard-description">Karar, execution, risk, strategy, alert ve queue görünürlüğü tek kullanıcı ekranında.</p>
          </div>
          <p className="font-mono text-xs text-emerald-200" data-testid="user-live-trading-dashboard-stream-state">stream={streamState}</p>
        </div>
      </header>

      <div className="flex flex-wrap items-end gap-2" data-testid="user-live-trading-dashboard-toolbar">
        <label className="space-y-1" data-testid="user-live-trading-dashboard-window-field">
          <span className="text-xs text-slate-400">Window</span>
          <select value={windowSize} onChange={(event) => setWindowSize(event.target.value)} className="h-10 rounded border border-slate-700 bg-black px-2 text-sm" data-testid="user-live-trading-dashboard-window-select">
            {WINDOW_OPTIONS.map((option) => <option key={option} value={option} data-testid={`user-live-trading-dashboard-window-option-${option}`}>{option}</option>)}
          </select>
        </label>
        <Button type="button" variant="outline" onClick={load} data-testid="user-live-trading-dashboard-refresh-button">Yenile</Button>
        <Button type="button" variant="outline" onClick={() => exportDailyReport("json")} data-testid="user-live-trading-dashboard-export-json-button">Export JSON</Button>
        <Button type="button" variant="outline" onClick={() => exportDailyReport("csv")} data-testid="user-live-trading-dashboard-export-csv-button">Export CSV</Button>
        <Link to="/user/alerts" data-testid="user-live-trading-dashboard-open-alerts-link"><Button type="button" variant="outline" data-testid="user-live-trading-dashboard-open-alerts-button">Alert Center</Button></Link>
        <Link to="/user/execution" data-testid="user-live-trading-dashboard-open-execution-link"><Button type="button" variant="outline" data-testid="user-live-trading-dashboard-open-execution-button">Execution View</Button></Link>
      </div>

      <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6" data-testid="user-live-trading-kpi-grid">
        <MetricCard title="running bots" value={summary?.bots?.running_bots ?? 0} testId="user-live-kpi-running-bots" />
        <MetricCard title="open positions" value={summary?.open_positions?.positions_count ?? 0} testId="user-live-kpi-open-positions" />
        <MetricCard title="pnl today" value={performance?.pnl_today ?? 0} testId="user-live-kpi-pnl-today" />
        <MetricCard title="risk score" value={risk?.own_portfolio_exposure ?? 0} testId="user-live-kpi-risk-score" />
        <MetricCard title="active strategies" value={strategies?.strategy_count ?? 0} testId="user-live-kpi-active-strategies" />
        <MetricCard title="queue depth" value={queue?.queue_depth ?? 0} testId="user-live-kpi-queue-depth" />
      </div>

      <div className="grid gap-3 lg:grid-cols-3" data-testid="user-live-dashboard-primary-grid">
        <article className="rounded border border-slate-700 bg-slate-900 p-4" data-testid="user-live-alerts-card">
          <h3 className="text-base font-semibold" data-testid="user-live-alerts-title">Runtime Alert Snapshot</h3>
          <div className="mt-3 space-y-2" data-testid="user-live-alerts-list">
            {alerts.length === 0 ? <p className="text-sm text-emerald-300" data-testid="user-live-alerts-empty">Aktif uyarı yok</p> : alerts.map((item, idx) => (
              <div key={`${item.code}-${idx}`} className="rounded border border-amber-700 bg-amber-950/30 p-2" data-testid={`user-live-alert-item-${idx}`}>
                <p className="text-xs uppercase tracking-wide text-amber-300">{item.code}</p>
                <p className="text-sm text-slate-100">{item.message}</p>
              </div>
            ))}
          </div>
        </article>

        <article className="rounded border border-slate-700 bg-slate-900 p-4" data-testid="user-live-decision-cards-panel">
          <h3 className="text-base font-semibold" data-testid="user-live-decision-cards-title">Son Kararlar</h3>
          <div className="mt-3 space-y-2" data-testid="user-live-decision-cards-list">
            {(decisionCards || []).slice(0, 6).map((row, idx) => (
              <div key={`${row.symbol}-${idx}`} className="rounded border border-slate-800 p-3" data-testid={`user-live-decision-card-${idx}`}>
                <p className="font-semibold">{row.symbol}</p>
                <p className="text-xs text-slate-400">{row.decision} · confidence={row.confidence}</p>
                <p className="text-xs text-cyan-300">{row.dominant_family || "-"}</p>
              </div>
            ))}
          </div>
        </article>

        <article className="rounded border border-slate-700 bg-slate-900 p-4" data-testid="user-live-queue-panel">
          <h3 className="text-base font-semibold" data-testid="user-live-queue-title">Pending Decisions / Orders</h3>
          <div className="mt-3 space-y-2" data-testid="user-live-queue-items">
            {(queue?.pending_orders || []).slice(0, 6).map((row, idx) => (
              <div key={`${row.intent_id}-${idx}`} className="rounded border border-slate-800 p-2" data-testid={`user-live-queue-order-${idx}`}>
                <p className="font-mono text-xs">{row.intent_id}</p>
                <p className="text-xs text-slate-400">{row.symbol} · {row.status} · risk={row.risk_score}</p>
              </div>
            ))}
          </div>
        </article>
      </div>

      <div className="grid gap-3 lg:grid-cols-2" data-testid="user-live-trading-tables-grid">
        <article className="rounded border border-slate-700 bg-slate-900 p-4" data-testid="user-live-position-snapshot-panel">
          <h3 className="text-base font-semibold" data-testid="user-live-position-snapshot-title">Aktif Pozisyonlar</h3>
          <div className="mt-3 overflow-x-auto">
            <table className="min-w-full text-sm" data-testid="user-live-position-snapshot-table">
              <thead>
                <tr className="text-left text-slate-400"><th className="py-1">Symbol</th><th className="py-1">Side</th><th className="py-1">Entry</th><th className="py-1">Current</th><th className="py-1">UPnL</th></tr>
              </thead>
              <tbody>
                {(positions?.positions || []).slice(0, 8).map((row, idx) => (
                  <tr key={`${row.position_id}-${idx}`} className="border-t border-slate-800" data-testid={`user-live-position-snapshot-row-${idx}`}>
                    <td>{row.symbol}</td><td>{row.side}</td><td>{row.entry_price}</td><td>{row.current_price}</td><td>{row.unrealized_pnl}</td>
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
                <tr className="text-left text-slate-400"><th className="py-1">Time</th><th className="py-1">Symbol</th><th className="py-1">Side</th><th className="py-1">Size</th><th className="py-1">PNL</th></tr>
              </thead>
              <tbody>
                {(trades?.items || []).slice(0, 10).map((row, idx) => (
                  <tr key={`${row.trade_id}-${idx}`} className="border-t border-slate-800" data-testid={`user-live-trades-row-${idx}`}>
                    <td>{formatDate(row.timestamp)}</td><td>{row.symbol}</td><td>{row.side}</td><td>{row.size}</td><td>{row.pnl}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      </div>

      <article className="rounded border border-slate-700 bg-slate-900 p-4" data-testid="user-live-strategy-performance-panel">
        <h3 className="text-base font-semibold" data-testid="user-live-strategy-performance-title">Strategy Performance (Backtest ↔ Live)</h3>
        <div className="mt-3 overflow-x-auto">
          <table className="min-w-full text-sm" data-testid="user-live-strategy-performance-table">
            <thead><tr className="text-left text-slate-400"><th>Strategy</th><th>Backtest Win</th><th>Live Win</th><th>Deviation %</th></tr></thead>
            <tbody>
              {(strategyPerformance?.items || []).slice(0, 8).map((row, idx) => (
                <tr key={`${row.strategy_id}-${idx}`} className="border-t border-slate-800" data-testid={`user-live-strategy-performance-row-${idx}`}>
                  <td>{row.strategy_id}</td><td>{row.backtest?.win_rate ?? 0}</td><td>{row.live?.win_rate ?? 0}</td><td>{row.deviation_pct ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>

      <article className="rounded border border-slate-700 bg-slate-900 p-4" data-testid="user-live-daily-report-panel">
        <h3 className="text-base font-semibold" data-testid="user-live-daily-report-title">Daily Report Snapshot</h3>
        <pre className="mt-3 overflow-x-auto whitespace-pre-wrap text-xs text-slate-300" data-testid="user-live-daily-report-json">{JSON.stringify(dailyReport || {}, null, 2)}</pre>
      </article>

      <p className="text-xs text-slate-500" data-testid="user-live-dashboard-loading-state">loading={String(loading)}</p>
    </section>
  );
}