import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

const WORKFLOW_STEP_LABELS = {
  ops: "OPS",
  risk: "RISK",
  final: "FINAL",
  completed: "TAMAMLANDI",
};

const COMPLETABLE_STEPS = new Set(["ops", "risk", "final"]);

const buildWorkflowMap = (items) => {
  const next = {};
  (items || []).forEach((item) => {
    if (item?.user_id) {
      next[item.user_id] = item;
    }
  });
  return next;
};

const getSlaMeta = (slaDueAt, nowMs) => {
  if (!slaDueAt) {
    return { label: "SLA yok", className: "border-slate-300 bg-slate-100 text-slate-700" };
  }
  const diffMs = new Date(slaDueAt).getTime() - nowMs;
  const absoluteMinutes = Math.max(0, Math.floor(Math.abs(diffMs) / 60000));
  if (diffMs < 0) {
    return {
      label: `Gecikme: ${absoluteMinutes} dk`,
      className: "border-red-300 bg-red-100 text-red-700",
    };
  }
  if (absoluteMinutes <= 5) {
    return { label: `${absoluteMinutes} dk kaldı`, className: "border-red-300 bg-red-100 text-red-700" };
  }
  if (absoluteMinutes <= 15) {
    return { label: `${absoluteMinutes} dk kaldı`, className: "border-amber-300 bg-amber-100 text-amber-800" };
  }
  return { label: `${absoluteMinutes} dk kaldı`, className: "border-emerald-300 bg-emerald-100 text-emerald-800" };
};

const formatDateTime = (value) => {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleString();
};

export const AdminUserApprovalsPage = () => {
  const [requests, setRequests] = useState([]);
  const [contexts, setContexts] = useState({});
  const [workflowByUser, setWorkflowByUser] = useState({});
  const [loading, setLoading] = useState(false);
  const [busyActionKey, setBusyActionKey] = useState(null);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("requested_at");
  const [sortDir, setSortDir] = useState("asc");
  const [selectedIds, setSelectedIds] = useState([]);
  const [decisionReason, setDecisionReason] = useState("");
  const [emailSuggestions, setEmailSuggestions] = useState([]);
  const [activeDecisionUserId, setActiveDecisionUserId] = useState(null);
  const [clockMs, setClockMs] = useState(Date.now());

  const refreshWorkflowQueue = useCallback(async () => {
    const { data } = await apiClient.get("/admin/onboarding/workflow/queue");
    setWorkflowByUser(buildWorkflowMap(data?.items || []));
  }, []);

  const loadRequests = useCallback(async () => {
    setLoading(true);
    try {
      const [approvalsResult, workflowResult] = await Promise.allSettled([
        apiClient.get("/admin/user-approvals", {
          params: {
            status: "pending",
            search: search || undefined,
            sort_by: sortBy,
            sort_dir: sortDir,
          },
        }),
        apiClient.get("/admin/onboarding/workflow/queue"),
      ]);

      if (approvalsResult.status === "rejected") {
        throw approvalsResult.reason;
      }

      const list = approvalsResult.value?.data || [];
      setRequests(list);
      setSelectedIds((prev) => prev.filter((id) => list.some((item) => item.id === id)));

      if (workflowResult.status === "fulfilled") {
        setWorkflowByUser(buildWorkflowMap(workflowResult.value?.data?.items || []));
      }
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Onay talepleri alınamadı");
    } finally {
      setLoading(false);
    }
  }, [search, sortBy, sortDir]);

  useEffect(() => {
    loadRequests();
  }, [loadRequests]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setClockMs(Date.now());
    }, 30000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const timer = setTimeout(async () => {
      try {
        const { data } = await apiClient.get("/admin/user-approvals/email-suggestions", {
          params: { query: search || "", limit: 8 },
        });
        setEmailSuggestions(data?.suggestions || []);
      } catch {
        setEmailSuggestions([]);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [search]);

  const allSelected = useMemo(
    () => requests.length > 0 && selectedIds.length === requests.length,
    [requests, selectedIds],
  );

  const toggleSelectAll = () => {
    if (allSelected) {
      setSelectedIds([]);
    } else {
      setSelectedIds(requests.map((item) => item.id));
    }
  };

  const toggleSelection = (userId) => {
    setSelectedIds((prev) => (prev.includes(userId) ? prev.filter((id) => id !== userId) : [...prev, userId]));
  };

  const loadContext = async (userId) => {
    try {
      const [contextResult, workflowResult] = await Promise.allSettled([
        apiClient.get(`/admin/onboarding/${userId}/context`),
        apiClient.get(`/admin/onboarding/${userId}/workflow`),
      ]);

      if (contextResult.status === "rejected") {
        throw contextResult.reason;
      }

      const contextPayload = contextResult.value?.data;
      setContexts((prev) => ({ ...prev, [userId]: contextPayload }));

      if (workflowResult.status === "fulfilled") {
        const workflowCase = workflowResult.value?.data?.workflow_case;
        setWorkflowByUser((prev) => {
          const next = { ...prev };
          if (workflowCase?.workflow_case_id) {
            next[userId] = {
              workflow_case_id: workflowCase.workflow_case_id,
              user_id: userId,
              current_step: workflowCase.current_step,
              assigned_admin_id: workflowCase.assigned_admin_id,
              priority_score: workflowCase.priority_score,
              sla_due_at: workflowCase.sla_due_at,
              supervisor_queue: workflowCase.supervisor_queue,
              workflow_status: workflowCase.workflow_status,
              escalated_at: workflowCase.escalated_at,
            };
          } else {
            delete next[userId];
          }
          return next;
        });
      }

      return contextPayload;
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Onboarding context alınamadı");
      return null;
    }
  };

  const requireReason = () => {
    if (decisionReason.trim().length < 5) {
      toast.error("Decision reason zorunlu (min 5 karakter)");
      return false;
    }
    return true;
  };

  const handleBulkReject = async () => {
    if (selectedIds.length === 0) {
      toast.error("En az bir kullanıcı seçin");
      return;
    }
    if (!requireReason()) return;
    const confirmed = window.confirm(`${selectedIds.length} kullanıcı reject edilsin mi?`);
    if (!confirmed) return;
    try {
      await apiClient.post("/admin/user-approvals/bulk-reject", {
        ids: selectedIds,
        reason: decisionReason.trim(),
        confirm_token: "CONFIRM",
      });
      toast.success("Seçili kullanıcılar reject edildi");
      setSelectedIds([]);
      await loadRequests();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Bulk reject başarısız");
    }
  };

  const handleSingleApprove = async (userId) => {
    if (!requireReason()) return;
    const context = contexts[userId] || (await loadContext(userId));
    if (!context) return;
    if (context.approval_disabled) {
      toast.error(`Approval disabled: ${(context.approval_disable_reasons || []).join(", ")}`);
      return;
    }

    const confirmed = window.confirm("Auto-approve kararı uygulansın mı? (double confirm)");
    if (!confirmed) return;
    try {
      await apiClient.post(`/admin/onboarding/${userId}/decision/auto-approve`, {
        decision: "approve",
        reason: decisionReason.trim(),
        confirm_token: "CONFIRM",
      });
      toast.success("Kullanıcı approve edildi");
      await loadRequests();
      setContexts((prev) => {
        const next = { ...prev };
        delete next[userId];
        return next;
      });
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Approve işlemi başarısız");
    }
  };

  const handleSingleReject = async (userId) => {
    if (!requireReason()) return;
    const confirmed = window.confirm("Kullanıcı reject edilsin mi? (double confirm)");
    if (!confirmed) return;
    try {
      await apiClient.post(`/admin/onboarding/${userId}/decision`, {
        decision: "reject",
        reason: decisionReason.trim(),
        confirm_token: "CONFIRM",
      });
      toast.success("Kullanıcı reject edildi");
      await loadRequests();
      setContexts((prev) => {
        const next = { ...prev };
        delete next[userId];
        return next;
      });
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Reject işlemi başarısız");
    }
  };

  const handleStartWorkflow = async (userId) => {
    setBusyActionKey(`start-${userId}`);
    try {
      await apiClient.post(`/admin/onboarding/${userId}/workflow/start`, {
        assigned_admin_id: null,
      });
      await refreshWorkflowQueue();
      await loadContext(userId);
      toast.success("Workflow başlatıldı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Workflow başlatılamadı");
    } finally {
      setBusyActionKey(null);
    }
  };

  const handleCompleteStep = async (userId) => {
    const workflow = workflowByUser[userId];
    const currentStep = String(workflow?.current_step || "").toLowerCase();
    if (!COMPLETABLE_STEPS.has(currentStep)) {
      toast.error("Tamamlanabilir aktif adım bulunamadı");
      return;
    }
    setBusyActionKey(`complete-${userId}`);
    try {
      await apiClient.post(`/admin/onboarding/${userId}/workflow/steps/${currentStep}/complete`, {
        note: decisionReason.trim() || `ui_step_complete_${currentStep}`,
      });
      await refreshWorkflowQueue();
      await loadContext(userId);
      toast.success(`${WORKFLOW_STEP_LABELS[currentStep] || currentStep} adımı tamamlandı`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Workflow adımı tamamlanamadı");
    } finally {
      setBusyActionKey(null);
    }
  };

  const openDecisionSupport = async (userId) => {
    if (!contexts[userId]) {
      const payload = await loadContext(userId);
      if (!payload) {
        return;
      }
    }
    setActiveDecisionUserId(userId);
  };

  const activeDecisionContext = activeDecisionUserId ? contexts[activeDecisionUserId] : null;

  const handleRejectStale = async () => {
    if (!requireReason()) return;
    const confirmed = window.confirm("30 günden eski pending talepler reject edilsin mi?");
    if (!confirmed) return;
    try {
      const { data } = await apiClient.post("/admin/user-approvals/reject-stale", {
        stale_days: 30,
        reason: decisionReason.trim(),
      });
      toast.success(`${data?.count || 0} stale talep reject edildi`);
      await loadRequests();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Stale reject başarısız");
    }
  };

  return (
    <section className="space-y-4" data-testid="admin-user-approvals-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="admin-user-approvals-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-black" data-testid="admin-user-approvals-title">
          Kullanıcı Onay Merkezi
        </h2>
        <p className="mt-2 text-sm text-black/70" data-testid="admin-user-approvals-description">
          Yeni kayıt olan kullanıcılar burada bekler. Onay sonrası user panel girişine izin verilir.
        </p>
      </header>

      <div className="border border-black/30 bg-orange-100 p-4" data-testid="admin-user-approvals-toolbar">
        <div className="grid gap-2 md:grid-cols-3" data-testid="admin-user-approvals-filter-grid">
          <Input
            placeholder="Search email"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            list="admin-user-approvals-email-suggestions"
            data-testid="admin-user-approvals-search-input"
          />
          <datalist id="admin-user-approvals-email-suggestions" data-testid="admin-user-approvals-email-suggestions-list">
            {emailSuggestions.map((item, index) => (
              <option key={item} value={item} data-testid={`admin-user-approvals-email-suggestion-${index}`}>
                {item}
              </option>
            ))}
          </datalist>
          <select
            className="border border-black/40 bg-white px-3 py-2 text-sm"
            value={sortBy}
            onChange={(event) => setSortBy(event.target.value)}
            data-testid="admin-user-approvals-sort-by"
          >
            <option value="requested_at">requested_at</option>
            <option value="email">email</option>
          </select>
          <select
            className="border border-black/40 bg-white px-3 py-2 text-sm"
            value={sortDir}
            onChange={(event) => setSortDir(event.target.value)}
            data-testid="admin-user-approvals-sort-dir"
          >
            <option value="asc">asc</option>
            <option value="desc">desc</option>
          </select>
        </div>
        <div className="mt-3 flex flex-wrap gap-2" data-testid="admin-user-approvals-bulk-actions">
          <Button
            className="border border-black bg-orange-500 text-black hover:bg-orange-600"
            onClick={loadRequests}
            data-testid="admin-user-approvals-refresh-button"
          >
            Yenile
          </Button>
          <Button
            className="border border-black bg-black text-orange-400 hover:bg-zinc-800"
            disabled
            data-testid="admin-user-approvals-bulk-approve-button"
          >
            Bulk Approve (Disabled)
          </Button>
          <Button
            className="border border-black bg-red-600 text-white hover:bg-red-700"
            onClick={handleBulkReject}
            data-testid="admin-user-approvals-bulk-reject-button"
          >
            Bulk Reject
          </Button>
          <Button
            className="border border-black bg-amber-500 text-black hover:bg-amber-600"
            onClick={handleRejectStale}
            data-testid="admin-user-approvals-reject-stale-button"
          >
            Reject Stale (&gt;30g)
          </Button>
          <Input
            placeholder="Decision reason (approve/reject için zorunlu)"
            value={decisionReason}
            onChange={(event) => setDecisionReason(event.target.value)}
            className="max-w-[320px]"
            data-testid="admin-user-approvals-decision-reason-input"
          />
        </div>
        <p className="mt-2 text-sm text-black" data-testid="admin-user-approvals-count">
          Bekleyen Talep: {requests.length} · Seçili: {selectedIds.length}
        </p>
      </div>

      <div className="border border-black/30 bg-orange-100" data-testid="admin-user-approvals-table-wrapper">
        <Table data-testid="admin-user-approvals-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="admin-approvals-head-select">
                <Checkbox
                  checked={allSelected}
                  onCheckedChange={toggleSelectAll}
                  data-testid="admin-approvals-select-all"
                />
              </TableHead>
              <TableHead data-testid="admin-approvals-head-email">E-posta</TableHead>
              <TableHead data-testid="admin-approvals-head-status">Durum</TableHead>
              <TableHead data-testid="admin-approvals-head-risk">Risk/KYC</TableHead>
              <TableHead data-testid="admin-approvals-head-workflow">Workflow</TableHead>
              <TableHead data-testid="admin-approvals-head-sla">SLA</TableHead>
              <TableHead data-testid="admin-approvals-head-requested">Talep Zamanı</TableHead>
              <TableHead data-testid="admin-approvals-head-action">Aksiyon</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {requests.map((item) => (
              <TableRow key={item.id} data-testid={`admin-approval-row-${item.id}`}>
                <TableCell data-testid={`admin-approval-select-${item.id}`}>
                  <Checkbox
                    checked={selectedIds.includes(item.id)}
                    onCheckedChange={() => toggleSelection(item.id)}
                    data-testid={`admin-approval-checkbox-${item.id}`}
                  />
                </TableCell>
                <TableCell data-testid={`admin-approval-email-${item.id}`}>{item.email}</TableCell>
                <TableCell data-testid={`admin-approval-status-${item.id}`}>{item.approval_status}</TableCell>
                <TableCell data-testid={`admin-approval-risk-${item.id}`}>
                  <div className="text-xs">
                    <div>KYC: {contexts[item.id]?.kyc_status || "-"}</div>
                    <div>Risk: {contexts[item.id]?.risk_score ?? "-"}</div>
                    <div>AML: {contexts[item.id]?.aml_flag || "-"}</div>
                  </div>
                </TableCell>
                <TableCell data-testid={`admin-approval-workflow-${item.id}`}>
                  {workflowByUser[item.id] ? (
                    <div className="space-y-1 text-xs" data-testid={`admin-approval-workflow-box-${item.id}`}>
                      <Badge
                        className="border border-black/20 bg-white text-black"
                        data-testid={`admin-approval-workflow-step-badge-${item.id}`}
                      >
                        {WORKFLOW_STEP_LABELS[String(workflowByUser[item.id]?.current_step || "").toLowerCase()] || String(workflowByUser[item.id]?.current_step || "-").toUpperCase()}
                      </Badge>
                      <div data-testid={`admin-approval-workflow-priority-${item.id}`}>
                        Öncelik: {workflowByUser[item.id]?.priority_score ?? "-"}
                      </div>
                      <div data-testid={`admin-approval-workflow-owner-${item.id}`}>
                        Atanan: {workflowByUser[item.id]?.assigned_admin_id || "-"}
                      </div>
                      {(workflowByUser[item.id]?.supervisor_queue || workflowByUser[item.id]?.workflow_status === "escalated") && (
                        <Badge
                          variant="destructive"
                          className="mt-1"
                          data-testid={`admin-approval-workflow-escalated-badge-${item.id}`}
                        >
                          Escalated
                        </Badge>
                      )}
                    </div>
                  ) : (
                    <Badge variant="outline" data-testid={`admin-approval-workflow-empty-badge-${item.id}`}>
                      Workflow yok
                    </Badge>
                  )}
                </TableCell>
                <TableCell data-testid={`admin-approval-sla-${item.id}`}>
                  {(() => {
                    const slaMeta = getSlaMeta(workflowByUser[item.id]?.sla_due_at, clockMs);
                    return (
                      <div className="space-y-1 text-xs" data-testid={`admin-approval-sla-box-${item.id}`}>
                        <span
                          className={`inline-flex rounded border px-2 py-0.5 font-semibold ${slaMeta.className}`}
                          data-testid={`admin-approval-sla-countdown-${item.id}`}
                        >
                          {slaMeta.label}
                        </span>
                        <div className="text-black/70" data-testid={`admin-approval-sla-due-at-${item.id}`}>
                          Due: {formatDateTime(workflowByUser[item.id]?.sla_due_at)}
                        </div>
                      </div>
                    );
                  })()}
                </TableCell>
                <TableCell data-testid={`admin-approval-requested-at-${item.id}`}>
                  {new Date(item.approval_requested_at).toLocaleString()}
                </TableCell>
                <TableCell data-testid={`admin-approval-actions-${item.id}`}>
                  <div className="flex flex-wrap gap-2" data-testid={`admin-approval-action-buttons-${item.id}`}>
                    <Button
                      size="sm"
                      className="border border-black bg-white text-black hover:bg-zinc-100"
                      onClick={() => loadContext(item.id)}
                      data-testid={`admin-approval-context-button-${item.id}`}
                    >
                      Context
                    </Button>
                    <Button
                      size="sm"
                      className="border border-black bg-indigo-100 text-indigo-900 hover:bg-indigo-200"
                      onClick={() => openDecisionSupport(item.id)}
                      data-testid={`admin-approval-decision-support-button-${item.id}`}
                    >
                      Decision Support
                    </Button>
                    {!workflowByUser[item.id] ? (
                      <Button
                        size="sm"
                        className="border border-black bg-lime-200 text-black hover:bg-lime-300"
                        onClick={() => handleStartWorkflow(item.id)}
                        disabled={busyActionKey === `start-${item.id}`}
                        data-testid={`admin-approval-workflow-start-button-${item.id}`}
                      >
                        {busyActionKey === `start-${item.id}` ? "Başlatılıyor..." : "Start Workflow"}
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        className="border border-black bg-blue-100 text-blue-900 hover:bg-blue-200"
                        onClick={() => handleCompleteStep(item.id)}
                        disabled={!COMPLETABLE_STEPS.has(String(workflowByUser[item.id]?.current_step || "").toLowerCase()) || busyActionKey === `complete-${item.id}`}
                        data-testid={`admin-approval-workflow-complete-step-button-${item.id}`}
                      >
                        {busyActionKey === `complete-${item.id}` ? "Tamamlanıyor..." : "Complete Step"}
                      </Button>
                    )}
                    <Button
                      size="sm"
                      className="border border-black bg-black text-orange-400 hover:bg-zinc-800"
                      onClick={() => handleSingleApprove(item.id)}
                      data-testid={`admin-approval-approve-button-${item.id}`}
                    >
                      Approve
                    </Button>
                    <Button
                      size="sm"
                      className="border border-black bg-red-600 text-white hover:bg-red-700"
                      onClick={() => handleSingleReject(item.id)}
                      data-testid={`admin-approval-reject-button-${item.id}`}
                    >
                      Reject
                    </Button>
                  </div>
                  {contexts[item.id]?.approval_disabled && (
                    <p className="mt-2 text-xs text-red-700" data-testid={`admin-approval-disable-reasons-${item.id}`}>
                      Disabled: {(contexts[item.id]?.approval_disable_reasons || []).join(", ")}
                    </p>
                  )}
                  {contexts[item.id]?.decision_engine?.why_approving && (
                    <p className="mt-1 text-xs text-black/70" data-testid={`admin-approval-why-${item.id}`}>
                      Why: {contexts[item.id]?.decision_engine?.why_approving}
                    </p>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {!loading && requests.length === 0 && (
              <TableRow data-testid="admin-approval-empty-row">
                <TableCell colSpan={8} className="text-center text-sm text-black/70" data-testid="admin-approval-empty-text">
                  Bekleyen kullanıcı talebi bulunmuyor.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <Sheet open={Boolean(activeDecisionUserId)} onOpenChange={(open) => !open && setActiveDecisionUserId(null)}>
        <SheetContent className="overflow-y-auto" side="right" data-testid="admin-approval-decision-support-drawer">
          <SheetHeader data-testid="admin-approval-decision-support-header">
            <SheetTitle data-testid="admin-approval-decision-support-title">Decision Support</SheetTitle>
            <SheetDescription data-testid="admin-approval-decision-support-description">
              Workflow karar destek özeti · Kullanıcı: {activeDecisionUserId || "-"}
            </SheetDescription>
          </SheetHeader>

          <div className="mt-6 space-y-4" data-testid="admin-approval-decision-support-content">
            <div className="rounded border border-black/20 bg-white p-3" data-testid="admin-approval-decision-support-recommendation-card">
              <p className="text-xs uppercase tracking-wide text-black/60" data-testid="admin-approval-decision-support-recommendation-label">
                Önerilen Aksiyon
              </p>
              <p className="mt-1 text-base font-semibold" data-testid="admin-approval-decision-support-recommended-action">
                {activeDecisionContext?.decision_support?.recommended_action || "-"}
              </p>
              <p className="mt-1 text-sm text-black/70" data-testid="admin-approval-decision-support-confidence">
                Confidence: {activeDecisionContext?.decision_support?.confidence ?? "-"}
              </p>
            </div>

            <div className="rounded border border-black/20 bg-white p-3" data-testid="admin-approval-decision-support-summary-card">
              <p className="text-xs uppercase tracking-wide text-black/60" data-testid="admin-approval-decision-support-summary-label">
                Human Readable Summary
              </p>
              <p className="mt-1 text-sm" data-testid="admin-approval-decision-support-summary">
                {activeDecisionContext?.decision_support?.human_readable_summary || "-"}
              </p>
              <p className="mt-2 text-sm" data-testid="admin-approval-decision-support-why">
                Why: {activeDecisionContext?.decision_engine?.why_approving || "-"}
              </p>
            </div>

            <div className="rounded border border-black/20 bg-white p-3" data-testid="admin-approval-decision-support-reason-codes-card">
              <p className="text-xs uppercase tracking-wide text-black/60" data-testid="admin-approval-decision-support-reason-codes-label">
                Reason Codes
              </p>
              <div className="mt-2 flex flex-wrap gap-2" data-testid="admin-approval-decision-support-reason-codes-list">
                {(activeDecisionContext?.decision_support?.reason_codes || []).length === 0 && (
                  <Badge variant="outline" data-testid="admin-approval-decision-support-reason-code-empty">
                    reason code yok
                  </Badge>
                )}
                {(activeDecisionContext?.decision_support?.reason_codes || []).map((code, index) => (
                  <Badge
                    key={`${code}-${index}`}
                    variant="secondary"
                    className="bg-slate-100 text-slate-800"
                    data-testid={`admin-approval-decision-support-reason-code-${index}`}
                  >
                    {code}
                  </Badge>
                ))}
              </div>
            </div>

            <Button
              type="button"
              className="w-full border border-black bg-black text-orange-300 hover:bg-zinc-900"
              onClick={() => setActiveDecisionUserId(null)}
              data-testid="admin-approval-decision-support-close-button"
            >
              Kapat
            </Button>
          </div>
        </SheetContent>
      </Sheet>
    </section>
  );
};
