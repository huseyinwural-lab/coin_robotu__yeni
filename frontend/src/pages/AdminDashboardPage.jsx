import { useEffect, useState } from "react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { MetricCard } from "@/components/MetricCard";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

const criticalActions = [
  { key: "stop_all_bots", label: "STOP ALL BOTS" },
  { key: "disable_futures", label: "Disable Futures" },
  { key: "force_close", label: "Force Close All Positions" },
  { key: "risk_mode", label: "Emergency Risk Mode" },
];

export const AdminDashboardPage = () => {
  const [summary, setSummary] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [lastUpdatedAt, setLastUpdatedAt] = useState("");

  const fetchSummary = async () => {
    setIsLoading(true);
    setLoadError("");
    try {
      const { data } = await apiClient.get("/dashboard/summary");
      setSummary(data || null);
      setAlerts(data?.alerts || []);
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

  const runCriticalAction = (label) => {
    const firstCheck = window.confirm(`${label} aksiyonunu başlatmak istediğine emin misin?`);
    if (!firstCheck) return;
    const secondCheck = window.confirm("Bu işlem canlı sistemler için kritik olabilir. Tekrar onaylıyor musun?");
    if (secondCheck) {
      toast.warning(`${label} komutu kontrol yüzeyinde tetiklendi (skeleton).`);
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
          <Button onClick={fetchSummary} data-testid="admin-dashboard-refresh-button">Yenile</Button>
        </div>
      </header>

      {loadError && (
        <div className="border border-amber-500/40 bg-amber-950/20 p-3 text-sm text-amber-200" data-testid="admin-dashboard-warning-alert">
          Son yenileme sırasında hata oluştu: {loadError}
        </div>
      )}

      {alerts.length > 0 && (
        <div className="border border-red-500/60 bg-red-950/20 p-4" data-testid="admin-alerts-banner">
          <p className="text-xs uppercase tracking-widest text-red-300" data-testid="admin-alerts-title">CRITICAL ALERTS</p>
          <div className="mt-3 space-y-2" data-testid="admin-alerts-list">
            {alerts.map((alert) => (
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

      {alerts.length === 0 && (
        <div className="border border-slate-800 bg-slate-900 p-4 text-sm text-slate-400" data-testid="admin-alerts-empty-state">
          Aktif kritik alert bulunmuyor.
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
              onClick={() => runCriticalAction(action.label)}
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
