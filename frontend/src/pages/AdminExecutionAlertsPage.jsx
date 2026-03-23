import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

const alertStatusOptions = ["all", "open", "ack", "resolved"];
const deliveryStatusOptions = ["all", "PENDING", "SENT", "FAILED", "RETRY_SCHEDULED", "DEAD", "SENT_MOCKED", "CHANNEL_DISABLED"];

export const AdminExecutionAlertsPage = () => {
  const [loading, setLoading] = useState(false);
  const [resendLoadingId, setResendLoadingId] = useState("");
  const [testLoading, setTestLoading] = useState(false);
  const [retryDueLoading, setRetryDueLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState("all");
  const [deliveryFilter, setDeliveryFilter] = useState("all");
  const [includeTest, setIncludeTest] = useState(false);
  const [resendReason, setResendReason] = useState("manual_resend");

  const [summary, setSummary] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [attempts, setAttempts] = useState([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [summaryRes, alertsRes, attemptsRes] = await Promise.all([
        apiClient.get("/admin-phase3/execution-alerts/delivery-summary"),
        apiClient.get("/admin-phase3/execution-alerts", {
          params: {
            status_filter: statusFilter,
            delivery_filter: deliveryFilter,
            include_test: includeTest,
            limit: 50,
          },
        }),
        apiClient.get("/admin-phase3/execution-alerts/delivery-attempts", {
          params: {
            status_filter: deliveryFilter,
            is_test: includeTest ? null : false,
            limit: 50,
          },
        }),
      ]);
      setSummary(summaryRes.data || null);
      setAlerts(alertsRes.data || []);
      setAttempts(attemptsRes.data?.items || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Execution alerts verisi yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, [deliveryFilter, includeTest, statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const resendAlert = async (alertId) => {
    if (resendReason.trim().length < 3) {
      toast.error("Resend reason en az 3 karakter olmalı");
      return;
    }
    setResendLoadingId(alertId);
    try {
      await apiClient.post(`/admin-phase3/execution-alerts/${encodeURIComponent(alertId)}/resend`, {
        reason: resendReason.trim(),
      });
      toast.success("Resend tetiklendi");
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Resend başarısız");
    } finally {
      setResendLoadingId("");
    }
  };

  const sendTestAlert = async () => {
    setTestLoading(true);
    try {
      await apiClient.post("/admin-phase3/execution-alerts/test-delivery", {
        severity: "INFO",
        event_type: "execution_test_alert",
        symbol: "BTCUSDT",
        state: "failed",
        failure_reason: "manual_test_alert",
      });
      toast.success("Test alert gönderildi (is_test=true)");
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Test alert başarısız");
    } finally {
      setTestLoading(false);
    }
  };

  const runDueRetries = async () => {
    setRetryDueLoading(true);
    try {
      const { data } = await apiClient.post("/admin-phase3/execution-alerts/delivery/retry-due", null, {
        params: { limit: 20 },
      });
      toast.success(`Due retry batch işlendi: ${data?.processed_count ?? 0}`);
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Due retry batch başarısız");
    } finally {
      setRetryDueLoading(false);
    }
  };

  return (
    <section className="space-y-4" data-testid="execution-alerts-page">
      <header className="border border-black/30 bg-orange-200 p-4" data-testid="execution-alerts-header">
        <h1 className="text-4xl font-black uppercase" data-testid="execution-alerts-title">Execution Alerts Delivery Ops</h1>
        <p className="text-sm" data-testid="execution-alerts-subtitle">Real webhook delivery + retry/backoff + resend + test alert</p>
      </header>

      <div className="grid gap-2 border border-black/20 bg-white p-3 md:grid-cols-6" data-testid="execution-alerts-filters-grid">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="border border-black/30 px-2 py-2 text-sm" data-testid="execution-alerts-status-filter">
          {alertStatusOptions.map((opt) => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>

        <select value={deliveryFilter} onChange={(e) => setDeliveryFilter(e.target.value)} className="border border-black/30 px-2 py-2 text-sm" data-testid="execution-alerts-delivery-filter">
          {deliveryStatusOptions.map((opt) => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>

        <label className="flex items-center gap-2 text-sm" data-testid="execution-alerts-include-test-toggle-row">
          <input type="checkbox" checked={includeTest} onChange={(e) => setIncludeTest(e.target.checked)} data-testid="execution-alerts-include-test-toggle" />
          include test alerts
        </label>

        <Input value={resendReason} onChange={(e) => setResendReason(e.target.value)} placeholder="resend reason" data-testid="execution-alerts-resend-reason-input" />

        <Button onClick={load} className="border border-black bg-black text-orange-300" data-testid="execution-alerts-refresh-button">Yenile</Button>
        <div className="flex items-center gap-2" data-testid="execution-alerts-actions-row">
          <Button variant="outline" onClick={sendTestAlert} disabled={testLoading} data-testid="execution-alerts-send-test-button">Send Test Alert</Button>
          <Button variant="outline" onClick={runDueRetries} disabled={retryDueLoading} data-testid="execution-alerts-run-due-retries-button">Run Due Retries</Button>
        </div>
      </div>

      <div className="border border-black/20 bg-orange-50 p-3" data-testid="execution-alerts-summary-panel">
        <p className="font-semibold" data-testid="execution-alerts-provider-title">Provider Health</p>
        <p data-testid="execution-alerts-provider-line">
          enabled={String(summary?.provider?.enabled)} provider={summary?.provider?.provider || "-"} destination={summary?.provider?.destination_masked || "-"}
        </p>
        <p data-testid="execution-alerts-provider-retry-line">
          timeout={summary?.provider?.timeout_seconds || "-"}s base_backoff={summary?.provider?.base_backoff_seconds || "-"}s max_retry={summary?.provider?.max_retry || "-"}
        </p>
        <p className="text-xs" data-testid="execution-alerts-provider-health-line">
          last_success={summary?.provider_health?.last_success?.request_timestamp || "-"} · last_failure={summary?.provider_health?.last_failure?.request_timestamp || "-"}
        </p>
        <p className="mt-2 text-xs" data-testid="execution-alerts-status-counts">
          status_counts: {JSON.stringify(summary?.status_counts || {})}
        </p>
      </div>

      <div className="border border-black/20 bg-white p-3" data-testid="execution-alerts-list-panel">
        <h2 className="text-base font-semibold" data-testid="execution-alerts-list-title">Execution Alerts</h2>
        <div className="mt-2 space-y-2" data-testid="execution-alerts-list-items">
          {alerts.map((alert, idx) => {
            const deliveryStatus = String(alert?.delivery_status?.status || "PENDING").toUpperCase();
            const canResend = ["FAILED", "DEAD", "RETRY_SCHEDULED", "SENT_MOCKED", "CHANNEL_DISABLED"].includes(deliveryStatus);
            return (
              <article key={alert.id} className="rounded border border-black/20 bg-zinc-50 p-2" data-testid={`execution-alerts-item-${idx}`}>
                <p data-testid={`execution-alerts-item-meta-${idx}`}>{alert.alert_type} | {alert.severity} | {alert.status}</p>
                <p className="text-xs" data-testid={`execution-alerts-item-delivery-${idx}`}>
                  delivery={deliveryStatus} provider={alert.delivery_provider || "-"} attempts={alert.attempt_count ?? 0}
                </p>
                <p className="text-xs" data-testid={`execution-alerts-item-error-${idx}`}>
                  last_error={alert.last_error_code || "-"} {alert.last_error_message || ""}
                </p>
                <div className="mt-1 flex gap-2" data-testid={`execution-alerts-item-actions-${idx}`}>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!canResend || resendLoadingId === alert.id}
                    onClick={() => resendAlert(alert.id)}
                    data-testid={`execution-alerts-item-resend-button-${idx}`}
                  >
                    Resend
                  </Button>
                </div>
              </article>
            );
          })}
          {!loading && alerts.length === 0 && <p data-testid="execution-alerts-empty">Alert yok</p>}
        </div>
      </div>

      <div className="border border-black/20 bg-white p-3" data-testid="execution-alerts-attempts-panel">
        <h2 className="text-base font-semibold" data-testid="execution-alerts-attempts-title">Recent Delivery Attempts</h2>
        <div className="mt-2 space-y-1" data-testid="execution-alerts-attempts-list">
          {attempts.map((row, idx) => (
            <div key={row.id} className="rounded border border-black/15 bg-zinc-50 p-2 text-xs" data-testid={`execution-alerts-attempt-item-${idx}`}>
              <p data-testid={`execution-alerts-attempt-main-${idx}`}>
                alert={row.alert_id} | status={row.status} | attempt={row.attempt_no} | provider={row.provider}
              </p>
              <p data-testid={`execution-alerts-attempt-destination-${idx}`}>destination={row.destination_masked}</p>
              <p data-testid={`execution-alerts-attempt-response-${idx}`}>response_code={row.response_code ?? "-"} error={row.error_code || "-"}</p>
            </div>
          ))}
          {!loading && attempts.length === 0 && <p data-testid="execution-alerts-attempts-empty">Attempt kaydı yok</p>}
        </div>
      </div>

      <p className="text-sm" data-testid="execution-alerts-loading">loading: {String(loading)}</p>
    </section>
  );
};
