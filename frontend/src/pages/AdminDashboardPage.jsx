import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { MetricCard } from "@/components/MetricCard";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

const criticalActions = [
  { key: "stop_all_bots", label: "STOP ALL BOTS", endpoint: "/phase4/kill-switch/stop-all-bots" },
  { key: "disable_futures", label: "Disable Futures", endpoint: "/phase4/kill-switch/disable-futures" },
  { key: "force_close", label: "Force Close All Positions", endpoint: "/phase4/kill-switch/close-all-positions" },
  { key: "risk_mode", label: "Emergency Risk Mode", endpoint: "/v1/admin/emergency_stop", payload: { reason: "dashboard_emergency_risk_mode" } },
];

export const AdminDashboardPage = () => {
  const [summary, setSummary] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [lastUpdatedAt, setLastUpdatedAt] = useState("");
  const [alertSeverityFilter, setAlertSeverityFilter] = useState("all");
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);
  const [actionCenterSummary, setActionCenterSummary] = useState(null);
  const [closeResult, setCloseResult] = useState(null);

  const filteredAlerts = useMemo(() => {
    if (alertSeverityFilter === "all") {
      return alerts;
    }
    return alerts.filter((alert) => String(alert?.severity || "").toUpperCase() === alertSeverityFilter);
  }, [alerts, alertSeverityFilter]);

  const fetchSummary = async () => {
    setIsLoading(true);
    setLoadError("");
    try {
      const [{ data }, { data: actionSummary }] = await Promise.all([
        apiClient.get("/dashboard/summary"),
        apiClient.get("/admin/action-center/summary"),
      ]);
      setSummary(data || null);
      setAlerts(data?.alerts || []);
      setActionCenterSummary(actionSummary || null);
      setLastUpdatedAt(new Date().toISOString());
    } catch (error) {
      const message = error?.response?.data?.detail || "Admin dashboard verisi yüklenemedi";
      setLoadError(message);
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchSummary();
  }, []);

  useEffect(() => {
    if (!autoRefreshEnabled) {
      return undefined;
    }
    const timer = setInterval(fetchSummary, 30000);
    return () => clearInterval(timer);
  }, [autoRefreshEnabled]);

  const runCriticalAction = async (action) => {
    const label = action.label;
    const firstCheck = window.confirm(`${label} aksiyonunu başlatmak istediğine emin misin?`);
    if (!firstCheck) return;
    const secondCheck = window.confirm("Bu işlem canlı sistemler için kritik olabilir. Tekrar onaylıyor musun?");
    if (!secondCheck) return;
    try {
      await apiClient.post(action.endpoint, action.payload || {});
      toast.success(`${label} çalıştırıldı`);
      await fetchSummary();
    } catch (error) {
      toast.error(error?.response?.data?.detail || `${label} başarısız`);
    }
  };

  const runCloseNextActions = async () => {
    const confirmed = window.confirm("Açık aksiyonları otomatik kapatmayı başlatmak istiyor musun?");
    if (!confirmed) return;
    try {
      const { data } = await apiClient.post("/admin/action-center/close-next-actions", {
        ack_open_alerts: true,
        reject_stale_approvals: true,
        stale_days: 30,
        retry_timeout_rejections: true,
        clear_kill_switch: false,
      });
      setCloseResult(data || null);
      toast.success("Auto-close tamamlandı");
      await fetchSummary();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Auto-close başarısız");
    }
  };

  const ackAlert = async (alertId) => {
    try {
      await apiClient.post(`/admin/system-alerts/${alertId}/ack`);
      setAlerts((prev) => prev.filter((item) => item.id !== alertId));
      toast.success("Alert ack edildi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Alert ack edilemedi");
    }
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
          <Button className="mt-3" onClick={fetchSummary} data-testid="admin-dashboard-broken-retry-button">Tekrar Dene</Button>
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
            <Button variant="outline" onClick={runCloseNextActions} data-testid="admin-dashboard-auto-close-next-actions-button">Auto-Close Next Actions</Button>
            <Button onClick={fetchSummary} data-testid="admin-dashboard-refresh-button">Yenile</Button>
          </div>
        </div>
      </header>

      <div className="grid gap-3 md:grid-cols-2" data-testid="admin-dashboard-action-center-grid">
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-dashboard-action-center-summary-card">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-dashboard-action-center-summary-title">Action Center Summary</p>
          <div className="mt-2 grid gap-1 text-xs" data-testid="admin-dashboard-action-center-summary-content">
            <p data-testid="admin-dashboard-action-center-open-alerts">open_alerts: {actionCenterSummary?.open_alerts ?? "-"}</p>
            <p data-testid="admin-dashboard-action-center-pending-approvals">pending_approvals: {actionCenterSummary?.pending_approvals ?? "-"}</p>
            <p data-testid="admin-dashboard-action-center-stale-approvals">stale_pending_approvals: {actionCenterSummary?.stale_pending_approvals ?? "-"}</p>
            <p data-testid="admin-dashboard-action-center-rejected-intents">rejected_intents: {actionCenterSummary?.rejected_intents ?? "-"}</p>
            <p data-testid="admin-dashboard-action-center-timeout-rejections">timeout_rejected_intents: {actionCenterSummary?.timeout_rejected_intents ?? "-"}</p>
            <p data-testid="admin-dashboard-action-center-kill-switch">kill_switch_active: {String(actionCenterSummary?.kill_switch_active ?? false)}</p>
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
            </div>
          ) : (
            <p className="mt-2 text-xs text-slate-400" data-testid="admin-dashboard-action-center-result-empty">Henüz auto-close çalıştırılmadı.</p>
          )}
        </article>
      </div>

      {loadError && (
        <div className="border border-amber-500/40 bg-amber-950/20 p-3 text-sm text-amber-200" data-testid="admin-dashboard-warning-alert">
          Son yenileme sırasında hata oluştu: {loadError}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2" data-testid="admin-alerts-filter-row">
        <label className="text-xs text-slate-400" htmlFor="admin-alerts-severity-filter" data-testid="admin-alerts-filter-label">Severity Filter</label>
        <select
          id="admin-alerts-severity-filter"
          value={alertSeverityFilter}
          onChange={(event) => setAlertSeverityFilter(event.target.value)}
          className="h-9 rounded border border-slate-700 bg-slate-950 px-2 text-sm"
          data-testid="admin-alerts-severity-filter-select"
        >
          <option value="all" data-testid="admin-alerts-severity-filter-option-all">all</option>
          <option value="CRITICAL" data-testid="admin-alerts-severity-filter-option-critical">CRITICAL</option>
          <option value="WARNING" data-testid="admin-alerts-severity-filter-option-warning">WARNING</option>
          <option value="INFO" data-testid="admin-alerts-severity-filter-option-info">INFO</option>
        </select>
      </div>

      {filteredAlerts.length > 0 && (
        <div className="border border-red-500/60 bg-red-950/20 p-4" data-testid="admin-alerts-banner">
          <p className="text-xs uppercase tracking-widest text-red-300" data-testid="admin-alerts-title">CRITICAL ALERTS</p>
          <div className="mt-3 space-y-2" data-testid="admin-alerts-list">
            {filteredAlerts.map((alert) => (
              <div key={alert.id} className="flex flex-wrap items-center justify-between gap-2 border border-red-700/40 p-2" data-testid={`admin-alert-row-${alert.id}`}>
                <div className="text-xs" data-testid={`admin-alert-meta-${alert.id}`}>
                  <span className="font-semibold" data-testid={`admin-alert-type-${alert.id}`}>{alert.alert_type}</span> ·
                  <span className="ml-1" data-testid={`admin-alert-severity-${alert.id}`}>{alert.severity}</span> ·
                  <span className="ml-1" data-testid={`admin-alert-occurrences-${alert.id}`}>x{alert.occurrences}</span>
                  <p className="text-slate-300" data-testid={`admin-alert-message-${alert.id}`}>{alert.message}</p>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  className="border-red-400 bg-transparent text-red-300"
                  onClick={() => ackAlert(alert.id)}
                  data-testid={`admin-alert-ack-${alert.id}`}
                >
                  Ack
                </Button>
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
        <MetricCard label="Kullanıcı" value={summary?.metrics?.users ?? "-"} tone="blue" testId="admin-metric-users" />
        <MetricCard label="Running Bot" value={summary?.metrics?.running_bots ?? "-"} tone="blue" testId="admin-metric-active-bots" />
        <MetricCard label="Risk Policy" value={summary?.metrics?.risk_policies ?? "-"} tone="blue" testId="admin-metric-risk-policies" />
        <MetricCard label="Template" value={summary?.metrics?.strategy_templates ?? "-"} tone="blue" testId="admin-metric-strategies" />
        <MetricCard label="WS Status" value={summary?.metrics?.websocket_status ?? "-"} tone="blue" testId="admin-metric-ws-status" />
        <MetricCard label="Signal / 5m" value={summary?.metrics?.signals_5m ?? "-"} tone="orange" testId="admin-metric-signals" />
        <MetricCard label="Paper Trade / 5m" value={summary?.metrics?.paper_trades_5m ?? "-"} tone="orange" testId="admin-metric-paper-trades" />
        <MetricCard label="Open Positions" value={summary?.metrics?.open_positions ?? "-"} tone="blue" testId="admin-metric-open-positions" />
        <MetricCard label="Critical Audit" value={summary?.metrics?.critical_audits ?? "-"} tone="red" testId="admin-metric-critical-audits" />
      </div>

      <div className="border border-red-500/50 bg-red-950/20 p-4" data-testid="admin-critical-actions-panel">
        <p className="text-xs uppercase tracking-widest text-red-300" data-testid="admin-critical-actions-title">Kritik Kontrol Alanı</p>
        <div className="mt-3 grid gap-2 md:grid-cols-2" data-testid="admin-critical-actions-grid">
          {criticalActions.map((action) => (
            <Button
              key={action.key}
              variant="outline"
              className="border-red-400 bg-transparent text-red-300 hover:bg-red-900/40 hover:text-red-100"
              onClick={() => runCriticalAction(action)}
              data-testid={`admin-critical-action-${action.key}`}
            >
              {action.label}
            </Button>
          ))}
        </div>
      </div>
    </section>
  );
};
