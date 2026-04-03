import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { OnboardingObservabilitySnapshot } from "@/components/OnboardingObservabilitySnapshot";
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
  { key: "websocket_status", label: "WS Status", route: "/admin/system-status" },
  { key: "signals_5m", label: "Signal / 5m", route: "/admin/live-trading-dashboard" },
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
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [lastUpdatedAt, setLastUpdatedAt] = useState("");
  const [alertFilters, setAlertFilters] = useState({
    status_filter: "all",
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
  const [latestAutoCloseAudit, setLatestAutoCloseAudit] = useState(null);
  const [killSwitchState, setKillSwitchState] = useState(null);
  const [actionAuditSnippet, setActionAuditSnippet] = useState([]);
  const [incidentHistory, setIncidentHistory] = useState({ audit_events: [], recent_alerts: [] });
  const [runtimePnlSummary, setRuntimePnlSummary] = useState(null);
  const [runtimeAlerts, setRuntimeAlerts] = useState([]);
  const [runtimeSmoke, setRuntimeSmoke] = useState(null);
  const [runtimeKillSwitch, setRuntimeKillSwitch] = useState(null);
  const [runtimeExecutionMode, setRuntimeExecutionMode] = useState(null);
  const [runtimeReadiness, setRuntimeReadiness] = useState(null);
  const [runtimeGoLiveChecklist, setRuntimeGoLiveChecklist] = useState(null);
  const [runtimeProxyHealth, setRuntimeProxyHealth] = useState(null);
  const [runtimeCanaryRunResult, setRuntimeCanaryRunResult] = useState(null);
  const [runtimeValidationLoading, setRuntimeValidationLoading] = useState(false);
  const [runtimeDryRunResult, setRuntimeDryRunResult] = useState(null);
  const [goLiveWizardState, setGoLiveWizardState] = useState(null);
  const [runtimeTimelineEvents, setRuntimeTimelineEvents] = useState([]);
  const [runtimeWsStatus, setRuntimeWsStatus] = useState("connecting");
  const [timelineAutoScroll, setTimelineAutoScroll] = useState(true);
  const [runtimeAlertFilters, setRuntimeAlertFilters] = useState({ severity: "all", state: "all", symbol: "", user_id: "", window_minutes: "60" });
  const [alertNoteDrafts, setAlertNoteDrafts] = useState({});
  const timelineContainerRef = useRef(null);
  const [criticalDialogState, setCriticalDialogState] = useState({
    open: false,
    actionKey: "",
    reason: "",
    phrase: "",
    step: 1,
    restartTargets: { backend: true, frontend: true },
  });
  const [alertDetail, setAlertDetail] = useState(null);
  const [alertDetailTimeline, setAlertDetailTimeline] = useState([]);
  const [alertDetailTimelineLoading, setAlertDetailTimelineLoading] = useState(false);
  const [isAlertDetailOpen, setIsAlertDetailOpen] = useState(false);
  const [isCloseResultOpen, setIsCloseResultOpen] = useState(false);
  const [drilldown, setDrilldown] = useState({ open: false, metricKey: "", route: "" });
  const hasLoadedOnceRef = useRef(false);

  const isManagerRole = ["super_admin", "admin"].includes(String(user?.role || ""));
  const isSuperAdmin = String(user?.role || "") === "super_admin";
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

  const runtimeTimelineFiltered = useMemo(() => {
    const now = Date.now();
    const windowMs = Number(runtimeAlertFilters.window_minutes || 60) * 60 * 1000;
    return runtimeTimelineEvents.filter((event) => {
      const severityOk = runtimeAlertFilters.severity === "all" || String(event?.severity || "").toUpperCase() === runtimeAlertFilters.severity;
      const stateOk = runtimeAlertFilters.state === "all" || String(event?.state || "").toUpperCase() === runtimeAlertFilters.state;
      const symbolOk = !runtimeAlertFilters.symbol || String(event?.symbol || "").toUpperCase().includes(String(runtimeAlertFilters.symbol).toUpperCase());
      const userOk = !runtimeAlertFilters.user_id || String(event?.user_id || "").includes(runtimeAlertFilters.user_id);
      const ts = Date.parse(event?.timestamp || "");
      const timeOk = Number.isFinite(ts) ? (now - ts <= windowMs) : true;
      return severityOk && stateOk && symbolOk && userOk && timeOk;
    });
  }, [runtimeTimelineEvents, runtimeAlertFilters]);

  const allFilteredSelected = filteredAlerts.length > 0 && filteredAlerts.every((item) => selectedAlertIds.includes(item.id));

  const loadDashboard = useCallback(async () => {
    if (hasLoadedOnceRef.current) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }
    setLoadError("");

    try {
      const [
        summaryResponse,
        actionSummaryResponse,
        killSwitchResponse,
        incidentResponse,
        alertsResponse,
        latestAutoCloseResponse,
        actionAuditResponse,
        runtimePnlSummaryResponse,
        runtimeAlertsResponse,
        runtimeSmokeResponse,
        runtimeKillSwitchResponse,
        runtimeExecutionModeResponse,
        runtimeReadinessResponse,
        runtimeGoLiveChecklistResponse,
        runtimeProxyHealthResponse,
        runtimeWizardStateResponse,
        runtimeTimelineResponse,
      ] = await Promise.all([
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
        apiClient.get("/admin/action-center/close-next-actions/latest"),
        apiClient.get("/admin/live-trading/control-layer/action-audit", { params: { since_hours: 48, limit: 8 } }),
        apiClient.get("/runtime/pnl/summary"),
        apiClient.get("/runtime/alerts", {
          params: {
            limit: 20,
            severity: runtimeAlertFilters.severity !== "all" ? runtimeAlertFilters.severity : undefined,
            state: runtimeAlertFilters.state !== "all" ? runtimeAlertFilters.state : undefined,
            symbol: runtimeAlertFilters.symbol || undefined,
            user_id: runtimeAlertFilters.user_id || undefined,
            window_minutes: Number(runtimeAlertFilters.window_minutes || 60),
          },
        }),
        apiClient.get("/runtime/health/smoke"),
        apiClient.get("/runtime/safety/kill-switch"),
        apiClient.get("/runtime/execution/mode"),
        apiClient.get("/runtime/canary/readiness-score"),
        apiClient.get("/runtime/go-live/checklist"),
        apiClient.get("/runtime/exchange/proxy-health"),
        apiClient.get("/runtime/go-live/wizard/state"),
        (isManagerRole
          ? apiClient.get("/runtime/ws/execution-timeline", { params: { limit: 120 } })
          : Promise.resolve({ data: { status: "disabled_role", items: [] } }))
          .catch((error) => ({
            data: {
              status: Number(error?.response?.status || 0) === 404 ? "disabled_missing_endpoint" : "polling_error",
              items: [],
            },
          })),
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
      setLatestAutoCloseAudit(latestAutoCloseResponse?.data?.found ? latestAutoCloseResponse?.data?.item : null);
      setActionAuditSnippet(actionAuditResponse?.data?.items || []);
      setRuntimePnlSummary(runtimePnlSummaryResponse?.data || null);
      setRuntimeAlerts(runtimeAlertsResponse?.data?.items || []);
      setRuntimeSmoke(runtimeSmokeResponse?.data?.smoke || null);
      setRuntimeKillSwitch(runtimeKillSwitchResponse?.data?.kill_switch || null);
      setRuntimeExecutionMode(runtimeExecutionModeResponse?.data || null);
      setRuntimeReadiness(runtimeReadinessResponse?.data?.result || null);
      setRuntimeGoLiveChecklist(runtimeGoLiveChecklistResponse?.data?.result || null);
      setRuntimeProxyHealth(runtimeProxyHealthResponse?.data?.result || null);
      setGoLiveWizardState(runtimeWizardStateResponse?.data?.result || null);
      const timelineItems = Array.isArray(runtimeTimelineResponse?.data?.items) ? runtimeTimelineResponse.data.items : [];
      setRuntimeTimelineEvents(timelineItems.slice(-50).reverse());
      setRuntimeWsStatus(String(runtimeTimelineResponse?.data?.status || (isManagerRole ? "http_polling" : "disabled_role")));
      setLastUpdatedAt(new Date().toISOString());
    } catch (error) {
      const message = error?.response?.data?.detail || "Admin dashboard verisi yüklenemedi";
      setLoadError(typeof message === "string" ? message : "Admin dashboard verisi yüklenemedi");
      toast.error(typeof message === "string" ? message : "Admin dashboard verisi yüklenemedi");
    } finally {
      hasLoadedOnceRef.current = true;
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [alertFilters, isManagerRole, runtimeAlertFilters]);

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

  useEffect(() => {
    if (!isManagerRole) {
      setRuntimeWsStatus("disabled_role");
      setRuntimeTimelineEvents([]);
      return undefined;
    }
    setRuntimeWsStatus((prev) => (prev === "connecting" ? "http_polling" : prev));
    return undefined;
  }, [isManagerRole]);

  useEffect(() => {
    if (!timelineAutoScroll) {
      return;
    }
    if (timelineContainerRef.current) {
      timelineContainerRef.current.scrollTop = 0;
    }
  }, [runtimeTimelineEvents, timelineAutoScroll]);

  const handleRuntimeAlertAction = useCallback(async (alertId, actionType, payload = {}) => {
    const routeMap = {
      acknowledge: `/runtime/alerts/${alertId}/ack`,
      mute_temporarily: `/runtime/alerts/${alertId}/mute`,
      resolve: `/runtime/alerts/${alertId}/resolve`,
      escalate: `/runtime/alerts/${alertId}/escalate`,
      attach_note: `/runtime/alerts/${alertId}/note`,
    };

    try {
      await apiClient.post(routeMap[actionType], payload);
      toast.success(`Alert aksiyonu başarılı: ${actionType}`);
      await loadDashboard();
    } catch (error) {
      const message = error?.response?.data?.detail || "Alert aksiyonu başarısız";
      toast.error(typeof message === "string" ? message : "Alert aksiyonu başarısız");
    }
  }, [loadDashboard]);

  const handleKillSwitchAction = useCallback(async (action) => {
    const endpoint = action === "activate" ? "/runtime/safety/kill-switch/activate" : "/runtime/safety/kill-switch/deactivate";
    const reason = action === "activate" ? "manual_dashboard_activation" : "manual_dashboard_release";
    try {
      await apiClient.post(endpoint, { reason });
      toast.success(`Kill switch ${action === "activate" ? "aktif" : "pasif"} edildi`);
      await loadDashboard();
    } catch (error) {
      const message = error?.response?.data?.detail || "Kill switch aksiyonu başarısız";
      toast.error(typeof message === "string" ? message : "Kill switch aksiyonu başarısız");
    }
  }, [loadDashboard]);

  const runLiveLifecycleValidation = useCallback(async () => {
    setRuntimeValidationLoading(true);
    try {
      const { data } = await apiClient.post("/runtime/exchange/live-lifecycle/run", { symbol: "BTCUSDT", size: 0.0001 });
      setRuntimeCanaryRunResult(data?.result || null);
      toast.success("Live lifecycle doğrulaması PASS");
      await loadDashboard();
    } catch (error) {
      const detail = error?.response?.data?.detail;
      const message = typeof detail === "string" ? detail : (detail?.status ? JSON.stringify(detail) : "Live lifecycle doğrulaması başarısız");
      toast.error(message);
    } finally {
      setRuntimeValidationLoading(false);
    }
  }, [loadDashboard]);

  const runCanaryValidation = useCallback(async () => {
    setRuntimeValidationLoading(true);
    try {
      const { data } = await apiClient.post("/runtime/canary/run", { symbol: "BTCUSDT", size: 0.0001, strategy_name: "ema_rsi" });
      setRuntimeCanaryRunResult(data?.result || null);
      toast.success("Canary run tamamlandı");
      await loadDashboard();
    } catch (error) {
      const detail = error?.response?.data?.detail;
      const message = typeof detail === "string" ? detail : (detail?.status ? JSON.stringify(detail) : "Canary run başarısız");
      toast.error(message);
    } finally {
      setRuntimeValidationLoading(false);
    }
  }, [loadDashboard]);

  const runKillSwitchRollbackValidation = useCallback(async () => {
    setRuntimeValidationLoading(true);
    try {
      const { data } = await apiClient.post("/runtime/safety/kill-switch/verify-rollback", { symbol: "BTCUSDT" });
      setRuntimeCanaryRunResult(data?.result || null);
      toast.success("Kill-switch rollback doğrulaması PASS");
      await loadDashboard();
    } catch (error) {
      const detail = error?.response?.data?.detail;
      const message = typeof detail === "string" ? detail : (detail?.status ? JSON.stringify(detail) : "Kill-switch rollback doğrulaması başarısız");
      toast.error(message);
    } finally {
      setRuntimeValidationLoading(false);
    }
  }, [loadDashboard]);

  const runFinalRegressionValidation = useCallback(async () => {
    setRuntimeValidationLoading(true);
    try {
      const { data } = await apiClient.post("/runtime/regression/final-run", { symbol: "BTCUSDT", size: 0.0001, strategy_name: "ema_rsi" });
      setRuntimeCanaryRunResult(data?.result || null);
      toast.success("Final regression PASS");
      await loadDashboard();
    } catch (error) {
      const detail = error?.response?.data?.detail;
      const message = typeof detail === "string" ? detail : (detail?.status ? JSON.stringify(detail) : "Final regression başarısız");
      toast.error(message);
    } finally {
      setRuntimeValidationLoading(false);
    }
  }, [loadDashboard]);

  const runSingleFlowDryRun = useCallback(async () => {
    setRuntimeValidationLoading(true);
    try {
      const { data } = await apiClient.post("/runtime/go-live/dry-run/run", { symbol: "BTCUSDT", size: 0.0001 });
      setRuntimeDryRunResult(data?.result || null);
      toast.success("Dry-run tek akış PASS");
      await loadDashboard();
    } catch (error) {
      const detail = error?.response?.data?.detail;
      const message = typeof detail === "string" ? detail : (detail?.status ? JSON.stringify(detail) : "Dry-run tek akış başarısız");
      toast.error(message);
    } finally {
      setRuntimeValidationLoading(false);
    }
  }, [loadDashboard]);

  const runWizardReadinessCheck = useCallback(async () => {
    setRuntimeValidationLoading(true);
    try {
      const { data } = await apiClient.post("/runtime/go-live/wizard/readiness-check", {});
      setGoLiveWizardState(data?.result || null);
      toast.success("Wizard readiness adımı tamamlandı");
      await loadDashboard();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Wizard readiness adımı başarısız");
    } finally {
      setRuntimeValidationLoading(false);
    }
  }, [loadDashboard]);

  const runWizardCanaryCheck = useCallback(async () => {
    setRuntimeValidationLoading(true);
    try {
      const { data } = await apiClient.post("/runtime/go-live/wizard/canary-check", { symbol: "BTCUSDT", size: 0.0001 });
      setGoLiveWizardState(data?.result || null);
      toast.success("Wizard canary adımı tamamlandı");
      await loadDashboard();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Wizard canary adımı başarısız");
    } finally {
      setRuntimeValidationLoading(false);
    }
  }, [loadDashboard]);

  const runWizardArm = useCallback(async () => {
    setRuntimeValidationLoading(true);
    try {
      const { data } = await apiClient.post("/runtime/go-live/wizard/arm", {});
      setGoLiveWizardState(data?.result || null);
      toast.success("Wizard live-arm adımı tamamlandı");
      await loadDashboard();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Wizard arm adımı başarısız");
    } finally {
      setRuntimeValidationLoading(false);
    }
  }, [loadDashboard]);

  const runWizardConfirm = useCallback(async () => {
    setRuntimeValidationLoading(true);
    try {
      const { data } = await apiClient.post("/runtime/go-live/wizard/confirm", {});
      setGoLiveWizardState(data?.result || null);
      toast.success("Wizard confirm adımı tamamlandı");
      await loadDashboard();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Wizard confirm adımı başarısız");
    } finally {
      setRuntimeValidationLoading(false);
    }
  }, [loadDashboard]);

  const runWizardRollback = useCallback(async () => {
    setRuntimeValidationLoading(true);
    try {
      const { data } = await apiClient.post("/runtime/go-live/wizard/rollback", {});
      setGoLiveWizardState(data?.result || null);
      toast.success("Wizard rollback tetiklendi");
      await loadDashboard();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Wizard rollback başarısız");
    } finally {
      setRuntimeValidationLoading(false);
    }
  }, [loadDashboard]);

  const navigateToAuditContext = ({ action = "", q = "", requestId = "", sessionId = "" } = {}) => {
    const params = new URLSearchParams();
    if (action) params.set("action", action);
    if (q) params.set("q", q);
    if (requestId) params.set("request_id", requestId);
    if (sessionId) params.set("session_id", sessionId);
    navigate(`/admin/audit-logs${params.toString() ? `?${params.toString()}` : ""}`);
  };

  const openCriticalDialog = (actionKey, options = {}) => {
    const defaultReason = options?.reasonHint || (actionKey === "kill_on" ? "dashboard_kill_switch_activate" : "dashboard_manual_operation");
    setCriticalDialogState({
      open: true,
      actionKey,
      reason: defaultReason,
      phrase: "",
      step: 1,
      restartTargets: { backend: true, frontend: true },
    });
  };

  const advanceCriticalStep = () => {
    if (!criticalDialogState.reason || criticalDialogState.reason.trim().length < 5) {
      toast.error("1. adım için reason zorunlu (min 5 karakter)");
      return;
    }
    setCriticalDialogState((prev) => ({ ...prev, step: 2 }));
  };

  const executeSuggestedAction = (alert) => {
    const actionKey = alert?.recommendation?.suggested_action?.action_key;
    if (actionKey === "auto_close_run") {
      openCriticalDialog("auto_close_run", { reasonHint: `${alert?.id || "alert"}_auto_close` });
      return;
    }
    if (actionKey === "restart_services") {
      openCriticalDialog("restart_services", { reasonHint: `${alert?.id || "alert"}_restart_services` });
      return;
    }
    if (actionKey === "go_risk_orchestrator") {
      navigate("/admin/risk-orchestrator");
      return;
    }
    navigateToAuditContext({
      action: "ACTION_CENTER",
      q: String(alert?.root_cause_code || alert?.alert_type || "").trim(),
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

    if (criticalDialogState.step !== 2) {
      toast.error("Lütfen önce 1. adımı tamamlayın");
      return;
    }

    try {
      let actionResponse = null;
      if (criticalDialogState.actionKey === "kill_on") {
        const { data } = await apiClient.post("/admin/action-center/global-kill-switch/toggle", {
          active: true,
          reason: criticalDialogState.reason,
          confirmation_phrase: criticalDialogState.phrase,
          requested_by: user?.email,
        });
        actionResponse = data;
        setCloseResult(data || null);
      }
      if (criticalDialogState.actionKey === "kill_off") {
        const { data } = await apiClient.post("/admin/action-center/global-kill-switch/toggle", {
          active: false,
          reason: criticalDialogState.reason,
          confirmation_phrase: criticalDialogState.phrase,
          requested_by: user?.email,
        });
        actionResponse = data;
        setCloseResult(data || null);
      }
      if (criticalDialogState.actionKey === "restart_services") {
        const targets = [];
        if (criticalDialogState.restartTargets.backend) targets.push("backend");
        if (criticalDialogState.restartTargets.frontend) targets.push("frontend");
        const { data } = await apiClient.post("/admin/action-center/restart-services", {
          targets,
          reason: criticalDialogState.reason,
          confirmation_phrase: criticalDialogState.phrase,
        });
        actionResponse = data;
        setCloseResult(data || null);
      }
      if (criticalDialogState.actionKey === "clear_all_alerts") {
        const { data } = await apiClient.post("/admin/action-center/alerts/clear-all", {
          status_filter: alertFilters.status_filter,
          reason: criticalDialogState.reason,
          confirmation_phrase: criticalDialogState.phrase,
        });
        actionResponse = data;
        setCloseResult(data || null);
      }
      if (criticalDialogState.actionKey === "bulk_ack_alerts") {
        const { data } = await apiClient.post("/admin/action-center/alerts/bulk-ack", {
          ids: selectedAlertIds,
          reason: criticalDialogState.reason,
          confirmation_phrase: criticalDialogState.phrase,
        });
        actionResponse = data;
        setCloseResult(data || null);
        setSelectedAlertIds([]);
      }
      if (criticalDialogState.actionKey === "auto_close_run") {
        const { data } = await apiClient.post("/admin/action-center/close-next-actions", {
          ack_open_alerts: true,
          reject_stale_approvals: true,
          stale_days: 30,
          retry_timeout_rejections: true,
          clear_kill_switch: false,
          reason: criticalDialogState.reason,
          confirmation_phrase: criticalDialogState.phrase,
        });
        actionResponse = data;
        setCloseResult(data || null);
        setIsCloseResultOpen(true);
      }

      if (!actionResponse?.audit_log_id) {
        toast.error("Audit log üretilemedi, aksiyon doğrulanmadı");
        return;
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
        confirmation_phrase: "ACK SELECTED ALERTS",
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
      setAlertDetailTimeline([]);
      setIsAlertDetailOpen(true);

      setAlertDetailTimelineLoading(true);
      try {
        const q = String(data?.root_cause_code || data?.alert_type || data?.source || "").trim();
        const timelineRes = await apiClient.get("/audit-logs/timeline", {
          params: {
            q: q || undefined,
            limit: 30,
          },
        });
        setAlertDetailTimeline(timelineRes?.data?.items || []);
      } catch {
        setAlertDetailTimeline([]);
      } finally {
        setAlertDetailTimelineLoading(false);
      }
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Alert detayı alınamadı");
    }
  };

  const openDrilldown = (metric) => {
    setDrilldown({ open: true, metricKey: metric.key, route: metric.route });
  };

  if (isLoading && !summary) {
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
            {isRefreshing && (
              <p className="text-xs text-cyan-300" data-testid="admin-dashboard-refreshing-indicator">yenileniyor...</p>
            )}
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
            <Button variant="outline" onClick={() => navigate("/admin/live-trading-dashboard")} data-testid="admin-dashboard-go-live-control-hub-button">Live Control Hub</Button>
            <Button variant="outline" onClick={() => navigate("/admin/pipeline-operations")} data-testid="admin-dashboard-go-pipeline-operations-button">Unified Pipeline Ops</Button>
            <Button variant="outline" onClick={runCloseNextActions} data-testid="admin-dashboard-auto-close-run-now-button">Auto-Close Run Now</Button>
            <Button onClick={loadDashboard} data-testid="admin-dashboard-refresh-button">Yenile</Button>
          </div>
        </div>
      </header>

      <OnboardingObservabilitySnapshot
        onOpenDetail={() => navigate("/admin/onboarding-observability")}
      />

      <div className="grid gap-3 md:grid-cols-4" data-testid="admin-dashboard-runtime-ops-grid">
        <article className="border border-emerald-700/40 bg-slate-900 p-3" data-testid="admin-dashboard-runtime-pnl-card">
          <p className="text-xs uppercase tracking-widest text-emerald-300" data-testid="admin-dashboard-runtime-pnl-title">Canlı PnL Özeti</p>
          <div className="mt-2 space-y-1 text-xs" data-testid="admin-dashboard-runtime-pnl-content">
            <p data-testid="admin-dashboard-runtime-pnl-scope">scope: {runtimePnlSummary?.scope || "-"}</p>
            <p data-testid="admin-dashboard-runtime-pnl-open-positions">open_positions: {runtimePnlSummary?.open_positions ?? "-"}</p>
            <p data-testid="admin-dashboard-runtime-pnl-realized">realized: {runtimePnlSummary?.realized_pnl ?? "-"}</p>
            <p data-testid="admin-dashboard-runtime-pnl-unrealized">unrealized: {runtimePnlSummary?.unrealized_pnl ?? "-"}</p>
            <p data-testid="admin-dashboard-runtime-pnl-net">net: {runtimePnlSummary?.net_pnl ?? "-"}</p>
          </div>
        </article>

        <article className="border border-amber-700/40 bg-slate-900 p-3 md:col-span-2" data-testid="admin-dashboard-runtime-alerts-card">
          <div className="flex flex-wrap items-center justify-between gap-2" data-testid="admin-dashboard-runtime-alerts-header">
            <p className="text-xs uppercase tracking-widest text-amber-300" data-testid="admin-dashboard-runtime-alerts-title">Runtime Alert Triage</p>
            <Button variant="outline" size="sm" onClick={loadDashboard} data-testid="admin-dashboard-runtime-alerts-refresh-button">Yenile</Button>
          </div>

          <div className="mt-2 grid gap-2 md:grid-cols-6" data-testid="admin-dashboard-runtime-alerts-filters">
            <select
              className="h-9 rounded border border-slate-700 bg-slate-950 px-2 text-xs"
              value={runtimeAlertFilters.severity}
              onChange={(event) => setRuntimeAlertFilters((prev) => ({ ...prev, severity: event.target.value }))}
              data-testid="admin-dashboard-runtime-alert-filter-severity"
            >
              <option value="all">severity: all</option>
              <option value="INFO">INFO</option>
              <option value="WARNING">WARNING</option>
              <option value="CRITICAL">CRITICAL</option>
            </select>
            <select
              className="h-9 rounded border border-slate-700 bg-slate-950 px-2 text-xs"
              value={runtimeAlertFilters.state}
              onChange={(event) => setRuntimeAlertFilters((prev) => ({ ...prev, state: event.target.value }))}
              data-testid="admin-dashboard-runtime-alert-filter-state"
            >
              <option value="all">state: all</option>
              <option value="CREATED">CREATED</option>
              <option value="SENT">SENT</option>
              <option value="PARTIALLY_FILLED">PARTIALLY_FILLED</option>
              <option value="FILLED">FILLED</option>
              <option value="FAILED">FAILED</option>
              <option value="CANCELED">CANCELED</option>
              <option value="open">open</option>
              <option value="acknowledged">acknowledged</option>
              <option value="muted">muted</option>
              <option value="resolved">resolved</option>
              <option value="escalated">escalated</option>
            </select>
            <select
              className="h-9 rounded border border-slate-700 bg-slate-950 px-2 text-xs"
              value={runtimeAlertFilters.window_minutes}
              onChange={(event) => setRuntimeAlertFilters((prev) => ({ ...prev, window_minutes: event.target.value }))}
              data-testid="admin-dashboard-runtime-alert-filter-window"
            >
              <option value="15">15 dk</option>
              <option value="60">1 saat</option>
              <option value="1440">24 saat</option>
            </select>
            <Input
              value={runtimeAlertFilters.symbol}
              onChange={(event) => setRuntimeAlertFilters((prev) => ({ ...prev, symbol: event.target.value }))}
              placeholder="symbol"
              className="h-9 bg-slate-950 text-xs"
              data-testid="admin-dashboard-runtime-alert-filter-symbol"
            />
            <Input
              value={runtimeAlertFilters.user_id}
              onChange={(event) => setRuntimeAlertFilters((prev) => ({ ...prev, user_id: event.target.value }))}
              placeholder="user"
              className="h-9 bg-slate-950 text-xs"
              data-testid="admin-dashboard-runtime-alert-filter-user"
            />
            <Button variant="outline" size="sm" onClick={loadDashboard} data-testid="admin-dashboard-runtime-alert-filter-apply-button">Apply</Button>
          </div>

          <div className="mt-2 max-h-52 space-y-2 overflow-auto" data-testid="admin-dashboard-runtime-alerts-list">
            {runtimeAlerts.slice(0, 8).map((item) => (
              <article key={item.id} className="border border-slate-700 p-2 text-xs" data-testid={`admin-dashboard-runtime-alert-item-${item.id}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded border border-slate-600 px-1" data-testid={`admin-dashboard-runtime-alert-item-severity-${item.id}`}>{item.severity}</span>
                  <span className="rounded border border-slate-600 px-1" data-testid={`admin-dashboard-runtime-alert-item-state-${item.id}`}>{item.status}</span>
                  <span data-testid={`admin-dashboard-runtime-alert-item-type-${item.id}`}>{item.alert_type}</span>
                </div>
                <p className="mt-1 text-slate-300" data-testid={`admin-dashboard-runtime-alert-item-message-${item.id}`}>{item.message}</p>
                <p className="mt-1 text-cyan-300" data-testid={`admin-dashboard-runtime-alert-item-suggested-action-${item.id}`}>{item?.suggestion?.suggested_action || "-"}</p>
                <p className="text-slate-500" data-testid={`admin-dashboard-runtime-alert-item-runbook-hint-${item.id}`}>runbook: {item?.suggestion?.runbook_hint || "-"}</p>

                <div className="mt-2 flex flex-wrap gap-1" data-testid={`admin-dashboard-runtime-alert-item-actions-${item.id}`}>
                  <Button size="sm" variant="outline" onClick={() => handleRuntimeAlertAction(item.id, "acknowledge")} data-testid={`admin-dashboard-runtime-alert-item-ack-${item.id}`}>Ack</Button>
                  <Button size="sm" variant="outline" onClick={() => handleRuntimeAlertAction(item.id, "mute_temporarily", { minutes: 15, note: "mute_15m" })} data-testid={`admin-dashboard-runtime-alert-item-mute-15m-${item.id}`}>Mute 15m</Button>
                  <Button size="sm" variant="outline" onClick={() => handleRuntimeAlertAction(item.id, "mute_temporarily", { minutes: 60, note: "mute_1h" })} data-testid={`admin-dashboard-runtime-alert-item-mute-1h-${item.id}`}>Mute 1h</Button>
                  <Button size="sm" variant="outline" onClick={() => handleRuntimeAlertAction(item.id, "mute_temporarily", { minutes: 1440, note: "mute_24h" })} data-testid={`admin-dashboard-runtime-alert-item-mute-24h-${item.id}`}>Mute 24h</Button>
                  <Button size="sm" variant="outline" onClick={() => handleRuntimeAlertAction(item.id, "resolve", { note: "resolved_from_dashboard" })} data-testid={`admin-dashboard-runtime-alert-item-resolve-${item.id}`}>Resolve</Button>
                  <Button size="sm" variant="outline" onClick={() => handleRuntimeAlertAction(item.id, "escalate", { note: "escalated_from_dashboard" })} data-testid={`admin-dashboard-runtime-alert-item-escalate-${item.id}`}>Escalate</Button>
                </div>

                <div className="mt-2 flex gap-2">
                  <Input
                    value={alertNoteDrafts[item.id] || ""}
                    onChange={(event) => setAlertNoteDrafts((prev) => ({ ...prev, [item.id]: event.target.value }))}
                    placeholder="operator note"
                    className="h-8 bg-slate-950 text-xs"
                    data-testid={`admin-dashboard-runtime-alert-item-note-input-${item.id}`}
                  />
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleRuntimeAlertAction(item.id, "attach_note", { note: alertNoteDrafts[item.id] || "" })}
                    data-testid={`admin-dashboard-runtime-alert-item-note-save-${item.id}`}
                  >
                    Note
                  </Button>
                </div>
              </article>
            ))}
            {runtimeAlerts.length === 0 && <p data-testid="admin-dashboard-runtime-alerts-empty">Runtime alert yok</p>}
          </div>
        </article>

        <article className="border border-cyan-700/40 bg-slate-900 p-3" data-testid="admin-dashboard-runtime-smoke-card">
          <p className="text-xs uppercase tracking-widest text-cyan-300" data-testid="admin-dashboard-runtime-smoke-title">Son Smoke Sonucu</p>
          <div className="mt-2 space-y-1 text-xs" data-testid="admin-dashboard-runtime-smoke-content">
            <p data-testid="admin-dashboard-runtime-smoke-status">status: {runtimeSmoke?.run_status || "no_data"}</p>
            <p data-testid="admin-dashboard-runtime-smoke-summary">summary: {runtimeSmoke?.summary || "-"}</p>
            <p data-testid="admin-dashboard-runtime-smoke-completed-at">completed_at: {runtimeSmoke?.completed_at || "-"}</p>
            <p data-testid="admin-dashboard-runtime-execution-mode">mode: {runtimeExecutionMode?.mode || "sim"}</p>
            <p data-testid="admin-dashboard-runtime-canary-mode">canary: {runtimeExecutionMode?.flags?.CANARY_MODE || "false"}</p>
            <p data-testid="admin-dashboard-runtime-kill-switch-status">kill_switch: {runtimeKillSwitch?.active ? "ACTIVE" : "INACTIVE"}</p>
            <p data-testid="admin-dashboard-runtime-kill-switch-reason">reason: {runtimeKillSwitch?.reason || "-"}</p>
            <div className="flex gap-2 pt-1" data-testid="admin-dashboard-runtime-kill-switch-actions">
              <Button size="sm" variant="outline" onClick={() => handleKillSwitchAction("activate")} data-testid="admin-dashboard-runtime-kill-switch-activate-button">Kill ON</Button>
              <Button size="sm" variant="outline" onClick={() => handleKillSwitchAction("deactivate")} data-testid="admin-dashboard-runtime-kill-switch-deactivate-button">Kill OFF</Button>
            </div>
          </div>
        </article>

        <article className="border border-lime-700/40 bg-slate-900 p-3 md:col-span-2" data-testid="admin-dashboard-runtime-readiness-card">
          <div className="flex flex-wrap items-center justify-between gap-2" data-testid="admin-dashboard-runtime-readiness-header">
            <p className="text-xs uppercase tracking-widest text-lime-300" data-testid="admin-dashboard-runtime-readiness-title">Canary Readiness & Go/No-Go</p>
            <span
              className={`rounded border px-2 py-1 text-xs ${runtimeReadiness?.status === "READY" ? "border-emerald-500 text-emerald-300" : runtimeReadiness?.status === "WARNING" ? "border-amber-500 text-amber-300" : "border-rose-500 text-rose-300"}`}
              data-testid="admin-dashboard-runtime-readiness-status"
            >
              {runtimeReadiness?.status || "NOT_READY"}
            </span>
          </div>

          <div className="mt-2 grid gap-2 text-xs md:grid-cols-2" data-testid="admin-dashboard-runtime-readiness-content">
            <div className="space-y-1" data-testid="admin-dashboard-runtime-readiness-score-block">
              <p data-testid="admin-dashboard-runtime-readiness-score">score: {runtimeReadiness?.score ?? 0}</p>
              <p data-testid="admin-dashboard-runtime-readiness-component-execution">execution: {String(runtimeReadiness?.components?.execution ?? false)}</p>
              <p data-testid="admin-dashboard-runtime-readiness-component-pnl">pnl: {String(runtimeReadiness?.components?.pnl ?? false)}</p>
              <p data-testid="admin-dashboard-runtime-readiness-component-alerts">alerts: {String(runtimeReadiness?.components?.alerts ?? false)}</p>
              <p data-testid="admin-dashboard-runtime-readiness-component-smoke">smoke: {runtimeReadiness?.components?.smoke || "NO_DATA"}</p>
              <p data-testid="admin-dashboard-runtime-readiness-component-exchange">exchange: {String(runtimeReadiness?.components?.exchange ?? false)}</p>
            </div>

            <div className="space-y-1" data-testid="admin-dashboard-runtime-go-live-block">
              <p data-testid="admin-dashboard-runtime-go-live-decision">go_live: {String(runtimeGoLiveChecklist?.go_live ?? false)}</p>
              <p data-testid="admin-dashboard-runtime-go-live-queue-backlog">queue_backlog: {runtimeGoLiveChecklist?.metrics?.queue_backlog ?? "-"}</p>
              <p data-testid="admin-dashboard-runtime-go-live-critical-alerts">critical_alerts_30m: {runtimeGoLiveChecklist?.metrics?.critical_open_alerts_30m ?? "-"}</p>
              <p data-testid="admin-dashboard-runtime-go-live-smoke-status">smoke_status: {runtimeGoLiveChecklist?.metrics?.smoke_status || "-"}</p>
              <p data-testid="admin-dashboard-runtime-go-live-proxy-spot-mismatch">spot_proxy_mismatch: {String(runtimeProxyHealth?.spot?.proxy_token_mismatch ?? false)}</p>
              <p data-testid="admin-dashboard-runtime-go-live-proxy-futures-mismatch">futures_proxy_mismatch: {String(runtimeProxyHealth?.futures?.proxy_token_mismatch ?? false)}</p>
            </div>
          </div>

          <div className="mt-2 flex flex-wrap gap-2" data-testid="admin-dashboard-runtime-readiness-actions">
            <Button size="sm" variant="outline" onClick={runLiveLifecycleValidation} disabled={runtimeValidationLoading} data-testid="admin-dashboard-runtime-readiness-run-live-lifecycle-button">
              Live Lifecycle Run
            </Button>
            <Button size="sm" variant="outline" onClick={runCanaryValidation} disabled={runtimeValidationLoading} data-testid="admin-dashboard-runtime-readiness-run-canary-button">
              Canary Run
            </Button>
            <Button size="sm" variant="outline" onClick={runKillSwitchRollbackValidation} disabled={runtimeValidationLoading} data-testid="admin-dashboard-runtime-readiness-run-kill-switch-verify-button">
              Kill-Switch Verify
            </Button>
            <Button size="sm" variant="outline" onClick={runFinalRegressionValidation} disabled={runtimeValidationLoading} data-testid="admin-dashboard-runtime-readiness-run-final-regression-button">
              Final Regression
            </Button>
            <Button size="sm" variant="outline" onClick={runSingleFlowDryRun} disabled={runtimeValidationLoading} data-testid="admin-dashboard-runtime-readiness-run-single-flow-dry-run-button">
              Single-Flow Dry-Run
            </Button>
            <Button size="sm" variant="outline" onClick={loadDashboard} disabled={runtimeValidationLoading} data-testid="admin-dashboard-runtime-readiness-refresh-go-live-button">
              Refresh Go/No-Go
            </Button>
          </div>

          <div className="mt-3 rounded border border-cyan-700/40 p-2" data-testid="admin-dashboard-go-live-wizard-card">
            <div className="flex flex-wrap items-center justify-between gap-2" data-testid="admin-dashboard-go-live-wizard-header">
              <p className="text-xs uppercase tracking-widest text-cyan-300" data-testid="admin-dashboard-go-live-wizard-title">Go-Live Wizard</p>
              <span className="text-xs text-slate-300" data-testid="admin-dashboard-go-live-wizard-stage">stage: {goLiveWizardState?.stage || "idle"}</span>
            </div>
            <p className="mt-1 text-xs text-slate-400" data-testid="admin-dashboard-go-live-wizard-role-lock">
              role-lock: {isSuperAdmin ? "UNLOCKED(super_admin)" : "LOCKED(super_admin only)"}
            </p>
            <div className="mt-2 flex flex-wrap gap-2" data-testid="admin-dashboard-go-live-wizard-actions">
              <Button size="sm" variant="outline" onClick={runWizardReadinessCheck} disabled={runtimeValidationLoading || !isSuperAdmin} data-testid="admin-dashboard-go-live-wizard-readiness-check-button">1) Readiness Check</Button>
              <Button size="sm" variant="outline" onClick={runWizardCanaryCheck} disabled={runtimeValidationLoading || !isSuperAdmin} data-testid="admin-dashboard-go-live-wizard-canary-check-button">2) Canary PASS Check</Button>
              <Button size="sm" variant="outline" onClick={runWizardArm} disabled={runtimeValidationLoading || !isSuperAdmin} data-testid="admin-dashboard-go-live-wizard-arm-button">3) Live Arm</Button>
              <Button size="sm" variant="outline" onClick={runWizardConfirm} disabled={runtimeValidationLoading || !isSuperAdmin} data-testid="admin-dashboard-go-live-wizard-confirm-button">4) Confirm</Button>
              <Button size="sm" variant="outline" onClick={runWizardRollback} disabled={runtimeValidationLoading || !isSuperAdmin} data-testid="admin-dashboard-go-live-wizard-rollback-button">Rollback</Button>
            </div>
            <p className="mt-2 text-xs text-slate-300" data-testid="admin-dashboard-go-live-wizard-state-flags">
              armed={String(goLiveWizardState?.armed || false)} · confirmed={String(goLiveWizardState?.confirmed || false)} · rolled_back={String(goLiveWizardState?.rolled_back || false)}
            </p>
          </div>

          {Array.isArray(runtimeGoLiveChecklist?.reasons) && runtimeGoLiveChecklist.reasons.length > 0 && (
            <div className="mt-2 space-y-1" data-testid="admin-dashboard-runtime-go-live-reasons-list">
              {runtimeGoLiveChecklist.reasons.map((reason, index) => (
                <p key={`${reason}-${index}`} className="text-xs text-rose-300" data-testid={`admin-dashboard-runtime-go-live-reason-${index}`}>
                  - {reason}
                </p>
              ))}
            </div>
          )}

          <p className="mt-2 text-xs text-slate-400" data-testid="admin-dashboard-runtime-readiness-last-run-status">
            son_validation_status: {runtimeCanaryRunResult?.status || "-"}
          </p>
          <p className="text-xs text-slate-400" data-testid="admin-dashboard-runtime-dry-run-last-status">
            dry_run_status: {runtimeDryRunResult?.status || "-"}
          </p>
        </article>
      </div>

      <article className="border border-fuchsia-700/40 bg-slate-900 p-3" data-testid="admin-dashboard-runtime-timeline-panel">
        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="admin-dashboard-runtime-timeline-header">
          <p className="text-xs uppercase tracking-widest text-fuchsia-300" data-testid="admin-dashboard-runtime-timeline-title">Execution Timeline Stream</p>
          <div className="flex items-center gap-2 text-xs" data-testid="admin-dashboard-runtime-timeline-controls">
            <span data-testid="admin-dashboard-runtime-timeline-connection-status">ws_status: {runtimeWsStatus}</span>
            <label data-testid="admin-dashboard-runtime-timeline-auto-scroll-toggle-wrapper">
              <input type="checkbox" checked={timelineAutoScroll} onChange={(event) => setTimelineAutoScroll(event.target.checked)} data-testid="admin-dashboard-runtime-timeline-auto-scroll-toggle" />
              auto-scroll
            </label>
          </div>
        </div>
        <div ref={timelineContainerRef} className="mt-2 max-h-48 space-y-1 overflow-auto text-xs" data-testid="admin-dashboard-runtime-timeline-list">
          {runtimeTimelineFiltered.map((event, index) => (
            <div key={`${event?.order_id || 'no-order'}-${event?.timestamp || index}-${index}`} className="border border-slate-700 px-2 py-1" data-testid={`admin-dashboard-runtime-timeline-item-${index}`}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded border border-slate-600 px-1" data-testid={`admin-dashboard-runtime-timeline-item-severity-${index}`}>{event?.severity || "INFO"}</span>
                <span className="rounded border border-slate-600 px-1" data-testid={`admin-dashboard-runtime-timeline-item-state-${index}`}>{event?.state || "-"}</span>
                <span data-testid={`admin-dashboard-runtime-timeline-item-symbol-${index}`}>{event?.symbol || "-"}</span>
                <span data-testid={`admin-dashboard-runtime-timeline-item-user-${index}`}>{event?.user_id || "-"}</span>
              </div>
              <p className="text-slate-400" data-testid={`admin-dashboard-runtime-timeline-item-timestamp-${index}`}>{event?.timestamp || "-"}</p>
              {(event?.meta?.reject_reason || event?.meta?.fail_reason) && (
                <p className="text-red-300" data-testid={`admin-dashboard-runtime-timeline-item-error-${index}`}>reason: {event?.meta?.reject_reason || event?.meta?.fail_reason}</p>
              )}
            </div>
          ))}
          {runtimeTimelineFiltered.length === 0 && <p data-testid="admin-dashboard-runtime-timeline-empty">Timeline event yok</p>}
        </div>
      </article>

      <div className="border border-cyan-700/60 bg-slate-900 p-4" data-testid="admin-dashboard-global-action-toolbar">
        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="admin-dashboard-global-action-toolbar-header">
          <p className="text-xs uppercase tracking-widest text-cyan-300" data-testid="admin-dashboard-global-action-toolbar-title">Global Action Toolbar</p>
          {!isManagerRole && (
            <p className="text-xs text-amber-300" data-testid="admin-dashboard-global-action-toolbar-lock">LOCKED: kritik aksiyonlar sadece super_admin + admin</p>
          )}
        </div>
        <fieldset
          disabled={!isManagerRole}
          className="mt-3 flex flex-wrap gap-2 disabled:cursor-not-allowed disabled:opacity-70"
          data-testid="admin-dashboard-global-action-toolbar-actions"
        >
          <Button
            className="bg-red-700 text-white hover:bg-red-800"
            onClick={() => openCriticalDialog("kill_on")}
            disabled={!isManagerRole || killSwitchActive}
            data-testid="admin-dashboard-kill-switch-enable-button"
          >
            Kill Switch (2-Step Onay)
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
            Restart Services (2-Step Onay)
          </Button>
          <Button
            variant="outline"
            onClick={() => openCriticalDialog("clear_all_alerts")}
            disabled={!isManagerRole}
            data-testid="admin-dashboard-clear-all-alerts-button"
          >
            Clear All Alerts (2-Step Onay)
          </Button>
        </fieldset>
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
                className="flex cursor-pointer items-center justify-between border border-slate-700 px-2 py-2 text-left text-xs transition-colors hover:border-cyan-400"
                data-testid={`admin-dashboard-action-center-drilldown-${item.key}`}
              >
                <span className="underline decoration-dotted">{item.label} · drilldown</span>
                <span className="flex items-center gap-2">
                  <span className="font-semibold" data-testid={`admin-dashboard-action-center-value-${item.key}`}>
                    {String(actionCenterSummary?.[item.key] ?? "-")}
                  </span>
                  <span className="text-cyan-300" data-testid={`admin-dashboard-action-center-open-icon-${item.key}`}>↗</span>
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
              <Button
                variant="outline"
                size="sm"
                onClick={() => navigateToAuditContext({ action: "ACTION_CENTER_CLOSE_NEXT_ACTIONS" })}
                data-testid="admin-dashboard-auto-close-context-audit-link-button"
              >
                Context Audit
              </Button>
            </div>
          ) : (
            <div className="mt-2 space-y-2" data-testid="admin-dashboard-action-center-result-empty">
              <p className="text-xs text-slate-400" data-testid="admin-dashboard-action-center-result-empty-text">Henüz auto-close çalıştırılmadı.</p>
              {latestAutoCloseAudit && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => navigateToAuditContext({ action: latestAutoCloseAudit.action || "ACTION_CENTER_CLOSE_NEXT_ACTIONS" })}
                  data-testid="admin-dashboard-auto-close-last-log-button"
                >
                  Son Auto-Close Logunu Aç
                </Button>
              )}
            </div>
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
              <Button
                variant="outline"
                size="sm"
                className="mt-2"
                onClick={() =>
                  navigateToAuditContext({
                    action: item.action,
                    requestId: item?.details?.request_id,
                    sessionId: item?.details?.session_id,
                  })
                }
                data-testid={`admin-dashboard-incident-history-context-link-${index}`}
              >
                Bu Aksiyonun Logu
              </Button>
            </article>
          ))}
          {(incidentHistory?.audit_events || []).length === 0 && (
            <p className="text-xs text-slate-500" data-testid="admin-dashboard-incident-history-empty">Incident kaydı yok.</p>
          )}
        </div>
      </div>

      <div className="border border-fuchsia-700/40 bg-slate-900 p-3" data-testid="admin-dashboard-action-audit-snippet-panel">
        <div className="flex items-center justify-between" data-testid="admin-dashboard-action-audit-snippet-header">
          <p className="text-xs uppercase tracking-widest text-fuchsia-300" data-testid="admin-dashboard-action-audit-snippet-title">Global Action Audit Snippet</p>
          <Button variant="outline" onClick={() => navigate("/admin/action-audit")} data-testid="admin-dashboard-action-audit-open-page-button">Detay</Button>
        </div>
        <div className="mt-2 max-h-32 space-y-1 overflow-auto" data-testid="admin-dashboard-action-audit-snippet-list">
          {actionAuditSnippet.slice(0, 8).map((item, index) => (
            <article key={`${item.id}-${index}`} className="border border-fuchsia-700/40 p-2 text-xs" data-testid={`admin-dashboard-action-audit-snippet-item-${index}`}>
              <p data-testid={`admin-dashboard-action-audit-snippet-action-${index}`}>{item.action}</p>
              <p className="text-slate-400" data-testid={`admin-dashboard-action-audit-snippet-meta-${index}`}>{item.created_at} · {item.actor_role}</p>
            </article>
          ))}
          {actionAuditSnippet.length === 0 && (
            <p className="text-xs text-slate-500" data-testid="admin-dashboard-action-audit-snippet-empty">Action audit kaydı yok.</p>
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
          Bulk ACK Flow ({selectedAlertIds.length})
        </Button>
        <p className="text-xs text-slate-500" data-testid="admin-alerts-bulk-ack-flow-hint">
          Flow: Select → Bulk ACK Flow → reason + phrase → Onayla
        </p>
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
                  <span className="ml-1" data-testid={`admin-alert-service-${alert.id}`}>service={String(alert.source || "core").split(".")[0]}</span>
                  <p className="text-slate-300" data-testid={`admin-alert-message-${alert.id}`}>{alert.message}</p>
                </div>
                <div className="flex flex-wrap gap-2" data-testid={`admin-alert-actions-${alert.id}`}>
                  <Button
                    size="sm"
                    variant="outline"
                    className="border-red-400 bg-transparent text-red-300"
                    onClick={() => ackSingleAlert(alert.id)}
                    disabled={!isManagerRole}
                    data-testid={`admin-alert-ack-${alert.id}`}
                  >
                    Mute / Ack
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
                    onClick={() =>
                      navigateToAuditContext({
                        action: "ACTION_CENTER",
                        q: String(alert.root_cause_code || alert.alert_type || "").trim(),
                      })
                    }
                    data-testid={`admin-alert-root-cause-link-${alert.id}`}
                  >
                    Investigate
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => openCriticalDialog("restart_services", { reasonHint: `${alert.id}_restart_from_alert` })}
                    disabled={!isManagerRole}
                    data-testid={`admin-alert-restart-service-${alert.id}`}
                  >
                    Restart Service
                  </Button>
                  <Button
                    size="sm"
                    className="bg-emerald-700 text-white hover:bg-emerald-800"
                    onClick={() => executeSuggestedAction(alert)}
                    disabled={
                      !isManagerRole
                      && ["auto_close_run", "restart_services"].includes(alert?.recommendation?.suggested_action?.action_key)
                    }
                    data-testid={`admin-alert-suggested-action-${alert.id}`}
                  >
                    {alert?.recommendation?.suggested_action?.action_label || "Önerilen Aksiyon"}
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
          const cardClass = threshold.level === "critical" ? "bg-red-950/40" : threshold.level === "warning" ? "bg-amber-950/20" : "bg-slate-900";

          return (
            <button
              key={item.key}
              type="button"
              className={`border p-3 text-left transition-colors hover:border-cyan-400 ${borderClass} ${cardClass}`}
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
        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="admin-critical-actions-header">
          <p className="text-xs uppercase tracking-widest text-red-300" data-testid="admin-critical-actions-title">Kritik Kontrol Alanı</p>
          <p className="text-xs text-red-200" data-testid="admin-critical-actions-role-lock-badge">
            role-lock: {isManagerRole ? "UNLOCKED" : "LOCKED"}
          </p>
        </div>
        <p className="mt-2 text-xs text-red-200" data-testid="admin-critical-actions-double-confirm-visible">Double-confirm aktif: işlem için reason + phrase zorunlu.</p>
        {!isManagerRole && (
          <p className="mt-1 text-xs text-amber-300" data-testid="admin-critical-actions-rbac-warning">
            Bu bölümde çalıştırma yetkisi yok. Sadece super_admin + admin aksiyon başlatabilir.
          </p>
        )}
        <fieldset
          disabled={!isManagerRole}
          className="mt-3 grid gap-2 md:grid-cols-2 disabled:cursor-not-allowed disabled:opacity-70"
          data-testid="admin-critical-actions-grid"
        >
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
        </fieldset>
        {(incidentHistory?.audit_events || []).length > 0 && (
          <div className="mt-3 rounded border border-red-700/50 bg-black/20 p-2 text-xs" data-testid="admin-critical-actions-last-operation-panel">
            <p className="font-semibold text-red-200" data-testid="admin-critical-actions-last-operation-title">Son Kritik Aksiyon</p>
            <p data-testid="admin-critical-actions-last-operation-action">action: {incidentHistory.audit_events[0]?.action || "-"}</p>
            <p data-testid="admin-critical-actions-last-operation-actor">actor_role: {incidentHistory.audit_events[0]?.actor_role || "-"}</p>
            <Button
              variant="outline"
              size="sm"
              className="mt-2"
              onClick={() =>
                navigateToAuditContext({
                  action: incidentHistory.audit_events[0]?.action,
                  requestId: incidentHistory.audit_events[0]?.details?.request_id,
                  sessionId: incidentHistory.audit_events[0]?.details?.session_id,
                })
              }
              data-testid="admin-critical-actions-last-operation-log-link"
            >
              Bu İşlemin Logu
            </Button>
          </div>
        )}
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
            <p className="text-xs text-slate-300" data-testid="admin-dashboard-critical-confirm-step-indicator">
              execution_step: {criticalDialogState.step}/2
            </p>
            <div data-testid="admin-dashboard-critical-confirm-reason-field">
              <p className="text-xs text-slate-400">Step 1 · Reason</p>
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

            {criticalDialogState.step >= 2 && (
              <div data-testid="admin-dashboard-critical-confirm-phrase-field">
                <p className="text-xs text-slate-400">
                  Step 2 · Confirm phrase: <span data-testid="admin-dashboard-critical-confirm-expected-phrase">{ACTION_CONFIG[criticalDialogState.actionKey]?.expectedPhrase || "-"}</span>
                </p>
                <Input
                  value={criticalDialogState.phrase}
                  onChange={(event) => setCriticalDialogState((prev) => ({ ...prev, phrase: event.target.value }))}
                  className="mt-1 bg-slate-900"
                  data-testid="admin-dashboard-critical-confirm-phrase-input"
                />
              </div>
            )}
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setCriticalDialogState((prev) => ({ ...prev, open: false }))}
              data-testid="admin-dashboard-critical-confirm-cancel-button"
            >
              Vazgeç
            </Button>
            {criticalDialogState.step === 1 ? (
              <Button onClick={advanceCriticalStep} disabled={!isManagerRole} data-testid="admin-dashboard-critical-confirm-step1-button">
                1. Adımı Tamamla
              </Button>
            ) : (
              <Button onClick={runCriticalAction} disabled={!isManagerRole} data-testid="admin-dashboard-critical-confirm-submit-button">
                2. Adım: Onayla ve Çalıştır
              </Button>
            )}
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
              <p className="mt-1 text-xs text-slate-400" data-testid="admin-dashboard-alert-detail-service-action-map">
                service={String(alertDetail?.source || "core").split(".")[0]} → action={alertDetail?.recommendation?.suggested_action?.action_label || "investigate"}
              </p>
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
                <Button
                  size="sm"
                  className="bg-emerald-700 text-white hover:bg-emerald-800"
                  onClick={() => executeSuggestedAction(alertDetail)}
                  disabled={
                    !isManagerRole
                    && ["auto_close_run", "restart_services"].includes(alertDetail?.recommendation?.suggested_action?.action_key)
                  }
                  data-testid="admin-dashboard-alert-detail-suggested-action-button"
                >
                  {alertDetail?.recommendation?.suggested_action?.action_label || "Önerilen Aksiyonu Uygula"}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    navigateToAuditContext({
                      action: "ACTION_CENTER",
                      q: String(alertDetail?.root_cause_code || alertDetail?.alert_type || "").trim(),
                    })
                  }
                  data-testid="admin-dashboard-alert-detail-context-audit-button"
                >
                  Context Audit
                </Button>
              </div>
            </div>
            <pre className="max-h-52 overflow-auto border border-slate-700 bg-black p-2 text-[11px]" data-testid="admin-dashboard-alert-detail-json">
              {JSON.stringify(alertDetail?.details || {}, null, 2)}
            </pre>

            <div className="rounded border border-slate-700 bg-slate-900 p-2" data-testid="admin-dashboard-alert-detail-event-chain-panel">
              <p className="font-semibold" data-testid="admin-dashboard-alert-detail-event-chain-title">Event Chain / Timeline</p>
              {alertDetailTimelineLoading ? (
                <p className="mt-2 text-xs text-slate-400" data-testid="admin-dashboard-alert-detail-event-chain-loading">yükleniyor...</p>
              ) : (
                <div className="mt-2 max-h-44 space-y-1 overflow-auto" data-testid="admin-dashboard-alert-detail-event-chain-list">
                  {alertDetailTimeline.slice(0, 10).map((item, idx) => (
                    <article key={`${item.id}-${idx}`} className="border border-slate-700 p-2 text-[11px]" data-testid={`admin-dashboard-alert-detail-event-chain-item-${idx}`}>
                      <p data-testid={`admin-dashboard-alert-detail-event-chain-action-${idx}`}>{item.action}</p>
                      <p className="text-slate-400" data-testid={`admin-dashboard-alert-detail-event-chain-meta-${idx}`}>
                        {item.created_at ? new Date(item.created_at).toLocaleString() : "-"} · {item.actor_role || "system"}
                      </p>
                    </article>
                  ))}
                  {alertDetailTimeline.length === 0 && (
                    <p className="text-xs text-slate-500" data-testid="admin-dashboard-alert-detail-event-chain-empty">İlgili event chain bulunamadı.</p>
                  )}
                </div>
              )}
            </div>
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
            <Button
              variant="outline"
              onClick={() => navigateToAuditContext({ action: "ACTION_CENTER_CLOSE_NEXT_ACTIONS" })}
              data-testid="admin-dashboard-auto-close-result-audit-link-button"
            >
              Auto-Close Context Audit
            </Button>
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
