import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";

const WINDOW_OPTIONS = ["1h", "6h", "24h"];

const MetricCard = ({ title, value, testId }) => (
  <article className="rounded border border-slate-700 bg-slate-900 p-3" data-testid={`${testId}-card`}>
    <p className="text-xs uppercase tracking-wider text-slate-500" data-testid={`${testId}-label`}>{title}</p>
    <p className="mt-1 text-lg font-bold" data-testid={`${testId}-value`}>{value ?? "-"}</p>
  </article>
);

const MODE_PHRASES = {
  LIVE: "SWITCH TO LIVE",
  PAPER: "SWITCH TO PAPER",
  MOCK: "SWITCH TO MOCK",
};

const ACTION_PHRASES = {
  kill_on: "DISABLE TRADING",
  kill_off: "ENABLE TRADING",
  fallback_on: "ENABLE FALLBACK",
  fallback_off: "DISABLE FALLBACK",
  set_latency: "SET LATENCY THRESHOLD",
  risk_update: "UPDATE RISK CONTROLS",
  risk_override: "APPLY RISK OVERRIDE",
  snapshot: "CAPTURE SNAPSHOT",
  reset_daily: "RESET DAILY METRICS",
  retry_orders: "RETRY FAILED ORDERS",
};

const FIX_ACTIONS = [
  "reconnect-exchange",
  "restart-service",
  "cancel-stuck-orders",
  "requeue-timeout-intents",
  "flush-retry-queue",
  "force-resync-positions",
];

export const AdminLiveTradingDashboardPage = () => {
  const { user } = useAuth();
  const isManager = ["super_admin", "admin"].includes(String(user?.role || ""));

  const [windowSize, setWindowSize] = useState("1h");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [loading, setLoading] = useState(true);

  const [summary, setSummary] = useState(null);
  const [scannerHealth, setScannerHealth] = useState(null);
  const [executionQuality, setExecutionQuality] = useState(null);
  const [riskSummary, setRiskSummary] = useState(null);
  const [dailyReport, setDailyReport] = useState(null);
  const [learningSummary, setLearningSummary] = useState(null);

  const [controlState, setControlState] = useState(null);
  const [criticalAlerts, setCriticalAlerts] = useState([]);
  const [failedOrders, setFailedOrders] = useState([]);
  const [openPositions, setOpenPositions] = useState([]);

  const [selectedFailedIds, setSelectedFailedIds] = useState([]);

  const [latencyForm, setLatencyForm] = useState({ scan_latency_ms: "1500", decision_latency_ms: "900", execution_latency_ms: "1600" });
  const [riskForm, setRiskForm] = useState({ max_loss_pct: "5", account_exposure_pct: "60", symbol_exposure_pct: "25" });
  const [riskOverrideForm, setRiskOverrideForm] = useState({ decision: "force_reject", ttl_minutes: "30" });

  const [actionDialog, setActionDialog] = useState({
    open: false,
    actionKey: "",
    title: "",
    expectedPhrase: "",
    reason: "",
    phrase: "",
    context: {},
  });

  const openActionDialog = ({ actionKey, title, expectedPhrase, reason, context }) => {
    setActionDialog({
      open: true,
      actionKey,
      title,
      expectedPhrase,
      reason: reason || "",
      phrase: "",
      context: context || {},
    });
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [
        summaryRes,
        scannerRes,
        executionRes,
        riskRes,
        dailyRes,
        learningRes,
        controlRes,
        alertsRes,
        failedRes,
        positionsRes,
      ] = await Promise.all([
        apiClient.get("/admin/live-trading/summary", { params: { window: windowSize } }),
        apiClient.get("/admin/live-trading/scanner-health", { params: { window: windowSize } }),
        apiClient.get("/admin/live-trading/execution-quality", { params: { window: windowSize } }),
        apiClient.get("/admin/live-trading/risk-summary", { params: { window: windowSize } }),
        apiClient.get("/admin/live-trading/daily-report"),
        apiClient.get("/admin/live-trading/learning-summary", { params: { window: windowSize } }),
        apiClient.get("/admin/live-trading/control-layer/state"),
        apiClient.get("/admin/live-trading/control-layer/critical-alerts", { params: { status_filter: "all", limit: 40 } }),
        apiClient.get("/admin/live-trading/control-layer/execution-quality/failed-orders", { params: { status_filter: "all", limit: 100 } }),
        apiClient.get("/admin/live-trading/control-layer/trading-performance/open-positions", { params: { limit: 100 } }),
      ]);

      setSummary(summaryRes.data || null);
      setScannerHealth(scannerRes.data || null);
      setExecutionQuality(executionRes.data || null);
      setRiskSummary(riskRes.data || null);
      setDailyReport(dailyRes.data || null);
      setLearningSummary(learningRes.data || null);
      setControlState(controlRes.data || null);
      setCriticalAlerts(alertsRes.data?.items || []);
      setFailedOrders(failedRes.data?.items || []);
      setOpenPositions(positionsRes.data?.items || []);

      const threshold = controlRes.data?.latency_thresholds;
      if (threshold) {
        setLatencyForm({
          scan_latency_ms: String(threshold.scan_latency_ms ?? "1500"),
          decision_latency_ms: String(threshold.decision_latency_ms ?? "900"),
          execution_latency_ms: String(threshold.execution_latency_ms ?? "1600"),
        });
      }

      if (riskRes.data) {
        setRiskForm({
          max_loss_pct: String(riskRes.data.daily_loss_pct ?? 5),
          account_exposure_pct: String(riskRes.data.config?.account_max_notional_pct ?? 60),
          symbol_exposure_pct: String(riskRes.data.config?.symbol_max_notional_pct ?? 25),
        });
      }
    } catch (error) {
      const detail = error?.response?.data?.detail;
      const message = typeof detail === "string" ? detail : "Live Trading Dashboard verisi alınamadı";
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [windowSize]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!autoRefresh) return undefined;
    const timer = setInterval(() => load(), 30000);
    return () => clearInterval(timer);
  }, [autoRefresh, load]);

  const runAction = async () => {
    if (!actionDialog.reason || actionDialog.reason.trim().length < 3) {
      toast.error("Reason zorunlu");
      return;
    }
    if (actionDialog.phrase.trim().toUpperCase() !== actionDialog.expectedPhrase) {
      toast.error(`Phrase hatalı. Beklenen: ${actionDialog.expectedPhrase}`);
      return;
    }

    try {
      if (actionDialog.actionKey.startsWith("mode_")) {
        const mode = actionDialog.actionKey.replace("mode_", "").toUpperCase();
        await apiClient.post("/admin/live-trading/control-layer/execution-mode", {
          mode,
          reason: actionDialog.reason,
          confirmation_phrase: actionDialog.phrase,
        });
      }

      if (["kill_on", "kill_off", "fallback_on", "fallback_off", "set_latency"].includes(actionDialog.actionKey)) {
        await apiClient.post("/admin/live-trading/control-layer/system-health", {
          action: actionDialog.actionKey,
          reason: actionDialog.reason,
          confirmation_phrase: actionDialog.phrase,
          scan_latency_ms: Number(latencyForm.scan_latency_ms || 0),
          decision_latency_ms: Number(latencyForm.decision_latency_ms || 0),
          execution_latency_ms: Number(latencyForm.execution_latency_ms || 0),
        });
      }

      if (actionDialog.actionKey === "risk_update") {
        await apiClient.post("/admin/live-trading/control-layer/risk-controls", {
          max_loss_pct: Number(riskForm.max_loss_pct || 0),
          account_exposure_pct: Number(riskForm.account_exposure_pct || 0),
          symbol_exposure_pct: Number(riskForm.symbol_exposure_pct || 0),
          reason: actionDialog.reason,
          confirmation_phrase: actionDialog.phrase,
        });
      }

      if (actionDialog.actionKey === "risk_override") {
        await apiClient.post("/admin/live-trading/control-layer/risk-override", {
          decision: riskOverrideForm.decision,
          ttl_minutes: Number(riskOverrideForm.ttl_minutes || 30),
          reason: actionDialog.reason,
          confirmation_phrase: actionDialog.phrase,
        });
      }

      if (actionDialog.actionKey === "snapshot") {
        await apiClient.post("/admin/live-trading/control-layer/trading-performance/snapshot", {
          reason: actionDialog.reason,
          confirmation_phrase: actionDialog.phrase,
        });
      }

      if (actionDialog.actionKey === "reset_daily") {
        await apiClient.post("/admin/live-trading/control-layer/trading-performance/reset-daily", {
          reason: actionDialog.reason,
          confirmation_phrase: actionDialog.phrase,
        });
      }

      if (actionDialog.actionKey === "retry_orders") {
        await apiClient.post("/admin/live-trading/control-layer/execution-quality/retry", {
          ids: selectedFailedIds,
          reason: actionDialog.reason,
          confirmation_phrase: actionDialog.phrase,
        });
        setSelectedFailedIds([]);
      }

      if (actionDialog.actionKey === "alert_action") {
        await apiClient.post(`/admin/live-trading/control-layer/critical-alerts/${actionDialog.context.alertId}/action`, {
          action: actionDialog.context.alertAction,
          reason: actionDialog.reason,
          fix_action: actionDialog.context.fixAction,
          mute_minutes: Number(actionDialog.context.muteMinutes || 30),
        });
      }

      toast.success("Aksiyon tamamlandı");
      setActionDialog((prev) => ({ ...prev, open: false }));
      await load();
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : JSON.stringify(detail || {}));
    }
  };

  const alertPanelClass = useMemo(() => {
    const criticalCount = criticalAlerts.filter((item) => String(item.severity || "").toUpperCase() === "CRITICAL").length;
    if (criticalCount > 0) return "border-red-700 bg-red-950/20";
    return "border-emerald-700 bg-emerald-950/20";
  }, [criticalAlerts]);

  return (
    <section className="space-y-4" data-testid="admin-live-trading-dashboard-page">
      <header className="border border-emerald-800/60 bg-emerald-950/20 p-4" data-testid="admin-live-trading-dashboard-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-emerald-300" data-testid="admin-live-trading-dashboard-title">Live Dashboard Control Hub</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="admin-live-trading-dashboard-description">
          Aktif kontrol + müdahale + izlenebilirlik katmanı. role={user?.role || "unknown"}
        </p>
      </header>

      <div className="flex flex-wrap items-end gap-2" data-testid="admin-live-trading-dashboard-toolbar">
        <label className="space-y-1" data-testid="admin-live-trading-dashboard-window-field">
          <span className="text-xs text-slate-400">Summary Window</span>
          <select
            value={windowSize}
            onChange={(event) => setWindowSize(event.target.value)}
            className="h-10 rounded border border-slate-700 bg-black px-2 text-sm"
            data-testid="admin-live-trading-dashboard-window-select"
          >
            {WINDOW_OPTIONS.map((option) => (
              <option key={option} value={option} data-testid={`admin-live-trading-dashboard-window-option-${option}`}>{option}</option>
            ))}
          </select>
        </label>

        <Button type="button" variant="outline" onClick={load} data-testid="admin-live-trading-dashboard-refresh-button">Yenile</Button>
        <Button type="button" variant="outline" onClick={() => setAutoRefresh((prev) => !prev)} data-testid="admin-live-trading-dashboard-auto-refresh-toggle-button">
          auto-refresh: {autoRefresh ? "ON" : "OFF"}
        </Button>
        <p className="text-xs text-slate-400" data-testid="admin-live-trading-dashboard-server-clock">clock: {controlState?.server_clock || "-"}</p>
      </div>

      <div className="rounded border border-cyan-700/60 bg-slate-900 p-4" data-testid="live-control-execution-mode-panel">
        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="live-control-execution-mode-header">
          <p className="text-xs uppercase tracking-widest text-cyan-300" data-testid="live-control-execution-mode-title">Execution Mode (P0)</p>
          <p className="text-xs text-slate-300" data-testid="live-control-execution-mode-current">current_mode: {controlState?.execution_mode || "-"}</p>
        </div>
        <div className="mt-3 flex flex-wrap gap-2" data-testid="live-control-execution-mode-actions">
          {(["LIVE", "PAPER", "MOCK"]).map((mode) => (
            <Button
              key={mode}
              onClick={() =>
                openActionDialog({
                  actionKey: `mode_${mode.toLowerCase()}`,
                  title: `Switch Mode -> ${mode}`,
                  expectedPhrase: MODE_PHRASES[mode],
                  reason: `switch_to_${mode.toLowerCase()}`,
                })
              }
              disabled={!isManager}
              data-testid={`live-control-execution-mode-switch-${mode.toLowerCase()}-button`}
            >
              {mode}
            </Button>
          ))}
        </div>
        <div className="mt-2 space-y-1" data-testid="live-control-execution-mode-snapshots-list">
          {(controlState?.execution_mode_snapshots || []).slice(-3).map((item, idx) => (
            <p key={`${item.captured_at}-${idx}`} className="text-xs text-slate-400" data-testid={`live-control-execution-mode-snapshot-${idx}`}>
              {item.captured_at} · {item.previous_mode} → {item.mode}
            </p>
          ))}
        </div>
      </div>

      <div className="rounded border border-red-700/60 bg-red-950/20 p-4" data-testid="live-control-system-health-panel">
        <p className="text-xs uppercase tracking-widest text-red-300" data-testid="live-control-system-health-title">Risk & Kill Controls (P0)</p>
        <div className="mt-3 flex flex-wrap gap-2" data-testid="live-control-system-health-actions">
          <Button disabled={!isManager} onClick={() => openActionDialog({ actionKey: "kill_on", title: "Kill Switch ON", expectedPhrase: ACTION_PHRASES.kill_on, reason: "kill_switch_on" })} data-testid="live-control-kill-switch-on-button">Kill ON</Button>
          <Button variant="outline" disabled={!isManager} onClick={() => openActionDialog({ actionKey: "kill_off", title: "Kill Switch OFF", expectedPhrase: ACTION_PHRASES.kill_off, reason: "kill_switch_off" })} data-testid="live-control-kill-switch-off-button">Kill OFF</Button>
          <Button variant="outline" disabled={!isManager} onClick={() => openActionDialog({ actionKey: "fallback_on", title: "Fallback ON", expectedPhrase: ACTION_PHRASES.fallback_on, reason: "fallback_on" })} data-testid="live-control-fallback-on-button">Fallback ON</Button>
          <Button variant="outline" disabled={!isManager} onClick={() => openActionDialog({ actionKey: "fallback_off", title: "Fallback OFF", expectedPhrase: ACTION_PHRASES.fallback_off, reason: "fallback_off" })} data-testid="live-control-fallback-off-button">Fallback OFF</Button>
        </div>

        <div className="mt-3 grid gap-2 md:grid-cols-4" data-testid="live-control-latency-threshold-grid">
          <Input value={latencyForm.scan_latency_ms} onChange={(e) => setLatencyForm((p) => ({ ...p, scan_latency_ms: e.target.value }))} data-testid="live-control-latency-scan-input" placeholder="scan latency ms" />
          <Input value={latencyForm.decision_latency_ms} onChange={(e) => setLatencyForm((p) => ({ ...p, decision_latency_ms: e.target.value }))} data-testid="live-control-latency-decision-input" placeholder="decision latency ms" />
          <Input value={latencyForm.execution_latency_ms} onChange={(e) => setLatencyForm((p) => ({ ...p, execution_latency_ms: e.target.value }))} data-testid="live-control-latency-execution-input" placeholder="execution latency ms" />
          <Button disabled={!isManager} onClick={() => openActionDialog({ actionKey: "set_latency", title: "Set Latency Threshold", expectedPhrase: ACTION_PHRASES.set_latency, reason: "update_latency_threshold" })} data-testid="live-control-latency-apply-button">Threshold Uygula</Button>
        </div>
      </div>

      <div className={`rounded border p-4 ${alertPanelClass}`} data-testid="live-control-critical-alerts-panel">
        <p className="text-xs uppercase tracking-widest" data-testid="live-control-critical-alerts-title">Critical Alerts → Action System (P0)</p>
        <div className="mt-2 space-y-2" data-testid="live-control-critical-alerts-list">
          {criticalAlerts.length === 0 && <p className="text-sm" data-testid="live-control-critical-alerts-empty">aktif alert yok</p>}
          {criticalAlerts.map((item, idx) => (
            <article key={item.id} className="rounded border border-slate-700 bg-black/20 p-3" data-testid={`live-control-critical-alert-item-${idx}`}>
              <p className="text-sm font-semibold" data-testid={`live-control-critical-alert-head-${idx}`}>{item.alert_type} · {item.severity} · {item.status}</p>
              <p className="mt-1 text-xs text-slate-300" data-testid={`live-control-critical-alert-msg-${idx}`}>{item.message}</p>
              <p className="mt-1 text-xs text-slate-400" data-testid={`live-control-critical-alert-root-${idx}`}>root={item.root_cause_code || "-"}</p>
              <div className="mt-2 flex flex-wrap gap-2" data-testid={`live-control-critical-alert-actions-${idx}`}>
                <Button size="sm" variant="outline" onClick={() => openActionDialog({ actionKey: "alert_action", title: "Resolve Alert", expectedPhrase: "ACK SELECTED ALERTS", reason: "resolve_alert", context: { alertId: item.id, alertAction: "resolve" } })} data-testid={`live-control-alert-resolve-${idx}`}>Resolve</Button>
                <Button size="sm" variant="outline" onClick={() => openActionDialog({ actionKey: "alert_action", title: "Mute Alert", expectedPhrase: "ACK SELECTED ALERTS", reason: "mute_alert", context: { alertId: item.id, alertAction: "mute", muteMinutes: 30 } })} data-testid={`live-control-alert-mute-${idx}`}>Mute</Button>
                <Button size="sm" variant="outline" disabled={!isManager} onClick={() => openActionDialog({ actionKey: "alert_action", title: "Escalate Alert", expectedPhrase: "ACK SELECTED ALERTS", reason: "escalate_alert", context: { alertId: item.id, alertAction: "escalate" } })} data-testid={`live-control-alert-escalate-${idx}`}>Escalate</Button>
                <Select
                  onValueChange={(value) =>
                    openActionDialog({
                      actionKey: "alert_action",
                      title: `Fix Action: ${value}`,
                      expectedPhrase: "ACK SELECTED ALERTS",
                      reason: `fix_action_${value}`,
                      context: { alertId: item.id, alertAction: "fix_action", fixAction: value },
                    })
                  }
                >
                  <SelectTrigger className="h-8 w-[220px]" data-testid={`live-control-alert-fix-select-${idx}`}>
                    <SelectValue placeholder="Fix Action" />
                  </SelectTrigger>
                  <SelectContent>
                    {FIX_ACTIONS.map((action) => (
                      <SelectItem key={action} value={action} data-testid={`live-control-alert-fix-option-${idx}-${action}`}>{action}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="mt-2 max-h-24 space-y-1 overflow-auto" data-testid={`live-control-alert-history-${idx}`}>
                {(item.history || []).slice(0, 4).map((row, hIdx) => (
                  <p key={`${row.id}-${hIdx}`} className="text-[11px] text-slate-400" data-testid={`live-control-alert-history-item-${idx}-${hIdx}`}>
                    {row.created_at} · {row.action}
                  </p>
                ))}
              </div>
            </article>
          ))}
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-2" data-testid="live-control-performance-and-reliability-grid">
        <article className="rounded border border-slate-700 bg-slate-900 p-4" data-testid="live-control-performance-panel">
          <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="live-control-performance-title">Trading Performance Control (P1)</p>
          <div className="mt-2 flex flex-wrap gap-2" data-testid="live-control-performance-actions">
            <Button variant="outline" disabled={!isManager} onClick={() => openActionDialog({ actionKey: "snapshot", title: "Capture Snapshot", expectedPhrase: ACTION_PHRASES.snapshot, reason: "manual_snapshot" })} data-testid="live-control-capture-snapshot-button">Snapshot</Button>
            <Button variant="outline" disabled={!isManager} onClick={() => openActionDialog({ actionKey: "reset_daily", title: "Reset Daily Metrics", expectedPhrase: ACTION_PHRASES.reset_daily, reason: "daily_reset" })} data-testid="live-control-reset-daily-button">Daily Reset</Button>
          </div>

          <div className="mt-3 grid gap-2 sm:grid-cols-2" data-testid="live-control-performance-kpis">
            <MetricCard title="trades_count_today" value={summary?.trading_performance?.trades_count_today ?? "-"} testId="live-control-perf-trades" />
            <MetricCard title="pnl_today_usdt" value={summary?.trading_performance?.pnl_today_usdt ?? "-"} testId="live-control-perf-pnl" />
            <MetricCard title="open_positions" value={openPositions.length} testId="live-control-perf-open-positions" />
            <MetricCard title="execution_quality" value={executionQuality?.execution_quality_score ?? "-"} testId="live-control-perf-quality" />
          </div>

          <div className="mt-3 max-h-44 space-y-2 overflow-auto" data-testid="live-control-open-positions-list">
            {openPositions.slice(0, 12).map((item, idx) => (
              <article key={item.id} className="rounded border border-slate-700 p-2 text-xs" data-testid={`live-control-open-position-item-${idx}`}>
                {item.symbol} · {item.side} · qty={item.quantity} · entry={item.entry_price} · upnl={item.unrealized_pnl}
              </article>
            ))}
            {openPositions.length === 0 && <p className="text-xs text-slate-500" data-testid="live-control-open-positions-empty">open position yok</p>}
          </div>
        </article>

        <article className="rounded border border-slate-700 bg-slate-900 p-4" data-testid="live-control-execution-quality-panel">
          <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="live-control-execution-quality-title">Execution Reliability (P1)</p>
          <div className="mt-2 flex flex-wrap items-center gap-2" data-testid="live-control-retry-actions">
            <Button
              onClick={() =>
                openActionDialog({
                  actionKey: "retry_orders",
                  title: "Retry Failed Orders",
                  expectedPhrase: ACTION_PHRASES.retry_orders,
                  reason: "manual_retry_failed_orders",
                })
              }
              data-testid="live-control-retry-selected-button"
            >
              Retry ({selectedFailedIds.length})
            </Button>
          </div>

          <div className="mt-3 max-h-52 space-y-2 overflow-auto" data-testid="live-control-failed-orders-list">
            {failedOrders.slice(0, 40).map((item, idx) => (
              <article key={item.id} className="rounded border border-slate-700 p-2 text-xs" data-testid={`live-control-failed-order-item-${idx}`}>
                <label className="flex items-start gap-2" data-testid={`live-control-failed-order-select-wrap-${idx}`}>
                  <input
                    type="checkbox"
                    checked={selectedFailedIds.includes(item.id)}
                    onChange={(e) =>
                      setSelectedFailedIds((prev) =>
                        e.target.checked ? [...prev, item.id] : prev.filter((id) => id !== item.id)
                      )
                    }
                    data-testid={`live-control-failed-order-select-${idx}`}
                  />
                  <span data-testid={`live-control-failed-order-text-${idx}`}>
                    {item.event_type} · {item.entity_id} · status={item.status} · retry={item.retry_count}/{item.max_retry}
                    <br />
                    {item.error_message}
                  </span>
                </label>
              </article>
            ))}
            {failedOrders.length === 0 && <p className="text-xs text-slate-500" data-testid="live-control-failed-orders-empty">failed order yok</p>}
          </div>
        </article>
      </div>

      <div className="rounded border border-amber-700/60 bg-amber-950/20 p-4" data-testid="live-control-risk-engine-panel">
        <p className="text-xs uppercase tracking-widest text-amber-300" data-testid="live-control-risk-engine-title">Risk Engine Control (P0)</p>
        <div className="mt-3 grid gap-2 md:grid-cols-4" data-testid="live-control-risk-form-grid">
          <Input value={riskForm.max_loss_pct} onChange={(e) => setRiskForm((p) => ({ ...p, max_loss_pct: e.target.value }))} data-testid="live-control-risk-max-loss-input" placeholder="max loss %" />
          <Input value={riskForm.account_exposure_pct} onChange={(e) => setRiskForm((p) => ({ ...p, account_exposure_pct: e.target.value }))} data-testid="live-control-risk-account-exposure-input" placeholder="account exposure %" />
          <Input value={riskForm.symbol_exposure_pct} onChange={(e) => setRiskForm((p) => ({ ...p, symbol_exposure_pct: e.target.value }))} data-testid="live-control-risk-symbol-exposure-input" placeholder="symbol exposure %" />
          <Button disabled={!isManager} onClick={() => openActionDialog({ actionKey: "risk_update", title: "Update Risk Controls", expectedPhrase: ACTION_PHRASES.risk_update, reason: "risk_control_update" })} data-testid="live-control-risk-update-button">Risk Güncelle</Button>
        </div>

        <div className="mt-3 grid gap-2 md:grid-cols-4" data-testid="live-control-risk-override-grid">
          <Select value={riskOverrideForm.decision} onValueChange={(value) => setRiskOverrideForm((p) => ({ ...p, decision: value }))}>
            <SelectTrigger data-testid="live-control-risk-override-decision-select">
              <SelectValue placeholder="override decision" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="force_allow" data-testid="live-control-risk-override-option-force-allow">force_allow</SelectItem>
              <SelectItem value="force_reject" data-testid="live-control-risk-override-option-force-reject">force_reject</SelectItem>
            </SelectContent>
          </Select>
          <Input value={riskOverrideForm.ttl_minutes} onChange={(e) => setRiskOverrideForm((p) => ({ ...p, ttl_minutes: e.target.value }))} data-testid="live-control-risk-override-ttl-input" placeholder="ttl minutes" />
          <Button disabled={!isManager} onClick={() => openActionDialog({ actionKey: "risk_override", title: "Apply Risk Override", expectedPhrase: ACTION_PHRASES.risk_override, reason: "risk_override" })} data-testid="live-control-risk-override-button">Risk Override</Button>
          <p className="text-xs text-slate-300" data-testid="live-control-risk-override-current">active_override: {String(controlState?.risk_override?.active || false)}</p>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-4" data-testid="admin-live-trading-dashboard-kpi-grid">
        <MetricCard title="execution_mode" value={controlState?.execution_mode || summary?.system_health?.execution_mode || "-"} testId="live-dashboard-kpi-execution-mode" />
        <MetricCard title="execution_quality_score" value={summary?.system_health?.execution_quality_score ?? "-"} testId="live-dashboard-kpi-execution-quality-score" />
        <MetricCard title="retry_queue_count" value={controlState?.retry_queue_count ?? "-"} testId="live-dashboard-kpi-retry-queue-count" />
        <MetricCard title="fallback_rate" value={scannerHealth?.fallback_rate ?? "-"} testId="live-dashboard-kpi-fallback-rate" />
      </div>

      <p className="text-xs text-slate-500" data-testid="live-dashboard-loading-state">loading={String(loading)}</p>

      <Dialog open={actionDialog.open} onOpenChange={(open) => setActionDialog((prev) => ({ ...prev, open }))}>
        <DialogContent className="max-w-2xl border border-amber-700 bg-slate-950" data-testid="live-control-action-confirm-modal">
          <DialogHeader>
            <DialogTitle data-testid="live-control-action-confirm-title">{actionDialog.title}</DialogTitle>
            <DialogDescription data-testid="live-control-action-confirm-description">
              Double confirm zorunlu. reason + phrase olmadan aksiyon çalışmaz.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3" data-testid="live-control-action-confirm-form">
            <div data-testid="live-control-action-confirm-reason-field">
              <p className="text-xs text-slate-400">Reason</p>
              <Textarea value={actionDialog.reason} onChange={(e) => setActionDialog((p) => ({ ...p, reason: e.target.value }))} className="mt-1 bg-slate-900" data-testid="live-control-action-confirm-reason-input" />
            </div>
            <div data-testid="live-control-action-confirm-phrase-field">
              <p className="text-xs text-slate-400">Confirm phrase: <span data-testid="live-control-action-confirm-expected-phrase">{actionDialog.expectedPhrase}</span></p>
              <Input value={actionDialog.phrase} onChange={(e) => setActionDialog((p) => ({ ...p, phrase: e.target.value }))} className="mt-1 bg-slate-900" data-testid="live-control-action-confirm-phrase-input" />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setActionDialog((prev) => ({ ...prev, open: false }))} data-testid="live-control-action-confirm-cancel-button">Vazgeç</Button>
            <Button onClick={runAction} data-testid="live-control-action-confirm-submit-button">Onayla ve Çalıştır</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
};
