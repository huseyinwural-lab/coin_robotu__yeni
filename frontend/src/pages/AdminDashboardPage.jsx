import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
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
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";

const DRILLDOWN_METRICS = [
  { key: "open_alerts", label: "open_alerts", route: "/admin/system-alerts" },
  { key: "pending_approvals", label: "pending_approvals", route: "/admin/user-approvals" },
  { key: "stale_pending_approvals", label: "stale_pending_approvals", route: "/admin/user-approvals" },
  { key: "rejected_intents", label: "rejected_intents", route: "/admin/execution-queue" },
  { key: "timeout_rejected_intents", label: "timeout_rejected_intents", route: "/admin/runtime/recovery" },
  { key: "kill_switch_active", label: "kill_switch_active", route: "/admin/phase4-live" },
];

const KPI_CONFIG = [
  { key: "users", label: "Kullanıcı", route: "/admin/users/customers" },
  { key: "running_bots", label: "Running Bot", route: "/admin/strategies" },
  { key: "risk_policies", label: "Risk Policy", route: "/admin/risk-orchestrator" },
  { key: "strategy_templates", label: "Template", route: "/admin/strategies" },
  { key: "websocket_status", label: "WS Status", route: "/admin/monitoring" },
  { key: "signals_5m", label: "Signal / 5m", route: "/admin/anomaly-timeline" },
  { key: "paper_trades_5m", label: "Paper Trade / 5m", route: "/admin/live-trading-dashboard" },
  { key: "open_positions", label: "Open Positions", route: "/admin/positions-monitor" },
  { key: "critical_audits", label: "Critical Audit", route: "/admin/audit-logs" },
];

const QUICK_ACTIONS = [
  { key: "go-approvals", label: "Go to approvals", route: "/admin/user-approvals" },
  { key: "go-intents", label: "Go to intents", route: "/admin/execution-queue" },
  { key: "go-recovery", label: "Go to runtime recovery", route: "/admin/runtime/recovery" },
  { key: "go-alerts", label: "Go to system alerts", route: "/admin/system-alerts" },
  { key: "go-audit", label: "Go to audit logs", route: "/admin/audit-logs" },
];

const ACTION_CONFIG = {
  kill_on: {
    title: "Kill Switch Aktif Et",
    description: "Trading akışını global olarak durdurur.",
    expectedPhrase: "DISABLE TRADING",
  },
  kill_off: {
    title: "Kill Switch Pasif Et",
    description: "Trading akışını yeniden aktive eder.",
    expectedPhrase: "ENABLE TRADING",
  },
  restart_services: {
    title: "Restart Services",
    description: "Backend/frontend servislerini restart kuyruğuna alır.",
    expectedPhrase: "RESTART SERVICES",
  },
  clear_all_alerts: {
    title: "Clear All Alerts",
    description: "Seçili status kapsamındaki tüm alertleri ACK yapar.",
    expectedPhrase: "CLEAR ALL ALERTS",
  },
  bulk_ack_alerts: {
    title: "Bulk Ack Alerts",
    description: "Seçtiğin alertleri tek işlemde ACK yapar.",
    expectedPhrase: "ACK SELECTED ALERTS",
  },
  auto_close_run: {
    title: "Auto-Close Run Now",
    description: "Action center auto-close adımlarını hemen tetikler.",
    expectedPhrase: "RUN AUTO CLOSE",
  },
};

const formatTrend = (currentValue, previousValue) => {
  const currentNumber = Number(currentValue);
  const previousNumber = Number(previousValue);
  if (!Number.isFinite(currentNumber) || !Number.isFinite(previousNumber)) {
    return { direction: "neutral", text: "→" };
  }
  if (currentNumber > previousNumber) {
    return { direction: "up", text: `↑ +${currentNumber - previousNumber}` };
  }
  if (currentNumber < previousNumber) {
    return { direction: "down", text: `↓ ${currentNumber - previousNumber}` };
  }
  return { direction: "neutral", text: "→ 0" };
};

const kpiThreshold = (key, value) => {
  if (key === "websocket_status") {
    if (String(value || "").toLowerCase() !== "connected") {
      return { level: "critical", label: "WS disconnected" };
    }
    return { level: "normal", label: "WS healthy" };
  }
  if (key === "critical_audits" && Number(value) > 0) {
    return { level: "critical", label: "Critical audit var" };
  }
  if (key === "signals_5m" && Number(value) === 0) {
    return { level: "warning", label: "Signal akışı zayıf" };
  }
  return { level: "normal", label: "Threshold normal" };
};

export const AdminDashboardPage = () => {
  const navigate = useNavigate();
  const { user } = useAuth();

  const [summary, setSummary] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [previousMetrics, setPreviousMetrics] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [lastUpdatedAt, setLastUpdatedAt] = useState("");
  const [alertFilters, setAlertFilters] = useState({
    status_filter: "open",
    severity: "all",
    alert_type: "all",
    source: "",
    window_hours: "24",
  });
  const [selectedAlertIds, setSelectedAlertIds] = useState([]);
  const [globalQuery, setGlobalQuery] = useState("");
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);
  const [actionCenterSummary, setActionCenterSummary] = useState(null);
  const [closeResult, setCloseResult] = useState(null);
  const [killSwitchState, setKillSwitchState] = useState(null);
  const [incidentHistory, setIncidentHistory] = useState({ audit_events: [], recent_alerts: [] });
  const [criticalDialogState, setCriticalDialogState] = useState({
    open: false,
    actionKey: "",
    reason: "",
    phrase: "",
    restartTargets: { backend: true, frontend: true },
  });
  const [alertDetail, setAlertDetail] = useState(null);
  const [isAlertDetailOpen, setIsAlertDetailOpen] = useState(false);
  const [isCloseResultOpen, setIsCloseResultOpen] = useState(false);
  const [drilldown, setDrilldown] = useState({ open: false, metricKey: "", route: "" });

  const isManagerRole = ["super_admin", "admin"].includes(String(user?.role || ""));
  const killSwitchActive = useMemo(() => {
    if (killSwitchState) {
      return !Boolean(killSwitchState.trading_enabled);
    }
    return Boolean(actionCenterSummary?.kill_switch_active);
  }, [killSwitchState, actionCenterSummary]);

  const filteredAlerts = useMemo(() => {
    const needle = globalQuery.trim().toLowerCase();
    if (!needle) {
      return alerts;
    }
    return alerts.filter((alert) => {
      const source = String(alert?.source || "").toLowerCase();
      const message = String(alert?.message || "").toLowerCase();
      const type = String(alert?.alert_type || "").toLowerCase();
      const rootCause = String(alert?.root_cause_code || "").toLowerCase();
      return source.includes(needle) || message.includes(needle) || type.includes(needle) || rootCause.includes(needle);
    });
  }, [alerts, globalQuery]);

  const quickActions = useMemo(() => {
    const needle = globalQuery.trim().toLowerCase();
    if (!needle) {
      return QUICK_ACTIONS;
    }
    return QUICK_ACTIONS.filter((item) => item.label.toLowerCase().includes(needle));
  }, [globalQuery]);

  const drilldownAlertRows = useMemo(() => {
    if (drilldown.metricKey === "open_alerts") {
      return filteredAlerts.slice(0, 10);
    }
    return [];
  }, [drilldown.metricKey, filteredAlerts]);

  const alertTypeOptions = useMemo(() => {
    const set = new Set();
    for (const item of alerts) {
      if (item?.alert_type) {
        set.add(item.alert_type);
      }
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b));
  }, [alerts]);

  const allFilteredSelected = filteredAlerts.length > 0 && filteredAlerts.every((item) => selectedAlertIds.includes(item.id));

  const loadDashboard = useCallback(async () => {
    setIsLoading(true);
    setLoadError("");

    try {
      const [summaryResponse, actionSummaryResponse, killSwitchResponse, incidentResponse, alertsResponse] = await Promise.all([
        apiClient.get("/dashboard/summary"),
        apiClient.get("/admin/action-center/summary"),
        apiClient.get("/admin/kill-switch"),
        apiClient.get("/admin/action-center/incident-history", { params: { limit: 25 } }),
        apiClient.get("/admin/action-center/alerts", {
          params: {
            status_filter: alertFilters.status_filter,
            severity: alertFilters.severity !== "all" ? alertFilters.severity : undefined,
            alert_type: alertFilters.alert_type !== "all" ? alertFilters.alert_type : undefined,
            source: alertFilters.source || undefined,
            window_hours: Number(alertFilters.window_hours || 24),
            limit: 250,
          },
        }),
      ]);

      const summaryPayload = summaryResponse?.data || null;
      setSummary((prevSummary) => {
        if (prevSummary?.metrics) {
          setPreviousMetrics(prevSummary.metrics);
        }
        return summaryPayload;
      });
      setActionCenterSummary(actionSummaryResponse?.data || null);
      setKillSwitchState(killSwitchResponse?.data || null);
      setIncidentHistory(incidentResponse?.data || { audit_events: [], recent_alerts: [] });
      setAlerts(alertsResponse?.data?.items || []);
      setLastUpdatedAt(new Date().toISOString());
    } catch (error) {
      const message = error?.response?.data?.detail || "Admin dashboard verisi yüklenemedi";
      setLoadError(typeof message === "string" ? message : "Admin dashboard verisi yüklenemedi");
      toast.error(typeof message === "string" ? message : "Admin dashboard verisi yüklenemedi");
    } finally {
      setIsLoading(false);
    }
  }, [alertFilters]);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  useEffect(() => {
    if (!autoRefreshEnabled) {
      return undefined;
    }
    const timer = setInterval(loadDashboard, 30000);
    return () => clearInterval(timer);
  }, [autoRefreshEnabled, loadDashboard]);

  const openCriticalDialog = (actionKey) => {
    const defaultReason = actionKey === "kill_on" ? "dashboard_kill_switch_activate" : "dashboard_manual_operation";
    setCriticalDialogState({
      open: true,
      actionKey,
      reason: defaultReason,
      phrase: "",
      restartTargets: { backend: true, frontend: true },
    });
  };

  const runCriticalAction = async () => {
    const config = ACTION_CONFIG[criticalDialogState.actionKey];
    if (!config) {
      return;
    }
    if (!isManagerRole) {
      toast.error("Bu aksiyon sadece super_admin + admin için açık");
      return;
    }

    if (criticalDialogState.phrase.trim().toUpperCase() !== config.expectedPhrase) {
      toast.error(`Onay ifadesi hatalı. Beklenen: ${config.expectedPhrase}`);
      return;
    }

    if (!criticalDialogState.reason || criticalDialogState.reason.trim().length < 5) {
      toast.error("Neden alanı zorunlu (min 5 karakter)");
      return;
    }

    try {
      if (criticalDialogState.actionKey === "kill_on") {
        await apiClient.post("/admin/action-center/global-kill-switch/toggle", {
          active: true,
          reason: criticalDialogState.reason,
          confirmation_phrase: criticalDialogState.phrase,
          requested_by: user?.email,
        });
      }
      if (criticalDialogState.actionKey === "kill_off") {
        await apiClient.post("/admin/action-center/global-kill-switch/toggle", {
          active: false,
          reason: criticalDialogState.reason,
          confirmation_phrase: criticalDialogState.phrase,
          requested_by: user?.email,
        });
      }
      if (criticalDialogState.actionKey === "restart_services") {
        const targets = [];
        if (criticalDialogState.restartTargets.backend) targets.push("backend");
        if (criticalDialogState.restartTargets.frontend) targets.push("frontend");
        await apiClient.post("/admin/action-center/restart-services", {
          targets,
          reason: criticalDialogState.reason,
          confirmation_phrase: criticalDialogState.phrase,
        });
      }
      if (criticalDialogState.actionKey === "clear_all_alerts") {
        await apiClient.post("/admin/action-center/alerts/clear-all", {
          status_filter: alertFilters.status_filter,
          reason: criticalDialogState.reason,
          confirmation_phrase: criticalDialogState.phrase,
        });
      }
      if (criticalDialogState.actionKey === "bulk_ack_alerts") {
        await apiClient.post("/admin/action-center/alerts/bulk-ack", {
          ids: selectedAlertIds,
          reason: criticalDialogState.reason,
        });
        setSelectedAlertIds([]);
      }
      if (criticalDialogState.actionKey === "auto_close_run") {
        const { data } = await apiClient.post("/admin/action-center/close-next-actions", {
          ack_open_alerts: true,
          reject_stale_approvals: true,
          stale_days: 30,
          retry_timeout_rejections: true,
          clear_kill_switch: false,
        });
        setCloseResult(data || null);
        setIsCloseResultOpen(true);
      }

      toast.success(`${config.title} tamamlandı`);
      setCriticalDialogState((prev) => ({ ...prev, open: false }));
      await loadDashboard();
    } catch (error) {
      const message = error?.response?.data?.detail;
      const prettyMessage = typeof message === "string" ? message : JSON.stringify(message || {});
      toast.error(prettyMessage || `${config.title} başarısız`);
    }
  };

  const runCloseNextActions = async () => {
    openCriticalDialog("auto_close_run");
  };

  const toggleAlertSelection = (alertId) => {
    setSelectedAlertIds((prev) => (prev.includes(alertId) ? prev.filter((id) => id !== alertId) : [...prev, alertId]));
  };

  const toggleSelectAllFiltered = () => {
    if (allFilteredSelected) {
      const filteredIds = new Set(filteredAlerts.map((item) => item.id));
      setSelectedAlertIds((prev) => prev.filter((id) => !filteredIds.has(id)));
      return;
    }
    setSelectedAlertIds((prev) => {
      const next = new Set(prev);
      for (const item of filteredAlerts) {
        next.add(item.id);
      }
      return Array.from(next);
    });
  };

  const ackSingleAlert = async (alertId) => {
    try {
      await apiClient.post("/admin/action-center/alerts/bulk-ack", {
        ids: [alertId],
        reason: "single_row_ack",
      });
      toast.success("Alert ack edildi");
      await loadDashboard();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Alert ack edilemedi");
    }
  };

  const openAlertDetail = async (alertId) => {
    try {
      const { data } = await apiClient.get(`/admin/action-center/alerts/${alertId}/detail`);
      setAlertDetail(data || null);
      setIsAlertDetailOpen(true);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Alert detayı alınamadı");
    }
  };

  const openDrilldown = (metric) => {
    setDrilldown({ open: true, metricKey: metric.key, route: metric.route });
  };

  if (isLoading) {
    return <LoadingSkeleton rows={8} testId="admin-dashboard-loading-skeleton" />;
  }

  if (!summary) {
    return (
      <section className="space-y-4" data-testid="admin-dashboard-broken-state">
        <div className="border border-rose-500/40 bg-rose-900/20 p-4" data-testid="admin-dashboard-broken-alert">
          <p className="text-sm font-semibold text-rose-200" data-testid="admin-dashboard-broken-title">Dashboard verisi alınamadı</p>
          <p className="mt-1 text-sm text-rose-100" data-testid="admin-dashboard-broken-message">{loadError || "Servis geçici olarak yanıt vermiyor."}</p>
          <Button className="mt-3" onClick={loadDashboard} data-testid="admin-dashboard-broken-retry-button">Tekrar Dene</Button>
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-4" data-testid="admin-dashboard-page">
      <header className="border border-blue-900 bg-slate-900 p-4" data-testid="admin-dashboard-header">
        <div className="flex flex-wrap items-start justify-between gap-3" data-testid="admin-dashboard-header-row">
          <div data-testid="admin-dashboard-header-left">
            <h2 className="text-4xl font-black uppercase tracking-tight text-blue-300" data-testid="admin-dashboard-title">Admin Dashboard Shell</h2>
            <p className="mt-2 text-sm text-slate-400" data-testid="admin-dashboard-description">Normal alanlar mavi, kritik alanlar kırmızı. Double-confirm pattern aktif.</p>
            <p className="mt-1 text-xs text-slate-500" data-testid="admin-dashboard-last-updated">Son güncelleme: {lastUpdatedAt ? new Date(lastUpdatedAt).toLocaleString() : "-"}</p>
            <p className="mt-1 text-xs text-slate-400" data-testid="admin-dashboard-role-badge">
              role={user?.role || "unknown"} · critical_access={String(isManagerRole)}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2" data-testid="admin-dashboard-header-controls">
            <label className="text-xs text-slate-400" data-testid="admin-dashboard-auto-refresh-toggle-wrapper">
              <input
                type="checkbox"
                checked={autoRefreshEnabled}
                onChange={(event) => setAutoRefreshEnabled(event.target.checked)}
                className="mr-2"
                data-testid="admin-dashboard-auto-refresh-toggle"
              />
              auto-refresh(30s)
            </label>
            <Button variant="outline" onClick={() => navigate("/admin/audit-logs")} data-testid="admin-dashboard-go-audit-logs-button">Audit Logs</Button>
            <Button variant="outline" onClick={runCloseNextActions} data-testid="admin-dashboard-auto-close-run-now-button">Auto-Close Run Now</Button>
            <Button onClick={loadDashboard} data-testid="admin-dashboard-refresh-button">Yenile</Button>
          </div>
        </div>
      </header>

      <div className="border border-cyan-700/60 bg-slate-900 p-4" data-testid="admin-dashboard-global-action-toolbar">
        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="admin-dashboard-global-action-toolbar-header">
          <p className="text-xs uppercase tracking-widest text-cyan-300" data-testid="admin-dashboard-global-action-toolbar-title">Global Action Toolbar</p>
          {!isManagerRole && (
            <p className="text-xs text-amber-300" data-testid="admin-dashboard-global-action-toolbar-lock">LOCKED: kritik aksiyonlar sadece super_admin + admin</p>
          )}
        </div>
        <div className="mt-3 flex flex-wrap gap-2" data-testid="admin-dashboard-global-action-toolbar-actions">
          <Button
            className="bg-red-700 text-white hover:bg-red-800"
            onClick={() => openCriticalDialog("kill_on")}
            disabled={!isManagerRole || killSwitchActive}
            data-testid="admin-dashboard-kill-switch-enable-button"
          >
            Kill Switch Aktif Et
          </Button>
          <Button
            variant="outline"
            onClick={() => openCriticalDialog("kill_off")}
            disabled={!isManagerRole || !killSwitchActive}
            data-testid="admin-dashboard-kill-switch-disable-button"
          >
            Kill Switch Pasif Et
          </Button>
          <Button
            variant="outline"
            onClick={() => openCriticalDialog("restart_services")}
            disabled={!isManagerRole}
            data-testid="admin-dashboard-restart-services-button"
          >
            Restart Services
          </Button>
          <Button
            variant="outline"
            onClick={() => openCriticalDialog("clear_all_alerts")}
            disabled={!isManagerRole}
            data-testid="admin-dashboard-clear-all-alerts-button"
          >
            Clear All Alerts
          </Button>
        </div>
        <div className="mt-2 grid gap-1 text-xs text-slate-300 md:grid-cols-3" data-testid="admin-dashboard-global-action-toolbar-status-grid">
          <p data-testid="admin-dashboard-kill-switch-status">kill_switch_active: {String(killSwitchActive)}</p>
          <p data-testid="admin-dashboard-trading-enabled-status">trading_enabled: {String(killSwitchState?.trading_enabled ?? false)}</p>
          <p data-testid="admin-dashboard-kill-switch-reason-code">reason_code: {killSwitchState?.reason_code || "-"}</p>
        </div>
      </div>

      <div className="border border-indigo-700/50 bg-slate-900 p-4" data-testid="admin-dashboard-quick-action-search-panel">
        <p className="text-xs uppercase tracking-widest text-indigo-300" data-testid="admin-dashboard-quick-action-search-title">Search / Global Quick Action Bar</p>
        <Input
          value={globalQuery}
          onChange={(event) => setGlobalQuery(event.target.value)}
          placeholder="search alerts, metrics, quick actions"
          className="mt-2 bg-slate-950"
          data-testid="admin-dashboard-global-search-input"
        />
        <div className="mt-2 flex flex-wrap gap-2" data-testid="admin-dashboard-quick-action-list">
          {quickActions.map((item) => (
            <Button
              key={item.key}
              variant="outline"
              className="text-xs"
              onClick={() => navigate(item.route)}
              data-testid={`admin-dashboard-quick-action-${item.key}`}
            >
              {item.label}
            </Button>
          ))}
          {quickActions.length === 0 && (
            <p className="text-xs text-slate-500" data-testid="admin-dashboard-quick-action-empty">Eşleşen hızlı aksiyon yok.</p>
          )}
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2" data-testid="admin-dashboard-action-center-grid">
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-dashboard-action-center-summary-card">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-dashboard-action-center-summary-title">Action Center Summary</p>
          <div className="mt-2 grid gap-2" data-testid="admin-dashboard-action-center-summary-content">
            {DRILLDOWN_METRICS.map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => openDrilldown(item)}
                className="flex items-center justify-between border border-slate-700 px-2 py-2 text-left text-xs hover:border-slate-500"
                data-testid={`admin-dashboard-action-center-drilldown-${item.key}`}
              >
                <span>{item.label}</span>
                <span data-testid={`admin-dashboard-action-center-value-${item.key}`}>
                  {String(actionCenterSummary?.[item.key] ?? "-")}
                </span>
              </button>
            ))}
          </div>
          <div className="mt-2 flex flex-wrap gap-2" data-testid="admin-dashboard-action-center-direct-links">
            <Button variant="outline" onClick={() => navigate("/admin/user-approvals")} data-testid="admin-dashboard-go-approvals-button">Go to approvals</Button>
            <Button variant="outline" onClick={() => navigate("/admin/execution-queue")} data-testid="admin-dashboard-go-intents-button">Go to intents</Button>
          </div>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-dashboard-action-center-result-card">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-dashboard-action-center-result-title">Last Auto-Close Result</p>
          {closeResult ? (
            <div className="mt-2 grid gap-1 text-xs" data-testid="admin-dashboard-action-center-result-content">
              <p data-testid="admin-dashboard-action-center-result-status">status: {closeResult.status}</p>
              <p data-testid="admin-dashboard-action-center-result-acked">acked_alerts: {closeResult.acked_alerts}</p>
              <p data-testid="admin-dashboard-action-center-result-rejected-approvals">rejected_approvals: {closeResult.rejected_approvals}</p>
              <p data-testid="admin-dashboard-action-center-result-retried">retried_intents: {closeResult.retried_intents}</p>
              <Button variant="outline" size="sm" onClick={() => setIsCloseResultOpen(true)} data-testid="admin-dashboard-auto-close-result-detail-button">Sonuç Detayı</Button>
            </div>
          ) : (
            <p className="mt-2 text-xs text-slate-400" data-testid="admin-dashboard-action-center-result-empty">Henüz auto-close çalıştırılmadı.</p>
          )}
        </article>
      </div>

      <div className="border border-violet-700/40 bg-slate-900 p-3" data-testid="admin-dashboard-incident-history-panel">
        <div className="flex items-center justify-between" data-testid="admin-dashboard-incident-history-header">
          <p className="text-xs uppercase tracking-widest text-violet-300" data-testid="admin-dashboard-incident-history-title">Notification / Incident History</p>
          <Button variant="outline" onClick={() => navigate("/admin/audit-logs")} data-testid="admin-dashboard-incident-history-audit-link-button">Audit log'a git</Button>
        </div>
        <div className="mt-2 max-h-40 space-y-2 overflow-auto" data-testid="admin-dashboard-incident-history-list">
          {(incidentHistory?.audit_events || []).slice(0, 15).map((item, index) => (
            <article key={`${item.id}-${index}`} className="border border-slate-700 p-2 text-xs" data-testid={`admin-dashboard-incident-history-item-${index}`}>
              <p data-testid={`admin-dashboard-incident-history-action-${index}`}>{item.action}</p>
              <p className="text-slate-400" data-testid={`admin-dashboard-incident-history-meta-${index}`}>
                {item.created_at ? new Date(item.created_at).toLocaleString() : "-"} · {item.actor_role || "unknown"}
              </p>
            </article>
          ))}
          {(incidentHistory?.audit_events || []).length === 0 && (
            <p className="text-xs text-slate-500" data-testid="admin-dashboard-incident-history-empty">Incident kaydı yok.</p>
          )}
        </div>
      </div>

      {loadError && (
        <div className="border border-amber-500/40 bg-amber-950/20 p-3 text-sm text-amber-200" data-testid="admin-dashboard-warning-alert">
          Son yenileme sırasında hata oluştu: {loadError}
        </div>
      )}

      <div className="grid gap-2 border border-red-700/40 bg-red-950/20 p-3 md:grid-cols-6" data-testid="admin-alerts-filter-row">
        <label className="text-xs text-slate-400" htmlFor="admin-alerts-severity-filter" data-testid="admin-alerts-filter-label">Severity Filter</label>
        <select
          id="admin-alerts-severity-filter"
          value={alertFilters.severity}
          onChange={(event) => setAlertFilters((prev) => ({ ...prev, severity: event.target.value }))}
          className="h-9 rounded border border-slate-700 bg-slate-950 px-2 text-sm"
          data-testid="admin-alerts-severity-filter-select"
        >
          <option value="all" data-testid="admin-alerts-severity-filter-option-all">all</option>
          <option value="CRITICAL" data-testid="admin-alerts-severity-filter-option-critical">CRITICAL</option>
          <option value="WARNING" data-testid="admin-alerts-severity-filter-option-warning">WARNING</option>
          <option value="INFO" data-testid="admin-alerts-severity-filter-option-info">INFO</option>
        </select>

        <select
          value={alertFilters.alert_type}
          onChange={(event) => setAlertFilters((prev) => ({ ...prev, alert_type: event.target.value }))}
          className="h-9 rounded border border-slate-700 bg-slate-950 px-2 text-sm"
          data-testid="admin-alerts-type-filter-select"
        >
          <option value="all" data-testid="admin-alerts-type-filter-option-all">all types</option>
          {alertTypeOptions.map((item, index) => (
            <option key={`${item}-${index}`} value={item} data-testid={`admin-alerts-type-filter-option-${index}`}>{item}</option>
          ))}
        </select>

        <Input
          value={alertFilters.source}
          onChange={(event) => setAlertFilters((prev) => ({ ...prev, source: event.target.value }))}
          placeholder="source filter"
          className="h-9 bg-slate-950"
          data-testid="admin-alerts-source-filter-input"
        />

        <select
          value={alertFilters.window_hours}
          onChange={(event) => setAlertFilters((prev) => ({ ...prev, window_hours: event.target.value }))}
          className="h-9 rounded border border-slate-700 bg-slate-950 px-2 text-sm"
          data-testid="admin-alerts-time-filter-select"
        >
          <option value="1" data-testid="admin-alerts-time-filter-option-1h">last 1h</option>
          <option value="6" data-testid="admin-alerts-time-filter-option-6h">last 6h</option>
          <option value="24" data-testid="admin-alerts-time-filter-option-24h">last 24h</option>
          <option value="168" data-testid="admin-alerts-time-filter-option-7d">last 7d</option>
        </select>

        <select
          value={alertFilters.status_filter}
          onChange={(event) => setAlertFilters((prev) => ({ ...prev, status_filter: event.target.value }))}
          className="h-9 rounded border border-slate-700 bg-slate-950 px-2 text-sm"
          data-testid="admin-alerts-status-filter-select"
        >
          <option value="open" data-testid="admin-alerts-status-filter-option-open">open</option>
          <option value="ack" data-testid="admin-alerts-status-filter-option-ack">ack</option>
          <option value="all" data-testid="admin-alerts-status-filter-option-all">all</option>
        </select>

        <Button variant="outline" onClick={loadDashboard} data-testid="admin-alerts-apply-filter-button">Filtreleri Uygula</Button>
      </div>

      <div className="flex flex-wrap items-center gap-2" data-testid="admin-alerts-bulk-actions-row">
        <label className="flex items-center gap-2 text-xs text-slate-300" data-testid="admin-alerts-select-all-wrapper">
          <input
            type="checkbox"
            checked={allFilteredSelected}
            onChange={toggleSelectAllFiltered}
            data-testid="admin-alerts-select-all-checkbox"
          />
          Select all filtered
        </label>
        <p className="text-xs text-slate-400" data-testid="admin-alerts-selected-count">selected: {selectedAlertIds.length}</p>
        <Button
          variant="outline"
          onClick={() => openCriticalDialog("bulk_ack_alerts")}
          disabled={!isManagerRole || selectedAlertIds.length === 0}
          data-testid="admin-alerts-bulk-ack-button"
        >
          Bulk Ack
        </Button>
      </div>

      {filteredAlerts.length > 0 && (
        <div className="border border-red-500/60 bg-red-950/20 p-4" data-testid="admin-alerts-banner">
          <p className="text-xs uppercase tracking-widest text-red-300" data-testid="admin-alerts-title">CRITICAL ALERTS</p>
          <div className="mt-3 space-y-2" data-testid="admin-alerts-list">
            {filteredAlerts.map((alert) => (
              <div key={alert.id} className="flex flex-wrap items-center justify-between gap-2 border border-red-700/40 p-2" data-testid={`admin-alert-row-${alert.id}`}>
                <div className="text-xs" data-testid={`admin-alert-meta-${alert.id}`}>
                  <label className="mr-2 inline-flex items-center gap-1" data-testid={`admin-alert-select-wrapper-${alert.id}`}>
                    <input
                      type="checkbox"
                      checked={selectedAlertIds.includes(alert.id)}
                      onChange={() => toggleAlertSelection(alert.id)}
                      data-testid={`admin-alert-select-${alert.id}`}
                    />
                  </label>
                  <span className="font-semibold" data-testid={`admin-alert-type-${alert.id}`}>{alert.alert_type}</span> ·
                  <span className="ml-1" data-testid={`admin-alert-severity-${alert.id}`}>{alert.severity}</span> ·
                  <span className="ml-1" data-testid={`admin-alert-occurrences-${alert.id}`}>x{alert.occurrences}</span>
                  <span className="ml-1" data-testid={`admin-alert-source-${alert.id}`}>source={alert.source || "unknown"}</span>
                  <p className="text-slate-300" data-testid={`admin-alert-message-${alert.id}`}>{alert.message}</p>
                </div>
                <div className="flex flex-wrap gap-2" data-testid={`admin-alert-actions-${alert.id}`}>
                  <Button
                    size="sm"
                    variant="outline"
                    className="border-red-400 bg-transparent text-red-300"
                    onClick={() => ackSingleAlert(alert.id)}
                    data-testid={`admin-alert-ack-${alert.id}`}
                  >
                    Ack
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => openAlertDetail(alert.id)}
                    data-testid={`admin-alert-detail-${alert.id}`}
                  >
                    Detay
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => navigate("/admin/audit-logs")}
                    data-testid={`admin-alert-root-cause-link-${alert.id}`}
                  >
                    Root Cause / Çözüm
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {filteredAlerts.length === 0 && (
        <div className="border border-slate-800 bg-slate-900 p-4 text-sm text-slate-400" data-testid="admin-alerts-empty-state">
          Bu filtre için alert bulunmuyor.
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-8" data-testid="admin-dashboard-metrics-grid">
        {KPI_CONFIG.map((item) => {
          const currentValue = summary?.metrics?.[item.key];
          const previousValue = previousMetrics?.[item.key];
          const trend = formatTrend(currentValue, previousValue);
          const threshold = kpiThreshold(item.key, currentValue);
          const borderClass = threshold.level === "critical" ? "border-red-600" : threshold.level === "warning" ? "border-amber-600" : "border-slate-700";
          const valueClass = threshold.level === "critical" ? "text-red-300" : threshold.level === "warning" ? "text-amber-300" : "text-slate-100";

          return (
            <button
              key={item.key}
              type="button"
              className={`border bg-slate-900 p-3 text-left ${borderClass}`}
              onClick={() => navigate(item.route)}
              data-testid={`admin-dashboard-kpi-card-${item.key}`}
            >
              <p className="text-xs uppercase tracking-widest text-slate-400" data-testid={`admin-dashboard-kpi-label-${item.key}`}>{item.label}</p>
              <p className={`mt-2 font-mono text-2xl font-semibold ${valueClass}`} data-testid={`admin-dashboard-kpi-value-${item.key}`}>{String(currentValue ?? "-")}</p>
              <p className="mt-1 text-xs text-slate-500" data-testid={`admin-dashboard-kpi-trend-${item.key}`}>{trend.text}</p>
              <p className="mt-1 text-xs" data-testid={`admin-dashboard-kpi-threshold-${item.key}`}>{threshold.label}</p>
            </button>
          );
        })}
      </div>

      <div className="border border-red-500/50 bg-red-950/20 p-4" data-testid="admin-critical-actions-panel">
        <p className="text-xs uppercase tracking-widest text-red-300" data-testid="admin-critical-actions-title">Kritik Kontrol Alanı</p>
        <p className="mt-2 text-xs text-red-200" data-testid="admin-critical-actions-double-confirm-visible">Double-confirm aktif: işlem için reason + phrase zorunlu.</p>
        <div className="mt-3 grid gap-2 md:grid-cols-2" data-testid="admin-critical-actions-grid">
          <Button
            variant="outline"
            className="border-red-400 bg-transparent text-red-300 hover:bg-red-900/40 hover:text-red-100"
            onClick={() => openCriticalDialog("kill_on")}
            disabled={!isManagerRole || killSwitchActive}
            data-testid="admin-critical-action-kill-on"
          >
            Kill Switch Aktif Et
          </Button>
          <Button
            variant="outline"
            className="border-red-400 bg-transparent text-red-300 hover:bg-red-900/40 hover:text-red-100"
            onClick={() => openCriticalDialog("kill_off")}
            disabled={!isManagerRole || !killSwitchActive}
            data-testid="admin-critical-action-kill-off"
          >
            Kill Switch Pasif Et
          </Button>
          <Button
            variant="outline"
            className="border-red-400 bg-transparent text-red-300 hover:bg-red-900/40 hover:text-red-100"
            onClick={() => openCriticalDialog("restart_services")}
            disabled={!isManagerRole}
            data-testid="admin-critical-action-restart-services"
          >
            Restart Services
          </Button>
          <Button
            variant="outline"
            className="border-red-400 bg-transparent text-red-300 hover:bg-red-900/40 hover:text-red-100"
            onClick={() => navigate("/admin/audit-logs")}
            data-testid="admin-critical-action-log-link"
          >
            İşlem Logları (Kim / Ne Zaman)
          </Button>
        </div>
      </div>

      <Dialog
        open={criticalDialogState.open}
        onOpenChange={(open) => setCriticalDialogState((prev) => ({ ...prev, open }))}
      >
        <DialogContent className="max-w-xl border border-red-700 bg-slate-950" data-testid="admin-dashboard-critical-confirm-modal">
          <DialogHeader>
            <DialogTitle data-testid="admin-dashboard-critical-confirm-title">{ACTION_CONFIG[criticalDialogState.actionKey]?.title || "Kritik Aksiyon"}</DialogTitle>
            <DialogDescription data-testid="admin-dashboard-critical-confirm-description">
              {ACTION_CONFIG[criticalDialogState.actionKey]?.description || ""}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3" data-testid="admin-dashboard-critical-confirm-form">
            <div data-testid="admin-dashboard-critical-confirm-reason-field">
              <p className="text-xs text-slate-400">Reason</p>
              <Textarea
                value={criticalDialogState.reason}
                onChange={(event) => setCriticalDialogState((prev) => ({ ...prev, reason: event.target.value }))}
                className="mt-1 bg-slate-900"
                data-testid="admin-dashboard-critical-confirm-reason-input"
              />
            </div>

            {criticalDialogState.actionKey === "restart_services" && (
              <div className="rounded border border-slate-700 p-2" data-testid="admin-dashboard-restart-targets-field">
                <p className="text-xs text-slate-400">Restart Targets</p>
                <label className="mt-2 flex items-center gap-2 text-xs" data-testid="admin-dashboard-restart-target-backend-wrapper">
                  <input
                    type="checkbox"
                    checked={criticalDialogState.restartTargets.backend}
                    onChange={(event) =>
                      setCriticalDialogState((prev) => ({
                        ...prev,
                        restartTargets: { ...prev.restartTargets, backend: event.target.checked },
                      }))
                    }
                    data-testid="admin-dashboard-restart-target-backend-checkbox"
                  />
                  backend
                </label>
                <label className="mt-1 flex items-center gap-2 text-xs" data-testid="admin-dashboard-restart-target-frontend-wrapper">
                  <input
                    type="checkbox"
                    checked={criticalDialogState.restartTargets.frontend}
                    onChange={(event) =>
                      setCriticalDialogState((prev) => ({
                        ...prev,
                        restartTargets: { ...prev.restartTargets, frontend: event.target.checked },
                      }))
                    }
                    data-testid="admin-dashboard-restart-target-frontend-checkbox"
                  />
                  frontend
                </label>
              </div>
            )}

            <div data-testid="admin-dashboard-critical-confirm-phrase-field">
              <p className="text-xs text-slate-400">
                Confirm phrase: <span data-testid="admin-dashboard-critical-confirm-expected-phrase">{ACTION_CONFIG[criticalDialogState.actionKey]?.expectedPhrase || "-"}</span>
              </p>
              <Input
                value={criticalDialogState.phrase}
                onChange={(event) => setCriticalDialogState((prev) => ({ ...prev, phrase: event.target.value }))}
                className="mt-1 bg-slate-900"
                data-testid="admin-dashboard-critical-confirm-phrase-input"
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setCriticalDialogState((prev) => ({ ...prev, open: false }))}
              data-testid="admin-dashboard-critical-confirm-cancel-button"
            >
              Vazgeç
            </Button>
            <Button onClick={runCriticalAction} disabled={!isManagerRole} data-testid="admin-dashboard-critical-confirm-submit-button">
              Onayla ve Çalıştır
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={isAlertDetailOpen} onOpenChange={setIsAlertDetailOpen}>
        <DialogContent className="max-w-2xl border border-slate-700 bg-slate-950" data-testid="admin-dashboard-alert-detail-modal">
          <DialogHeader>
            <DialogTitle data-testid="admin-dashboard-alert-detail-title">Alert Detayı</DialogTitle>
            <DialogDescription data-testid="admin-dashboard-alert-detail-description">Root cause ve çözüm önerisi</DialogDescription>
          </DialogHeader>

          <div className="space-y-2 text-xs" data-testid="admin-dashboard-alert-detail-content">
            <p data-testid="admin-dashboard-alert-detail-type">alert_type: {alertDetail?.alert_type || "-"}</p>
            <p data-testid="admin-dashboard-alert-detail-severity">severity: {alertDetail?.severity || "-"}</p>
            <p data-testid="admin-dashboard-alert-detail-source">source: {alertDetail?.source || "-"}</p>
            <p data-testid="admin-dashboard-alert-detail-root-cause">root_cause_code: {alertDetail?.root_cause_code || "-"}</p>
            <p data-testid="admin-dashboard-alert-detail-message">message: {alertDetail?.message || "-"}</p>
            <div className="rounded border border-slate-700 bg-slate-900 p-2" data-testid="admin-dashboard-alert-detail-recommendation-panel">
              <p className="font-semibold" data-testid="admin-dashboard-alert-detail-recommendation-title">{alertDetail?.recommendation?.title || "Öneri"}</p>
              <p className="mt-1 text-slate-300" data-testid="admin-dashboard-alert-detail-recommendation-description">{alertDetail?.recommendation?.description || "-"}</p>
              <div className="mt-2 flex flex-wrap gap-2" data-testid="admin-dashboard-alert-detail-recommendation-actions">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => navigate(alertDetail?.recommendation?.runbook_link || "/admin/anomaly-timeline")}
                  data-testid="admin-dashboard-alert-detail-runbook-link-button"
                >
                  Runbook Aç
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => navigate(alertDetail?.audit_log_link || "/admin/audit-logs")}
                  data-testid="admin-dashboard-alert-detail-audit-link-button"
                >
                  Audit Link
                </Button>
              </div>
            </div>
            <pre className="max-h-52 overflow-auto border border-slate-700 bg-black p-2 text-[11px]" data-testid="admin-dashboard-alert-detail-json">
              {JSON.stringify(alertDetail?.details || {}, null, 2)}
            </pre>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={isCloseResultOpen} onOpenChange={setIsCloseResultOpen}>
        <DialogContent className="max-w-xl border border-slate-700 bg-slate-950" data-testid="admin-dashboard-auto-close-result-modal">
          <DialogHeader>
            <DialogTitle data-testid="admin-dashboard-auto-close-result-modal-title">Auto-Close Sonuç Detayı</DialogTitle>
            <DialogDescription data-testid="admin-dashboard-auto-close-result-modal-description">Manual trigger çıktısı ve log erişimi</DialogDescription>
          </DialogHeader>
          <pre className="max-h-64 overflow-auto border border-slate-700 bg-black p-2 text-[11px]" data-testid="admin-dashboard-auto-close-result-json">
            {JSON.stringify(closeResult || {}, null, 2)}
          </pre>
          <DialogFooter>
            <Button variant="outline" onClick={() => navigate("/admin/audit-logs")} data-testid="admin-dashboard-auto-close-result-audit-link-button">Audit Log'a Git</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Sheet open={drilldown.open} onOpenChange={(open) => setDrilldown((prev) => ({ ...prev, open }))}>
        <SheetContent side="right" className="w-full max-w-2xl overflow-auto border-l border-slate-700 bg-slate-950" data-testid="admin-dashboard-drilldown-drawer">
          <SheetHeader>
            <SheetTitle data-testid="admin-dashboard-drilldown-title">KPI Drill-Down · {drilldown.metricKey || "-"}</SheetTitle>
            <SheetDescription data-testid="admin-dashboard-drilldown-description">
              Metrik detayını incele, ardından ilgili operasyon sayfasına geç.
            </SheetDescription>
          </SheetHeader>

          <div className="mt-4 space-y-3" data-testid="admin-dashboard-drilldown-content">
            <p className="text-sm text-slate-300" data-testid="admin-dashboard-drilldown-current-value">
              current_value={String(actionCenterSummary?.[drilldown.metricKey] ?? summary?.metrics?.[drilldown.metricKey] ?? "-")}
            </p>

            {drilldown.metricKey === "pending_approvals" && (
              <p className="text-xs text-slate-400" data-testid="admin-dashboard-drilldown-pending-approvals-note">
                Onay bekleyen kullanıcılar için bulk approve/reject akışına hızlı geçiş önerilir.
              </p>
            )}
            {drilldown.metricKey === "rejected_intents" && (
              <p className="text-xs text-slate-400" data-testid="admin-dashboard-drilldown-rejected-intents-note">
                Rejected intent’ler için queue/recovery panelini açıp retry pattern kontrol edin.
              </p>
            )}

            {drilldownAlertRows.length > 0 && (
              <div className="space-y-2" data-testid="admin-dashboard-drilldown-alert-preview-list">
                {drilldownAlertRows.map((item, index) => (
                  <article key={`${item.id}-${index}`} className="border border-slate-700 p-2 text-xs" data-testid={`admin-dashboard-drilldown-alert-preview-${index}`}>
                    <p data-testid={`admin-dashboard-drilldown-alert-type-${index}`}>{item.alert_type} · {item.severity}</p>
                    <p className="text-slate-400" data-testid={`admin-dashboard-drilldown-alert-message-${index}`}>{item.message}</p>
                  </article>
                ))}
              </div>
            )}

            <div className="flex flex-wrap gap-2" data-testid="admin-dashboard-drilldown-actions">
              <Button onClick={() => navigate(drilldown.route || "/admin/dashboard")} data-testid="admin-dashboard-drilldown-go-target-button">İlgili Sayfaya Git</Button>
              <Button variant="outline" onClick={() => navigate("/admin/user-approvals")} data-testid="admin-dashboard-drilldown-go-approvals-button">Go to approvals</Button>
              <Button variant="outline" onClick={() => navigate("/admin/execution-queue")} data-testid="admin-dashboard-drilldown-go-intents-button">Go to intents</Button>
            </div>
          </div>
        </SheetContent>
      </Sheet>
    </section>
  );
};
