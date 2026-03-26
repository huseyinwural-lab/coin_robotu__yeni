import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";

const formatUsd = (value) => {
  const numeric = Number(value || 0);
  return new Intl.NumberFormat("tr-TR", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(numeric);
};

const toIsoOrNull = (value) => {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toISOString();
};

export const AdminCommercialOpsPage = () => {
  const { user } = useAuth();
  const [isLoading, setIsLoading] = useState(false);
  const [overview, setOverview] = useState(null);
  const [filters, setFilters] = useState({
    environment: "live",
    time_window: "last_30_days",
    from: "",
    to: "",
  });

  const isSuperAdmin = user?.role === "super_admin";

  const loadOverview = useCallback(async () => {
    if (!isSuperAdmin) return;
    setIsLoading(true);
    try {
      const params = {
        environment: filters.environment,
        time_window: filters.time_window,
      };
      const fromIso = toIsoOrNull(filters.from);
      const toIso = toIsoOrNull(filters.to);
      if (fromIso) params.from = fromIso;
      if (toIso) params.to = toIso;

      const { data } = await apiClient.get("/admin/commercial/overview", { params });
      setOverview(data || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Commercial overview yüklenemedi");
    } finally {
      setIsLoading(false);
    }
  }, [filters.environment, filters.time_window, filters.from, filters.to, isSuperAdmin]);

  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  const executive = useMemo(() => {
    const fa = overview?.financial_accuracy || {};
    const revenue = overview?.revenue_model || {};
    const risk = overview?.risk_summary || {};
    const users = overview?.user_economics || {};
    return {
      netTotal: fa.net_total_usd || 0,
      grossTotal: fa.gross_total_usd || 0,
      totalRevenue: revenue.total_revenue_usd || 0,
      riskExposure: risk.risk_exposure_usd || 0,
      userCount: users.total_users || 0,
      payingUsers: users.paying_users || 0,
    };
  }, [overview]);

  const pnlAnalytics = useMemo(() => {
    const fa = overview?.financial_accuracy || {};
    const grossTotal = Number(fa.gross_total_usd || 0);
    const netTotal = Number(fa.net_total_usd || 0);
    const realizedGross = Number(fa.realized_gross_usd || 0);
    const unrealizedGross = Number(fa.unrealized_gross_usd || 0);
    const margin = grossTotal === 0 ? 0 : (netTotal / grossTotal) * 100;
    const unrealizedShare = grossTotal === 0 ? 0 : (unrealizedGross / grossTotal) * 100;
    const realizedShare = grossTotal === 0 ? 0 : (realizedGross / grossTotal) * 100;
    return {
      grossTotal,
      netTotal,
      margin,
      unrealizedShare,
      realizedShare,
      grossToNetDelta: Number(fa.net_vs_gross_delta_usd || 0),
    };
  }, [overview]);

  if (!isSuperAdmin) {
    return (
      <section className="border border-rose-500/40 bg-rose-950/20 p-4" data-testid="admin-commercial-super-admin-only">
        <h2 className="text-xl font-bold" data-testid="admin-commercial-super-admin-only-title">Bu alan sadece super_admin için açık</h2>
        <p className="text-sm text-rose-200" data-testid="admin-commercial-super-admin-only-message">Commercial Ops verisi hassas yönetim verisidir.</p>
      </section>
    );
  }

  const financialAccuracy = overview?.financial_accuracy || {};
  const revenueModel = overview?.revenue_model || {};
  const userEconomics = overview?.user_economics || {};
  const riskSummary = overview?.risk_summary || {};
  const usageAnalytics = overview?.usage_analytics || {};
  const dataQuality = overview?.data_quality || {};
  const appliedFilters = overview?.applied_filters || {};

  return (
    <section className="space-y-4" data-testid="admin-commercial-ops-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="admin-commercial-ops-header">
        <h2 className="text-4xl font-black uppercase text-black" data-testid="admin-commercial-ops-title">Commercial Ops</h2>
        <p className="text-sm text-black/80" data-testid="admin-commercial-ops-description">Tek endpoint sözleşmesi ile ticari operasyon görünümü.</p>
      </header>

      <section className="border border-black/30 bg-orange-100 p-4" data-testid="admin-commercial-overview-filter-panel">
        <p className="text-xs uppercase tracking-widest" data-testid="admin-commercial-overview-filter-title">Overview Filters</p>
        <div className="mt-3 grid gap-2 md:grid-cols-5" data-testid="admin-commercial-overview-filter-grid">
          <select
            className="border border-black/40 bg-white px-3 py-2 text-sm"
            value={filters.environment}
            onChange={(event) => setFilters((prev) => ({ ...prev, environment: event.target.value }))}
            data-testid="admin-commercial-overview-environment-select"
          >
            <option value="live">live</option>
            <option value="testnet">testnet</option>
          </select>
          <select
            className="border border-black/40 bg-white px-3 py-2 text-sm"
            value={filters.time_window}
            onChange={(event) => setFilters((prev) => ({ ...prev, time_window: event.target.value }))}
            data-testid="admin-commercial-overview-time-window-select"
          >
            <option value="last_7_days">last_7_days</option>
            <option value="last_30_days">last_30_days</option>
            <option value="last_90_days">last_90_days</option>
            <option value="all_time">all_time</option>
          </select>
          <Input
            type="datetime-local"
            value={filters.from}
            onChange={(event) => setFilters((prev) => ({ ...prev, from: event.target.value }))}
            data-testid="admin-commercial-overview-from-input"
          />
          <Input
            type="datetime-local"
            value={filters.to}
            onChange={(event) => setFilters((prev) => ({ ...prev, to: event.target.value }))}
            data-testid="admin-commercial-overview-to-input"
          />
          <Button onClick={loadOverview} disabled={isLoading} data-testid="admin-commercial-overview-refresh-button">
            {isLoading ? "Yükleniyor..." : "Overview Yenile"}
          </Button>
        </div>
        <div className="mt-2 text-xs text-black/80" data-testid="admin-commercial-overview-applied-filters">
          environment={appliedFilters.environment || "-"} • time_window={appliedFilters.time_window || "-"}
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-4" data-testid="admin-commercial-executive-kpi-grid">
        <article className="border border-black/30 bg-orange-100 p-3" data-testid="admin-commercial-kpi-net-total-card">
          <p className="text-xs" data-testid="admin-commercial-kpi-net-total-label">Executive KPI • Net Total</p>
          <p className="text-xl font-semibold" data-testid="admin-commercial-kpi-net-total-value">{formatUsd(executive.netTotal)}</p>
        </article>
        <article className="border border-black/30 bg-orange-100 p-3" data-testid="admin-commercial-kpi-gross-total-card">
          <p className="text-xs" data-testid="admin-commercial-kpi-gross-total-label">Executive KPI • Gross Total</p>
          <p className="text-xl font-semibold" data-testid="admin-commercial-kpi-gross-total-value">{formatUsd(executive.grossTotal)}</p>
        </article>
        <article className="border border-black/30 bg-orange-100 p-3" data-testid="admin-commercial-kpi-revenue-total-card">
          <p className="text-xs" data-testid="admin-commercial-kpi-revenue-total-label">Executive KPI • Total Revenue</p>
          <p className="text-xl font-semibold" data-testid="admin-commercial-kpi-revenue-total-value">{formatUsd(executive.totalRevenue)}</p>
        </article>
        <article className="border border-black/30 bg-orange-100 p-3" data-testid="admin-commercial-kpi-risk-exposure-card">
          <p className="text-xs" data-testid="admin-commercial-kpi-risk-exposure-label">Executive KPI • Risk Exposure</p>
          <p className="text-xl font-semibold" data-testid="admin-commercial-kpi-risk-exposure-value">{formatUsd(executive.riskExposure)}</p>
        </article>
      </section>

      <section className="border border-black/30 bg-orange-100 p-4" data-testid="admin-commercial-financial-accuracy-panel">
        <p className="text-xs uppercase tracking-widest" data-testid="admin-commercial-financial-accuracy-title">Financial Accuracy</p>
        <div className="mt-3 grid gap-3 md:grid-cols-3" data-testid="admin-commercial-financial-accuracy-grid">
          <div data-testid="admin-commercial-financial-accuracy-realized-value">Realized Gross: {formatUsd(financialAccuracy.realized_gross_usd)}</div>
          <div data-testid="admin-commercial-financial-accuracy-unrealized-value">Unrealized Gross: {formatUsd(financialAccuracy.unrealized_gross_usd)}</div>
          <div data-testid="admin-commercial-financial-accuracy-net-value">Net Total: {formatUsd(financialAccuracy.net_total_usd)}</div>
          <div data-testid="admin-commercial-financial-accuracy-fee-value">Fee Total: {formatUsd(financialAccuracy.trading_fee_total_usd)}</div>
          <div data-testid="admin-commercial-financial-accuracy-funding-value">Funding Total: {formatUsd(financialAccuracy.funding_total_usd)}</div>
          <div data-testid="admin-commercial-financial-accuracy-commission-value">Commission Total: {formatUsd(financialAccuracy.commission_total_usd)}</div>
        </div>
      </section>

      <section className="border border-black/30 bg-orange-100 p-4" data-testid="admin-commercial-revenue-model-panel">
        <p className="text-xs uppercase tracking-widest" data-testid="admin-commercial-revenue-model-title">Revenue Model</p>
        <div className="mt-2 text-sm" data-testid="admin-commercial-revenue-model-total-value">Toplam Revenue: {formatUsd(revenueModel.total_revenue_usd)}</div>
        <div className="mt-3 overflow-x-auto" data-testid="admin-commercial-revenue-components-table-wrapper">
          <Table data-testid="admin-commercial-revenue-components-table">
            <TableHeader>
              <TableRow>
                <TableHead data-testid="admin-commercial-revenue-components-head-type">Component</TableHead>
                <TableHead data-testid="admin-commercial-revenue-components-head-revenue">Revenue</TableHead>
                <TableHead data-testid="admin-commercial-revenue-components-head-source">Source</TableHead>
                <TableHead data-testid="admin-commercial-revenue-components-head-rate">Avg Rate</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(revenueModel.component_breakdown || []).map((row, idx) => (
                <TableRow key={`${row.component_type}-${idx}`} data-testid={`admin-commercial-revenue-component-row-${idx}`}>
                  <TableCell data-testid={`admin-commercial-revenue-component-type-${idx}`}>{row.component_type}</TableCell>
                  <TableCell data-testid={`admin-commercial-revenue-component-revenue-${idx}`}>{formatUsd(row.revenue_usd)}</TableCell>
                  <TableCell data-testid={`admin-commercial-revenue-component-source-${idx}`}>{formatUsd(row.source_amount_usd)}</TableCell>
                  <TableCell data-testid={`admin-commercial-revenue-component-rate-${idx}`}>{Number(row.share_rate_avg || 0).toFixed(4)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </section>

      <section className="border border-black/30 bg-orange-100 p-4" data-testid="admin-commercial-user-economics-panel">
        <p className="text-xs uppercase tracking-widest" data-testid="admin-commercial-user-economics-title">User Economics</p>
        <div className="mt-3 grid gap-3 md:grid-cols-3" data-testid="admin-commercial-user-economics-kpi-grid">
          <div data-testid="admin-commercial-user-economics-total-users-value">Toplam User: {executive.userCount}</div>
          <div data-testid="admin-commercial-user-economics-paying-users-value">Paying User: {executive.payingUsers}</div>
          <div data-testid="admin-commercial-user-economics-avg-ltv-value">Avg LTV: {formatUsd(userEconomics.avg_ltv_usd)}</div>
        </div>
        <div className="mt-3 overflow-x-auto" data-testid="admin-commercial-user-economics-top-users-table-wrapper">
          <Table data-testid="admin-commercial-user-economics-top-users-table">
            <TableHeader>
              <TableRow>
                <TableHead data-testid="admin-commercial-user-economics-top-users-head-email">User</TableHead>
                <TableHead data-testid="admin-commercial-user-economics-top-users-head-ltv">LTV</TableHead>
                <TableHead data-testid="admin-commercial-user-economics-top-users-head-revenue">Revenue Contribution</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(userEconomics.top_users || []).map((row, idx) => (
                <TableRow key={`${row.user_id}-${idx}`} data-testid={`admin-commercial-user-economics-top-user-row-${idx}`}>
                  <TableCell data-testid={`admin-commercial-user-economics-top-user-email-${idx}`}>{row.user_email || row.user_id}</TableCell>
                  <TableCell data-testid={`admin-commercial-user-economics-top-user-ltv-${idx}`}>{formatUsd(row.ltv_usd)}</TableCell>
                  <TableCell data-testid={`admin-commercial-user-economics-top-user-revenue-${idx}`}>{formatUsd(row.revenue_contribution_usd)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </section>

      <section className="border border-black/30 bg-orange-100 p-4" data-testid="admin-commercial-pnl-analytics-panel">
        <p className="text-xs uppercase tracking-widest" data-testid="admin-commercial-pnl-analytics-title">PnL Analytics</p>
        <div className="mt-3 grid gap-3 md:grid-cols-4" data-testid="admin-commercial-pnl-analytics-grid">
          <div data-testid="admin-commercial-pnl-analytics-margin-value">Net/Gross %: {pnlAnalytics.margin.toFixed(2)}%</div>
          <div data-testid="admin-commercial-pnl-analytics-realized-share-value">Realized Pay %: {pnlAnalytics.realizedShare.toFixed(2)}%</div>
          <div data-testid="admin-commercial-pnl-analytics-unrealized-share-value">Unrealized Pay %: {pnlAnalytics.unrealizedShare.toFixed(2)}%</div>
          <div data-testid="admin-commercial-pnl-analytics-delta-value">Gross-Net Delta: {formatUsd(pnlAnalytics.grossToNetDelta)}</div>
        </div>
      </section>

      <section className="border border-black/30 bg-orange-100 p-4" data-testid="admin-commercial-risk-exposure-panel">
        <p className="text-xs uppercase tracking-widest" data-testid="admin-commercial-risk-exposure-title">Risk & Exposure</p>
        <div className="mt-3 grid gap-3 md:grid-cols-3" data-testid="admin-commercial-risk-exposure-kpi-grid">
          <div data-testid="admin-commercial-risk-exposure-open-position-value">Open Position: {riskSummary.open_position_count || 0}</div>
          <div data-testid="admin-commercial-risk-exposure-drift-count-value">Drift Count: {riskSummary.high_drift_reconciliation_count || 0}</div>
          <div data-testid="admin-commercial-risk-exposure-kill-switch-value">Kill Switch: {riskSummary.kill_switch_enabled ? "Açık" : "Kapalı"}</div>
        </div>
      </section>

      <section className="border border-black/30 bg-orange-100 p-4" data-testid="admin-commercial-usage-analytics-panel">
        <p className="text-xs uppercase tracking-widest" data-testid="admin-commercial-usage-analytics-title">Usage Analytics</p>
        <div className="mt-3 grid gap-3 md:grid-cols-4" data-testid="admin-commercial-usage-analytics-kpi-grid">
          <div data-testid="admin-commercial-usage-analytics-total-trades-value">Trades: {usageAnalytics.total_trades || 0}</div>
          <div data-testid="admin-commercial-usage-analytics-unique-users-value">Unique User: {usageAnalytics.unique_users || 0}</div>
          <div data-testid="admin-commercial-usage-analytics-unique-symbols-value">Unique Symbol: {usageAnalytics.unique_symbols || 0}</div>
          <div data-testid="admin-commercial-usage-analytics-notional-value">Notional: {formatUsd(usageAnalytics.total_notional_usd)}</div>
        </div>
      </section>

      <section className="border border-black/30 bg-orange-100 p-4" data-testid="admin-commercial-data-quality-panel">
        <p className="text-xs uppercase tracking-widest" data-testid="admin-commercial-data-quality-title">Data Quality</p>
        <div className="mt-3 grid gap-3 md:grid-cols-3" data-testid="admin-commercial-data-quality-grid">
          <div data-testid="admin-commercial-data-quality-status-value">Status: {dataQuality.status || "-"}</div>
          <div data-testid="admin-commercial-data-quality-empty-data-value">Empty Data: {dataQuality.empty_data ? "Evet" : "Hayır"}</div>
          <div data-testid="admin-commercial-data-quality-freshness-value">Freshness: {dataQuality.freshness_seconds ?? "-"}</div>
        </div>
      </section>
    </section>
  );
};
