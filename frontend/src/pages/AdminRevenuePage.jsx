import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

export const AdminRevenuePage = () => {
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState(null);
  const [filters, setFilters] = useState({
    environment: "live",
    start_date: "",
    end_date: "",
    user_email: "",
    symbol: "",
    top_limit: 10,
  });

  const loadSummary = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/admin/revenue/summary", {
        params: {
          environment: filters.environment,
          start_date: filters.start_date || undefined,
          end_date: filters.end_date || undefined,
          user_email: filters.user_email || undefined,
          symbol: filters.symbol ? filters.symbol.toUpperCase() : undefined,
          top_limit: filters.top_limit,
        },
      });
      setSummary(data || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Revenue summary alınamadı");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  const dailyRows = useMemo(() => summary?.daily_revenue || [], [summary]);
  const maxDaily = useMemo(() => {
    const max = dailyRows.reduce((acc, row) => Math.max(acc, Number(row.total_revenue_usd || 0)), 0);
    return max > 0 ? max : 1;
  }, [dailyRows]);

  return (
    <section className="space-y-5" data-testid="admin-revenue-page">
      <header className="border border-black/30 bg-orange-300 p-4" data-testid="admin-revenue-header">
        <h1 className="text-4xl font-black uppercase" data-testid="admin-revenue-title">Revenue Engine</h1>
        <p className="text-sm text-black/80" data-testid="admin-revenue-subtitle">Total revenue, günlük dağılım, top users/symbols.</p>
      </header>

      <section className="grid gap-2 rounded border border-black/30 bg-orange-100 p-3 md:grid-cols-6" data-testid="admin-revenue-filters">
        <select
          className="h-10 rounded border px-2"
          value={filters.environment}
          onChange={(event) => setFilters((prev) => ({ ...prev, environment: event.target.value }))}
          data-testid="admin-revenue-filter-environment-select"
        >
          <option value="live">live</option>
          <option value="live">live</option>
        </select>
        <Input type="datetime-local" value={filters.start_date} onChange={(event) => setFilters((prev) => ({ ...prev, start_date: event.target.value }))} data-testid="admin-revenue-filter-start-date-input" />
        <Input type="datetime-local" value={filters.end_date} onChange={(event) => setFilters((prev) => ({ ...prev, end_date: event.target.value }))} data-testid="admin-revenue-filter-end-date-input" />
        <Input placeholder="user_email" value={filters.user_email} onChange={(event) => setFilters((prev) => ({ ...prev, user_email: event.target.value }))} data-testid="admin-revenue-filter-user-email-input" />
        <Input placeholder="symbol" value={filters.symbol} onChange={(event) => setFilters((prev) => ({ ...prev, symbol: event.target.value }))} data-testid="admin-revenue-filter-symbol-input" />
        <div className="flex gap-2" data-testid="admin-revenue-filter-actions">
          <Input type="number" min={1} max={50} value={filters.top_limit} onChange={(event) => setFilters((prev) => ({ ...prev, top_limit: Number(event.target.value || 10) }))} data-testid="admin-revenue-filter-top-limit-input" />
          <Button onClick={loadSummary} data-testid="admin-revenue-filter-refresh-button">Yenile</Button>
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-2" data-testid="admin-revenue-cards-grid">
        <article className="rounded border border-black/30 bg-white p-3" data-testid="admin-revenue-total-card">
          <p className="text-xs uppercase" data-testid="admin-revenue-total-label">Total Revenue</p>
          <p className="text-2xl font-semibold" data-testid="admin-revenue-total-value">{Number(summary?.total_revenue_usd || 0).toFixed(6)} USD</p>
        </article>
        <article className="rounded border border-black/30 bg-white p-3" data-testid="admin-revenue-today-card">
          <p className="text-xs uppercase" data-testid="admin-revenue-today-label">Today Revenue</p>
          <p className="text-2xl font-semibold" data-testid="admin-revenue-today-value">{Number(summary?.today_revenue_usd || 0).toFixed(6)} USD</p>
        </article>
      </section>

      <section className="rounded border border-black/30 bg-white p-4" data-testid="admin-revenue-daily-graph-card">
        <h2 className="mb-2 text-lg font-semibold" data-testid="admin-revenue-daily-graph-title">Daily Revenue Graph</h2>
        <div className="space-y-2" data-testid="admin-revenue-daily-graph-list">
          {dailyRows.map((row) => (
            <div key={row.date} className="grid grid-cols-[120px_1fr_90px] items-center gap-2" data-testid={`admin-revenue-daily-row-${row.date}`}>
              <p className="text-xs" data-testid={`admin-revenue-daily-date-${row.date}`}>{row.date}</p>
              <div className="h-3 rounded bg-orange-100" data-testid={`admin-revenue-daily-bar-track-${row.date}`}>
                <div
                  className="h-3 rounded bg-orange-500"
                  style={{ width: `${Math.max(2, (Number(row.total_revenue_usd || 0) / maxDaily) * 100)}%` }}
                  data-testid={`admin-revenue-daily-bar-fill-${row.date}`}
                />
              </div>
              <p className="text-right text-xs" data-testid={`admin-revenue-daily-value-${row.date}`}>{Number(row.total_revenue_usd || 0).toFixed(4)}</p>
            </div>
          ))}
          {!dailyRows.length && <p className="text-xs text-slate-500" data-testid="admin-revenue-daily-empty">Günlük revenue verisi yok</p>}
        </div>
      </section>

      <section className="grid gap-3 lg:grid-cols-2" data-testid="admin-revenue-tables-grid">
        <article className="rounded border border-black/30 bg-white p-3" data-testid="admin-revenue-top-users-card">
          <h2 className="mb-2 text-lg font-semibold" data-testid="admin-revenue-top-users-title">Top Users</h2>
          <Table data-testid="admin-revenue-top-users-table">
            <TableHeader>
              <TableRow>
                <TableHead data-testid="admin-revenue-top-users-head-email">Email</TableHead>
                <TableHead data-testid="admin-revenue-top-users-head-user-id">User ID</TableHead>
                <TableHead data-testid="admin-revenue-top-users-head-revenue">Revenue</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(summary?.top_users || []).map((row) => (
                <TableRow key={`${row.user_id}-${row.email}`} data-testid={`admin-revenue-top-user-row-${row.user_id}`}>
                  <TableCell data-testid={`admin-revenue-top-user-email-${row.user_id}`}>{row.email}</TableCell>
                  <TableCell data-testid={`admin-revenue-top-user-id-${row.user_id}`}>{row.user_id}</TableCell>
                  <TableCell data-testid={`admin-revenue-top-user-revenue-${row.user_id}`}>{Number(row.revenue_usd || 0).toFixed(6)}</TableCell>
                </TableRow>
              ))}
              {!(summary?.top_users || []).length && (
                <TableRow>
                  <TableCell colSpan={3} className="text-center text-sm text-slate-500" data-testid="admin-revenue-top-users-empty">Kayıt yok</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </article>

        <article className="rounded border border-black/30 bg-white p-3" data-testid="admin-revenue-top-symbols-card">
          <h2 className="mb-2 text-lg font-semibold" data-testid="admin-revenue-top-symbols-title">Top Symbols</h2>
          <Table data-testid="admin-revenue-top-symbols-table">
            <TableHeader>
              <TableRow>
                <TableHead data-testid="admin-revenue-top-symbols-head-symbol">Symbol</TableHead>
                <TableHead data-testid="admin-revenue-top-symbols-head-revenue">Revenue</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(summary?.top_symbols || []).map((row) => (
                <TableRow key={row.symbol} data-testid={`admin-revenue-top-symbol-row-${row.symbol}`}>
                  <TableCell data-testid={`admin-revenue-top-symbol-name-${row.symbol}`}>{row.symbol}</TableCell>
                  <TableCell data-testid={`admin-revenue-top-symbol-revenue-${row.symbol}`}>{Number(row.revenue_usd || 0).toFixed(6)}</TableCell>
                </TableRow>
              ))}
              {!(summary?.top_symbols || []).length && (
                <TableRow>
                  <TableCell colSpan={2} className="text-center text-sm text-slate-500" data-testid="admin-revenue-top-symbols-empty">Kayıt yok</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </article>
      </section>

      {loading && <p className="text-xs text-slate-500" data-testid="admin-revenue-loading-indicator">Yükleniyor...</p>}
    </section>
  );
};
