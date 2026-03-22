import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CartesianGrid, Line, LineChart, Tooltip, XAxis, YAxis } from "recharts";
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
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";

const ACTION_META = {
  ws_reconnect: { endpoint: "/runtime/ws/reconnect", phrase: "RECONNECT WS", panelKey: "control" },
  ws_new_session: { endpoint: "/runtime/ws/force-new-session", phrase: "FORCE NEW WS SESSION", panelKey: "control" },
  pipeline_resync: { endpoint: "/runtime/pipeline/resync", phrase: "FORCE PIPELINE RESYNC", panelKey: "control" },
  pipeline_flush: { endpoint: "/runtime/pipeline/flush", phrase: "FLUSH PIPELINE", panelKey: "control" },
  gate_recheck: { endpoint: "/runtime/gate/recheck", phrase: "RECHECK RELEASE GATE", panelKey: "control" },
  service_restart: { endpoint: "/runtime/service/restart", phrase: "RESTART SERVICE", panelKey: "recovery" },
  policy_update: { endpoint: "/runtime/alert-policy", phrase: "UPDATE ALERT POLICY", panelKey: "control", method: "put" },
  policy_rollback: { endpoint: "/runtime/alert-policy/rollback", phrase: "ROLLBACK ALERT POLICY", panelKey: "control" },
  policy_test_alert: { endpoint: "/runtime/alert-policy/test-alert", phrase: "SEND TEST ALERT", panelKey: "control" },
  exchange_revalidate: { endpoint: "/runtime/exchange/revalidate/{connection_id}", phrase: "REVALIDATE EXCHANGE", panelKey: "monitoring" },
  exchange_disable: { endpoint: "/runtime/exchange/disable-key/{connection_id}", phrase: "DISABLE EXCHANGE KEY", panelKey: "monitoring" },
  scanner_start: { endpoint: "/admin/universe-monitor/scanner/start", phrase: "START SCANNER", panelKey: "scannerOps" },
  scanner_stop: { endpoint: "/admin/universe-monitor/scanner/stop", phrase: "STOP SCANNER", panelKey: "scannerOps" },
  scanner_trigger: { endpoint: "/admin/universe-monitor/scanner/trigger", phrase: "TRIGGER MANUAL SCAN", panelKey: "scannerOps" },
  scanner_whitelist_update: { endpoint: "/admin/universe-monitor/scanner/symbol-lists/whitelist", phrase: "UPDATE SYMBOL LIST", panelKey: "scannerOps" },
  scanner_blacklist_update: { endpoint: "/admin/universe-monitor/scanner/symbol-lists/blacklist", phrase: "UPDATE SYMBOL LIST", panelKey: "scannerOps" },
  universe_bulk_toggle: { endpoint: "/admin/universe-monitor/universe/symbols/bulk-toggle", phrase: "BULK UPDATE SYMBOLS", panelKey: "scannerOps" },
  universe_filter_update: { endpoint: "/admin/universe-monitor/universe/filter-config", phrase: "UPDATE FILTER CONFIG", panelKey: "scannerOps" },
  rollout_promote: { endpoint: "/admin/universe-monitor/rollout/promote", phrase: "PROMOTE ROLLOUT", panelKey: "rolloutOps" },
  rollout_demote: { endpoint: "/admin/universe-monitor/rollout/demote", phrase: "DEMOTE ROLLOUT", panelKey: "rolloutOps" },
  rollout_rollback: { endpoint: "/admin/universe-monitor/rollout/rollback", phrase: "ROLLBACK ROLLOUT", panelKey: "rolloutOps" },
  risk_exposure_limit: { endpoint: "/admin/universe-monitor/risk/exposure-limit", phrase: "UPDATE EXPOSURE LIMIT", panelKey: "riskOps", method: "put" },
  risk_exposure_override: { endpoint: "/admin/universe-monitor/risk/exposure-override", phrase: "APPLY EXPOSURE OVERRIDE", panelKey: "riskOps" },
  strategy_disable: { endpoint: "/admin/universe-monitor/strategy/{strategy_id}/disable", phrase: "DISABLE STRATEGY", panelKey: "slowOps" },
  strategy_throttle: { endpoint: "/admin/universe-monitor/strategy/{strategy_id}/throttle", phrase: "THROTTLE STRATEGY", panelKey: "slowOps" },
  symbol_pause: { endpoint: "/admin/universe-monitor/symbol/{symbol}/pause", phrase: "PAUSE SYMBOL", panelKey: "slowOps" },
  freshness_sla_update: { endpoint: "/admin/universe-monitor/freshness/sla-config", phrase: "UPDATE SLA CONFIG", panelKey: "freshnessOps", method: "put" },
  freshness_rescan_stale: { endpoint: "/admin/universe-monitor/scanner/rescan-stale", phrase: "RESCAN STALE", panelKey: "freshnessOps" },
  kpi_generate: { endpoint: "/admin/universe-monitor/recommendation/generate", phrase: "GENERATE KPI RECOMMENDATION", panelKey: "kpiOps" },
  kpi_apply: { endpoint: "/admin/universe-monitor/recommendation/apply", phrase: "APPLY RECOMMENDATION", panelKey: "kpiOps" },
  kpi_reject: { endpoint: "/admin/universe-monitor/recommendation/reject", phrase: "REJECT RECOMMENDATION", panelKey: "kpiOps" },
  kpi_postpone: { endpoint: "/admin/universe-monitor/recommendation/postpone", phrase: "POSTPONE RECOMMENDATION", panelKey: "kpiOps" },
};

const extractErrorMeta = (error) => {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") {
    return { traceId: "-", message: detail };
  }
  const traceId = detail?.trace_id || error?.response?.data?.trace_id || "-";
  const message = detail?.message || detail?.error_code || JSON.stringify(detail || {});
  return { traceId, message };
};

const ResultBadge = ({ result, testId }) => {
  if (!result) {
    return <p className="text-xs text-slate-500" data-testid={`${testId}-empty`}>Henüz aksiyon sonucu yok.</p>;
  }

  return (
    <div className="space-y-1 text-xs text-emerald-200" data-testid={`${testId}-payload`}>
      <p className="font-semibold text-emerald-300" data-testid={`${testId}-last-action-result-label`}>last_action_result</p>
      <p data-testid={`${testId}-status`}>status={result.status || "-"}</p>
      <p data-testid={`${testId}-trace-id`}>trace_id={result.trace_id || "-"}</p>
      <p data-testid={`${testId}-message`}>message={result.message || "-"}</p>
      <p data-testid={`${testId}-state-snapshot`}>state_snapshot={JSON.stringify(result.state_snapshot || {}).slice(0, 180)}</p>
    </div>
  );
};

const PanelShell = ({ title, subtitle, stateNode, reasonNode, actionNode, resultNode, testId }) => (
  <article className="rounded-xl border border-slate-700 bg-slate-900/90 p-4" data-testid={testId}>
    <div className="mb-3" data-testid={`${testId}-header`}>
      <h3 className="text-base font-semibold text-slate-100" data-testid={`${testId}-title`}>{title}</h3>
      <p className="text-xs text-slate-400" data-testid={`${testId}-subtitle`}>{subtitle}</p>
    </div>
    <div className="grid gap-3 md:grid-cols-4" data-testid={`${testId}-quad-grid`}>
      <section className="rounded border border-slate-700 bg-black/20 p-2" data-testid={`${testId}-state-block`}>
        <p className="text-[11px] uppercase tracking-wider text-cyan-300" data-testid={`${testId}-state-label`}>State</p>
        <div className="mt-2" data-testid={`${testId}-state-content`}>{stateNode}</div>
      </section>
      <section className="rounded border border-slate-700 bg-black/20 p-2" data-testid={`${testId}-reason-block`}>
        <p className="text-[11px] uppercase tracking-wider text-amber-300" data-testid={`${testId}-reason-label`}>Reason</p>
        <div className="mt-2" data-testid={`${testId}-reason-content`}>{reasonNode}</div>
      </section>
      <section className="rounded border border-slate-700 bg-black/20 p-2" data-testid={`${testId}-action-block`}>
        <p className="text-[11px] uppercase tracking-wider text-rose-300" data-testid={`${testId}-action-label`}>Action</p>
        <div className="mt-2" data-testid={`${testId}-action-content`}>{actionNode}</div>
      </section>
      <section className="rounded border border-slate-700 bg-black/20 p-2" data-testid={`${testId}-result-block`}>
        <p className="text-[11px] uppercase tracking-wider text-emerald-300" data-testid={`${testId}-result-label`}>Result</p>
        <div className="mt-2" data-testid={`${testId}-result-content`}>{resultNode}</div>
      </section>
    </div>
  </article>
);

const SummaryBar = ({ wsHealth, gateStatus, overridesActive, alertsHistory, allowedQuoteAssets, testId }) => (
  <section className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5" data-testid={testId}>
    <div className="rounded-lg border border-cyan-700/50 bg-cyan-950/20 p-3" data-testid={`${testId}-ws-card`}>
      <p className="text-xs text-cyan-300" data-testid={`${testId}-ws-label`}>WS Session</p>
      <p className="mt-1 text-sm font-semibold" data-testid={`${testId}-ws-value`}>{wsHealth?.state?.session_id || "-"}</p>
    </div>
    <div className="rounded-lg border border-red-700/50 bg-red-950/20 p-3" data-testid={`${testId}-gate-card`}>
      <p className="text-xs text-red-300" data-testid={`${testId}-gate-label`}>Gate</p>
      <p className="mt-1 text-sm font-semibold" data-testid={`${testId}-gate-value`}>{gateStatus?.status || "-"}</p>
    </div>
    <div className="rounded-lg border border-amber-700/50 bg-amber-950/20 p-3" data-testid={`${testId}-override-card`}>
      <p className="text-xs text-amber-300" data-testid={`${testId}-override-label`}>Active Override</p>
      <p className="mt-1 text-sm font-semibold" data-testid={`${testId}-override-value`}>{overridesActive.length}</p>
    </div>
    <div className="rounded-lg border border-violet-700/50 bg-violet-950/20 p-3" data-testid={`${testId}-alert-card`}>
      <p className="text-xs text-violet-300" data-testid={`${testId}-alert-label`}>Open Alerts</p>
      <p className="mt-1 text-sm font-semibold" data-testid={`${testId}-alert-value`}>{alertsHistory.length}</p>
    </div>
    <div className="rounded-lg border border-emerald-700/50 bg-emerald-950/20 p-3" data-testid={`${testId}-allowed-quotes-card`}>
      <p className="text-xs text-emerald-300" data-testid={`${testId}-allowed-quotes-label`}>Allowed Quote Assets</p>
      <p className="mt-1 text-sm font-semibold" data-testid={`${testId}-allowed-quotes-value`}>{(allowedQuoteAssets || []).join(", ") || "-"}</p>
    </div>
  </section>
);

export const PipelineOperationsPage = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const isSuperAdmin = String(user?.role || "") === "super_admin";
  const isProductionEnv = String(process.env.REACT_APP_ENV || "").toLowerCase() === "production";

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [globalError, setGlobalError] = useState("");
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);
  const [autoRefreshIntervalSec, setAutoRefreshIntervalSec] = useState("15");
  const [opsTab, setOpsTab] = useState("rollout");

  const [wsHealth, setWsHealth] = useState(null);
  const [gateStatus, setGateStatus] = useState(null);
  const [guardTelemetry, setGuardTelemetry] = useState(null);
  const [allowedQuoteAssets, setAllowedQuoteAssets] = useState([]);
  const [exchangeMonitoring, setExchangeMonitoring] = useState(null);
  const [hardeningAnalytics, setHardeningAnalytics] = useState([]);
  const [actionAudit, setActionAudit] = useState([]);
  const [alertsHistory, setAlertsHistory] = useState([]);
  const [alertPolicy, setAlertPolicy] = useState(null);
  const [heartbeat, setHeartbeat] = useState(null);
  const [overridesActive, setOverridesActive] = useState([]);
  const [overrideHistory, setOverrideHistory] = useState([]);

  const [serviceTarget, setServiceTarget] = useState("all");
  const [lagThreshold, setLagThreshold] = useState("60");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [alertSinceHours, setAlertSinceHours] = useState("24");
  const [alertEventFilter, setAlertEventFilter] = useState("");
  const [runtimeMode, setRuntimeMode] = useState("MOCK");
  const [scannerOps, setScannerOps] = useState({ runtime: {}, symbol_universe: [], whitelist: [], blacklist: [], manual_trigger: {} });
  const [rolloutOps, setRolloutOps] = useState(null);
  const [riskOps, setRiskOps] = useState({ cluster_exposure: [], symbol_exposure: [], config: {} });
  const [riskOverrides, setRiskOverrides] = useState([]);
  const [slowOps, setSlowOps] = useState({ disabled_strategies: [], throttled_strategies: {}, paused_symbols: [] });
  const [universeFilterConfig, setUniverseFilterConfig] = useState({ min_liquidity_usd: 1000000, min_volume_24h_usd: 5000000, max_spread_bps: 40 });
  const [freshnessSlaConfig, setFreshnessSlaConfig] = useState({ latency_threshold: 1200, stale_threshold_sec: 900 });
  const [staleEntities, setStaleEntities] = useState([]);
  const [freshnessHeatmap, setFreshnessHeatmap] = useState([]);
  const [fallbackTimeline, setFallbackTimeline] = useState([]);
  const [kpiActiveRecommendations, setKpiActiveRecommendations] = useState([]);
  const [kpiRecommendationHistory, setKpiRecommendationHistory] = useState([]);
  const [trendRange, setTrendRange] = useState("24h");
  const [trendSymbolFilter, setTrendSymbolFilter] = useState("");
  const [trendStrategyFilter, setTrendStrategyFilter] = useState("");
  const [metricsHistory, setMetricsHistory] = useState({ latency_series: [], pnl_series: [], risk_veto_series: [], overlays: [] });
  const [exportModal, setExportModal] = useState({ open: false, range: "24h", output_format: "csv", metrics: "latency_avg_ms,pnl_sum,risk_veto_count", symbol: "", strategy: "" });
  const [exportJobs, setExportJobs] = useState([]);
  const [bulkImportModal, setBulkImportModal] = useState({ open: false, csvText: "", preview: null, applyMode: "apply_valid_only" });
  const [debugPanelOpen, setDebugPanelOpen] = useState(false);
  const [debugUniversePayload, setDebugUniversePayload] = useState(null);

  const [reasonControl, setReasonControl] = useState("pipeline_control_manual_action");
  const [reasonRecovery, setReasonRecovery] = useState("pipeline_recovery_manual_action");
  const [reasonAlerts, setReasonAlerts] = useState("runtime_alert_manual_action");

  const [overrideForm, setOverrideForm] = useState({
    override_type: "risk_override",
    scope: "global",
    ttl_minutes: "30",
    reason: "runtime_override_manual",
    confirmation_phrase: "CREATE OVERRIDE",
  });
  const [alertPolicyForm, setAlertPolicyForm] = useState({
    execution_quality_warning_threshold: "60",
    execution_quality_critical_threshold: "40",
    permission_drift_warning_per_day: "2",
    permission_drift_critical_per_day: "5",
  });

  const [bulkSelection, setBulkSelection] = useState([]);
  const [bulkSymbolsInput, setBulkSymbolsInput] = useState("BTCUSDT,ETHUSDT");
  const [symbolListModal, setSymbolListModal] = useState({ open: false, listType: "whitelist", symbolsText: "" });
  const [auditDrawerOpen, setAuditDrawerOpen] = useState(false);
  const [auditDrawerTab, setAuditDrawerTab] = useState("action_audit");
  const [auditDrawerItems, setAuditDrawerItems] = useState([]);
  const [auditLogDrawerItems, setAuditLogDrawerItems] = useState([]);
  const [selectedAuditDetail, setSelectedAuditDetail] = useState(null);
  const [auditFilters, setAuditFilters] = useState({ user_id: "", action_type: "", since_hours: "24", trace_id: "" });
  const [riskLimitForm, setRiskLimitForm] = useState({ max_total_exposure_pct: "50", max_symbol_exposure_pct: "25", max_cluster_exposure_pct: "35" });
  const [riskOverrideForm, setRiskOverrideForm] = useState({ override_type: "force_allow", scope: "global", ttl_minutes: "30" });
  const [slowActionForm, setSlowActionForm] = useState({ strategy_id: "spot_pullback_v1", throttle_profile: "soft", symbol: "BTCUSDT" });
  const [stateValidation, setStateValidation] = useState({
    wsReconnectSessionChanged: false,
    overrideAffectsExecution: false,
    gateUsesCiResult: false,
    tradeBlockVisible: false,
    suggestions: {},
    lastCheckedAt: null,
  });
  const [panelResult, setPanelResult] = useState({
    control: null,
    recovery: null,
    monitoring: null,
    traceability: null,
    override: null,
    alerts: null,
    scannerOps: null,
    rolloutOps: null,
    riskOps: null,
    slowOps: null,
    freshnessOps: null,
    kpiOps: null,
  });

  const [actionDialog, setActionDialog] = useState({
    open: false,
    actionKey: "",
    reason: "",
    phrase: "",
    panelKey: "control",
    context: {},
  });

  const load = useCallback(async (showLoader = true) => {
    if (showLoader) setLoading(true);
    else setRefreshing(true);
    try {
      const [
        wsRes,
        gateRes,
        activeRes,
        historyRes,
        guardRes,
        exchangeRes,
        hardeningRes,
        alertsRes,
        policyRes,
        auditRes,
        quotePolicyRes,
        validationRes,
        scannerStateRes,
        rolloutStateRes,
        exposureRes,
        exposureOverrideRes,
        slowControlRes,
        filterConfigRes,
        freshnessSlaRes,
        staleListRes,
        heatmapRes,
        fallbackRes,
        kpiActiveRes,
        kpiHistoryRes,
        metricsHistoryRes,
        exportJobsRes,
      ] = await Promise.all([
        apiClient.get("/runtime/ws/health"),
        apiClient.get("/runtime/gate/status"),
        apiClient.get("/runtime/override/active"),
        apiClient.get("/runtime/override/history", { params: { limit: 30 } }),
        apiClient.get("/runtime/guard/telemetry", { params: { limit: 100 } }),
        apiClient.get("/runtime/exchange/monitoring", { params: { limit: 100 } }),
        apiClient.get("/runtime/hardening/analytics", { params: { time_window_hours: 48 } }),
        apiClient.get("/runtime/alerts/history", {
          params: {
            status_filter: "all",
            severity: severityFilter === "all" ? undefined : severityFilter,
            since_hours: Number(alertSinceHours || 24),
            event_type: alertEventFilter || undefined,
            limit: 100,
          },
        }),
        apiClient.get("/runtime/alert-policy"),
        apiClient.get("/runtime/action-audit", { params: { since_hours: 48, limit: 40 } }),
        apiClient.get("/runtime/quote-policy"),
        apiClient.get("/runtime/state-validation"),
        apiClient.get("/admin/universe-monitor/scanner/state"),
        apiClient.get("/admin/universe-monitor/rollout/status"),
        apiClient.get("/admin/universe-monitor/risk/exposure-clusters"),
        apiClient.get("/admin/universe-monitor/risk/exposure-override/active"),
        apiClient.get("/admin/universe-monitor/slow-controls/status"),
        apiClient.get("/admin/universe-monitor/universe/filter-config"),
        apiClient.get("/admin/universe-monitor/freshness/sla-config"),
        apiClient.get("/admin/universe-monitor/freshness/stale-list", { params: { limit: 200 } }),
        apiClient.get("/admin/universe-monitor/freshness-heatmap", { params: { window: "24h" } }),
        apiClient.get("/admin/universe-monitor/fallback-events", { params: { limit: 40 } }),
        apiClient.get("/admin/universe-monitor/recommendation/active"),
        apiClient.get("/admin/universe-monitor/recommendation/history"),
        apiClient.get("/admin/universe-monitor/metrics/history", {
          params: {
            range: trendRange,
            symbol: trendSymbolFilter || undefined,
            strategy: trendStrategyFilter || undefined,
          },
        }),
        apiClient.get("/admin/universe-monitor/export/jobs", { params: { limit: 30 } }),
      ]);

      try {
        const modeRes = await apiClient.get("/admin/live-trading/control-layer/state");
        setRuntimeMode(String(modeRes.data?.execution_mode || "MOCK").toUpperCase());
      } catch {
        setRuntimeMode("MOCK");
      }

      setWsHealth(wsRes.data || null);
      setGateStatus(gateRes.data || null);
      setOverridesActive(activeRes.data?.items || []);
      setOverrideHistory(historyRes.data?.items || []);
      setGuardTelemetry(guardRes.data || null);
      setAllowedQuoteAssets(quotePolicyRes.data?.allowed_quote_assets || guardRes.data?.allowed_quote_assets || []);
      setExchangeMonitoring(exchangeRes.data || null);
      setHardeningAnalytics(hardeningRes.data?.items || []);
      setAlertsHistory(alertsRes.data?.items || []);
      setAlertPolicy(policyRes.data || null);
      setActionAudit(auditRes.data?.items || []);
      setScannerOps(scannerStateRes.data || { runtime: {}, symbol_universe: [], whitelist: [], blacklist: [], manual_trigger: {} });
      setRolloutOps(rolloutStateRes.data || null);
      setRiskOps(exposureRes.data || { cluster_exposure: [], symbol_exposure: [], config: {} });
      setRiskOverrides(exposureOverrideRes.data?.items || []);
      setSlowOps(slowControlRes.data || { disabled_strategies: [], throttled_strategies: {}, paused_symbols: [] });
      setUniverseFilterConfig(filterConfigRes.data || { min_liquidity_usd: 1000000, min_volume_24h_usd: 5000000, max_spread_bps: 40 });
      setFreshnessSlaConfig(freshnessSlaRes.data || { latency_threshold: 1200, stale_threshold_sec: 900 });
      setStaleEntities(staleListRes.data?.items || []);
      setFreshnessHeatmap(heatmapRes.data?.items || []);
      setFallbackTimeline(fallbackRes.data?.items || []);
      setKpiActiveRecommendations(kpiActiveRes.data?.items || []);
      setKpiRecommendationHistory(kpiHistoryRes.data?.items || []);
      setMetricsHistory(metricsHistoryRes.data || { latency_series: [], pnl_series: [], risk_veto_series: [], overlays: [] });
      setExportJobs(exportJobsRes.data?.items || []);
      setStateValidation({
        wsReconnectSessionChanged: Boolean(validationRes.data?.ws_session_changed),
        overrideAffectsExecution: Boolean(validationRes.data?.override_effect_applied),
        gateUsesCiResult: String(validationRes.data?.gate_source || "").toLowerCase() === "ci_script",
        tradeBlockVisible: Boolean(validationRes.data?.guard_block_visible),
        suggestions: validationRes.data?.suggestions || {},
        lastCheckedAt: validationRes.data?.checked_at || new Date().toISOString(),
      });

      const policy = policyRes.data?.policy;
      if (policy) {
        setAlertPolicyForm({
          execution_quality_warning_threshold: String(policy.execution_quality_warning_threshold ?? 60),
          execution_quality_critical_threshold: String(policy.execution_quality_critical_threshold ?? 40),
          permission_drift_warning_per_day: String(policy.permission_drift_warning_per_day ?? 2),
          permission_drift_critical_per_day: String(policy.permission_drift_critical_per_day ?? 5),
        });
      }

      const cfg = exposureRes.data?.config || {};
      setRiskLimitForm((prev) => ({
        ...prev,
        max_total_exposure_pct: String(cfg.max_total_exposure_pct ?? prev.max_total_exposure_pct),
        max_symbol_exposure_pct: String(cfg.max_symbol_exposure_pct ?? prev.max_symbol_exposure_pct),
        max_cluster_exposure_pct: String(cfg.max_cluster_exposure_pct ?? prev.max_cluster_exposure_pct),
      }));

      setGlobalError("");

      return {
        wsHealth: wsRes.data || null,
        gateStatus: gateRes.data || null,
        overridesActive: activeRes.data?.items || [],
        guardTelemetry: guardRes.data || null,
        stateValidation: validationRes.data || null,
        scannerOps: scannerStateRes.data || null,
        rolloutOps: rolloutStateRes.data || null,
        riskOps: exposureRes.data || null,
        slowOps: slowControlRes.data || null,
        freshnessOps: staleListRes.data || null,
        kpiOps: kpiActiveRes.data || null,
      };
    } catch (error) {
      const detail = error?.response?.data?.detail;
      const message = typeof detail === "string" ? detail : "Pipeline operations verisi alınamadı";
      setGlobalError(message);
      toast.error(message);
      return null;
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [severityFilter, alertSinceHours, alertEventFilter, trendRange, trendSymbolFilter, trendStrategyFilter]);

  useEffect(() => {
    load(true);
  }, [load]);

  useEffect(() => {
    if (!autoRefreshEnabled) return undefined;
    const intervalMs = Math.max(Number(autoRefreshIntervalSec || 15), 5) * 1000;
    const timer = window.setInterval(() => {
      load(false);
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [autoRefreshEnabled, autoRefreshIntervalSec, load]);

  const openActionDialog = (actionKey, panelKey, reasonHint, context = {}) => {
    setActionDialog({
      open: true,
      actionKey,
      reason: reasonHint || (panelKey === "recovery" ? reasonRecovery : reasonControl),
      phrase: "",
      panelKey,
      context,
    });
  };

  const setActionSuccess = (panelKey, payload, toastTitle) => {
    const resultPayload = payload || null;
    setPanelResult((prev) => ({ ...prev, [panelKey]: resultPayload }));
    toast.success(`${toastTitle} | trace_id: ${resultPayload?.trace_id || "-"}`);
  };

  const setActionFailure = (panelKey, error, toastTitle) => {
    const { traceId, message } = extractErrorMeta(error);
    setGlobalError(message);
    setPanelResult((prev) => ({
      ...prev,
      [panelKey]: { status: "error", trace_id: traceId, message },
    }));
    toast.error(`${toastTitle} | trace_id: ${traceId} | ${message}`);
  };

  const parseSymbolsText = (value) => {
    const raw = String(value || "")
      .split(/[\n,;\s]+/g)
      .map((item) => item.trim().toUpperCase())
      .filter(Boolean);
    return Array.from(new Set(raw));
  };

  const onBulkCsvFileUpload = async (file) => {
    if (!file) return;
    const text = await file.text();
    setBulkImportModal((prev) => ({ ...prev, csvText: text }));
  };

  const previewBulkImport = async () => {
    if (!bulkImportModal.csvText.trim()) {
      toast.error("CSV içeriği boş olamaz");
      return;
    }
    try {
      const { data } = await apiClient.post("/admin/universe-monitor/universe/symbols/bulk-import/preview", {
        csv_text: bulkImportModal.csvText,
        reason: reasonControl,
        confirmation_phrase: "PREVIEW BULK IMPORT",
      });
      setBulkImportModal((prev) => ({ ...prev, preview: data.preview || null }));
      setActionSuccess("scannerOps", data, "Bulk preview oluşturuldu");
    } catch (error) {
      setActionFailure("scannerOps", error, "Bulk preview başarısız");
    }
  };

  const applyBulkImport = async () => {
    const previewId = bulkImportModal.preview?.preview_id;
    if (!previewId) {
      toast.error("Önce preview oluşturun");
      return;
    }
    try {
      const { data } = await apiClient.post("/admin/universe-monitor/universe/symbols/bulk-import/apply", {
        preview_id: previewId,
        apply_mode: bulkImportModal.applyMode,
        reason: reasonControl,
        confirmation_phrase: "APPLY BULK IMPORT",
      });
      setActionSuccess("scannerOps", data, "Bulk apply tamamlandı");
      await load(false);
    } catch (error) {
      setActionFailure("scannerOps", error, "Bulk apply başarısız");
    }
  };

  const createExportJob = async () => {
    try {
      const metrics = parseSymbolsText(exportModal.metrics.replaceAll(",", " ")).map((item) => item.toLowerCase());
      const { data } = await apiClient.post("/admin/universe-monitor/export/job", {
        range: exportModal.range,
        output_format: exportModal.output_format,
        metrics,
        symbol: exportModal.symbol || null,
        strategy: exportModal.strategy || null,
        reason: reasonControl,
        confirmation_phrase: "CREATE EXPORT JOB",
      });
      setActionSuccess("trend", data, "Export job queued");
      setExportModal((prev) => ({ ...prev, open: false }));
      await load(false);
    } catch (error) {
      setActionFailure("trend", error, "Export job oluşturulamadı");
    }
  };

  const retryExportJob = async (jobId) => {
    try {
      const { data } = await apiClient.post(`/admin/universe-monitor/export/job/${jobId}/retry`, {
        reason: reasonControl,
        confirmation_phrase: "CREATE EXPORT JOB",
      });
      setActionSuccess("trend", data, "Export retry queued");
      await load(false);
    } catch (error) {
      setActionFailure("trend", error, "Export retry başarısız");
    }
  };

  const loadDebugUniverse = async () => {
    try {
      const { data } = await apiClient.get("/debug/effective-universe", {
        params: { market_type: "spot", scanner_mode: "ALL_MARKET_SYMBOLS", top_n: 120 },
      });
      setDebugUniversePayload(data || null);
    } catch (error) {
      const { message } = extractErrorMeta(error);
      setDebugUniversePayload({ error: message });
    }
  };

  const loadAuditDrawerData = async (tab = auditDrawerTab) => {
    try {
      const sinceHours = Number(auditFilters.since_hours || 24);
      const params = {
        since_hours: sinceHours,
        user_id: auditFilters.user_id || undefined,
        action_type: auditFilters.action_type || undefined,
      };
      const [{ data: actionAuditRes }, { data: auditLogsRes }] = await Promise.all([
        apiClient.get("/runtime/action-audit", { params }),
        apiClient.get("/audit-logs/timeline", {
          params: {
            limit: 120,
            actor_user_id: auditFilters.user_id || undefined,
            action: auditFilters.action_type || undefined,
            request_id: auditFilters.trace_id || undefined,
            q: auditFilters.trace_id || undefined,
            date_from: new Date(Date.now() - sinceHours * 3600 * 1000).toISOString(),
          },
        }),
      ]);

      const traceFilter = String(auditFilters.trace_id || "").trim().toLowerCase();
      const filteredActionAudit = (actionAuditRes.items || []).filter((item) => {
        if (!traceFilter) return true;
        const details = item.details || {};
        const traceId = String(details.trace_id || details.request_id || "").toLowerCase();
        return traceId.includes(traceFilter);
      });

      const filteredAuditLogs = (auditLogsRes.items || []).filter((item) => {
        if (!traceFilter) return true;
        const details = item.details || {};
        const traceId = String(details.trace_id || item.request_id || "").toLowerCase();
        return traceId.includes(traceFilter);
      });

      setAuditDrawerItems(filteredActionAudit);
      setAuditLogDrawerItems(filteredAuditLogs);
      if (tab === "action_audit") {
        setSelectedAuditDetail(filteredActionAudit[0] || null);
      } else {
        setSelectedAuditDetail(filteredAuditLogs[0] || null);
      }
    } catch (error) {
      const { traceId, message } = extractErrorMeta(error);
      toast.error(`Audit drawer yüklenemedi | trace_id: ${traceId} | ${message}`);
    }
  };

  const openAuditDrawer = async (tab) => {
    setAuditDrawerTab(tab);
    setAuditDrawerOpen(true);
    await loadAuditDrawerData(tab);
  };

  const openAuditDetail = async (id) => {
    try {
      const { data } = await apiClient.get(`/runtime/action-audit/${id}`);
      setSelectedAuditDetail(data || null);
    } catch (error) {
      const { traceId, message } = extractErrorMeta(error);
      toast.error(`Audit detay alınamadı | trace_id: ${traceId} | ${message}`);
    }
  };

  const submitDialogAction = async () => {
    const meta = ACTION_META[actionDialog.actionKey];
    if (!meta) return;
    if (!actionDialog.reason || actionDialog.reason.trim().length < 5) {
      toast.error("Reason zorunlu (min 5 karakter)");
      return;
    }
    if (actionDialog.phrase.trim().toUpperCase() !== meta.phrase) {
      toast.error(`Phrase hatalı. Beklenen: ${meta.phrase}`);
      return;
    }

    try {
      let response;
      if (actionDialog.actionKey === "service_restart") {
        response = await apiClient.post(meta.endpoint, {
          reason: actionDialog.reason,
          confirmation_phrase: actionDialog.phrase,
          service: serviceTarget,
        });
      } else if (["scanner_start", "scanner_stop", "scanner_trigger", "rollout_promote", "rollout_demote", "rollout_rollback"].includes(actionDialog.actionKey)) {
        response = await apiClient.post(meta.endpoint, {
          reason: actionDialog.reason,
          confirmation_phrase: actionDialog.phrase,
        });
      } else if (actionDialog.actionKey === "freshness_sla_update") {
        response = await apiClient.put(meta.endpoint, {
          latency_threshold: Number(freshnessSlaConfig.latency_threshold || 0),
          stale_threshold_sec: Number(freshnessSlaConfig.stale_threshold_sec || 0),
          reason: actionDialog.reason,
          confirmation_phrase: actionDialog.phrase,
        });
      } else if (actionDialog.actionKey === "freshness_rescan_stale") {
        response = await apiClient.post(meta.endpoint, {
          limit: Number(actionDialog.context?.limit || 200),
          reason: actionDialog.reason,
          confirmation_phrase: actionDialog.phrase,
        });
      } else if (actionDialog.actionKey === "kpi_generate") {
        response = await apiClient.post(meta.endpoint, {
          reason: actionDialog.reason,
          confirmation_phrase: actionDialog.phrase,
        });
      } else if (["kpi_apply", "kpi_reject", "kpi_postpone"].includes(actionDialog.actionKey)) {
        response = await apiClient.post(meta.endpoint, {
          recommendation_id: actionDialog.context?.recommendationId,
          reason: actionDialog.reason,
          confirmation_phrase: actionDialog.phrase,
        });
      } else if (["scanner_whitelist_update", "scanner_blacklist_update"].includes(actionDialog.actionKey)) {
        response = await apiClient.post(meta.endpoint, {
          action: actionDialog.context?.action || "replace",
          symbols: actionDialog.context?.symbols || [],
          reason: actionDialog.reason,
          confirmation_phrase: actionDialog.phrase,
        });
      } else if (actionDialog.actionKey === "universe_bulk_toggle") {
        response = await apiClient.post(meta.endpoint, {
          symbols: actionDialog.context?.symbols || [],
          enabled: Boolean(actionDialog.context?.enabled),
          reason: actionDialog.reason,
          confirmation_phrase: actionDialog.phrase,
        });
      } else if (actionDialog.actionKey === "universe_filter_update") {
        response = await apiClient.put(meta.endpoint, {
          min_liquidity_usd: Number(universeFilterConfig.min_liquidity_usd || 0),
          min_volume_24h_usd: Number(universeFilterConfig.min_volume_24h_usd || 0),
          max_spread_bps: Number(universeFilterConfig.max_spread_bps || 0),
          reason: actionDialog.reason,
          confirmation_phrase: actionDialog.phrase,
        });
      } else if (actionDialog.actionKey === "risk_exposure_limit") {
        response = await apiClient.put(meta.endpoint, {
          max_total_exposure_pct: Number(riskLimitForm.max_total_exposure_pct || 0),
          max_symbol_exposure_pct: Number(riskLimitForm.max_symbol_exposure_pct || 0),
          max_cluster_exposure_pct: Number(riskLimitForm.max_cluster_exposure_pct || 0),
          reason: actionDialog.reason,
          confirmation_phrase: actionDialog.phrase,
          force: true,
        });
      } else if (actionDialog.actionKey === "risk_exposure_override") {
        response = await apiClient.post(meta.endpoint, {
          override_type: riskOverrideForm.override_type,
          scope: riskOverrideForm.scope,
          ttl_minutes: Number(riskOverrideForm.ttl_minutes || 30),
          reason: actionDialog.reason,
          confirmation_phrase: actionDialog.phrase,
        });
      } else if (["strategy_disable", "strategy_throttle", "symbol_pause"].includes(actionDialog.actionKey)) {
        let endpoint = meta.endpoint;
        endpoint = endpoint.replace("{strategy_id}", actionDialog.context?.strategyId || "");
        endpoint = endpoint.replace("{symbol}", actionDialog.context?.symbol || "");
        const body = {
          reason: actionDialog.reason,
          confirmation_phrase: actionDialog.phrase,
        };
        if (actionDialog.actionKey === "strategy_throttle") {
          body.throttle_profile = actionDialog.context?.throttleProfile || "soft";
        }
        if (actionDialog.actionKey === "symbol_pause") {
          body.pause = true;
        }
        response = await apiClient.post(endpoint, body);
      } else if (actionDialog.actionKey === "pipeline_flush") {
        response = await apiClient.post(meta.endpoint, {
          reason: actionDialog.reason,
          confirmation_phrase: actionDialog.phrase,
          queue_type: "all",
        });
      } else if (actionDialog.actionKey === "policy_update") {
        response = await apiClient.put(meta.endpoint, {
          execution_quality_warning_threshold: Number(alertPolicyForm.execution_quality_warning_threshold || 60),
          execution_quality_critical_threshold: Number(alertPolicyForm.execution_quality_critical_threshold || 40),
          permission_drift_warning_per_day: Number(alertPolicyForm.permission_drift_warning_per_day || 2),
          permission_drift_critical_per_day: Number(alertPolicyForm.permission_drift_critical_per_day || 5),
          reason: actionDialog.reason,
          confirmation_phrase: actionDialog.phrase,
        });
      } else if (["exchange_revalidate", "exchange_disable"].includes(actionDialog.actionKey)) {
        const connectionId = actionDialog.context?.connectionId;
        if (!connectionId) {
          toast.error("connection_id gerekli");
          return;
        }
        const endpoint = meta.endpoint.replace("{connection_id}", connectionId);
        response = await apiClient.post(endpoint, {
          reason: actionDialog.reason,
          confirmation_phrase: actionDialog.phrase,
        });
      } else {
        response = await apiClient.post(meta.endpoint, {
          reason: actionDialog.reason,
          confirmation_phrase: actionDialog.phrase,
        });
      }

      setActionSuccess(actionDialog.panelKey, response.data || null, "Aksiyon başarılı");
      setActionDialog((prev) => ({ ...prev, open: false }));
      await load(false);
    } catch (error) {
      setActionFailure(actionDialog.panelKey, error, "Aksiyon başarısız");
    }
  };

  const runManualHeartbeat = async () => {
    if (!reasonRecovery || reasonRecovery.trim().length < 5) {
      toast.error("Recovery reason zorunlu (min 5 karakter)");
      return;
    }
    try {
      const { data } = await apiClient.post("/runtime/heartbeat/check", {
        lag_threshold_seconds: Number(lagThreshold || 60),
      });
      setHeartbeat(data || null);
      setActionSuccess("recovery", data || null, "Heartbeat kontrolü başarılı");
      await load(false);
    } catch (error) {
      setActionFailure("recovery", error, "Heartbeat kontrolü başarısız");
    }
  };

  const runOverrideCreate = async () => {
    try {
      const { data } = await apiClient.post("/runtime/override/create", {
        override_type: overrideForm.override_type,
        scope: overrideForm.scope,
        ttl_minutes: Number(overrideForm.ttl_minutes || 30),
        reason: overrideForm.reason,
        confirmation_phrase: overrideForm.confirmation_phrase,
      });
      setActionSuccess("override", data || null, "Override oluşturma başarılı");
      await load(false);
    } catch (error) {
      setActionFailure("override", error, "Override oluşturma başarısız");
    }
  };

  const runOverrideCancel = async (overrideId) => {
    try {
      const { data } = await apiClient.post(`/runtime/override/${overrideId}/cancel`, {
        reason: overrideForm.reason,
        confirmation_phrase: "CANCEL OVERRIDE",
      });
      setActionSuccess("override", data || null, "Override iptali başarılı");
      await load(false);
    } catch (error) {
      setActionFailure("override", error, "Override iptali başarısız");
    }
  };

  const runAlertAction = async (alertId, action, muteMinutes = 30) => {
    if (!reasonAlerts || reasonAlerts.trim().length < 3) {
      toast.error("Alert reason zorunlu");
      return;
    }
    try {
      const { data } = await apiClient.post(`/runtime/alerts/${alertId}/action`, {
        action,
        reason: reasonAlerts,
        mute_minutes: muteMinutes,
      });
      setActionSuccess("alerts", data || null, `Alert ${action} başarılı`);
      await load(false);
    } catch (error) {
      setActionFailure("alerts", error, `Alert ${action} başarısız`);
    }
  };

  const runBulkAlertAction = async (action) => {
    if (bulkSelection.length === 0) {
      toast.error("Önce en az bir alert seçin");
      return;
    }
    if (!reasonAlerts || reasonAlerts.trim().length < 3) {
      toast.error("Alert reason zorunlu");
      return;
    }
    try {
      const { data } = await apiClient.post("/runtime/alerts/bulk-action", {
        ids: bulkSelection,
        action,
        reason: reasonAlerts,
        mute_minutes: 30,
      });
      setBulkSelection([]);
      setActionSuccess("alerts", data || null, `Bulk ${action} başarılı`);
      await load(false);
    } catch (error) {
      setActionFailure("alerts", error, `Bulk ${action} başarısız`);
    }
  };

  const openSymbolListEditor = (listType) => {
    const current = listType === "whitelist" ? scannerOps?.whitelist || [] : scannerOps?.blacklist || [];
    setSymbolListModal({
      open: true,
      listType,
      symbolsText: current.join(", "),
    });
  };

  const submitSymbolListEditor = () => {
    const symbols = parseSymbolsText(symbolListModal.symbolsText);
    if (symbols.length === 0) {
      toast.error("En az bir symbol girin");
      return;
    }
    const actionKey = symbolListModal.listType === "whitelist" ? "scanner_whitelist_update" : "scanner_blacklist_update";
    openActionDialog(actionKey, "scannerOps", reasonControl, { action: "replace", symbols });
    setSymbolListModal((prev) => ({ ...prev, open: false }));
  };

  const runUniverseBulkToggle = (enabled) => {
    const symbols = parseSymbolsText(bulkSymbolsInput);
    if (symbols.length === 0) {
      toast.error("Bulk symbol list boş olamaz");
      return;
    }
    openActionDialog("universe_bulk_toggle", "scannerOps", reasonControl, { symbols, enabled });
  };

  const topReasons = useMemo(() => {
    const rows = [...(guardTelemetry?.top_reasons || [])];
    rows.sort((a, b) => {
      const aInvalid = String(a?.reason || "").toUpperCase() === "INVALID_QUOTE_ASSET" ? 0 : 1;
      const bInvalid = String(b?.reason || "").toUpperCase() === "INVALID_QUOTE_ASSET" ? 0 : 1;
      if (aInvalid !== bInvalid) return aInvalid - bInvalid;
      return Number(b?.count || 0) - Number(a?.count || 0);
    });
    return rows.slice(0, 6);
  }, [guardTelemetry]);
  const blockedTrades = useMemo(() => {
    const rows = [...(guardTelemetry?.blocked_trade_list || [])];
    rows.sort((a, b) => {
      const aReason = (a.reason_codes || [a.reason || "UNKNOWN"])[0];
      const bReason = (b.reason_codes || [b.reason || "UNKNOWN"])[0];
      const aInvalid = String(aReason).toUpperCase() === "INVALID_QUOTE_ASSET" ? 0 : 1;
      const bInvalid = String(bReason).toUpperCase() === "INVALID_QUOTE_ASSET" ? 0 : 1;
      if (aInvalid !== bInvalid) return aInvalid - bInvalid;
      return String(b.updated_at || "").localeCompare(String(a.updated_at || ""));
    });
    return rows.slice(0, 10);
  }, [guardTelemetry]);
  const invalidQuoteReasonCount = useMemo(
    () => Number((guardTelemetry?.top_reasons || []).find((item) => String(item?.reason || "").toUpperCase() === "INVALID_QUOTE_ASSET")?.count || 0),
    [guardTelemetry],
  );
  const exchangeTrend = useMemo(() => (exchangeMonitoring?.trend || []).slice(-8), [exchangeMonitoring]);
  const auditSlice = useMemo(() => actionAudit.slice(0, 20), [actionAudit]);

  return (
    <section className="space-y-5" data-testid="pipeline-operations-page">
      <header className="rounded-2xl border border-slate-700 bg-gradient-to-r from-slate-900 via-zinc-900 to-slate-950 p-5" data-testid="pipeline-operations-header">
        <div className="flex flex-wrap items-start justify-between gap-3" data-testid="pipeline-operations-header-row">
          <div data-testid="pipeline-operations-header-copy">
            <h1 className="text-4xl font-black uppercase tracking-tight text-slate-100" data-testid="pipeline-operations-title">Unified Pipeline Operations Panel</h1>
            <p className="mt-2 text-sm text-slate-400" data-testid="pipeline-operations-description">
              Öncelik sırası: Control → Recovery → Monitoring → Traceability · role={user?.role || "unknown"} · MODE: {runtimeMode}
            </p>
          </div>
          <div className="flex flex-wrap gap-2" data-testid="pipeline-operations-header-actions">
            <Button variant="outline" onClick={() => navigate("/admin/live-trading-dashboard")} data-testid="pipeline-operations-open-live-dashboard-button">Live Dashboard</Button>
            <select value={autoRefreshIntervalSec} onChange={(e) => setAutoRefreshIntervalSec(e.target.value)} className="h-9 rounded border border-slate-700 px-2 text-sm" data-testid="pipeline-operations-auto-refresh-interval-select">
              <option value="5">5s</option>
              <option value="15">15s</option>
              <option value="60">60s</option>
            </select>
            <Button variant="outline" onClick={() => setAutoRefreshEnabled((prev) => !prev)} data-testid="pipeline-operations-auto-refresh-toggle-button">Auto-Refresh: {autoRefreshEnabled ? "ON" : "OFF"}</Button>
            <Button variant="outline" onClick={() => load(false)} data-testid="pipeline-operations-refresh-button">Yenile</Button>
          </div>
        </div>
      </header>

      {globalError && (
        <div className="rounded border border-red-700 bg-red-100 p-3 text-sm text-red-800" data-testid="pipeline-operations-global-error-banner">
          API Error: {globalError}
        </div>
      )}

      <SummaryBar
        wsHealth={wsHealth}
        gateStatus={gateStatus}
        overridesActive={overridesActive}
        alertsHistory={alertsHistory}
        allowedQuoteAssets={allowedQuoteAssets}
        testId="pipeline-operations-summary-bar"
      />

      <article className="rounded-xl border border-slate-700 bg-slate-900/90 p-4" data-testid="pipeline-operations-universe-ops-panel">
        <h3 className="text-base font-semibold text-slate-100" data-testid="pipeline-operations-universe-ops-title">Universe Operations (Faz-1)</h3>
        <div className="mt-3 flex flex-wrap gap-2" data-testid="pipeline-operations-universe-ops-tabs">
          <Button variant={opsTab === "rollout" ? "default" : "outline"} onClick={() => setOpsTab("rollout")} data-testid="pipeline-operations-tab-rollout-button">Rollout</Button>
          <Button variant={opsTab === "scanner" ? "default" : "outline"} onClick={() => setOpsTab("scanner")} data-testid="pipeline-operations-tab-scanner-button">Scanner</Button>
          <Button variant={opsTab === "risk" ? "default" : "outline"} onClick={() => setOpsTab("risk")} data-testid="pipeline-operations-tab-risk-button">Risk/Exposure</Button>
          <Button variant={opsTab === "slow" ? "default" : "outline"} onClick={() => setOpsTab("slow")} data-testid="pipeline-operations-tab-slow-button">Slow Control</Button>
          <Button variant={opsTab === "freshness" ? "default" : "outline"} onClick={() => setOpsTab("freshness")} data-testid="pipeline-operations-tab-freshness-button">Freshness/SLA</Button>
          <Button variant={opsTab === "kpi" ? "default" : "outline"} onClick={() => setOpsTab("kpi")} data-testid="pipeline-operations-tab-kpi-button">KPI Rec</Button>
          <Button variant={opsTab === "trend" ? "default" : "outline"} onClick={() => setOpsTab("trend")} data-testid="pipeline-operations-tab-trend-button">Trend</Button>
        </div>

        {opsTab === "rollout" && (
          <div className="mt-4 grid gap-3 md:grid-cols-2" data-testid="pipeline-operations-rollout-tab-content">
            <div className="space-y-2 text-xs" data-testid="pipeline-operations-rollout-state">
              <p data-testid="pipeline-operations-rollout-current-stage">current_stage={rolloutOps?.current_stage || "-"}</p>
              <p data-testid="pipeline-operations-rollout-recommended-stage">recommended_stage={rolloutOps?.recommended_stage || "-"}</p>
              <p data-testid="pipeline-operations-rollout-previous-stage">previous_stage={rolloutOps?.previous_stage || "-"}</p>
              <p data-testid="pipeline-operations-rollout-pending-approvers">pending_approvers={(rolloutOps?.pending_approvers || []).join(",") || "-"}</p>
              <p data-testid="pipeline-operations-rollout-approval-policy">approval_policy={rolloutOps?.approval_policy || "-"}</p>
            </div>
            <div className="space-y-2" data-testid="pipeline-operations-rollout-actions">
              <Button disabled={!isSuperAdmin} onClick={() => openActionDialog("rollout_promote", "rolloutOps", reasonControl)} data-testid="pipeline-operations-rollout-promote-button">Force Promote</Button>
              <Button variant="outline" disabled={!isSuperAdmin} onClick={() => openActionDialog("rollout_demote", "rolloutOps", reasonControl)} data-testid="pipeline-operations-rollout-demote-button">Force Demote</Button>
              <Button variant="outline" disabled={!isSuperAdmin} onClick={() => openActionDialog("rollout_rollback", "rolloutOps", reasonControl)} data-testid="pipeline-operations-rollout-rollback-button">Rollback</Button>
              <ResultBadge result={panelResult.rolloutOps} testId="pipeline-operations-rollout-result" />
            </div>
          </div>
        )}

        {opsTab === "scanner" && (
          <div className="mt-4 grid gap-3 md:grid-cols-2" data-testid="pipeline-operations-scanner-tab-content">
            <div className="space-y-2 text-xs" data-testid="pipeline-operations-scanner-state">
              <p data-testid="pipeline-operations-scanner-running">running={String(scannerOps?.runtime?.running ?? false)}</p>
              <p data-testid="pipeline-operations-scanner-last-started">last_started_at={scannerOps?.runtime?.last_started_at || "-"}</p>
              <p data-testid="pipeline-operations-scanner-last-stopped">last_stopped_at={scannerOps?.runtime?.last_stopped_at || "-"}</p>
              <p data-testid="pipeline-operations-scanner-last-trigger-status">last_manual_trigger_status={scannerOps?.runtime?.last_manual_trigger_status || "-"}</p>
              <p data-testid="pipeline-operations-scanner-last-trigger-request-id">request_id={scannerOps?.runtime?.last_manual_trigger_request_id || scannerOps?.manual_trigger?.request_id || "-"}</p>
              <p data-testid="pipeline-operations-scanner-universe-size">universe_size={(scannerOps?.symbol_universe || []).length}</p>
            </div>
            <div className="space-y-2" data-testid="pipeline-operations-scanner-actions">
              <div className="flex flex-wrap gap-2" data-testid="pipeline-operations-scanner-run-actions">
                <Button disabled={!isSuperAdmin} onClick={() => openActionDialog("scanner_start", "scannerOps", reasonControl)} data-testid="pipeline-operations-scanner-start-button">Start</Button>
                <Button variant="outline" disabled={!isSuperAdmin} onClick={() => openActionDialog("scanner_stop", "scannerOps", reasonControl)} data-testid="pipeline-operations-scanner-stop-button">Stop</Button>
                <Button variant="outline" disabled={!isSuperAdmin} onClick={() => openActionDialog("scanner_trigger", "scannerOps", reasonControl)} data-testid="pipeline-operations-scanner-trigger-button">Run Scan Now</Button>
              </div>

              <div className="flex flex-wrap gap-2" data-testid="pipeline-operations-scanner-symbol-list-actions">
                <Button variant="outline" onClick={() => openSymbolListEditor("whitelist")} data-testid="pipeline-operations-scanner-whitelist-edit-button">Edit Whitelist</Button>
                <Button variant="outline" onClick={() => openSymbolListEditor("blacklist")} data-testid="pipeline-operations-scanner-blacklist-edit-button">Edit Blacklist</Button>
                <Button variant="outline" onClick={() => setBulkImportModal((prev) => ({ ...prev, open: true }))} data-testid="pipeline-operations-scanner-bulk-open-modal-button">Bulk Upload</Button>
              </div>

              <Input value={bulkSymbolsInput} onChange={(e) => setBulkSymbolsInput(e.target.value)} data-testid="pipeline-operations-scanner-bulk-symbols-input" placeholder="BTCUSDT,ETHUSDT,..." />
              <div className="flex flex-wrap gap-2" data-testid="pipeline-operations-scanner-bulk-actions">
                <Button variant="outline" onClick={() => runUniverseBulkToggle(true)} data-testid="pipeline-operations-scanner-bulk-enable-button">Bulk Enable</Button>
                <Button variant="outline" onClick={() => runUniverseBulkToggle(false)} data-testid="pipeline-operations-scanner-bulk-disable-button">Bulk Disable</Button>
              </div>

              <div className="grid grid-cols-3 gap-2" data-testid="pipeline-operations-scanner-filter-config-grid">
                <Input value={String(universeFilterConfig.min_liquidity_usd ?? "")} onChange={(e) => setUniverseFilterConfig((prev) => ({ ...prev, min_liquidity_usd: e.target.value }))} data-testid="pipeline-operations-scanner-filter-liquidity-input" />
                <Input value={String(universeFilterConfig.min_volume_24h_usd ?? "")} onChange={(e) => setUniverseFilterConfig((prev) => ({ ...prev, min_volume_24h_usd: e.target.value }))} data-testid="pipeline-operations-scanner-filter-volume-input" />
                <Input value={String(universeFilterConfig.max_spread_bps ?? "")} onChange={(e) => setUniverseFilterConfig((prev) => ({ ...prev, max_spread_bps: e.target.value }))} data-testid="pipeline-operations-scanner-filter-spread-input" />
              </div>
              <Button variant="outline" onClick={() => openActionDialog("universe_filter_update", "scannerOps", reasonControl)} data-testid="pipeline-operations-scanner-filter-save-button">Save Filter Config</Button>

              {!isProductionEnv && isSuperAdmin && (
                <div className="rounded border border-amber-700 p-2" data-testid="pipeline-operations-debug-panel-wrap">
                  <div className="flex gap-2" data-testid="pipeline-operations-debug-panel-actions">
                    <Button variant="outline" onClick={() => setDebugPanelOpen((prev) => !prev)} data-testid="pipeline-operations-debug-panel-toggle-button">DEBUG EFFECTIVE UNIVERSE</Button>
                    {debugPanelOpen && <Button variant="outline" onClick={loadDebugUniverse} data-testid="pipeline-operations-debug-panel-refresh-button">Debug Refresh</Button>}
                  </div>
                  {debugPanelOpen && <pre className="mt-2 max-h-28 overflow-auto text-[11px]" data-testid="pipeline-operations-debug-panel-json">{JSON.stringify(debugUniversePayload || {}, null, 2)}</pre>}
                </div>
              )}

              <ResultBadge result={panelResult.scannerOps} testId="pipeline-operations-scanner-result" />
            </div>
          </div>
        )}

        {opsTab === "risk" && (
          <div className="mt-4 grid gap-3 md:grid-cols-2" data-testid="pipeline-operations-risk-tab-content">
            <div className="space-y-2 text-xs" data-testid="pipeline-operations-risk-state">
              <p data-testid="pipeline-operations-risk-portfolio-exposure">portfolio_exposure={riskOps?.portfolio_exposure ?? "-"}</p>
              <p data-testid="pipeline-operations-risk-cluster-count">cluster_count={(riskOps?.cluster_exposure || []).length}</p>
              <p data-testid="pipeline-operations-risk-symbol-count">symbol_count={(riskOps?.symbol_exposure || []).length}</p>
              <p data-testid="pipeline-operations-risk-active-override-count">active_overrides={riskOverrides.length}</p>
              <div className="max-h-20 overflow-auto" data-testid="pipeline-operations-risk-active-override-list">
                {riskOverrides.slice(0, 6).map((item, idx) => (
                  <p key={item.override_id} data-testid={`pipeline-operations-risk-active-override-${idx}`}>{item.override_type} · {item.scope} · ttl={item.ttl_remaining_seconds}s</p>
                ))}
              </div>
            </div>
            <div className="space-y-2" data-testid="pipeline-operations-risk-actions">
              <div className="grid grid-cols-3 gap-2" data-testid="pipeline-operations-risk-limit-grid">
                <Input value={riskLimitForm.max_total_exposure_pct} onChange={(e) => setRiskLimitForm((prev) => ({ ...prev, max_total_exposure_pct: e.target.value }))} data-testid="pipeline-operations-risk-total-limit-input" />
                <Input value={riskLimitForm.max_symbol_exposure_pct} onChange={(e) => setRiskLimitForm((prev) => ({ ...prev, max_symbol_exposure_pct: e.target.value }))} data-testid="pipeline-operations-risk-symbol-limit-input" />
                <Input value={riskLimitForm.max_cluster_exposure_pct} onChange={(e) => setRiskLimitForm((prev) => ({ ...prev, max_cluster_exposure_pct: e.target.value }))} data-testid="pipeline-operations-risk-cluster-limit-input" />
              </div>
              <Button variant="outline" disabled={!isSuperAdmin} onClick={() => openActionDialog("risk_exposure_limit", "riskOps", reasonControl)} data-testid="pipeline-operations-risk-limit-update-button">Update Exposure Limit</Button>

              <div className="grid grid-cols-3 gap-2" data-testid="pipeline-operations-risk-override-grid">
                <Input value={riskOverrideForm.override_type} onChange={(e) => setRiskOverrideForm((prev) => ({ ...prev, override_type: e.target.value }))} data-testid="pipeline-operations-risk-override-type-input" />
                <Input value={riskOverrideForm.scope} onChange={(e) => setRiskOverrideForm((prev) => ({ ...prev, scope: e.target.value }))} data-testid="pipeline-operations-risk-override-scope-input" />
                <Input value={riskOverrideForm.ttl_minutes} onChange={(e) => setRiskOverrideForm((prev) => ({ ...prev, ttl_minutes: e.target.value }))} data-testid="pipeline-operations-risk-override-ttl-input" />
              </div>
              <Button variant="outline" disabled={!isSuperAdmin} onClick={() => openActionDialog("risk_exposure_override", "riskOps", reasonControl)} data-testid="pipeline-operations-risk-override-apply-button">Override Risk</Button>
              <ResultBadge result={panelResult.riskOps} testId="pipeline-operations-risk-result" />
            </div>
          </div>
        )}

        {opsTab === "slow" && (
          <div className="mt-4 grid gap-3 md:grid-cols-2" data-testid="pipeline-operations-slow-tab-content">
            <div className="space-y-2 text-xs" data-testid="pipeline-operations-slow-state">
              <p data-testid="pipeline-operations-slow-disabled-count">disabled_strategies={(slowOps?.disabled_strategies || []).length}</p>
              <p data-testid="pipeline-operations-slow-throttled-count">throttled_strategies={Object.keys(slowOps?.throttled_strategies || {}).length}</p>
              <p data-testid="pipeline-operations-slow-paused-count">paused_symbols={(slowOps?.paused_symbols || []).length}</p>
              <div className="max-h-24 overflow-auto" data-testid="pipeline-operations-slow-disabled-list">
                {(slowOps?.disabled_strategies || []).slice(0, 8).map((item, idx) => (
                  <p key={`${item}-${idx}`} data-testid={`pipeline-operations-slow-disabled-item-${idx}`}>{item}</p>
                ))}
              </div>
            </div>
            <div className="space-y-2" data-testid="pipeline-operations-slow-actions">
              <Input value={slowActionForm.strategy_id} onChange={(e) => setSlowActionForm((prev) => ({ ...prev, strategy_id: e.target.value }))} data-testid="pipeline-operations-slow-strategy-id-input" />
              <div className="flex flex-wrap gap-2" data-testid="pipeline-operations-slow-strategy-actions">
                <Button variant="outline" disabled={!isSuperAdmin} onClick={() => openActionDialog("strategy_disable", "slowOps", reasonControl, { strategyId: slowActionForm.strategy_id })} data-testid="pipeline-operations-slow-disable-button">Disable Strategy</Button>
                <Input value={slowActionForm.throttle_profile} onChange={(e) => setSlowActionForm((prev) => ({ ...prev, throttle_profile: e.target.value }))} className="w-28" data-testid="pipeline-operations-slow-throttle-profile-input" />
                <Button variant="outline" disabled={!isSuperAdmin} onClick={() => openActionDialog("strategy_throttle", "slowOps", reasonControl, { strategyId: slowActionForm.strategy_id, throttleProfile: slowActionForm.throttle_profile })} data-testid="pipeline-operations-slow-throttle-button">Throttle</Button>
              </div>

              <div className="flex flex-wrap gap-2" data-testid="pipeline-operations-slow-symbol-actions">
                <Input value={slowActionForm.symbol} onChange={(e) => setSlowActionForm((prev) => ({ ...prev, symbol: e.target.value.toUpperCase() }))} className="w-40" data-testid="pipeline-operations-slow-symbol-input" />
                <Button variant="outline" disabled={!isSuperAdmin} onClick={() => openActionDialog("symbol_pause", "slowOps", reasonControl, { symbol: slowActionForm.symbol })} data-testid="pipeline-operations-slow-symbol-pause-button">Pause Symbol</Button>
              </div>
              <ResultBadge result={panelResult.slowOps} testId="pipeline-operations-slow-result" />
            </div>
          </div>
        )}

        {opsTab === "freshness" && (
          <div className="mt-4 grid gap-3 md:grid-cols-2" data-testid="pipeline-operations-freshness-tab-content">
            <div className="space-y-2 text-xs" data-testid="pipeline-operations-freshness-state">
              <p data-testid="pipeline-operations-freshness-stale-count">stale_count={staleEntities.length}</p>
              <p data-testid="pipeline-operations-freshness-heatmap-count">heatmap_items={freshnessHeatmap.length}</p>
              <p data-testid="pipeline-operations-freshness-fallback-count">fallback_events={fallbackTimeline.length}</p>
              <div className="max-h-40 overflow-auto" data-testid="pipeline-operations-freshness-stale-list">
                {staleEntities.slice(0, 20).map((item, idx) => (
                  <p key={`${item.entity_type}-${item.entity_id}-${idx}`} className={item.severity === "critical" ? "text-red-700" : "text-amber-700"} data-testid={`pipeline-operations-freshness-stale-item-${idx}`}>
                    {item.entity_type}:{item.entity_id} · age={item.age_sec}s · {item.severity}
                  </p>
                ))}
                {staleEntities.length === 0 && <p data-testid="pipeline-operations-freshness-empty-state">No data yet: stale entity bulunmadı veya event akışı henüz oluşmadı.</p>}
              </div>
              <div className="max-h-28 overflow-auto" data-testid="pipeline-operations-freshness-fallback-timeline">
                {fallbackTimeline.slice(0, 10).map((item, idx) => (
                  <p key={`${item.id}-${idx}`} data-testid={`pipeline-operations-freshness-fallback-item-${idx}`}>{item.created_at || "-"} · {item.event_type || item.effective_mode || "fallback"}</p>
                ))}
              </div>
              <div className="max-h-28 overflow-auto" data-testid="pipeline-operations-freshness-heatmap-list">
                {freshnessHeatmap.slice(0, 12).map((item, idx) => (
                  <p key={`${item.bucket}-${idx}`} data-testid={`pipeline-operations-freshness-heatmap-item-${idx}`}>{item.bucket || item.ts || "-"} · age={item.snapshot_age_avg_sec ?? "-"}s · stale={item.stale_block_count ?? 0}</p>
                ))}
                {freshnessHeatmap.length === 0 && <p data-testid="pipeline-operations-freshness-heatmap-empty">No data yet: heatmap için snapshot üretilmedi.</p>}
              </div>
            </div>
            <div className="space-y-2" data-testid="pipeline-operations-freshness-actions">
              <div className="grid grid-cols-2 gap-2" data-testid="pipeline-operations-freshness-sla-grid">
                <Input value={String(freshnessSlaConfig.latency_threshold ?? "")} onChange={(e) => setFreshnessSlaConfig((prev) => ({ ...prev, latency_threshold: e.target.value }))} data-testid="pipeline-operations-freshness-latency-threshold-input" />
                <Input value={String(freshnessSlaConfig.stale_threshold_sec ?? "")} onChange={(e) => setFreshnessSlaConfig((prev) => ({ ...prev, stale_threshold_sec: e.target.value }))} data-testid="pipeline-operations-freshness-stale-threshold-input" />
              </div>
              <Button variant="outline" disabled={!isSuperAdmin} onClick={() => openActionDialog("freshness_sla_update", "freshnessOps", reasonControl)} data-testid="pipeline-operations-freshness-update-sla-button">Update SLA</Button>
              <Button variant="outline" disabled={!isSuperAdmin} onClick={() => openActionDialog("freshness_rescan_stale", "freshnessOps", reasonControl, { limit: 300 })} data-testid="pipeline-operations-freshness-rescan-all-button">Rescan All Stale</Button>
              <ResultBadge result={panelResult.freshnessOps} testId="pipeline-operations-freshness-result" />
            </div>
          </div>
        )}

        {opsTab === "kpi" && (
          <div className="mt-4 grid gap-3 md:grid-cols-2" data-testid="pipeline-operations-kpi-tab-content">
            <div className="space-y-2 text-xs" data-testid="pipeline-operations-kpi-state">
              <p data-testid="pipeline-operations-kpi-active-count">active_recommendations={kpiActiveRecommendations.length}</p>
              <p data-testid="pipeline-operations-kpi-history-count">history_count={kpiRecommendationHistory.length}</p>
              <div className="max-h-40 overflow-auto" data-testid="pipeline-operations-kpi-active-list">
                {kpiActiveRecommendations.map((item, idx) => (
                  <div key={item.id} className="rounded border border-slate-700 p-2" data-testid={`pipeline-operations-kpi-active-item-${idx}`}>
                    <p data-testid={`pipeline-operations-kpi-active-problem-${idx}`}>{item.problem}</p>
                    <p data-testid={`pipeline-operations-kpi-active-impact-${idx}`}>{item.expected_impact} · conf={item.confidence_score}</p>
                    <div className="mt-1 flex gap-1" data-testid={`pipeline-operations-kpi-active-actions-${idx}`}>
                      <Button size="sm" variant="outline" onClick={() => openActionDialog("kpi_apply", "kpiOps", reasonControl, { recommendationId: item.id })} data-testid={`pipeline-operations-kpi-apply-${idx}`}>Apply</Button>
                      <Button size="sm" variant="outline" onClick={() => openActionDialog("kpi_reject", "kpiOps", reasonControl, { recommendationId: item.id })} data-testid={`pipeline-operations-kpi-reject-${idx}`}>Reject</Button>
                      <Button size="sm" variant="outline" onClick={() => openActionDialog("kpi_postpone", "kpiOps", reasonControl, { recommendationId: item.id })} data-testid={`pipeline-operations-kpi-postpone-${idx}`}>Later</Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="space-y-2" data-testid="pipeline-operations-kpi-actions">
              <Button disabled={!isSuperAdmin} onClick={() => openActionDialog("kpi_generate", "kpiOps", reasonControl)} data-testid="pipeline-operations-kpi-generate-button">KPI Recommendation Üret</Button>
              <div className="max-h-40 overflow-auto" data-testid="pipeline-operations-kpi-history-list">
                {kpiRecommendationHistory.slice(-20).reverse().map((item, idx) => (
                  <p key={`${item.id}-${idx}`} data-testid={`pipeline-operations-kpi-history-item-${idx}`}>{item.decided_at || item.created_at} · {item.status} · {item.problem}</p>
                ))}
                {kpiRecommendationHistory.length === 0 && <p data-testid="pipeline-operations-kpi-history-empty">No data yet: recommendation history oluşmadı.</p>}
              </div>
              <ResultBadge result={panelResult.kpiOps} testId="pipeline-operations-kpi-result" />
            </div>
          </div>
        )}

        {opsTab === "trend" && (
          <div className="mt-4 space-y-3" data-testid="pipeline-operations-trend-tab-content">
            <div className="grid gap-2 md:grid-cols-4" data-testid="pipeline-operations-trend-filter-grid">
              <Input value={trendRange} onChange={(e) => setTrendRange(e.target.value)} data-testid="pipeline-operations-trend-range-input" placeholder="1h/24h/7d/30d" />
              <Input value={trendSymbolFilter} onChange={(e) => setTrendSymbolFilter(e.target.value.toUpperCase())} data-testid="pipeline-operations-trend-symbol-input" placeholder="symbol" />
              <Input value={trendStrategyFilter} onChange={(e) => setTrendStrategyFilter(e.target.value)} data-testid="pipeline-operations-trend-strategy-input" placeholder="strategy" />
              <Button variant="outline" onClick={() => load(false)} data-testid="pipeline-operations-trend-refresh-button">Trend Yenile</Button>
            </div>

            <div className="flex flex-wrap gap-2" data-testid="pipeline-operations-export-actions">
              <Button variant="outline" onClick={() => setExportModal((prev) => ({ ...prev, open: true }))} data-testid="pipeline-operations-export-open-modal-button">Export</Button>
            </div>

            <div className="grid gap-3 lg:grid-cols-3" data-testid="pipeline-operations-trend-charts-grid">
              <div className="min-w-0 rounded border border-slate-700 p-2" data-testid="pipeline-operations-trend-latency-chart-wrap">
                <p className="text-xs font-semibold">Execution Latency Trend</p>
                <div className="h-40 min-w-0" data-testid="pipeline-operations-trend-latency-chart">
                  <LineChart width={520} height={150} data={metricsHistory.latency_series || []}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="ts" hide />
                    <YAxis />
                    <Tooltip />
                    <Line type="monotone" dataKey="avg_ms" stroke="#16a34a" dot={false} />
                    <Line type="monotone" dataKey="p95_ms" stroke="#ef4444" dot={false} />
                  </LineChart>
                </div>
              </div>

              <div className="min-w-0 rounded border border-slate-700 p-2" data-testid="pipeline-operations-trend-pnl-chart-wrap">
                <p className="text-xs font-semibold">PnL Trend</p>
                <div className="h-40 min-w-0" data-testid="pipeline-operations-trend-pnl-chart">
                  <LineChart width={520} height={150} data={metricsHistory.pnl_series || []}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="ts" hide />
                    <YAxis />
                    <Tooltip />
                    <Line type="monotone" dataKey="sum" stroke="#2563eb" dot={false} />
                  </LineChart>
                </div>
              </div>

              <div className="min-w-0 rounded border border-slate-700 p-2" data-testid="pipeline-operations-trend-risk-veto-chart-wrap">
                <p className="text-xs font-semibold">Risk Veto Trend</p>
                <div className="h-40 min-w-0" data-testid="pipeline-operations-trend-risk-veto-chart">
                  <LineChart width={520} height={150} data={metricsHistory.risk_veto_series || []}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="ts" hide />
                    <YAxis />
                    <Tooltip />
                    <Line type="monotone" dataKey="count" stroke="#f59e0b" dot={false} />
                  </LineChart>
                </div>
              </div>
            </div>

            <div className="max-h-24 overflow-auto text-xs" data-testid="pipeline-operations-trend-overlays-list">
              {(metricsHistory.overlays || []).slice(0, 15).map((item, idx) => (
                <p key={`${item.ts}-${idx}`} data-testid={`pipeline-operations-trend-overlay-item-${idx}`}>{item.ts} · {item.event} · {item.message || "-"}</p>
              ))}
              {(!metricsHistory.overlays || metricsHistory.overlays.length === 0) && <p data-testid="pipeline-operations-trend-overlay-empty">No data yet: overlay event bulunamadı.</p>}
            </div>

            <div className="max-h-32 overflow-auto text-xs" data-testid="pipeline-operations-export-job-list">
              {exportJobs.map((job, idx) => (
                <div key={job.job_id} className="mb-1 rounded border border-slate-700 p-2" data-testid={`pipeline-operations-export-job-item-${idx}`}>
                  <p data-testid={`pipeline-operations-export-job-status-${idx}`}>{job.job_id} · {job.status} · trace={job.trace_id}</p>
                  <p data-testid={`pipeline-operations-export-job-count-${idx}`}>rows={job.result_row_count || 0}</p>
                  <div className="mt-1 flex gap-1" data-testid={`pipeline-operations-export-job-actions-${idx}`}>
                    {job.result_url && <Button size="sm" variant="outline" onClick={() => window.open(`${process.env.REACT_APP_BACKEND_URL}${job.result_url}`, "_blank")} data-testid={`pipeline-operations-export-download-${idx}`}>Download</Button>}
                    {(job.status === "failed" || job.status === "done") && <Button size="sm" variant="outline" onClick={() => retryExportJob(job.job_id)} data-testid={`pipeline-operations-export-retry-${idx}`}>Retry</Button>}
                  </div>
                </div>
              ))}
              {exportJobs.length === 0 && <p data-testid="pipeline-operations-export-job-empty">No data yet: export job bulunamadı.</p>}
            </div>
            <ResultBadge result={panelResult.trend} testId="pipeline-operations-trend-result" />
          </div>
        )}
      </article>

      <article className="rounded-xl border border-slate-700 bg-slate-900/90 p-4" data-testid="pipeline-operations-state-validation-panel">
        <h3 className="text-base font-semibold text-slate-100" data-testid="pipeline-operations-state-validation-title">State Validation Checklist</h3>
        <p className="text-xs text-slate-400" data-testid="pipeline-operations-state-validation-description">Gerçek endpoint: `/runtime/state-validation`</p>
        <div className="mt-3 grid gap-2 md:grid-cols-2" data-testid="pipeline-operations-state-validation-grid">
          <p data-testid="pipeline-operations-state-validation-ws">
            WS reconnect session değişimi: <span className={`font-semibold ${stateValidation.wsReconnectSessionChanged ? "text-emerald-700" : "text-red-700"}`}>{stateValidation.wsReconnectSessionChanged ? "PASS" : "FAIL"}</span>
            {!stateValidation.wsReconnectSessionChanged && <span className="ml-2 text-xs text-red-700">{stateValidation.suggestions?.ws_session_changed}</span>}
          </p>
          <p data-testid="pipeline-operations-state-validation-override">
            Override state etkisi: <span className={`font-semibold ${stateValidation.overrideAffectsExecution ? "text-emerald-700" : "text-red-700"}`}>{stateValidation.overrideAffectsExecution ? "PASS" : "FAIL"}</span>
            {!stateValidation.overrideAffectsExecution && <span className="ml-2 text-xs text-red-700">{stateValidation.suggestions?.override_effect_applied}</span>}
          </p>
          <p data-testid="pipeline-operations-state-validation-gate">
            Gate CI script sonucu: <span className={`font-semibold ${stateValidation.gateUsesCiResult ? "text-emerald-700" : "text-red-700"}`}>{stateValidation.gateUsesCiResult ? "PASS" : "FAIL"}</span>
            {!stateValidation.gateUsesCiResult && <span className="ml-2 text-xs text-red-700">{stateValidation.suggestions?.gate_source}</span>}
          </p>
          <p data-testid="pipeline-operations-state-validation-block">
            Trade block guard listesine düşüş: <span className={`font-semibold ${stateValidation.tradeBlockVisible ? "text-emerald-700" : "text-red-700"}`}>{stateValidation.tradeBlockVisible ? "PASS" : "FAIL"}</span>
            {!stateValidation.tradeBlockVisible && <span className="ml-2 text-xs text-red-700">{stateValidation.suggestions?.guard_block_visible}</span>}
          </p>
        </div>
      </article>

      <section className="space-y-3" data-testid="pipeline-operations-control-section">
        <h2 className="text-base font-semibold uppercase tracking-wider text-cyan-300" data-testid="pipeline-operations-control-section-title">Control</h2>

        <PanelShell
          title="WS + Pipeline Control"
          subtitle="Bağlantı ve pipeline müdahalesi"
          testId="pipeline-operations-ws-control-panel"
          stateNode={
            <div className="space-y-1 text-xs text-slate-300" data-testid="pipeline-operations-ws-control-state">
              <p data-testid="pipeline-operations-ws-control-state-session">session={wsHealth?.state?.session_id || "-"}</p>
              <p data-testid="pipeline-operations-ws-control-state-reconnect">reconnect_count={wsHealth?.state?.reconnect_count || 0}</p>
              <p data-testid="pipeline-operations-ws-control-state-status">status={wsHealth?.state?.status || "-"}</p>
              <p data-testid="pipeline-operations-ws-control-state-last-error">last_error={wsHealth?.last_error || "-"}</p>
              <p data-testid="pipeline-operations-ws-control-state-reconnect-reason">reconnect_reason={wsHealth?.reconnect_reason || "-"}</p>
              <div className="max-h-20 space-y-1 overflow-auto" data-testid="pipeline-operations-ws-control-connection-logs">
                <p className="font-semibold" data-testid="pipeline-operations-ws-control-connection-logs-title">Connection Logs (son 5)</p>
                {(wsHealth?.recent_reconnect_reasons || []).map((item, idx) => (
                  <p key={`${item.created_at}-${idx}`} data-testid={`pipeline-operations-ws-control-connection-log-${idx}`}>{item.created_at} · {item.reason}</p>
                ))}
              </div>
            </div>
          }
          reasonNode={
            <Textarea
              value={reasonControl}
              onChange={(e) => setReasonControl(e.target.value)}
              className="min-h-20 bg-slate-950"
              data-testid="pipeline-operations-control-reason-input"
            />
          }
          actionNode={
            <div className="grid gap-2" data-testid="pipeline-operations-ws-control-actions">
              <Button disabled={!isSuperAdmin} onClick={() => openActionDialog("ws_reconnect", "control", reasonControl)} data-testid="pipeline-operations-action-ws-reconnect-button">Reconnect WS</Button>
              <Button variant="outline" disabled={!isSuperAdmin} onClick={() => openActionDialog("ws_new_session", "control", reasonControl)} data-testid="pipeline-operations-action-ws-new-session-button">Force New Session</Button>
              <Button variant="outline" disabled={!isSuperAdmin} onClick={() => openActionDialog("pipeline_resync", "control", reasonControl)} data-testid="pipeline-operations-action-pipeline-resync-button">Force Resync</Button>
              <Button variant="outline" disabled={!isSuperAdmin} onClick={() => openActionDialog("pipeline_flush", "control", reasonControl)} data-testid="pipeline-operations-action-pipeline-flush-button">Flush Queues</Button>
            </div>
          }
          resultNode={<ResultBadge result={panelResult.control} testId="pipeline-operations-ws-control-result" />}
        />

        <PanelShell
          title="Gate + Alert Policy Control"
          subtitle="Release gate ve policy değişiklikleri"
          testId="pipeline-operations-gate-panel"
          stateNode={
            <div className="space-y-1 text-xs text-slate-300" data-testid="pipeline-operations-gate-state">
              <p data-testid="pipeline-operations-gate-state-status">gate_status={gateStatus?.status || "-"}</p>
              <p data-testid="pipeline-operations-gate-state-final">final_decision={gateStatus?.final_decision || "-"}</p>
              <p data-testid="pipeline-operations-gate-state-reasons">reason_count={(gateStatus?.reason_codes || []).length}</p>
              <div className="max-h-20 space-y-1 overflow-auto" data-testid="pipeline-operations-gate-rules-table">
                {(gateStatus?.rules || []).slice(0, 6).map((rule, idx) => (
                  <div
                    key={`${rule.rule_id}-${idx}`}
                    className={`rounded border px-2 py-1 ${(rule.result || "").toUpperCase() === "FAIL" ? "border-red-500 bg-red-950/30 text-red-200" : "border-emerald-600 bg-emerald-950/20 text-emerald-200"}`}
                    data-testid={`pipeline-operations-gate-rule-${idx}`}
                  >
                    <p data-testid={`pipeline-operations-gate-rule-id-${idx}`}>{rule.rule_id} · {rule.result}</p>
                    <p data-testid={`pipeline-operations-gate-rule-message-${idx}`}>{rule.message}</p>
                    <button
                      type="button"
                      className="underline"
                      onClick={() => navigate("/admin/execution-policies")}
                      data-testid={`pipeline-operations-gate-rule-fix-hint-${idx}`}
                    >
                      {rule.fix_hint}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          }
          reasonNode={
            <div className="space-y-2" data-testid="pipeline-operations-gate-reason-content">
              <Textarea value={reasonControl} onChange={(e) => setReasonControl(e.target.value)} className="min-h-20 bg-slate-950" data-testid="pipeline-operations-gate-reason-input" />
              <div className="grid grid-cols-2 gap-2" data-testid="pipeline-operations-alert-policy-form-grid">
                <Input value={alertPolicyForm.execution_quality_warning_threshold} onChange={(e) => setAlertPolicyForm((prev) => ({ ...prev, execution_quality_warning_threshold: e.target.value }))} data-testid="pipeline-operations-policy-warning-input" />
                <Input value={alertPolicyForm.execution_quality_critical_threshold} onChange={(e) => setAlertPolicyForm((prev) => ({ ...prev, execution_quality_critical_threshold: e.target.value }))} data-testid="pipeline-operations-policy-critical-input" />
                <Input value={alertPolicyForm.permission_drift_warning_per_day} onChange={(e) => setAlertPolicyForm((prev) => ({ ...prev, permission_drift_warning_per_day: e.target.value }))} data-testid="pipeline-operations-policy-drift-warning-input" />
                <Input value={alertPolicyForm.permission_drift_critical_per_day} onChange={(e) => setAlertPolicyForm((prev) => ({ ...prev, permission_drift_critical_per_day: e.target.value }))} data-testid="pipeline-operations-policy-drift-critical-input" />
              </div>
            </div>
          }
          actionNode={
            <div className="grid gap-2" data-testid="pipeline-operations-gate-actions">
              <Button disabled={!isSuperAdmin} onClick={() => openActionDialog("gate_recheck", "control", reasonControl)} data-testid="pipeline-operations-action-gate-recheck-button">Gate Re-check</Button>
              <Button variant="outline" disabled={!isSuperAdmin} onClick={() => openActionDialog("policy_update", "control", reasonControl)} data-testid="pipeline-operations-action-policy-update-button">Policy Update</Button>
              <Button variant="outline" disabled={!isSuperAdmin} onClick={() => openActionDialog("policy_rollback", "control", reasonControl)} data-testid="pipeline-operations-action-policy-rollback-button">Policy Rollback</Button>
              <Button variant="outline" disabled={!isSuperAdmin} onClick={() => openActionDialog("policy_test_alert", "control", reasonControl)} data-testid="pipeline-operations-action-policy-test-alert-button">Send Test Alert</Button>
            </div>
          }
          resultNode={<ResultBadge result={panelResult.control} testId="pipeline-operations-gate-result" />}
        />

        <PanelShell
          title="Override Control"
          subtitle="Runtime override yarat / iptal"
          testId="pipeline-operations-override-panel"
          stateNode={
            <div className="space-y-1 text-xs text-slate-300" data-testid="pipeline-operations-override-state">
              <p data-testid="pipeline-operations-override-state-active-count">active_count={overridesActive.length}</p>
              <p data-testid="pipeline-operations-override-state-history-count">history_count={overrideHistory.length}</p>
              <p data-testid="pipeline-operations-override-state-ttl-cap">ttl_cap=120</p>
              <p data-testid="pipeline-operations-override-state-impacted-total">impacted_total={overridesActive.reduce((sum, item) => sum + Number(item.impacted_trades_count || 0), 0)}</p>
            </div>
          }
          reasonNode={
            <div className="grid gap-2" data-testid="pipeline-operations-override-reason-content">
              <Input value={overrideForm.reason} onChange={(e) => setOverrideForm((prev) => ({ ...prev, reason: e.target.value }))} data-testid="pipeline-operations-override-reason-input" />
              <Input value={overrideForm.confirmation_phrase} onChange={(e) => setOverrideForm((prev) => ({ ...prev, confirmation_phrase: e.target.value }))} data-testid="pipeline-operations-override-phrase-input" />
            </div>
          }
          actionNode={
            <div className="space-y-2" data-testid="pipeline-operations-override-actions">
              <div className="grid grid-cols-2 gap-2" data-testid="pipeline-operations-override-form-grid">
                <Input value={overrideForm.override_type} onChange={(e) => setOverrideForm((prev) => ({ ...prev, override_type: e.target.value }))} data-testid="pipeline-operations-override-type-input" />
                <Input value={overrideForm.scope} onChange={(e) => setOverrideForm((prev) => ({ ...prev, scope: e.target.value }))} data-testid="pipeline-operations-override-scope-input" />
                <Input value={overrideForm.ttl_minutes} onChange={(e) => setOverrideForm((prev) => ({ ...prev, ttl_minutes: e.target.value }))} data-testid="pipeline-operations-override-ttl-input" />
                <Button disabled={!isSuperAdmin} onClick={runOverrideCreate} data-testid="pipeline-operations-override-create-button">Create Override</Button>
              </div>
              <div className="max-h-24 space-y-1 overflow-auto" data-testid="pipeline-operations-override-active-list">
                {overridesActive.slice(0, 8).map((item, idx) => (
                  <div key={item.override_id} className="flex items-center justify-between gap-2 text-[11px]" data-testid={`pipeline-operations-override-active-item-${idx}`}>
                    <span data-testid={`pipeline-operations-override-active-item-text-${idx}`}>{item.override_id} · {item.type} · ttl={item.ttl_remaining_seconds ?? "-"}s · impacted={item.impacted_trades_count ?? 0}</span>
                    <Button size="sm" variant="outline" disabled={!isSuperAdmin} onClick={() => runOverrideCancel(item.override_id)} data-testid={`pipeline-operations-override-cancel-button-${idx}`}>Cancel</Button>
                  </div>
                ))}
              </div>
            </div>
          }
          resultNode={<ResultBadge result={panelResult.override} testId="pipeline-operations-override-result" />}
        />
      </section>

      <section className="space-y-3" data-testid="pipeline-operations-recovery-section">
        <h2 className="text-base font-semibold uppercase tracking-wider text-emerald-300" data-testid="pipeline-operations-recovery-section-title">Recovery</h2>
        <PanelShell
          title="Heartbeat + Service Recovery"
          subtitle="Sistem canlılık kontrolü ve servis yeniden başlatma"
          testId="pipeline-operations-recovery-panel"
          stateNode={
            <div className="space-y-1 text-xs text-slate-300" data-testid="pipeline-operations-recovery-state">
              <p data-testid="pipeline-operations-recovery-state-heartbeat">heartbeat_status={heartbeat?.heartbeat?.status || "-"}</p>
              <p data-testid="pipeline-operations-recovery-state-lag">lag_seconds={heartbeat?.lag_seconds ?? "-"}</p>
              <p data-testid="pipeline-operations-recovery-state-warning">warning={String(heartbeat?.warning_triggered || false)}</p>
            </div>
          }
          reasonNode={
            <Textarea value={reasonRecovery} onChange={(e) => setReasonRecovery(e.target.value)} className="min-h-20 bg-slate-950" data-testid="pipeline-operations-recovery-reason-input" />
          }
          actionNode={
            <div className="space-y-2" data-testid="pipeline-operations-recovery-actions">
              <div className="flex flex-wrap gap-2" data-testid="pipeline-operations-recovery-health-controls">
                <Input value={lagThreshold} onChange={(e) => setLagThreshold(e.target.value)} className="w-36 bg-slate-950" data-testid="pipeline-operations-recovery-lag-threshold-input" />
                <Button variant="outline" onClick={runManualHeartbeat} data-testid="pipeline-operations-recovery-heartbeat-check-button">Manual Health Check</Button>
              </div>
              <div className="flex flex-wrap gap-2" data-testid="pipeline-operations-recovery-service-controls">
                <Input value={serviceTarget} onChange={(e) => setServiceTarget(e.target.value)} className="w-36 bg-slate-950" data-testid="pipeline-operations-recovery-service-target-input" />
                <Button disabled={!isSuperAdmin} onClick={() => openActionDialog("service_restart", "recovery", reasonRecovery)} data-testid="pipeline-operations-recovery-service-restart-button">Restart Service</Button>
              </div>
            </div>
          }
          resultNode={<ResultBadge result={panelResult.recovery} testId="pipeline-operations-recovery-result" />}
        />
      </section>

      <section className="space-y-3" data-testid="pipeline-operations-monitoring-section">
        <h2 className="text-base font-semibold uppercase tracking-wider text-violet-300" data-testid="pipeline-operations-monitoring-section-title">Monitoring</h2>
        <div className="grid gap-3 xl:grid-cols-2" data-testid="pipeline-operations-monitoring-grid">
          <PanelShell
            title="Guard Telemetry"
            subtitle="Bloklanan trade nedenleri"
            testId="pipeline-operations-guard-panel"
            stateNode={
              <div className="space-y-1 text-xs text-slate-300" data-testid="pipeline-operations-guard-state">
                <p data-testid="pipeline-operations-guard-state-blocked">blocked={(guardTelemetry?.blocked_trade_list || []).length}</p>
                <p data-testid="pipeline-operations-guard-state-override-impact">override_impacted={(guardTelemetry?.override_impacted_trades || []).length}</p>
                <p data-testid="pipeline-operations-guard-state-invalid-quote-badge">
                  <span className="inline-flex rounded-full border border-red-500/70 bg-red-950 px-2 py-0.5 text-[11px] font-semibold text-red-200">INVALID_QUOTE_ASSET {invalidQuoteReasonCount}</span>
                </p>
              </div>
            }
            reasonNode={<p className="text-xs text-slate-400" data-testid="pipeline-operations-guard-reason">Bu panel root-cause önceliklendirmesi için kullanılır.</p>}
            actionNode={
              <div className="space-y-2" data-testid="pipeline-operations-guard-actions-view">
                <div className="max-h-20 space-y-1 overflow-auto" data-testid="pipeline-operations-guard-top-reasons-list">
                  {topReasons.map((item, idx) => (
                    <p
                      key={`${item.reason}-${idx}`}
                      className={`text-[11px] ${String(item.reason).toUpperCase() === "INVALID_QUOTE_ASSET" ? "font-semibold text-red-300" : "text-slate-300"}`}
                      data-testid={`pipeline-operations-guard-top-reason-${idx}`}
                    >
                      {item.reason}: {item.count}
                    </p>
                  ))}
                </div>
                <div className="max-h-24 space-y-1 overflow-auto" data-testid="pipeline-operations-guard-blocked-trades-list">
                  {blockedTrades.map((item, idx) => (
                    <p
                      key={`${item.id}-${idx}`}
                      className={`rounded px-2 py-1 text-[11px] ${(item.reason_codes || [item.reason || "UNKNOWN"])[0] === "INVALID_QUOTE_ASSET" ? "border border-red-500/60 bg-red-950/50 text-red-200" : "text-slate-300"}`}
                      data-testid={`pipeline-operations-guard-blocked-trade-${idx}`}
                    >
                      {item.symbol || "UNKNOWN"} | {(item.reason_codes || [item.reason || "UNKNOWN"])[0] || "UNKNOWN"} | {item.updated_at || "-"}
                    </p>
                  ))}
                </div>
              </div>
            }
            resultNode={<ResultBadge result={panelResult.monitoring} testId="pipeline-operations-guard-result" />}
          />

          <PanelShell
            title="Exchange Monitoring"
            subtitle="Drift ve bağlantı eğilimi"
            testId="pipeline-operations-exchange-panel"
            stateNode={
              <div className="space-y-1 text-xs text-slate-300" data-testid="pipeline-operations-exchange-state">
                <p data-testid="pipeline-operations-exchange-state-drift-count">drift_count={(exchangeMonitoring?.drift_details || []).length}</p>
                <p data-testid="pipeline-operations-exchange-state-connection-count">connection_count={(exchangeMonitoring?.connection_details || []).length}</p>
              </div>
            }
            reasonNode={<p className="text-xs text-slate-400" data-testid="pipeline-operations-exchange-reason">Drift trendi yükselirse key revalidation/disable aksiyonu planlanır.</p>}
            actionNode={
              <div className="space-y-2" data-testid="pipeline-operations-exchange-trend-list">
                <div className="max-h-20 space-y-1 overflow-auto" data-testid="pipeline-operations-exchange-trend-buckets">
                  {exchangeTrend.map((item, idx) => (
                    <p key={`${item.bucket}-${idx}`} className="text-[11px] text-slate-300" data-testid={`pipeline-operations-exchange-trend-item-${idx}`}>{item.bucket}: {item.count}</p>
                  ))}
                </div>
                <div className="max-h-24 space-y-1 overflow-auto" data-testid="pipeline-operations-exchange-connection-table">
                  {(exchangeMonitoring?.connection_details || []).slice(0, 6).map((item, idx) => (
                    <div key={item.id} className="flex items-center justify-between gap-2 text-[11px]" data-testid={`pipeline-operations-exchange-connection-row-${idx}`}>
                      <span data-testid={`pipeline-operations-exchange-connection-text-${idx}`}>{item.exchange} · {item.market_type} · {item.user_id}</span>
                      <div className="flex gap-1" data-testid={`pipeline-operations-exchange-connection-actions-${idx}`}>
                        <Button size="sm" variant="outline" disabled={!isSuperAdmin} onClick={() => openActionDialog("exchange_revalidate", "monitoring", reasonControl, { connectionId: item.id })} data-testid={`pipeline-operations-exchange-revalidate-${idx}`}>Revalidate</Button>
                        <Button size="sm" variant="outline" disabled={!isSuperAdmin} onClick={() => openActionDialog("exchange_disable", "monitoring", reasonControl, { connectionId: item.id })} data-testid={`pipeline-operations-exchange-disable-${idx}`}>Disable</Button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            }
            resultNode={<ResultBadge result={panelResult.monitoring} testId="pipeline-operations-exchange-result" />}
          />

          <PanelShell
            title="Alert Center"
            subtitle="Açık alarmlara müdahale"
            testId="pipeline-operations-alert-center-panel"
            stateNode={
              <div className="space-y-1 text-xs text-slate-300" data-testid="pipeline-operations-alert-center-state">
                <p data-testid="pipeline-operations-alert-center-state-total">total_alerts={alertsHistory.length}</p>
                <p data-testid="pipeline-operations-alert-center-state-selection">selected={bulkSelection.length}</p>
              </div>
            }
            reasonNode={
              <div className="space-y-2" data-testid="pipeline-operations-alert-center-reason-content">
                <Textarea value={reasonAlerts} onChange={(e) => setReasonAlerts(e.target.value)} className="min-h-20 bg-slate-950" data-testid="pipeline-operations-alert-center-reason-input" />
                <Input value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)} className="bg-slate-950" data-testid="pipeline-operations-alert-center-severity-filter-input" placeholder="severity (all|INFO|WARNING|CRITICAL)" />
                <Input value={alertSinceHours} onChange={(e) => setAlertSinceHours(e.target.value)} className="bg-slate-950" data-testid="pipeline-operations-alert-center-time-filter-input" placeholder="since_hours" />
                <Input value={alertEventFilter} onChange={(e) => setAlertEventFilter(e.target.value)} className="bg-slate-950" data-testid="pipeline-operations-alert-center-event-filter-input" placeholder="event type" />
              </div>
            }
            actionNode={
              <div className="space-y-2" data-testid="pipeline-operations-alert-center-actions">
                <div className="flex flex-wrap gap-2" data-testid="pipeline-operations-alert-center-bulk-actions">
                  <Button size="sm" variant="outline" onClick={() => runBulkAlertAction("ack")} data-testid="pipeline-operations-alert-center-bulk-ack-button">Bulk Ack</Button>
                  <Button size="sm" variant="outline" onClick={() => runBulkAlertAction("mute")} data-testid="pipeline-operations-alert-center-bulk-mute-button">Bulk Mute</Button>
                  <Button size="sm" variant="outline" onClick={() => runBulkAlertAction("resolve")} data-testid="pipeline-operations-alert-center-bulk-resolve-button">Bulk Resolve</Button>
                </div>
                <div className="max-h-36 space-y-1 overflow-auto" data-testid="pipeline-operations-alert-center-list">
                  {alertsHistory.slice(0, 12).map((item, idx) => (
                    <div key={item.id} className="flex items-center justify-between gap-2 text-[11px]" data-testid={`pipeline-operations-alert-center-item-${idx}`}>
                      <label className="flex items-center gap-2" data-testid={`pipeline-operations-alert-center-item-label-${idx}`}>
                        <input
                          type="checkbox"
                          checked={bulkSelection.includes(item.id)}
                          onChange={(e) => setBulkSelection((prev) => (e.target.checked ? [...prev, item.id] : prev.filter((id) => id !== item.id)))}
                          data-testid={`pipeline-operations-alert-center-select-${idx}`}
                        />
                        <span data-testid={`pipeline-operations-alert-center-text-${idx}`}>
                          {item.alert_type} ·
                          <span className={`ml-1 rounded px-1 py-0.5 ${(item.severity || "").toUpperCase() === "CRITICAL" ? "bg-red-700 text-white" : (item.severity || "").toUpperCase() === "WARNING" ? "bg-amber-500 text-black" : "bg-emerald-600 text-white"}`}>{item.severity}</span>
                        </span>
                      </label>
                      <div className="flex gap-1" data-testid={`pipeline-operations-alert-center-row-actions-${idx}`}>
                        <Button size="sm" variant="outline" onClick={() => runAlertAction(item.id, "ack")} data-testid={`pipeline-operations-alert-center-ack-${idx}`}>Ack</Button>
                        <Button size="sm" variant="outline" onClick={() => runAlertAction(item.id, "mute", 30)} data-testid={`pipeline-operations-alert-center-mute-${idx}`}>Mute</Button>
                        <Button size="sm" variant="outline" onClick={() => runAlertAction(item.id, "resolve")} data-testid={`pipeline-operations-alert-center-resolve-${idx}`}>Resolve</Button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            }
            resultNode={<ResultBadge result={panelResult.alerts} testId="pipeline-operations-alert-center-result" />}
          />
        </div>
      </section>

      <section className="space-y-3" data-testid="pipeline-operations-traceability-section">
        <h2 className="text-base font-semibold uppercase tracking-wider text-fuchsia-300" data-testid="pipeline-operations-traceability-section-title">Traceability</h2>
        <PanelShell
          title="Action Audit + Hardening Analytics"
          subtitle="Kim / neden / hangi trace ile"
          testId="pipeline-operations-traceability-panel"
          stateNode={
            <div className="space-y-1 text-xs text-slate-300" data-testid="pipeline-operations-traceability-state">
              <p data-testid="pipeline-operations-traceability-state-audit-count">action_audit_count={actionAudit.length}</p>
              <p data-testid="pipeline-operations-traceability-state-hardening-count">hardening_count={hardeningAnalytics.length}</p>
            </div>
          }
          reasonNode={<p className="text-xs text-slate-400" data-testid="pipeline-operations-traceability-reason">Tüm kritik aksiyonlar trace_id ile Action→Result bağlamında takip edilir.</p>}
          actionNode={
            <div className="space-y-2" data-testid="pipeline-operations-traceability-actions">
              <Button variant="outline" onClick={() => openAuditDrawer("action_audit")} data-testid="pipeline-operations-traceability-open-action-audit-button">Action Audit Aç</Button>
              <Button variant="outline" onClick={() => openAuditDrawer("audit_logs")} data-testid="pipeline-operations-traceability-open-audit-logs-button">Audit Logs Aç</Button>
              <div className="max-h-28 space-y-1 overflow-auto" data-testid="pipeline-operations-traceability-audit-list">
                {auditSlice.map((item, idx) => (
                  <p key={item.id} className="text-[11px] text-slate-300" data-testid={`pipeline-operations-traceability-audit-item-${idx}`}>
                    {item.created_at} · {item.action} · {item.actor_role}
                  </p>
                ))}
              </div>
            </div>
          }
          resultNode={<ResultBadge result={panelResult.traceability} testId="pipeline-operations-traceability-result" />}
        />
      </section>

      <Sheet open={auditDrawerOpen} onOpenChange={setAuditDrawerOpen}>
        <SheetContent side="right" className="w-full max-w-4xl overflow-y-auto border-l border-emerald-700 bg-slate-950" data-testid="pipeline-operations-action-audit-drawer">
          <SheetHeader>
            <SheetTitle data-testid="pipeline-operations-action-audit-drawer-title">Action Audit & Logs</SheetTitle>
            <SheetDescription data-testid="pipeline-operations-action-audit-drawer-description">Unified panel içinde traceability inceleme alanı</SheetDescription>
          </SheetHeader>

          <div className="mt-4 space-y-3" data-testid="pipeline-operations-action-audit-drawer-filters">
            <div className="grid gap-2 md:grid-cols-4" data-testid="pipeline-operations-action-audit-filter-grid">
              <Input value={auditFilters.user_id} onChange={(e) => setAuditFilters((prev) => ({ ...prev, user_id: e.target.value }))} placeholder="user_id" data-testid="pipeline-operations-action-audit-filter-user-id-input" />
              <Input value={auditFilters.action_type} onChange={(e) => setAuditFilters((prev) => ({ ...prev, action_type: e.target.value }))} placeholder="action_type" data-testid="pipeline-operations-action-audit-filter-action-type-input" />
              <Input value={auditFilters.since_hours} onChange={(e) => setAuditFilters((prev) => ({ ...prev, since_hours: e.target.value }))} placeholder="last N hours" data-testid="pipeline-operations-action-audit-filter-since-hours-input" />
              <Input value={auditFilters.trace_id} onChange={(e) => setAuditFilters((prev) => ({ ...prev, trace_id: e.target.value }))} placeholder="trace_id" data-testid="pipeline-operations-action-audit-filter-trace-id-input" />
            </div>
            <Button variant="outline" onClick={() => loadAuditDrawerData()} data-testid="pipeline-operations-action-audit-filter-apply-button">Filtre Uygula</Button>
          </div>

          <div className="mt-4 flex gap-2" data-testid="pipeline-operations-action-audit-drawer-tabs">
            <Button variant={auditDrawerTab === "action_audit" ? "default" : "outline"} onClick={() => { setAuditDrawerTab("action_audit"); setSelectedAuditDetail(auditDrawerItems[0] || null); }} data-testid="pipeline-operations-action-audit-tab-button">Action Audit</Button>
            <Button variant={auditDrawerTab === "audit_logs" ? "default" : "outline"} onClick={() => { setAuditDrawerTab("audit_logs"); setSelectedAuditDetail(auditLogDrawerItems[0] || null); }} data-testid="pipeline-operations-audit-logs-tab-button">Audit Logs</Button>
            <Button variant={auditDrawerTab === "hardening" ? "default" : "outline"} onClick={() => { setAuditDrawerTab("hardening"); setSelectedAuditDetail(null); }} data-testid="pipeline-operations-hardening-analytics-tab-button">Hardening Analytics</Button>
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-2" data-testid="pipeline-operations-action-audit-drawer-content-grid">
            <div className="max-h-[52vh] space-y-2 overflow-auto" data-testid="pipeline-operations-action-audit-drawer-list">
              {auditDrawerTab === "action_audit" && auditDrawerItems.map((item, idx) => {
                const details = item.details || {};
                const traceId = details.trace_id || details.request_id || "-";
                const status = details.status || item.severity || "-";
                const message = details.message || details.reason || "-";
                const snapshot = JSON.stringify(details.state_snapshot || details.snapshot || {}).slice(0, 120);
                return (
                  <button key={item.id} type="button" className="w-full rounded border border-slate-700 p-2 text-left text-xs" onClick={() => openAuditDetail(item.id)} data-testid={`pipeline-operations-action-audit-drawer-item-${idx}`}>
                    <p data-testid={`pipeline-operations-action-audit-item-action-${idx}`}>{item.action}</p>
                    <p data-testid={`pipeline-operations-action-audit-item-meta-${idx}`}>{item.actor_user_id} · {item.created_at}</p>
                    <p data-testid={`pipeline-operations-action-audit-item-trace-${idx}`}>trace_id={traceId}</p>
                    <p data-testid={`pipeline-operations-action-audit-item-status-${idx}`}>status={status}</p>
                    <p data-testid={`pipeline-operations-action-audit-item-message-${idx}`}>message={message}</p>
                    <p data-testid={`pipeline-operations-action-audit-item-snapshot-${idx}`}>snapshot={snapshot || "-"}</p>
                  </button>
                );
              })}

              {auditDrawerTab === "audit_logs" && auditLogDrawerItems.map((item, idx) => {
                const details = item.details || {};
                const traceId = details.trace_id || item.request_id || "-";
                const status = details.status || item.severity || "-";
                const message = details.message || details.reason || "-";
                const snapshot = JSON.stringify(details.state_snapshot || details.snapshot || {}).slice(0, 120);
                return (
                  <button key={item.id} type="button" className="w-full rounded border border-slate-700 p-2 text-left text-xs" onClick={() => setSelectedAuditDetail(item)} data-testid={`pipeline-operations-audit-logs-drawer-item-${idx}`}>
                    <p data-testid={`pipeline-operations-audit-logs-item-action-${idx}`}>{item.action}</p>
                    <p data-testid={`pipeline-operations-audit-logs-item-meta-${idx}`}>{item.actor_user_id} · {item.created_at}</p>
                    <p data-testid={`pipeline-operations-audit-logs-item-trace-${idx}`}>trace_id={traceId}</p>
                    <p data-testid={`pipeline-operations-audit-logs-item-status-${idx}`}>status={status}</p>
                    <p data-testid={`pipeline-operations-audit-logs-item-message-${idx}`}>message={message}</p>
                    <p data-testid={`pipeline-operations-audit-logs-item-snapshot-${idx}`}>snapshot={snapshot || "-"}</p>
                  </button>
                );
              })}

              {auditDrawerTab === "hardening" && actionAudit.slice(0, 25).filter((item) => {
                const action = String(item.action || "").toUpperCase();
                return action.includes("OVERRIDE") || action.includes("HEARTBEAT") || action.includes("GATE") || action.includes("WS_");
              }).map((item, idx) => (
                <article key={item.id} className="rounded border border-amber-600 p-2 text-xs" data-testid={`pipeline-operations-hardening-analytics-item-${idx}`}>
                  <p data-testid={`pipeline-operations-hardening-analytics-action-${idx}`}>{item.action}</p>
                  <p data-testid={`pipeline-operations-hardening-analytics-meta-${idx}`}>{item.created_at} · {item.actor_role}</p>
                </article>
              ))}
            </div>

            <div className="max-h-[52vh] overflow-auto rounded border border-slate-700 p-3 text-xs" data-testid="pipeline-operations-action-audit-drawer-detail">
              <p className="font-semibold" data-testid="pipeline-operations-action-audit-detail-title">Action / Result Detail</p>
              <pre className="mt-2 whitespace-pre-wrap" data-testid="pipeline-operations-action-audit-detail-json">{JSON.stringify(selectedAuditDetail || {}, null, 2)}</pre>
            </div>
          </div>
        </SheetContent>
      </Sheet>

      <Dialog open={exportModal.open} onOpenChange={(open) => setExportModal((prev) => ({ ...prev, open }))}>
        <DialogContent className="max-w-xl border border-emerald-700 bg-slate-950" data-testid="pipeline-operations-export-modal">
          <DialogHeader>
            <DialogTitle data-testid="pipeline-operations-export-modal-title">Export Data</DialogTitle>
            <DialogDescription data-testid="pipeline-operations-export-modal-description">Audit-first export job oluştur</DialogDescription>
          </DialogHeader>
          <div className="grid gap-2" data-testid="pipeline-operations-export-modal-form">
            <Input value={exportModal.range} onChange={(e) => setExportModal((prev) => ({ ...prev, range: e.target.value }))} data-testid="pipeline-operations-export-range-input" placeholder="range (1h/24h/7d/30d)" />
            <Input value={exportModal.output_format} onChange={(e) => setExportModal((prev) => ({ ...prev, output_format: e.target.value }))} data-testid="pipeline-operations-export-format-input" placeholder="csv/json" />
            <Input value={exportModal.metrics} onChange={(e) => setExportModal((prev) => ({ ...prev, metrics: e.target.value }))} data-testid="pipeline-operations-export-metrics-input" placeholder="latency_avg_ms,pnl_sum,risk_veto_count" />
            <Input value={exportModal.symbol} onChange={(e) => setExportModal((prev) => ({ ...prev, symbol: e.target.value.toUpperCase() }))} data-testid="pipeline-operations-export-symbol-input" placeholder="symbol(optional)" />
            <Input value={exportModal.strategy} onChange={(e) => setExportModal((prev) => ({ ...prev, strategy: e.target.value }))} data-testid="pipeline-operations-export-strategy-input" placeholder="strategy(optional)" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setExportModal((prev) => ({ ...prev, open: false }))} data-testid="pipeline-operations-export-cancel-button">Vazgeç</Button>
            <Button onClick={createExportJob} data-testid="pipeline-operations-export-submit-button">Create Export Job</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={bulkImportModal.open} onOpenChange={(open) => setBulkImportModal((prev) => ({ ...prev, open }))}>
        <DialogContent className="max-w-2xl border border-emerald-700 bg-slate-950" data-testid="pipeline-operations-bulk-import-modal">
          <DialogHeader>
            <DialogTitle data-testid="pipeline-operations-bulk-import-modal-title">Bulk Symbol Import</DialogTitle>
            <DialogDescription data-testid="pipeline-operations-bulk-import-modal-description">CSV paste/upload + validation preview</DialogDescription>
          </DialogHeader>
          <div className="space-y-2" data-testid="pipeline-operations-bulk-import-modal-form">
            <input type="file" accept=".csv,text/csv" onChange={(e) => onBulkCsvFileUpload(e.target.files?.[0])} data-testid="pipeline-operations-bulk-import-file-input" />
            <Textarea value={bulkImportModal.csvText} onChange={(e) => setBulkImportModal((prev) => ({ ...prev, csvText: e.target.value }))} className="min-h-32" data-testid="pipeline-operations-bulk-import-textarea" />
            <div className="flex gap-2" data-testid="pipeline-operations-bulk-import-actions">
              <Button variant="outline" onClick={previewBulkImport} data-testid="pipeline-operations-bulk-import-preview-button">Preview</Button>
              <Input value={bulkImportModal.applyMode} onChange={(e) => setBulkImportModal((prev) => ({ ...prev, applyMode: e.target.value }))} className="w-48" data-testid="pipeline-operations-bulk-import-apply-mode-input" />
              <Button variant="outline" onClick={applyBulkImport} data-testid="pipeline-operations-bulk-import-apply-button">Apply</Button>
              {bulkImportModal.preview?.preview_id && (
                <Button
                  variant="outline"
                  onClick={() => window.open(`${process.env.REACT_APP_BACKEND_URL}/api/admin/universe-monitor/universe/symbols/bulk-import/${bulkImportModal.preview.preview_id}/errors.csv`, "_blank")}
                  data-testid="pipeline-operations-bulk-import-errors-export-button"
                >
                  Export Errors
                </Button>
              )}
            </div>

            {bulkImportModal.preview && (
              <div className="rounded border border-slate-700 p-2 text-xs" data-testid="pipeline-operations-bulk-import-preview-summary">
                <p data-testid="pipeline-operations-bulk-import-preview-counts">input={bulkImportModal.preview.total_input} valid={bulkImportModal.preview.valid_count} invalid={bulkImportModal.preview.invalid_count}</p>
                <p data-testid="pipeline-operations-bulk-import-preview-reasons">reasons={JSON.stringify(bulkImportModal.preview.reason_counts || {})}</p>
                <div className="mt-1 max-h-28 overflow-auto" data-testid="pipeline-operations-bulk-import-preview-invalid-list">
                  {(bulkImportModal.preview.invalid_items || []).slice(0, 20).map((item, idx) => (
                    <p key={`${item.symbol}-${idx}`} data-testid={`pipeline-operations-bulk-import-invalid-item-${idx}`}>{item.symbol} · {item.reason}</p>
                  ))}
                </div>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setBulkImportModal((prev) => ({ ...prev, open: false }))} data-testid="pipeline-operations-bulk-import-close-button">Kapat</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={symbolListModal.open} onOpenChange={(open) => setSymbolListModal((prev) => ({ ...prev, open }))}>
        <DialogContent className="max-w-xl border border-emerald-700 bg-slate-950" data-testid="pipeline-operations-symbol-list-modal">
          <DialogHeader>
            <DialogTitle data-testid="pipeline-operations-symbol-list-modal-title">{symbolListModal.listType} edit</DialogTitle>
            <DialogDescription data-testid="pipeline-operations-symbol-list-modal-description">
              Virgül veya satır ile symbol girin (örn: BTCUSDT, ETHUSDT).
            </DialogDescription>
          </DialogHeader>
          <Textarea
            value={symbolListModal.symbolsText}
            onChange={(e) => setSymbolListModal((prev) => ({ ...prev, symbolsText: e.target.value }))}
            className="min-h-36"
            data-testid="pipeline-operations-symbol-list-modal-textarea"
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setSymbolListModal((prev) => ({ ...prev, open: false }))} data-testid="pipeline-operations-symbol-list-modal-cancel-button">Vazgeç</Button>
            <Button onClick={submitSymbolListEditor} data-testid="pipeline-operations-symbol-list-modal-save-button">Kaydet</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={actionDialog.open} onOpenChange={(open) => setActionDialog((prev) => ({ ...prev, open }))}>
        <DialogContent className="max-w-xl border border-amber-700 bg-slate-950" data-testid="pipeline-operations-action-dialog">
          <DialogHeader>
            <DialogTitle data-testid="pipeline-operations-action-dialog-title">Control Action Confirm</DialogTitle>
            <DialogDescription data-testid="pipeline-operations-action-dialog-description">
              reason + phrase zorunlu. Beklenen phrase: {ACTION_META[actionDialog.actionKey]?.phrase || "-"}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2" data-testid="pipeline-operations-action-dialog-form">
            <Textarea value={actionDialog.reason} onChange={(e) => setActionDialog((prev) => ({ ...prev, reason: e.target.value }))} data-testid="pipeline-operations-action-dialog-reason-input" />
            <Input value={actionDialog.phrase} onChange={(e) => setActionDialog((prev) => ({ ...prev, phrase: e.target.value }))} data-testid="pipeline-operations-action-dialog-phrase-input" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setActionDialog((prev) => ({ ...prev, open: false }))} data-testid="pipeline-operations-action-dialog-cancel-button">Vazgeç</Button>
            <Button onClick={submitDialogAction} data-testid="pipeline-operations-action-dialog-submit-button">Onayla</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <p className="text-xs text-slate-500" data-testid="pipeline-operations-loading-state">loading={String(loading)} refreshing={String(refreshing)}</p>
    </section>
  );
};
