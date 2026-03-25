import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

export const AdminUserEconomicsPage = () => {
  const [loading, setLoading] = useState(false);
  const [payload, setPayload] = useState(null);
  const [filters, setFilters] = useState({
    environment: "live",
    start_date: "",
    end_date: "",
    user_email: "",
    symbol: "",
    churn_inactive_days: 30,
    cohort_month: "",
    top_limit: 10,
  });

  const fetchEconomics = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/admin/users/economics", {
        params: {
          environment: filters.environment,
          start_date: filters.start_date || undefined,
          end_date: filters.end_date || undefined,
          user_email: filters.user_email || undefined,
          symbol: filters.symbol ? filters.symbol.toUpperCase() : undefined,
          churn_inactive_days: filters.churn_inactive_days,
          cohort_month: filters.cohort_month || undefined,
          top_limit: filters.top_limit,
        },
      });
      setPayload(data || null);
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
          <Button onClick={fetchEconomics} data-testid="admin-user-economics-filter-refresh-button">Yenile</Button>
        </div>
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
