import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";

const policySeed = {
  reference_equity_usd: 10000,
  account_max_notional_pct: 60,
  symbol_max_notional_pct: 25,
  strategy_max_concurrent_positions: 3,
  strategy_cooldown_seconds: 60,
  max_order_frequency_per_min: 6,
  max_order_burst_per_10s: 3,
  daily_loss_limit_pct: 5,
  duplicate_suppression_window_seconds: 300,
};

const overrideSeed = {
  override_type: "symbol",
  target_key: "",
  max_notional_pct: "",
  max_open_count: "",
  block_new_adds: false,
  expires_in_minutes: "60",
  reason_note: "",
};

const controlReasonSeed = {
  kill_switch: "",
  global_trading_pause: "",
  force_risk_check: "",
};

const toNumberOrNull = (value) => {
  if (value === "" || value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const buildRejectQuery = (filters) => {
  const params = new URLSearchParams();
  params.set("limit", "50");
  if (filters.reason_code) params.set("reason_code", filters.reason_code);
  if (filters.symbol) params.set("symbol", filters.symbol);
  if (filters.strategy_id) params.set("strategy_id", filters.strategy_id);
  return params.toString();
};

const buildQueueQuery = ({ scope, state, criticalFirst }) => {
  const params = new URLSearchParams();
  params.set("limit", "50");
  params.set("scope", scope);
  params.set("critical_first", criticalFirst ? "true" : "false");
  if (state) params.set("state", state);
  return params.toString();
};

export const AdminRiskOrchestratorPage = () => {
  const { user } = useAuth();
  const isSuperAdmin = user?.role === "super_admin";
  const [activeTab, setActiveTab] = useState("risk-gate");

  const [loading, setLoading] = useState(true);
  const [policy, setPolicy] = useState(policySeed);
  const [status, setStatus] = useState(null);
  const [simulation, setSimulation] = useState(null);
  const [history, setHistory] = useState({ versions: [], change_requests: [] });
  const [applyReason, setApplyReason] = useState("");
  const [applyNote, setApplyNote] = useState("");
  const [doubleConfirm, setDoubleConfirm] = useState(false);
  const [applyDialogOpen, setApplyDialogOpen] = useState(false);

  const [overrideForm, setOverrideForm] = useState(overrideSeed);
  const [overrides, setOverrides] = useState([]);

  const [controlReasons, setControlReasons] = useState(controlReasonSeed);
  const [supervisor, setSupervisor] = useState(null);
  const [positions, setPositions] = useState([]);
  const [interventionState, setInterventionState] = useState({
    position_id: "",
    action_type: "reduce_position",
    reason_note: "",
    reduce_ratio: "0.5",
    expires_in_minutes: "60",
  });

  const [rejectFilters, setRejectFilters] = useState({ reason_code: "", symbol: "", strategy_id: "" });
  const [rejects, setRejects] = useState([]);
  const [rejectDetail, setRejectDetail] = useState(null);
  const [rejectDialogOpen, setRejectDialogOpen] = useState(false);

  const [autoTriggers, setAutoTriggers] = useState([]);
  const [timeline, setTimeline] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [approvals, setApprovals] = useState([]);
  const [decisionTraces, setDecisionTraces] = useState([]);
  const [approvalNotes, setApprovalNotes] = useState({});
  const [assignmentInputs, setAssignmentInputs] = useState({});
  const [applyWithOverride, setApplyWithOverride] = useState(false);
  const [lastApplyResult, setLastApplyResult] = useState(null);
  const [revertSimulations, setRevertSimulations] = useState({});
  const [queueScope, setQueueScope] = useState("all");
  const [queueState, setQueueState] = useState("pending");
  const [criticalFirst, setCriticalFirst] = useState(true);
  const [dashboardData, setDashboardData] = useState(null);
  const [rejectInsights, setRejectInsights] = useState([]);
  const [decisionIntelligence, setDecisionIntelligence] = useState(null);
  const [sweepResult, setSweepResult] = useState(null);

  const refreshCore = useCallback(async () => {
    const queueQuery = buildQueueQuery({ scope: queueScope, state: queueState, criticalFirst });
    const [
      policyRes,
      statusRes,
      historyRes,
      overrideRes,
      positionRes,
      triggerRes,
      timelineRes,
      alertsRes,
      approvalsRes,
      tracesRes,
      dashboardRes,
      insightsRes,
    ] = await Promise.all([
      apiClient.get("/strategy-domain/admin/risk-orchestrator/policy"),
      apiClient.get("/strategy-domain/admin/risk-orchestrator/status"),
      apiClient.get("/strategy-domain/admin/risk-orchestrator/policy/history?limit=20"),
      apiClient.get("/strategy-domain/admin/risk-orchestrator/exposure/overrides?active_only=true"),
      apiClient.get("/strategy-domain/admin/risk-orchestrator/supervisor/positions?limit=50"),
      apiClient.get("/strategy-domain/admin/risk-orchestrator/auto-trigger-logs?limit=30"),
      apiClient.get("/strategy-domain/admin/risk-orchestrator/audit/timeline?limit=40"),
      apiClient.get("/strategy-domain/admin/risk-orchestrator/alerts?limit=30"),
      apiClient.get(`/strategy-domain/admin/risk-orchestrator/policy/queue?${queueQuery}`),
      apiClient.get("/strategy-domain/admin/risk-orchestrator/policy/decision-traces?limit=25"),
      apiClient.get("/strategy-domain/admin/risk-orchestrator/operations/dashboard"),
      apiClient.get("/strategy-domain/admin/risk-orchestrator/rejects/insights"),
    ]);

    setPolicy(policyRes.data || policySeed);
    setStatus(statusRes.data || null);
    setHistory(historyRes.data || { versions: [], change_requests: [] });
    setOverrides(overrideRes.data || []);
    setPositions(positionRes.data || []);
    setAutoTriggers(triggerRes.data || []);
    setTimeline(timelineRes.data || []);
    setAlerts(alertsRes.data || []);
    setApprovals(approvalsRes.data || []);
    setDecisionTraces(tracesRes.data || []);
    setDashboardData(dashboardRes.data || null);
    setRejectInsights(insightsRes.data?.insights || []);
  }, [criticalFirst, queueScope, queueState]);

  const refreshRejects = useCallback(async () => {
    const query = buildRejectQuery(rejectFilters);
    const { data } = await apiClient.get(`/strategy-domain/admin/risk-orchestrator/rejects?${query}`);
    setRejects(data || []);
  }, [rejectFilters]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      await Promise.all([refreshCore(), refreshRejects()]);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Risk Enforcement paneli yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, [refreshCore, refreshRejects]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const roleBadge = useMemo(() => {
    if (isSuperAdmin) return "super_admin";
    return user?.role || "admin";
  }, [isSuperAdmin, user?.role]);

  const handleSimulate = async () => {
    try {
      const payload = {
        candidate_policy: {
          reference_equity_usd: Number(policy.reference_equity_usd),
          account_max_notional_pct: Number(policy.account_max_notional_pct),
          symbol_max_notional_pct: Number(policy.symbol_max_notional_pct),
          strategy_max_concurrent_positions: Number(policy.strategy_max_concurrent_positions),
          strategy_cooldown_seconds: Number(policy.strategy_cooldown_seconds),
          max_order_frequency_per_min: Number(policy.max_order_frequency_per_min),
          max_order_burst_per_10s: Number(policy.max_order_burst_per_10s),
          daily_loss_limit_pct: Number(policy.daily_loss_limit_pct),
          duplicate_suppression_window_seconds: Number(policy.duplicate_suppression_window_seconds),
        },
      };
      const { data } = await apiClient.post("/strategy-domain/admin/risk-orchestrator/policy/simulate", payload);
      setSimulation(data);
      setDoubleConfirm(false);
      toast.success("What-if simülasyonu tamamlandı.");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Simülasyon çalıştırılamadı");
    }
  };

  const handleApply = async () => {
    if (!simulation?.simulation_id) {
      toast.error("Önce simülasyon çalıştırmalısınız.");
      return;
    }
    try {
      const requestKey = `ui-${simulation.simulation_id}-${user?.id || "unknown"}`;
      const { data } = await apiClient.post("/strategy-domain/admin/risk-orchestrator/policy/apply", {
        simulation_id: simulation.simulation_id,
        reason_note: applyReason,
        approval_note: applyNote,
        double_confirmed: doubleConfirm,
        apply_with_override: applyWithOverride,
        request_key: requestKey,
        expected_policy_version: status?.policy?.policy_version,
      });
      setLastApplyResult(data);
      if (data.status === "applied") {
        toast.success("Policy başarıyla uygulandı.");
      } else if (data.status === "pending" || data.status === "assigned") {
        toast.info("Policy second approval kuyruğuna alındı.");
      } else if (data.status === "blocked") {
        toast.error("CRITICAL gate nedeniyle apply bloklandı.");
      } else {
        toast.info(`Apply sonucu: ${data.status}`);
      }
      setApplyDialogOpen(false);
      setApplyReason("");
      setApplyNote("");
      setDoubleConfirm(false);
      await refreshCore();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Policy apply başarısız");
    }
  };

  const handleRevertSimulate = async (versionId) => {
    try {
      const { data } = await apiClient.post(
        `/strategy-domain/admin/risk-orchestrator/policy/revert/${versionId}/simulate`,
      );
      setRevertSimulations((prev) => ({ ...prev, [versionId]: data.simulation }));
      toast.success("Revert impact simulation hazırlandı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Revert simulation başarısız");
    }
  };

  const handleRevertApply = async (versionId) => {
    if (!isSuperAdmin) return;
    const simulation = revertSimulations[versionId];
    if (!simulation?.simulation_id) {
      toast.error("Önce revert simulation çalıştırın");
      return;
    }
    try {
      const requestKey = `revert-${simulation.simulation_id}-${user?.id || "unknown"}`;
      const { data } = await apiClient.post(`/strategy-domain/admin/risk-orchestrator/policy/revert/${versionId}/apply`, {
        simulation_id: simulation.simulation_id,
        reason_note: "Revert apply",
        double_confirmed: true,
        apply_with_override: true,
        request_key: requestKey,
        expected_policy_version: status?.policy?.policy_version,
      });
      setLastApplyResult(data);
      if (data.status === "applied") {
        toast.success("Revert apply tamamlandı");
      } else {
        toast.info(`Revert sonucu: ${data.status}`);
      }
      await refreshCore();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Revert apply başarısız");
    }
  };

  const executeControlAction = async (actionType) => {
    try {
      const reason = controlReasons[actionType];
      if (!reason) {
        toast.error("Aksiyon sebebi zorunludur.");
        return;
      }
      await apiClient.post("/strategy-domain/admin/risk-orchestrator/actions/execute", {
        action_type: actionType,
        reason_note: reason,
        context: {},
      });
      toast.success("Kritik risk aksiyonu işlendi.");
      setControlReasons((prev) => ({ ...prev, [actionType]: "" }));
      await refreshCore();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Aksiyon çalıştırılamadı");
    }
  };

  const handleOverrideCreate = async () => {
    try {
      await apiClient.post("/strategy-domain/admin/risk-orchestrator/exposure/overrides", {
        override_type: overrideForm.override_type,
        target_key: overrideForm.target_key,
        reason_note: overrideForm.reason_note,
        max_notional_pct: toNumberOrNull(overrideForm.max_notional_pct),
        max_open_count: toNumberOrNull(overrideForm.max_open_count),
        block_new_adds: overrideForm.block_new_adds,
        expires_in_minutes: toNumberOrNull(overrideForm.expires_in_minutes),
      });
      toast.success("Exposure override kaydedildi.");
      setOverrideForm(overrideSeed);
      await refreshCore();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Override oluşturulamadı");
    }
  };

  const handleOverrideDeactivate = async (overrideId) => {
    try {
      await apiClient.post(`/strategy-domain/admin/risk-orchestrator/exposure/overrides/${overrideId}/deactivate`, {
        reason_note: "Manual deactivate",
      });
      toast.success("Override pasif hale getirildi");
      await refreshCore();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Override kapatılamadı");
    }
  };

  const handleSupervisorRun = async () => {
    try {
      const { data } = await apiClient.post("/strategy-domain/admin/risk-orchestrator/supervisor/run");
      setSupervisor(data);
      toast.success("In-trade supervisor çalıştırıldı");
      await refreshCore();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Supervisor çalıştırılamadı");
    }
  };

  const handleIntervene = async () => {
    try {
      await apiClient.post("/strategy-domain/admin/risk-orchestrator/supervisor/intervene", {
        position_id: interventionState.position_id,
        action_type: interventionState.action_type,
        reason_note: interventionState.reason_note,
        payload: {
          reduce_ratio: toNumberOrNull(interventionState.reduce_ratio),
          expires_in_minutes: toNumberOrNull(interventionState.expires_in_minutes),
        },
      });
      toast.success("Pozisyon müdahalesi işlendi");
      setInterventionState((prev) => ({ ...prev, reason_note: "" }));
      await refreshCore();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Müdahale başarısız");
    }
  };

  const openRejectDetail = async (rejectId) => {
    try {
      const { data } = await apiClient.get(`/strategy-domain/admin/risk-orchestrator/rejects/${rejectId}`);
      setRejectDetail(data);
      setRejectDialogOpen(true);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Reject detayı açılamadı");
    }
  };

  const handleApprovalDecision = async (approvalId, decision) => {
    const decisionNote = approvalNotes[approvalId] || "operasyon onayı";
    try {
      if (decision === "approve") {
        const { data } = await apiClient.post(
          `/strategy-domain/admin/risk-orchestrator/policy/approvals/${approvalId}/approve`,
          { decision_note: decisionNote },
        );
        setLastApplyResult(data);
        toast.success("4-eyes approval onayı işlendi");
      } else {
        await apiClient.post(`/strategy-domain/admin/risk-orchestrator/policy/approvals/${approvalId}/reject`, {
          decision_note: decisionNote,
        });
        toast.info("Approval request reddedildi");
      }
      setApprovalNotes((prev) => ({ ...prev, [approvalId]: "" }));
      await refreshCore();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Approval aksiyonu başarısız");
    }
  };

  const handleAssign = async (approvalId, autoAssign) => {
    try {
      const assigneeId = assignmentInputs[approvalId] || "";
      await apiClient.post(`/strategy-domain/admin/risk-orchestrator/policy/queue/${approvalId}/assign`, {
        assignee_id: autoAssign ? null : assigneeId,
        auto_assign: autoAssign,
      });
      toast.success(autoAssign ? "Auto-assign tamamlandı" : "Manual assignment tamamlandı");
      await refreshCore();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Assignment başarısız");
    }
  };

  const handleQueueSweep = async () => {
    try {
      const { data } = await apiClient.post("/strategy-domain/admin/risk-orchestrator/policy/queue/sweep");
      setSweepResult(data);
      toast.success("Escalation sweep çalıştırıldı");
      await refreshCore();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Queue sweep başarısız");
    }
  };

  const handleForceApply = async (approvalId) => {
    if (!isSuperAdmin) return;
    try {
      const { data } = await apiClient.post(
        `/strategy-domain/admin/risk-orchestrator/policy/queue/${approvalId}/force-apply`,
        { reason_note: "SLA breach force apply" },
      );
      setLastApplyResult(data);
      toast.success("Force apply tamamlandı");
      await refreshCore();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Force apply başarısız");
    }
  };

  const loadDecisionIntelligence = async (traceId) => {
    try {
      const { data } = await apiClient.get(
        `/strategy-domain/admin/risk-orchestrator/policy/decision-intelligence/${traceId}`,
      );
      setDecisionIntelligence(data);
      toast.success("Decision intelligence yüklendi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Decision intelligence yüklenemedi");
    }
  };

  const superAdminOnlyTitle = isSuperAdmin ? "" : "Sadece super_admin kullanıcıları çalıştırabilir";

  return (
    <section className="space-y-6 pb-8" data-testid="risk-enforcement-page">
      <header
        className="sticky top-0 z-10 rounded-xl border bg-gradient-to-r from-slate-900 via-slate-800 to-emerald-950 p-4 shadow-lg"
        data-testid="risk-enforcement-sticky-status"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div data-testid="risk-enforcement-header-left">
            <h1 className="text-4xl font-black tracking-tight text-emerald-200" data-testid="risk-enforcement-title">
              Risk Enforcement + Intervention System
            </h1>
            <p className="mt-2 text-sm text-slate-300" data-testid="risk-enforcement-subtitle">
              Simülasyon zorunlu, audit zorunlu, kritik aksiyonlar role-gated.
            </p>
          </div>
          <div className="flex items-center gap-2" data-testid="risk-enforcement-header-badges">
            <Badge data-testid="risk-role-badge">Rol: {roleBadge}</Badge>
            <Badge variant={status?.kill_switch_active ? "destructive" : "secondary"} data-testid="risk-kill-switch-badge">
              Kill Switch: {status?.kill_switch_active ? "AKTİF" : "pasif"}
            </Badge>
            <Badge variant={status?.trading_enabled ? "secondary" : "destructive"} data-testid="risk-trading-enabled-badge">
              Trading: {status?.trading_enabled ? "açık" : "pause"}
            </Badge>
            <Button variant="outline" onClick={loadAll} data-testid="risk-refresh-all-button">
              Yenile
            </Button>
          </div>
        </div>
      </header>

      <div className="flex flex-wrap gap-2" data-testid="risk-tabs-row">
        {[
          ["risk-gate", "Risk Gate"],
          ["operations", "Operations"],
          ["monitoring", "Monitoring"],
          ["approvals", "Approvals & Trace"],
          ["control-tower", "Control Tower"],
        ].map(([tabKey, tabLabel]) => (
          <Button
            key={tabKey}
            variant={activeTab === tabKey ? "default" : "outline"}
            onClick={() => setActiveTab(tabKey)}
            data-testid={`risk-tab-button-${tabKey}`}
          >
            {tabLabel}
          </Button>
        ))}
      </div>

      {loading && (
        <Card data-testid="risk-page-loading-card">
          <CardContent className="pt-6 text-sm text-slate-400" data-testid="risk-page-loading-text">
            Risk paneli yükleniyor...
          </CardContent>
        </Card>
      )}

      <div className="grid gap-5 xl:grid-cols-2" data-testid="risk-main-grid">
        {activeTab === "risk-gate" && (
        <Card data-testid="risk-policy-management-card">
          <CardHeader>
            <CardTitle data-testid="risk-policy-management-title">1) Policy Management</CardTitle>
            <CardDescription data-testid="risk-policy-management-description">
              Apply öncesi simülasyon + double-confirm zorunlu.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-2 sm:grid-cols-2" data-testid="risk-policy-input-grid">
              {Object.keys(policySeed).map((key) => (
                <div key={key} className="space-y-1" data-testid={`risk-policy-input-wrapper-${key}`}>
                  <label className="text-xs text-slate-500" data-testid={`risk-policy-input-label-${key}`}>
                    {key}
                  </label>
                  <Input
                    type="number"
                    value={policy[key] ?? ""}
                    onChange={(event) => setPolicy((prev) => ({ ...prev, [key]: event.target.value }))}
                    data-testid={`risk-policy-input-${key}`}
                  />
                </div>
              ))}
            </div>

            <div className="flex flex-wrap gap-2" data-testid="risk-policy-action-buttons">
              <Button onClick={handleSimulate} data-testid="risk-policy-simulate-button">
                Simülasyon Çalıştır
              </Button>
              <Button
                variant="secondary"
                onClick={() => setApplyDialogOpen(true)}
                disabled={!isSuperAdmin}
                title={superAdminOnlyTitle}
                data-testid="risk-policy-open-apply-dialog-button"
              >
                Apply (Double Confirm)
              </Button>
              <div className="flex items-center gap-2 rounded border px-2" data-testid="risk-apply-with-override-wrapper">
                <Checkbox
                  checked={applyWithOverride}
                  onCheckedChange={(checked) => setApplyWithOverride(checked === true)}
                  data-testid="risk-apply-with-override-checkbox"
                />
                <span className="text-xs">CRITICAL için apply_with_override</span>
              </div>
            </div>

            <div className="rounded-lg border p-3" data-testid="risk-policy-simulation-result-box">
              <p className="text-xs text-slate-500" data-testid="risk-policy-simulation-label">Son simülasyon</p>
              {!simulation && (
                <p className="text-sm text-slate-400" data-testid="risk-policy-simulation-empty">Henüz simülasyon yok.</p>
              )}
              {simulation && (
                <div className="space-y-2" data-testid="risk-policy-simulation-content">
                  <Badge
                    variant={simulation.result_status === "critical" ? "destructive" : "secondary"}
                    data-testid="risk-policy-simulation-status-badge"
                  >
                    Durum: {simulation.result_status}
                  </Badge>
                  <p className="text-xs text-slate-500" data-testid="risk-policy-simulation-id">
                    simulation_id: {simulation.simulation_id}
                  </p>
                  <p className="text-xs" data-testid="risk-policy-simulation-score">
                    risk_score: {simulation.risk_score} · classification: {simulation.classification}
                  </p>
                  <p className="text-xs text-slate-500" data-testid="risk-policy-simulation-flow">
                    flow: {simulation.approval_flow?.rule_path || "-"}
                  </p>
                  <div className="space-y-1" data-testid="risk-policy-diff-list">
                    {Object.entries(simulation.diff_summary?.changed_fields || {}).map(([field, diff]) => (
                      <div
                        key={field}
                        className="flex items-center justify-between text-xs"
                        data-testid={`risk-policy-diff-row-${field}`}
                      >
                        <span>{field}</span>
                        <span>
                          {String(diff.before)} → {String(diff.after)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="rounded-lg border p-3" data-testid="risk-policy-history-box">
              <p className="text-xs text-slate-500" data-testid="risk-policy-history-title">Versiyon geçmişi</p>
              <div className="mt-2 space-y-2" data-testid="risk-policy-history-list">
                {(history.versions || []).slice(0, 6).map((version) => (
                  <div
                    key={version.version_id}
                    className="flex flex-wrap items-center justify-between gap-2 rounded border p-2 text-xs"
                    data-testid={`risk-policy-history-row-${version.version_id}`}
                  >
                    <span data-testid={`risk-policy-history-version-no-${version.version_id}`}>v{version.version_no}</span>
                    <span data-testid={`risk-policy-history-reason-${version.version_id}`}>{version.reason_note}</span>
                    <span data-testid={`risk-policy-history-created-${version.version_id}`}>
                      {new Date(version.created_at).toLocaleString()}
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={false}
                      onClick={() => handleRevertSimulate(version.version_id)}
                      data-testid={`risk-policy-revert-simulate-button-${version.version_id}`}
                    >
                      Revert Simulate
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={!isSuperAdmin || !revertSimulations[version.version_id]}
                      title={superAdminOnlyTitle}
                      onClick={() => handleRevertApply(version.version_id)}
                      data-testid={`risk-policy-revert-apply-button-${version.version_id}`}
                    >
                      Revert Apply
                    </Button>
                    {revertSimulations[version.version_id] && (
                      <p
                        className="w-full text-[11px] text-slate-500"
                        data-testid={`risk-policy-revert-impact-${version.version_id}`}
                      >
                        impact score: {revertSimulations[version.version_id].risk_score} ·
                        class: {revertSimulations[version.version_id].classification}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
        )}

        {activeTab === "risk-gate" && (
        <Card data-testid="risk-control-actions-card">
          <CardHeader>
            <CardTitle data-testid="risk-control-actions-title">2) Critical Risk Control Actions</CardTitle>
            <CardDescription data-testid="risk-control-actions-description">
              Kill switch, global pause, force risk check (reason zorunlu).
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {[
              ["kill_switch", "Kill Switch"],
              ["global_trading_pause", "Global Trading Pause"],
              ["force_risk_check", "Force Risk Check"],
            ].map(([actionType, title]) => (
              <div key={actionType} className="rounded-lg border p-3" data-testid={`risk-control-action-box-${actionType}`}>
                <p className="text-sm font-semibold" data-testid={`risk-control-action-title-${actionType}`}>{title}</p>
                <Textarea
                  value={controlReasons[actionType] || ""}
                  onChange={(event) =>
                    setControlReasons((prev) => ({
                      ...prev,
                      [actionType]: event.target.value,
                    }))
                  }
                  placeholder="Aksiyon sebebi"
                  className="mt-2"
                  data-testid={`risk-control-action-reason-input-${actionType}`}
                />
                <Button
                  className="mt-2"
                  variant="destructive"
                  onClick={() => executeControlAction(actionType)}
                  disabled={!isSuperAdmin}
                  title={superAdminOnlyTitle}
                  data-testid={`risk-control-action-submit-button-${actionType}`}
                >
                  Uygula
                </Button>
              </div>
            ))}

            <div className="rounded-lg border p-3" data-testid="risk-supervisor-box">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold" data-testid="risk-supervisor-title">In-Trade Supervisor</p>
                <Button onClick={handleSupervisorRun} data-testid="risk-supervisor-run-button">
                  Supervisor Run
                </Button>
              </div>
              {supervisor && (
                <div className="mt-2 space-y-1 text-xs" data-testid="risk-supervisor-result-list">
                  <p data-testid="risk-supervisor-evaluated-at">{new Date(supervisor.evaluated_at).toLocaleString()}</p>
                  {(supervisor.breaches || []).length === 0 && (
                    <p data-testid="risk-supervisor-empty-breach">Breach yok.</p>
                  )}
                  {(supervisor.breaches || []).map((breach, index) => (
                    <div key={`${breach.key}-${index}`} data-testid={`risk-supervisor-breach-row-${index}`}>
                      {breach.breach_type} · {breach.key} · {breach.open_count}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
        )}

        {activeTab === "operations" && (
        <Card data-testid="risk-exposure-card">
          <CardHeader>
            <CardTitle data-testid="risk-exposure-title">3) Exposure Control & Manual Override</CardTitle>
            <CardDescription data-testid="risk-exposure-description">
              Symbol/strategy bazlı limit override ve block-adds.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-2 sm:grid-cols-2" data-testid="risk-exposure-form-grid">
              <select
                value={overrideForm.override_type}
                onChange={(event) => setOverrideForm((prev) => ({ ...prev, override_type: event.target.value }))}
                className="h-9 rounded-md border bg-background px-2"
                data-testid="risk-override-type-select"
              >
                <option value="symbol">symbol</option>
                <option value="strategy">strategy</option>
                <option value="block_adds">block_adds</option>
              </select>
              <Input
                value={overrideForm.target_key}
                onChange={(event) => setOverrideForm((prev) => ({ ...prev, target_key: event.target.value }))}
                placeholder="Target key"
                data-testid="risk-override-target-input"
              />
              <Input
                value={overrideForm.max_notional_pct}
                onChange={(event) => setOverrideForm((prev) => ({ ...prev, max_notional_pct: event.target.value }))}
                placeholder="max notional %"
                data-testid="risk-override-max-notional-input"
              />
              <Input
                value={overrideForm.max_open_count}
                onChange={(event) => setOverrideForm((prev) => ({ ...prev, max_open_count: event.target.value }))}
                placeholder="max open count"
                data-testid="risk-override-max-open-count-input"
              />
              <Input
                value={overrideForm.expires_in_minutes}
                onChange={(event) => setOverrideForm((prev) => ({ ...prev, expires_in_minutes: event.target.value }))}
                placeholder="expiry (min)"
                data-testid="risk-override-expiry-input"
              />
              <div className="flex items-center gap-2" data-testid="risk-override-block-adds-wrapper">
                <Checkbox
                  checked={overrideForm.block_new_adds}
                  onCheckedChange={(checked) =>
                    setOverrideForm((prev) => ({ ...prev, block_new_adds: checked === true }))
                  }
                  data-testid="risk-override-block-adds-checkbox"
                />
                <span className="text-xs">block_new_adds</span>
              </div>
            </div>
            <Textarea
              value={overrideForm.reason_note}
              onChange={(event) => setOverrideForm((prev) => ({ ...prev, reason_note: event.target.value }))}
              placeholder="Override reason"
              data-testid="risk-override-reason-textarea"
            />
            <Button
              onClick={handleOverrideCreate}
              disabled={!isSuperAdmin}
              title={superAdminOnlyTitle}
              data-testid="risk-override-create-button"
            >
              Override Ekle
            </Button>

            <div className="space-y-2" data-testid="risk-override-active-list">
              {overrides.map((item) => (
                <div
                  key={item.override_id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded border p-2 text-xs"
                  data-testid={`risk-override-row-${item.override_id}`}
                >
                  <span data-testid={`risk-override-target-${item.override_id}`}>{item.override_type} · {item.target_key}</span>
                  <span data-testid={`risk-override-status-${item.override_id}`}>{item.status}</span>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!isSuperAdmin}
                    title={superAdminOnlyTitle}
                    onClick={() => handleOverrideDeactivate(item.override_id)}
                    data-testid={`risk-override-deactivate-button-${item.override_id}`}
                  >
                    Deactivate
                  </Button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
        )}

        {activeTab === "operations" && (
        <Card data-testid="risk-intervention-card">
          <CardHeader>
            <CardTitle data-testid="risk-intervention-title">4) Open Position Intervention</CardTitle>
            <CardDescription data-testid="risk-intervention-description">
              Reduce, close, block further adds.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-2 sm:grid-cols-2" data-testid="risk-intervention-form-grid">
              <select
                value={interventionState.position_id}
                onChange={(event) => setInterventionState((prev) => ({ ...prev, position_id: event.target.value }))}
                className="h-9 rounded-md border bg-background px-2"
                data-testid="risk-intervention-position-select"
              >
                <option value="">Pozisyon seçin</option>
                {positions.map((position) => (
                  <option key={position.position_id} value={position.position_id}>
                    {position.symbol} · {position.position_id}
                  </option>
                ))}
              </select>
              <select
                value={interventionState.action_type}
                onChange={(event) => setInterventionState((prev) => ({ ...prev, action_type: event.target.value }))}
                className="h-9 rounded-md border bg-background px-2"
                data-testid="risk-intervention-action-select"
              >
                <option value="reduce_position">reduce_position</option>
                <option value="close_position">close_position</option>
                <option value="block_further_adds">block_further_adds</option>
              </select>
              <Input
                value={interventionState.reduce_ratio}
                onChange={(event) => setInterventionState((prev) => ({ ...prev, reduce_ratio: event.target.value }))}
                placeholder="reduce ratio"
                data-testid="risk-intervention-reduce-ratio-input"
              />
              <Input
                value={interventionState.expires_in_minutes}
                onChange={(event) =>
                  setInterventionState((prev) => ({
                    ...prev,
                    expires_in_minutes: event.target.value,
                  }))
                }
                placeholder="block expiry"
                data-testid="risk-intervention-expiry-input"
              />
            </div>
            <Textarea
              value={interventionState.reason_note}
              onChange={(event) => setInterventionState((prev) => ({ ...prev, reason_note: event.target.value }))}
              placeholder="Intervention reason"
              data-testid="risk-intervention-reason-textarea"
            />
            <Button
              onClick={handleIntervene}
              disabled={!isSuperAdmin}
              title={superAdminOnlyTitle}
              data-testid="risk-intervention-submit-button"
            >
              Müdahale Uygula
            </Button>

            <div className="space-y-1" data-testid="risk-open-position-list">
              {positions.map((position) => (
                <div
                  key={position.position_id}
                  className="grid grid-cols-[1fr_auto_auto] items-center gap-2 rounded border p-2 text-xs"
                  data-testid={`risk-open-position-row-${position.position_id}`}
                >
                  <span data-testid={`risk-open-position-meta-${position.position_id}`}>
                    {position.symbol} · size: {Number(position.size).toFixed(4)}
                  </span>
                  <Badge data-testid={`risk-open-position-status-${position.position_id}`}>{position.status}</Badge>
                  <span data-testid={`risk-open-position-pnl-${position.position_id}`}>
                    pnl: {Number(position.unrealized_pnl).toFixed(2)}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
        )}
      </div>

      {activeTab === "monitoring" && (
      <div className="grid gap-5 xl:grid-cols-2" data-testid="risk-bottom-grid">
        <Card data-testid="risk-rejects-card">
          <CardHeader>
            <CardTitle data-testid="risk-rejects-title">5) Risk Rejects (Drill-down)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-2 sm:grid-cols-3" data-testid="risk-rejects-filter-grid">
              <Input
                value={rejectFilters.reason_code}
                onChange={(event) => setRejectFilters((prev) => ({ ...prev, reason_code: event.target.value }))}
                placeholder="reason_code"
                data-testid="risk-rejects-filter-reason-input"
              />
              <Input
                value={rejectFilters.symbol}
                onChange={(event) => setRejectFilters((prev) => ({ ...prev, symbol: event.target.value }))}
                placeholder="symbol"
                data-testid="risk-rejects-filter-symbol-input"
              />
              <Input
                value={rejectFilters.strategy_id}
                onChange={(event) => setRejectFilters((prev) => ({ ...prev, strategy_id: event.target.value }))}
                placeholder="strategy_id"
                data-testid="risk-rejects-filter-strategy-input"
              />
            </div>
            <Button onClick={refreshRejects} data-testid="risk-rejects-filter-apply-button">
              Filter Uygula
            </Button>

            <div className="space-y-2" data-testid="risk-rejects-list">
              {rejects.map((row) => (
                <button
                  type="button"
                  key={row.id}
                  onClick={() => openRejectDetail(row.id)}
                  className="w-full rounded border p-2 text-left text-xs transition-colors hover:bg-slate-50"
                  data-testid={`risk-reject-row-button-${row.id}`}
                >
                  <p data-testid={`risk-reject-row-meta-${row.id}`}>
                    {row.strategy_id || "-"} · {row.symbol || "-"}
                  </p>
                  <p className="text-slate-500" data-testid={`risk-reject-row-reasons-${row.id}`}>
                    {(row.reason_codes || []).join(", ") || "-"}
                  </p>
                </button>
              ))}
            </div>

            <div className="rounded border p-2" data-testid="risk-reject-insight-panel">
              <p className="text-xs font-semibold" data-testid="risk-reject-insight-title">Suggest Adjustment</p>
              <div className="mt-2 space-y-1" data-testid="risk-reject-insight-list">
                {rejectInsights.length === 0 && (
                  <p className="text-xs text-slate-500" data-testid="risk-reject-insight-empty">
                    Eşik altında, öneri yok.
                  </p>
                )}
                {rejectInsights.map((item) => (
                  <div key={`${item.rule}-${item.count}`} className="text-xs" data-testid={`risk-reject-insight-row-${item.rule}`}>
                    <span className="font-medium">{item.rule}</span> · {item.count}x · öneri: {item.suggestion}
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card data-testid="risk-alerts-card">
          <CardHeader>
            <CardTitle data-testid="risk-alerts-title">6) Alerts + Auto Trigger Logs</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-2" data-testid="risk-alert-list">
              {alerts.map((alert) => (
                <div
                  key={alert.id}
                  className="rounded border p-2 text-xs"
                  data-testid={`risk-alert-row-${alert.id}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span data-testid={`risk-alert-type-${alert.id}`}>{alert.alert_type}</span>
                    <Badge
                      variant={alert.severity === "CRITICAL" ? "destructive" : "secondary"}
                      data-testid={`risk-alert-severity-${alert.id}`}
                    >
                      {alert.severity}
                    </Badge>
                  </div>
                  <p className="mt-1 text-slate-600" data-testid={`risk-alert-message-${alert.id}`}>{alert.message}</p>
                </div>
              ))}
            </div>

            <div className="space-y-2" data-testid="risk-auto-trigger-list">
              {autoTriggers.map((trigger) => (
                <div
                  key={trigger.trigger_id}
                  className="rounded border p-2 text-xs"
                  data-testid={`risk-auto-trigger-row-${trigger.trigger_id}`}
                >
                  <p data-testid={`risk-auto-trigger-main-${trigger.trigger_id}`}>
                    {trigger.breach_type} · {trigger.target_key}
                  </p>
                  <p className="text-slate-500" data-testid={`risk-auto-trigger-action-${trigger.trigger_id}`}>
                    öneri: {trigger.suggested_action}
                  </p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
      )}

      {activeTab === "monitoring" && (
      <Card data-testid="risk-audit-timeline-card">
        <CardHeader>
          <CardTitle data-testid="risk-audit-timeline-title">7) Audit & Governance Timeline</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2" data-testid="risk-audit-timeline-list">
            {timeline.map((item) => (
              <div
                key={`${item.event_type}-${item.event_id}`}
                className="rounded border p-2 text-xs"
                data-testid={`risk-audit-item-${item.event_type}-${item.event_id}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span data-testid={`risk-audit-item-type-${item.event_id}`}>{item.event_type}</span>
                  <span data-testid={`risk-audit-item-status-${item.event_id}`}>{item.status}</span>
                  <span data-testid={`risk-audit-item-created-${item.event_id}`}>
                    {new Date(item.created_at).toLocaleString()}
                  </span>
                </div>
                <p className="mt-1 text-slate-600" data-testid={`risk-audit-item-reason-${item.event_id}`}>
                  {item.reason_note}
                </p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
      )}

      {activeTab === "approvals" && (
      <div className="grid gap-5 xl:grid-cols-2" data-testid="risk-approvals-main-grid">
        <Card data-testid="risk-approval-queue-card">
          <CardHeader>
            <CardTitle data-testid="risk-approval-queue-title">4-Eyes Approval Queue</CardTitle>
            <CardDescription data-testid="risk-approval-queue-description">
              pending/assigned/approved/rejected/expired + SLA countdown + ownership
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-2 sm:grid-cols-2" data-testid="risk-queue-filter-grid">
              <select
                value={queueScope}
                onChange={(event) => setQueueScope(event.target.value)}
                className="h-9 rounded-md border bg-background px-2"
                data-testid="risk-queue-scope-select"
              >
                <option value="all">All</option>
                <option value="my">My approvals</option>
                <option value="unassigned">Unassigned</option>
              </select>
              <select
                value={queueState}
                onChange={(event) => setQueueState(event.target.value)}
                className="h-9 rounded-md border bg-background px-2"
                data-testid="risk-queue-state-select"
              >
                <option value="">all states</option>
                <option value="pending">pending</option>
                <option value="assigned">assigned</option>
                <option value="approved">approved</option>
                <option value="rejected">rejected</option>
                <option value="expired">expired</option>
              </select>
              <div className="flex items-center gap-2" data-testid="risk-queue-critical-first-wrapper">
                <Checkbox
                  checked={criticalFirst}
                  onCheckedChange={(checked) => setCriticalFirst(checked === true)}
                  data-testid="risk-queue-critical-first-checkbox"
                />
                <span className="text-xs">Critical first sorting</span>
              </div>
              <Button variant="outline" onClick={handleQueueSweep} data-testid="risk-queue-sweep-button">
                Escalation Sweep
              </Button>
            </div>

            {sweepResult && (
              <div className="rounded border p-2 text-xs" data-testid="risk-queue-sweep-result">
                warning: {sweepResult.warning_escalations} · critical: {sweepResult.critical_escalations} · stuck: {sweepResult.stuck_detected}
              </div>
            )}

            <div className="rounded border p-2 text-xs" data-testid="risk-last-apply-result-box">
              <p data-testid="risk-last-apply-status">last_status: {lastApplyResult?.status || "-"}</p>
              <p data-testid="risk-last-apply-classification">classification: {lastApplyResult?.classification || "-"}</p>
              <p data-testid="risk-last-apply-score">risk_score: {lastApplyResult?.risk_score ?? "-"}</p>
              <p data-testid="risk-last-apply-rule">rule_path: {lastApplyResult?.rule_path || "-"}</p>
            </div>

            <div className="space-y-2" data-testid="risk-approval-queue-list">
              {approvals.map((item) => (
                <div key={item.approval_id} className="rounded border p-2 text-xs" data-testid={`risk-approval-row-${item.approval_id}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span data-testid={`risk-approval-state-${item.approval_id}`}>{item.state}</span>
                    <Badge
                      variant={item.classification === "CRITICAL" ? "destructive" : "secondary"}
                      data-testid={`risk-approval-classification-${item.approval_id}`}
                    >
                      {item.classification}
                    </Badge>
                  </div>
                  <p className="mt-1" data-testid={`risk-approval-meta-${item.approval_id}`}>
                    score: {item.risk_score} · expires: {new Date(item.expires_at).toLocaleString()}
                  </p>
                  <p
                    className={`font-medium ${
                      item.sla_stage === "critical" || item.sla_stage === "expired"
                        ? "text-red-600"
                        : item.sla_stage === "approaching"
                          ? "text-yellow-600"
                          : "text-emerald-600"
                    }`}
                    data-testid={`risk-approval-countdown-${item.approval_id}`}
                  >
                    SLA: {item.sla_remaining_seconds}s · stage: {item.sla_stage}
                  </p>
                  <p className="text-slate-600" data-testid={`risk-approval-requested-by-${item.approval_id}`}>
                    requested_by: {item.requested_by} · assigned_to: {item.assigned_to || "-"} · second_approver: {item.second_approver_id || "-"}
                  </p>

                  <div className="mt-2 grid gap-2 sm:grid-cols-2" data-testid={`risk-approval-assignment-${item.approval_id}`}>
                    <Input
                      value={assignmentInputs[item.approval_id] || ""}
                      onChange={(event) =>
                        setAssignmentInputs((prev) => ({
                          ...prev,
                          [item.approval_id]: event.target.value,
                        }))
                      }
                      placeholder="Manual assignee user_id"
                      data-testid={`risk-approval-assignee-input-${item.approval_id}`}
                    />
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleAssign(item.approval_id, false)}
                        data-testid={`risk-approval-assign-manual-button-${item.approval_id}`}
                      >
                        Manual Assign
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleAssign(item.approval_id, true)}
                        data-testid={`risk-approval-assign-auto-button-${item.approval_id}`}
                      >
                        Auto Assign
                      </Button>
                    </div>
                  </div>

                  <Textarea
                    className="mt-2"
                    value={approvalNotes[item.approval_id] || ""}
                    onChange={(event) =>
                      setApprovalNotes((prev) => ({
                        ...prev,
                        [item.approval_id]: event.target.value,
                      }))
                    }
                    placeholder="Approval/reject note"
                    data-testid={`risk-approval-note-input-${item.approval_id}`}
                  />

                  <div className="mt-2 flex gap-2" data-testid={`risk-approval-actions-${item.approval_id}`}>
                    <Button
                      size="sm"
                      onClick={() => handleApprovalDecision(item.approval_id, "approve")}
                      disabled={!(["pending", "assigned"].includes(item.state))}
                      data-testid={`risk-approval-approve-button-${item.approval_id}`}
                    >
                      Approve
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() => handleApprovalDecision(item.approval_id, "reject")}
                      disabled={!(["pending", "assigned"].includes(item.state))}
                      data-testid={`risk-approval-reject-button-${item.approval_id}`}
                    >
                      Reject
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleForceApply(item.approval_id)}
                      disabled={!isSuperAdmin || !(["pending", "assigned", "expired"].includes(item.state))}
                      data-testid={`risk-approval-force-apply-button-${item.approval_id}`}
                    >
                      Force Apply
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card data-testid="risk-decision-trace-card">
          <CardHeader>
            <CardTitle data-testid="risk-decision-trace-title">Decision Trace</CardTitle>
            <CardDescription data-testid="risk-decision-trace-description">
              simulation → score → classification → approval → rule path zinciri
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2" data-testid="risk-decision-trace-list">
            {decisionTraces.map((trace) => (
              <div
                key={trace.trace_id}
                className="rounded border p-2 text-xs"
                data-testid={`risk-decision-trace-row-${trace.trace_id}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span data-testid={`risk-decision-trace-state-${trace.trace_id}`}>{trace.decision_state}</span>
                  <span data-testid={`risk-decision-trace-rule-${trace.trace_id}`}>{trace.rule_path}</span>
                </div>
                <p data-testid={`risk-decision-trace-score-${trace.trace_id}`}>
                  {trace.classification} · score: {trace.risk_score}
                </p>
                <p className="text-slate-600" data-testid={`risk-decision-trace-meta-${trace.trace_id}`}>
                  req: {trace.requested_by} · appr: {trace.approver_id || "-"}
                </p>
                <Button
                  size="sm"
                  variant="outline"
                  className="mt-2"
                  onClick={() => loadDecisionIntelligence(trace.trace_id)}
                  data-testid={`risk-decision-trace-intelligence-button-${trace.trace_id}`}
                >
                  Decision Intelligence
                </Button>
              </div>
            ))}

            {decisionIntelligence && (
              <div className="rounded border p-2 text-xs" data-testid="risk-decision-intelligence-panel">
                <p data-testid="risk-decision-intelligence-why">
                  why: {decisionIntelligence.why_decision?.explanation || "-"}
                </p>
                <pre className="mt-1 max-h-44 overflow-auto rounded bg-slate-950 p-2 text-slate-100" data-testid="risk-decision-intelligence-breakdown-json">
                  {JSON.stringify(decisionIntelligence.risk_breakdown || {}, null, 2)}
                </pre>
                <pre className="mt-1 max-h-44 overflow-auto rounded bg-slate-950 p-2 text-slate-100" data-testid="risk-decision-intelligence-diff-json">
                  {JSON.stringify(decisionIntelligence.before_after_diff || {}, null, 2)}
                </pre>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
      )}

      {activeTab === "control-tower" && (
      <div className="grid gap-5 xl:grid-cols-2" data-testid="risk-control-tower-grid">
        <Card data-testid="risk-control-tower-summary-card">
          <CardHeader>
            <CardTitle data-testid="risk-control-tower-summary-title">Operational Dashboard</CardTitle>
            <CardDescription data-testid="risk-control-tower-summary-description">
              Tek bakışta queue, reject spike, override kullanımı ve risk dağılımı.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-2 sm:grid-cols-2" data-testid="risk-control-tower-summary-metrics">
            <div className="rounded border p-2 text-xs" data-testid="ct-active-pending">
              active_pending: {dashboardData?.active_pending_approvals ?? "-"}
            </div>
            <div className="rounded border p-2 text-xs" data-testid="ct-critical-queue">
              critical_queue: {dashboardData?.critical_queue ?? "-"}
            </div>
            <div className="rounded border p-2 text-xs" data-testid="ct-unassigned">
              unassigned: {dashboardData?.unassigned ?? "-"}
            </div>
            <div className="rounded border p-2 text-xs" data-testid="ct-my-approvals">
              my_approvals: {dashboardData?.my_approvals ?? "-"}
            </div>
            <div className="rounded border p-2 text-xs" data-testid="ct-reject-spike">
              reject_spike_last_hour: {dashboardData?.reject_spike_last_hour ?? "-"}
            </div>
            <div className="rounded border p-2 text-xs" data-testid="ct-override-usage">
              override_usage: {dashboardData?.override_usage?.active_count ?? "-"} / {Number(dashboardData?.override_usage?.total_notional_pct || 0).toFixed(2)}%
            </div>
          </CardContent>
        </Card>

        <Card data-testid="risk-control-tower-distribution-card">
          <CardHeader>
            <CardTitle data-testid="risk-control-tower-distribution-title">Risk Score Distribution & Throughput</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="rounded border p-2 text-xs" data-testid="ct-risk-distribution-json">
              <pre>{JSON.stringify(dashboardData?.risk_score_distribution || {}, null, 2)}</pre>
            </div>
            <div className="rounded border p-2 text-xs" data-testid="ct-throughput-json">
              <pre>{JSON.stringify(dashboardData?.approval_throughput_last_hour || {}, null, 2)}</pre>
            </div>
          </CardContent>
        </Card>
      </div>
      )}

      <Dialog open={applyDialogOpen} onOpenChange={setApplyDialogOpen}>
        <DialogContent data-testid="risk-policy-apply-dialog">
          <DialogHeader>
            <DialogTitle data-testid="risk-policy-apply-dialog-title">Policy Apply Confirm</DialogTitle>
            <DialogDescription data-testid="risk-policy-apply-dialog-description">
              Simülasyon olmadan apply kapalıdır. Reason ve double-confirm zorunlu.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3" data-testid="risk-policy-apply-dialog-content">
            <p className="text-xs" data-testid="risk-policy-apply-dialog-simulation-id">
              simulation_id: {simulation?.simulation_id || "-"}
            </p>
            <p className="text-xs" data-testid="risk-policy-apply-dialog-gate">
              risk_score: {simulation?.risk_score ?? "-"} · class: {simulation?.classification || "-"}
            </p>
            <p className="text-xs text-slate-500" data-testid="risk-policy-apply-dialog-version-check">
              expected_policy_version: {status?.policy?.policy_version ?? "-"}
            </p>
            <Textarea
              value={applyReason}
              onChange={(event) => setApplyReason(event.target.value)}
              placeholder="Apply reason"
              data-testid="risk-policy-apply-reason-textarea"
            />
            <Textarea
              value={applyNote}
              onChange={(event) => setApplyNote(event.target.value)}
              placeholder="Approval note"
              data-testid="risk-policy-apply-note-textarea"
            />
            <div className="flex items-center gap-2" data-testid="risk-policy-apply-double-confirm-wrapper">
              <Checkbox
                checked={doubleConfirm}
                onCheckedChange={(checked) => setDoubleConfirm(checked === true)}
                data-testid="risk-policy-apply-double-confirm-checkbox"
              />
              <span className="text-xs">Evet, kritik değişikliğin canlı sistemi etkileyeceğini onaylıyorum.</span>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setApplyDialogOpen(false)} data-testid="risk-policy-apply-cancel-button">
              Vazgeç
            </Button>
            <Button
              onClick={handleApply}
              disabled={!isSuperAdmin || !doubleConfirm || !simulation}
              title={superAdminOnlyTitle}
              data-testid="risk-policy-apply-confirm-button"
            >
              Apply Policy
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={rejectDialogOpen} onOpenChange={setRejectDialogOpen}>
        <DialogContent data-testid="risk-reject-detail-dialog">
          <DialogHeader>
            <DialogTitle data-testid="risk-reject-detail-title">Reject Root Cause</DialogTitle>
            <DialogDescription data-testid="risk-reject-detail-description">
              İşlem reddinin kök nedeni ve metrik detayları.
            </DialogDescription>
          </DialogHeader>

          {rejectDetail && (
            <div className="space-y-2 text-xs" data-testid="risk-reject-detail-content">
              <p data-testid="risk-reject-detail-id">id: {rejectDetail.id}</p>
              <p data-testid="risk-reject-detail-root-cause">root_cause: {rejectDetail.root_cause || "-"}</p>
              <p data-testid="risk-reject-detail-symbol">symbol: {rejectDetail.symbol || "-"}</p>
              <p data-testid="risk-reject-detail-strategy">strategy: {rejectDetail.strategy_id || "-"}</p>
              <pre className="max-h-60 overflow-auto rounded bg-slate-950 p-2 text-slate-100" data-testid="risk-reject-detail-json">
                {JSON.stringify(rejectDetail.details || {}, null, 2)}
              </pre>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </section>
  );
};
