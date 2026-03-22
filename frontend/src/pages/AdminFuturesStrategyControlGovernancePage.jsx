import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { apiClient } from "@/lib/api";

const TAB_ITEMS = [
  { key: "overview", label: "Overview" },
  { key: "universe_control", label: "Universe Control" },
  { key: "rollout", label: "Rollout" },
  { key: "strategy_governance", label: "Strategy Governance" },
  { key: "capital_governance", label: "Capital Governance" },
  { key: "drift_action_center", label: "Drift Action Center" },
  { key: "audit_history", label: "Audit / History" },
];

const ACTIONS = [
  { key: "enable", label: "Enable" },
  { key: "throttle", label: "Throttle" },
  { key: "pause", label: "Pause" },
  { key: "resume", label: "Resume" },
  { key: "disable", label: "Disable", destructive: true, confirmPhrase: "DISABLE STRATEGY" },
  { key: "decommission", label: "Decommission", destructive: true, confirmPhrase: "DECOMMISSION STRATEGY" },
];

const BULK_CONFIRM_MAP = {
  pause: "BULK PAUSE",
  resume: "BULK RESUME",
  throttle: "BULK THROTTLE",
};

const ROLLOUT_CONFIRM_MAP = {
  promote_shadow: "PROMOTE SHADOW",
  rollout: "APPLY ROLLOUT",
  rollback: "ROLLBACK LAST ACTION",
};

export const AdminFuturesStrategyControlGovernancePage = () => {
  const [activeTab, setActiveTab] = useState("strategy_governance");
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [overviewPayload, setOverviewPayload] = useState(null);
  const [capitalPayload, setCapitalPayload] = useState({ budget: null, usage: null, drift: null, globalRisk: null });

  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailPayload, setDetailPayload] = useState(null);

  const [actionModal, setActionModal] = useState({ open: false, action: null, strategy: null });
  const [actionReason, setActionReason] = useState("");
  const [actionConfirm, setActionConfirm] = useState("");
  const [throttleLevel, setThrottleLevel] = useState("L1");
  const [dryRun, setDryRun] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [selectedStrategyIds, setSelectedStrategyIds] = useState([]);
  const [bulkAction, setBulkAction] = useState("pause");
  const [bulkReason, setBulkReason] = useState("");
  const [bulkConfirm, setBulkConfirm] = useState("");
  const [bulkThrottleLevel, setBulkThrottleLevel] = useState("L1");
  const [bulkSubmitting, setBulkSubmitting] = useState(false);
  const [bulkResult, setBulkResult] = useState(null);

  const [rolloutStrategyId, setRolloutStrategyId] = useState("");
  const [rolloutOperation, setRolloutOperation] = useState("rollout");
  const [rolloutReason, setRolloutReason] = useState("");
  const [rolloutConfirm, setRolloutConfirm] = useState("");
  const [rolloutPercentage, setRolloutPercentage] = useState(10);
  const [rolloutSubmitting, setRolloutSubmitting] = useState(false);
  const [rolloutPrecheck, setRolloutPrecheck] = useState(null);
  const [rolloutResult, setRolloutResult] = useState(null);

  const [lastActionResult, setLastActionResult] = useState(null);

  const actionMeta = useMemo(() => ACTIONS.find((item) => item.key === actionModal.action) || null, [actionModal.action]);
  const strategies = useMemo(() => overviewPayload?.strategies || [], [overviewPayload]);
  const selectedRolloutStrategy = useMemo(
    () => strategies.find((item) => item.strategy_id === rolloutStrategyId) || null,
    [rolloutStrategyId, strategies],
  );

  const strategyCount = strategies.length;
  const disabledCount = strategies.filter((row) => row.lifecycle_state === "DISABLED").length;
  const throttledCount = strategies.filter((row) => row.throttle_level !== "NONE").length;
  const driftCount = strategies.reduce((acc, row) => acc + Number(row.drift_count || 0), 0);

  const loadOverview = useCallback(async () => {
    const response = await apiClient.get("/admin/futures/strategy-control/overview");
    const data = response.data || null;
    setOverviewPayload(data);
    const firstId = data?.strategies?.[0]?.strategy_id || "";
    setRolloutStrategyId((prev) => prev || firstId);
  }, []);

  const loadCapital = useCallback(async () => {
    const [budgetRes, usageRes, driftRes, riskRes] = await Promise.all([
      apiClient.get("/admin/futures/capital-budget"),
      apiClient.get("/admin/futures/capital-usage"),
      apiClient.get("/admin/futures/capital-drift"),
      apiClient.get("/admin/futures/global-risk"),
    ]);
    setCapitalPayload({
      budget: budgetRes.data || null,
      usage: usageRes.data || null,
      drift: driftRes.data || null,
      globalRisk: riskRes.data || null,
    });
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setErrorMessage("");
    try {
      await Promise.all([loadOverview(), loadCapital()]);
    } catch (error) {
      const message = error?.response?.data?.detail || "Strategy Control verisi alınamadı";
      setErrorMessage(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [loadCapital, loadOverview]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const openDetail = async (strategyId) => {
    setDetailOpen(true);
    setDetailLoading(true);
    try {
      const [detailRes, auditRes] = await Promise.all([
        apiClient.get(`/admin/futures/strategy/${strategyId}/detail`),
        apiClient.get(`/admin/futures/strategy/${strategyId}/audit-history`),
      ]);
      setDetailPayload({
        ...(detailRes.data || {}),
        audit_items: (auditRes.data || {}).items || [],
      });
    } catch (error) {
      const message = error?.response?.data?.detail || "Strategy detail alınamadı";
      toast.error(message);
      setDetailPayload(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const openActionModal = (action, strategy) => {
    setActionModal({ open: true, action, strategy });
    setActionReason("");
    setActionConfirm("");
    setThrottleLevel("L1");
    setDryRun(false);
  };

  const submitAction = async () => {
    if (!actionModal.strategy || !actionMeta) return;
    if (String(actionReason || "").trim().length < 3) {
      toast.error("Reason zorunlu (min 3 karakter)");
      return;
    }
    if (actionMeta.confirmPhrase && actionConfirm.trim().toUpperCase() !== actionMeta.confirmPhrase) {
      toast.error(`Onay ifadesi eşleşmeli: ${actionMeta.confirmPhrase}`);
      return;
    }

    setSubmitting(true);
    try {
      const body = {
        reason: actionReason.trim(),
        confirm_phrase: actionConfirm.trim() || null,
        throttle_level: actionMeta.key === "throttle" ? throttleLevel : null,
        dry_run: dryRun,
      };
      const { data } = await apiClient.post(`/admin/futures/strategy/${actionModal.strategy.strategy_id}/${actionMeta.key}`, body);
      setLastActionResult(data || null);
      if (data?.status === "rejected") {
        toast.error(data?.message || "Aksiyon reddedildi");
      } else {
        toast.success(data?.message || "Aksiyon uygulandı");
      }
      await loadOverview();
      setActionModal({ open: false, action: null, strategy: null });
    } catch (error) {
      const message = error?.response?.data?.detail || "Aksiyon uygulanamadı";
      toast.error(message);
    } finally {
      setSubmitting(false);
    }
  };

  const toggleStrategySelect = (strategyId) => {
    setSelectedStrategyIds((prev) => (prev.includes(strategyId) ? prev.filter((id) => id !== strategyId) : [...prev, strategyId]));
  };

  const submitBulkAction = async () => {
    if (selectedStrategyIds.length === 0) {
      toast.error("Bulk için en az bir strategy seçmelisiniz");
      return;
    }
    if (bulkReason.trim().length < 3) {
      toast.error("Bulk reason zorunlu");
      return;
    }
    const expected = BULK_CONFIRM_MAP[bulkAction];
    if (bulkConfirm.trim().toUpperCase() !== expected) {
      toast.error(`Bulk confirm ifadesi eşleşmeli: ${expected}`);
      return;
    }

    setBulkSubmitting(true);
    try {
      const { data } = await apiClient.post("/admin/futures/strategy/bulk-action", {
        reason: bulkReason.trim(),
        confirm_phrase: bulkConfirm.trim(),
        strategy_ids: selectedStrategyIds,
        action: bulkAction,
        throttle_level: bulkAction === "throttle" ? bulkThrottleLevel : null,
        dry_run: false,
      });
      setBulkResult(data || null);
      setLastActionResult(data || null);
      if (data?.status === "rejected") toast.error(data?.message || "Bulk action reddedildi");
      else toast.success(data?.message || "Bulk action uygulandı");
      await loadOverview();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Bulk action başarısız");
    } finally {
      setBulkSubmitting(false);
    }
  };

  const loadRolloutPrecheck = async () => {
    if (!rolloutStrategyId) return;
    try {
      const { data } = await apiClient.get(`/admin/futures/strategy/${rolloutStrategyId}/rollout-precheck`);
      setRolloutPrecheck(data?.precheck || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Rollout pre-check alınamadı");
    }
  };

  const submitRolloutOperation = async () => {
    if (!rolloutStrategyId) {
      toast.error("Rollout için strategy seçin");
      return;
    }
    if (rolloutReason.trim().length < 3) {
      toast.error("Rollout reason zorunlu");
      return;
    }
    const expected = ROLLOUT_CONFIRM_MAP[rolloutOperation];
    if (rolloutConfirm.trim().toUpperCase() !== expected) {
      toast.error(`Onay ifadesi eşleşmeli: ${expected}`);
      return;
    }

    setRolloutSubmitting(true);
    try {
      let url = "";
      let body = { reason: rolloutReason.trim(), confirm_phrase: rolloutConfirm.trim(), dry_run: false };
      if (rolloutOperation === "promote_shadow") {
        url = `/admin/futures/strategy/${rolloutStrategyId}/promote-shadow`;
      } else if (rolloutOperation === "rollout") {
        url = `/admin/futures/strategy/${rolloutStrategyId}/rollout`;
        body = { ...body, rollout_percentage: Number(rolloutPercentage || 10) };
      } else {
        url = `/admin/futures/strategy/${rolloutStrategyId}/rollback`;
      }

      const { data } = await apiClient.post(url, body);
      setRolloutResult(data || null);
      setLastActionResult(data || null);
      if (data?.status === "rejected") toast.error(data?.message || "Rollout aksiyonu reddedildi");
      else if (data?.status === "auto_rollback") toast.error(data?.message || "Auto rollback tetiklendi");
      else toast.success(data?.message || "Rollout aksiyonu tamamlandı");

      await loadOverview();
      await loadRolloutPrecheck();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Rollout aksiyonu başarısız");
    } finally {
      setRolloutSubmitting(false);
    }
  };

  return (
    <section className="space-y-4" data-testid="strategy-control-governance-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="strategy-control-governance-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-black" data-testid="strategy-control-governance-title">
          Strategy Control + Governance System
        </h2>
        <p className="mt-2 text-sm text-black/80" data-testid="strategy-control-governance-description">
          Faz-2 kapsamı: rollout/shadow kontrolü, güvenli bulk operasyon (pause/resume/throttle) ve tek-adım rollback.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3 border border-black/30 bg-orange-100 p-4" data-testid="strategy-control-governance-toolbar">
        <Button className="border border-black bg-black text-orange-400 hover:bg-zinc-800" onClick={loadAll} data-testid="strategy-control-governance-refresh-button">
          Yenile
        </Button>
        <p className="text-sm text-black" data-testid="strategy-control-governance-loading-text">loading: {String(loading)}</p>
        <p className="text-sm text-black" data-testid="strategy-control-governance-phase-scope-text">scope: {overviewPayload?.phase_scope || "phase_2_rollout_bulk_rollback"}</p>
      </div>

      {loading && <div className="border border-black/25 bg-orange-50 p-4 text-sm" data-testid="strategy-control-governance-loading-state">Strategy Control paneli yükleniyor...</div>}
      {!loading && Boolean(errorMessage) && (
        <div className="border border-red-700 bg-red-100 p-4 text-sm text-red-900" data-testid="strategy-control-governance-error-state">
          Hata: {errorMessage}
        </div>
      )}

      {!loading && !errorMessage && (
        <>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4" data-testid="strategy-control-governance-summary-grid">
            <MetricCard testId="strategy-control-summary-strategy-count" title="Strategies" value={strategyCount} />
            <MetricCard testId="strategy-control-summary-disabled" title="Disabled" value={disabledCount} />
            <MetricCard testId="strategy-control-summary-throttled" title="Throttled" value={throttledCount} />
            <MetricCard testId="strategy-control-summary-drift" title="Drift Alerts" value={driftCount} />
          </div>

          <Tabs value={activeTab} onValueChange={setActiveTab} data-testid="strategy-control-governance-tabs-root">
            <TabsList className="h-auto flex-wrap justify-start gap-1 bg-orange-200 p-1" data-testid="strategy-control-governance-tabs-list">
              {TAB_ITEMS.map((tab) => (
                <TabsTrigger key={tab.key} value={tab.key} className="border border-black/20 data-[state=active]:bg-black data-[state=active]:text-orange-300" data-testid={`strategy-control-tab-trigger-${tab.key}`}>
                  {tab.label}
                </TabsTrigger>
              ))}
            </TabsList>

            <TabsContent value="overview" data-testid="strategy-control-tab-overview">
              <StrategyTable rows={strategies} onOpenDetail={openDetail} onRunAction={openActionModal} compact selectedStrategyIds={selectedStrategyIds} onToggleStrategy={null} />
            </TabsContent>

            <TabsContent value="universe_control" data-testid="strategy-control-tab-universe-control">
              <PlaceholderPanel testId="strategy-control-universe-control-placeholder" title="Universe Control" reason="Bu iterasyonda odak rollout/bulk/rollback; universe kapsamı değişmedi." />
            </TabsContent>

            <TabsContent value="rollout" data-testid="strategy-control-tab-rollout">
              <div className="space-y-3 border border-black/25 bg-orange-100 p-4" data-testid="strategy-control-rollout-panel">
                <h3 className="text-base font-semibold" data-testid="strategy-control-rollout-title">Rollout / Shadow Control</h3>

                <div className="grid gap-3 md:grid-cols-2" data-testid="strategy-control-rollout-controls-grid">
                  <div className="space-y-2" data-testid="strategy-control-rollout-strategy-selector-block">
                    <p className="text-xs" data-testid="strategy-control-rollout-strategy-selector-label">Strategy</p>
                    <select className="h-10 rounded border border-black/40 bg-white px-3 text-sm" value={rolloutStrategyId} onChange={(e) => setRolloutStrategyId(e.target.value)} data-testid="strategy-control-rollout-strategy-select">
                      {strategies.map((row) => (
                        <option key={row.strategy_id} value={row.strategy_id}>{row.strategy_id}</option>
                      ))}
                    </select>
                    <Button size="sm" variant="outline" onClick={loadRolloutPrecheck} data-testid="strategy-control-rollout-precheck-button">Pre-check Çalıştır</Button>
                  </div>

                  <div className="space-y-2" data-testid="strategy-control-rollout-operation-block">
                    <p className="text-xs" data-testid="strategy-control-rollout-operation-label">Operation</p>
                    <select className="h-10 rounded border border-black/40 bg-white px-3 text-sm" value={rolloutOperation} onChange={(e) => setRolloutOperation(e.target.value)} data-testid="strategy-control-rollout-operation-select">
                      <option value="promote_shadow">Promote Shadow</option>
                      <option value="rollout">Apply Rollout %</option>
                      <option value="rollback">Rollback Last Action</option>
                    </select>
                    {rolloutOperation === "rollout" && (
                      <select className="h-10 rounded border border-black/40 bg-white px-3 text-sm" value={rolloutPercentage} onChange={(e) => setRolloutPercentage(Number(e.target.value))} data-testid="strategy-control-rollout-percentage-select">
                        <option value={10}>10%</option>
                        <option value={25}>25%</option>
                        <option value={50}>50%</option>
                        <option value={100}>100%</option>
                      </select>
                    )}
                  </div>
                </div>

                <Textarea value={rolloutReason} onChange={(e) => setRolloutReason(e.target.value)} placeholder="Rollout nedeni" className="border-black/40" data-testid="strategy-control-rollout-reason-input" />
                <Input value={rolloutConfirm} onChange={(e) => setRolloutConfirm(e.target.value)} placeholder={`Onay ifadesi: ${ROLLOUT_CONFIRM_MAP[rolloutOperation]}`} className="border-black/40" data-testid="strategy-control-rollout-confirm-input" />
                <Button onClick={submitRolloutOperation} disabled={rolloutSubmitting} className="border border-black bg-black text-orange-300" data-testid="strategy-control-rollout-submit-button">
                  {rolloutSubmitting ? "Çalışıyor..." : "Rollout Aksiyonunu Uygula"}
                </Button>

                {selectedRolloutStrategy && (
                  <div className="rounded border border-black/20 bg-orange-50 p-2" data-testid="strategy-control-rollout-selected-state-card">
                    <p className="text-xs" data-testid="strategy-control-rollout-selected-state-strategy">strategy={selectedRolloutStrategy.strategy_id}</p>
                    <p className="text-xs" data-testid="strategy-control-rollout-selected-state-mode">mode={selectedRolloutStrategy.rollout_mode} percentage={selectedRolloutStrategy.rollout_percentage}%</p>
                    <p className="text-xs" data-testid="strategy-control-rollout-selected-state-health">health={selectedRolloutStrategy.health_score} error_rate={selectedRolloutStrategy.error_rate_pct}%</p>
                  </div>
                )}

                {rolloutPrecheck && (
                  <div className="rounded border border-black/20 bg-orange-50 p-3" data-testid="strategy-control-rollout-precheck-result-card">
                    <p className="text-xs font-semibold" data-testid="strategy-control-rollout-precheck-status">precheck_status={rolloutPrecheck.status}</p>
                    <p className="text-xs" data-testid="strategy-control-rollout-precheck-health">health_ok={String(rolloutPrecheck?.checks?.health?.ok)}</p>
                    <p className="text-xs" data-testid="strategy-control-rollout-precheck-error">recent_error_ok={String(rolloutPrecheck?.checks?.recent_error?.ok)}</p>
                    <p className="text-xs" data-testid="strategy-control-rollout-precheck-drift">drift_ok={String(rolloutPrecheck?.checks?.drift?.ok)}</p>
                    <p className="text-xs" data-testid="strategy-control-rollout-precheck-checklist">checklist_ok={String(rolloutPrecheck?.checks?.checklist?.ok)}</p>
                  </div>
                )}

                {rolloutResult && (
                  <div className="rounded border border-black/20 bg-orange-50 p-3" data-testid="strategy-control-rollout-result-card">
                    <p className="text-xs" data-testid="strategy-control-rollout-result-status">status={rolloutResult.status}</p>
                    <p className="text-xs" data-testid="strategy-control-rollout-result-trace">trace_id={rolloutResult.trace_id}</p>
                    <p className="text-xs" data-testid="strategy-control-rollout-result-message">message={rolloutResult.message}</p>
                    {rolloutResult?.auto_rollback?.triggered && (
                      <p className="text-xs text-red-900" data-testid="strategy-control-rollout-result-auto-rollback-info">
                        auto_rollback_reason={(rolloutResult?.auto_rollback?.reason || []).join(";")} · thresholds=health&lt;50,error&gt;3%
                      </p>
                    )}
                  </div>
                )}
              </div>
            </TabsContent>

            <TabsContent value="strategy_governance" data-testid="strategy-control-tab-strategy-governance">
              <div className="mb-3 space-y-2 rounded border border-black/25 bg-orange-100 p-4" data-testid="strategy-control-bulk-panel">
                <h3 className="text-base font-semibold" data-testid="strategy-control-bulk-title">Bulk Operation (safe scope)</h3>
                <p className="text-xs" data-testid="strategy-control-bulk-scope-note">Kapsam bilinçli sınırlı: pause / resume / throttle. Disable/Decommission bulk yok.</p>
                <div className="grid gap-2 md:grid-cols-2" data-testid="strategy-control-bulk-controls-grid">
                  <select className="h-10 rounded border border-black/40 bg-white px-3 text-sm" value={bulkAction} onChange={(e) => setBulkAction(e.target.value)} data-testid="strategy-control-bulk-action-select">
                    <option value="pause">pause</option>
                    <option value="resume">resume</option>
                    <option value="throttle">throttle</option>
                  </select>
                  {bulkAction === "throttle" && (
                    <select className="h-10 rounded border border-black/40 bg-white px-3 text-sm" value={bulkThrottleLevel} onChange={(e) => setBulkThrottleLevel(e.target.value)} data-testid="strategy-control-bulk-throttle-level-select">
                      <option value="L1">L1</option>
                      <option value="L2">L2</option>
                      <option value="L3">L3</option>
                    </select>
                  )}
                </div>
                <Textarea value={bulkReason} onChange={(e) => setBulkReason(e.target.value)} placeholder="Bulk action nedeni" className="border-black/40" data-testid="strategy-control-bulk-reason-input" />
                <Input value={bulkConfirm} onChange={(e) => setBulkConfirm(e.target.value)} placeholder={`Onay ifadesi: ${BULK_CONFIRM_MAP[bulkAction]}`} className="border-black/40" data-testid="strategy-control-bulk-confirm-input" />
                <Button onClick={submitBulkAction} disabled={bulkSubmitting} className="border border-black bg-black text-orange-300" data-testid="strategy-control-bulk-submit-button">
                  {bulkSubmitting ? "Bulk çalışıyor..." : "Bulk Action Uygula"}
                </Button>
                {bulkResult && (
                  <p className="text-xs" data-testid="strategy-control-bulk-result-text">{bulkResult.message}</p>
                )}
              </div>

              <StrategyTable rows={strategies} onOpenDetail={openDetail} onRunAction={openActionModal} selectedStrategyIds={selectedStrategyIds} onToggleStrategy={toggleStrategySelect} />
            </TabsContent>

            <TabsContent value="capital_governance" data-testid="strategy-control-tab-capital-governance">
              <div className="grid gap-3 md:grid-cols-2" data-testid="strategy-control-capital-summary-grid">
                <MetricCard testId="strategy-control-capital-equity" title="Portfolio Equity" value={capitalPayload?.budget?.portfolio_capital_registry?.portfolio_equity ?? 0} />
                <MetricCard testId="strategy-control-capital-risk-state" title="Global Risk" value={`${capitalPayload?.globalRisk?.risk_state || "NORMAL"} (${capitalPayload?.globalRisk?.global_risk_score ?? 0})`} />
              </div>
              <div className="mt-3 border border-black/25 bg-orange-100 p-4" data-testid="strategy-control-capital-drift-panel">
                <h3 className="text-base font-semibold" data-testid="strategy-control-capital-drift-title">Capital Drift Events</h3>
                {(capitalPayload?.drift?.capital_drift_events || []).length === 0 && <p className="mt-2 text-sm" data-testid="strategy-control-capital-drift-empty">No data yet: aktif capital drift eventi bulunmuyor.</p>}
                {(capitalPayload?.drift?.capital_drift_events || []).map((item, index) => (
                  <p key={`${item?.strategy_id}-${index}`} className="mt-1 text-xs" data-testid={`strategy-control-capital-drift-item-${index}`}>
                    {item?.strategy_id}: severity={item?.drift_severity} reason={(item?.reasons || []).join(",")}
                  </p>
                ))}
              </div>
            </TabsContent>

            <TabsContent value="drift_action_center" data-testid="strategy-control-tab-drift-action-center">
              <div className="border border-black/25 bg-orange-100 p-4" data-testid="strategy-control-drift-action-center-panel">
                <h3 className="text-base font-semibold" data-testid="strategy-control-drift-action-center-title">Drift Action Center</h3>
                <p className="mt-1 text-xs" data-testid="strategy-control-drift-action-center-reason">Faz-3 backlog: Ack/Mute/Disable/Retrain/Ignore aksiyonları bu turda açılmadı.</p>
              </div>
            </TabsContent>

            <TabsContent value="audit_history" data-testid="strategy-control-tab-audit-history">
              <div className="border border-black/25 bg-orange-100 p-4" data-testid="strategy-control-audit-history-panel">
                <h3 className="text-base font-semibold" data-testid="strategy-control-audit-history-title">Last Action Result</h3>
                {!lastActionResult && <p className="mt-2 text-sm" data-testid="strategy-control-audit-history-empty">No data yet: bu oturumda henüz aksiyon çalıştırılmadı.</p>}
                {lastActionResult && (
                  <div className="mt-2 rounded border border-black/20 bg-orange-50 p-3" data-testid="strategy-control-audit-history-last-action-card">
                    <p className="text-xs" data-testid="strategy-control-audit-history-last-action-status">status={lastActionResult.status}</p>
                    <p className="text-xs" data-testid="strategy-control-audit-history-last-action-trace">trace_id={lastActionResult.trace_id}</p>
                    <p className="text-xs" data-testid="strategy-control-audit-history-last-action-message">message={lastActionResult.message}</p>
                  </div>
                )}
              </div>
            </TabsContent>
          </Tabs>
        </>
      )}

      <Dialog open={actionModal.open} onOpenChange={(open) => setActionModal((prev) => ({ ...prev, open }))}>
        <DialogContent className="border border-black/40 bg-orange-50" data-testid="strategy-control-action-dialog">
          <DialogHeader>
            <DialogTitle data-testid="strategy-control-action-dialog-title">{actionMeta?.label || "Action"} · {actionModal.strategy?.strategy_id || "-"}</DialogTitle>
            <DialogDescription data-testid="strategy-control-action-dialog-description">Reason + confirm + audit zorunludur. Disable/Decommission ekstra güvenlik kontrolü içerir.</DialogDescription>
          </DialogHeader>
          <Textarea value={actionReason} onChange={(e) => setActionReason(e.target.value)} placeholder="Neden bu aksiyonu alıyorsunuz?" className="border-black/40" data-testid="strategy-control-action-dialog-reason-input" />
          {actionMeta?.key === "throttle" && (
            <select value={throttleLevel} onChange={(e) => setThrottleLevel(e.target.value)} className="h-10 rounded border border-black/40 bg-white px-3 text-sm" data-testid="strategy-control-action-dialog-throttle-level-select">
              <option value="L1">L1</option>
              <option value="L2">L2</option>
              <option value="L3">L3</option>
            </select>
          )}
          {actionMeta?.confirmPhrase && <Input value={actionConfirm} onChange={(e) => setActionConfirm(e.target.value)} placeholder={`Onay ifadesi: ${actionMeta.confirmPhrase}`} className="border-black/40" data-testid="strategy-control-action-dialog-confirm-input" />}
          <label className="flex items-center gap-2 text-xs" data-testid="strategy-control-action-dialog-dry-run-label">
            <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} data-testid="strategy-control-action-dialog-dry-run-checkbox" />
            dry-run (state yazmadan önizleme)
          </label>
          <DialogFooter>
            <Button variant="outline" onClick={() => setActionModal({ open: false, action: null, strategy: null })} data-testid="strategy-control-action-dialog-cancel-button">Vazgeç</Button>
            <Button onClick={submitAction} disabled={submitting} className="border border-black bg-black text-orange-300" data-testid="strategy-control-action-dialog-submit-button">
              {submitting ? "Uygulanıyor..." : "Aksiyonu Uygula"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Sheet open={detailOpen} onOpenChange={setDetailOpen}>
        <SheetContent side="right" className="w-[92vw] max-w-2xl overflow-y-auto border-l border-black bg-orange-50" data-testid="strategy-control-detail-drawer">
          <SheetHeader>
            <SheetTitle data-testid="strategy-control-detail-drawer-title">Strategy Detail</SheetTitle>
            <SheetDescription data-testid="strategy-control-detail-drawer-description">Trade list / execution log / export Faz-2 içinde placeholder olarak sunulur.</SheetDescription>
          </SheetHeader>
          {detailLoading && <p className="mt-4 text-sm" data-testid="strategy-control-detail-loading">Detail yükleniyor...</p>}
          {!detailLoading && !detailPayload && <p className="mt-4 text-sm" data-testid="strategy-control-detail-empty">No data yet: strategy detay verisi alınamadı.</p>}
          {!detailLoading && detailPayload && (
            <div className="mt-4 space-y-4" data-testid="strategy-control-detail-content">
              <InfoCard testId="strategy-control-detail-summary-card" lines={[
                `strategy=${detailPayload?.strategy?.strategy_id}`,
                `state=${detailPayload?.strategy?.control_state} lifecycle=${detailPayload?.strategy?.lifecycle_state}`,
                `rollout_mode=${detailPayload?.strategy?.rollout_mode} rollout_percentage=${detailPayload?.strategy?.rollout_percentage}%`,
              ]} />
              <InfoCard testId="strategy-control-detail-trade-list-panel" title="Trade List" lines={[detailPayload?.trade_list?.reason || "No data yet"]} />
              <InfoCard testId="strategy-control-detail-execution-log-panel" title="Execution Log" lines={[detailPayload?.execution_history?.reason || "No data yet"]} />
              <InfoCard testId="strategy-control-detail-transition-history-panel" title="Transition History" lines={(detailPayload?.transition_history || []).map((item) => `${item?.from || "NONE"}→${item?.to || "NONE"} reason=${item?.reason || "-"}`)} emptyText="No data yet: geçiş geçmişi bulunmuyor." />
              <InfoCard testId="strategy-control-detail-audit-history-panel" title="Audit History" lines={(detailPayload?.audit_items || []).map((item) => `${item?.created_at || "-"} · ${item?.action || "-"} · severity=${item?.severity || "-"}`)} emptyText="No data yet: strategy için audit kaydı bulunmuyor." />
            </div>
          )}
        </SheetContent>
      </Sheet>
    </section>
  );
};

const MetricCard = ({ testId, title, value }) => (
  <div className="border border-black/25 bg-orange-100 p-3" data-testid={`${testId}-card`}>
    <p className="text-xs uppercase" data-testid={`${testId}-title`}>{title}</p>
    <p className="text-xl font-bold" data-testid={`${testId}-value`}>{value}</p>
  </div>
);

const PlaceholderPanel = ({ testId, title, reason }) => (
  <div className="border border-black/25 bg-orange-100 p-4" data-testid={testId}>
    <h3 className="text-base font-semibold" data-testid={`${testId}-title`}>{title}</h3>
    <p className="mt-1 text-sm" data-testid={`${testId}-reason`}>No data yet: {reason}</p>
  </div>
);

const InfoCard = ({ testId, title, lines = [], emptyText }) => (
  <div className="rounded border border-black/20 bg-orange-100 p-3" data-testid={testId}>
    {title && <h4 className="text-sm font-semibold" data-testid={`${testId}-title`}>{title}</h4>}
    {lines.length === 0 && <p className="text-xs" data-testid={`${testId}-empty`}>{emptyText || "No data yet"}</p>}
    {lines.map((line, idx) => (
      <p key={`${testId}-${idx}`} className="text-xs" data-testid={`${testId}-line-${idx}`}>{line}</p>
    ))}
  </div>
);

const StrategyTable = ({ rows, onOpenDetail, onRunAction, compact = false, selectedStrategyIds, onToggleStrategy }) => (
  <div className="border border-black/25 bg-orange-100" data-testid={compact ? "strategy-control-table-compact" : "strategy-control-table-full"}>
    <div className="border-b border-black/20 px-4 py-3" data-testid={compact ? "strategy-control-table-compact-header" : "strategy-control-table-full-header"}>
      <h3 className="text-base font-semibold" data-testid={compact ? "strategy-control-table-compact-title" : "strategy-control-table-full-title"}>Strategy Lifecycle Control</h3>
    </div>
    <Table data-testid={compact ? "strategy-control-table-compact-table" : "strategy-control-table-full-table"}>
      <TableHeader>
        <TableRow>
          {onToggleStrategy && <TableHead data-testid="strategy-control-table-head-select">Select</TableHead>}
          <TableHead data-testid="strategy-control-table-head-strategy">Strategy</TableHead>
          <TableHead data-testid="strategy-control-table-head-state">State</TableHead>
          <TableHead data-testid="strategy-control-table-head-shadow-live">Shadow/Live</TableHead>
          <TableHead data-testid="strategy-control-table-head-rollout">Rollout</TableHead>
          <TableHead data-testid="strategy-control-table-head-health">Health</TableHead>
          <TableHead data-testid="strategy-control-table-head-error">Error%</TableHead>
          <TableHead data-testid="strategy-control-table-head-actions">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row, index) => (
          <TableRow key={row.strategy_id} data-testid={`strategy-control-table-row-${index}`}>
            {onToggleStrategy && (
              <TableCell data-testid={`strategy-control-table-select-${index}`}>
                <input type="checkbox" checked={selectedStrategyIds.includes(row.strategy_id)} onChange={() => onToggleStrategy(row.strategy_id)} data-testid={`strategy-control-table-select-checkbox-${index}`} />
              </TableCell>
            )}
            <TableCell data-testid={`strategy-control-table-strategy-${index}`}>{row.strategy_id}</TableCell>
            <TableCell data-testid={`strategy-control-table-state-${index}`}>{row.control_state} / {row.throttle_level}</TableCell>
            <TableCell data-testid={`strategy-control-table-shadow-live-${index}`}>{row.shadow_live_state}</TableCell>
            <TableCell data-testid={`strategy-control-table-rollout-${index}`}>{row.rollout_mode} / {row.rollout_percentage}%</TableCell>
            <TableCell data-testid={`strategy-control-table-health-${index}`}>{row.health_score}</TableCell>
            <TableCell data-testid={`strategy-control-table-error-${index}`}>{row.error_rate_pct}</TableCell>
            <TableCell data-testid={`strategy-control-table-actions-${index}`}>
              <div className="flex flex-wrap gap-1">
                <Button size="sm" variant="outline" onClick={() => onOpenDetail(row.strategy_id)} data-testid={`strategy-control-open-detail-button-${index}`}>Detail</Button>
                {ACTIONS.map((action) => (
                  <Button key={`${row.strategy_id}-${action.key}`} size="sm" variant="outline" onClick={() => onRunAction(action.key, row)} className={action.destructive ? "border-red-800 text-red-900" : ""} data-testid={`strategy-control-action-${action.key}-button-${index}`}>{action.label}</Button>
                ))}
              </div>
            </TableCell>
          </TableRow>
        ))}
        {rows.length === 0 && (
          <TableRow data-testid="strategy-control-table-empty-row">
            <TableCell colSpan={onToggleStrategy ? 8 : 7} className="text-center text-sm" data-testid="strategy-control-table-empty-text">No data yet: strategy kayıtları henüz oluşmadı veya geçici olarak alınamadı.</TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  </div>
);
