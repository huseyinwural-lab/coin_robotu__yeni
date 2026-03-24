import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

const adminRoleOptions = ["super_admin", "admin", "ops"];
const statusOptions = ["all", "active", "disabled"];
const riskLevelOptions = ["all", "high", "medium", "low", "unassigned"];

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
    risk_level: "all",
    exchange: "",
    trading_enabled: "all",
    page: 1,
    page_size: 25,
  });
  const [pagination, setPagination] = useState({ page: 1, page_size: 25, total: 0, pages: 1 });
  const [selectedUserIds, setSelectedUserIds] = useState([]);
  const [createForm, setCreateForm] = useState({
    email: "",
    password: "",
    role: "admin",
  });
  const [inviteForm, setInviteForm] = useState({ email: "", invited_role: "user" });
  const [bulkLoading, setBulkLoading] = useState(false);
  const [inlineLoadingMap, setInlineLoadingMap] = useState({});
  const [securityDetail, setSecurityDetail] = useState(null);
  const [securityDetailUserId, setSecurityDetailUserId] = useState("");
  const [securityDetailLoading, setSecurityDetailLoading] = useState(false);

  useEffect(() => {
    setFilters((prev) => ({
      ...prev,
      role: isAdminScope ? "all" : "user",
      page: 1,
    }));
    setSelectedUserIds([]);
  }, [scope]);

  const loadUsers = useCallback(async () => {
    setLoading(true);
    try {
      const roleValue = isAdminScope
        ? (filters.role !== "all" ? filters.role : undefined)
        : "user";
      const tradingEnabledValue = filters.trading_enabled === "all" ? undefined : filters.trading_enabled === "true";

      const { data } = await apiClient.get("/admin/identity/users", {
        params: {
          search: filters.search || undefined,
          role: roleValue,
          status: filters.status,
          risk_level: filters.risk_level !== "all" ? filters.risk_level : undefined,
          trading_enabled: tradingEnabledValue,
          exchange: filters.exchange || undefined,
          page: filters.page,
          page_size: filters.page_size,
        },
      });
      setUsers(data?.items || []);
      setPagination(data?.pagination || { page: filters.page, page_size: filters.page_size, total: 0, pages: 1 });
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Kullanıcı listesi alınamadı");
    } finally {
      setLoading(false);
    }
  }, [filters, isAdminScope]);

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

  const requestInlineUpdate = async (userId, payload, successMessage) => {
    setInlineLoadingMap((prev) => ({ ...prev, [userId]: true }));
    try {
      const { data } = await apiClient.patch(`/admin/identity/users/${userId}/inline`, payload);
      if (data?.status === "approval_required") {
        toast.success(`Onay talebi açıldı (${data.request_id})`);
      } else {
        toast.success(successMessage || "Güncellendi");
      }
      await loadUsers();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Güncelleme başarısız");
    } finally {
      setInlineLoadingMap((prev) => ({ ...prev, [userId]: false }));
    }
  };

  const getCriticalConfirmation = (title) => {
    const confirmed = window.confirm(`${title}\n\nBu işlem kritik. Devam etmek istiyor musunuz?`);
    if (!confirmed) return null;
    const reason = window.prompt("Lütfen işlem gerekçesini yazın (zorunlu):", "operational_control_update");
    if (!reason || !reason.trim()) {
      toast.error("Kritik işlem için reason zorunlu");
      return null;
    }
    return { critical_confirmed: true, reason: reason.trim() };
  };

  const loadSecurityDetail = async (userId) => {
    setSecurityDetailLoading(true);
    setSecurityDetailUserId(userId);
    try {
      const { data } = await apiClient.get(`/admin/identity/users/${userId}/security`);
      setSecurityDetail(data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Security detail yüklenemedi");
    } finally {
      setSecurityDetailLoading(false);
    }
  };

  const unlockPolicyLock = async (userId) => {
    const confirmPayload = getCriticalConfirmation("Policy lock kaldır");
    if (!confirmPayload) return;
    try {
      await apiClient.post(`/admin/identity/users/${userId}/unlock-policy-lock`, { reason: confirmPayload.reason });
      toast.success("Policy lock kaldırıldı");
      if (securityDetailUserId === userId) {
        await loadSecurityDetail(userId);
      }
      await loadUsers();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Policy unlock başarısız");
    }
  };

  const revokeSession = async (sessionId) => {
    const confirmPayload = getCriticalConfirmation("Session revoke");
    if (!confirmPayload) return;
    try {
      await apiClient.post(`/auth/sessions/${sessionId}/revoke`, { reason: confirmPayload.reason });
      toast.success("Session revoke edildi");
      if (securityDetailUserId) {
        await loadSecurityDetail(securityDetailUserId);
      }
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Session revoke başarısız");
    }
  };

  const updateRole = async (userId, role) => {
    const confirmPayload = getCriticalConfirmation("Rol güncelle");
    if (!confirmPayload) return;
    await requestInlineUpdate(userId, { role, ...confirmPayload }, "Rol güncellendi");
  };

  const toggleStatus = async (user) => {
    const nextStatus = user.status === "active" ? "disabled" : "active";
    const confirmPayload = getCriticalConfirmation(`Kullanıcı ${nextStatus} işlemi`);
    if (!confirmPayload) return;
    await requestInlineUpdate(user.id, { status: nextStatus, ...confirmPayload }, `Kullanıcı ${nextStatus} yapıldı`);
  };

  const toggleTrading = async (user) => {
    const next = !Boolean(user?.identity_controls?.trading_enabled);
    const confirmPayload = getCriticalConfirmation(next ? "Live trading enable" : "Trading disable");
    if (!confirmPayload) return;
    await requestInlineUpdate(user.id, { trading_enabled: next, ...confirmPayload }, `Trading ${next ? "açıldı" : "kapatıldı"}`);
  };

  const setKillSwitch = async (user, active) => {
    setInlineLoadingMap((prev) => ({ ...prev, [user.id]: true }));
    try {
      await apiClient.post(`/admin/identity/users/${user.id}/kill-switch`, {
        active,
        reason: active ? "manual_kill_switch_activate" : "manual_kill_switch_release",
      });
      toast.success(active ? "Kill switch aktif" : "Kill switch kapatıldı");
      await loadUsers();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Kill switch işlemi başarısız");
    } finally {
      setInlineLoadingMap((prev) => ({ ...prev, [user.id]: false }));
    }
  };

  const requestSoftDelete = async (user) => {
    const confirmPayload = getCriticalConfirmation("Soft delete request");
    if (!confirmPayload) return;
    try {
      const { data } = await apiClient.post(`/admin/identity/users/${user.id}/soft-delete/request`, {
        reason: confirmPayload.reason,
        critical_confirmed: true,
      });
      toast.success(`Soft delete approval request açıldı (${data?.request_id})`);
      await loadUsers();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Soft delete request açılamadı");
    }
  };

  const requestHardDelete = async (user) => {
    const confirmPayload = getCriticalConfirmation("Hard delete request");
    if (!confirmPayload) return;
    try {
      const { data } = await apiClient.post(`/admin/identity/users/${user.id}/hard-delete/request`, {
        reason: confirmPayload.reason,
        critical_confirmed: true,
      });
      toast.success(`Hard delete approval request açıldı (${data?.request_id})`);
      await loadUsers();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Hard delete request açılamadı");
    }
  };

  const applyBulkStatus = async (status) => {
    if (selectedUserIds.length === 0) {
      toast.error("Önce kullanıcı seçin");
      return;
    }
    const confirmPayload = getCriticalConfirmation(`Bulk ${status} request`);
    if (!confirmPayload) return;
    setBulkLoading(true);
    try {
      const { data } = await apiClient.post("/admin/identity/users/bulk-status", {
        user_ids: selectedUserIds,
        status,
        reason: confirmPayload.reason,
        critical_confirmed: true,
      });
      toast.success(`Bulk ${status} tamamlandı (success=${data?.success ?? 0})`);
      setSelectedUserIds([]);
      await loadUsers();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Bulk işlem başarısız");
    } finally {
      setBulkLoading(false);
    }
  };

  const createInvite = async () => {
    if (!inviteForm.email.trim()) {
      toast.error("Invite email zorunlu");
      return;
    }
    try {
      const { data } = await apiClient.post("/admin/identity/invites", {
        email: inviteForm.email.trim(),
        invited_role: inviteForm.invited_role,
        expires_hours: 24,
      });
      toast.success(`Invite oluşturuldu (${data?.delivery_status})`);
      setInviteForm({ email: "", invited_role: inviteForm.invited_role });
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Invite oluşturulamadı");
    }
  };

  const toggleSelectAll = () => {
    if (selectedUserIds.length === users.length) {
      setSelectedUserIds([]);
      return;
    }
    setSelectedUserIds(users.map((item) => item.id));
  };

  const toggleSelectUser = (userId) => {
    setSelectedUserIds((prev) => (prev.includes(userId) ? prev.filter((item) => item !== userId) : [...prev, userId]));
  };

  const nextPage = () => setFilters((prev) => ({ ...prev, page: Math.min((pagination.pages || 1), prev.page + 1) }));
  const prevPage = () => setFilters((prev) => ({ ...prev, page: Math.max(1, prev.page - 1) }));

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
            onChange={(event) => setFilters((prev) => ({ ...prev, search: event.target.value, page: 1 }))}
            placeholder="Search email / user id"
            data-testid="admin-users-search-input"
          />

          <select
            className="border border-black/40 bg-white px-3 py-2 text-sm"
            value={filters.role}
            onChange={(event) => setFilters((prev) => ({ ...prev, role: event.target.value, page: 1 }))}
            data-testid="admin-users-role-filter-select"
          >
            <option value="all">all roles</option>
            {adminRoleOptions.map((role) => (
              <option key={role} value={role}>{role}</option>
            ))}
            <option value="user">user</option>
          </select>

          <select
            className="border border-black/40 bg-white px-3 py-2 text-sm"
            value={filters.status}
            onChange={(event) => setFilters((prev) => ({ ...prev, status: event.target.value, page: 1 }))}
            data-testid="admin-users-status-filter-select"
          >
            {statusOptions.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>

          <select
            className="border border-black/40 bg-white px-3 py-2 text-sm"
            value={filters.risk_level}
            onChange={(event) => setFilters((prev) => ({ ...prev, risk_level: event.target.value, page: 1 }))}
            data-testid="admin-users-risk-level-filter-select"
          >
            {riskLevelOptions.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>

          <select
            className="border border-black/40 bg-white px-3 py-2 text-sm"
            value={filters.trading_enabled}
            onChange={(event) => setFilters((prev) => ({ ...prev, trading_enabled: event.target.value, page: 1 }))}
            data-testid="admin-users-trading-enabled-filter-select"
          >
            <option value="all">trading: all</option>
            <option value="true">trading: true</option>
            <option value="false">trading: false</option>
          </select>

          <Input
            value={filters.exchange}
            onChange={(event) => setFilters((prev) => ({ ...prev, exchange: event.target.value, page: 1 }))}
            placeholder="exchange (binance/bybit)"
            data-testid="admin-users-exchange-filter-input"
          />

          <select
            className="border border-black/40 bg-white px-3 py-2 text-sm"
            value={String(filters.page_size)}
            onChange={(event) => setFilters((prev) => ({ ...prev, page_size: Number(event.target.value), page: 1 }))}
            data-testid="admin-users-page-size-select"
          >
            <option value="10">10</option>
            <option value="25">25</option>
            <option value="50">50</option>
            <option value="100">100</option>
          </select>
        </div>

        <div className="flex flex-wrap items-center gap-2" data-testid="admin-users-actions-row">
          <Button className="border border-black bg-black text-orange-400 hover:bg-zinc-800" onClick={loadUsers} data-testid="admin-users-refresh-button">
            Yenile
          </Button>
          <Button
            className="border border-black bg-red-200 text-black hover:bg-red-300"
            onClick={() => applyBulkStatus("disabled")}
            disabled={bulkLoading || selectedUserIds.length === 0}
            data-testid="admin-users-bulk-disable-button"
          >
            Bulk Disable
          </Button>
          <Button
            className="border border-black bg-emerald-200 text-black hover:bg-emerald-300"
            onClick={() => applyBulkStatus("active")}
            disabled={bulkLoading || selectedUserIds.length === 0}
            data-testid="admin-users-bulk-enable-button"
          >
            Bulk Enable
          </Button>
          <p className="text-sm text-black" data-testid="admin-users-count-text">
            Toplam kullanıcı: {pagination.total}
          </p>
          <p className="text-sm text-black" data-testid="admin-users-role-counts-text">
            super_admin:{roleCounts.super_admin || 0} · admin:{roleCounts.admin || 0} · ops:{roleCounts.ops || 0} · user:{roleCounts.user || 0}
          </p>
          <p className="text-xs text-black/80" data-testid="admin-users-selected-count-text">Seçili: {selectedUserIds.length}</p>
        </div>

        <div className="grid gap-2 border border-black/30 bg-orange-50 p-3 md:grid-cols-4" data-testid="admin-users-pagination-panel">
          <p className="text-xs text-black/80" data-testid="admin-users-page-indicator">page={pagination.page} / {pagination.pages}</p>
          <p className="text-xs text-black/80" data-testid="admin-users-page-size-indicator">page_size={pagination.page_size}</p>
          <Button variant="outline" onClick={prevPage} disabled={filters.page <= 1} data-testid="admin-users-prev-page-button">Prev</Button>
          <Button variant="outline" onClick={nextPage} disabled={filters.page >= pagination.pages} data-testid="admin-users-next-page-button">Next</Button>
        </div>

        {isAdminScope && (
          <div className="grid gap-2 border border-black/30 bg-orange-50 p-3 md:grid-cols-5" data-testid="admin-users-create-admin-form">
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

            <Input
              value={inviteForm.email}
              onChange={(event) => setInviteForm((prev) => ({ ...prev, email: event.target.value }))}
              placeholder="Invite email (MOCKED)"
              data-testid="admin-users-invite-email-input"
            />
            <Button className="border border-black bg-sky-200 text-black hover:bg-sky-300" onClick={createInvite} data-testid="admin-users-create-invite-button">
              Invite Gönder (MOCKED)
            </Button>
          </div>
        )}
      </div>

      <div className="border border-black/30 bg-orange-100" data-testid="admin-users-table-wrapper">
        <Table data-testid="admin-users-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="admin-users-head-select">
                <input type="checkbox" checked={users.length > 0 && selectedUserIds.length === users.length} onChange={toggleSelectAll} data-testid="admin-users-select-all-checkbox" />
              </TableHead>
              <TableHead data-testid="admin-users-head-email">Email</TableHead>
              <TableHead data-testid="admin-users-head-role">Role</TableHead>
              <TableHead data-testid="admin-users-head-status">Status</TableHead>
              <TableHead data-testid="admin-users-head-identity">Identity / Trading</TableHead>
              <TableHead data-testid="admin-users-head-observability">Observability</TableHead>
              <TableHead data-testid="admin-users-head-created">Created</TableHead>
              <TableHead data-testid="admin-users-head-actions">{isAdminScope ? "Actions" : "User Actions"}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.map((user) => (
              <TableRow key={user.id} data-testid={`admin-users-row-${user.id}`}>
                <TableCell data-testid={`admin-users-select-cell-${user.id}`}>
                  <input
                    type="checkbox"
                    checked={selectedUserIds.includes(user.id)}
                    onChange={() => toggleSelectUser(user.id)}
                    data-testid={`admin-users-select-checkbox-${user.id}`}
                  />
                </TableCell>
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
                <TableCell data-testid={`admin-users-identity-cell-${user.id}`}>
                  <div className="space-y-1 text-xs" data-testid={`admin-users-identity-wrap-${user.id}`}>
                    <p data-testid={`admin-users-risk-status-${user.id}`}>risk: {user.identity_controls?.risk_status || "-"}</p>
                    <p data-testid={`admin-users-trading-status-${user.id}`}>trading: {user.identity_controls?.trading_status || "-"}</p>
                    <p data-testid={`admin-users-exchange-connected-${user.id}`}>exchange: {String(Boolean(user.identity_controls?.exchange_connected))}</p>
                    <p data-testid={`admin-users-error-state-${user.id}`}>error: {user.identity_controls?.error_state || "-"}</p>
                    <p data-testid={`admin-users-live-eligible-${user.id}`}>eligible: {String(Boolean(user.identity_controls?.live_trading_eligible))}</p>
                    {user.identity_controls?.non_compliant && (
                      <span className="inline-block rounded border border-amber-700 bg-amber-200 px-2 py-1 text-[10px] font-semibold text-amber-900" data-testid={`admin-users-non-compliant-badge-${user.id}`}>
                        non-compliant
                      </span>
                    )}
                  </div>
                </TableCell>
                <TableCell data-testid={`admin-users-observability-cell-${user.id}`}>
                  <div className="space-y-1 text-xs" data-testid={`admin-users-observability-wrap-${user.id}`}>
                    <p data-testid={`admin-users-trade-count-${user.id}`}>trades: {user.observability?.trade_count ?? 0}</p>
                    <p data-testid={`admin-users-error-rate-${user.id}`}>error_rate: {user.observability?.error_rate ?? 0}</p>
                    <p data-testid={`admin-users-avg-quality-${user.id}`}>avg_quality: {user.observability?.avg_execution_quality ?? 0}</p>
                  </div>
                </TableCell>
                <TableCell className="text-xs" data-testid={`admin-users-created-at-${user.id}`}>{new Date(user.created_at).toLocaleString()}</TableCell>
                <TableCell data-testid={`admin-users-actions-${user.id}`}>
                  <div className="flex flex-wrap gap-2" data-testid={`admin-users-actions-wrap-${user.id}`}>
                    <Button
                      size="sm"
                      className={user.status === "active" ? "border border-red-700 bg-red-600 text-white hover:bg-red-700" : "border border-emerald-700 bg-emerald-600 text-black hover:bg-emerald-700"}
                      onClick={() => toggleStatus(user)}
                      disabled={Boolean(inlineLoadingMap[user.id])}
                      data-testid={`admin-users-toggle-status-button-${user.id}`}
                    >
                      {user.status === "active" ? "Disable" : "Enable"}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => toggleTrading(user)}
                      disabled={Boolean(inlineLoadingMap[user.id])}
                      data-testid={`admin-users-toggle-trading-button-${user.id}`}
                    >
                      {user?.identity_controls?.trading_enabled ? "Disable Trading" : "Enable Trading"}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => loadSecurityDetail(user.id)}
                      data-testid={`admin-users-security-detail-button-${user.id}`}
                    >
                      Security Detail
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setKillSwitch(user, !Boolean(user?.identity_controls?.kill_switch_active))}
                      disabled={Boolean(inlineLoadingMap[user.id])}
                      data-testid={`admin-users-kill-switch-button-${user.id}`}
                    >
                      {user?.identity_controls?.kill_switch_active ? "Kill OFF" : "Kill ON"}
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => requestSoftDelete(user)} data-testid={`admin-users-soft-delete-request-button-${user.id}`}>
                      Soft Delete Req
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => requestHardDelete(user)} data-testid={`admin-users-hard-delete-request-button-${user.id}`}>
                      Hard Delete Req
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}

            {!loading && users.length === 0 && (
              <TableRow data-testid="admin-users-empty-row">
                <TableCell colSpan={8} className="text-center text-sm text-black/70" data-testid="admin-users-empty-text">
                  Kriterlere uygun kullanıcı bulunamadı. Filtreleri temizleyip tekrar deneyin.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {securityDetailUserId && (
        <div className="space-y-2 border border-black/30 bg-orange-50 p-3" data-testid="admin-users-security-detail-panel">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold" data-testid="admin-users-security-detail-title">Security Detail: {securityDetail?.email || securityDetailUserId}</p>
            <Button variant="outline" onClick={() => setSecurityDetailUserId("")} data-testid="admin-users-security-detail-close-button">Kapat</Button>
          </div>

          {securityDetailLoading ? (
            <p className="text-xs" data-testid="admin-users-security-detail-loading">Yükleniyor...</p>
          ) : securityDetail ? (
            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-1 border border-black/20 bg-white p-2 text-xs" data-testid="admin-users-security-state-card">
                <p data-testid="admin-users-security-mfa-enabled">mfa_enabled: {String(Boolean(securityDetail?.mfa?.is_enabled))}</p>
                <p data-testid="admin-users-security-mfa-methods">methods: {(securityDetail?.mfa?.enabled_methods || []).join(",") || "-"}</p>
                <p data-testid="admin-users-security-backup-remaining">backup_codes_remaining: {securityDetail?.mfa?.backup_codes_remaining ?? 0}</p>
                <p data-testid="admin-users-security-policy-lock-until">policy_locked_until: {securityDetail?.security_state?.policy_locked_until || "-"}</p>
                <p data-testid="admin-users-security-password-expires">password_expires_at: {securityDetail?.security_state?.password_expires_at || "-"}</p>
                <Button variant="outline" onClick={() => unlockPolicyLock(securityDetailUserId)} data-testid="admin-users-security-unlock-button">Unlock Policy Lock</Button>
              </div>

              <div className="space-y-1 border border-black/20 bg-white p-2 text-xs" data-testid="admin-users-session-list-card">
                <p className="font-semibold" data-testid="admin-users-session-list-title">Active Sessions</p>
                {(securityDetail?.sessions || []).map((session) => (
                  <div key={session.session_id} className="flex flex-wrap items-center gap-2" data-testid={`admin-users-session-item-${session.session_id}`}>
                    <span>{session.ip_address || "-"} · {session.device_fingerprint || "-"}</span>
                    <Button size="sm" variant="outline" onClick={() => revokeSession(session.session_id)} data-testid={`admin-users-session-revoke-button-${session.session_id}`}>
                      Revoke
                    </Button>
                  </div>
                ))}
                {(securityDetail?.sessions || []).length === 0 && <p data-testid="admin-users-session-list-empty">Active session yok</p>}
              </div>

              <div className="space-y-1 border border-black/20 bg-white p-2 text-xs md:col-span-2" data-testid="admin-users-login-history-card">
                <p className="font-semibold" data-testid="admin-users-login-history-title">Login History</p>
                {(securityDetail?.login_history || []).slice(0, 10).map((item) => (
                  <p key={item.id} data-testid={`admin-users-login-history-item-${item.id}`}>
                    {item.created_at} · {item.outcome} · {item.ip_address || "-"} · {item.failure_reason || "-"}
                  </p>
                ))}
                {(securityDetail?.login_history || []).length === 0 && <p data-testid="admin-users-login-history-empty">Login history yok</p>}
              </div>
            </div>
          ) : (
            <p className="text-xs" data-testid="admin-users-security-detail-empty">Detail bulunamadı.</p>
          )}
        </div>
      )}
    </section>
  );
};
