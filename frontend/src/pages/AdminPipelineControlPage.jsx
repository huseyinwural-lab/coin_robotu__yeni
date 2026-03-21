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
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";

const ACTION_MAP = {
  ws_reconnect: { endpoint: "/runtime/ws/reconnect", phrase: "RECONNECT WS" },
  ws_new_session: { endpoint: "/runtime/ws/force-new-session", phrase: "FORCE NEW WS SESSION" },
  pipeline_resync: { endpoint: "/runtime/pipeline/resync", phrase: "FORCE PIPELINE RESYNC" },
  pipeline_flush: { endpoint: "/runtime/pipeline/flush", phrase: "FLUSH PIPELINE" },
  gate_recheck: { endpoint: "/runtime/gate/recheck", phrase: "RECHECK RELEASE GATE" },
  service_restart: { endpoint: "/runtime/service/restart", phrase: "RESTART SERVICE" },
  test_alert: { endpoint: "/runtime/alert-policy/test-alert", phrase: "SEND TEST ALERT" },
};

export const AdminPipelineControlPage = () => {
  const { user } = useAuth();
  const isSuperAdmin = String(user?.role || "") === "super_admin";

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const [wsHealth, setWsHealth] = useState(null);
  const [gateStatus, setGateStatus] = useState(null);
  const [overridesActive, setOverridesActive] = useState([]);
  const [overrideHistory, setOverrideHistory] = useState([]);
  const [guardTelemetry, setGuardTelemetry] = useState(null);
  const [heartbeat, setHeartbeat] = useState(null);
  const [exchangeMonitoring, setExchangeMonitoring] = useState(null);
  const [hardeningAnalytics, setHardeningAnalytics] = useState([]);
  const [alertsHistory, setAlertsHistory] = useState([]);
  const [alertPolicy, setAlertPolicy] = useState(null);
  const [actionAudit, setActionAudit] = useState([]);

  const [lagThreshold, setLagThreshold] = useState("60");
  const [serviceTarget, setServiceTarget] = useState("all");

  const [overrideForm, setOverrideForm] = useState({ override_type: "risk_override", scope: "global", ttl_minutes: "30" });
  const [alertPolicyForm, setAlertPolicyForm] = useState({
    execution_quality_warning_threshold: "60",
    execution_quality_critical_threshold: "40",
    permission_drift_warning_per_day: "2",
    permission_drift_critical_per_day: "5",
  });
  const [severityFilter, setSeverityFilter] = useState("all");
  const [bulkSelection, setBulkSelection] = useState([]);

  const [actionDialog, setActionDialog] = useState({ open: false, actionKey: "", reason: "", phrase: "", context: {} });

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
        heartbeatRes,
        exchangeRes,
        hardeningRes,
        alertsRes,
        policyRes,
        auditRes,
      ] = await Promise.all([
        apiClient.get("/runtime/ws/health"),
        apiClient.get("/runtime/gate/status"),
        apiClient.get("/runtime/override/active"),
        apiClient.get("/runtime/override/history", { params: { limit: 50 } }),
        apiClient.get("/runtime/guard/telemetry", { params: { limit: 100 } }),
        apiClient.post("/runtime/heartbeat/check", { lag_threshold_seconds: Number(lagThreshold || 60) }),
        apiClient.get("/runtime/exchange/monitoring", { params: { limit: 100 } }),
        apiClient.get("/runtime/hardening/analytics", { params: { time_window_hours: 48 } }),
        apiClient.get("/runtime/alerts/history", { params: { status_filter: "all", severity: severityFilter === "all" ? undefined : severityFilter } }),
        apiClient.get("/runtime/alert-policy"),
        apiClient.get("/runtime/action-audit", { params: { since_hours: 48, limit: 30 } }),
      ]);

      setWsHealth(wsRes.data || null);
      setGateStatus(gateRes.data || null);
      setOverridesActive(activeRes.data?.items || []);
      setOverrideHistory(historyRes.data?.items || []);
      setGuardTelemetry(guardRes.data || null);
      setHeartbeat(heartbeatRes.data || null);
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
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Runtime control verisi alınamadı");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [lagThreshold, severityFilter]);

  useEffect(() => {
    load(true);
  }, [load]);

  const openAction = (actionKey, context = {}) => {
    setActionDialog({ open: true, actionKey, reason: context.reason || "", phrase: "", context });
  };

  const executeAction = async () => {
    const config = ACTION_MAP[actionDialog.actionKey];
    if (!config) return;
    if (!actionDialog.reason || actionDialog.reason.trim().length < 3) {
      toast.error("Reason zorunlu");
      return;
    }
    if (actionDialog.phrase.trim().toUpperCase() !== config.phrase) {
      toast.error(`Phrase hatalı. Beklenen: ${config.phrase}`);
      return;
    }

    try {
      const payload = { reason: actionDialog.reason, confirmation_phrase: actionDialog.phrase };
      if (actionDialog.actionKey === "pipeline_flush") payload.queue_type = "all";
      if (actionDialog.actionKey === "service_restart") payload.service = serviceTarget;
      await apiClient.post(config.endpoint, payload);
      toast.success("Aksiyon tamamlandı");
      setActionDialog((prev) => ({ ...prev, open: false }));
      await load(false);
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : JSON.stringify(detail || {}));
    }
  };

  const createOverrideAction = async () => {
    if (!isSuperAdmin) {
      toast.error("Sadece super_admin override oluşturabilir");
      return;
    }
    try {
      await apiClient.post("/runtime/override/create", {
        ...overrideForm,
        ttl_minutes: Number(overrideForm.ttl_minutes || 30),
        reason: "manual_runtime_override",
        confirmation_phrase: "CREATE OVERRIDE",
      });
      toast.success("Override oluşturuldu");
      await load(false);
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : JSON.stringify(detail || {}));
    }
  };

  const cancelOverrideAction = async (overrideId) => {
    try {
      await apiClient.post(`/runtime/override/${overrideId}/cancel`, {
        reason: "manual_override_cancel",
        confirmation_phrase: "CANCEL OVERRIDE",
      });
      toast.success("Override iptal edildi");
      await load(false);
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : JSON.stringify(detail || {}));
    }
  };

  const runAlertAction = async (alertId, action, muteMinutes = 30) => {
    try {
      await apiClient.post(`/runtime/alerts/${alertId}/action`, {
        action,
        reason: `runtime_alert_${action}`,
        mute_minutes: muteMinutes,
      });
      toast.success(`Alert ${action} tamamlandı`);
      await load(false);
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : JSON.stringify(detail || {}));
    }
  };

  const runBulkAlertAction = async (action) => {
    if (bulkSelection.length === 0) {
      toast.error("Önce alert seçin");
      return;
    }
    try {
      await apiClient.post("/runtime/alerts/bulk-action", {
        ids: bulkSelection,
        action,
        reason: `runtime_alert_bulk_${action}`,
        mute_minutes: 30,
      });
      setBulkSelection([]);
      toast.success(`Bulk ${action} tamamlandı`);
      await load(false);
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : JSON.stringify(detail || {}));
    }
  };

  const updatePolicy = async () => {
    try {
      await apiClient.put("/runtime/alert-policy", {
        execution_quality_warning_threshold: Number(alertPolicyForm.execution_quality_warning_threshold || 60),
        execution_quality_critical_threshold: Number(alertPolicyForm.execution_quality_critical_threshold || 40),
        permission_drift_warning_per_day: Number(alertPolicyForm.permission_drift_warning_per_day || 2),
        permission_drift_critical_per_day: Number(alertPolicyForm.permission_drift_critical_per_day || 5),
        reason: "policy_update_from_runtime_panel",
        confirmation_phrase: "UPDATE ALERT POLICY",
      });
      toast.success("Alert policy güncellendi");
      await load(false);
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : JSON.stringify(detail || {}));
    }
  };

  const rollbackPolicy = async () => {
    try {
      await apiClient.post("/runtime/alert-policy/rollback", {});
      toast.success("Alert policy rollback tamamlandı");
      await load(false);
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : JSON.stringify(detail || {}));
    }
  };

  const filteredHardening = useMemo(() => hardeningAnalytics.slice(0, 40), [hardeningAnalytics]);

  return (
    <section className="space-y-4" data-testid="admin-pipeline-control-page">
      <header className="rounded border border-cyan-700/60 bg-cyan-950/20 p-4" data-testid="admin-pipeline-control-header">
        <h1 className="text-4xl font-black uppercase tracking-tight text-cyan-300" data-testid="admin-pipeline-control-title">Pipeline Control & Recovery</h1>
        <p className="mt-2 text-sm text-slate-400" data-testid="admin-pipeline-control-description">
          Runtime müdahale katmanı · role={user?.role || "unknown"} · refreshing={String(refreshing)}
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-2" data-testid="admin-pipeline-control-top-actions">
        <Button variant="outline" onClick={() => load(false)} data-testid="admin-pipeline-control-refresh-button">Yenile</Button>
        <Input value={lagThreshold} onChange={(e) => setLagThreshold(e.target.value)} className="w-40 bg-slate-900" data-testid="admin-pipeline-control-lag-threshold-input" placeholder="lag threshold sec" />
        <p className="text-xs text-slate-400" data-testid="admin-pipeline-control-heartbeat-status">heartbeat_status={heartbeat?.status || "-"} lag={heartbeat?.lag_seconds || "-"}</p>
      </div>

      <div className="grid gap-3 lg:grid-cols-2" data-testid="admin-pipeline-control-core-grid">
        <article className="rounded border border-slate-700 bg-slate-900 p-3" data-testid="admin-pipeline-control-ws-panel">
          <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="admin-pipeline-control-ws-title">WS / Pipeline Control</p>
          <div className="mt-2 flex flex-wrap gap-2" data-testid="admin-pipeline-control-ws-actions">
            <Button disabled={!isSuperAdmin} onClick={() => openAction("ws_reconnect", { reason: "manual_ws_reconnect" })} data-testid="admin-pipeline-control-ws-reconnect-button">Reconnect WS</Button>
            <Button variant="outline" disabled={!isSuperAdmin} onClick={() => openAction("ws_new_session", { reason: "force_new_ws_session" })} data-testid="admin-pipeline-control-ws-new-session-button">Force New Session</Button>
            <Button variant="outline" disabled={!isSuperAdmin} onClick={() => openAction("pipeline_resync", { reason: "force_pipeline_resync" })} data-testid="admin-pipeline-control-pipeline-resync-button">Force Resync</Button>
            <Button variant="outline" disabled={!isSuperAdmin} onClick={() => openAction("pipeline_flush", { reason: "flush_runtime_queues" })} data-testid="admin-pipeline-control-pipeline-flush-button">Queue Flush</Button>
          </div>
          <p className="mt-2 text-xs text-slate-400" data-testid="admin-pipeline-control-ws-state">session={wsHealth?.state?.session_id || "-"} · reconnects={wsHealth?.state?.reconnect_count || 0}</p>
          <div className="mt-2 max-h-24 space-y-1 overflow-auto" data-testid="admin-pipeline-control-ws-log-list">
            {(wsHealth?.connection_logs || []).slice(-8).map((item, idx) => (
              <p key={`${item.created_at}-${idx}`} className="text-[11px] text-slate-400" data-testid={`admin-pipeline-control-ws-log-item-${idx}`}>{item.created_at} · {item.event}</p>
            ))}
          </div>
        </article>

        <article className="rounded border border-red-700/60 bg-red-950/20 p-3" data-testid="admin-pipeline-control-gate-panel">
          <p className="text-xs uppercase tracking-widest text-red-300" data-testid="admin-pipeline-control-gate-title">Release Gate</p>
          <div className="mt-2 flex flex-wrap gap-2" data-testid="admin-pipeline-control-gate-actions">
            <Button disabled={!isSuperAdmin} onClick={() => openAction("gate_recheck", { reason: "manual_release_gate_recheck" })} data-testid="admin-pipeline-control-gate-recheck-button">Manual Re-check</Button>
            <Button variant="outline" onClick={() => window.location.assign("/admin/execution-policies")} data-testid="admin-pipeline-control-gate-fix-link-button">Config Fix'e Git</Button>
          </div>
          <p className="mt-2 text-xs text-slate-300" data-testid="admin-pipeline-control-gate-status">status={gateStatus?.status || "-"} · final={gateStatus?.final_decision || "-"}</p>
          <div className="mt-2 max-h-24 space-y-1 overflow-auto" data-testid="admin-pipeline-control-gate-reasons-list">
            {(gateStatus?.reason_codes || []).map((item, idx) => (
              <p key={`${item}-${idx}`} className="text-[11px] text-red-200" data-testid={`admin-pipeline-control-gate-reason-${idx}`}>{item}</p>
            ))}
          </div>
        </article>
      </div>

      <div className="grid gap-3 lg:grid-cols-2" data-testid="admin-pipeline-control-override-grid">
        <article className="rounded border border-amber-700/60 bg-amber-950/20 p-3" data-testid="admin-pipeline-control-override-panel">
          <p className="text-xs uppercase tracking-widest text-amber-300" data-testid="admin-pipeline-control-override-title">Override Control</p>
          <div className="mt-2 grid gap-2 md:grid-cols-4" data-testid="admin-pipeline-control-override-form-grid">
            <Input value={overrideForm.override_type} onChange={(e) => setOverrideForm((p) => ({ ...p, override_type: e.target.value }))} data-testid="admin-pipeline-control-override-type-input" />
            <Input value={overrideForm.scope} onChange={(e) => setOverrideForm((p) => ({ ...p, scope: e.target.value }))} data-testid="admin-pipeline-control-override-scope-input" />
            <Input value={overrideForm.ttl_minutes} onChange={(e) => setOverrideForm((p) => ({ ...p, ttl_minutes: e.target.value }))} data-testid="admin-pipeline-control-override-ttl-input" />
            <Button disabled={!isSuperAdmin} onClick={createOverrideAction} data-testid="admin-pipeline-control-override-create-button">Create</Button>
          </div>
          <p className="mt-1 text-xs text-slate-400" data-testid="admin-pipeline-control-override-ttl-cap">max_ttl={overridesActive?.max_ttl_minutes || 120} min</p>
          <div className="mt-2 max-h-24 space-y-1 overflow-auto" data-testid="admin-pipeline-control-active-overrides-list">
            {overridesActive.map((item, idx) => (
              <div key={item.override_id} className="flex items-center justify-between gap-2 text-[11px]" data-testid={`admin-pipeline-control-active-override-${idx}`}>
                <span>{item.override_id} · {item.type} · expires={item.expires_at}</span>
                <Button size="sm" variant="outline" disabled={!isSuperAdmin} onClick={() => cancelOverrideAction(item.override_id)} data-testid={`admin-pipeline-control-cancel-override-${idx}`}>Cancel</Button>
              </div>
            ))}
          </div>
          <div className="mt-2 max-h-24 space-y-1 overflow-auto" data-testid="admin-pipeline-control-override-history-list">
            {overrideHistory.slice(0, 8).map((item, idx) => (
              <p key={`${item.override_id}-${idx}`} className="text-[11px] text-slate-400" data-testid={`admin-pipeline-control-override-history-item-${idx}`}>{item.timestamp} · {item.action_type}</p>
            ))}
          </div>
        </article>

        <article className="rounded border border-slate-700 bg-slate-900 p-3" data-testid="admin-pipeline-control-guard-panel">
          <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="admin-pipeline-control-guard-title">Guard Telemetry</p>
          <div className="mt-2 max-h-24 space-y-1 overflow-auto" data-testid="admin-pipeline-control-top-reasons-list">
            {(guardTelemetry?.top_reasons || []).slice(0, 8).map((item, idx) => (
              <p key={`${item.reason}-${idx}`} className="text-[11px] text-slate-400" data-testid={`admin-pipeline-control-top-reason-${idx}`}>{item.reason}: {item.count}</p>
            ))}
          </div>
          <div className="mt-2 max-h-28 space-y-1 overflow-auto" data-testid="admin-pipeline-control-blocked-trades-list">
            {(guardTelemetry?.blocked_trade_list || []).slice(0, 12).map((item, idx) => (
              <p key={item.id} className="text-[11px] text-slate-400" data-testid={`admin-pipeline-control-blocked-trade-${idx}`}>
                {item.symbol || "-"} · {item.intent_token} · reason={(item.reason_codes || [])[0] || item.admin_note || "-"}
              </p>
            ))}
          </div>
        </article>
      </div>

      <div className="grid gap-3 lg:grid-cols-2" data-testid="admin-pipeline-control-health-exchange-grid">
        <article className="rounded border border-green-700/60 bg-green-950/20 p-3" data-testid="admin-pipeline-control-heartbeat-panel">
          <p className="text-xs uppercase tracking-widest text-green-300" data-testid="admin-pipeline-control-heartbeat-title">Heartbeat & Service Recovery</p>
          <div className="mt-2 flex flex-wrap gap-2" data-testid="admin-pipeline-control-heartbeat-actions">
            <Button variant="outline" onClick={() => load(false)} data-testid="admin-pipeline-control-manual-health-check-button">Manual Health Check</Button>
            <Input value={serviceTarget} onChange={(e) => setServiceTarget(e.target.value)} className="w-32 bg-slate-900" data-testid="admin-pipeline-control-service-target-input" />
            <Button disabled={!isSuperAdmin} onClick={() => openAction("service_restart", { reason: `restart_${serviceTarget}` })} data-testid="admin-pipeline-control-service-restart-button">Service Restart</Button>
          </div>
          <p className="mt-2 text-xs text-slate-400" data-testid="admin-pipeline-control-heartbeat-lag-warning">lag_threshold={heartbeat?.lag_threshold_seconds || "-"} · warning={String(heartbeat?.warning_triggered || false)}</p>
        </article>

        <article className="rounded border border-indigo-700/60 bg-indigo-950/20 p-3" data-testid="admin-pipeline-control-exchange-panel">
          <p className="text-xs uppercase tracking-widest text-indigo-300" data-testid="admin-pipeline-control-exchange-title">Exchange Monitoring</p>
          <div className="mt-2 max-h-24 space-y-1 overflow-auto" data-testid="admin-pipeline-control-exchange-drift-list">
            {(exchangeMonitoring?.drift_details || []).slice(0, 10).map((item, idx) => (
              <p key={item.id} className="text-[11px] text-slate-400" data-testid={`admin-pipeline-control-exchange-drift-${idx}`}>
                user={item.user_id} · {item.exchange} · critical={String(item.is_critical)}
              </p>
            ))}
          </div>
          <div className="mt-2 max-h-24 space-y-1 overflow-auto" data-testid="admin-pipeline-control-exchange-trend-list">
            {(exchangeMonitoring?.trend || []).slice(-10).map((item, idx) => (
              <p key={`${item.bucket}-${idx}`} className="text-[11px] text-slate-400" data-testid={`admin-pipeline-control-exchange-trend-${idx}`}>{item.bucket}: {item.count}</p>
            ))}
          </div>
        </article>
      </div>

      <div className="grid gap-3 lg:grid-cols-2" data-testid="admin-pipeline-control-alerts-policy-grid">
        <article className="rounded border border-rose-700/60 bg-rose-950/20 p-3" data-testid="admin-pipeline-control-alert-history-panel">
          <div className="flex items-center justify-between" data-testid="admin-pipeline-control-alert-history-header">
            <p className="text-xs uppercase tracking-widest text-rose-300" data-testid="admin-pipeline-control-alert-history-title">Alert History / Active Alerts</p>
            <Input value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)} className="w-28 bg-slate-900" data-testid="admin-pipeline-control-alert-severity-filter-input" />
          </div>
          <div className="mt-2 flex flex-wrap gap-2" data-testid="admin-pipeline-control-alert-bulk-actions">
            <Button size="sm" variant="outline" onClick={() => runBulkAlertAction("ack")} data-testid="admin-pipeline-control-alert-bulk-ack-button">Bulk Ack</Button>
            <Button size="sm" variant="outline" onClick={() => runBulkAlertAction("mute")} data-testid="admin-pipeline-control-alert-bulk-mute-button">Bulk Mute</Button>
            <Button size="sm" variant="outline" onClick={() => runBulkAlertAction("resolve")} data-testid="admin-pipeline-control-alert-bulk-resolve-button">Bulk Resolve</Button>
          </div>
          <div className="mt-2 max-h-40 space-y-1 overflow-auto" data-testid="admin-pipeline-control-alert-list">
            {alertsHistory.slice(0, 20).map((item, idx) => (
              <div key={item.id} className="flex items-center justify-between gap-2 text-[11px]" data-testid={`admin-pipeline-control-alert-item-${idx}`}>
                <label className="flex items-center gap-1" data-testid={`admin-pipeline-control-alert-select-wrap-${idx}`}>
                  <input
                    type="checkbox"
                    checked={bulkSelection.includes(item.id)}
                    onChange={(e) => setBulkSelection((prev) => (e.target.checked ? [...prev, item.id] : prev.filter((id) => id !== item.id)))}
                    data-testid={`admin-pipeline-control-alert-select-${idx}`}
                  />
                  <span>{item.alert_type} · {item.severity} · {item.status}</span>
                </label>
                <div className="flex gap-1" data-testid={`admin-pipeline-control-alert-actions-${idx}`}>
                  <Button size="sm" variant="outline" onClick={() => runAlertAction(item.id, "ack")} data-testid={`admin-pipeline-control-alert-ack-${idx}`}>Ack</Button>
                  <Button size="sm" variant="outline" onClick={() => runAlertAction(item.id, "mute", 30)} data-testid={`admin-pipeline-control-alert-mute-${idx}`}>Mute</Button>
                  <Button size="sm" variant="outline" onClick={() => runAlertAction(item.id, "resolve")} data-testid={`admin-pipeline-control-alert-resolve-${idx}`}>Resolve</Button>
                </div>
              </div>
            ))}
          </div>
        </article>

        <article className="rounded border border-purple-700/60 bg-purple-950/20 p-3" data-testid="admin-pipeline-control-alert-policy-panel">
          <p className="text-xs uppercase tracking-widest text-purple-300" data-testid="admin-pipeline-control-alert-policy-title">Alert Policy</p>
          <div className="mt-2 grid gap-2 md:grid-cols-2" data-testid="admin-pipeline-control-alert-policy-form-grid">
            <Input value={alertPolicyForm.execution_quality_warning_threshold} onChange={(e) => setAlertPolicyForm((p) => ({ ...p, execution_quality_warning_threshold: e.target.value }))} data-testid="admin-pipeline-control-alert-policy-warning-threshold-input" />
            <Input value={alertPolicyForm.execution_quality_critical_threshold} onChange={(e) => setAlertPolicyForm((p) => ({ ...p, execution_quality_critical_threshold: e.target.value }))} data-testid="admin-pipeline-control-alert-policy-critical-threshold-input" />
            <Input value={alertPolicyForm.permission_drift_warning_per_day} onChange={(e) => setAlertPolicyForm((p) => ({ ...p, permission_drift_warning_per_day: e.target.value }))} data-testid="admin-pipeline-control-alert-policy-drift-warning-input" />
            <Input value={alertPolicyForm.permission_drift_critical_per_day} onChange={(e) => setAlertPolicyForm((p) => ({ ...p, permission_drift_critical_per_day: e.target.value }))} data-testid="admin-pipeline-control-alert-policy-drift-critical-input" />
          </div>
          <div className="mt-2 flex flex-wrap gap-2" data-testid="admin-pipeline-control-alert-policy-actions">
            <Button disabled={!isSuperAdmin} onClick={updatePolicy} data-testid="admin-pipeline-control-alert-policy-update-button">Update Policy</Button>
            <Button variant="outline" disabled={!isSuperAdmin} onClick={rollbackPolicy} data-testid="admin-pipeline-control-alert-policy-rollback-button">Rollback</Button>
            <Button variant="outline" disabled={!isSuperAdmin} onClick={() => openAction("test_alert", { reason: "manual_test_alert" })} data-testid="admin-pipeline-control-alert-policy-test-alert-button">Test Alert</Button>
          </div>
          <p className="mt-2 text-[11px] text-slate-400" data-testid="admin-pipeline-control-alert-policy-version-count">versions={(alertPolicy?.versions || []).length}</p>
        </article>
      </div>

      <article className="rounded border border-slate-700 bg-slate-900 p-3" data-testid="admin-pipeline-control-audit-analytics-panel">
        <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="admin-pipeline-control-audit-analytics-title">Hardening / Override Analytics + Global Action Audit</p>
        <div className="mt-2 max-h-40 space-y-1 overflow-auto" data-testid="admin-pipeline-control-audit-analytics-list">
          {filteredHardening.map((item, idx) => (
            <p key={item.id} className="text-[11px] text-slate-400" data-testid={`admin-pipeline-control-audit-analytics-item-${idx}`}>
              {item.created_at} · {item.action} · role={item.actor_role}
            </p>
          ))}
        </div>
        <div className="mt-2 max-h-32 space-y-1 overflow-auto" data-testid="admin-pipeline-control-action-audit-list">
          {actionAudit.slice(0, 10).map((item, idx) => (
            <p key={item.id} className="text-[11px] text-slate-500" data-testid={`admin-pipeline-control-action-audit-item-${idx}`}>
              {item.created_at} · {item.action} · {item.actor_user_id}
            </p>
          ))}
        </div>
      </article>

      <Dialog open={actionDialog.open} onOpenChange={(open) => setActionDialog((prev) => ({ ...prev, open }))}>
        <DialogContent className="max-w-xl border border-amber-700 bg-slate-950" data-testid="admin-pipeline-control-action-confirm-modal">
          <DialogHeader>
            <DialogTitle data-testid="admin-pipeline-control-action-confirm-title">Runtime Action Confirm</DialogTitle>
            <DialogDescription data-testid="admin-pipeline-control-action-confirm-description">
              Emin misin? reason + confirm phrase zorunlu.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2" data-testid="admin-pipeline-control-action-confirm-form">
            <Textarea value={actionDialog.reason} onChange={(e) => setActionDialog((p) => ({ ...p, reason: e.target.value }))} data-testid="admin-pipeline-control-action-confirm-reason-input" />
            <p className="text-xs text-slate-400" data-testid="admin-pipeline-control-action-confirm-expected-phrase">
              expected_phrase={ACTION_MAP[actionDialog.actionKey]?.phrase || "-"}
            </p>
            <Input value={actionDialog.phrase} onChange={(e) => setActionDialog((p) => ({ ...p, phrase: e.target.value }))} data-testid="admin-pipeline-control-action-confirm-phrase-input" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setActionDialog((prev) => ({ ...prev, open: false }))} data-testid="admin-pipeline-control-action-confirm-cancel-button">Vazgeç</Button>
            <Button onClick={executeAction} data-testid="admin-pipeline-control-action-confirm-submit-button">Onayla</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <p className="text-xs text-slate-500" data-testid="admin-pipeline-control-loading-state">loading={String(loading)}</p>
    </section>
  );
};
