import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { MetricCard } from "@/components/MetricCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

const defaultOverrideForm = {
  reason_code: "false_positive",
  reason_note: "",
  ttl_minutes: 30,
};

export const MonitoringPage = () => {
  const [metrics, setMetrics] = useState(null);
  const [driftDays, setDriftDays] = useState(7);
  const [drift, setDrift] = useState(null);
  const [releaseGate, setReleaseGate] = useState(null);
  const [overrideHistory, setOverrideHistory] = useState([]);
  const [overrideAnalytics, setOverrideAnalytics] = useState(null);
  const [alertHistory, setAlertHistory] = useState([]);
  const [hardeningTrend, setHardeningTrend] = useState(null);
  const [activeAlerts, setActiveAlerts] = useState([]);
  const [alertPolicy, setAlertPolicy] = useState({});
  const [overrideForm, setOverrideForm] = useState(defaultOverrideForm);
  const [isOverrideSubmitting, setIsOverrideSubmitting] = useState(false);
  const [isPageVisible, setIsPageVisible] = useState(true);
  const [nowMs, setNowMs] = useState(Date.now());
  const [isLoading, setIsLoading] = useState(true);

  const fetchMonitoring = useCallback(async () => {
    try {
      const [
        { data: monitoringData },
        { data: driftData },
        { data: releaseGateData },
        { data: historyData },
        { data: analyticsData },
        { data: alertsData },
        { data: hardeningData },
        { data: activeAlertsData },
        { data: alertPolicyData },
      ] = await Promise.all([
        apiClient.get("/pipeline/monitoring"),
        apiClient.get(`/phase4/admin/permission-drift-trend?days=${driftDays}`),
        apiClient.get("/phase4/admin/release-gate"),
        apiClient.get("/phase4/admin/release-gate/overrides?limit=20"),
        apiClient.get(`/phase4/admin/override-analytics?days=${driftDays}`),
        apiClient.get("/phase4/admin/alert-history?limit=30"),
        apiClient.get("/admin-phase3/hardening-checklist/trend"),
        apiClient.get("/phase4/admin/active-alerts"),
        apiClient.get("/phase4/admin/alert-policy"),
      ]);
      setMetrics(monitoringData);
      setDrift(driftData);
      setReleaseGate(releaseGateData);
      setOverrideHistory(historyData);
      setOverrideAnalytics(analyticsData);
      setAlertHistory(alertsData);
      setHardeningTrend(hardeningData);
      setActiveAlerts(activeAlertsData);
      setAlertPolicy(alertPolicyData);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Monitoring verisi alınamadı");
    } finally {
      setIsLoading(false);
    }
  }, [driftDays]);

  useEffect(() => {
    const onVisibility = () => setIsPageVisible(document.visibilityState === "visible");
    document.addEventListener("visibilitychange", onVisibility);
    onVisibility();
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  useEffect(() => {
    fetchMonitoring();
  }, [fetchMonitoring]);

  useEffect(() => {
    const refreshMs = releaseGate?.override_active && isPageVisible ? 15000 : 30000;
    const timer = setInterval(fetchMonitoring, refreshMs);
    return () => clearInterval(timer);
  }, [fetchMonitoring, releaseGate?.override_active, isPageVisible]);

  useEffect(() => {
    const timer = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const points = drift?.points || [];
  const maxCount = Math.max(...points.map((point) => point.event_count), 1);
  const linePoints = points
    .map((point, index) => {
      const x = (index / Math.max(points.length - 1, 1)) * 100;
      const y = 100 - (point.event_count / maxCount) * 100;
      return `${x},${y}`;
    })
    .join(" ");

  const analyticsPoints = overrideAnalytics?.points || [];
  const overrideExpiryMs = releaseGate?.override_expires_at ? new Date(releaseGate.override_expires_at).getTime() : null;
  const remainingMs = overrideExpiryMs ? Math.max(0, overrideExpiryMs - nowMs) : 0;
  const remainingMinutes = Math.floor(remainingMs / 60000);
  const remainingSeconds = Math.floor((remainingMs % 60000) / 1000);
  const overrideExpired = Boolean(releaseGate?.override_active) && remainingMs <= 0;
  const overrideWarning = Boolean(releaseGate?.override_active) && remainingMs > 0 && remainingMs <= 5 * 60 * 1000;
  const progressPct = overrideExpiryMs && releaseGate?.override_active
    ? Math.max(0, Math.min(100, (remainingMs / (30 * 60 * 1000)) * 100))
    : 0;

  const submitOverride = async () => {
    if (!overrideForm.reason_note || overrideForm.reason_note.trim().length < 12) {
      toast.error("reason_note en az 12 karakter olmalı");
      return;
    }

    setIsOverrideSubmitting(true);
    try {
      await apiClient.post("/phase4/admin/release-gate/override", {
        reason_code: overrideForm.reason_code,
        reason_note: overrideForm.reason_note,
        ttl_minutes: Number(overrideForm.ttl_minutes) || 30,
        deploy_context: { source: "admin_monitoring_ui" },
      });
      toast.success("Manual override aktif edildi");
      setOverrideForm(defaultOverrideForm);
      await fetchMonitoring();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Override oluşturulamadı");
    } finally {
      setIsOverrideSubmitting(false);
    }
  };

  const revokeOverride = async (overrideId) => {
    try {
      await apiClient.post(`/phase4/admin/release-gate/override/${overrideId}/revoke`);
      toast.success("Override revoke edildi");
      await fetchMonitoring();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Override revoke başarısız");
    }
  };

  const saveAlertPolicy = async () => {
    try {
      await apiClient.put("/phase4/admin/alert-policy", alertPolicy);
      toast.success("Alert policy güncellendi");
      await fetchMonitoring();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Alert policy kaydedilemedi");
    }
  };

  return (
    <section className="space-y-4" data-testid="monitoring-page">
      <header className="border border-blue-900 bg-slate-900 p-4" data-testid="monitoring-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-blue-300" data-testid="monitoring-title">Pipeline Monitoring</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="monitoring-description">Websocket, signal rate, paper trade ve latency durumu.</p>
      </header>

      <div className="flex flex-wrap items-center gap-3 border border-slate-800 bg-slate-900 p-3" data-testid="monitoring-operability-bar">
        <span className="text-xs text-slate-300" data-testid="monitoring-operability-refresh-mode">
          auto-refresh: {releaseGate?.override_active ? "15s" : "30s"}
        </span>
        <span className="text-xs text-slate-300" data-testid="monitoring-operability-page-visibility">
          page_visible: {String(isPageVisible)}
        </span>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-10" data-testid="monitoring-metrics-grid">
        <MetricCard label="WS Status" value={isLoading ? "loading" : (metrics?.websocket_status || "-")} tone="blue" testId="monitoring-ws-status" />
        <MetricCard label="Signal / 5m" value={isLoading ? "loading" : (metrics?.signal_rate_last_5m ?? "-")} testId="monitoring-signal-rate" />
        <MetricCard label="Paper Trade / 5m" value={isLoading ? "loading" : (metrics?.paper_trades_last_5m ?? "-")} tone="orange" testId="monitoring-paper-trades" />
        <MetricCard label="Open Positions" value={isLoading ? "loading" : (metrics?.open_positions ?? "-")} testId="monitoring-open-positions" />
        <MetricCard label="Latency ms" value={isLoading ? "loading" : (metrics?.latency_ms ?? "-")} tone="blue" testId="monitoring-latency" />
        <MetricCard label="Transitions / 5m" value={isLoading ? "loading" : (metrics?.execution_transitions_5m ?? "-")} tone="orange" testId="monitoring-transitions" />
        <MetricCard label="Release Gate" value={isLoading ? "loading" : (metrics?.release_gate_status ?? "-")} tone={metrics?.release_gate_status === "READY" ? "blue" : metrics?.release_gate_status === "WARNING" ? "orange" : "red"} testId="monitoring-release-gate" />
        <MetricCard label="Gate Checked" value={isLoading ? "loading" : (metrics?.release_gate_last_checked ?? "-")} tone="blue" testId="monitoring-release-gate-checked" />
        <MetricCard label="Kill Switch" value={isLoading ? "loading" : String(metrics?.global_trading_pause ?? false)} tone={metrics?.global_trading_pause ? "red" : "blue"} testId="monitoring-kill-switch" />
        <MetricCard label="Exec Errors/5m" value={isLoading ? "loading" : (metrics?.execution_errors_5m ?? "-")} tone="red" testId="monitoring-execution-errors-5m" />
      </div>

      <div className="border border-orange-700 bg-orange-200 p-4" data-testid="monitoring-release-gate-override-status-panel">
        <p className="text-xs uppercase tracking-widest text-black" data-testid="monitoring-release-gate-override-status-title">Release Gate Override Status</p>
        <p className="mt-2 text-sm text-black" data-testid="monitoring-release-gate-override-status-line">
          status={releaseGate?.status || "-"} | override_active={String(releaseGate?.override_active || false)} | override_expires_at={releaseGate?.override_expires_at || "-"}
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-3" data-testid="monitoring-release-gate-override-countdown-row">
          <span className={`rounded border px-2 py-1 text-xs ${overrideExpired ? "border-red-700 bg-red-700 text-white" : overrideWarning ? "border-yellow-600 bg-yellow-200 text-black" : "border-green-700 bg-green-200 text-black"}`} data-testid="monitoring-release-gate-override-countdown-badge">
            {releaseGate?.override_active ? (overrideExpired ? "expired" : `${remainingMinutes}m ${remainingSeconds}s`) : "no-active-override"}
          </span>
          <span className="text-xs text-black" data-testid="monitoring-release-gate-override-countdown-note">
            {overrideWarning ? "son 5 dk warning" : ""}
          </span>
        </div>
        <div className="mt-2 h-2 w-full overflow-hidden rounded bg-black/20" data-testid="monitoring-release-gate-override-progress-wrapper">
          <div className={`h-full ${overrideWarning ? "bg-yellow-500" : "bg-green-600"}`} style={{ width: `${progressPct}%` }} data-testid="monitoring-release-gate-override-progress-bar" />
        </div>
        <div className="mt-3 grid gap-2 md:grid-cols-4" data-testid="monitoring-release-gate-override-form-grid">
          <select
            value={overrideForm.reason_code}
            onChange={(event) => setOverrideForm((prev) => ({ ...prev, reason_code: event.target.value }))}
            className="border border-black bg-orange-100 px-3 py-2 text-sm text-black"
            data-testid="monitoring-release-gate-override-reason-code-select"
          >
            <option value="false_positive">false_positive</option>
            <option value="exchange_incident">exchange_incident</option>
            <option value="ops_emergency">ops_emergency</option>
            <option value="manual_review">manual_review</option>
          </select>
          <Input
            value={overrideForm.reason_note}
            onChange={(event) => setOverrideForm((prev) => ({ ...prev, reason_note: event.target.value }))}
            placeholder="reason_note (min 12)"
            className="border-black bg-orange-100 text-black"
            data-testid="monitoring-release-gate-override-reason-note-input"
          />
          <Input
            type="number"
            min={1}
            max={60}
            value={overrideForm.ttl_minutes}
            onChange={(event) => setOverrideForm((prev) => ({ ...prev, ttl_minutes: event.target.value }))}
            className="border-black bg-orange-100 text-black"
            data-testid="monitoring-release-gate-override-ttl-input"
          />
          <Button className="bg-black text-orange-400 hover:bg-zinc-900" onClick={submitOverride} data-testid="monitoring-release-gate-override-submit-button" disabled={isOverrideSubmitting}>
            {isOverrideSubmitting ? "Gönderiliyor..." : "Override Aç"}
          </Button>
        </div>
      </div>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="monitoring-details-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="monitoring-heartbeat-label">Heartbeat</p>
        <p className="mt-2 font-mono text-sm" data-testid="monitoring-heartbeat-value">{metrics?.heartbeat || "-"}</p>
        <p className="mt-2 font-mono text-xs text-slate-400" data-testid="monitoring-queue-depth">Queue Depth: {metrics?.queue_depth ?? "-"}</p>
        <p className="mt-1 font-mono text-xs text-slate-400" data-testid="monitoring-running-bots">Running Bots: {metrics?.active_bots_running ?? "-"}</p>
        <p className="mt-1 font-mono text-xs text-slate-400" data-testid="monitoring-reconnects">WS Reconnect /5m: {metrics?.websocket_reconnects_5m ?? "-"}</p>
        <p className="mt-1 font-mono text-xs text-slate-400" data-testid="monitoring-idempotency">Idempotency Keys /5m: {metrics?.idempotency_keys_5m ?? "-"}</p>
        <p className="mt-1 font-mono text-xs text-slate-400" data-testid="monitoring-duplicates">Duplicate Blocked /5m: {metrics?.duplicate_signals_blocked_5m ?? "-"}</p>
        <p className="mt-1 font-mono text-xs text-slate-400" data-testid="monitoring-correlation-rejections">Correlation Rejections /5m: {metrics?.correlation_rejections_5m ?? "-"}</p>
        <p className="mt-1 font-mono text-xs text-slate-400" data-testid="monitoring-failed-pending">Failed Events Pending: {metrics?.failed_events_pending ?? "-"}</p>
        <p className="mt-1 font-mono text-xs text-slate-400" data-testid="monitoring-failed-dead">Failed Events Dead: {metrics?.failed_events_dead ?? "-"}</p>
        <p className="mt-1 font-mono text-xs text-slate-400" data-testid="monitoring-kill-switch-reasons">Kill Switch Reasons: {(metrics?.kill_switch_reasons || []).join(",") || "-"}</p>
      </div>

      <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="monitoring-permission-drift-panel">
        <div className="flex flex-wrap items-center justify-between gap-3" data-testid="monitoring-permission-drift-header">
          <div>
            <p className="text-xs uppercase tracking-widest text-blue-300" data-testid="monitoring-permission-drift-kicker">Exchange Monitoring</p>
            <h3 className="text-lg font-semibold text-slate-100" data-testid="monitoring-permission-drift-title">Permission Drift Trend</h3>
          </div>
          <div className="flex gap-2" data-testid="monitoring-permission-drift-toggle-group">
            <button
              className={`border px-3 py-1 text-xs ${driftDays === 7 ? "border-blue-400 bg-blue-700 text-white" : "border-slate-700 text-slate-300"}`}
              onClick={() => setDriftDays(7)}
              data-testid="monitoring-permission-drift-7d-button"
            >
              7 Gün
            </button>
            <button
              className={`border px-3 py-1 text-xs ${driftDays === 30 ? "border-blue-400 bg-blue-700 text-white" : "border-slate-700 text-slate-300"}`}
              onClick={() => setDriftDays(30)}
              data-testid="monitoring-permission-drift-30d-button"
            >
              30 Gün
            </button>
          </div>
        </div>

        <div className="grid gap-2 sm:grid-cols-3" data-testid="monitoring-permission-drift-summary-grid">
          <MetricCard label="Affected Users" value={drift?.affected_user_count ?? "-"} tone="blue" testId="monitoring-permission-drift-affected-users" />
          <MetricCard label="Critical Drift" value={drift?.critical_drift_count ?? "-"} tone="red" testId="monitoring-permission-drift-critical-count" />
          <MetricCard label="Latest Event" value={drift?.latest_timestamp || "-"} tone="orange" testId="monitoring-permission-drift-latest-timestamp" />
        </div>

        <div className="border border-slate-800 bg-slate-950 p-3" data-testid="monitoring-permission-drift-chart-wrapper">
          <svg viewBox="0 0 100 100" className="h-40 w-full" data-testid="monitoring-permission-drift-line-chart">
            <polyline fill="none" stroke="#60a5fa" strokeWidth="2" points={linePoints || "0,100 100,100"} />
          </svg>
          <div className="mt-2 flex flex-wrap gap-2" data-testid="monitoring-permission-drift-chart-labels">
            {points.slice(-6).map((point) => (
              <span key={point.date} className="rounded border border-slate-700 px-2 py-1 font-mono text-xs text-slate-400" data-testid={`monitoring-permission-drift-point-${point.date}`}>
                {point.date}: {point.event_count}
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="monitoring-hardening-trend-panel">
        <p className="text-xs uppercase tracking-widest text-blue-300" data-testid="monitoring-hardening-trend-title">Hardening Checklist Trend</p>
        <div className="grid gap-3 sm:grid-cols-3" data-testid="monitoring-hardening-trend-summary-grid">
          <MetricCard label="Avg Score(5)" value={hardeningTrend?.average_score_last_5 ?? "-"} tone="blue" testId="monitoring-hardening-avg-score" />
          <MetricCard label="Trend Alarm" value={String(hardeningTrend?.trend_alarm ?? false)} tone={hardeningTrend?.trend_alarm ? "red" : "orange"} testId="monitoring-hardening-trend-alarm" />
          <MetricCard label="Critical Alarm" value={String(hardeningTrend?.critical_alarm ?? false)} tone={hardeningTrend?.critical_alarm ? "red" : "orange"} testId="monitoring-hardening-critical-alarm" />
        </div>
      </div>

      <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="monitoring-override-analytics-panel">
        <p className="text-xs uppercase tracking-widest text-blue-300" data-testid="monitoring-override-analytics-title">Override Analytics</p>
        <div className="grid gap-2 sm:grid-cols-3" data-testid="monitoring-override-analytics-cards-grid">
          <MetricCard label="Blocked Gate / Period" value={analyticsPoints.reduce((sum, item) => sum + item.blocked_gate_count, 0)} tone="red" testId="monitoring-override-analytics-blocked-total" />
          <MetricCard label="Override Count" value={analyticsPoints.reduce((sum, item) => sum + item.override_count, 0)} tone="orange" testId="monitoring-override-analytics-override-total" />
          <MetricCard label="Override Deploy Uses" value={analyticsPoints.reduce((sum, item) => sum + item.override_deploy_count, 0)} tone="blue" testId="monitoring-override-analytics-deploy-total" />
        </div>
        <div className="grid gap-2 sm:grid-cols-2" data-testid="monitoring-alert-source-breakdown-grid">
          {Object.entries(overrideAnalytics?.alert_source_breakdown || {}).slice(0, 8).map(([source, count]) => (
            <div key={source} className="border border-slate-700 p-2 text-xs" data-testid={`monitoring-alert-source-${source}`}>
              {source}: {count}
            </div>
          ))}
        </div>
      </div>

      <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="monitoring-override-history-panel">
        <p className="text-xs uppercase tracking-widest text-blue-300" data-testid="monitoring-override-history-title">Override History</p>
        <div className="space-y-2" data-testid="monitoring-override-history-list">
          {overrideHistory.map((row) => (
            <div key={row.override_id} className="grid gap-2 border border-slate-700 p-3 md:grid-cols-5" data-testid={`monitoring-override-history-row-${row.override_id}`}>
              <p className="text-xs" data-testid={`monitoring-override-history-reason-${row.override_id}`}>{row.reason_code}</p>
              <p className="text-xs" data-testid={`monitoring-override-history-note-${row.override_id}`}>{row.reason_note}</p>
              <p className="text-xs" data-testid={`monitoring-override-history-expiry-${row.override_id}`}>{row.expires_at}</p>
              <p className="text-xs" data-testid={`monitoring-override-history-uses-${row.override_id}`}>deploy_use={row.used_deploy_count}</p>
              <Button
                className="h-8 border border-red-500 bg-red-700 text-white hover:bg-red-800"
                onClick={() => revokeOverride(row.override_id)}
                data-testid={`monitoring-override-history-revoke-button-${row.override_id}`}
                disabled={Boolean(row.revoked_at)}
              >
                {row.revoked_at ? "Revoked" : "Revoke"}
              </Button>
            </div>
          ))}
        </div>
      </div>

      <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="monitoring-alert-history-panel">
        <p className="text-xs uppercase tracking-widest text-blue-300" data-testid="monitoring-alert-history-title">Alert History</p>
        <div className="space-y-2" data-testid="monitoring-alert-history-list">
          {alertHistory.slice(0, 20).map((row, index) => (
            <div key={`${row.created_at}-${index}`} className="border border-slate-700 p-2 text-xs" data-testid={`monitoring-alert-history-item-${index}`}>
              [{row.severity}] {row.action} — {row.created_at}
            </div>
          ))}
        </div>
      </div>

      <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="monitoring-active-alerts-panel">
        <p className="text-xs uppercase tracking-widest text-blue-300" data-testid="monitoring-active-alerts-title">Active Alerts</p>
        <div className="grid gap-2 sm:grid-cols-3" data-testid="monitoring-active-alerts-grid">
          {activeAlerts.map((alert) => (
            <div key={alert.code} className={`border p-2 text-xs ${alert.severity === "critical" ? "border-red-600 bg-red-950/20" : "border-yellow-600 bg-yellow-950/20"}`} data-testid={`monitoring-active-alert-${alert.code}`}>
              {alert.code} · {alert.severity} · value={alert.value}
            </div>
          ))}
          {activeAlerts.length === 0 && (
            <p className="text-xs text-slate-400" data-testid="monitoring-active-alerts-empty">Aktif alarm yok.</p>
          )}
        </div>
      </div>

      <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="monitoring-alert-policy-panel">
        <p className="text-xs uppercase tracking-widest text-blue-300" data-testid="monitoring-alert-policy-title">Alert Policy</p>
        <div className="grid gap-2 sm:grid-cols-2" data-testid="monitoring-alert-policy-grid">
          <Input type="number" value={alertPolicy?.execution_quality_warning_threshold ?? 60} onChange={(event) => setAlertPolicy((prev) => ({ ...prev, execution_quality_warning_threshold: Number(event.target.value) }))} data-testid="monitoring-alert-policy-execution-warning-input" />
          <Input type="number" value={alertPolicy?.execution_quality_critical_threshold ?? 40} onChange={(event) => setAlertPolicy((prev) => ({ ...prev, execution_quality_critical_threshold: Number(event.target.value) }))} data-testid="monitoring-alert-policy-execution-critical-input" />
          <Input type="number" value={alertPolicy?.permission_drift_warning_per_day ?? 2} onChange={(event) => setAlertPolicy((prev) => ({ ...prev, permission_drift_warning_per_day: Number(event.target.value) }))} data-testid="monitoring-alert-policy-drift-warning-input" />
          <Input type="number" value={alertPolicy?.permission_drift_critical_per_day ?? 5} onChange={(event) => setAlertPolicy((prev) => ({ ...prev, permission_drift_critical_per_day: Number(event.target.value) }))} data-testid="monitoring-alert-policy-drift-critical-input" />
          <Input type="number" value={alertPolicy?.gate_override_warning_per_day ?? 2} onChange={(event) => setAlertPolicy((prev) => ({ ...prev, gate_override_warning_per_day: Number(event.target.value) }))} data-testid="monitoring-alert-policy-override-warning-input" />
          <Input type="number" value={alertPolicy?.gate_override_critical_per_day ?? 5} onChange={(event) => setAlertPolicy((prev) => ({ ...prev, gate_override_critical_per_day: Number(event.target.value) }))} data-testid="monitoring-alert-policy-override-critical-input" />
          <Input value={alertPolicy?.ops_webhook_url ?? ""} onChange={(event) => setAlertPolicy((prev) => ({ ...prev, ops_webhook_url: event.target.value }))} className="sm:col-span-2" data-testid="monitoring-alert-policy-ops-webhook-input" placeholder="Ops webhook URL" />
        </div>
        <Button className="bg-blue-700 text-white hover:bg-blue-800" onClick={saveAlertPolicy} data-testid="monitoring-alert-policy-save-button">Alert Policy Kaydet</Button>
      </div>
    </section>
  );
};