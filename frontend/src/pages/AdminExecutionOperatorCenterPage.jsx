import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { apiClient } from "@/lib/api";

export const AdminExecutionOperatorCenterPage = () => {
  const [windowRange, setWindowRange] = useState("7d");
  const [centerData, setCenterData] = useState(null);
  const [drilldownData, setDrilldownData] = useState(null);
  const [drilldownIntentId, setDrilldownIntentId] = useState("");
  const [selectedIntentIds, setSelectedIntentIds] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [highConfirmModal, setHighConfirmModal] = useState({ open: false, action: "", intentIds: [] });

  const topAnomalies = useMemo(() => centerData?.top_risky_intents || [], [centerData?.top_risky_intents]);

  const loadOperatorCenter = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data } = await apiClient.get(`/execution-safety/operator-center?window=${windowRange}&limit=10`);
      setCenterData(data || null);
      const available = new Set((data?.top_risky_intents || []).map((item) => item.intent_id).filter(Boolean));
      setSelectedIntentIds((prev) => prev.filter((intentId) => available.has(intentId)));
    } catch (requestError) {
      const message = requestError?.response?.data?.detail || "Operator center verisi alınamadı";
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [windowRange]);

  useEffect(() => {
    loadOperatorCenter();
  }, [loadOperatorCenter]);

  useEffect(() => {
    const intentFromQuery = new URLSearchParams(window.location.search).get("intent_id");
    if (intentFromQuery) {
      loadDrilldown(intentFromQuery);
    }
  }, [loadDrilldown]);

  const loadDrilldown = useCallback(async (intentId) => {
    if (!intentId) {
      toast.error("Drilldown için intent_id gerekli");
      return;
    }
    try {
      const { data } = await apiClient.get(`/execution-safety/anomalies/drilldown/${intentId}?limit=150`);
      setDrilldownIntentId(intentId);
      setDrilldownData(data || null);
      toast.success("Correlation drilldown yüklendi");
    } catch (requestError) {
      toast.error(requestError?.response?.data?.detail || "Drilldown yüklenemedi");
    }
  }, []);

  const selectAll = useMemo(() => {
    const visibleIds = topAnomalies.map((item) => item.intent_id).filter(Boolean);
    if (!visibleIds.length) return false;
    return visibleIds.every((intentId) => selectedIntentIds.includes(intentId));
  }, [topAnomalies, selectedIntentIds]);

  const resolveIntentSelection = useCallback((intentIds = []) => {
    const provided = Array.isArray(intentIds) ? intentIds.filter(Boolean) : [];
    if (provided.length) return Array.from(new Set(provided));
    return Array.from(new Set(selectedIntentIds.filter(Boolean)));
  }, [selectedIntentIds]);

  const executeQuickAction = useCallback(async (actionKey, directIntentIds = []) => {
    const endpointMap = {
      retry: "/execution-safety/recovery/bulk-retry",
      reconcile: "/execution-safety/recovery/bulk-reconcile",
      cancel: "/execution-safety/recovery/bulk-cancel",
      escalate: "/execution-safety/recovery/bulk-move-to-quarantine",
    };
    const endpoint = endpointMap[actionKey];
    if (!endpoint) {
      toast.error("Geçersiz aksiyon");
      return;
    }

    const intentIds = resolveIntentSelection(directIntentIds);
    if (!intentIds.length) {
      toast.error("Aksiyon için intent seçin");
      return;
    }

    const selectedRows = topAnomalies.filter((item) => intentIds.includes(item.intent_id));
    const hasHigh = selectedRows.some((item) => String(item.severity_level || item.severity || "").toUpperCase() === "HIGH");
    if (hasHigh && !highConfirmModal.open) {
      setHighConfirmModal({ open: true, action: actionKey, intentIds });
      return;
    }

    setActionLoading(true);
    try {
      await apiClient.post(endpoint, {
        selection_mode: "explicit_ids",
        intent_ids: intentIds,
        limit: Math.max(intentIds.length, 1),
        reason: `operator_center_${actionKey}`,
        requested_by: "admin-ui",
      });
      toast.success(`${actionKey.toUpperCase()} aksiyonu tamamlandı`);
      setHighConfirmModal({ open: false, action: "", intentIds: [] });
      setSelectedIntentIds([]);
      await loadOperatorCenter();
      if (drilldownIntentId) {
        await loadDrilldown(drilldownIntentId);
      }
    } catch (requestError) {
      toast.error(requestError?.response?.data?.detail || "Quick action başarısız");
    } finally {
      setActionLoading(false);
    }
  }, [drilldownIntentId, highConfirmModal.open, loadDrilldown, loadOperatorCenter, resolveIntentSelection, topAnomalies]);

  return (
    <section className="space-y-4" data-testid="execution-operator-center-page">
      <header className="rounded-lg border border-slate-700 bg-slate-900 p-4" data-testid="execution-operator-center-header">
        <div className="flex flex-wrap items-center justify-between gap-3" data-testid="execution-operator-center-header-row">
          <div data-testid="execution-operator-center-header-text">
            <h1 className="text-2xl font-semibold text-slate-100" data-testid="execution-operator-center-title">Execution Operator Center</h1>
            <p className="text-xs text-slate-300" data-testid="execution-operator-center-subtitle">Tek ekran: anomaly, severity, öneri, quick action, correlation drilldown.</p>
          </div>
          <div className="flex items-center gap-2" data-testid="execution-operator-center-header-controls">
            <select
              value={windowRange}
              onChange={(event) => setWindowRange(event.target.value)}
              className="rounded border border-slate-600 bg-slate-950 px-2 py-1 text-xs text-white"
              data-testid="execution-operator-center-window-select"
            >
              <option value="7d">7d</option>
              <option value="30d">30d</option>
            </select>
            <Button onClick={loadOperatorCenter} variant="outline" disabled={loading || actionLoading} data-testid="execution-operator-center-refresh-button">Yenile</Button>
          </div>
        </div>
      </header>

      {loading && !centerData && (
        <div className="grid gap-3 lg:grid-cols-3" data-testid="execution-operator-center-loading-skeleton-grid">
          <Skeleton className="h-24 bg-slate-800" data-testid="execution-operator-center-loading-skeleton-0" />
          <Skeleton className="h-24 bg-slate-800" data-testid="execution-operator-center-loading-skeleton-1" />
          <Skeleton className="h-24 bg-slate-800" data-testid="execution-operator-center-loading-skeleton-2" />
        </div>
      )}

      {!!error && (
        <div className="rounded border border-red-700/50 bg-red-950/20 p-3" data-testid="execution-operator-center-error-state">
          <p className="text-xs text-red-200" data-testid="execution-operator-center-error-message">{error}</p>
          <Button className="mt-2" variant="outline" onClick={loadOperatorCenter} data-testid="execution-operator-center-error-retry-button">Tekrar Dene</Button>
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-3" data-testid="execution-operator-center-main-grid">
        <article className="rounded-lg border border-rose-700/40 bg-slate-900 p-3 xl:col-span-2" data-testid="execution-operator-center-top-anomalies-card">
          <div className="flex flex-wrap items-center justify-between gap-2" data-testid="execution-operator-center-top-anomalies-header">
            <h2 className="text-sm font-semibold text-rose-100" data-testid="execution-operator-center-top-anomalies-title">Top 10 Riskli Intent</h2>
            <p className="text-xs text-slate-300" data-testid="execution-operator-center-top-anomalies-total">total_anomalies: {centerData?.total_anomalies ?? 0}</p>
          </div>

          <div className="mt-2 rounded border border-slate-700 bg-slate-950 p-2" data-testid="execution-operator-center-quick-actions-panel">
            <div className="flex flex-wrap items-center justify-between gap-2" data-testid="execution-operator-center-quick-actions-header">
              <label className="flex items-center gap-2 text-xs text-slate-300" data-testid="execution-operator-center-select-all-wrapper">
                <input
                  type="checkbox"
                  checked={selectAll}
                  onChange={(event) => {
                    if (!event.target.checked) {
                      setSelectedIntentIds([]);
                      return;
                    }
                    setSelectedIntentIds(topAnomalies.map((item) => item.intent_id).filter(Boolean));
                  }}
                  data-testid="execution-operator-center-select-all-checkbox"
                />
                Tümünü seç ({selectedIntentIds.length})
              </label>
              <p className="text-[11px] text-slate-400" data-testid="execution-operator-center-high-confirm-rule">HIGH için modal zorunlu</p>
            </div>
            <div className="mt-2 flex flex-wrap gap-2" data-testid="execution-operator-center-quick-actions-buttons">
              <Button size="sm" variant="outline" disabled={actionLoading} onClick={() => executeQuickAction("retry")} data-testid="execution-operator-center-quick-action-retry-button">Retry</Button>
              <Button size="sm" variant="outline" disabled={actionLoading} onClick={() => executeQuickAction("reconcile")} data-testid="execution-operator-center-quick-action-reconcile-button">Reconcile</Button>
              <Button size="sm" variant="outline" disabled={actionLoading} onClick={() => executeQuickAction("cancel")} data-testid="execution-operator-center-quick-action-cancel-button">Cancel</Button>
              <Button size="sm" variant="outline" disabled={actionLoading} onClick={() => executeQuickAction("escalate")} data-testid="execution-operator-center-quick-action-escalate-button">Escalate</Button>
            </div>
          </div>

          <div className="mt-3 max-h-[420px] space-y-2 overflow-y-auto" data-testid="execution-operator-center-top-anomalies-list">
            {topAnomalies.map((item, index) => (
              <div
                key={`${item.intent_id || "unknown"}-${index}`}
                className={`rounded border p-2 ${String(item.severity_level || item.severity || "").toUpperCase() === "HIGH" ? "border-rose-500/70 bg-rose-950/30" : "border-slate-700 bg-slate-950"}`}
                data-testid={`execution-operator-center-top-anomaly-item-${index}`}
              >
                <div className="flex flex-wrap items-start justify-between gap-2" data-testid={`execution-operator-center-top-anomaly-item-header-${index}`}>
                  <label className="flex items-center gap-2 text-xs text-slate-300" data-testid={`execution-operator-center-top-anomaly-item-select-wrapper-${index}`}>
                    <input
                      type="checkbox"
                      checked={!!item.intent_id && selectedIntentIds.includes(item.intent_id)}
                      disabled={!item.intent_id}
                      onChange={(event) => {
                        if (!item.intent_id) return;
                        setSelectedIntentIds((prev) => {
                          const next = new Set(prev);
                          if (event.target.checked) next.add(item.intent_id);
                          else next.delete(item.intent_id);
                          return Array.from(next);
                        });
                      }}
                      data-testid={`execution-operator-center-top-anomaly-item-checkbox-${index}`}
                    />
                    {item.type}
                  </label>
                  <Button size="sm" variant="outline" onClick={() => loadDrilldown(item.intent_id)} disabled={!item.intent_id} data-testid={`execution-operator-center-top-anomaly-item-drilldown-button-${index}`}>Drilldown</Button>
                </div>
                <p className="text-xs text-slate-300" data-testid={`execution-operator-center-top-anomaly-item-severity-${index}`}>severity: {item.severity_level || item.severity}</p>
                <p className="text-xs text-slate-300" data-testid={`execution-operator-center-top-anomaly-item-score-${index}`}>severity_score: {item.severity_score ?? item.risk_score}</p>
                <p className="text-xs text-slate-300" data-testid={`execution-operator-center-top-anomaly-item-priority-${index}`}>priority: {item.priority}</p>
                <p className="text-xs text-slate-300" data-testid={`execution-operator-center-top-anomaly-item-intent-${index}`}>intent_id: {item.intent_id || "-"}</p>
                <p className="text-xs text-amber-200" data-testid={`execution-operator-center-top-anomaly-item-reason-${index}`}>reason: {item.reason || "-"}</p>
                <div className="mt-1 space-y-1" data-testid={`execution-operator-center-top-anomaly-item-recommended-actions-${index}`}>
                  {(item.recommended_actions || []).map((rec, recIdx) => (
                    <p key={`${rec.action}-${recIdx}`} className="text-[11px] text-cyan-200" data-testid={`execution-operator-center-top-anomaly-item-recommended-action-${index}-${recIdx}`}>
                      {rec.action} ({rec.confidence}) - {rec.reason}
                    </p>
                  ))}
                </div>
              </div>
            ))}
            {topAnomalies.length === 0 && <p className="text-xs text-slate-400" data-testid="execution-operator-center-top-anomalies-empty">Anomaly bulunamadı.</p>}
          </div>
        </article>

        <aside className="space-y-4" data-testid="execution-operator-center-side-column">
          <article className="rounded-lg border border-slate-700 bg-slate-900 p-3" data-testid="execution-operator-center-blocker-breakdown-card">
            <h3 className="text-sm font-semibold text-slate-100" data-testid="execution-operator-center-blocker-breakdown-title">Blocker Breakdown</h3>
            {(centerData?.blocker_breakdown || []).slice(0, 8).map((item, index) => (
              <p key={`${item.code}-${index}`} className="mt-1 text-xs text-slate-300" data-testid={`execution-operator-center-blocker-breakdown-item-${index}`}>{item.code}: {item.count}</p>
            ))}
            {!(centerData?.blocker_breakdown || []).length && <p className="mt-1 text-xs text-slate-500" data-testid="execution-operator-center-blocker-breakdown-empty">Veri yok.</p>}
          </article>

          <article className="rounded-lg border border-slate-700 bg-slate-900 p-3" data-testid="execution-operator-center-recommendation-rollup-card">
            <h3 className="text-sm font-semibold text-slate-100" data-testid="execution-operator-center-recommendation-rollup-title">Recommended Actions Rollup</h3>
            {(centerData?.recommended_actions || []).map((item, index) => (
              <p key={`${item.action}-${index}`} className="mt-1 text-xs text-slate-300" data-testid={`execution-operator-center-recommendation-rollup-item-${index}`}>
                {item.action}: count={item.count} avg_confidence={item.avg_confidence}
              </p>
            ))}
            {!(centerData?.recommended_actions || []).length && <p className="mt-1 text-xs text-slate-500" data-testid="execution-operator-center-recommendation-rollup-empty">Öneri rollup yok.</p>}
          </article>

          <article className="rounded-lg border border-slate-700 bg-slate-900 p-3" data-testid="execution-operator-center-recent-failures-card">
            <h3 className="text-sm font-semibold text-slate-100" data-testid="execution-operator-center-recent-failures-title">Recent Failures</h3>
            {(centerData?.recent_failures || []).slice(0, 6).map((item, index) => (
              <p key={`${item.failure_id}-${index}`} className="mt-1 text-xs text-slate-300" data-testid={`execution-operator-center-recent-failure-item-${index}`}>
                {item.failure_class} / {item.entity_id} / retry={item.retry_count}
              </p>
            ))}
            {!(centerData?.recent_failures || []).length && <p className="mt-1 text-xs text-slate-500" data-testid="execution-operator-center-recent-failures-empty">Failure kaydı yok.</p>}
          </article>
        </aside>
      </div>

      <section className="rounded-lg border border-indigo-700/30 bg-slate-900 p-4" data-testid="execution-operator-center-drilldown-panel">
        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="execution-operator-center-drilldown-header">
          <h2 className="text-sm font-semibold text-indigo-100" data-testid="execution-operator-center-drilldown-title">Correlation-Aware Drilldown</h2>
          <p className="text-xs text-slate-300" data-testid="execution-operator-center-drilldown-active-intent">active_intent: {drilldownIntentId || "-"}</p>
        </div>
        {!drilldownData && <p className="mt-2 text-xs text-slate-400" data-testid="execution-operator-center-drilldown-empty">Anomaly satırından Drilldown butonuna tıklayarak zinciri açın.</p>}
        {drilldownData && (
          <div className="mt-2 grid gap-3 lg:grid-cols-2" data-testid="execution-operator-center-drilldown-content-grid">
            <article className="rounded border border-slate-700 bg-slate-950 p-2" data-testid="execution-operator-center-drilldown-links-card">
              <h3 className="text-xs font-semibold text-slate-100" data-testid="execution-operator-center-drilldown-links-title">Chain Links</h3>
              {Object.entries(drilldownData.chain_links || {}).map(([key, value], index) => (
                <a key={key} href={value} className="mt-1 block text-xs text-cyan-300 underline-offset-2 hover:underline" data-testid={`execution-operator-center-drilldown-link-${index}`}>{key}: {value}</a>
              ))}
            </article>
            <article className="rounded border border-slate-700 bg-slate-950 p-2" data-testid="execution-operator-center-drilldown-timeline-card">
              <h3 className="text-xs font-semibold text-slate-100" data-testid="execution-operator-center-drilldown-timeline-title">Timeline</h3>
              <div className="mt-1 max-h-56 space-y-1 overflow-y-auto" data-testid="execution-operator-center-drilldown-timeline-list">
                {(drilldownData.timeline || []).slice(0, 40).map((item, index) => (
                  <p key={`${item.at}-${index}`} className="text-xs text-slate-300" data-testid={`execution-operator-center-drilldown-timeline-item-${index}`}>
                    {item.at} / {item.type} / {item.title} / {item.status}
                  </p>
                ))}
              </div>
            </article>
          </div>
        )}
      </section>

      <Dialog
        open={highConfirmModal.open}
        onOpenChange={(open) => {
          if (!open) {
            setHighConfirmModal({ open: false, action: "", intentIds: [] });
          }
        }}
      >
        <DialogContent data-testid="execution-operator-center-high-confirm-modal">
          <DialogHeader>
            <DialogTitle data-testid="execution-operator-center-high-confirm-modal-title">HIGH Aksiyon Onayı</DialogTitle>
            <DialogDescription data-testid="execution-operator-center-high-confirm-modal-description">
              HIGH severity anomaly aksiyonu onaylanmadan uygulanmaz.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1 text-xs text-slate-300" data-testid="execution-operator-center-high-confirm-modal-body">
            <p data-testid="execution-operator-center-high-confirm-modal-action">action: {highConfirmModal.action}</p>
            <p data-testid="execution-operator-center-high-confirm-modal-intent-count">intent_count: {highConfirmModal.intentIds.length}</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setHighConfirmModal({ open: false, action: "", intentIds: [] })} data-testid="execution-operator-center-high-confirm-modal-cancel-button">Vazgeç</Button>
            <Button onClick={() => executeQuickAction(highConfirmModal.action, highConfirmModal.intentIds)} disabled={actionLoading} data-testid="execution-operator-center-high-confirm-modal-confirm-button">Onayla</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
};
