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
  const [lastActionResult, setLastActionResult] = useState(null);

  const actionMeta = useMemo(() => ACTIONS.find((item) => item.key === actionModal.action) || null, [actionModal.action]);
  const strategies = useMemo(() => overviewPayload?.strategies || [], [overviewPayload]);
  const strategyCount = strategies.length;
  const disabledCount = strategies.filter((row) => row.lifecycle_state === "DISABLED").length;
  const throttledCount = strategies.filter((row) => row.throttle_level !== "NONE").length;
  const driftCount = strategies.reduce((acc, row) => acc + Number(row.drift_count || 0), 0);

  const loadOverview = useCallback(async () => {
    const response = await apiClient.get("/admin/futures/strategy-control/overview");
    setOverviewPayload(response.data || null);
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
      const { data } = await apiClient.post(
        `/admin/futures/strategy/${actionModal.strategy.strategy_id}/${actionMeta.key}`,
        body,
      );

      setLastActionResult(data || null);
      if (data?.status === "rejected") {
        toast.error(data?.message || "Aksiyon reddedildi");
      } else {
        toast.success(data?.message || "Aksiyon uygulandı");
      }

      await loadOverview();
      if (detailOpen && detailPayload?.strategy?.strategy_id === actionModal.strategy.strategy_id) {
        await openDetail(actionModal.strategy.strategy_id);
      }
      setActionModal({ open: false, action: null, strategy: null });
    } catch (error) {
      const message = error?.response?.data?.detail || "Aksiyon uygulanamadı";
      toast.error(message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="space-y-4" data-testid="strategy-control-governance-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="strategy-control-governance-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-black" data-testid="strategy-control-governance-title">
          Strategy Control + Governance System
        </h2>
        <p className="mt-2 text-sm text-black/80" data-testid="strategy-control-governance-description">
          Faz-1 kapsamı: lifecycle kontrolü, reason/confirm güvenlik katmanı, super_admin aksiyon yetkisi ve audit-first governance.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3 border border-black/30 bg-orange-100 p-4" data-testid="strategy-control-governance-toolbar">
        <Button className="border border-black bg-black text-orange-400 hover:bg-zinc-800" onClick={loadAll} data-testid="strategy-control-governance-refresh-button">
          Yenile
        </Button>
        <p className="text-sm text-black" data-testid="strategy-control-governance-loading-text">loading: {String(loading)}</p>
        <p className="text-sm text-black" data-testid="strategy-control-governance-phase-scope-text">scope: {overviewPayload?.phase_scope || "phase_1_control_foundation"}</p>
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
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="strategy-control-summary-strategy-count-card">
              <p className="text-xs uppercase">Strategies</p>
              <p className="text-xl font-bold" data-testid="strategy-control-summary-strategy-count-value">{strategyCount}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="strategy-control-summary-disabled-card">
              <p className="text-xs uppercase">Disabled</p>
              <p className="text-xl font-bold" data-testid="strategy-control-summary-disabled-value">{disabledCount}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="strategy-control-summary-throttled-card">
              <p className="text-xs uppercase">Throttled</p>
              <p className="text-xl font-bold" data-testid="strategy-control-summary-throttled-value">{throttledCount}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="strategy-control-summary-drift-card">
              <p className="text-xs uppercase">Drift Alerts</p>
              <p className="text-xl font-bold" data-testid="strategy-control-summary-drift-value">{driftCount}</p>
            </div>
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
              <StrategyTable rows={strategies} onOpenDetail={openDetail} onRunAction={openActionModal} compact />
            </TabsContent>

            <TabsContent value="universe_control" data-testid="strategy-control-tab-universe-control">
              <PlaceholderPanel
                testId="strategy-control-universe-control-placeholder"
                title="Universe Control"
                reason="Faz-1 odak alanı strategy lifecycle olduğu için Universe Control aksiyonları Faz-2 backlog'a alındı."
              />
            </TabsContent>

            <TabsContent value="rollout" data-testid="strategy-control-tab-rollout">
              <PlaceholderPanel
                testId="strategy-control-rollout-placeholder"
                title="Rollout"
                reason="Canary %10→25→50→100 ve health-gate auto-rollback davranışı tanımlandı; implementasyon Faz-2 backlog."
              />
            </TabsContent>

            <TabsContent value="strategy_governance" data-testid="strategy-control-tab-strategy-governance">
              <StrategyTable rows={strategies} onOpenDetail={openDetail} onRunAction={openActionModal} />
            </TabsContent>

            <TabsContent value="capital_governance" data-testid="strategy-control-tab-capital-governance">
              <div className="grid gap-3 md:grid-cols-2" data-testid="strategy-control-capital-summary-grid">
                <div className="border border-black/25 bg-orange-100 p-3" data-testid="strategy-control-capital-equity-card">
                  <p className="text-xs uppercase">Portfolio Equity</p>
                  <p className="text-lg font-bold" data-testid="strategy-control-capital-equity-value">
                    {capitalPayload?.budget?.portfolio_capital_registry?.portfolio_equity ?? 0}
                  </p>
                </div>
                <div className="border border-black/25 bg-orange-100 p-3" data-testid="strategy-control-capital-risk-state-card">
                  <p className="text-xs uppercase">Global Risk</p>
                  <p className="text-lg font-bold" data-testid="strategy-control-capital-risk-state-value">
                    {(capitalPayload?.globalRisk?.risk_state || "NORMAL")} ({capitalPayload?.globalRisk?.global_risk_score ?? 0})
                  </p>
                </div>
              </div>
              <div className="mt-3 border border-black/25 bg-orange-100 p-4" data-testid="strategy-control-capital-drift-panel">
                <h3 className="text-base font-semibold" data-testid="strategy-control-capital-drift-title">Capital Drift Events</h3>
                {(capitalPayload?.drift?.capital_drift_events || []).length === 0 && (
                  <p className="mt-2 text-sm" data-testid="strategy-control-capital-drift-empty">No data yet: aktif capital drift eventi bulunmuyor.</p>
                )}
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
                <p className="mt-1 text-xs" data-testid="strategy-control-drift-action-center-reason">
                  Faz-1 içinde sadece görünürlük sağlanır. Ack/Mute/Disable/Retrain aksiyonları Faz-3 kapsamında açılacaktır.
                </p>
                {strategies.filter((row) => row.drift_count > 0).map((row, index) => (
                  <div key={row.strategy_id} className="mt-2 rounded border border-black/20 bg-orange-50 p-2" data-testid={`strategy-control-drift-action-center-item-${index}`}>
                    <p className="text-xs" data-testid={`strategy-control-drift-action-center-item-strategy-${index}`}>
                      {row.strategy_id}: drift={row.drift_count} severity={row.drift_severity}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-2" data-testid={`strategy-control-drift-action-center-item-actions-${index}`}>
                      <Button size="sm" variant="outline" disabled data-testid={`strategy-control-drift-ack-button-${index}`}>Ack (Faz-3)</Button>
                      <Button size="sm" variant="outline" disabled data-testid={`strategy-control-drift-mute-button-${index}`}>Mute (Faz-3)</Button>
                      <Button size="sm" variant="outline" disabled data-testid={`strategy-control-drift-disable-button-${index}`}>Disable (Faz-3)</Button>
                    </div>
                  </div>
                ))}
                {strategies.filter((row) => row.drift_count > 0).length === 0 && (
                  <p className="mt-2 text-sm" data-testid="strategy-control-drift-action-center-empty">No data yet: action gerektiren drift alarmı yok.</p>
                )}
              </div>
            </TabsContent>

            <TabsContent value="audit_history" data-testid="strategy-control-tab-audit-history">
              <div className="border border-black/25 bg-orange-100 p-4" data-testid="strategy-control-audit-history-panel">
                <h3 className="text-base font-semibold" data-testid="strategy-control-audit-history-title">Last Action Result</h3>
                {!lastActionResult && (
                  <p className="mt-2 text-sm" data-testid="strategy-control-audit-history-empty">No data yet: bu oturumda henüz aksiyon çalıştırılmadı.</p>
                )}
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
            <DialogTitle data-testid="strategy-control-action-dialog-title">
              {actionMeta?.label || "Action"} · {actionModal.strategy?.strategy_id || "-"}
            </DialogTitle>
            <DialogDescription data-testid="strategy-control-action-dialog-description">
              Kritik aksiyonlarda reason + confirm + audit log zorunludur. Disable/Decommission için rollback referansı üretilir.
            </DialogDescription>
          </DialogHeader>

          <Textarea
            value={actionReason}
            onChange={(event) => setActionReason(event.target.value)}
            placeholder="Neden bu aksiyonu alıyorsunuz?"
            className="border-black/40"
            data-testid="strategy-control-action-dialog-reason-input"
          />

          {actionMeta?.key === "throttle" && (
            <select
              value={throttleLevel}
              onChange={(event) => setThrottleLevel(event.target.value)}
              className="h-10 rounded border border-black/40 bg-white px-3 text-sm"
              data-testid="strategy-control-action-dialog-throttle-level-select"
            >
              <option value="L1">L1</option>
              <option value="L2">L2</option>
              <option value="L3">L3</option>
            </select>
          )}

          {actionMeta?.confirmPhrase && (
            <Input
              value={actionConfirm}
              onChange={(event) => setActionConfirm(event.target.value)}
              placeholder={`Onay ifadesi: ${actionMeta.confirmPhrase}`}
              className="border-black/40"
              data-testid="strategy-control-action-dialog-confirm-input"
            />
          )}

          <label className="flex items-center gap-2 text-xs" data-testid="strategy-control-action-dialog-dry-run-label">
            <input type="checkbox" checked={dryRun} onChange={(event) => setDryRun(event.target.checked)} data-testid="strategy-control-action-dialog-dry-run-checkbox" />
            dry-run (state yazmadan önizleme)
          </label>

          <DialogFooter>
            <Button variant="outline" onClick={() => setActionModal({ open: false, action: null, strategy: null })} data-testid="strategy-control-action-dialog-cancel-button">
              Vazgeç
            </Button>
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
            <SheetDescription data-testid="strategy-control-detail-drawer-description">
              Trade list / execution log / export Faz-1 içinde placeholder olarak sunulur.
            </SheetDescription>
          </SheetHeader>

          {detailLoading && <p className="mt-4 text-sm" data-testid="strategy-control-detail-loading">Detail yükleniyor...</p>}
          {!detailLoading && !detailPayload && <p className="mt-4 text-sm" data-testid="strategy-control-detail-empty">No data yet: strategy detay verisi alınamadı.</p>}

          {!detailLoading && detailPayload && (
            <div className="mt-4 space-y-4" data-testid="strategy-control-detail-content">
              <div className="rounded border border-black/20 bg-orange-100 p-3" data-testid="strategy-control-detail-summary-card">
                <p className="text-xs" data-testid="strategy-control-detail-summary-strategy">strategy={detailPayload?.strategy?.strategy_id}</p>
                <p className="text-xs" data-testid="strategy-control-detail-summary-state">state={detailPayload?.strategy?.control_state} lifecycle={detailPayload?.strategy?.lifecycle_state}</p>
                <p className="text-xs" data-testid="strategy-control-detail-summary-trace">last_transition_reason={detailPayload?.strategy?.last_transition_reason || "-"}</p>
              </div>

              <div className="rounded border border-black/20 bg-orange-100 p-3" data-testid="strategy-control-detail-trade-list-panel">
                <h4 className="text-sm font-semibold" data-testid="strategy-control-detail-trade-list-title">Trade List</h4>
                <p className="text-xs" data-testid="strategy-control-detail-trade-list-empty-reason">{detailPayload?.trade_list?.reason || "No data yet"}</p>
              </div>

              <div className="rounded border border-black/20 bg-orange-100 p-3" data-testid="strategy-control-detail-execution-log-panel">
                <h4 className="text-sm font-semibold" data-testid="strategy-control-detail-execution-log-title">Execution Log</h4>
                <p className="text-xs" data-testid="strategy-control-detail-execution-log-empty-reason">{detailPayload?.execution_history?.reason || "No data yet"}</p>
              </div>

              <div className="rounded border border-black/20 bg-orange-100 p-3" data-testid="strategy-control-detail-transition-history-panel">
                <h4 className="text-sm font-semibold" data-testid="strategy-control-detail-transition-history-title">Transition History</h4>
                {(detailPayload?.transition_history || []).length === 0 && <p className="text-xs" data-testid="strategy-control-detail-transition-history-empty">No data yet: geçiş geçmişi bulunmuyor.</p>}
                {(detailPayload?.transition_history || []).map((item, index) => (
                  <p key={`${item?.at}-${index}`} className="text-xs" data-testid={`strategy-control-detail-transition-history-item-${index}`}>
                    {item?.from || "NONE"} → {item?.to || "NONE"} · reason={item?.reason || "-"} · at={item?.at || "-"}
                  </p>
                ))}
              </div>

              <div className="rounded border border-black/20 bg-orange-100 p-3" data-testid="strategy-control-detail-audit-history-panel">
                <h4 className="text-sm font-semibold" data-testid="strategy-control-detail-audit-history-title">Audit History</h4>
                {(detailPayload?.audit_items || []).length === 0 && <p className="text-xs" data-testid="strategy-control-detail-audit-history-empty">No data yet: strategy için audit kaydı bulunmuyor.</p>}
                {(detailPayload?.audit_items || []).map((item, index) => (
                  <p key={item?.id || index} className="text-xs" data-testid={`strategy-control-detail-audit-history-item-${index}`}>
                    {item?.created_at || "-"} · {item?.action || "-"} · severity={item?.severity || "-"}
                  </p>
                ))}
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </section>
  );
};

const PlaceholderPanel = ({ testId, title, reason }) => {
  return (
    <div className="border border-black/25 bg-orange-100 p-4" data-testid={testId}>
      <h3 className="text-base font-semibold" data-testid={`${testId}-title`}>{title}</h3>
      <p className="mt-1 text-sm" data-testid={`${testId}-reason`}>No data yet: {reason}</p>
    </div>
  );
};

const StrategyTable = ({ rows, onOpenDetail, onRunAction, compact = false }) => {
  return (
    <div className="border border-black/25 bg-orange-100" data-testid={compact ? "strategy-control-table-compact" : "strategy-control-table-full"}>
      <div className="border-b border-black/20 px-4 py-3" data-testid={compact ? "strategy-control-table-compact-header" : "strategy-control-table-full-header"}>
        <h3 className="text-base font-semibold" data-testid={compact ? "strategy-control-table-compact-title" : "strategy-control-table-full-title"}>Strategy Lifecycle Control</h3>
      </div>
      <Table data-testid={compact ? "strategy-control-table-compact-table" : "strategy-control-table-full-table"}>
        <TableHeader>
          <TableRow>
            <TableHead data-testid="strategy-control-table-head-strategy">Strategy</TableHead>
            <TableHead data-testid="strategy-control-table-head-state">State</TableHead>
            <TableHead data-testid="strategy-control-table-head-shadow-live">Shadow/Live</TableHead>
            <TableHead data-testid="strategy-control-table-head-health">Health</TableHead>
            <TableHead data-testid="strategy-control-table-head-pnl">PnL</TableHead>
            <TableHead data-testid="strategy-control-table-head-drift">Drift</TableHead>
            <TableHead data-testid="strategy-control-table-head-actions">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, index) => (
            <TableRow key={row.strategy_id} data-testid={`strategy-control-table-row-${index}`}>
              <TableCell data-testid={`strategy-control-table-strategy-${index}`}>{row.strategy_id}</TableCell>
              <TableCell data-testid={`strategy-control-table-state-${index}`}>
                {row.control_state} / {row.throttle_level}
              </TableCell>
              <TableCell data-testid={`strategy-control-table-shadow-live-${index}`}>{row.shadow_live_state}</TableCell>
              <TableCell data-testid={`strategy-control-table-health-${index}`}>{row.health_score}</TableCell>
              <TableCell data-testid={`strategy-control-table-pnl-${index}`}>{row.pnl_rolling}</TableCell>
              <TableCell data-testid={`strategy-control-table-drift-${index}`}>{row.drift_count} ({row.drift_severity})</TableCell>
              <TableCell data-testid={`strategy-control-table-actions-${index}`}>
                <div className="flex flex-wrap gap-1">
                  <Button size="sm" variant="outline" onClick={() => onOpenDetail(row.strategy_id)} data-testid={`strategy-control-open-detail-button-${index}`}>
                    Detail
                  </Button>
                  {ACTIONS.map((action) => (
                    <Button
                      key={`${row.strategy_id}-${action.key}`}
                      size="sm"
                      variant="outline"
                      onClick={() => onRunAction(action.key, row)}
                      className={action.destructive ? "border-red-800 text-red-900" : ""}
                      data-testid={`strategy-control-action-${action.key}-button-${index}`}
                    >
                      {action.label}
                    </Button>
                  ))}
                </div>
              </TableCell>
            </TableRow>
          ))}

          {rows.length === 0 && (
            <TableRow data-testid="strategy-control-table-empty-row">
              <TableCell colSpan={7} className="text-center text-sm" data-testid="strategy-control-table-empty-text">
                No data yet: strategy kayıtları henüz oluşmadı veya geçici olarak alınamadı.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
};
