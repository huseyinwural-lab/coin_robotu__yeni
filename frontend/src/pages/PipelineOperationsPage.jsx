import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
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

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

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
  const [stateValidation, setStateValidation] = useState({
    wsReconnectSessionChanged: null,
    overrideAffectsExecution: null,
    gateUsesCiResult: null,
    tradeBlockVisible: null,
    lastCheckedAt: null,
  });
  const [panelResult, setPanelResult] = useState({
    control: null,
    recovery: null,
    monitoring: null,
    traceability: null,
    override: null,
    alerts: null,
  });

  const [actionDialog, setActionDialog] = useState({
    open: false,
    actionKey: "",
    reason: "",
    phrase: "",
    panelKey: "control",
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
            limit: 100,
          },
        }),
        apiClient.get("/runtime/alert-policy"),
        apiClient.get("/runtime/action-audit", { params: { since_hours: 48, limit: 40 } }),
        apiClient.get("/runtime/quote-policy"),
      ]);

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

      const policy = policyRes.data?.policy;
      if (policy) {
        setAlertPolicyForm({
          execution_quality_warning_threshold: String(policy.execution_quality_warning_threshold ?? 60),
          execution_quality_critical_threshold: String(policy.execution_quality_critical_threshold ?? 40),
          permission_drift_warning_per_day: String(policy.permission_drift_warning_per_day ?? 2),
          permission_drift_critical_per_day: String(policy.permission_drift_critical_per_day ?? 5),
        });
      }

      const guardTopReasons = guardRes.data?.top_reasons || [];
      const hasInvalidQuoteBlock = guardTopReasons.some((item) => String(item?.reason || "").toUpperCase() === "INVALID_QUOTE_ASSET");
      setStateValidation((prev) => ({
        ...prev,
        tradeBlockVisible: hasInvalidQuoteBlock,
        lastCheckedAt: new Date().toISOString(),
      }));

      return {
        wsHealth: wsRes.data || null,
        gateStatus: gateRes.data || null,
        overridesActive: activeRes.data?.items || [],
        guardTelemetry: guardRes.data || null,
      };
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Pipeline operations verisi alınamadı");
      return null;
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [severityFilter]);

  useEffect(() => {
    load(true);
  }, [load]);

  const openActionDialog = (actionKey, panelKey, reasonHint) => {
    setActionDialog({
      open: true,
      actionKey,
      reason: reasonHint || (panelKey === "recovery" ? reasonRecovery : reasonControl),
      phrase: "",
      panelKey,
    });
  };

  const setActionSuccess = (panelKey, payload, toastTitle) => {
    const resultPayload = payload || null;
    setPanelResult((prev) => ({ ...prev, [panelKey]: resultPayload }));
    toast.success(`${toastTitle} | trace_id: ${resultPayload?.trace_id || "-"}`);
  };

  const setActionFailure = (panelKey, error, toastTitle) => {
    const { traceId, message } = extractErrorMeta(error);
    setPanelResult((prev) => ({
      ...prev,
      [panelKey]: { status: "error", trace_id: traceId, message },
    }));
    toast.error(`${toastTitle} | trace_id: ${traceId} | ${message}`);
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

    const previousWsSessionId = wsHealth?.state?.session_id || null;
    try {
      let response;
      if (actionDialog.actionKey === "service_restart") {
        response = await apiClient.post(meta.endpoint, {
          reason: actionDialog.reason,
          confirmation_phrase: actionDialog.phrase,
          service: serviceTarget,
        });
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
      } else {
        response = await apiClient.post(meta.endpoint, {
          reason: actionDialog.reason,
          confirmation_phrase: actionDialog.phrase,
        });
      }

      setActionSuccess(actionDialog.panelKey, response.data || null, "Aksiyon başarılı");
      setActionDialog((prev) => ({ ...prev, open: false }));
      const latest = await load(false);

      if (["ws_reconnect", "ws_new_session"].includes(actionDialog.actionKey)) {
        const nextWsSessionId = latest?.wsHealth?.state?.session_id || null;
        setStateValidation((prev) => ({
          ...prev,
          wsReconnectSessionChanged: Boolean(previousWsSessionId && nextWsSessionId && previousWsSessionId !== nextWsSessionId),
        }));
      }

      if (actionDialog.actionKey === "gate_recheck") {
        const hasCiScripts = Array.isArray(response.data?.scripts) && response.data.scripts.length > 0;
        setStateValidation((prev) => ({ ...prev, gateUsesCiResult: hasCiScripts }));
      }
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
    const previousCount = overridesActive.length;
    try {
      const { data } = await apiClient.post("/runtime/override/create", {
        override_type: overrideForm.override_type,
        scope: overrideForm.scope,
        ttl_minutes: Number(overrideForm.ttl_minutes || 30),
        reason: overrideForm.reason,
        confirmation_phrase: overrideForm.confirmation_phrase,
      });
      setActionSuccess("override", data || null, "Override oluşturma başarılı");
      const latest = await load(false);
      const currentCount = latest?.overridesActive?.length ?? previousCount;
      setStateValidation((prev) => ({ ...prev, overrideAffectsExecution: currentCount !== previousCount }));
    } catch (error) {
      setActionFailure("override", error, "Override oluşturma başarısız");
    }
  };

  const runOverrideCancel = async (overrideId) => {
    const previousCount = overridesActive.length;
    try {
      const { data } = await apiClient.post(`/runtime/override/${overrideId}/cancel`, {
        reason: overrideForm.reason,
        confirmation_phrase: "CANCEL OVERRIDE",
      });
      setActionSuccess("override", data || null, "Override iptali başarılı");
      const latest = await load(false);
      const currentCount = latest?.overridesActive?.length ?? previousCount;
      setStateValidation((prev) => ({ ...prev, overrideAffectsExecution: currentCount !== previousCount }));
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
              Öncelik sırası: Control → Recovery → Monitoring → Traceability · role={user?.role || "unknown"}
            </p>
          </div>
          <div className="flex flex-wrap gap-2" data-testid="pipeline-operations-header-actions">
            <Button variant="outline" onClick={() => navigate("/admin/pipeline-control")} data-testid="pipeline-operations-open-legacy-page-button">Legacy Pipeline Control</Button>
            <Button variant="outline" onClick={() => navigate("/admin/live-trading-dashboard")} data-testid="pipeline-operations-open-live-dashboard-button">Live Dashboard</Button>
            <Button variant="outline" onClick={() => load(false)} data-testid="pipeline-operations-refresh-button">Yenile</Button>
          </div>
        </div>
      </header>

      <SummaryBar
        wsHealth={wsHealth}
        gateStatus={gateStatus}
        overridesActive={overridesActive}
        alertsHistory={alertsHistory}
        allowedQuoteAssets={allowedQuoteAssets}
        testId="pipeline-operations-summary-bar"
      />

      <article className="rounded-xl border border-slate-700 bg-slate-900/90 p-4" data-testid="pipeline-operations-state-validation-panel">
        <h3 className="text-base font-semibold text-slate-100" data-testid="pipeline-operations-state-validation-title">State Validation Checklist</h3>
        <p className="text-xs text-slate-400" data-testid="pipeline-operations-state-validation-description">Dummy state yok: her kontrol canlı aksiyon/telemetry verisiyle doğrulanır.</p>
        <div className="mt-3 grid gap-2 md:grid-cols-2" data-testid="pipeline-operations-state-validation-grid">
          <p data-testid="pipeline-operations-state-validation-ws">
            WS reconnect session değişimi: <span className="font-semibold">{stateValidation.wsReconnectSessionChanged === null ? "BEKLENİYOR" : stateValidation.wsReconnectSessionChanged ? "PASS" : "FAIL"}</span>
          </p>
          <p data-testid="pipeline-operations-state-validation-override">
            Override state etkisi: <span className="font-semibold">{stateValidation.overrideAffectsExecution === null ? "BEKLENİYOR" : stateValidation.overrideAffectsExecution ? "PASS" : "FAIL"}</span>
          </p>
          <p data-testid="pipeline-operations-state-validation-gate">
            Gate CI script sonucu: <span className="font-semibold">{stateValidation.gateUsesCiResult === null ? "BEKLENİYOR" : stateValidation.gateUsesCiResult ? "PASS" : "FAIL"}</span>
          </p>
          <p data-testid="pipeline-operations-state-validation-block">
            Trade block guard listesine düşüş: <span className="font-semibold">{stateValidation.tradeBlockVisible === null ? "BEKLENİYOR" : stateValidation.tradeBlockVisible ? "PASS" : "FAIL"}</span>
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
                    <span data-testid={`pipeline-operations-override-active-item-text-${idx}`}>{item.override_id} · {item.type}</span>
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
              <div className="max-h-28 space-y-1 overflow-auto" data-testid="pipeline-operations-exchange-trend-list">
                {exchangeTrend.map((item, idx) => (
                  <p key={`${item.bucket}-${idx}`} className="text-[11px] text-slate-300" data-testid={`pipeline-operations-exchange-trend-item-${idx}`}>{item.bucket}: {item.count}</p>
                ))}
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
                <Input value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)} className="bg-slate-950" data-testid="pipeline-operations-alert-center-severity-filter-input" />
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
                        <span data-testid={`pipeline-operations-alert-center-text-${idx}`}>{item.alert_type} · {item.severity}</span>
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
              <Button variant="outline" onClick={() => navigate("/admin/action-audit")} data-testid="pipeline-operations-traceability-open-action-audit-button">Action Audit Sayfası</Button>
              <Button variant="outline" onClick={() => navigate("/admin/audit-logs") } data-testid="pipeline-operations-traceability-open-audit-logs-button">Audit Logs</Button>
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
