import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

export const AdminUserEconomicsPage = () => {
  const [loading, setLoading] = useState(false);
  const [payload, setPayload] = useState(null);
  const [retentionPayload, setRetentionPayload] = useState(null);
  const [segmentPayload, setSegmentPayload] = useState(null);
  const [snapshotTrendPayload, setSnapshotTrendPayload] = useState(null);
  const [snapshotRunning, setSnapshotRunning] = useState(false);
  const [filters, setFilters] = useState({
    environment: "live",
    start_date: "",
    end_date: "",
    user_email: "",
    symbol: "",
    churn_inactive_days: 30,
    cohort_month: "",
    top_limit: 10,
    retention_granularity: "weekly",
    retention_lookback: 12,
    snapshot_type: "daily",
  });

  const fetchEconomics = useCallback(async () => {
    setLoading(true);
    try {
      const commonParams = {
        environment: filters.environment,
        start_date: filters.start_date || undefined,
        end_date: filters.end_date || undefined,
        user_email: filters.user_email || undefined,
        symbol: filters.symbol ? filters.symbol.toUpperCase() : undefined,
        churn_inactive_days: filters.churn_inactive_days,
        cohort_month: filters.cohort_month || undefined,
        top_limit: filters.top_limit,
      };

      const [economicsRes, retentionRes, segmentRes, snapshotTrendRes] = await Promise.all([
        apiClient.get("/admin/users/economics", { params: commonParams }),
        apiClient.get("/admin/users/economics/retention-trend", {
          params: {
            environment: filters.environment,
            granularity: filters.retention_granularity,
            lookback_periods: filters.retention_lookback,
          },
        }),
        apiClient.get("/admin/users/economics/segment-profitability", {
          params: {
            environment: filters.environment,
            churn_inactive_days: filters.churn_inactive_days,
            top_limit: filters.top_limit,
          },
        }),
        apiClient.get("/admin/users/economics/snapshots/trend", {
          params: {
            environment: filters.environment,
            snapshot_type: filters.snapshot_type,
            limit: 30,
          },
        }),
      ]);

      setPayload(economicsRes?.data || null);
      setRetentionPayload(retentionRes?.data || null);
      setSegmentPayload(segmentRes?.data || null);
      setSnapshotTrendPayload(snapshotTrendRes?.data || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "User economics alınamadı");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    fetchEconomics();
  }, [fetchEconomics]);

  const kpis = payload?.kpis || {};
  const retentionPoints = useMemo(() => retentionPayload?.points || [], [retentionPayload]);
  const segmentCards = segmentPayload?.segment_cards || [];
  const retentionMax = useMemo(
    () => Math.max(1, retentionPoints.reduce((acc, item) => Math.max(acc, Number(item.retention_rate_pct || 0)), 0)),
    [retentionPoints],
  );

  const runSnapshot = async () => {
    setSnapshotRunning(true);
    try {
      await apiClient.post("/admin/users/economics/snapshots/run", null, {
        params: {
          environment: filters.environment,
          snapshot_type: filters.snapshot_type,
          churn_inactive_days: filters.churn_inactive_days,
        },
      });
      toast.success("Snapshot oluşturuldu");
      fetchEconomics();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Snapshot oluşturulamadı");
    } finally {
      setSnapshotRunning(false);
    }
  };

  const exportEconomics = async (format) => {
    try {
      const response = await apiClient.get(`/admin/users/economics/export.${format}`, {
        params: {
          environment: filters.environment,
          start_date: filters.start_date || undefined,
          end_date: filters.end_date || undefined,
          user_email: filters.user_email || undefined,
          symbol: filters.symbol ? filters.symbol.toUpperCase() : undefined,
          churn_inactive_days: filters.churn_inactive_days,
          cohort_month: filters.cohort_month || undefined,
          top_limit: 200,
        },
        responseType: "blob",
      });
      const blob = new Blob([response.data]);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `user_economics_export.${format}`;
      link.click();
      window.URL.revokeObjectURL(url);
      toast.success(`${format.toUpperCase()} export hazır`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Export başarısız");
    }
  };

  return (
    <section className="space-y-5" data-testid="admin-user-economics-page">
      <header className="rounded border border-black/30 bg-cyan-100 p-4" data-testid="admin-user-economics-header">
        <h1 className="text-4xl font-black uppercase" data-testid="admin-user-economics-title">User Economics</h1>
        <p className="text-sm text-black/70" data-testid="admin-user-economics-subtitle">LTV, ARPU/ARPPU, churn, cohort ve user bazlı kârlılık görünümü.</p>
      </header>

      <section className="grid gap-2 rounded border border-black/30 bg-white p-3 md:grid-cols-4 lg:grid-cols-8" data-testid="admin-user-economics-filter-panel">
        <select className="h-10 rounded border px-2" value={filters.environment} onChange={(event) => setFilters((prev) => ({ ...prev, environment: event.target.value }))} data-testid="admin-user-economics-filter-environment-select">
          <option value="live">live</option>
          <option value="testnet">testnet</option>
        </select>
        <Input type="datetime-local" value={filters.start_date} onChange={(event) => setFilters((prev) => ({ ...prev, start_date: event.target.value }))} data-testid="admin-user-economics-filter-start-date-input" />
        <Input type="datetime-local" value={filters.end_date} onChange={(event) => setFilters((prev) => ({ ...prev, end_date: event.target.value }))} data-testid="admin-user-economics-filter-end-date-input" />
        <Input placeholder="user_email" value={filters.user_email} onChange={(event) => setFilters((prev) => ({ ...prev, user_email: event.target.value }))} data-testid="admin-user-economics-filter-user-email-input" />
        <Input placeholder="symbol" value={filters.symbol} onChange={(event) => setFilters((prev) => ({ ...prev, symbol: event.target.value }))} data-testid="admin-user-economics-filter-symbol-input" />
        <Input placeholder="cohort YYYY-MM" value={filters.cohort_month} onChange={(event) => setFilters((prev) => ({ ...prev, cohort_month: event.target.value }))} data-testid="admin-user-economics-filter-cohort-input" />
        <Input type="number" min={1} max={365} value={filters.churn_inactive_days} onChange={(event) => setFilters((prev) => ({ ...prev, churn_inactive_days: Number(event.target.value || 30) }))} data-testid="admin-user-economics-filter-churn-days-input" />
        <div className="flex gap-2" data-testid="admin-user-economics-filter-actions">
          <Input type="number" min={1} max={100} value={filters.top_limit} onChange={(event) => setFilters((prev) => ({ ...prev, top_limit: Number(event.target.value || 10) }))} data-testid="admin-user-economics-filter-top-limit-input" />
          <select className="h-10 rounded border px-2" value={filters.retention_granularity} onChange={(event) => setFilters((prev) => ({ ...prev, retention_granularity: event.target.value }))} data-testid="admin-user-economics-filter-retention-granularity-select">
            <option value="weekly">weekly</option>
            <option value="monthly">monthly</option>
          </select>
          <Input type="number" min={1} max={104} value={filters.retention_lookback} onChange={(event) => setFilters((prev) => ({ ...prev, retention_lookback: Number(event.target.value || 12) }))} data-testid="admin-user-economics-filter-retention-lookback-input" />
          <select className="h-10 rounded border px-2" value={filters.snapshot_type} onChange={(event) => setFilters((prev) => ({ ...prev, snapshot_type: event.target.value }))} data-testid="admin-user-economics-filter-snapshot-type-select">
            <option value="daily">daily</option>
            <option value="weekly">weekly</option>
          </select>
          <Button onClick={fetchEconomics} data-testid="admin-user-economics-filter-refresh-button">Yenile</Button>
        </div>
      </section>

      <section className="flex flex-wrap gap-2" data-testid="admin-user-economics-actions-row">
        <Button variant="outline" onClick={() => exportEconomics("csv")} data-testid="admin-user-economics-export-csv-button">Export CSV</Button>
        <Button variant="outline" onClick={() => exportEconomics("xlsx")} data-testid="admin-user-economics-export-xlsx-button">Export XLSX</Button>
        <Button onClick={runSnapshot} disabled={snapshotRunning} data-testid="admin-user-economics-run-snapshot-button">{snapshotRunning ? "Snapshot çalışıyor" : "Snapshot Çalıştır"}</Button>
      </section>

      <section className="grid gap-2 md:grid-cols-4" data-testid="admin-user-economics-kpi-cards-grid">
        <article className="rounded border border-black/30 bg-white p-3" data-testid="admin-user-economics-kpi-ltv-card"><p className="text-xs">AVG LTV</p><p className="text-xl font-semibold" data-testid="admin-user-economics-kpi-ltv-value">{Number(kpis.avg_ltv_usd || 0).toFixed(6)}</p></article>
        <article className="rounded border border-black/30 bg-white p-3" data-testid="admin-user-economics-kpi-arpu-card"><p className="text-xs">ARPU</p><p className="text-xl font-semibold" data-testid="admin-user-economics-kpi-arpu-value">{Number(kpis.arpu_usd || 0).toFixed(6)}</p></article>
        <article className="rounded border border-black/30 bg-white p-3" data-testid="admin-user-economics-kpi-arppu-card"><p className="text-xs">ARPPU</p><p className="text-xl font-semibold" data-testid="admin-user-economics-kpi-arppu-value">{Number(kpis.arppu_usd || 0).toFixed(6)}</p></article>
        <article className="rounded border border-black/30 bg-white p-3" data-testid="admin-user-economics-kpi-churn-card"><p className="text-xs">CHURN %</p><p className="text-xl font-semibold" data-testid="admin-user-economics-kpi-churn-value">{Number(kpis.churn_rate_pct || 0).toFixed(3)}</p></article>
      </section>

      <section className="grid gap-3 lg:grid-cols-2" data-testid="admin-user-economics-main-tables-grid">
        <article className="rounded border border-black/30 bg-white p-3" data-testid="admin-user-economics-top-users-card">
          <h2 className="mb-2 text-lg font-semibold" data-testid="admin-user-economics-top-users-title">Top Users</h2>
          <Table data-testid="admin-user-economics-top-users-table">
            <TableHeader>
              <TableRow>
                <TableHead data-testid="admin-user-economics-top-users-head-email">Email</TableHead>
                <TableHead data-testid="admin-user-economics-top-users-head-revenue">Revenue</TableHead>
                <TableHead data-testid="admin-user-economics-top-users-head-pnl">Realized PnL</TableHead>
                <TableHead data-testid="admin-user-economics-top-users-head-inactive-days">Inactive Days</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(payload?.top_users || []).map((row) => (
                <TableRow key={row.user_id} data-testid={`admin-user-economics-top-user-row-${row.user_id}`}>
                  <TableCell data-testid={`admin-user-economics-top-user-email-${row.user_id}`}>{row.email}</TableCell>
                  <TableCell data-testid={`admin-user-economics-top-user-revenue-${row.user_id}`}>{Number(row.revenue_contribution_usd || 0).toFixed(6)}</TableCell>
                  <TableCell data-testid={`admin-user-economics-top-user-pnl-${row.user_id}`}>{Number(row.realized_pnl_usd || 0).toFixed(6)}</TableCell>
                  <TableCell data-testid={`admin-user-economics-top-user-inactive-${row.user_id}`}>{row.inactive_days}</TableCell>
                </TableRow>
              ))}
              {!(payload?.top_users || []).length && <TableRow><TableCell colSpan={4} className="text-center text-sm text-slate-500" data-testid="admin-user-economics-top-users-empty">Kayıt yok</TableCell></TableRow>}
            </TableBody>
          </Table>
        </article>

        <article className="rounded border border-black/30 bg-white p-3" data-testid="admin-user-economics-churn-list-card">
          <h2 className="mb-2 text-lg font-semibold" data-testid="admin-user-economics-churn-list-title">Churn Listesi</h2>
          <Table data-testid="admin-user-economics-churn-list-table">
            <TableHeader>
              <TableRow>
                <TableHead data-testid="admin-user-economics-churn-list-head-email">Email</TableHead>
                <TableHead data-testid="admin-user-economics-churn-list-head-inactive-days">Inactive Days</TableHead>
                <TableHead data-testid="admin-user-economics-churn-list-head-cohort">Cohort</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(payload?.churn_list || []).map((row) => (
                <TableRow key={row.user_id} data-testid={`admin-user-economics-churn-row-${row.user_id}`}>
                  <TableCell data-testid={`admin-user-economics-churn-email-${row.user_id}`}>{row.email}</TableCell>
                  <TableCell data-testid={`admin-user-economics-churn-inactive-${row.user_id}`}>{row.inactive_days}</TableCell>
                  <TableCell data-testid={`admin-user-economics-churn-cohort-${row.user_id}`}>{row.cohort_month || "-"}</TableCell>
                </TableRow>
              ))}
              {!(payload?.churn_list || []).length && <TableRow><TableCell colSpan={3} className="text-center text-sm text-slate-500" data-testid="admin-user-economics-churn-empty">Kayıt yok</TableCell></TableRow>}
            </TableBody>
          </Table>
        </article>
      </section>

      <section className="rounded border border-black/30 bg-white p-3" data-testid="admin-user-economics-retention-trend-card">
        <h2 className="mb-2 text-lg font-semibold" data-testid="admin-user-economics-retention-trend-title">Retention Trend</h2>
        <div className="space-y-2" data-testid="admin-user-economics-retention-trend-list">
          {retentionPoints.map((point) => (
            <div key={`${point.cohort}-${point.period}`} className="grid grid-cols-[180px_1fr_90px] items-center gap-2" data-testid={`admin-user-economics-retention-trend-row-${point.cohort}-${point.period}`}>
              <p className="text-xs" data-testid={`admin-user-economics-retention-trend-label-${point.cohort}-${point.period}`}>{point.cohort} → {point.period}</p>
              <div className="h-3 rounded bg-cyan-100" data-testid={`admin-user-economics-retention-trend-bar-track-${point.cohort}-${point.period}`}>
                <div className="h-3 rounded bg-cyan-500" style={{ width: `${Math.max(2, (Number(point.retention_rate_pct || 0) / retentionMax) * 100)}%` }} data-testid={`admin-user-economics-retention-trend-bar-fill-${point.cohort}-${point.period}`} />
              </div>
              <p className="text-right text-xs" data-testid={`admin-user-economics-retention-trend-value-${point.cohort}-${point.period}`}>{Number(point.retention_rate_pct || 0).toFixed(2)}%</p>
            </div>
          ))}
          {!retentionPoints.length && <p className="text-xs text-slate-500" data-testid="admin-user-economics-retention-trend-empty">Retention trend verisi yok</p>}
        </div>
      </section>

      <section className="rounded border border-black/30 bg-white p-3" data-testid="admin-user-economics-segment-cards-card">
        <h2 className="mb-2 text-lg font-semibold" data-testid="admin-user-economics-segment-cards-title">Segment Profitability</h2>
        <div className="grid gap-2 md:grid-cols-5" data-testid="admin-user-economics-segment-cards-grid">
          {segmentCards.map((card) => (
            <article key={card.segment} className="rounded border border-black/20 p-2" data-testid={`admin-user-economics-segment-card-${card.segment}`}>
              <p className="text-xs uppercase" data-testid={`admin-user-economics-segment-card-segment-${card.segment}`}>{card.segment}</p>
              <p className="text-sm font-semibold" data-testid={`admin-user-economics-segment-card-users-${card.segment}`}>users: {card.users}</p>
              <p className="text-xs" data-testid={`admin-user-economics-segment-card-revenue-${card.segment}`}>rev: {Number(card.total_revenue_usd || 0).toFixed(6)}</p>
              <p className="text-xs" data-testid={`admin-user-economics-segment-card-pnl-${card.segment}`}>pnl: {Number(card.total_realized_pnl_usd || 0).toFixed(6)}</p>
            </article>
          ))}
          {!segmentCards.length && <p className="text-xs text-slate-500" data-testid="admin-user-economics-segment-cards-empty">Segment kartı yok</p>}
        </div>
      </section>

      <section className="grid gap-3 lg:grid-cols-2" data-testid="admin-user-economics-reengagement-grid">
        <article className="rounded border border-black/30 bg-white p-3" data-testid="admin-user-economics-churn-risk-card">
          <h2 className="mb-2 text-lg font-semibold" data-testid="admin-user-economics-churn-risk-title">Churn Risk</h2>
          <Table data-testid="admin-user-economics-churn-risk-table">
            <TableHeader><TableRow><TableHead data-testid="admin-user-economics-churn-risk-head-email">Email</TableHead><TableHead data-testid="admin-user-economics-churn-risk-head-inactive">Inactive</TableHead><TableHead data-testid="admin-user-economics-churn-risk-head-revenue">Revenue</TableHead></TableRow></TableHeader>
            <TableBody>
              {(segmentPayload?.churn_risk_list || []).map((row) => (
                <TableRow key={row.user_id} data-testid={`admin-user-economics-churn-risk-row-${row.user_id}`}>
                  <TableCell data-testid={`admin-user-economics-churn-risk-email-${row.user_id}`}>{row.email}</TableCell>
                  <TableCell data-testid={`admin-user-economics-churn-risk-inactive-${row.user_id}`}>{row.inactive_days}</TableCell>
                  <TableCell data-testid={`admin-user-economics-churn-risk-revenue-${row.user_id}`}>{Number(row.revenue_contribution_usd || 0).toFixed(6)}</TableCell>
                </TableRow>
              ))}
              {!(segmentPayload?.churn_risk_list || []).length && <TableRow><TableCell colSpan={3} className="text-center text-sm text-slate-500" data-testid="admin-user-economics-churn-risk-empty">Kayıt yok</TableCell></TableRow>}
            </TableBody>
          </Table>
        </article>
        <article className="rounded border border-black/30 bg-white p-3" data-testid="admin-user-economics-reengagement-list-card">
          <h2 className="mb-2 text-lg font-semibold" data-testid="admin-user-economics-reengagement-list-title">Re-engagement List</h2>
          <Table data-testid="admin-user-economics-reengagement-list-table">
            <TableHeader><TableRow><TableHead data-testid="admin-user-economics-reengagement-head-email">Email</TableHead><TableHead data-testid="admin-user-economics-reengagement-head-inactive">Inactive</TableHead><TableHead data-testid="admin-user-economics-reengagement-head-revenue">Revenue</TableHead></TableRow></TableHeader>
            <TableBody>
              {(segmentPayload?.reengagement_list || []).map((row) => (
                <TableRow key={row.user_id} data-testid={`admin-user-economics-reengagement-row-${row.user_id}`}>
                  <TableCell data-testid={`admin-user-economics-reengagement-email-${row.user_id}`}>{row.email}</TableCell>
                  <TableCell data-testid={`admin-user-economics-reengagement-inactive-${row.user_id}`}>{row.inactive_days}</TableCell>
                  <TableCell data-testid={`admin-user-economics-reengagement-revenue-${row.user_id}`}>{Number(row.revenue_contribution_usd || 0).toFixed(6)}</TableCell>
                </TableRow>
              ))}
              {!(segmentPayload?.reengagement_list || []).length && <TableRow><TableCell colSpan={3} className="text-center text-sm text-slate-500" data-testid="admin-user-economics-reengagement-empty">Kayıt yok</TableCell></TableRow>}
            </TableBody>
          </Table>
        </article>
      </section>

      <section className="rounded border border-black/30 bg-white p-3" data-testid="admin-user-economics-snapshot-trend-card">
        <h2 className="mb-2 text-lg font-semibold" data-testid="admin-user-economics-snapshot-trend-title">Snapshot Trend</h2>
        <Table data-testid="admin-user-economics-snapshot-trend-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="admin-user-economics-snapshot-trend-head-date">Date</TableHead>
              <TableHead data-testid="admin-user-economics-snapshot-trend-head-users">Users</TableHead>
              <TableHead data-testid="admin-user-economics-snapshot-trend-head-churn">Churn%</TableHead>
              <TableHead data-testid="admin-user-economics-snapshot-trend-head-revenue">Revenue</TableHead>
              <TableHead data-testid="admin-user-economics-snapshot-trend-head-ltv">Avg LTV</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(snapshotTrendPayload?.points || []).map((row) => (
              <TableRow key={row.snapshot_date} data-testid={`admin-user-economics-snapshot-trend-row-${row.snapshot_date}`}>
                <TableCell data-testid={`admin-user-economics-snapshot-trend-date-${row.snapshot_date}`}>{row.snapshot_date}</TableCell>
                <TableCell data-testid={`admin-user-economics-snapshot-trend-users-${row.snapshot_date}`}>{row.users}</TableCell>
                <TableCell data-testid={`admin-user-economics-snapshot-trend-churn-${row.snapshot_date}`}>{Number(row.churn_rate_pct || 0).toFixed(3)}</TableCell>
                <TableCell data-testid={`admin-user-economics-snapshot-trend-revenue-${row.snapshot_date}`}>{Number(row.total_revenue_usd || 0).toFixed(6)}</TableCell>
                <TableCell data-testid={`admin-user-economics-snapshot-trend-ltv-${row.snapshot_date}`}>{Number(row.avg_ltv_usd || 0).toFixed(6)}</TableCell>
              </TableRow>
            ))}
            {!(snapshotTrendPayload?.points || []).length && <TableRow><TableCell colSpan={5} className="text-center text-sm text-slate-500" data-testid="admin-user-economics-snapshot-trend-empty">Snapshot trend yok</TableCell></TableRow>}
          </TableBody>
        </Table>
      </section>

      <section className="rounded border border-black/30 bg-white p-3" data-testid="admin-user-economics-cohort-card">
        <h2 className="mb-2 text-lg font-semibold" data-testid="admin-user-economics-cohort-title">Cohort Görünümü</h2>
        <Table data-testid="admin-user-economics-cohort-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="admin-user-economics-cohort-head-month">Cohort</TableHead>
              <TableHead data-testid="admin-user-economics-cohort-head-users">Users</TableHead>
              <TableHead data-testid="admin-user-economics-cohort-head-paying-users">Paying</TableHead>
              <TableHead data-testid="admin-user-economics-cohort-head-churned-users">Churned</TableHead>
              <TableHead data-testid="admin-user-economics-cohort-head-total-revenue">Total Revenue</TableHead>
              <TableHead data-testid="admin-user-economics-cohort-head-avg-ltv">Avg LTV</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(payload?.cohorts || []).map((row) => (
              <TableRow key={row.cohort_month} data-testid={`admin-user-economics-cohort-row-${row.cohort_month}`}>
                <TableCell data-testid={`admin-user-economics-cohort-month-${row.cohort_month}`}>{row.cohort_month}</TableCell>
                <TableCell data-testid={`admin-user-economics-cohort-users-${row.cohort_month}`}>{row.users}</TableCell>
                <TableCell data-testid={`admin-user-economics-cohort-paying-${row.cohort_month}`}>{row.paying_users}</TableCell>
                <TableCell data-testid={`admin-user-economics-cohort-churned-${row.cohort_month}`}>{row.churned_users}</TableCell>
                <TableCell data-testid={`admin-user-economics-cohort-revenue-${row.cohort_month}`}>{Number(row.total_revenue_usd || 0).toFixed(6)}</TableCell>
                <TableCell data-testid={`admin-user-economics-cohort-ltv-${row.cohort_month}`}>{Number(row.avg_ltv_usd || 0).toFixed(6)}</TableCell>
              </TableRow>
            ))}
            {!(payload?.cohorts || []).length && <TableRow><TableCell colSpan={6} className="text-center text-sm text-slate-500" data-testid="admin-user-economics-cohort-empty">Cohort verisi yok</TableCell></TableRow>}
          </TableBody>
        </Table>
      </section>

      {loading && <p className="text-xs text-slate-500" data-testid="admin-user-economics-loading-indicator">Yükleniyor...</p>}
    </section>
  );
};
