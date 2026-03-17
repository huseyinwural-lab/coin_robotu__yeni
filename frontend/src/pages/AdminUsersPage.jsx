import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

const adminRoleOptions = ["super_admin", "admin", "ops"];

export const AdminUsersPage = ({ scope = "user" }) => {
  const { user: currentUser } = useAuth();
  const navigate = useNavigate();
  const isAdminScope = scope === "admin";
  const canCreateSuperAdmin = currentUser?.role === "super_admin";
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({
    search: "",
    role: "all",
    status: "all",
    sort_by: "created_at",
    sort_dir: "desc",
  });
  const [createForm, setCreateForm] = useState({
    email: "",
    password: "",
    role: "admin",
  });
  const [repairingUserId, setRepairingUserId] = useState(null);
  const [repairingAll, setRepairingAll] = useState(false);
  const [livePathSummary, setLivePathSummary] = useState(null);
  const [checkingLivePath, setCheckingLivePath] = useState(false);

  useEffect(() => {
    setFilters((prev) => ({ ...prev, role: "all" }));
  }, [scope]);

  const loadUsers = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/admin/users", {
        params: {
          scope,
          search: filters.search || undefined,
          role: isAdminScope && filters.role !== "all" ? filters.role : undefined,
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
  }, [filters, isAdminScope, scope]);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  const roleCounts = useMemo(() => {
    return users.reduce((acc, user) => {
      acc[user.role] = (acc[user.role] || 0) + 1;
      return acc;
    }, {});
  }, [users]);

  const handleCreateAdmin = async () => {
    if (!createForm.email.trim() || !createForm.password.trim()) {
      toast.error("Email ve şifre zorunlu");
      return;
    }
    try {
      await apiClient.post("/admin/users/admin-create", {
        email: createForm.email.trim(),
        password: createForm.password,
        role: createForm.role,
      });
      toast.success("Admin kullanıcı oluşturuldu");
      setCreateForm({ email: "", password: "", role: "admin" });
      await loadUsers();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Admin kullanıcı oluşturulamadı");
    }
  };

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

  const repairVenueAssignment = async (userId) => {
    setRepairingUserId(userId);
    try {
      const { data } = await apiClient.post(`/admin/users/${userId}/repair-venue-assignment`);
      if (data?.assignment_changed) {
        toast.success("Venue assignment onarıldı");
      } else {
        toast.success("Venue assignment zaten hazırdı");
      }
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Venue assignment onarılamadı");
    } finally {
      setRepairingUserId(null);
    }
  };

  const repairAllVenueAssignments = async () => {
    setRepairingAll(true);
    try {
      const { data } = await apiClient.post("/admin/users/repair-venue-assignments");
      toast.success(`Toplu onarım tamamlandı. changed=${data?.changed_assignments ?? 0}`);
      await loadUsers();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Toplu venue onarımı başarısız");
    } finally {
      setRepairingAll(false);
    }
  };

  const checkFuturesLivePath = async () => {
    setCheckingLivePath(true);
    try {
      const { data } = await apiClient.get("/admin/users/futures-live-path-check", { params: { limit: 300 } });
      setLivePathSummary(data || null);
      toast.success(`Futures live-path check tamamlandı. fail=${data?.fail_count ?? 0}`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Futures live-path check başarısız");
    } finally {
      setCheckingLivePath(false);
    }
  };

  return (
    <section className="space-y-4" data-testid="admin-users-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="admin-users-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-black" data-testid="admin-users-title">
          {isAdminScope ? "Admin Kullanıcıları" : "User Kullanıcıları"}
        </h2>
        <p className="mt-2 text-sm text-black/80" data-testid="admin-users-description">
          {isAdminScope
            ? "Admin/super_admin/ops kullanıcılarını ayrı listede yönet."
            : "Onaylanan müşteri kullanıcılarını ayrı listede görüntüle ve yönet."}
        </p>
      </header>

      <div className="flex flex-wrap gap-2" data-testid="admin-users-scope-menu-row">
        <Button
          className={isAdminScope ? "border border-black bg-lime-300 text-black hover:bg-lime-400" : "border border-black bg-orange-200 text-black hover:bg-orange-300"}
          onClick={() => navigate("/admin/users/admins")}
          data-testid="admin-users-scope-admins-button"
        >
          Admin Kullanıcıları
        </Button>
        <Button
          className={!isAdminScope ? "border border-black bg-lime-300 text-black hover:bg-lime-400" : "border border-black bg-orange-200 text-black hover:bg-orange-300"}
          onClick={() => navigate("/admin/users/customers")}
          data-testid="admin-users-scope-customers-button"
        >
          User Kullanıcıları
        </Button>
      </div>

      <div className="space-y-3 border border-black/30 bg-orange-100 p-4" data-testid="admin-users-toolbar">
        <div className="grid gap-2 md:grid-cols-4" data-testid="admin-users-filters-grid">
          <Input
            value={filters.search}
            onChange={(event) => setFilters((prev) => ({ ...prev, search: event.target.value }))}
            placeholder="Search email"
            data-testid="admin-users-search-input"
          />
          {isAdminScope && (
            <select
              className="border border-black/40 bg-white px-3 py-2 text-sm"
              value={filters.role}
              onChange={(event) => setFilters((prev) => ({ ...prev, role: event.target.value }))}
              data-testid="admin-users-role-filter-select"
            >
              <option value="all">all admin roles</option>
              {adminRoleOptions.map((role) => (
                <option key={role} value={role}>{role}</option>
              ))}
            </select>
          )}
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
          {!isAdminScope && (
            <Button
              className="border border-black bg-lime-200 text-black hover:bg-lime-300"
              onClick={repairAllVenueAssignments}
              disabled={repairingAll}
              data-testid="admin-users-bulk-repair-venue-assignments-button"
            >
              {repairingAll ? "Toplu Onarım Çalışıyor..." : "Toplu Venue Onar"}
            </Button>
          )}
          {!isAdminScope && (
            <Button
              className="border border-black bg-sky-200 text-black hover:bg-sky-300"
              onClick={checkFuturesLivePath}
              disabled={checkingLivePath}
              data-testid="admin-users-futures-live-path-check-button"
            >
              {checkingLivePath ? "Check Çalışıyor..." : "Futures Live-Path Check"}
            </Button>
          )}
          <p className="text-sm text-black" data-testid="admin-users-count-text">
            Toplam {isAdminScope ? "admin" : "user"} kullanıcı: {users.length}
          </p>
          {isAdminScope ? (
            <p className="text-sm text-black" data-testid="admin-users-role-counts-text">
              super_admin:{roleCounts.super_admin || 0} · admin:{roleCounts.admin || 0} · ops:{roleCounts.ops || 0}
            </p>
          ) : (
            <p className="text-sm text-black" data-testid="admin-users-user-scope-note">
              Not: Bu liste sadece onaylanan user hesaplarını gösterir.
            </p>
          )}
        </div>

        {!isAdminScope && (
          <div className="grid gap-2 border border-black/30 bg-orange-50 p-3 md:grid-cols-4" data-testid="admin-users-live-path-summary-panel">
            <p className="text-xs text-black/80" data-testid="admin-users-live-path-summary-total">total={livePathSummary?.total_users ?? 0}</p>
            <p className="text-xs text-black/80" data-testid="admin-users-live-path-summary-pass">pass={livePathSummary?.pass_count ?? 0}</p>
            <p className="text-xs text-black/80" data-testid="admin-users-live-path-summary-fail">fail={livePathSummary?.fail_count ?? 0}</p>
            <p className="text-xs text-black/80" data-testid="admin-users-live-path-summary-generated-at">generated_at={livePathSummary?.generated_at || "-"}</p>
          </div>
        )}

        {isAdminScope && (
          <div className="grid gap-2 border border-black/30 bg-orange-50 p-3 md:grid-cols-4" data-testid="admin-users-create-admin-form">
            <Input
              value={createForm.email}
              onChange={(event) => setCreateForm((prev) => ({ ...prev, email: event.target.value }))}
              placeholder="Yeni admin email"
              data-testid="admin-users-create-email-input"
            />
            <Input
              type="password"
              value={createForm.password}
              onChange={(event) => setCreateForm((prev) => ({ ...prev, password: event.target.value }))}
              placeholder="Geçici şifre"
              data-testid="admin-users-create-password-input"
            />
            <select
              className="border border-black/40 bg-white px-3 py-2 text-sm"
              value={createForm.role}
              onChange={(event) => setCreateForm((prev) => ({ ...prev, role: event.target.value }))}
              data-testid="admin-users-create-role-select"
            >
              <option value="admin">admin</option>
              <option value="ops">ops</option>
              {canCreateSuperAdmin && <option value="super_admin">super_admin</option>}
            </select>
            <Button
              className="border border-black bg-black text-orange-400 hover:bg-zinc-800"
              onClick={handleCreateAdmin}
              data-testid="admin-users-create-admin-button"
            >
              Admin Ekle
            </Button>
          </div>
        )}
      </div>

      <div className="border border-black/30 bg-orange-100" data-testid="admin-users-table-wrapper">
        <Table data-testid="admin-users-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="admin-users-head-email">Email</TableHead>
              <TableHead data-testid="admin-users-head-role">Role</TableHead>
              <TableHead data-testid="admin-users-head-status">Status</TableHead>
              <TableHead data-testid="admin-users-head-created">Created</TableHead>
              <TableHead data-testid="admin-users-head-actions">{isAdminScope ? "Actions" : "User Actions"}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.map((user) => (
              <TableRow key={user.id} data-testid={`admin-users-row-${user.id}`}>
                <TableCell data-testid={`admin-users-email-${user.id}`}>{user.email}</TableCell>
                <TableCell data-testid={`admin-users-role-cell-${user.id}`}>
                  {isAdminScope ? (
                    <select
                      className="border border-black/40 bg-white px-2 py-1 text-xs"
                      value={user.role}
                      onChange={(event) => updateRole(user.id, event.target.value)}
                      data-testid={`admin-users-role-select-${user.id}`}
                    >
                      {adminRoleOptions
                        .filter((role) => canCreateSuperAdmin || role !== "super_admin" || user.role === "super_admin")
                        .map((role) => (
                        <option key={role} value={role}>{role}</option>
                      ))}
                    </select>
                  ) : (
                    <span className="inline-block rounded border border-black/40 bg-white px-2 py-1 text-xs" data-testid={`admin-users-role-label-${user.id}`}>
                      {user.role}
                    </span>
                  )}
                </TableCell>
                <TableCell data-testid={`admin-users-status-${user.id}`}>
                  <span className={`inline-block rounded border px-2 py-1 text-xs ${user.status === "active" ? "border-emerald-700 bg-emerald-200 text-emerald-900" : "border-red-700 bg-red-200 text-red-900"}`} data-testid={`admin-users-status-badge-${user.id}`}>
                    {user.status}
                  </span>
                </TableCell>
                <TableCell className="text-xs" data-testid={`admin-users-created-at-${user.id}`}>{new Date(user.created_at).toLocaleString()}</TableCell>
                <TableCell data-testid={`admin-users-actions-${user.id}`}>
                  <div className="flex flex-wrap gap-2" data-testid={`admin-users-actions-wrap-${user.id}`}>
                    <Button
                      size="sm"
                      className={user.status === "active" ? "border border-red-700 bg-red-600 text-white hover:bg-red-700" : "border border-emerald-700 bg-emerald-600 text-black hover:bg-emerald-700"}
                      onClick={() => toggleStatus(user)}
                      data-testid={`admin-users-toggle-status-button-${user.id}`}
                    >
                      {user.status === "active" ? "Disable" : "Enable"}
                    </Button>
                    {!isAdminScope && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => repairVenueAssignment(user.id)}
                        disabled={repairingUserId === user.id}
                        data-testid={`admin-users-repair-venue-assignment-button-${user.id}`}
                      >
                        {repairingUserId === user.id ? "Onarılıyor..." : "Fix Venue"}
                      </Button>
                    )}
                  </div>
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
