import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";

export const AdminCommercialOpsPage = () => {
  const { user } = useAuth();
  const [isLoading, setIsLoading] = useState(true);
  const [users, setUsers] = useState([]);
  const [usage, setUsage] = useState([]);
  const [pnlData, setPnlData] = useState(null);
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const [usageFilters, setUsageFilters] = useState({ user_id: "", symbol: "", status: "all" });

  const isSuperAdmin = user?.role === "super_admin";

  const loadAll = useCallback(async () => {
    setIsLoading(true);
    try {
      const [usersRes, usageRes, pnlRes] = await Promise.all([
        apiClient.get("/admin/users", { params: { scope: "user", status: "all", limit: 300 } }),
        apiClient.get("/admin/commercial/usage-logs", { params: { limit: 120 } }),
        apiClient.get("/admin/commercial/total-pnl"),
      ]);
      setUsers(usersRes.data || []);
      setUsage(usageRes.data?.items || []);
      setPnlData(pnlRes.data || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Ticari panel verisi alınamadı");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isSuperAdmin) {
      loadAll();
    }
  }, [isSuperAdmin, loadAll]);

  const refreshUsage = async () => {
    try {
      const { data } = await apiClient.get("/admin/commercial/usage-logs", {
        params: {
          user_id: usageFilters.user_id || undefined,
          symbol: usageFilters.symbol ? usageFilters.symbol.toUpperCase() : undefined,
          status: usageFilters.status,
          limit: 200,
        },
      });
      setUsage(data?.items || []);
      toast.success("Usage logs yenilendi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Usage logs alınamadı");
    }
  };

  const updateStatus = async (row) => {
    const nextStatus = row.status === "active" ? "disabled" : "active";
    try {
      await apiClient.patch(`/admin/users/${row.id}/status`, { status: nextStatus });
      toast.success("Kullanıcı durumu güncellendi");
      await loadAll();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Durum güncellenemedi");
    }
  };

  const updateRole = async (row, nextRole) => {
    try {
      await apiClient.patch(`/admin/users/${row.id}/role`, { role: nextRole });
      toast.success("Rol güncellendi");
      await loadAll();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Rol güncellenemedi");
    }
  };

  const exportExcel = async () => {
    try {
      const response = await apiClient.get("/admin/commercial/monthly-pnl/export", {
        params: { month },
        responseType: "blob",
      });
      const blobUrl = window.URL.createObjectURL(new Blob([response.data]));
      const anchor = document.createElement("a");
      anchor.href = blobUrl;
      anchor.download = `monthly_pnl_${month}.xlsx`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(blobUrl);
      toast.success("Excel export indirildi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Excel export başarısız");
    }
  };

  const pnlSummary = useMemo(() => {
    const calendar = pnlData?.calendar_month?.summary || {};
    const last30 = pnlData?.last_30_days?.summary || {};
    return {
      calendarTotal: calendar.total_pnl ?? 0,
      last30Total: last30.total_pnl ?? 0,
      calendarUsers: calendar.user_count ?? 0,
      last30Users: last30.user_count ?? 0,
    };
  }, [pnlData]);

  if (!isSuperAdmin) {
    return (
      <section className="border border-rose-500/40 bg-rose-950/20 p-4" data-testid="admin-commercial-super-admin-only">
        <h2 className="text-xl font-bold" data-testid="admin-commercial-super-admin-only-title">Bu alan sadece super_admin için açık</h2>
        <p className="text-sm text-rose-200" data-testid="admin-commercial-super-admin-only-message">Kullanıcı bazlı finansal raporlar hassas veridir.</p>
      </section>
    );
  }

  return (
    <section className="space-y-4" data-testid="admin-commercial-ops-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="admin-commercial-ops-header">
        <h2 className="text-4xl font-black uppercase text-black" data-testid="admin-commercial-ops-title">Commercial Ops</h2>
        <p className="text-sm text-black/80" data-testid="admin-commercial-ops-description">User status, usage logs, total P&L ve aylık Excel export paneli.</p>
      </header>

      <div className="grid gap-3 md:grid-cols-4" data-testid="admin-commercial-pnl-cards-grid">
        <article className="border border-black/30 bg-orange-100 p-3" data-testid="admin-commercial-calendar-total-card">
          <p className="text-xs" data-testid="admin-commercial-calendar-total-label">Takvim Ayı Total P&L</p>
          <p className="text-xl font-semibold" data-testid="admin-commercial-calendar-total-value">{pnlSummary.calendarTotal}</p>
        </article>
        <article className="border border-black/30 bg-orange-100 p-3" data-testid="admin-commercial-last30-total-card">
          <p className="text-xs" data-testid="admin-commercial-last30-total-label">Son 30 Gün Total P&L</p>
          <p className="text-xl font-semibold" data-testid="admin-commercial-last30-total-value">{pnlSummary.last30Total}</p>
        </article>
        <article className="border border-black/30 bg-orange-100 p-3" data-testid="admin-commercial-calendar-users-card">
          <p className="text-xs" data-testid="admin-commercial-calendar-users-label">Takvim Ayı User Sayısı</p>
          <p className="text-xl font-semibold" data-testid="admin-commercial-calendar-users-value">{pnlSummary.calendarUsers}</p>
        </article>
        <article className="border border-black/30 bg-orange-100 p-3" data-testid="admin-commercial-last30-users-card">
          <p className="text-xs" data-testid="admin-commercial-last30-users-label">Son 30 Gün User Sayısı</p>
          <p className="text-xl font-semibold" data-testid="admin-commercial-last30-users-value">{pnlSummary.last30Users}</p>
        </article>
      </div>

      <section className="border border-black/30 bg-orange-100 p-4" data-testid="admin-commercial-export-panel">
        <p className="text-xs uppercase tracking-widest" data-testid="admin-commercial-export-title">Ay Sonu Excel Export</p>
        <div className="mt-2 flex flex-wrap items-center gap-2" data-testid="admin-commercial-export-controls">
          <Input type="month" value={month} onChange={(event) => setMonth(event.target.value)} data-testid="admin-commercial-export-month-input" />
          <Button onClick={exportExcel} data-testid="admin-commercial-export-button">Özet + User Sheet Excel İndir</Button>
          <Button variant="outline" onClick={loadAll} data-testid="admin-commercial-refresh-button">Tüm Paneli Yenile</Button>
        </div>
      </section>

      <section className="border border-black/30 bg-orange-100 p-4" data-testid="admin-commercial-users-panel">
        <p className="text-xs uppercase tracking-widest" data-testid="admin-commercial-users-title">User List & Status Yetki Kapsamı</p>
        {isLoading && <p className="text-sm" data-testid="admin-commercial-loading-users">Yükleniyor...</p>}
        <Table data-testid="admin-commercial-users-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="admin-commercial-users-head-email">Email</TableHead>
              <TableHead data-testid="admin-commercial-users-head-role">Role</TableHead>
              <TableHead data-testid="admin-commercial-users-head-status">Status</TableHead>
              <TableHead data-testid="admin-commercial-users-head-action">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.map((row) => (
              <TableRow key={row.id} data-testid={`admin-commercial-user-row-${row.id}`}>
                <TableCell data-testid={`admin-commercial-user-email-${row.id}`}>{row.email}</TableCell>
                <TableCell data-testid={`admin-commercial-user-role-cell-${row.id}`}>
                  <select
                    className="border border-black/40 bg-white px-2 py-1 text-xs"
                    value={row.role}
                    onChange={(event) => updateRole(row, event.target.value)}
                    data-testid={`admin-commercial-user-role-select-${row.id}`}
                  >
                    <option value="user">user</option>
                    <option value="admin">admin</option>
                  </select>
                </TableCell>
                <TableCell data-testid={`admin-commercial-user-status-${row.id}`}>{row.status}</TableCell>
                <TableCell data-testid={`admin-commercial-user-action-${row.id}`}>
                  <Button size="sm" onClick={() => updateStatus(row)} data-testid={`admin-commercial-user-toggle-status-button-${row.id}`}>
                    {row.status === "active" ? "Pasif Yap" : "Aktif Yap"}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>

      <section className="border border-black/30 bg-orange-100 p-4" data-testid="admin-commercial-usage-logs-panel">
        <p className="text-xs uppercase tracking-widest" data-testid="admin-commercial-usage-logs-title">Usage Logs</p>
        <div className="mt-2 grid gap-2 md:grid-cols-4" data-testid="admin-commercial-usage-logs-filters-grid">
          <Input placeholder="user_id" value={usageFilters.user_id} onChange={(event) => setUsageFilters((prev) => ({ ...prev, user_id: event.target.value }))} data-testid="admin-commercial-usage-logs-user-id-input" />
          <Input placeholder="symbol" value={usageFilters.symbol} onChange={(event) => setUsageFilters((prev) => ({ ...prev, symbol: event.target.value }))} data-testid="admin-commercial-usage-logs-symbol-input" />
          <select className="border border-black/40 bg-white px-3 py-2 text-sm" value={usageFilters.status} onChange={(event) => setUsageFilters((prev) => ({ ...prev, status: event.target.value }))} data-testid="admin-commercial-usage-logs-status-select">
            <option value="all">all</option>
            <option value="FILLED">FILLED</option>
            <option value="CANCELED">CANCELED</option>
            <option value="REJECTED">REJECTED</option>
            <option value="NEW">NEW</option>
          </select>
          <Button onClick={refreshUsage} data-testid="admin-commercial-usage-logs-filter-button">Usage Logs Filtrele</Button>
        </div>

        <div className="mt-3 overflow-x-auto" data-testid="admin-commercial-usage-logs-table-wrapper">
          <Table data-testid="admin-commercial-usage-logs-table">
            <TableHeader>
              <TableRow>
                <TableHead data-testid="admin-commercial-usage-logs-head-time">Zaman</TableHead>
                <TableHead data-testid="admin-commercial-usage-logs-head-user">User</TableHead>
                <TableHead data-testid="admin-commercial-usage-logs-head-symbol">Symbol</TableHead>
                <TableHead data-testid="admin-commercial-usage-logs-head-order-id">order_id</TableHead>
                <TableHead data-testid="admin-commercial-usage-logs-head-status">Status</TableHead>
                <TableHead data-testid="admin-commercial-usage-logs-head-pnl">PnL</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {usage.map((item) => (
                <TableRow key={item.log_id} data-testid={`admin-commercial-usage-log-row-${item.log_id}`}>
                  <TableCell data-testid={`admin-commercial-usage-log-time-${item.log_id}`}>{new Date(item.opened_at).toLocaleString()}</TableCell>
                  <TableCell data-testid={`admin-commercial-usage-log-user-${item.log_id}`}>{item.user_email}</TableCell>
                  <TableCell data-testid={`admin-commercial-usage-log-symbol-${item.log_id}`}>{item.symbol}</TableCell>
                  <TableCell data-testid={`admin-commercial-usage-log-order-id-${item.log_id}`}>{item.order_id}</TableCell>
                  <TableCell data-testid={`admin-commercial-usage-log-status-${item.log_id}`}>{item.execution_status}</TableCell>
                  <TableCell data-testid={`admin-commercial-usage-log-pnl-${item.log_id}`}>{item.pnl}</TableCell>
                </TableRow>
              ))}
              {usage.length === 0 && (
                <TableRow data-testid="admin-commercial-usage-logs-empty-row">
                  <TableCell colSpan={6} className="text-center text-sm" data-testid="admin-commercial-usage-logs-empty-text">Log kaydı bulunamadı.</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </section>
    </section>
  );
};
