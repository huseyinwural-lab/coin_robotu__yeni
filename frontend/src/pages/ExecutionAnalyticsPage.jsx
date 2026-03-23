import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { apiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { toast } from "sonner";

const SOURCE_OPTIONS = ["all", "production", "paper", "simulation", "replay"];
const STATUS_OPTIONS = ["all", "filled", "timeout", "rejected", "failed", "cancelled", "submitted", "pending"];
const readFilter = (sp, key, fallback = "") => sp.get(key) || fallback;

export const ExecutionAnalyticsPage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [loading, setLoading] = useState(false);
  const [refreshMs, setRefreshMs] = useState(10000);
  const [summary, setSummary] = useState(null);
  const [stateLatency, setStateLatency] = useState([]);
  const [slowestStates, setSlowestStates] = useState([]);
  const [timeoutDistribution, setTimeoutDistribution] = useState([]);
  const [failureTrend, setFailureTrend] = useState([]);
  const [failureClasses, setFailureClasses] = useState([]);
  const [executionAlerts, setExecutionAlerts] = useState([]);
  const [alertStatusFilter, setAlertStatusFilter] = useState("all");
  const [autoAckPolicy, setAutoAckPolicy] = useState(null);
  const [autoAckReason, setAutoAckReason] = useState("policy_update");
  const [autoAckDryRun, setAutoAckDryRun] = useState(true);
  const [autoAckPreviewToken, setAutoAckPreviewToken] = useState("");
  const [autoAckPreviewCount, setAutoAckPreviewCount] = useState(0);
  const [autoAckRunning, setAutoAckRunning] = useState(false);

  const filters = useMemo(
    () => ({
      search: readFilter(searchParams, "search"),
      state: readFilter(searchParams, "state", "all"),
      status: readFilter(searchParams, "status", "all"),
      source_type: readFilter(searchParams, "source_type", "all"),
      symbol: readFilter(searchParams, "symbol"),
      strategy: readFilter(searchParams, "strategy"),
      correlation_id: readFilter(searchParams, "correlation_id"),
      order_id: readFilter(searchParams, "order_id"),
      time_from: readFilter(searchParams, "time_from"),
      time_to: readFilter(searchParams, "time_to"),
      snapshot_at: readFilter(searchParams, "snapshot_at"),
    }),
    [searchParams],
  );

  const updateFilter = (key, value) => {
    const next = new URLSearchParams(searchParams);
    if (!value || value === "all") {
      next.delete(key);
    } else {
      next.set(key, value);
    }
    setSearchParams(next, { replace: true });
  };

  const buildParams = () => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (!value || value === "all") return;
      params.set(key, value);
    });
    return params.toString();
  };

  const loadAnalytics = async () => {
    setLoading(true);
    try {
      const query = buildParams();
      const [summaryRes, stateLatencyRes, failureRes, alertsRes, policyRes] = await Promise.all([
        apiClient.get(`/admin-phase3/execution-analytics/summary?${query}`),
        apiClient.get(`/admin-phase3/execution-analytics/state-latency?${query}`),
        apiClient.get(`/admin-phase3/execution-analytics/failure-trends?${query}`),
        apiClient.get("/admin-phase3/execution-alerts", { params: { status_filter: alertStatusFilter, limit: 50 } }),
        apiClient.get("/admin-phase3/execution-alerts/auto-ack/policy"),
      ]);
      setSummary(summaryRes.data || null);
      setStateLatency(stateLatencyRes.data?.rows || []);
      setSlowestStates(stateLatencyRes.data?.slowest_states || summaryRes.data?.failure_metrics?.slowest_states || []);
      setTimeoutDistribution(stateLatencyRes.data?.timeout_distribution || summaryRes.data?.timeout_metrics?.timeout_distribution || []);
      setFailureTrend(failureRes.data?.daily_trend || []);
      setFailureClasses(failureRes.data?.top_failure_classes || []);
      setExecutionAlerts(alertsRes.data || []);
      setAutoAckPolicy(policyRes.data?.policy || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Execution analytics yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAnalytics();
  }, [searchParams, alertStatusFilter]);

  useEffect(() => {
    const timer = setInterval(loadAnalytics, refreshMs);
    return () => clearInterval(timer);
  }, [refreshMs, searchParams, alertStatusFilter]);

  const markAlertSeen = async (alertId) => {
    try {
      await apiClient.post(`/admin-phase3/execution-alerts/${alertId}/seen`);
      await loadAnalytics();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Alert seen işlemi başarısız");
    }
  };

  const ackAlert = async (alertId) => {
    try {
      await apiClient.post(`/admin-phase3/execution-alerts/${alertId}/ack`);
      await loadAnalytics();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Alert ack işlemi başarısız");
    }
  };

  const updateAutoAckPolicy = async (patch = {}) => {
    try {
      const payload = {
        enabled: patch.enabled ?? Boolean(autoAckPolicy?.enabled),
        threshold_hours: Number(patch.threshold_hours ?? autoAckPolicy?.threshold_hours ?? 24),
        only_execution_alerts: patch.only_execution_alerts ?? Boolean(autoAckPolicy?.only_execution_alerts ?? true),
        reason: autoAckReason || "policy_update",
      };
      const { data } = await apiClient.put("/admin-phase3/execution-alerts/auto-ack/policy", payload);
      setAutoAckPolicy(data?.policy || null);
      toast.success("INFO auto-ack policy güncellendi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Auto-ack policy güncellenemedi");
    }
  };

  const runInfoAutoAck = async () => {
    if (!autoAckPreviewToken) {
      toast.error("Önce auto-ack preview çalıştırın");
      return;
    }
    setAutoAckRunning(true);
    try {
      const { data } = await apiClient.post("/admin-phase3/execution-alerts/auto-ack/run", null, {
        params: {
          reason: autoAckReason || "scheduled_auto_ack",
          preview_token: autoAckPreviewToken,
          dry_run: autoAckDryRun,
        },
      });
      toast.success(`${autoAckDryRun ? "Dry-run" : "Run"} tamamlandı: ${data?.acked_count ?? 0} alert`);
      setAutoAckPreviewToken("");
      setAutoAckPreviewCount(0);
      await loadAnalytics();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "INFO auto-ack run başarısız");
    } finally {
      setAutoAckRunning(false);
    }
  };

  const previewInfoAutoAck = async () => {
    try {
      const { data } = await apiClient.post("/admin-phase3/execution-alerts/auto-ack/preview");
      setAutoAckPreviewToken(data?.preview_token || "");
      setAutoAckPreviewCount(Number(data?.matched_count || 0));
      toast.success(`Preview hazır: ${data?.matched_count || 0} eşleşme`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Auto-ack preview başarısız");
      setAutoAckPreviewToken("");
      setAutoAckPreviewCount(0);
    }
  };

  const applyDefaultAutoAck = async () => {
    try {
      const { data } = await apiClient.post("/admin-phase3/execution-alerts/auto-ack/apply-default");
      toast.success(`INFO auto-ack (24h seen) uygulandı: ${data?.updated_count ?? 0}`);
      await loadAnalytics();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Default auto-ack başarısız");
    }
  };

  const totals = summary?.totals || {};
  const timeoutMetrics = summary?.timeout_metrics || {};
  const retryMetrics = summary?.retry_metrics || {};
  const failureMetrics = summary?.failure_metrics || {};

  return (
    <section className="space-y-4" data-testid="execution-control-analytics-page">
      <div className="grid gap-3 md:grid-cols-6" data-testid="execution-control-analytics-filters">
        <div>
          <Label>search</Label>
          <Input value={filters.search} onChange={(e) => updateFilter("search", e.target.value)} data-testid="execution-control-analytics-search-input" />
        </div>
        <div>
          <Label>state</Label>
          <Select value={filters.state || "all"} onValueChange={(v) => updateFilter("state", v)}>
            <SelectTrigger data-testid="execution-control-analytics-state-select"><SelectValue /></SelectTrigger>
            <SelectContent>{["all", "created", "submitted", "acknowledged", "partially_filled", "timeout", "fallback_submitted", "filled", "rejected", "failed", "cancelled"].map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div>
          <Label>status</Label>
          <Select value={filters.status || "all"} onValueChange={(v) => updateFilter("status", v)}>
            <SelectTrigger data-testid="execution-control-analytics-status-select"><SelectValue /></SelectTrigger>
            <SelectContent>{STATUS_OPTIONS.map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div>
          <Label>source_type</Label>
          <Select value={filters.source_type || "all"} onValueChange={(v) => updateFilter("source_type", v)}>
            <SelectTrigger data-testid="execution-control-analytics-source-select"><SelectValue /></SelectTrigger>
            <SelectContent>{SOURCE_OPTIONS.map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div>
          <Label>symbol</Label>
          <Input value={filters.symbol} onChange={(e) => updateFilter("symbol", e.target.value)} data-testid="execution-control-analytics-symbol-input" />
        </div>
        <div>
          <Label>strategy</Label>
          <Input value={filters.strategy} onChange={(e) => updateFilter("strategy", e.target.value)} data-testid="execution-control-analytics-strategy-input" />
        </div>
        <div>
          <Label>correlation_id</Label>
          <Input value={filters.correlation_id} onChange={(e) => updateFilter("correlation_id", e.target.value)} data-testid="execution-control-analytics-correlation-input" />
        </div>
        <div>
          <Label>order_id</Label>
          <Input value={filters.order_id} onChange={(e) => updateFilter("order_id", e.target.value)} data-testid="execution-control-analytics-order-id-input" />
        </div>
        <div>
          <Label>time_from (ISO)</Label>
          <Input value={filters.time_from} onChange={(e) => updateFilter("time_from", e.target.value)} placeholder="2026-03-22T00:00:00+00:00" data-testid="execution-control-analytics-time-from-input" />
        </div>
        <div>
          <Label>time_to (ISO)</Label>
          <Input value={filters.time_to} onChange={(e) => updateFilter("time_to", e.target.value)} placeholder="2026-03-22T23:59:59+00:00" data-testid="execution-control-analytics-time-to-input" />
        </div>
        <div>
          <Label>snapshot_at (ISO)</Label>
          <Input value={filters.snapshot_at} onChange={(e) => updateFilter("snapshot_at", e.target.value)} placeholder="2026-03-22T23:59:59+00:00" data-testid="execution-control-analytics-snapshot-input" />
        </div>
        <div>
          <Label>refresh</Label>
          <Select value={String(refreshMs)} onValueChange={(v) => setRefreshMs(Number(v))}>
            <SelectTrigger data-testid="execution-control-analytics-refresh-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="5000">5s</SelectItem>
              <SelectItem value="10000">10s</SelectItem>
              <SelectItem value="20000">20s</SelectItem>
              <SelectItem value="30000">30s</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="flex flex-wrap gap-2" data-testid="execution-control-analytics-filter-actions">
        <Button onClick={loadAnalytics} data-testid="execution-control-analytics-refresh-button">Yenile</Button>
        <Button variant="outline" onClick={() => setSearchParams(new URLSearchParams(), { replace: true })} data-testid="execution-control-analytics-clear-filters-button">Temizle</Button>
      </div>

      <div className="grid gap-3 md:grid-cols-5" data-testid="execution-control-analytics-summary-grid">
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="execution-control-analytics-total-transitions-card">
          <p className="text-xs text-slate-400">total transitions</p>
          <p className="text-lg font-semibold">{totals.transitions || 0}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="execution-control-analytics-total-events-card">
          <p className="text-xs text-slate-400">total events</p>
          <p className="text-lg font-semibold">{totals.events || 0}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="execution-control-analytics-timeout-rate-card">
          <p className="text-xs text-slate-400">timeout rate</p>
          <p className="text-lg font-semibold">{timeoutMetrics.timeout_rate || 0}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="execution-control-analytics-failure-rate-card">
          <p className="text-xs text-slate-400">failure rate</p>
          <p className="text-lg font-semibold">{failureMetrics.failure_rate || 0}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="execution-control-analytics-slowest-state-card">
          <p className="text-xs text-slate-400">SLOWEST STATE</p>
          <p className="text-sm font-semibold">
            {slowestStates[0]?.state || failureMetrics?.slowest_state?.state || "-"}
            {" "}
            → {slowestStates[0]?.avg_latency_ms || failureMetrics?.slowest_state?.avg_latency_ms || 0}ms avg
          </p>
        </article>
      </div>

      <div className="rounded border border-slate-700 bg-slate-950 p-3 text-xs" data-testid="execution-control-analytics-snapshot-meta">
        <p data-testid="execution-control-analytics-snapshot-at">snapshot_at={summary?.snapshot_at || "-"}</p>
        <p data-testid="execution-control-analytics-retry-metrics">retry_count={retryMetrics.retry_count || 0} · retry_success_ratio={retryMetrics.retry_success_ratio || 0} · fallback_usage_rate={retryMetrics.fallback_usage_rate || 0}</p>
        <p data-testid="execution-control-analytics-failure-metrics">failed_or_rejected={failureMetrics.failed_or_rejected_count || 0} · dead_letter={failureMetrics.dead_letter_count || 0}</p>
        <p data-testid="execution-control-analytics-timeout-distribution">timeout_distribution={JSON.stringify(timeoutDistribution || [])}</p>
        <p data-testid="execution-control-analytics-loading-state">loading={loading ? "true" : "false"}</p>
      </div>

      <div className="overflow-x-auto border border-slate-800 bg-slate-900" data-testid="execution-control-analytics-state-latency-table-wrapper">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>state</TableHead>
              <TableHead>count</TableHead>
              <TableHead>avg_latency_ms</TableHead>
              <TableHead>p95_latency_ms</TableHead>
              <TableHead>min_latency_ms</TableHead>
              <TableHead>max_latency_ms</TableHead>
              <TableHead>timeout_count</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {stateLatency.map((row) => (
              <TableRow key={row.state} data-testid={`execution-control-analytics-state-latency-row-${row.state}`}>
                <TableCell>{row.state}</TableCell>
                <TableCell>{row.count}</TableCell>
                <TableCell>{row.avg_latency_ms}</TableCell>
                <TableCell>{row.p95_latency_ms ?? "-"}</TableCell>
                <TableCell>{row.min_latency_ms ?? "-"}</TableCell>
                <TableCell>{row.max_latency_ms ?? "-"}</TableCell>
                <TableCell>{row.timeout_count ?? 0}</TableCell>
              </TableRow>
            ))}
            {!stateLatency.length && (
              <TableRow><TableCell colSpan={7}>Kayıt yok</TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <div className="grid gap-3 md:grid-cols-2" data-testid="execution-control-analytics-failure-section">
        <div className="overflow-x-auto border border-slate-800 bg-slate-900" data-testid="execution-control-analytics-failure-trend-table-wrapper">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>date</TableHead>
                <TableHead>total</TableHead>
                <TableHead>dead_letter</TableHead>
                <TableHead>resolved</TableHead>
                <TableHead>open</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {failureTrend.map((row) => (
                <TableRow key={row.date} data-testid={`execution-control-analytics-failure-trend-row-${row.date}`}>
                  <TableCell>{row.date}</TableCell>
                  <TableCell>{row.total_failures}</TableCell>
                  <TableCell>{row.dead_letter_count}</TableCell>
                  <TableCell>{row.resolved_count}</TableCell>
                  <TableCell>{row.open_count}</TableCell>
                </TableRow>
              ))}
              {!failureTrend.length && (
                <TableRow><TableCell colSpan={5}>Kayıt yok</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </div>

        <div className="overflow-x-auto border border-slate-800 bg-slate-900" data-testid="execution-control-analytics-failure-classes-table-wrapper">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>failure_class</TableHead>
                <TableHead>count</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {failureClasses.map((row) => (
                <TableRow key={row.failure_class} data-testid={`execution-control-analytics-failure-class-row-${row.failure_class}`}>
                  <TableCell>{row.failure_class}</TableCell>
                  <TableCell>{row.count}</TableCell>
                </TableRow>
              ))}
              {!failureClasses.length && (
                <TableRow><TableCell colSpan={2}>Kayıt yok</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </div>

      <div className="space-y-3 border border-slate-800 bg-slate-900 p-3" data-testid="execution-control-alert-panel">
        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="execution-control-alert-panel-header">
          <p className="text-sm font-semibold">Execution Alerts (son 50)</p>
          <Select value={alertStatusFilter} onValueChange={setAlertStatusFilter}>
            <SelectTrigger className="w-44" data-testid="execution-control-alert-status-filter-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">all</SelectItem>
              <SelectItem value="open">open</SelectItem>
              <SelectItem value="ack">ack</SelectItem>
              <SelectItem value="resolved">resolved</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="grid gap-2 rounded border border-slate-700 bg-slate-950 p-3 md:grid-cols-6" data-testid="execution-control-alert-auto-ack-policy-panel">
          <div className="flex items-center gap-2" data-testid="execution-control-alert-auto-ack-enabled-row">
            <Switch
              checked={Boolean(autoAckPolicy?.enabled)}
              onCheckedChange={(checked) => {
                setAutoAckPolicy((prev) => ({ ...(prev || {}), enabled: Boolean(checked) }));
              }}
              data-testid="execution-control-alert-auto-ack-enabled-switch"
            />
            <span className="text-xs">INFO auto-ack enabled</span>
          </div>

          <Input
            type="number"
            min={1}
            max={168}
            value={autoAckPolicy?.threshold_hours ?? 24}
            onChange={(event) => {
              const value = Math.min(Math.max(Number(event.target.value) || 24, 1), 168);
              setAutoAckPolicy((prev) => ({ ...(prev || {}), threshold_hours: value }));
            }}
            data-testid="execution-control-alert-auto-ack-threshold-input"
          />

          <Input
            value={autoAckReason}
            onChange={(event) => setAutoAckReason(event.target.value)}
            placeholder="policy reason"
            data-testid="execution-control-alert-auto-ack-reason-input"
          />

          <div className="flex items-center gap-2" data-testid="execution-control-alert-auto-ack-execution-only-row">
            <Switch
              checked={Boolean(autoAckPolicy?.only_execution_alerts ?? true)}
              onCheckedChange={(checked) => {
                setAutoAckPolicy((prev) => ({ ...(prev || {}), only_execution_alerts: Boolean(checked) }));
              }}
              data-testid="execution-control-alert-auto-ack-execution-only-switch"
            />
            <span className="text-xs">only execution alerts</span>
          </div>

          <div className="space-y-1 text-xs" data-testid="execution-control-alert-auto-ack-preview-info-row">
            <p data-testid="execution-control-alert-auto-ack-preview-token">preview_token: {autoAckPreviewToken || "-"}</p>
            <p data-testid="execution-control-alert-auto-ack-preview-count">matched_count: {autoAckPreviewCount}</p>
            <div className="flex items-center gap-2" data-testid="execution-control-alert-auto-ack-dry-run-row">
              <Switch
                checked={autoAckDryRun}
                onCheckedChange={(checked) => setAutoAckDryRun(Boolean(checked))}
                data-testid="execution-control-alert-auto-ack-dry-run-switch"
              />
              <span>dry-run</span>
            </div>
          </div>

          <div className="flex flex-wrap gap-2" data-testid="execution-control-alert-auto-ack-actions-row">
            <Button
              size="sm"
              variant="outline"
              onClick={() => updateAutoAckPolicy()}
              data-testid="execution-control-alert-auto-ack-policy-save-button"
            >
              Policy Kaydet
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={previewInfoAutoAck}
              data-testid="execution-control-alert-auto-ack-preview-button"
            >
              Preview
            </Button>
            <Button
              size="sm"
              onClick={runInfoAutoAck}
              disabled={autoAckRunning || String(autoAckReason || "").trim().length < 3 || !autoAckPreviewToken}
              title={!autoAckPreviewToken ? "Önce preview çalıştırılmalı" : ""}
              data-testid="execution-control-alert-auto-ack-run-button"
            >
              Run
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={applyDefaultAutoAck}
              data-testid="execution-control-alert-auto-ack-default-button"
            >
              Apply INFO &gt;24h Seen
            </Button>
          </div>
        </div>

        <div className="overflow-x-auto" data-testid="execution-control-alert-table-wrapper">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>severity</TableHead>
                <TableHead>alert_type</TableHead>
                <TableHead>status</TableHead>
                <TableHead>seen</TableHead>
                <TableHead>message</TableHead>
                <TableHead>created_at</TableHead>
                <TableHead>actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {executionAlerts.map((alert) => (
                <TableRow key={alert.id} data-testid={`execution-control-alert-row-${alert.id}`}>
                  <TableCell>{alert.severity}</TableCell>
                  <TableCell>{alert.alert_type}</TableCell>
                  <TableCell>{alert.status}</TableCell>
                  <TableCell>{String(Boolean(alert?.details?.seen))}</TableCell>
                  <TableCell className="max-w-[360px] truncate">{alert.message}</TableCell>
                  <TableCell>{alert.created_at}</TableCell>
                  <TableCell>
                    <div className="flex gap-2">
                      <Button size="sm" variant="outline" onClick={() => markAlertSeen(alert.id)} data-testid={`execution-control-alert-seen-button-${alert.id}`}>Seen</Button>
                      <Button size="sm" onClick={() => ackAlert(alert.id)} data-testid={`execution-control-alert-ack-button-${alert.id}`}>Ack</Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
              {!executionAlerts.length && (
                <TableRow><TableCell colSpan={7}>Alert kaydı yok</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </div>
    </section>
  );
};
