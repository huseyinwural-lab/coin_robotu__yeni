import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

const roleOptions = ["super_admin", "admin", "ops", "user"];

export const AdminUsersPage = () => {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({
    search: "",
    role: "all",
    status: "all",
    sort_by: "created_at",
    sort_dir: "desc",
  });

  const loadUsers = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/admin/users", {
        params: {
          search: filters.search || undefined,
          role: filters.role === "all" ? undefined : filters.role,
          status: filters.status,
          sort_by: filters.sort_by,
          sort_dir: filters.sort_dir,
        },
      });
      setUsers(data || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Kullanıcı listesi alınamadı");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  const roleCounts = useMemo(() => {
    return users.reduce((acc, user) => {
      acc[user.role] = (acc[user.role] || 0) + 1;
      return acc;
    }, {});
  }, [users]);

  const updateRole = async (userId, role) => {
    try {
      await apiClient.patch(`/admin/users/${userId}/role`, { role });
      toast.success("Rol güncellendi");
      await loadUsers();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Rol güncellenemedi");
    }
  };

  const toggleStatus = async (user) => {
    const nextStatus = user.status === "active" ? "disabled" : "active";
    try {
      await apiClient.patch(`/admin/users/${user.id}/status`, { status: nextStatus });
      toast.success(`Kullanıcı ${nextStatus} yapıldı`);
      await loadUsers();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Durum güncellenemedi");
    }
  };

  return (
    <section className="space-y-4" data-testid="admin-users-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="admin-users-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-black" data-testid="admin-users-title">Admin User Management</h2>
        <p className="mt-2 text-sm text-black/80" data-testid="admin-users-description">
          Kullanıcıları listele, rol ata, hesap durumunu active/disabled olarak yönet.
        </p>
      </header>

      <div className="space-y-3 border border-black/30 bg-orange-100 p-4" data-testid="admin-users-toolbar">
        <div className="grid gap-2 md:grid-cols-5" data-testid="admin-users-filters-grid">
          <Input
            value={filters.search}
            onChange={(event) => setFilters((prev) => ({ ...prev, search: event.target.value }))}
            placeholder="Search email"
            data-testid="admin-users-search-input"
          />
          <select
            className="border border-black/40 bg-white px-3 py-2 text-sm"
            value={filters.role}
            onChange={(event) => setFilters((prev) => ({ ...prev, role: event.target.value }))}
            data-testid="admin-users-role-filter-select"
          >
            <option value="all">all roles</option>
            {roleOptions.map((role) => (
              <option key={role} value={role}>{role}</option>
            ))}
          </select>
          <select
            className="border border-black/40 bg-white px-3 py-2 text-sm"
            value={filters.status}
            onChange={(event) => setFilters((prev) => ({ ...prev, status: event.target.value }))}
            data-testid="admin-users-status-filter-select"
          >
            <option value="all">all status</option>
            <option value="active">active</option>
            <option value="disabled">disabled</option>
          </select>
          <select
            className="border border-black/40 bg-white px-3 py-2 text-sm"
            value={filters.sort_by}
            onChange={(event) => setFilters((prev) => ({ ...prev, sort_by: event.target.value }))}
            data-testid="admin-users-sort-by-select"
          >
            <option value="created_at">created_at</option>
            <option value="email">email</option>
          </select>
          <select
            className="border border-black/40 bg-white px-3 py-2 text-sm"
            value={filters.sort_dir}
            onChange={(event) => setFilters((prev) => ({ ...prev, sort_dir: event.target.value }))}
            data-testid="admin-users-sort-dir-select"
          >
            <option value="desc">desc</option>
            <option value="asc">asc</option>
          </select>
        </div>

        <div className="flex flex-wrap items-center gap-2" data-testid="admin-users-actions-row">
          <Button className="border border-black bg-black text-orange-400 hover:bg-zinc-800" onClick={loadUsers} data-testid="admin-users-refresh-button">
            Yenile
          </Button>
          <p className="text-sm text-black" data-testid="admin-users-count-text">Toplam kullanıcı: {users.length}</p>
          <p className="text-sm text-black" data-testid="admin-users-role-counts-text">
            super_admin:{roleCounts.super_admin || 0} · admin:{roleCounts.admin || 0} · ops:{roleCounts.ops || 0} · user:{roleCounts.user || 0}
          </p>
        </div>
      </div>

      <div className="border border-black/30 bg-orange-100" data-testid="admin-users-table-wrapper">
        <Table data-testid="admin-users-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="admin-users-head-email">Email</TableHead>
              <TableHead data-testid="admin-users-head-role">Role</TableHead>
              <TableHead data-testid="admin-users-head-status">Status</TableHead>
              <TableHead data-testid="admin-users-head-created">Created</TableHead>
              <TableHead data-testid="admin-users-head-actions">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.map((user) => (
              <TableRow key={user.id} data-testid={`admin-users-row-${user.id}`}>
                <TableCell data-testid={`admin-users-email-${user.id}`}>{user.email}</TableCell>
                <TableCell data-testid={`admin-users-role-cell-${user.id}`}>
                  <select
                    className="border border-black/40 bg-white px-2 py-1 text-xs"
                    value={user.role}
                    onChange={(event) => updateRole(user.id, event.target.value)}
                    data-testid={`admin-users-role-select-${user.id}`}
                  >
                    {roleOptions.map((role) => (
                      <option key={role} value={role}>{role}</option>
                    ))}
                  </select>
                </TableCell>
                <TableCell data-testid={`admin-users-status-${user.id}`}>
                  <span className={`inline-block rounded border px-2 py-1 text-xs ${user.status === "active" ? "border-emerald-700 bg-emerald-200 text-emerald-900" : "border-red-700 bg-red-200 text-red-900"}`} data-testid={`admin-users-status-badge-${user.id}`}>
                    {user.status}
                  </span>
                </TableCell>
                <TableCell className="text-xs" data-testid={`admin-users-created-at-${user.id}`}>{new Date(user.created_at).toLocaleString()}</TableCell>
                <TableCell data-testid={`admin-users-actions-${user.id}`}>
                  <Button
                    size="sm"
                    className={user.status === "active" ? "border border-red-700 bg-red-600 text-white hover:bg-red-700" : "border border-emerald-700 bg-emerald-600 text-black hover:bg-emerald-700"}
                    onClick={() => toggleStatus(user)}
                    data-testid={`admin-users-toggle-status-button-${user.id}`}
                  >
                    {user.status === "active" ? "Disable" : "Enable"}
                  </Button>
                </TableCell>
              </TableRow>
            ))}

            {!loading && users.length === 0 && (
              <TableRow data-testid="admin-users-empty-row">
                <TableCell colSpan={5} className="text-center text-sm text-black/70" data-testid="admin-users-empty-text">
                  Kullanıcı bulunamadı.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </section>
  );
};
