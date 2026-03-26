import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";

const formatUsd = (value) => new Intl.NumberFormat("tr-TR", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(Number(value || 0));
const toIsoOrNull = (value) => {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toISOString();
};

export const AdminCommercialOpsPage = () => {
  const { user } = useAuth();
  const [isLoading, setIsLoading] = useState(false);
  const [overview, setOverview] = useState(null);
  const [filters, setFilters] = useState({ environment: "live", time_window: "last_30_days", from: "", to: "" });
  const [controlForm, setControlForm] = useState({
    user_id: "",
    trading_enabled: true,
    capital_frozen: false,
    withdraw_locked: false,
    emergency_stop: false,
    reason_note: "",
  });
  const [exportForm, setExportForm] = useState({
    export_type: "pnl",
    schema_version: "v1",
    output_format: "csv",
    reason_note: "commercial ops export",
  });
  const [scheduleForm, setScheduleForm] = useState({ export_type: "pnl", schedule_period: "daily", output_format: "csv" });
  const [selectedAlertIds, setSelectedAlertIds] = useState([]);
  const [bulkTriageStatus, setBulkTriageStatus] = useState("acknowledged");
  const [assignmentForm, setAssignmentForm] = useState({ alert_id: "", assigned_to_user_id: "", assigned_to_email: "", assignment_note: "" });
  const [infraStatus, setInfraStatus] = useState({ apiReachable: false, authReachable: true, lastOverviewRefreshStatus: "idle" });

  const isSuperAdmin = user?.role === "super_admin";

  const loadOverview = useCallback(async () => {
    if (!isSuperAdmin) return;
    setIsLoading(true);
    try {
      const params = { environment: filters.environment, time_window: filters.time_window };
      const fromIso = toIsoOrNull(filters.from);
      const toIso = toIsoOrNull(filters.to);
      if (fromIso) params.from = fromIso;
      if (toIso) params.to = toIso;
      const { data } = await apiClient.get("/admin/commercial/overview", { params });
      setOverview(data || null);
      setInfraStatus((prev) => ({ ...prev, apiReachable: true, authReachable: true, lastOverviewRefreshStatus: "success" }));
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Commercial overview yüklenemedi");
      setInfraStatus((prev) => ({ ...prev, apiReachable: false, lastOverviewRefreshStatus: "failed" }));
    } finally {
      setIsLoading(false);
    }
  }, [filters.environment, filters.time_window, filters.from, filters.to, isSuperAdmin]);

  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  const submitOperationalControl = async () => {
    if (!controlForm.user_id.trim()) {
      toast.error("User ID zorunludur");
      return;
    }
    try {
      await apiClient.post(`/admin/commercial/controls/${controlForm.user_id.trim()}`, controlForm);
      toast.success("Operational control güncellendi");
      setControlForm((prev) => ({ ...prev, reason_note: "" }));
      await loadOverview();
    } catch (error) {
      const detail = error?.response?.data?.detail;
      const reasonCode = typeof detail === "object" ? detail?.reason_code : undefined;
      toast.error(reasonCode ? `Operational control reddedildi: ${reasonCode}` : detail || "Operational control güncellenemedi");
    }
  };

  const updateAlertLifecycle = async (alertId, triageStatus) => {
    try {
      await apiClient.post(`/admin/commercial/alerts/${alertId}/lifecycle`, {
        triage_status: triageStatus,
        escalation_level: triageStatus === "resolved" ? "none" : "medium",
        resolution_note: triageStatus === "resolved" ? "Panel üzerinden çözüldü" : null,
        acknowledge: true,
      });
      toast.success("Alert lifecycle güncellendi");
      await loadOverview();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Alert lifecycle güncellenemedi");
    }
  };

  const toggleAlertSelection = (alertId) => {
    setSelectedAlertIds((prev) => (prev.includes(alertId) ? prev.filter((id) => id !== alertId) : [...prev, alertId]));
  };

  const runBulkAlertAction = async () => {
    if (selectedAlertIds.length === 0) {
      toast.error("Önce en az bir alert seçin");
      return;
    }
    try {
      await apiClient.post("/admin/commercial/alerts/bulk-lifecycle", {
        alert_ids: selectedAlertIds,
        triage_status: bulkTriageStatus,
        escalation_level: bulkTriageStatus === "resolved" ? "none" : "medium",
        acknowledge: true,
      });
      toast.success("Bulk alert aksiyonu tamamlandı");
      setSelectedAlertIds([]);
      await loadOverview();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Bulk alert aksiyonu başarısız");
    }
  };

  const assignAlertOwner = async () => {
    if (!assignmentForm.alert_id) {
      toast.error("alert_id zorunlu");
      return;
    }
    try {
      await apiClient.post(`/admin/commercial/alerts/${assignmentForm.alert_id}/assign`, assignmentForm);
      toast.success("Alert owner atandı");
      setAssignmentForm({ alert_id: "", assigned_to_user_id: "", assigned_to_email: "", assignment_note: "" });
      await loadOverview();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Alert assignment başarısız");
    }
  };

  const requestExport = async () => {
    try {
      await apiClient.post("/admin/commercial/exports/request", {
        ...exportForm,
        filters_snapshot: overview?.applied_filters || {},
        column_mapping: {},
        row_count: 0,
      });
      toast.success("Export request oluşturuldu");
      await loadOverview();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Export request başarısız");
    }
  };

  const createSchedule = async () => {
    try {
      await apiClient.post("/admin/commercial/exports/schedules", {
        ...scheduleForm,
        filters_snapshot: overview?.applied_filters || {},
      });
      toast.success("Export schedule oluşturuldu");
      await loadOverview();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Export schedule oluşturulamadı");
    }
  };

  const financialAccuracy = overview?.financial_accuracy || {};
  const revenueModel = overview?.revenue_model || {};
  const userEconomics = overview?.user_economics || {};
  const pnlAnalytics = overview?.pnl_analytics || {};
  const riskSummary = overview?.risk_summary || {};
  const usageAnalytics = overview?.usage_analytics || {};
  const dataQuality = overview?.data_quality || {};
  const exportOps = overview?.export_ops || {};
  const alertRail = overview?.alert_rail || [];
  const operationalControls = overview?.operational_controls || {};
  const appliedFilters = overview?.applied_filters || {};

  const executive = useMemo(
    () => ({
      netTotal: Number(financialAccuracy.net_total_usd || 0),
      grossTotal: Number(financialAccuracy.gross_total_usd || 0),
      totalRevenue: Number(revenueModel.total_revenue_usd || 0),
      riskExposure: Number(riskSummary.risk_exposure_usd || 0),
    }),
    [financialAccuracy, revenueModel, riskSummary],
  );

  if (!isSuperAdmin) {
    return (
      <section className="border border-rose-500/40 bg-rose-950/20 p-4" data-testid="admin-commercial-super-admin-only">
        <h2 className="text-xl font-bold" data-testid="admin-commercial-super-admin-only-title">Bu alan sadece super_admin için açık</h2>
        <p className="text-sm text-rose-200" data-testid="admin-commercial-super-admin-only-message">Commercial Ops verisi hassas yönetim verisidir.</p>
      </section>
    );
  }

  return (
    <section className="space-y-4" data-testid="admin-commercial-ops-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="admin-commercial-ops-header">
        <h2 className="text-4xl font-black uppercase text-black" data-testid="admin-commercial-ops-title">Commercial Ops</h2>
        <p className="text-sm text-black/80" data-testid="admin-commercial-ops-description">Tek contract ile tam backoffice operasyon paneli.</p>
        <div className="mt-3 grid gap-2 md:grid-cols-6" data-testid="admin-commercial-header-badges-grid">
          <div className="border border-black/20 bg-orange-100 p-2 text-xs" data-testid="admin-commercial-badge-data-freshness">data freshness: {dataQuality.freshness_seconds ?? "-"}</div>
          <div className="border border-black/20 bg-orange-100 p-2 text-xs" data-testid="admin-commercial-badge-reconciliation-status">reconciliation status: {financialAccuracy.reconciliation_status || "-"}</div>
          <div className="border border-black/20 bg-orange-100 p-2 text-xs" data-testid="admin-commercial-badge-duplicate-trade-status">duplicate trade status: {dataQuality.duplicate_trade_status || "-"}</div>
          <div className="border border-black/20 bg-orange-100 p-2 text-xs" data-testid="admin-commercial-badge-active-alert-count">active alerts: {alertRail.length}</div>
          <div className="border border-black/20 bg-orange-100 p-2 text-xs" data-testid="admin-commercial-badge-export-scheduler-health">scheduler health: {exportOps.scheduler_health || "-"}</div>
          <div className="border border-black/20 bg-orange-100 p-2 text-xs" data-testid="admin-commercial-badge-infra-health">infra: api={String(infraStatus.apiReachable)} auth={String(infraStatus.authReachable)} scheduler={exportOps.scheduler_health || "unknown"} refresh={infraStatus.lastOverviewRefreshStatus}</div>
        </div>
      </header>

      <section className="border border-black/30 bg-orange-100 p-4" data-testid="admin-commercial-overview-filter-panel">
        <p className="text-xs uppercase tracking-widest" data-testid="admin-commercial-overview-filter-title">Overview Filters</p>
        <div className="mt-3 grid gap-2 md:grid-cols-5" data-testid="admin-commercial-overview-filter-grid">
          <select className="border border-black/40 bg-white px-3 py-2 text-sm" value={filters.environment} onChange={(event) => setFilters((prev) => ({ ...prev, environment: event.target.value }))} data-testid="admin-commercial-overview-environment-select">
            <option value="live">live</option>
            <option value="testnet">testnet</option>
          </select>
          <select className="border border-black/40 bg-white px-3 py-2 text-sm" value={filters.time_window} onChange={(event) => setFilters((prev) => ({ ...prev, time_window: event.target.value }))} data-testid="admin-commercial-overview-time-window-select">
            <option value="last_7_days">last_7_days</option>
            <option value="last_30_days">last_30_days</option>
            <option value="last_90_days">last_90_days</option>
            <option value="all_time">all_time</option>
          </select>
          <Input type="datetime-local" value={filters.from} onChange={(event) => setFilters((prev) => ({ ...prev, from: event.target.value }))} data-testid="admin-commercial-overview-from-input" />
          <Input type="datetime-local" value={filters.to} onChange={(event) => setFilters((prev) => ({ ...prev, to: event.target.value }))} data-testid="admin-commercial-overview-to-input" />
          <Button onClick={loadOverview} disabled={isLoading} data-testid="admin-commercial-overview-refresh-button">{isLoading ? "Yükleniyor..." : "Overview Yenile"}</Button>
        </div>
        <div className="mt-2 text-xs text-black/80" data-testid="admin-commercial-overview-applied-filters">environment={appliedFilters.environment || "-"} • time_window={appliedFilters.time_window || "-"}</div>
      </section>

      <section className="grid gap-3 md:grid-cols-4" data-testid="admin-commercial-executive-kpi-grid">
        <article className="border border-black/30 bg-orange-100 p-3" data-testid="admin-commercial-kpi-net-total-card"><p className="text-xs" data-testid="admin-commercial-kpi-net-total-label">Executive KPI • Net Total</p><p className="text-xl font-semibold" data-testid="admin-commercial-kpi-net-total-value">{formatUsd(executive.netTotal)}</p></article>
        <article className="border border-black/30 bg-orange-100 p-3" data-testid="admin-commercial-kpi-gross-total-card"><p className="text-xs" data-testid="admin-commercial-kpi-gross-total-label">Executive KPI • Gross Total</p><p className="text-xl font-semibold" data-testid="admin-commercial-kpi-gross-total-value">{formatUsd(executive.grossTotal)}</p></article>
        <article className="border border-black/30 bg-orange-100 p-3" data-testid="admin-commercial-kpi-revenue-total-card"><p className="text-xs" data-testid="admin-commercial-kpi-revenue-total-label">Executive KPI • Total Revenue</p><p className="text-xl font-semibold" data-testid="admin-commercial-kpi-revenue-total-value">{formatUsd(executive.totalRevenue)}</p></article>
        <article className="border border-black/30 bg-orange-100 p-3" data-testid="admin-commercial-kpi-risk-exposure-card"><p className="text-xs" data-testid="admin-commercial-kpi-risk-exposure-label">Executive KPI • Risk Exposure</p><p className="text-xl font-semibold" data-testid="admin-commercial-kpi-risk-exposure-value">{formatUsd(executive.riskExposure)}</p></article>
      </section>

      <section className="grid gap-4 lg:grid-cols-2" data-testid="admin-commercial-main-grid">
        <article className="border border-black/30 bg-orange-100 p-4" data-testid="admin-commercial-financial-accuracy-panel">
          <p className="text-xs uppercase tracking-widest" data-testid="admin-commercial-financial-accuracy-title">Financial Accuracy</p>
          <div className="mt-2 grid gap-2 text-sm" data-testid="admin-commercial-financial-accuracy-grid">
            <div data-testid="admin-commercial-financial-accuracy-net-value">Net Total: {formatUsd(financialAccuracy.net_total_usd)}</div>
            <div data-testid="admin-commercial-financial-accuracy-reconciliation-status">Reconciliation: {financialAccuracy.reconciliation_status || "-"}</div>
            <div data-testid="admin-commercial-financial-accuracy-drift-value">PnL Drift: {formatUsd(financialAccuracy.pnl_drift_usd)}</div>
            <div data-testid="admin-commercial-financial-accuracy-duplicate-count">Duplicate Trade: {financialAccuracy.duplicate_trade_count || 0}</div>
          </div>
        </article>

        <article className="border border-black/30 bg-orange-100 p-4" data-testid="admin-commercial-revenue-model-panel">
          <p className="text-xs uppercase tracking-widest" data-testid="admin-commercial-revenue-model-title">Revenue Model</p>
          <div className="mt-2 grid gap-2 text-sm" data-testid="admin-commercial-revenue-model-grid">
            <div data-testid="admin-commercial-revenue-total-value">Total Revenue: {formatUsd(revenueModel.total_revenue_usd)}</div>
            <div data-testid="admin-commercial-revenue-subscription-value">Subscription: {formatUsd(revenueModel.subscription_revenue_usd)}</div>
            <div data-testid="admin-commercial-revenue-platform-fee-value">Platform Fee: {formatUsd(revenueModel.platform_fee_revenue_usd)}</div>
            <div data-testid="admin-commercial-revenue-profit-split-value">Profit Split: {formatUsd(revenueModel.profit_split_revenue_usd)}</div>
          </div>
          <div className="mt-2 overflow-x-auto" data-testid="admin-commercial-top-users-by-revenue-table-wrapper">
            <Table data-testid="admin-commercial-top-users-by-revenue-table">
              <TableHeader><TableRow><TableHead data-testid="admin-commercial-top-users-by-revenue-head-user">top users by revenue</TableHead><TableHead data-testid="admin-commercial-top-users-by-revenue-head-value">revenue</TableHead></TableRow></TableHeader>
              <TableBody>
                {(revenueModel.revenue_by_user || []).slice(0, 50).map((row, idx) => (
                  <TableRow key={`${row.user_id}-${idx}`} data-testid={`admin-commercial-top-users-by-revenue-row-${idx}`}>
                    <TableCell data-testid={`admin-commercial-top-users-by-revenue-user-${idx}`}>{row.user_email || row.user_id}</TableCell>
                    <TableCell data-testid={`admin-commercial-top-users-by-revenue-value-${idx}`}>{formatUsd(row.revenue_usd)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </article>

        <article className="border border-black/30 bg-orange-100 p-4" data-testid="admin-commercial-user-economics-panel">
          <p className="text-xs uppercase tracking-widest" data-testid="admin-commercial-user-economics-title">User Economics</p>
          <div className="mt-2 grid gap-2 text-sm" data-testid="admin-commercial-user-economics-grid">
            <div data-testid="admin-commercial-user-economics-arpu">ARPU: {formatUsd(userEconomics.arpu_usd)}</div>
            <div data-testid="admin-commercial-user-economics-arppu">ARPPU: {formatUsd(userEconomics.arppu_usd)}</div>
            <div data-testid="admin-commercial-user-economics-churn">Churn Rate: {Number(userEconomics.churn_rate_pct || 0).toFixed(2)}%</div>
            <div data-testid="admin-commercial-user-economics-inactive-count">Inactive Users: {userEconomics.inactive_user_count || 0}</div>
          </div>
          <div className="mt-2 overflow-x-auto" data-testid="admin-commercial-high-churn-risk-users-table-wrapper">
            <Table data-testid="admin-commercial-high-churn-risk-users-table">
              <TableHeader><TableRow><TableHead data-testid="admin-commercial-high-churn-head-user">high churn risk users</TableHead><TableHead data-testid="admin-commercial-high-churn-head-days">inactive_days</TableHead></TableRow></TableHeader>
              <TableBody>
                {(userEconomics.high_churn_risk_users || []).slice(0, 50).map((row, idx) => (
                  <TableRow key={`${row.user_id}-${idx}`} data-testid={`admin-commercial-high-churn-row-${idx}`}>
                    <TableCell data-testid={`admin-commercial-high-churn-user-${idx}`}>{row.user_email || row.user_id}</TableCell>
                    <TableCell data-testid={`admin-commercial-high-churn-days-${idx}`}>{row.inactive_days}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </article>

        <article className="border border-black/30 bg-orange-100 p-4" data-testid="admin-commercial-pnl-analytics-panel">
          <p className="text-xs uppercase tracking-widest" data-testid="admin-commercial-pnl-analytics-title">PnL Analytics</p>
          <div className="mt-2 overflow-x-auto" data-testid="admin-commercial-top-strategies-by-pnl-table-wrapper">
            <Table data-testid="admin-commercial-top-strategies-by-pnl-table">
              <TableHeader><TableRow><TableHead data-testid="admin-commercial-top-strategies-head-name">top strategies by pnl</TableHead><TableHead data-testid="admin-commercial-top-strategies-head-total">total pnl</TableHead></TableRow></TableHeader>
              <TableBody>
                {(pnlAnalytics.strategy_pnl_breakdown || []).slice(0, 50).map((row, idx) => (
                  <TableRow key={`${row.key}-${idx}`} data-testid={`admin-commercial-top-strategies-row-${idx}`}>
                    <TableCell data-testid={`admin-commercial-top-strategies-name-${idx}`}>{row.key}</TableCell>
                    <TableCell data-testid={`admin-commercial-top-strategies-total-${idx}`}>{formatUsd(row.total_pnl_usd)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div className="mt-2 overflow-x-auto" data-testid="admin-commercial-top-symbols-by-pnl-table-wrapper">
            <Table data-testid="admin-commercial-top-symbols-by-pnl-table">
              <TableHeader><TableRow><TableHead data-testid="admin-commercial-top-symbols-head-name">top symbols by pnl</TableHead><TableHead data-testid="admin-commercial-top-symbols-head-total">total pnl</TableHead></TableRow></TableHeader>
              <TableBody>
                {(pnlAnalytics.symbol_pnl_breakdown || []).slice(0, 50).map((row, idx) => (
                  <TableRow key={`${row.key}-${idx}`} data-testid={`admin-commercial-top-symbols-row-${idx}`}>
                    <TableCell data-testid={`admin-commercial-top-symbols-name-${idx}`}>{row.key}</TableCell>
                    <TableCell data-testid={`admin-commercial-top-symbols-total-${idx}`}>{formatUsd(row.total_pnl_usd)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </article>

        <article className="border border-black/30 bg-orange-100 p-4" data-testid="admin-commercial-risk-exposure-panel">
          <p className="text-xs uppercase tracking-widest" data-testid="admin-commercial-risk-exposure-title">Risk & Exposure</p>
          <div className="mt-2 grid gap-2 text-sm" data-testid="admin-commercial-risk-exposure-grid">
            <div data-testid="admin-commercial-risk-liq-score">Liquidation Risk Score: {Number(riskSummary.liquidation_risk_score || 0).toFixed(2)}</div>
            <div data-testid="admin-commercial-risk-margin-state">Margin Risk State: {riskSummary.margin_risk_state || "-"}</div>
            <div data-testid="admin-commercial-risk-breach-count">Risk Limit Breach: {riskSummary.risk_limit_breach_count || 0}</div>
          </div>
          <div className="mt-2 overflow-x-auto" data-testid="admin-commercial-breached-users-table-wrapper">
            <Table data-testid="admin-commercial-breached-users-table">
              <TableHeader><TableRow><TableHead data-testid="admin-commercial-breached-users-head-user">breached users</TableHead><TableHead data-testid="admin-commercial-breached-users-head-exposure">exposure</TableHead></TableRow></TableHeader>
              <TableBody>
                {(riskSummary.breached_users || []).slice(0, 50).map((row, idx) => (
                  <TableRow key={`${row.user_id}-${idx}`} data-testid={`admin-commercial-breached-users-row-${idx}`}>
                    <TableCell data-testid={`admin-commercial-breached-users-user-${idx}`}>{row.user_id}</TableCell>
                    <TableCell data-testid={`admin-commercial-breached-users-exposure-${idx}`}>{formatUsd(row.exposure_usd)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </article>

        <article className="border border-black/30 bg-orange-100 p-4" data-testid="admin-commercial-usage-analytics-panel">
          <p className="text-xs uppercase tracking-widest" data-testid="admin-commercial-usage-analytics-title">Usage Analytics</p>
          <div className="mt-2 grid gap-2 text-sm" data-testid="admin-commercial-usage-analytics-grid">
            <div data-testid="admin-commercial-usage-request-count">request_count: {usageAnalytics.request_count || 0}</div>
            <div data-testid="admin-commercial-usage-success-count">success_count: {usageAnalytics.success_count || 0}</div>
            <div data-testid="admin-commercial-usage-failure-count">failure_count: {usageAnalytics.failure_count || 0}</div>
            <div data-testid="admin-commercial-usage-error-rate">error_rate_pct: {Number(usageAnalytics.error_rate_pct || 0).toFixed(2)}%</div>
            <div data-testid="admin-commercial-usage-avg-latency">avg_latency_ms: {Number(usageAnalytics.avg_latency_ms || 0).toFixed(2)}</div>
            <div data-testid="admin-commercial-usage-p95-latency">p95_latency_ms: {Number(usageAnalytics.p95_latency_ms || 0).toFixed(2)}</div>
          </div>
        </article>

        <article className="border border-black/30 bg-orange-100 p-4" data-testid="admin-commercial-data-quality-panel">
          <p className="text-xs uppercase tracking-widest" data-testid="admin-commercial-data-quality-title">Data Quality</p>
          <div className="mt-2 grid gap-2 text-sm" data-testid="admin-commercial-data-quality-grid">
            <div data-testid="admin-commercial-data-quality-status">status: {dataQuality.status || "-"}</div>
            <div data-testid="admin-commercial-data-quality-duplicate-count">duplicate_trade_count: {dataQuality.duplicate_trade_count || 0}</div>
            <div data-testid="admin-commercial-data-quality-cross-source-state">cross_source_validation_state: {dataQuality.cross_source_validation_state || "-"}</div>
            <div data-testid="admin-commercial-data-quality-stale-source-count">stale_source_count: {dataQuality.stale_source_count || 0}</div>
          </div>
        </article>

        <article className="border border-black/30 bg-orange-100 p-4" data-testid="admin-commercial-export-ops-panel">
          <p className="text-xs uppercase tracking-widest" data-testid="admin-commercial-export-ops-title">Export Ops</p>
          <div className="mt-2 grid gap-2 md:grid-cols-2" data-testid="admin-commercial-export-ops-forms-grid">
            <div data-testid="admin-commercial-export-request-form">
              <p className="text-xs" data-testid="admin-commercial-export-request-form-title">Export Request</p>
              <Input value={exportForm.export_type} onChange={(event) => setExportForm((prev) => ({ ...prev, export_type: event.target.value }))} data-testid="admin-commercial-export-request-type-input" />
              <Input value={exportForm.reason_note} onChange={(event) => setExportForm((prev) => ({ ...prev, reason_note: event.target.value }))} data-testid="admin-commercial-export-request-reason-input" />
              <Button className="mt-2" onClick={requestExport} data-testid="admin-commercial-export-request-submit-button">Export Request Oluştur</Button>
            </div>
            <div data-testid="admin-commercial-export-schedule-form">
              <p className="text-xs" data-testid="admin-commercial-export-schedule-form-title">Schedule</p>
              <Input value={scheduleForm.export_type} onChange={(event) => setScheduleForm((prev) => ({ ...prev, export_type: event.target.value }))} data-testid="admin-commercial-export-schedule-type-input" />
              <select className="w-full border border-black/40 bg-white px-2 py-2 text-sm" value={scheduleForm.schedule_period} onChange={(event) => setScheduleForm((prev) => ({ ...prev, schedule_period: event.target.value }))} data-testid="admin-commercial-export-schedule-period-select">
                <option value="daily">daily</option>
                <option value="weekly">weekly</option>
                <option value="monthly">monthly</option>
              </select>
              <Button className="mt-2" onClick={createSchedule} data-testid="admin-commercial-export-schedule-submit-button">Schedule Oluştur</Button>
            </div>
          </div>
          <div className="mt-3 overflow-x-auto" data-testid="admin-commercial-recent-export-jobs-table-wrapper">
            <Table data-testid="admin-commercial-recent-export-jobs-table">
              <TableHeader><TableRow><TableHead data-testid="admin-commercial-recent-export-jobs-head-type">recent export jobs</TableHead><TableHead data-testid="admin-commercial-recent-export-jobs-head-period">period</TableHead><TableHead data-testid="admin-commercial-recent-export-jobs-head-status">status</TableHead><TableHead data-testid="admin-commercial-recent-export-jobs-head-last-run">last_run_at</TableHead><TableHead data-testid="admin-commercial-recent-export-jobs-head-retry-count">retry_count</TableHead><TableHead data-testid="admin-commercial-recent-export-jobs-head-next-retry">next_retry_at</TableHead><TableHead data-testid="admin-commercial-recent-export-jobs-head-running-started">running_started_at</TableHead><TableHead data-testid="admin-commercial-recent-export-jobs-head-stale-flag">stale_run_flag</TableHead><TableHead data-testid="admin-commercial-recent-export-jobs-head-failure">failure reason</TableHead></TableRow></TableHeader>
              <TableBody>
                {(exportOps.recent_export_jobs || []).slice(0, 50).map((row, idx) => (
                  <TableRow key={`${row.schedule_id}-${idx}`} data-testid={`admin-commercial-recent-export-jobs-row-${idx}`}>
                    <TableCell data-testid={`admin-commercial-recent-export-jobs-type-${idx}`}>{row.export_type}</TableCell>
                    <TableCell data-testid={`admin-commercial-recent-export-jobs-period-${idx}`}>{row.schedule_period}</TableCell>
                    <TableCell data-testid={`admin-commercial-recent-export-jobs-status-${idx}`}>{row.last_status}</TableCell>
                    <TableCell data-testid={`admin-commercial-recent-export-jobs-last-run-${idx}`}>{row.last_run_at ? new Date(row.last_run_at).toLocaleString() : "-"}</TableCell>
                    <TableCell data-testid={`admin-commercial-recent-export-jobs-retry-count-${idx}`}>{row.retry_count ?? 0}</TableCell>
                    <TableCell data-testid={`admin-commercial-recent-export-jobs-next-retry-${idx}`}>{row.next_retry_at ? new Date(row.next_retry_at).toLocaleString() : "-"}</TableCell>
                    <TableCell data-testid={`admin-commercial-recent-export-jobs-running-started-${idx}`}>{row.running_started_at ? new Date(row.running_started_at).toLocaleString() : "-"}</TableCell>
                    <TableCell data-testid={`admin-commercial-recent-export-jobs-stale-flag-${idx}`}>{String(Boolean(row.stale_run_flag))}</TableCell>
                    <TableCell data-testid={`admin-commercial-recent-export-jobs-failure-${idx}`}>{row.failure_reason || "-"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div className="mt-3 overflow-x-auto" data-testid="admin-commercial-recent-manifests-table-wrapper">
            <Table data-testid="admin-commercial-recent-manifests-table">
              <TableHeader><TableRow><TableHead data-testid="admin-commercial-recent-manifests-head-id">recent manifests</TableHead><TableHead data-testid="admin-commercial-recent-manifests-head-status">status</TableHead><TableHead data-testid="admin-commercial-recent-manifests-head-artifact">artifact</TableHead><TableHead data-testid="admin-commercial-recent-manifests-head-retention-state">retention_state</TableHead><TableHead data-testid="admin-commercial-recent-manifests-head-downloadable-state">downloadable_state</TableHead></TableRow></TableHeader>
              <TableBody>
                {(exportOps.recent_manifests || []).slice(0, 50).map((row, idx) => (
                  <TableRow key={`${row.export_id}-${idx}`} data-testid={`admin-commercial-recent-manifests-row-${idx}`}>
                    <TableCell data-testid={`admin-commercial-recent-manifests-id-${idx}`}>{row.export_id}</TableCell>
                    <TableCell data-testid={`admin-commercial-recent-manifests-status-${idx}`}>{row.delivery_status || row.status}</TableCell>
                    <TableCell data-testid={`admin-commercial-recent-manifests-artifact-${idx}`}>{row.artifact_ref || "-"}</TableCell>
                    <TableCell data-testid={`admin-commercial-recent-manifests-retention-state-${idx}`}>{row.retention_state || "-"}</TableCell>
                    <TableCell data-testid={`admin-commercial-recent-manifests-downloadable-state-${idx}`}>{row.downloadable_state || "-"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div className="mt-3 overflow-x-auto" data-testid="admin-commercial-recent-audits-table-wrapper">
            <Table data-testid="admin-commercial-recent-audits-table">
              <TableHeader><TableRow><TableHead data-testid="admin-commercial-recent-audits-head-id">recent audit trail</TableHead><TableHead data-testid="admin-commercial-recent-audits-head-actor">actor</TableHead><TableHead data-testid="admin-commercial-recent-audits-head-status">delivery_status</TableHead></TableRow></TableHeader>
              <TableBody>
                {(exportOps.recent_audits || []).slice(0, 50).map((row, idx) => (
                  <TableRow key={`${row.audit_id}-${idx}`} data-testid={`admin-commercial-recent-audits-row-${idx}`}>
                    <TableCell data-testid={`admin-commercial-recent-audits-id-${idx}`}>{row.export_id}</TableCell>
                    <TableCell data-testid={`admin-commercial-recent-audits-actor-${idx}`}>{row.actor_email || "-"}</TableCell>
                    <TableCell data-testid={`admin-commercial-recent-audits-status-${idx}`}>{row.delivery_status || "-"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </article>

        <article className="border border-black/30 bg-orange-100 p-4" data-testid="admin-commercial-alert-rail-panel">
          <p className="text-xs uppercase tracking-widest" data-testid="admin-commercial-alert-rail-title">Alert Rail</p>
          <div className="mt-2 grid gap-2 md:grid-cols-4" data-testid="admin-commercial-alert-bulk-controls-grid">
            <select className="border border-black/40 bg-white px-2 py-2 text-sm" value={bulkTriageStatus} onChange={(event) => setBulkTriageStatus(event.target.value)} data-testid="admin-commercial-alert-bulk-triage-select">
              <option value="acknowledged">acknowledged</option>
              <option value="investigating">investigating</option>
              <option value="resolved">resolved</option>
            </select>
            <Button onClick={runBulkAlertAction} data-testid="admin-commercial-alert-bulk-apply-button">Bulk Apply</Button>
            <Input placeholder="alert_id" value={assignmentForm.alert_id} onChange={(event) => setAssignmentForm((prev) => ({ ...prev, alert_id: event.target.value }))} data-testid="admin-commercial-alert-assignment-alert-id-input" />
            <Input placeholder="assigned user id" value={assignmentForm.assigned_to_user_id} onChange={(event) => setAssignmentForm((prev) => ({ ...prev, assigned_to_user_id: event.target.value }))} data-testid="admin-commercial-alert-assignment-user-id-input" />
            <Input placeholder="assigned email" value={assignmentForm.assigned_to_email} onChange={(event) => setAssignmentForm((prev) => ({ ...prev, assigned_to_email: event.target.value }))} data-testid="admin-commercial-alert-assignment-email-input" />
            <Input placeholder="assignment note" value={assignmentForm.assignment_note} onChange={(event) => setAssignmentForm((prev) => ({ ...prev, assignment_note: event.target.value }))} data-testid="admin-commercial-alert-assignment-note-input" />
            <Button onClick={assignAlertOwner} data-testid="admin-commercial-alert-assignment-submit-button">Assign Owner</Button>
            <div className="text-xs" data-testid="admin-commercial-alert-overdue-badge">SLA overdue: {alertRail.filter((row) => String(row.sla_state || "").includes("overdue")).length}</div>
          </div>
          <div className="mt-2 overflow-x-auto" data-testid="admin-commercial-recent-alerts-table-wrapper">
            <Table data-testid="admin-commercial-recent-alerts-table">
              <TableHeader><TableRow><TableHead data-testid="admin-commercial-recent-alerts-head-select">select</TableHead><TableHead data-testid="admin-commercial-recent-alerts-head-severity">severity</TableHead><TableHead data-testid="admin-commercial-recent-alerts-head-source">source</TableHead><TableHead data-testid="admin-commercial-recent-alerts-head-entity">entity</TableHead><TableHead data-testid="admin-commercial-recent-alerts-head-action">suggested_action</TableHead><TableHead data-testid="admin-commercial-recent-alerts-head-triage">triage_status</TableHead><TableHead data-testid="admin-commercial-recent-alerts-head-assigned">assigned</TableHead><TableHead data-testid="admin-commercial-recent-alerts-head-sla">sla_state</TableHead><TableHead data-testid="admin-commercial-recent-alerts-head-ack">acknowledged_at</TableHead><TableHead data-testid="admin-commercial-recent-alerts-head-ops">ops</TableHead></TableRow></TableHeader>
              <TableBody>
                {alertRail.slice(0, 50).map((row, idx) => (
                  <TableRow key={`${row.id}-${idx}`} data-testid={`admin-commercial-recent-alerts-row-${idx}`}>
                    <TableCell data-testid={`admin-commercial-recent-alerts-select-${idx}`}><input type="checkbox" checked={selectedAlertIds.includes(row.id)} onChange={() => toggleAlertSelection(row.id)} data-testid={`admin-commercial-recent-alerts-checkbox-${idx}`} /></TableCell>
                    <TableCell data-testid={`admin-commercial-recent-alerts-severity-${idx}`}>{row.severity}</TableCell>
                    <TableCell data-testid={`admin-commercial-recent-alerts-source-${idx}`}>{row.source}</TableCell>
                    <TableCell data-testid={`admin-commercial-recent-alerts-entity-${idx}`}>{`${row.entity_type}:${row.entity_id}`}</TableCell>
                    <TableCell data-testid={`admin-commercial-recent-alerts-action-${idx}`}>{row.suggested_action}</TableCell>
                    <TableCell data-testid={`admin-commercial-recent-alerts-triage-${idx}`}>{row.triage_status || "new"}</TableCell>
                    <TableCell data-testid={`admin-commercial-recent-alerts-assigned-${idx}`}>{row.assigned_to_email || "-"}</TableCell>
                    <TableCell data-testid={`admin-commercial-recent-alerts-sla-${idx}`}>{row.sla_state || "within_sla"}</TableCell>
                    <TableCell data-testid={`admin-commercial-recent-alerts-ack-${idx}`}>{row.acknowledged_at ? new Date(row.acknowledged_at).toLocaleString() : "-"}</TableCell>
                    <TableCell data-testid={`admin-commercial-recent-alerts-ops-${idx}`}>
                      <Button size="sm" disabled={!String(row.source || "").startsWith("commercial") } onClick={() => updateAlertLifecycle(row.id, "acknowledged")} data-testid={`admin-commercial-alert-ack-button-${idx}`}>Ack</Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </article>

        <article className="border border-black/30 bg-orange-100 p-4" data-testid="admin-commercial-operational-controls-panel">
          <p className="text-xs uppercase tracking-widest" data-testid="admin-commercial-operational-controls-title">Operational Controls</p>
          <div className="mt-2 grid gap-2 text-sm" data-testid="admin-commercial-operational-controls-summary-grid">
            <div data-testid="admin-commercial-operational-controls-trading-enabled-count">trading_enabled_count: {operationalControls.trading_enabled_count || 0}</div>
            <div data-testid="admin-commercial-operational-controls-emergency-stop-count">emergency_stop_count: {operationalControls.emergency_stop_count || 0}</div>
            <div data-testid="admin-commercial-operational-controls-capital-frozen-count">capital_frozen_count: {operationalControls.capital_frozen_count || 0}</div>
            <div data-testid="admin-commercial-operational-controls-withdraw-locked-count">withdraw_locked_count: {operationalControls.withdraw_locked_count || 0}</div>
          </div>
          <div className="mt-2 grid gap-2 md:grid-cols-3" data-testid="admin-commercial-operational-controls-form-grid">
            <Input placeholder="target user id" value={controlForm.user_id} onChange={(event) => setControlForm((prev) => ({ ...prev, user_id: event.target.value }))} data-testid="admin-commercial-operational-controls-user-id-input" />
            <select className="border border-black/40 bg-white px-2 py-2 text-sm" value={String(controlForm.trading_enabled)} onChange={(event) => setControlForm((prev) => ({ ...prev, trading_enabled: event.target.value === "true" }))} data-testid="admin-commercial-operational-controls-trading-enabled-select"><option value="true">trading_enabled=true</option><option value="false">trading_enabled=false</option></select>
            <select className="border border-black/40 bg-white px-2 py-2 text-sm" value={String(controlForm.capital_frozen)} onChange={(event) => setControlForm((prev) => ({ ...prev, capital_frozen: event.target.value === "true" }))} data-testid="admin-commercial-operational-controls-capital-frozen-select"><option value="false">capital_frozen=false</option><option value="true">capital_frozen=true</option></select>
            <select className="border border-black/40 bg-white px-2 py-2 text-sm" value={String(controlForm.withdraw_locked)} onChange={(event) => setControlForm((prev) => ({ ...prev, withdraw_locked: event.target.value === "true" }))} data-testid="admin-commercial-operational-controls-withdraw-locked-select"><option value="false">withdraw_locked=false</option><option value="true">withdraw_locked=true</option></select>
            <select className="border border-black/40 bg-white px-2 py-2 text-sm" value={String(controlForm.emergency_stop)} onChange={(event) => setControlForm((prev) => ({ ...prev, emergency_stop: event.target.value === "true" }))} data-testid="admin-commercial-operational-controls-emergency-stop-select"><option value="false">emergency_stop=false</option><option value="true">emergency_stop=true</option></select>
            <Input placeholder="reason note" value={controlForm.reason_note} onChange={(event) => setControlForm((prev) => ({ ...prev, reason_note: event.target.value }))} data-testid="admin-commercial-operational-controls-reason-note-input" />
            <Button onClick={submitOperationalControl} data-testid="admin-commercial-operational-controls-submit-button">Control Uygula</Button>
          </div>
          <div className="mt-3 overflow-x-auto" data-testid="admin-commercial-operational-controls-transitions-table-wrapper">
            <Table data-testid="admin-commercial-operational-controls-transitions-table">
              <TableHeader><TableRow><TableHead data-testid="admin-commercial-operational-controls-transitions-head-user">user</TableHead><TableHead data-testid="admin-commercial-operational-controls-transitions-head-changed-fields">changed_fields</TableHead><TableHead data-testid="admin-commercial-operational-controls-transitions-head-diff">previous → new</TableHead></TableRow></TableHeader>
              <TableBody>
                {(operationalControls.recent_actions || []).slice(0, 50).map((row, idx) => (
                  <TableRow key={`${row.transition_id}-${idx}`} data-testid={`admin-commercial-operational-controls-transitions-row-${idx}`}>
                    <TableCell data-testid={`admin-commercial-operational-controls-transitions-user-${idx}`}>{row.user_id}</TableCell>
                    <TableCell data-testid={`admin-commercial-operational-controls-transitions-changed-fields-${idx}`}>{(row.changed_fields || []).join(", ") || "-"}</TableCell>
                    <TableCell data-testid={`admin-commercial-operational-controls-transitions-diff-${idx}`}>
                      {JSON.stringify(row.previous_state_snapshot || {})} → {JSON.stringify(row.new_state_snapshot || {})}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </article>
      </section>
    </section>
  );
};
