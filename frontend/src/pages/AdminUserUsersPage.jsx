import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

const formatDate = (value) => {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("tr-TR", { hour12: false });
};

export const AdminUserUsersPage = () => {
  const [loading, setLoading] = useState(true);
  const [rows, setRows] = useState([]);
  const [busyMap, setBusyMap] = useState({});

  const loadUsers = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/admin/identity/users", {
        params: {
          role: "user",
          include_deleted: false,
          page: 1,
          page_size: 200,
        },
      });
      const items = Array.isArray(data?.items) ? data.items : [];
      setRows(items.filter((item) => String(item?.approval_status || "").toLowerCase() === "approved"));
    } catch (error) {
      toast.error(error?.response?.data?.detail || "User kullanıcılar yüklenemedi", {
        id: "admin-user-users-load-failed",
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  const toggleTrading = useCallback(async (userId, enabled) => {
    setBusyMap((prev) => ({ ...prev, [userId]: true }));
    try {
      await apiClient.patch(`/admin/identity/users/${userId}/trading-enabled-direct`, {
        trading_enabled: Boolean(enabled),
        reason: enabled ? "admin_user_list_trade_enable" : "admin_user_list_trade_disable",
      });
      toast.success(enabled ? "Trade aktif edildi" : "Trade durduruldu", {
        id: enabled ? `admin-user-users-trade-enable-${userId}` : `admin-user-users-trade-disable-${userId}`,
      });
      await loadUsers();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Trade durumu güncellenemedi", {
        id: `admin-user-users-trade-failed-${userId}`,
      });
    } finally {
      setBusyMap((prev) => ({ ...prev, [userId]: false }));
    }
  }, [loadUsers]);

  const hardDeleteUser = useCallback(async (userId, email) => {
    const confirmed = window.confirm(`${email} kullanıcısını kalıcı silmek istiyor musun? Bu işlem geri alınamaz.`);
    if (!confirmed) return;

    setBusyMap((prev) => ({ ...prev, [userId]: true }));
    try {
      await apiClient.delete(`/admin/identity/users/${userId}/hard-delete-direct`, {
        data: { reason: "admin_user_list_hard_delete" },
      });
      toast.success("Kullanıcı kalıcı silindi", { id: `admin-user-users-delete-${userId}` });
      await loadUsers();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Kullanıcı silinemedi", {
        id: `admin-user-users-delete-failed-${userId}`,
      });
    } finally {
      setBusyMap((prev) => ({ ...prev, [userId]: false }));
    }
  }, [loadUsers]);

  const totalApproved = useMemo(() => rows.length, [rows.length]);

  return (
    <section className="space-y-5" data-testid="admin-user-users-page">
      <header className="rounded border border-slate-800 bg-white p-4" data-testid="admin-user-users-header-card">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-black text-slate-900" data-testid="admin-user-users-title">Kullanıcılar / User Kullanıcılar</h1>
            <p className="mt-1 text-sm text-slate-600" data-testid="admin-user-users-subtitle">
              Onaylanmış kullanıcılar listesi · trade kontrol · hard delete
            </p>
          </div>
          <div className="flex items-center gap-2" data-testid="admin-user-users-header-actions">
            <span className="rounded bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700" data-testid="admin-user-users-total-approved-badge">
              toplam_onaylı={totalApproved}
            </span>
            <Button type="button" size="sm" onClick={loadUsers} data-testid="admin-user-users-refresh-button">
              Yenile
            </Button>
          </div>
        </div>
      </header>

      <div className="overflow-x-auto rounded border border-slate-800 bg-white" data-testid="admin-user-users-table-wrapper">
        <Table data-testid="admin-user-users-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="admin-user-users-table-head-username">Kullanıcı İsmi</TableHead>
              <TableHead data-testid="admin-user-users-table-head-active-status">Aktif / Pasif</TableHead>
              <TableHead data-testid="admin-user-users-table-head-trade-enable">Trade Aktif Et</TableHead>
              <TableHead data-testid="admin-user-users-table-head-trade-disable">Trade Durdur</TableHead>
              <TableHead data-testid="admin-user-users-table-head-delete">Sil</TableHead>
              <TableHead data-testid="admin-user-users-table-head-created-at">Kayıt Tarihi</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow data-testid="admin-user-users-loading-row">
                <TableCell colSpan={6} className="text-center text-slate-500" data-testid="admin-user-users-loading-cell">
                  yükleniyor...
                </TableCell>
              </TableRow>
            ) : rows.length === 0 ? (
              <TableRow data-testid="admin-user-users-empty-row">
                <TableCell colSpan={6} className="text-center text-slate-500" data-testid="admin-user-users-empty-cell">
                  onaylı user kullanıcı yok
                </TableCell>
              </TableRow>
            ) : (
              rows.map((row, index) => {
                const userId = row.id;
                const busy = Boolean(busyMap[userId]);
                const tradingEnabled = Boolean(row?.identity_controls?.trading_enabled);
                return (
                  <TableRow key={userId} data-testid={`admin-user-users-row-${index}`}>
                    <TableCell className="font-medium text-slate-900" data-testid={`admin-user-users-username-${index}`}>
                      {row.email || row.id}
                    </TableCell>
                    <TableCell data-testid={`admin-user-users-active-status-${index}`}>
                      {row.is_active ? (
                        <span className="rounded bg-emerald-100 px-2 py-1 text-xs font-semibold text-emerald-700">aktif</span>
                      ) : (
                        <span className="rounded bg-rose-100 px-2 py-1 text-xs font-semibold text-rose-700">pasif</span>
                      )}
                    </TableCell>
                    <TableCell data-testid={`admin-user-users-trade-enable-cell-${index}`}>
                      <Button
                        size="sm"
                        type="button"
                        disabled={busy || tradingEnabled}
                        onClick={() => toggleTrading(userId, true)}
                        data-testid={`admin-user-users-trade-enable-button-${index}`}
                      >
                        Trade Aktif Et
                      </Button>
                    </TableCell>
                    <TableCell data-testid={`admin-user-users-trade-disable-cell-${index}`}>
                      <Button
                        size="sm"
                        type="button"
                        variant="outline"
                        disabled={busy || !tradingEnabled}
                        onClick={() => toggleTrading(userId, false)}
                        data-testid={`admin-user-users-trade-disable-button-${index}`}
                      >
                        Trade Durdur
                      </Button>
                    </TableCell>
                    <TableCell data-testid={`admin-user-users-delete-cell-${index}`}>
                      <Button
                        size="sm"
                        type="button"
                        variant="destructive"
                        disabled={busy}
                        onClick={() => hardDeleteUser(userId, row.email || row.id)}
                        data-testid={`admin-user-users-delete-button-${index}`}
                      >
                        Sil
                      </Button>
                    </TableCell>
                    <TableCell className="text-xs text-slate-600" data-testid={`admin-user-users-created-at-${index}`}>
                      {formatDate(row.created_at)}
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>
    </section>
  );
};
