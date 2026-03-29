import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiClient } from "@/lib/api";

export const AdminRuntimeQuarantinePage = () => {
  const [snapshot, setSnapshot] = useState({ items: [], summary: {}, queue_metrics: {} });
  const [loading, setLoading] = useState(true);

  const [detailOpen, setDetailOpen] = useState(false);
  const [detailData, setDetailData] = useState(null);
  const [detailAction, setDetailAction] = useState("replay");
  const [detailNote, setDetailNote] = useState("");

  const [batchAction, setBatchAction] = useState("bulk_retry");
  const [batchStates, setBatchStates] = useState("FAILED,PARTIALLY_FILLED");
  const [batchReasonCodes, setBatchReasonCodes] = useState("stuck_ack");
  const [batchAgeMinutes, setBatchAgeMinutes] = useState("10");
  const [batchLimit, setBatchLimit] = useState("100");
  const [batchReason, setBatchReason] = useState("manual recovery");

  const loadEvents = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/execution-safety/quarantine?limit=250");
      setSnapshot({
        items: data?.items || [],
        summary: data?.summary || {},
        queue_metrics: data?.queue_metrics || {},
      });
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Quarantine listesi alınamadı");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadEvents();
  }, [loadEvents]);

  const runAction = async (eventId, action, note = "") => {
    if (!eventId) {
      return;
    }
    try {
      await apiClient.post(`/execution-safety/quarantine/${eventId}/${action}`, { note });
      toast.success(`Quarantine ${action} tamamlandı`);
      await loadEvents();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Quarantine aksiyonu başarısız");
    }
  };

  const inspectItem = async (quarantineId) => {
    try {
      const { data } = await apiClient.get(`/execution-safety/quarantine/${quarantineId}`);
      setDetailData(data || null);
      setDetailAction("replay");
      setDetailNote("");
      setDetailOpen(true);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Quarantine detail alınamadı");
    }
  };

  const detailJsonPayload = useMemo(() => JSON.stringify(detailData?.payload_snapshot || {}, null, 2), [detailData?.payload_snapshot]);
  const detailJsonError = useMemo(() => JSON.stringify(detailData?.error_snapshot || {}, null, 2), [detailData?.error_snapshot]);

  const runBatchAction = async () => {
    const endpointMap = {
      bulk_retry: "/execution-safety/recovery/bulk-retry",
      bulk_cancel: "/execution-safety/recovery/bulk-cancel",
      bulk_reconcile: "/execution-safety/recovery/bulk-reconcile",
      bulk_force_reconcile: "/execution-safety/recovery/bulk-force-reconcile",
      bulk_move_to_quarantine: "/execution-safety/recovery/bulk-move-to-quarantine",
      bulk_release_from_quarantine: "/execution-safety/recovery/bulk-release-from-quarantine",
    };
    const endpoint = endpointMap[batchAction];
    if (!endpoint) {
      toast.error("Geçersiz batch action");
      return;
    }
    const parseCsv = (value) =>
      String(value || "")
        .split(",")
        .map((part) => part.trim())
        .filter(Boolean);
    const payload = {
      action: batchAction,
      selection_mode: "by_filter",
      filters: {
        state: parseCsv(batchStates),
        reason_code: parseCsv(batchReasonCodes),
        age_minutes: Number(batchAgeMinutes || 0),
      },
      limit: Number(batchLimit || 100),
      requested_by: "admin-ui",
      reason: batchReason,
    };
    try {
      const { data } = await apiClient.post(endpoint, payload);
      toast.success(`Batch ${batchAction} tamamlandı (success: ${data?.success_count || 0}, failed: ${data?.failed_count || 0})`);
      await loadEvents();
    } catch (error) {
      toast.error(error?.response?.data?.detail || `Batch ${batchAction} başarısız`);
    }
  };

  return (
    <section className="space-y-4" data-testid="admin-runtime-quarantine-page">
      <header className="border border-red-700/50 bg-slate-900 p-4" data-testid="admin-runtime-quarantine-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-red-300" data-testid="admin-runtime-quarantine-title">Runtime Quarantine</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="admin-runtime-quarantine-description">
          Poison event’ler ve DLQ’ya düşen mesajlar burada listelenir.
        </p>

        <div className="mt-3 rounded border border-slate-700 bg-slate-950 p-3" data-testid="admin-runtime-quarantine-batch-panel">
          <p className="text-xs font-semibold text-slate-100" data-testid="admin-runtime-quarantine-batch-panel-title">Batch Action Panel</p>
          <div className="mt-2 grid gap-2 md:grid-cols-2 xl:grid-cols-3" data-testid="admin-runtime-quarantine-batch-form-grid">
            <Input value={batchAction} onChange={(event) => setBatchAction(event.target.value)} data-testid="admin-runtime-quarantine-batch-action-input" />
            <Input value={batchStates} onChange={(event) => setBatchStates(event.target.value)} data-testid="admin-runtime-quarantine-batch-state-filter-input" />
            <Input value={batchReasonCodes} onChange={(event) => setBatchReasonCodes(event.target.value)} data-testid="admin-runtime-quarantine-batch-reason-filter-input" />
            <Input value={batchAgeMinutes} onChange={(event) => setBatchAgeMinutes(event.target.value)} data-testid="admin-runtime-quarantine-batch-age-input" />
            <Input value={batchLimit} onChange={(event) => setBatchLimit(event.target.value)} data-testid="admin-runtime-quarantine-batch-limit-input" />
            <Input value={batchReason} onChange={(event) => setBatchReason(event.target.value)} data-testid="admin-runtime-quarantine-batch-reason-input" />
          </div>
          <Button className="mt-2 bg-cyan-500 text-black hover:bg-cyan-600" onClick={runBatchAction} data-testid="admin-runtime-quarantine-batch-run-button">
            Run Batch
          </Button>
        </div>

        <div className="mt-3 grid gap-2 text-xs md:grid-cols-2 xl:grid-cols-4" data-testid="admin-runtime-quarantine-queue-metrics-grid">
          <p data-testid="admin-runtime-quarantine-redis-available">redis_available: {snapshot?.queue_metrics?.redis_available ? "true" : "false"}</p>
          <p data-testid="admin-runtime-quarantine-runtime-events-queue">runtime_events_queue: {snapshot?.queue_metrics?.runtime_events_queue ?? 0}</p>
          <p data-testid="admin-runtime-quarantine-runtime-retry-queue">runtime_retry_queue: {snapshot?.queue_metrics?.runtime_retry_queue ?? 0}</p>
          <p data-testid="admin-runtime-quarantine-runtime-dead-letter-queue">runtime_dead_letter_queue: {snapshot?.queue_metrics?.runtime_dead_letter_queue ?? 0}</p>
        </div>
        <div className="mt-2 grid gap-2 text-xs md:grid-cols-2 xl:grid-cols-4" data-testid="admin-runtime-quarantine-summary-grid">
          {Object.entries(snapshot?.summary?.by_status || {}).map(([key, value]) => (
            <p key={`status-${key}`} data-testid={`admin-runtime-quarantine-summary-status-${key}`}>{key}: {value}</p>
          ))}
          {Object.entries(snapshot?.summary?.by_failure_stage || {}).map(([key, value]) => (
            <p key={`stage-${key}`} data-testid={`admin-runtime-quarantine-summary-stage-${key}`}>{key}: {value}</p>
          ))}
          {Object.keys(snapshot?.summary || {}).length === 0 && <p data-testid="admin-runtime-quarantine-summary-empty">summary: -</p>}
        </div>
        <Button className="mt-3 bg-red-600 text-white hover:bg-red-700" onClick={loadEvents} data-testid="admin-runtime-quarantine-refresh">
          Refresh
        </Button>
      </header>

      {loading && <p className="text-sm text-slate-400" data-testid="admin-runtime-quarantine-loading">Yükleniyor...</p>}
      {!loading && (snapshot?.items || []).length === 0 && <p className="text-sm text-slate-400" data-testid="admin-runtime-quarantine-empty">Quarantine kuyruğu boş.</p>}

      <div className="space-y-3" data-testid="admin-runtime-quarantine-list">
        {(snapshot?.items || []).map((eventItem) => {
          const rowId = eventItem.quarantine_id || eventItem.id;
          return (
            <div key={rowId} className="border border-slate-700 bg-slate-900 p-3" data-testid={`runtime-quarantine-row-${rowId}`}>
              <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3" data-testid={`runtime-quarantine-grid-${rowId}`}>
                <p className="text-sm" data-testid={`runtime-quarantine-entity-${rowId}`}>entity_type: {eventItem.entity_type}</p>
                <p className="text-sm" data-testid={`runtime-quarantine-event-${rowId}`}>event: {eventItem.event_type}</p>
                <p className="text-sm" data-testid={`runtime-quarantine-status-${rowId}`}>status: {eventItem.status}</p>
                <p className="text-sm" data-testid={`runtime-quarantine-reason-${rowId}`}>reason: {eventItem.reason || eventItem.reason_code || "-"}</p>
                <p className="text-xs text-slate-400" data-testid={`runtime-quarantine-retry-${rowId}`}>retry: {eventItem.retry_count}/{eventItem.max_retry}</p>
                <p className="text-xs text-slate-400" data-testid={`runtime-quarantine-error-${rowId}`}>error: {eventItem?.error_snapshot?.error_message || eventItem.error_message || "-"}</p>
              </div>
              <div className="mt-3 flex flex-wrap gap-2" data-testid={`runtime-quarantine-actions-${rowId}`}>
                <Button size="sm" className="bg-emerald-500 text-black hover:bg-emerald-600" onClick={() => runAction(rowId, "replay")} data-testid={`runtime-quarantine-replay-${rowId}`}>Replay</Button>
                <Button size="sm" variant="outline" className="border-slate-500 text-slate-200" onClick={() => runAction(rowId, "mark_resolved")} data-testid={`runtime-quarantine-resolve-${rowId}`}>Mark Resolved</Button>
                <Button size="sm" variant="outline" className="border-red-500 text-red-300" onClick={() => runAction(rowId, "mark_failed")} data-testid={`runtime-quarantine-mark-failed-${rowId}`}>Mark Failed</Button>
                <Button size="sm" variant="outline" className="border-amber-500 text-amber-300" onClick={() => inspectItem(rowId)} data-testid={`runtime-quarantine-inspect-${rowId}`}>Inspect</Button>
              </div>
            </div>
          );
        })}
      </div>

      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-w-4xl border border-slate-700 bg-slate-950 text-slate-100" data-testid="admin-runtime-quarantine-detail-dialog">
          <DialogHeader>
            <DialogTitle data-testid="admin-runtime-quarantine-detail-title">Quarantine Detail</DialogTitle>
            <DialogDescription data-testid="admin-runtime-quarantine-detail-description">Payload inspect, timeline, correlation chain ve aksiyon paneli</DialogDescription>
          </DialogHeader>

          <div className="grid gap-3 md:grid-cols-2" data-testid="admin-runtime-quarantine-detail-summary-grid">
            <p data-testid="admin-runtime-quarantine-detail-id">quarantine_id: {detailData?.quarantine_id || "-"}</p>
            <p data-testid="admin-runtime-quarantine-detail-intent">intent_id: {detailData?.intent_id || "-"}</p>
            <p data-testid="admin-runtime-quarantine-detail-correlation">correlation_id: {detailData?.correlation_id || "-"}</p>
            <p data-testid="admin-runtime-quarantine-detail-status">status: {detailData?.status || "-"}</p>
            <p data-testid="admin-runtime-quarantine-detail-failure-stage">failure_stage: {detailData?.failure_stage || "-"}</p>
            <p data-testid="admin-runtime-quarantine-detail-retry">retry: {detailData?.retry_count}/{detailData?.max_retry}</p>
          </div>

          <div className="grid gap-3 xl:grid-cols-2" data-testid="admin-runtime-quarantine-detail-json-grid">
            <div data-testid="admin-runtime-quarantine-detail-payload-panel">
              <p className="text-xs font-semibold text-slate-200">payload_snapshot</p>
              <Textarea value={detailJsonPayload} readOnly className="mt-1 h-40 text-xs" data-testid="admin-runtime-quarantine-detail-payload-json" />
            </div>
            <div data-testid="admin-runtime-quarantine-detail-error-panel">
              <p className="text-xs font-semibold text-slate-200">error_snapshot</p>
              <Textarea value={detailJsonError} readOnly className="mt-1 h-40 text-xs" data-testid="admin-runtime-quarantine-detail-error-json" />
            </div>
          </div>

          <div className="grid gap-3 xl:grid-cols-2" data-testid="admin-runtime-quarantine-detail-chain-grid">
            <div data-testid="admin-runtime-quarantine-detail-correlation-chain-panel">
              <p className="text-xs font-semibold text-slate-200">correlation_chain_link</p>
              <p className="text-xs text-slate-400" data-testid="admin-runtime-quarantine-detail-chain-timeline">timeline: {detailData?.correlation_chain_link?.intent_timeline || "-"}</p>
              <p className="text-xs text-slate-400" data-testid="admin-runtime-quarantine-detail-chain-reconcile">reconcile: {detailData?.correlation_chain_link?.intent_reconcile || "-"}</p>
              <p className="text-xs text-slate-400" data-testid="admin-runtime-quarantine-detail-chain-artifact">artifact: {detailData?.correlation_chain_link?.intent_artifact || "-"}</p>
            </div>
            <div data-testid="admin-runtime-quarantine-detail-resolution-history-panel">
              <p className="text-xs font-semibold text-slate-200">resolution_history</p>
              {(detailData?.resolution_history || []).slice(-5).map((entry, idx) => (
                <p key={`${entry?.created_at || idx}-${idx}`} className="text-xs text-slate-400" data-testid={`admin-runtime-quarantine-detail-resolution-history-item-${idx}`}>
                  {entry?.created_at || "-"} | {entry?.action || "-"} | {entry?.before_state || "-"} → {entry?.after_state || "-"}
                </p>
              ))}
              {(detailData?.resolution_history || []).length === 0 && <p className="text-xs text-slate-500" data-testid="admin-runtime-quarantine-detail-resolution-history-empty">history yok</p>}
            </div>
          </div>

          <div data-testid="admin-runtime-quarantine-detail-failure-timeline-panel">
            <p className="text-xs font-semibold text-slate-200">failure_timeline</p>
            {(detailData?.failure_timeline || []).slice(-8).map((entry, idx) => (
              <p key={`${entry?.at || idx}-${idx}`} className="text-xs text-slate-400" data-testid={`admin-runtime-quarantine-detail-failure-timeline-item-${idx}`}>
                {entry?.at || "-"} | {entry?.type || "-"} | {entry?.status || "-"} | {entry?.reason || "-"}
              </p>
            ))}
          </div>

          <div className="rounded border border-slate-700 bg-slate-900 p-3" data-testid="admin-runtime-quarantine-detail-action-panel">
            <p className="text-xs font-semibold text-slate-100">Action Panel</p>
            <div className="mt-2 grid gap-2 md:grid-cols-2" data-testid="admin-runtime-quarantine-detail-action-form-grid">
              <Input value={detailAction} onChange={(event) => setDetailAction(event.target.value)} data-testid="admin-runtime-quarantine-detail-action-input" />
              <Input value={detailNote} onChange={(event) => setDetailNote(event.target.value)} data-testid="admin-runtime-quarantine-detail-note-input" />
            </div>
            <div className="mt-2 flex flex-wrap gap-2" data-testid="admin-runtime-quarantine-detail-action-buttons">
              <Button size="sm" className="bg-emerald-500 text-black hover:bg-emerald-600" onClick={async () => { await runAction(detailData?.quarantine_id, detailAction, detailNote); await inspectItem(detailData?.quarantine_id); }} data-testid="admin-runtime-quarantine-detail-action-apply-button">Apply Action</Button>
              <Button size="sm" variant="outline" onClick={async () => { await runAction(detailData?.quarantine_id, "attach_note", detailNote); await inspectItem(detailData?.quarantine_id); }} data-testid="admin-runtime-quarantine-detail-action-note-button">Attach Note</Button>
              <Button size="sm" variant="outline" onClick={async () => { await runAction(detailData?.quarantine_id, "escalate", detailNote); await inspectItem(detailData?.quarantine_id); }} data-testid="admin-runtime-quarantine-detail-action-escalate-button">Escalate</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </section>
  );
};
