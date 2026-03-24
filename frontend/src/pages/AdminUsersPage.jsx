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
const approvalStatusOptions = ["pending", "approved", "rejected", "all"];
const inviteStatusOptions = ["all", "pending", "accepted", "cancelled", "expired"];
const HIGH_RISK_ACTION_KEYS = new Set(["hard_delete_user", "soft_delete_user", "grant_privileged_role", "enable_live_trading", "raise_capital_limit", "bulk_soft_delete_users"]);
const REQUEST_REASON_MIN_LEN = 12;
const OVERRIDE_REASON_MIN_LEN = 16;

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
  const [securityDetailError, setSecurityDetailError] = useState("");
  const [observabilityLoading, setObservabilityLoading] = useState(false);
  const [observabilityError, setObservabilityError] = useState("");
  const [activityTimeline, setActivityTimeline] = useState(null);
  const [securityTelemetry, setSecurityTelemetry] = useState(null);
  const [executionMetrics, setExecutionMetrics] = useState(null);
  const [tradingObservability, setTradingObservability] = useState(null);
  const [approvalQueue, setApprovalQueue] = useState([]);
  const [approvalStatusFilter, setApprovalStatusFilter] = useState("pending");
  const [approvalPolicies, setApprovalPolicies] = useState([]);
  const [customRoles, setCustomRoles] = useState([]);
  const [customRoleForm, setCustomRoleForm] = useState({ role_key: "", description: "", permissions: "", is_privileged: false, priority: 100 });
  const [customRoleDraftMap, setCustomRoleDraftMap] = useState({});
  const [invites, setInvites] = useState([]);
  const [inviteStatusFilter, setInviteStatusFilter] = useState("all");
  const [hardDeleteCandidates, setHardDeleteCandidates] = useState([]);
  const [deletedLifecycle, setDeletedLifecycle] = useState([]);
  const [deletedLifecycleLoading, setDeletedLifecycleLoading] = useState(false);
  const [selectedDeletedLifecycleUser, setSelectedDeletedLifecycleUser] = useState(null);
  const [bulkPreviewData, setBulkPreviewData] = useState(null);
  const [bulkPreviewLoading, setBulkPreviewLoading] = useState(false);
  const [bulkExecutionResult, setBulkExecutionResult] = useState(null);

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

  const roleCounts = useMemo(() => {
    return users.reduce((acc, user) => {
      acc[user.role] = (acc[user.role] || 0) + 1;
      return acc;
    }, {});
  }, [users]);

  const approvalImpactSummary = useMemo(() => {
    const pendingItems = approvalQueue.filter((item) => item.status === "pending");
    const impactedUsers = new Set(pendingItems.map((item) => item.target_user_id).filter(Boolean));
    const riskWeights = {
      hard_delete_user: 95,
      soft_delete_user: 85,
      delete_user: 85,
      grant_privileged_role: 90,
      raise_capital_limit: 80,
      enable_live_trading: 75,
      disable_admin: 70,
      disable_user: 60,
      enable_user: 50,
      restore_user: 65,
    };
    const riskTotal = pendingItems.reduce((acc, item) => acc + (riskWeights[item.action_key] || 45), 0);
    const normalizedRiskScore = pendingItems.length ? Math.min(100, Math.round(riskTotal / pendingItems.length)) : 0;
    return {
      pendingCount: pendingItems.length,
      impactedUsers: impactedUsers.size,
      normalizedRiskScore,
    };
  }, [approvalQueue]);

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

  const getCriticalConfirmation = (title, options = {}) => {
    const confirmed = window.confirm(`${title}\n\nBu işlem kritik. Devam etmek istiyor musunuz?`);
    if (!confirmed) return null;
    const reason = window.prompt("Lütfen işlem gerekçesini yazın (zorunlu):", "operational_control_update");
    if (!reason || reason.trim().length < REQUEST_REASON_MIN_LEN) {
      toast.error(`Reason en az ${REQUEST_REASON_MIN_LEN} karakter olmalı`);
      return null;
    }

    const basePayload = { critical_confirmed: true, reason: reason.trim() };
    if (!options.highRisk) {
      return basePayload;
    }

    const overrideReason = window.prompt("High-risk action için override reason yazın (zorunlu):", reason.trim());
    if (!overrideReason || overrideReason.trim().length < OVERRIDE_REASON_MIN_LEN) {
      toast.error(`Override reason en az ${OVERRIDE_REASON_MIN_LEN} karakter olmalı`);
      return null;
    }
    return { ...basePayload, override_reason: overrideReason.trim() };
  };

  const showInlineDiffPreview = ({ title, field, beforeValue, afterValue }) => {
    return window.confirm(`${title}\n\nDiff Preview\n${field}: ${String(beforeValue)} -> ${String(afterValue)}\n\nDevam edilsin mi?`);
  };

  const loadSecurityDetail = async (userId) => {
    setSecurityDetailLoading(true);
    setSecurityDetailUserId(userId);
    setSecurityDetailError("");
    try {
      const { data } = await apiClient.get(`/admin/identity/users/${userId}/security`);
      setSecurityDetail(data);
    } catch (error) {
      const message = error?.response?.data?.detail || "Security detail yüklenemedi";
      setSecurityDetailError(message);
      toast.error(message);
    } finally {
      setSecurityDetailLoading(false);
    }
  };

  const loadUserObservability = async (userId) => {
    setObservabilityLoading(true);
    setObservabilityError("");
    try {
      const [activityRes, telemetryRes, executionRes, tradingRes] = await Promise.all([
        apiClient.get(`/admin/identity/users/${userId}/activity-timeline`, { params: { limit: 120 } }),
        apiClient.get(`/admin/identity/users/${userId}/security-telemetry`),
        apiClient.get(`/admin/identity/users/${userId}/execution-metrics`),
        apiClient.get(`/admin/identity/users/${userId}/trading-observability`),
      ]);
      setActivityTimeline(activityRes?.data || null);
      setSecurityTelemetry(telemetryRes?.data || null);
      setExecutionMetrics(executionRes?.data || null);
      setTradingObservability(tradingRes?.data || null);
    } catch (error) {
      setObservabilityError(error?.response?.data?.detail || "Observability yüklenemedi");
    } finally {
      setObservabilityLoading(false);
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
    const current = users.find((item) => item.id === userId);
    if (!showInlineDiffPreview({ title: "Inline Role Edit", field: "role", beforeValue: current?.role, afterValue: role })) {
      return;
    }
    const isHighRisk = ["admin", "super_admin", "ops"].includes(String(role || "").toLowerCase());
    const confirmPayload = getCriticalConfirmation("Rol güncelle", { highRisk: isHighRisk });
    if (!confirmPayload) return;
    await requestInlineUpdate(userId, { role, ...confirmPayload }, "Rol güncellendi");
  };

  const toggleStatus = async (user) => {
    const nextStatus = user.status === "active" ? "disabled" : "active";
    if (!showInlineDiffPreview({ title: "Inline Status Edit", field: "status", beforeValue: user.status, afterValue: nextStatus })) {
      return;
    }
    const confirmPayload = getCriticalConfirmation(`Kullanıcı ${nextStatus} işlemi`);
    if (!confirmPayload) return;
    await requestInlineUpdate(user.id, { status: nextStatus, ...confirmPayload }, `Kullanıcı ${nextStatus} yapıldı`);
  };

  const toggleTrading = async (user) => {
    const next = !Boolean(user?.identity_controls?.trading_enabled);
    if (!showInlineDiffPreview({
      title: "Inline Trading Edit",
      field: "trading_enabled",
      beforeValue: Boolean(user?.identity_controls?.trading_enabled),
      afterValue: next,
    })) {
      return;
    }
    const confirmPayload = getCriticalConfirmation(next ? "Live trading enable" : "Trading disable", { highRisk: next });
    if (!confirmPayload) return;
    await requestInlineUpdate(user.id, { trading_enabled: next, ...confirmPayload }, `Trading ${next ? "açıldı" : "kapatıldı"}`);
  };

  const setKillSwitch = async (user, active) => {
    if (!showInlineDiffPreview({
      title: "Inline Kill Switch Edit",
      field: "kill_switch_active",
      beforeValue: Boolean(user?.identity_controls?.kill_switch_active),
      afterValue: active,
    })) {
      return;
    }
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
    const confirmPayload = getCriticalConfirmation("Soft delete request", { highRisk: true });
    if (!confirmPayload) return;
    try {
      const { data } = await apiClient.post(`/admin/identity/users/${user.id}/soft-delete/request`, {
        reason: confirmPayload.reason,
        critical_confirmed: true,
        override_reason: confirmPayload.override_reason,
      });
      toast.success(`Soft delete approval request açıldı (${data?.request_id})`);
      await loadUsers();
      await loadHardDeleteCandidates();
      await loadDeletedLifecycle();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Soft delete request açılamadı");
    }
  };

  const requestHardDelete = async (user) => {
    const confirmPayload = getCriticalConfirmation("Hard delete request", { highRisk: true });
    if (!confirmPayload) return;
    try {
      const { data } = await apiClient.post(`/admin/identity/users/${user.id}/hard-delete/request`, {
        reason: confirmPayload.reason,
        critical_confirmed: true,
        override_reason: confirmPayload.override_reason,
      });
      toast.success(`Hard delete approval request açıldı (${data?.request_id})`);
      await loadUsers();
      await loadHardDeleteCandidates();
      await loadDeletedLifecycle();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Hard delete request açılamadı");
    }
  };

  const requestRestoreUser = async (userId) => {
    const confirmPayload = getCriticalConfirmation("Restore user request");
    if (!confirmPayload) return;
    try {
      const { data } = await apiClient.post(`/admin/identity/users/${userId}/reactivate`, {
        reason: confirmPayload.reason,
      });
      toast.success(`Restore approval request açıldı (${data?.request_id})`);
      await loadApprovalQueue();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Restore request açılamadı");
    }
  };

  const previewBulkStatus = async (status) => {
    if (selectedUserIds.length === 0) {
      toast.error("Önce kullanıcı seçin");
      return;
    }
    setBulkPreviewLoading(true);
    setBulkExecutionResult(null);
    try {
      const { data } = await apiClient.post("/admin/identity/users/bulk-status/preview", {
        user_ids: selectedUserIds,
        status,
      });
      setBulkPreviewData({ ...data, requestedStatus: status });
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Bulk preview alınamadı");
    } finally {
      setBulkPreviewLoading(false);
    }
  };

  const applyBulkStatus = async (status) => {
    if (selectedUserIds.length === 0) {
      toast.error("Önce kullanıcı seçin");
      return;
    }
    const confirmPayload = getCriticalConfirmation(`Bulk ${status} request`, { highRisk: status === "deleted" });
    if (!confirmPayload) return;
    setBulkLoading(true);
    try {
      const { data } = await apiClient.post("/admin/identity/users/bulk-status", {
        user_ids: selectedUserIds,
        status,
        reason: confirmPayload.reason,
        critical_confirmed: true,
        override_reason: confirmPayload.override_reason,
      });
      toast.success(`Bulk ${status} tamamlandı (success=${data?.success ?? 0})`);
      setBulkExecutionResult(data || null);
      setSelectedUserIds([]);
      await loadUsers();
      await loadApprovalQueue();
      await loadDeletedLifecycle();
      await loadHardDeleteCandidates();
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
      await loadInvites();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Invite oluşturulamadı");
    }
  };

  const loadApprovalQueue = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/admin/identity/approvals", { params: { status_filter: approvalStatusFilter } });
      setApprovalQueue(data?.items || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Approval queue yüklenemedi");
    }
  }, [approvalStatusFilter]);

  const approveRequest = async (requestId) => {
    const requestRow = approvalQueue.find((item) => item.id === requestId);
    const confirmPayload = getCriticalConfirmation("Approval request approve", {
      highRisk: HIGH_RISK_ACTION_KEYS.has(requestRow?.action_key),
    });
    if (!confirmPayload) return;
    try {
      await apiClient.post(`/admin/identity/approvals/${requestId}/approve`, {
        note: confirmPayload.reason,
        override_reason: confirmPayload.override_reason,
      });
      toast.success("Request approve edildi");
      await loadApprovalQueue();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Approve başarısız");
    }
  };

  const rejectRequest = async (requestId) => {
    const reason = window.prompt("Reject reason zorunlu (min 12):", "policy_reject_reason");
    if (!reason || reason.trim().length < REQUEST_REASON_MIN_LEN) {
      toast.error(`Reject reason en az ${REQUEST_REASON_MIN_LEN} karakter olmalı`);
      return;
    }
    try {
      await apiClient.post(`/admin/identity/approvals/${requestId}/reject`, { note: reason.trim() });
      toast.success("Request reject edildi");
      await loadApprovalQueue();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Reject başarısız");
    }
  };

  const loadApprovalPolicies = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/admin/identity/approval-policies");
      setApprovalPolicies(data?.items || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Approval policy listesi alınamadı");
    }
  }, []);

  const toggleApprovalPolicy = async (actionKey, isEnabled) => {
    try {
      await apiClient.patch(`/admin/identity/approval-policies/${actionKey}`, { is_enabled: isEnabled });
      toast.success("Policy güncellendi");
      await loadApprovalPolicies();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Policy güncellenemedi");
    }
  };

  const loadCustomRoles = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/admin/identity/roles/custom");
      setCustomRoles(data?.items || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Custom roles yüklenemedi");
    }
  }, []);

  const createCustomRole = async () => {
    if (!customRoleForm.role_key.trim()) {
      toast.error("role_key zorunlu");
      return;
    }
    try {
      await apiClient.post("/admin/identity/roles/custom", {
        role_key: customRoleForm.role_key.trim(),
        description: customRoleForm.description,
        permissions: customRoleForm.permissions.split(",").map((item) => item.trim()).filter(Boolean),
        is_privileged: Boolean(customRoleForm.is_privileged),
        priority: Number(customRoleForm.priority || 100),
      });
      toast.success("Custom role oluşturuldu");
      setCustomRoleForm({ role_key: "", description: "", permissions: "", is_privileged: false, priority: 100 });
      await loadCustomRoles();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Custom role oluşturulamadı");
    }
  };

  const archiveCustomRole = async (roleId) => {
    try {
      await apiClient.post(`/admin/identity/roles/custom/${roleId}/archive`);
      toast.success("Role archive edildi");
      await loadCustomRoles();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Role archive edilemedi");
    }
  };

  const cloneCustomRole = async (roleId, roleKey) => {
    const cloneKey = window.prompt("Clone role key:", `${roleKey}-clone`);
    if (!cloneKey || !cloneKey.trim()) return;
    try {
      await apiClient.post(`/admin/identity/roles/custom/${roleId}/clone`, { new_role_key: cloneKey.trim() });
      toast.success("Role clone oluşturuldu");
      await loadCustomRoles();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Role clone başarısız");
    }
  };

  const saveCustomRoleUpdate = async (roleId) => {
    const draft = customRoleDraftMap[roleId];
    if (!draft) return;
    try {
      await apiClient.patch(`/admin/identity/roles/custom/${roleId}`, {
        description: draft.description,
        permissions: String(draft.permissions || "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        priority: Number(draft.priority || 100),
        is_privileged: Boolean(draft.is_privileged),
      });
      toast.success("Custom role güncellendi");
      setCustomRoleDraftMap((prev) => {
        const next = { ...prev };
        delete next[roleId];
        return next;
      });
      await loadCustomRoles();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Custom role güncellenemedi");
    }
  };

  const bindCustomRoleToSelectedUser = async (rolePolicyId) => {
    if (selectedUserIds.length !== 1) {
      toast.error("Custom role atamak için listeden tam 1 kullanıcı seçin");
      return;
    }
    try {
      await apiClient.post(`/admin/identity/users/${selectedUserIds[0]}/assign-custom-role`, { role_policy_id: rolePolicyId });
      toast.success("Custom role kullanıcıya atandı");
      await loadUsers();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Custom role atama başarısız");
    }
  };

  const addStrategyScope = async (userId) => {
    const strategyCode = window.prompt("Strategy code girin (zorunlu):", "");
    if (!strategyCode || !strategyCode.trim()) {
      toast.error("strategy_code zorunlu");
      return;
    }
    try {
      await apiClient.post(`/admin/identity/users/${userId}/strategy-scope`, {
        strategy_code: strategyCode.trim(),
        is_enabled: true,
      });
      toast.success("Strategy scope eklendi");
      await loadUsers();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Strategy scope eklenemedi");
    }
  };

  const addBotScope = async (userId) => {
    const botProfileId = window.prompt("Bot profile id girin (zorunlu):", "");
    if (!botProfileId || !botProfileId.trim()) {
      toast.error("bot_profile_id zorunlu");
      return;
    }
    try {
      await apiClient.post(`/admin/identity/users/${userId}/bot-scope`, {
        bot_profile_id: botProfileId.trim(),
        is_enabled: true,
      });
      toast.success("Bot scope eklendi");
      await loadUsers();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Bot scope eklenemedi");
    }
  };

  const loadInvites = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/admin/identity/invites", { params: { status_filter: inviteStatusFilter } });
      setInvites(data?.items || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Invite listesi yüklenemedi");
    }
  }, [inviteStatusFilter]);

  const resendInvite = async (inviteId) => {
    try {
      await apiClient.post(`/admin/identity/invites/${inviteId}/resend`);
      toast.success("Invite tekrar gönderildi (MOCKED)");
      await loadInvites();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Invite resend başarısız");
    }
  };

  const cancelInvite = async (inviteId) => {
    try {
      await apiClient.post(`/admin/identity/invites/${inviteId}/cancel`);
      toast.success("Invite cancel edildi");
      await loadInvites();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Invite cancel başarısız");
    }
  };

  const loadHardDeleteCandidates = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/admin/identity/users/hard-delete-candidates", { params: { limit: 200 } });
      setHardDeleteCandidates(data?.items || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Hard delete candidates yüklenemedi");
    }
  }, []);

  const loadDeletedLifecycle = useCallback(async () => {
    setDeletedLifecycleLoading(true);
    try {
      const { data } = await apiClient.get("/admin/identity/users/deleted-lifecycle", { params: { limit: 200 } });
      setDeletedLifecycle(data?.items || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Deleted lifecycle yüklenemedi");
    } finally {
      setDeletedLifecycleLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  useEffect(() => {
    loadApprovalQueue();
  }, [loadApprovalQueue]);

  useEffect(() => {
    loadApprovalPolicies();
    loadCustomRoles();
    loadInvites();
    loadHardDeleteCandidates();
    loadDeletedLifecycle();
  }, [loadApprovalPolicies, loadCustomRoles, loadInvites, loadHardDeleteCandidates, loadDeletedLifecycle]);

  const renderTrendChart = (trend, testIdPrefix) => {
    const values = [
      { key: "24h", value: Number(trend?.["24h"] || 0) },
      { key: "7d", value: Number(trend?.["7d"] || 0) },
      { key: "30d", value: Number(trend?.["30d"] || 0) },
    ];
    const maxValue = Math.max(...values.map((item) => item.value), 1);
    return (
      <div className="space-y-1" data-testid={`${testIdPrefix}-trend-chart`}>
        {values.map((item) => (
          <div key={item.key} className="flex items-center gap-2" data-testid={`${testIdPrefix}-trend-row-${item.key}`}>
            <span className="w-8 text-[10px]">{item.key}</span>
            <div className="h-2 flex-1 border border-black/15 bg-orange-100">
              <div className="h-full bg-black" style={{ width: `${Math.max((item.value / maxValue) * 100, item.value > 0 ? 8 : 0)}%` }}></div>
            </div>
            <span className="w-8 text-right text-[10px]">{item.value}</span>
          </div>
        ))}
      </div>
    );
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
            className="border border-black bg-yellow-200 text-black hover:bg-yellow-300"
            onClick={() => previewBulkStatus("disabled")}
            disabled={bulkPreviewLoading || selectedUserIds.length === 0}
            data-testid="admin-users-bulk-disable-preview-button"
          >
            Preview Disable
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
            className="border border-black bg-yellow-200 text-black hover:bg-yellow-300"
            onClick={() => previewBulkStatus("active")}
            disabled={bulkPreviewLoading || selectedUserIds.length === 0}
            data-testid="admin-users-bulk-enable-preview-button"
          >
            Preview Enable
          </Button>
          <Button
            className="border border-black bg-emerald-200 text-black hover:bg-emerald-300"
            onClick={() => applyBulkStatus("active")}
            disabled={bulkLoading || selectedUserIds.length === 0}
            data-testid="admin-users-bulk-enable-button"
          >
            Bulk Enable
          </Button>
          <Button
            className="border border-black bg-yellow-200 text-black hover:bg-yellow-300"
            onClick={() => previewBulkStatus("deleted")}
            disabled={bulkPreviewLoading || selectedUserIds.length === 0}
            data-testid="admin-users-bulk-delete-preview-button"
          >
            Preview Soft Delete
          </Button>
          <Button
            className="border border-black bg-red-300 text-black hover:bg-red-400"
            onClick={() => applyBulkStatus("deleted")}
            disabled={bulkLoading || selectedUserIds.length === 0}
            data-testid="admin-users-bulk-delete-button"
          >
            Bulk Soft Delete
          </Button>
          <p className="text-sm text-black" data-testid="admin-users-count-text">
            Toplam kullanıcı: {pagination.total}
          </p>
          <p className="text-sm text-black" data-testid="admin-users-role-counts-text">
            super_admin:{roleCounts.super_admin || 0} · admin:{roleCounts.admin || 0} · ops:{roleCounts.ops || 0} · user:{roleCounts.user || 0}
          </p>
          <p className="text-xs text-black/80" data-testid="admin-users-selected-count-text">Seçili: {selectedUserIds.length}</p>
          {bulkExecutionResult && (
            <p className="text-xs text-black/80" data-testid="admin-users-bulk-execution-result-text">
              partial_execution={String(Boolean((bulkExecutionResult?.failed || []).length > 0))} · requested={bulkExecutionResult?.requested ?? 0} · success={bulkExecutionResult?.success ?? 0}
            </p>
          )}
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
                      onClick={async () => {
                        await loadSecurityDetail(user.id);
                        await loadUserObservability(user.id);
                      }}
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
                    <Button size="sm" variant="outline" onClick={() => addStrategyScope(user.id)} data-testid={`admin-users-add-strategy-scope-button-${user.id}`}>
                      Add Strategy Scope
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => addBotScope(user.id)} data-testid={`admin-users-add-bot-scope-button-${user.id}`}>
                      Add Bot Scope
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

      {(bulkPreviewData || bulkPreviewLoading) && (
        <div className="space-y-3 border border-black/30 bg-yellow-50 p-3" data-testid="admin-users-bulk-preview-panel">
          <div className="flex flex-wrap items-center justify-between gap-2" data-testid="admin-users-bulk-preview-header-row">
            <h3 className="text-sm font-bold uppercase tracking-wide" data-testid="admin-users-bulk-preview-title">
              Bulk Preview {bulkPreviewData?.requestedStatus ? `(${bulkPreviewData.requestedStatus})` : ""}
            </h3>
            <div className="flex flex-wrap gap-2" data-testid="admin-users-bulk-preview-header-actions">
              <Button size="sm" variant="outline" onClick={() => setBulkPreviewData(null)} data-testid="admin-users-bulk-preview-close-button">Kapat</Button>
              <Button
                size="sm"
                className="border border-black bg-black text-orange-300 hover:bg-zinc-900"
                onClick={() => applyBulkStatus(bulkPreviewData?.requestedStatus || "disabled")}
                disabled={bulkLoading || !bulkPreviewData?.requestedStatus}
                data-testid="admin-users-bulk-preview-execute-button"
              >
                Preview Sonrası Uygula
              </Button>
            </div>
          </div>

          {bulkPreviewLoading ? (
            <p className="text-xs text-black/70" data-testid="admin-users-bulk-preview-loading-text">Bulk preview hazırlanıyor...</p>
          ) : (
            <>
              <div className="grid gap-2 border border-black/20 bg-white p-2 md:grid-cols-5" data-testid="admin-users-bulk-preview-summary-grid">
                <p className="text-xs" data-testid="admin-users-bulk-preview-total">total={bulkPreviewData?.summary?.total ?? 0}</p>
                <p className="text-xs" data-testid="admin-users-bulk-preview-eligible">eligible={bulkPreviewData?.summary?.eligible_count ?? 0}</p>
                <p className="text-xs" data-testid="admin-users-bulk-preview-blocked">blocked={bulkPreviewData?.summary?.blocked_count ?? 0}</p>
                <p className="text-xs" data-testid="admin-users-bulk-preview-high-risk">high_risk={bulkPreviewData?.summary?.high_risk_count ?? 0}</p>
                <p className="text-xs" data-testid="admin-users-bulk-preview-partial">partial_execution_expected={String(Boolean(bulkPreviewData?.summary?.partial_execution_expected))}</p>
                <p className="text-xs" data-testid="admin-users-bulk-preview-risk-total">risk_score_total={bulkPreviewData?.summary?.risk_score_total ?? 0}</p>
                <p className="text-xs md:col-span-2" data-testid="admin-users-bulk-preview-blocker-breakdown">
                  blocker_breakdown={Object.entries(bulkPreviewData?.summary?.blocker_breakdown || {}).map(([k, v]) => `${k}:${v}`).join(" | ") || "-"}
                </p>
                <p className="text-xs md:col-span-2" data-testid="admin-users-bulk-preview-action-summary">
                  action_summary={bulkPreviewData?.summary?.action_summary?.action_key || "-"} · impacted={bulkPreviewData?.summary?.action_summary?.impacted_users_count ?? 0}
                </p>
              </div>

              <div className="space-y-2" data-testid="admin-users-bulk-preview-item-list">
                {(bulkPreviewData?.items || []).map((item) => (
                  <div
                    key={item.user_id}
                    className={`border p-2 ${item.eligible ? "border-emerald-300 bg-white" : "border-red-300 bg-red-50"}`}
                    data-testid={`admin-users-bulk-preview-item-${item.user_id}`}
                  >
                    <p className="text-xs" data-testid={`admin-users-bulk-preview-email-${item.user_id}`}>{item.email || item.user_id}</p>
                    <p className="text-xs" data-testid={`admin-users-bulk-preview-risk-${item.user_id}`}>
                      risk_badge={item.risk_badge} · risk_score={item.risk_score}
                    </p>
                    <p className="text-xs" data-testid={`admin-users-bulk-preview-eligible-${item.user_id}`}>eligible={String(Boolean(item.eligible))}</p>
                    <p className="text-xs text-black/80" data-testid={`admin-users-bulk-preview-blockers-${item.user_id}`}>
                      blockers={(item.blockers || []).join(", ") || "-"}
                    </p>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-2" data-testid="admin-users-control-panels-grid">
        <div className="space-y-3 border border-black/30 bg-orange-50 p-3" data-testid="admin-users-approval-queue-panel">
          <div className="flex flex-wrap items-center justify-between gap-2" data-testid="admin-users-approval-queue-header-row">
            <h3 className="text-sm font-bold uppercase tracking-wide" data-testid="admin-users-approval-queue-title">Approval Queue</h3>
            <div className="flex flex-wrap items-center gap-2" data-testid="admin-users-approval-queue-controls">
              <select
                className="border border-black/40 bg-white px-2 py-1 text-xs"
                value={approvalStatusFilter}
                onChange={(event) => setApprovalStatusFilter(event.target.value)}
                data-testid="admin-users-approval-status-filter-select"
              >
                {approvalStatusOptions.map((statusValue) => (
                  <option key={statusValue} value={statusValue}>{statusValue}</option>
                ))}
              </select>
              <Button size="sm" variant="outline" onClick={loadApprovalQueue} data-testid="admin-users-approval-refresh-button">Yenile</Button>
            </div>
          </div>

          <div className="grid gap-2 border border-black/20 bg-white p-2 md:grid-cols-3" data-testid="admin-users-approval-impact-summary-grid">
            <p className="text-xs" data-testid="admin-users-approval-impact-pending-count">pending={approvalImpactSummary.pendingCount}</p>
            <p className="text-xs" data-testid="admin-users-approval-impact-user-count">impacted_users={approvalImpactSummary.impactedUsers}</p>
            <p className="text-xs" data-testid="admin-users-approval-impact-risk-score">risk_score={approvalImpactSummary.normalizedRiskScore}</p>
          </div>

          <div className="space-y-2" data-testid="admin-users-approval-list">
            {approvalQueue.map((request) => (
              <div key={request.id} className="space-y-2 border border-black/20 bg-white p-2" data-testid={`admin-users-approval-item-${request.id}`}>
                <p className="text-xs" data-testid={`admin-users-approval-action-${request.id}`}>{request.action_key}</p>
                <p className="text-xs" data-testid={`admin-users-approval-target-${request.id}`}>target: {request.target_user_id}</p>
                <p className="text-xs" data-testid={`admin-users-approval-meta-${request.id}`}>
                  status={request.status} · approvals={request.approval_count}/{request.required_approvals}
                </p>
                <p className="text-xs text-black/80" data-testid={`admin-users-approval-reason-${request.id}`}>reason: {request.request_reason || "-"}</p>

                <div className="space-y-1 border border-black/10 bg-orange-50 p-2 text-xs" data-testid={`admin-users-approval-diff-card-${request.id}`}>
                  {request?.impact_delta?.high_risk && (
                    <p className="bg-red-200 px-1 py-0.5 text-[11px] font-semibold" data-testid={`admin-users-approval-risk-banner-${request.id}`}>
                      HIGH-RISK ACTION
                    </p>
                  )}
                  <p data-testid={`admin-users-approval-risk-level-${request.id}`}>risk={request?.impact_delta?.risk_level} ({request?.impact_delta?.risk_score})</p>
                  <p data-testid={`admin-users-approval-risk-delta-${request.id}`}>risk_delta={request?.impact_delta?.risk_delta ?? 0}</p>
                  <p data-testid={`admin-users-approval-impacted-users-${request.id}`}>impacted_users={request?.impact_delta?.impacted_users_count ?? 1}</p>
                  <p data-testid={`admin-users-approval-delta-role-${request.id}`}>role: {request?.impact_delta?.previous?.role || "-"}{" → "}{request?.impact_delta?.desired?.role || "-"}</p>
                  <p data-testid={`admin-users-approval-delta-trading-${request.id}`}>trading: {String(request?.impact_delta?.previous?.trading_enabled)}{" → "}{String(request?.impact_delta?.desired?.trading_enabled)}</p>
                  <p data-testid={`admin-users-approval-delta-delete-${request.id}`}>delete_state: {request?.impact_delta?.previous?.delete_state || "-"}{" → "}{request?.impact_delta?.desired?.delete_state || "-"}</p>
                  <p data-testid={`admin-users-approval-delta-capital-${request.id}`}>capital_limit: {request?.impact_delta?.previous?.capital_limit ?? "-"}{" → "}{request?.impact_delta?.desired?.capital_limit ?? "-"}</p>
                  <p data-testid={`admin-users-approval-delta-changed-fields-${request.id}`}>changed_fields={(request?.impact_delta?.changed_fields || []).join(", ") || "-"}</p>
                  <p data-testid={`admin-users-approval-delta-numeric-${request.id}`}>
                    numeric_changes={Object.entries(request?.impact_delta?.numeric_changes || {}).map(([k, v]) => `${k}:${v}`).join(", ") || "-"}
                  </p>
                  <p data-testid={`admin-users-approval-delta-blockers-${request.id}`}>blockers={(request?.impact_delta?.blockers || []).join(", ") || "-"}</p>
                </div>

                <div className="flex flex-wrap gap-2" data-testid={`admin-users-approval-actions-${request.id}`}>
                  <Button
                    size="sm"
                    className="border border-black bg-emerald-200 text-black hover:bg-emerald-300"
                    onClick={() => approveRequest(request.id)}
                    disabled={request.status !== "pending"}
                    data-testid={`admin-users-approval-approve-button-${request.id}`}
                  >
                    Approve
                  </Button>
                  <Button
                    size="sm"
                    className="border border-black bg-red-200 text-black hover:bg-red-300"
                    onClick={() => rejectRequest(request.id)}
                    disabled={request.status !== "pending"}
                    data-testid={`admin-users-approval-reject-button-${request.id}`}
                  >
                    Reject
                  </Button>
                </div>
              </div>
            ))}
            {approvalQueue.length === 0 && (
              <p className="text-xs text-black/70" data-testid="admin-users-approval-empty-text">Filtreye uygun approval request bulunamadı.</p>
            )}
          </div>
        </div>

        <div className="space-y-3 border border-black/30 bg-orange-50 p-3" data-testid="admin-users-approval-policy-panel">
          <div className="flex items-center justify-between" data-testid="admin-users-approval-policy-header-row">
            <h3 className="text-sm font-bold uppercase tracking-wide" data-testid="admin-users-approval-policy-title">Approval Policies</h3>
            <Button size="sm" variant="outline" onClick={loadApprovalPolicies} data-testid="admin-users-approval-policy-refresh-button">Yenile</Button>
          </div>

          <div className="space-y-2" data-testid="admin-users-approval-policy-list">
            {approvalPolicies.map((policy) => (
              <div key={policy.action_key} className="flex flex-wrap items-center justify-between gap-2 border border-black/20 bg-white p-2" data-testid={`admin-users-policy-item-${policy.action_key}`}>
                <div className="space-y-1" data-testid={`admin-users-policy-metadata-${policy.action_key}`}>
                  <p className="text-xs font-semibold">{policy.action_key}</p>
                  <p className="text-[11px] text-black/75" data-testid={`admin-users-policy-approvals-${policy.action_key}`}>
                    required_approvals={policy.required_approvals}
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => toggleApprovalPolicy(policy.action_key, !policy.is_enabled)}
                  data-testid={`admin-users-policy-toggle-button-${policy.action_key}`}
                >
                  {policy.is_enabled ? "Disable" : "Enable"}
                </Button>
              </div>
            ))}
            {approvalPolicies.length === 0 && (
              <p className="text-xs text-black/70" data-testid="admin-users-approval-policy-empty-text">Approval policy bulunamadı.</p>
            )}
          </div>
        </div>

        <div className="space-y-3 border border-black/30 bg-orange-50 p-3" data-testid="admin-users-custom-role-panel">
          <div className="flex items-center justify-between" data-testid="admin-users-custom-role-header-row">
            <h3 className="text-sm font-bold uppercase tracking-wide" data-testid="admin-users-custom-role-title">Custom Roles</h3>
            <Button size="sm" variant="outline" onClick={loadCustomRoles} data-testid="admin-users-custom-role-refresh-button">Yenile</Button>
          </div>

          <div className="grid gap-2 border border-black/20 bg-white p-3 md:grid-cols-2" data-testid="admin-users-custom-role-create-grid">
            <Input
              value={customRoleForm.role_key}
              onChange={(event) => setCustomRoleForm((prev) => ({ ...prev, role_key: event.target.value }))}
              placeholder="role_key"
              data-testid="admin-users-custom-role-key-input"
            />
            <Input
              value={customRoleForm.description}
              onChange={(event) => setCustomRoleForm((prev) => ({ ...prev, description: event.target.value }))}
              placeholder="description"
              data-testid="admin-users-custom-role-description-input"
            />
            <Input
              value={customRoleForm.permissions}
              onChange={(event) => setCustomRoleForm((prev) => ({ ...prev, permissions: event.target.value }))}
              placeholder="permissions (virgülle)"
              data-testid="admin-users-custom-role-permissions-input"
            />
            <Input
              type="number"
              value={String(customRoleForm.priority)}
              onChange={(event) => setCustomRoleForm((prev) => ({ ...prev, priority: Number(event.target.value || 100) }))}
              placeholder="priority"
              data-testid="admin-users-custom-role-priority-input"
            />
            <label className="flex items-center gap-2 text-xs" data-testid="admin-users-custom-role-privileged-label">
              <input
                type="checkbox"
                checked={Boolean(customRoleForm.is_privileged)}
                onChange={(event) => setCustomRoleForm((prev) => ({ ...prev, is_privileged: event.target.checked }))}
                data-testid="admin-users-custom-role-privileged-checkbox"
              />
              is_privileged
            </label>
            <Button
              className="border border-black bg-black text-orange-400 hover:bg-zinc-800"
              onClick={createCustomRole}
              data-testid="admin-users-custom-role-create-button"
            >
              Custom Role Oluştur
            </Button>
          </div>

          <div className="space-y-2" data-testid="admin-users-custom-role-list">
            {customRoles.map((role) => {
              const draft = customRoleDraftMap[role.id];
              return (
                <div key={role.id} className="space-y-2 border border-black/20 bg-white p-2" data-testid={`admin-users-custom-role-item-${role.id}`}>
                  <p className="text-xs font-semibold" data-testid={`admin-users-custom-role-key-${role.id}`}>{role.role_key}</p>
                  <p className="text-[11px] text-black/75" data-testid={`admin-users-custom-role-status-${role.id}`}>
                    active={String(Boolean(role.is_active))} · privileged={String(Boolean(role.is_privileged))}
                  </p>
                  <p className="text-[11px] text-black/75" data-testid={`admin-users-custom-role-permissions-${role.id}`}>
                    permissions: {(role.permissions || []).join(", ") || "-"}
                  </p>

                  {draft ? (
                    <div className="grid gap-2 md:grid-cols-2" data-testid={`admin-users-custom-role-edit-grid-${role.id}`}>
                      <Input
                        value={draft.description}
                        onChange={(event) => setCustomRoleDraftMap((prev) => ({
                          ...prev,
                          [role.id]: { ...prev[role.id], description: event.target.value },
                        }))}
                        placeholder="description"
                        data-testid={`admin-users-custom-role-edit-description-input-${role.id}`}
                      />
                      <Input
                        value={draft.permissions}
                        onChange={(event) => setCustomRoleDraftMap((prev) => ({
                          ...prev,
                          [role.id]: { ...prev[role.id], permissions: event.target.value },
                        }))}
                        placeholder="permissions"
                        data-testid={`admin-users-custom-role-edit-permissions-input-${role.id}`}
                      />
                      <Input
                        type="number"
                        value={String(draft.priority)}
                        onChange={(event) => setCustomRoleDraftMap((prev) => ({
                          ...prev,
                          [role.id]: { ...prev[role.id], priority: Number(event.target.value || 100) },
                        }))}
                        placeholder="priority"
                        data-testid={`admin-users-custom-role-edit-priority-input-${role.id}`}
                      />
                      <label className="flex items-center gap-2 text-xs" data-testid={`admin-users-custom-role-edit-privileged-label-${role.id}`}>
                        <input
                          type="checkbox"
                          checked={Boolean(draft.is_privileged)}
                          onChange={(event) => setCustomRoleDraftMap((prev) => ({
                            ...prev,
                            [role.id]: { ...prev[role.id], is_privileged: event.target.checked },
                          }))}
                          data-testid={`admin-users-custom-role-edit-privileged-checkbox-${role.id}`}
                        />
                        is_privileged
                      </label>
                    </div>
                  ) : null}

                  <div className="flex flex-wrap gap-2" data-testid={`admin-users-custom-role-actions-${role.id}`}>
                    {!draft ? (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setCustomRoleDraftMap((prev) => ({
                          ...prev,
                          [role.id]: {
                            description: role.description || "",
                            permissions: (role.permissions || []).join(", "),
                            priority: Number(role.priority || 100),
                            is_privileged: Boolean(role.is_privileged),
                          },
                        }))}
                        data-testid={`admin-users-custom-role-edit-button-${role.id}`}
                      >
                        Edit
                      </Button>
                    ) : (
                      <>
                        <Button size="sm" variant="outline" onClick={() => saveCustomRoleUpdate(role.id)} data-testid={`admin-users-custom-role-save-button-${role.id}`}>
                          Save
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setCustomRoleDraftMap((prev) => {
                            const next = { ...prev };
                            delete next[role.id];
                            return next;
                          })}
                          data-testid={`admin-users-custom-role-cancel-edit-button-${role.id}`}
                        >
                          Cancel
                        </Button>
                      </>
                    )}

                    <Button size="sm" variant="outline" onClick={() => cloneCustomRole(role.id, role.role_key)} data-testid={`admin-users-custom-role-clone-button-${role.id}`}>
                      Clone
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => archiveCustomRole(role.id)} data-testid={`admin-users-custom-role-archive-button-${role.id}`}>
                      Archive
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => bindCustomRoleToSelectedUser(role.id)} data-testid={`admin-users-custom-role-bind-button-${role.id}`}>
                      Seçili Kullanıcıya Ata
                    </Button>
                  </div>
                </div>
              );
            })}
            {customRoles.length === 0 && (
              <p className="text-xs text-black/70" data-testid="admin-users-custom-role-empty-text">Custom role bulunamadı.</p>
            )}
          </div>
        </div>

        <div className="space-y-3 border border-black/30 bg-orange-50 p-3" data-testid="admin-users-invite-and-delete-panel">
          <div className="flex flex-wrap items-center justify-between gap-2" data-testid="admin-users-invite-header-row">
            <h3 className="text-sm font-bold uppercase tracking-wide" data-testid="admin-users-invite-title">Invite Lifecycle</h3>
            <div className="flex items-center gap-2" data-testid="admin-users-invite-controls">
              <select
                className="border border-black/40 bg-white px-2 py-1 text-xs"
                value={inviteStatusFilter}
                onChange={(event) => setInviteStatusFilter(event.target.value)}
                data-testid="admin-users-invite-status-filter-select"
              >
                {inviteStatusOptions.map((statusValue) => (
                  <option key={statusValue} value={statusValue}>{statusValue}</option>
                ))}
              </select>
              <Button size="sm" variant="outline" onClick={loadInvites} data-testid="admin-users-invite-refresh-button">Yenile</Button>
            </div>
          </div>

          <div className="grid gap-2 border border-black/20 bg-white p-3 md:grid-cols-3" data-testid="admin-users-invite-create-grid">
            <Input
              value={inviteForm.email}
              onChange={(event) => setInviteForm((prev) => ({ ...prev, email: event.target.value }))}
              placeholder="invite email"
              data-testid="admin-users-invite-panel-email-input"
            />
            <select
              className="border border-black/40 bg-white px-2 py-2 text-xs"
              value={inviteForm.invited_role}
              onChange={(event) => setInviteForm((prev) => ({ ...prev, invited_role: event.target.value }))}
              data-testid="admin-users-invite-panel-role-select"
            >
              <option value="user">user</option>
              <option value="ops">ops</option>
              <option value="admin">admin</option>
            </select>
            <Button
              className="border border-black bg-sky-200 text-black hover:bg-sky-300"
              onClick={createInvite}
              data-testid="admin-users-invite-panel-create-button"
            >
              Invite Oluştur (MOCKED)
            </Button>
          </div>

          <div className="space-y-2" data-testid="admin-users-invite-list">
            {invites.map((invite) => (
              <div key={invite.id} className="space-y-1 border border-black/20 bg-white p-2" data-testid={`admin-users-invite-item-${invite.id}`}>
                <p className="text-xs font-semibold" data-testid={`admin-users-invite-email-${invite.id}`}>{invite.email}</p>
                <p className="text-[11px] text-black/75" data-testid={`admin-users-invite-meta-${invite.id}`}>
                  role={invite.invited_role} · status={invite.status} · delivery={invite.delivery_status}
                </p>
                <p className="text-[11px] text-black/75" data-testid={`admin-users-invite-preview-token-${invite.id}`}>
                  preview_token={invite.preview_token || "-"}
                </p>
                <div className="flex flex-wrap gap-2" data-testid={`admin-users-invite-actions-${invite.id}`}>
                  <Button size="sm" variant="outline" onClick={() => resendInvite(invite.id)} data-testid={`admin-users-invite-resend-button-${invite.id}`}>
                    Resend
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => cancelInvite(invite.id)} data-testid={`admin-users-invite-cancel-button-${invite.id}`}>
                    Cancel
                  </Button>
                </div>
              </div>
            ))}
            {invites.length === 0 && (
              <p className="text-xs text-black/70" data-testid="admin-users-invite-empty-text">Invite bulunamadı.</p>
            )}
          </div>

          <div className="space-y-2 border border-black/20 bg-white p-2" data-testid="admin-users-hard-delete-candidates-panel">
            <div className="flex items-center justify-between" data-testid="admin-users-hard-delete-candidates-header-row">
              <p className="text-xs font-semibold" data-testid="admin-users-hard-delete-candidates-title">Hard Delete Candidates</p>
              <Button size="sm" variant="outline" onClick={loadHardDeleteCandidates} data-testid="admin-users-hard-delete-candidates-refresh-button">Yenile</Button>
            </div>
            {hardDeleteCandidates.slice(0, 10).map((candidate) => (
              <div key={candidate.user_id} className="border border-black/10 p-2" data-testid={`admin-users-hard-delete-candidate-item-${candidate.user_id}`}>
                <p className="text-[11px]" data-testid={`admin-users-hard-delete-candidate-email-${candidate.user_id}`}>{candidate.email}</p>
                <p className="text-[11px]" data-testid={`admin-users-hard-delete-candidate-eligible-${candidate.user_id}`}>
                  eligible={String(Boolean(candidate.eligible))}
                </p>
                <p className="text-[11px]" data-testid={`admin-users-hard-delete-candidate-retention-${candidate.user_id}`}>
                  retention_days_remaining={candidate.retention_days_remaining ?? 0}
                </p>
                <p className="text-[11px]" data-testid={`admin-users-hard-delete-candidate-risk-${candidate.user_id}`}>
                  risk_score={candidate.risk_score ?? 0}
                </p>
                <p className="text-[11px] text-black/75" data-testid={`admin-users-hard-delete-candidate-blockers-${candidate.user_id}`}>
                  blockers={(candidate.blockers || []).join(", ") || "-"}
                </p>
              </div>
            ))}
            {hardDeleteCandidates.length === 0 && (
              <p className="text-xs text-black/70" data-testid="admin-users-hard-delete-candidates-empty-text">Aday bulunamadı.</p>
            )}
          </div>

          <div className="space-y-2 border border-black/20 bg-white p-2" data-testid="admin-users-deleted-lifecycle-panel">
            <div className="flex items-center justify-between" data-testid="admin-users-deleted-lifecycle-header-row">
              <p className="text-xs font-semibold" data-testid="admin-users-deleted-lifecycle-title">Deleted Users Lifecycle</p>
              <Button size="sm" variant="outline" onClick={loadDeletedLifecycle} data-testid="admin-users-deleted-lifecycle-refresh-button">Yenile</Button>
            </div>

            {deletedLifecycleLoading ? (
              <p className="text-xs text-black/70" data-testid="admin-users-deleted-lifecycle-loading-text">Deleted lifecycle yükleniyor...</p>
            ) : (
              <div className="space-y-2" data-testid="admin-users-deleted-lifecycle-list">
                {deletedLifecycle.slice(0, 12).map((item) => (
                  <div key={item.user_id} className="space-y-1 border border-black/10 p-2" data-testid={`admin-users-deleted-lifecycle-item-${item.user_id}`}>
                    <p className="text-[11px] font-semibold" data-testid={`admin-users-deleted-lifecycle-email-${item.user_id}`}>{item.email}</p>
                    <p className="text-[11px]" data-testid={`admin-users-deleted-lifecycle-deleted-at-${item.user_id}`}>deleted_at={item.deleted_at || "-"}</p>
                    <p className="text-[11px]" data-testid={`admin-users-deleted-lifecycle-retention-${item.user_id}`}>retention_days_remaining={item.retention_days_remaining ?? 0}</p>
                    <p className="text-[11px]" data-testid={`admin-users-deleted-lifecycle-risk-${item.user_id}`}>risk_score={item.risk_score ?? 0}</p>
                    <p className="text-[11px] text-black/75" data-testid={`admin-users-deleted-lifecycle-blockers-${item.user_id}`}>
                      blockers={(item.blockers || []).join(", ") || "-"}
                    </p>
                    <div className="flex flex-wrap gap-2" data-testid={`admin-users-deleted-lifecycle-actions-${item.user_id}`}>
                      <Button size="sm" variant="outline" onClick={() => setSelectedDeletedLifecycleUser(item)} data-testid={`admin-users-deleted-lifecycle-detail-button-${item.user_id}`}>
                        Detail
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => requestRestoreUser(item.user_id)} data-testid={`admin-users-deleted-lifecycle-restore-button-${item.user_id}`}>
                        Restore Req
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => requestHardDelete({ id: item.user_id })} data-testid={`admin-users-deleted-lifecycle-hard-delete-button-${item.user_id}`}>
                        Hard Delete Req
                      </Button>
                    </div>
                  </div>
                ))}
                {deletedLifecycle.length === 0 && (
                  <p className="text-xs text-black/70" data-testid="admin-users-deleted-lifecycle-empty-text">Deleted kullanıcı bulunamadı.</p>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {selectedDeletedLifecycleUser && (
        <div className="space-y-2 border border-black/30 bg-orange-50 p-3" data-testid="admin-users-delete-detail-panel">
          <div className="flex items-center justify-between" data-testid="admin-users-delete-detail-header-row">
            <p className="text-sm font-semibold" data-testid="admin-users-delete-detail-title">Delete Detail: {selectedDeletedLifecycleUser.email}</p>
            <Button variant="outline" onClick={() => setSelectedDeletedLifecycleUser(null)} data-testid="admin-users-delete-detail-close-button">Kapat</Button>
          </div>
          <div className="grid gap-2 border border-black/20 bg-white p-2 text-xs" data-testid="admin-users-delete-detail-grid">
            <p data-testid="admin-users-delete-detail-user-id">user_id: {selectedDeletedLifecycleUser.user_id}</p>
            <p data-testid="admin-users-delete-detail-deleted-at">deleted_at: {selectedDeletedLifecycleUser.deleted_at || "-"}</p>
            <p data-testid="admin-users-delete-detail-retention">retention_days_remaining: {selectedDeletedLifecycleUser.retention_days_remaining ?? 0}</p>
            <p data-testid="admin-users-delete-detail-hard-delete-eligible">eligible_for_hard_delete: {String(Boolean(selectedDeletedLifecycleUser.eligible_for_hard_delete))}</p>
            <p data-testid="admin-users-delete-detail-risk-score">risk_score: {selectedDeletedLifecycleUser.risk_score ?? 0}</p>
            <p data-testid="admin-users-delete-detail-blockers">blockers: {(selectedDeletedLifecycleUser.blockers || []).join(", ") || "-"}</p>
          </div>
        </div>
      )}

      {securityDetailUserId && (
        <div className="space-y-2 border border-black/30 bg-orange-50 p-3" data-testid="admin-users-security-detail-panel">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold" data-testid="admin-users-security-detail-title">Security Detail: {securityDetail?.email || securityDetailUserId}</p>
            <Button variant="outline" onClick={() => setSecurityDetailUserId("")} data-testid="admin-users-security-detail-close-button">Kapat</Button>
          </div>

          {securityDetailLoading ? (
            <div className="space-y-2" data-testid="admin-users-security-detail-loading-state">
              <p className="text-xs" data-testid="admin-users-security-detail-loading">Yükleniyor...</p>
              <div className="h-14 animate-pulse border border-black/10 bg-orange-100" data-testid="admin-users-security-detail-skeleton"></div>
            </div>
          ) : securityDetailError ? (
            <div className="space-y-2" data-testid="admin-users-security-detail-error-state">
              <p className="text-xs text-red-700" data-testid="admin-users-security-detail-error-text">{securityDetailError}</p>
              <Button size="sm" variant="outline" onClick={() => loadSecurityDetail(securityDetailUserId)} data-testid="admin-users-security-detail-retry-button">Retry</Button>
            </div>
          ) : securityDetail ? (
            <div className="space-y-3">
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

              <div className="space-y-2 border border-black/25 bg-white p-2" data-testid="admin-users-observability-panel">
                <div className="flex flex-wrap items-center justify-between gap-2" data-testid="admin-users-observability-header-row">
                  <p className="text-xs font-semibold" data-testid="admin-users-observability-title">User Observability</p>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => loadUserObservability(securityDetailUserId)}
                    data-testid="admin-users-observability-refresh-button"
                  >
                    Yenile
                  </Button>
                </div>

                {observabilityLoading ? (
                  <div className="grid gap-2 md:grid-cols-2" data-testid="admin-users-observability-skeleton-grid">
                    <div className="h-20 animate-pulse border border-black/10 bg-orange-100" data-testid="admin-users-observability-skeleton-1"></div>
                    <div className="h-20 animate-pulse border border-black/10 bg-orange-100" data-testid="admin-users-observability-skeleton-2"></div>
                    <div className="h-20 animate-pulse border border-black/10 bg-orange-100" data-testid="admin-users-observability-skeleton-3"></div>
                    <div className="h-20 animate-pulse border border-black/10 bg-orange-100" data-testid="admin-users-observability-skeleton-4"></div>
                  </div>
                ) : observabilityError ? (
                  <div className="space-y-2" data-testid="admin-users-observability-error-state">
                    <p className="text-xs text-red-700" data-testid="admin-users-observability-error-text">{observabilityError}</p>
                    <Button size="sm" variant="outline" onClick={() => loadUserObservability(securityDetailUserId)} data-testid="admin-users-observability-retry-button">Retry</Button>
                  </div>
                ) : (
                  <div className="grid gap-2 md:grid-cols-2" data-testid="admin-users-observability-grid">
                    <div className="space-y-1 border border-black/15 p-2 text-xs" data-testid="admin-users-observability-activity-card">
                      <p className="font-semibold">Activity Timeline</p>
                      <p data-testid="admin-users-observability-activity-summary">24h={activityTimeline?.summary?.["24h"] ?? 0} · 7d={activityTimeline?.summary?.["7d"] ?? 0} · 30d={activityTimeline?.summary?.["30d"] ?? 0}</p>
                      {(activityTimeline?.items || []).slice(0, 5).map((item, idx) => (
                        <p key={`${item.timestamp}-${idx}`} data-testid={`admin-users-observability-activity-item-${idx}`}>{item.timestamp} · {item.event} · {item.severity}</p>
                      ))}
                      {(activityTimeline?.items || []).length === 0 && <p data-testid="admin-users-observability-activity-empty">Activity empty state</p>}
                    </div>

                    <div className="space-y-1 border border-black/15 p-2 text-xs" data-testid="admin-users-observability-security-card">
                      <p className="font-semibold">Security Telemetry</p>
                      <p data-testid="admin-users-observability-security-failed-trend">failed_24h={securityTelemetry?.failed_login_trend?.["24h"] ?? 0} · suspicious={String(Boolean(securityTelemetry?.ip_device_anomaly_summary?.suspicious))}</p>
                      <p data-testid="admin-users-observability-security-severity">severity={securityTelemetry?.normalized_severity || "low"} · risk={securityTelemetry?.normalized_risk_score ?? 0}</p>
                      <p data-testid="admin-users-observability-security-signals">signals={(securityTelemetry?.high_risk_signals || []).map((signal) => signal.signal).join(", ") || "-"}</p>
                      <p data-testid="admin-users-observability-security-mfa-failures">recent_mfa_failures={(securityTelemetry?.recent_mfa_failures || []).length}</p>
                      {renderTrendChart(securityTelemetry?.failed_login_trend, "admin-users-observability-security")}
                    </div>

                    <div className="space-y-1 border border-black/15 p-2 text-xs" data-testid="admin-users-observability-execution-card">
                      <p className="font-semibold">Execution & Reliability</p>
                      <p data-testid="admin-users-observability-execution-success-rate">success_rate={executionMetrics?.execution_success_rate ?? 0}%</p>
                      <p data-testid="admin-users-observability-execution-error-count">error_count={executionMetrics?.execution_error_count ?? 0}</p>
                      <p data-testid="admin-users-observability-execution-latency">latency_avg={executionMetrics?.execution_latency_summary?.avg_ms ?? 0}ms · p95={executionMetrics?.execution_latency_summary?.p95_ms ?? 0}ms</p>
                      <p data-testid="admin-users-observability-execution-errors">error_categories={(executionMetrics?.recent_error_categories || []).map((item) => `${item.code}:${item.count}`).join(", ") || "-"}</p>
                      {renderTrendChart(executionMetrics?.window_summary, "admin-users-observability-execution")}
                    </div>

                    <div className="space-y-1 border border-black/15 p-2 text-xs" data-testid="admin-users-observability-trading-card">
                      <p className="font-semibold">Trading Observability</p>
                      <p data-testid="admin-users-observability-trading-summary-card">
                        trade_summary_count={(tradingObservability?.recent_trade_count?.["24h"] ?? 0) + (tradingObservability?.recent_trade_count?.["7d"] ?? 0)} · state={Boolean(tradingObservability?.live_trading_status?.trading_enabled) ? "live" : "paused"}
                      </p>
                      <p data-testid="admin-users-observability-trading-live-status">trading_enabled={String(Boolean(tradingObservability?.live_trading_status?.trading_enabled))} · live_eligible={String(Boolean(tradingObservability?.live_trading_status?.live_trading_eligible))}</p>
                      <p data-testid="admin-users-observability-trading-trade-count">trade_24h={tradingObservability?.recent_trade_count?.["24h"] ?? 0} · trade_7d={tradingObservability?.recent_trade_count?.["7d"] ?? 0}</p>
                      <p data-testid="admin-users-observability-trading-impact">strategy={tradingObservability?.impact_summary?.strategy_scope_count ?? 0} · bot={tradingObservability?.impact_summary?.bot_scope_count ?? 0} · account={tradingObservability?.impact_summary?.account_mapping_count ?? 0}</p>
                      {renderTrendChart(tradingObservability?.recent_trade_count, "admin-users-observability-trading")}
                      <a href={tradingObservability?.trade_history_link || "#"} className="underline" data-testid="admin-users-observability-trade-history-link">Trade History Link</a>
                    </div>
                  </div>
                )}
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
