import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const AdminRuntimeQuarantinePage = () => {
  const [snapshot, setSnapshot] = useState({ items: [], summary: {}, queue_metrics: {} });
  const [loading, setLoading] = useState(true);

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

  const runAction = async (eventId, action) => {
    try {
      await apiClient.post(`/execution-safety/quarantine/${eventId}/${action}`);
      toast.success(`Quarantine ${action} tamamlandı`);
      await loadEvents();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Quarantine aksiyonu başarısız");
    }
  };

  return (
    <section className="space-y-4" data-testid="admin-runtime-quarantine-page">
      <header className="border border-red-700/50 bg-slate-900 p-4" data-testid="admin-runtime-quarantine-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-red-300" data-testid="admin-runtime-quarantine-title">Runtime Quarantine</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="admin-runtime-quarantine-description">
          Poison event’ler ve DLQ’ya düşen mesajlar burada listelenir.
        </p>
        <div className="mt-3 grid gap-2 text-xs md:grid-cols-2 xl:grid-cols-4" data-testid="admin-runtime-quarantine-queue-metrics-grid">
          <p data-testid="admin-runtime-quarantine-redis-available">redis_available: {snapshot?.queue_metrics?.redis_available ? "true" : "false"}</p>
          <p data-testid="admin-runtime-quarantine-runtime-events-queue">runtime_events_queue: {snapshot?.queue_metrics?.runtime_events_queue ?? 0}</p>
          <p data-testid="admin-runtime-quarantine-runtime-retry-queue">runtime_retry_queue: {snapshot?.queue_metrics?.runtime_retry_queue ?? 0}</p>
          <p data-testid="admin-runtime-quarantine-runtime-dead-letter-queue">runtime_dead_letter_queue: {snapshot?.queue_metrics?.runtime_dead_letter_queue ?? 0}</p>
        </div>
        <div className="mt-2 grid gap-2 text-xs md:grid-cols-2 xl:grid-cols-4" data-testid="admin-runtime-quarantine-summary-grid">
          {Object.entries(snapshot?.summary || {}).map(([key, value]) => (
            <p key={key} data-testid={`admin-runtime-quarantine-summary-${key}`}>{key}: {value}</p>
          ))}
          {Object.keys(snapshot?.summary || {}).length === 0 && (
            <p data-testid="admin-runtime-quarantine-summary-empty">summary: -</p>
          )}
        </div>
        <Button className="mt-3 bg-red-600 text-white hover:bg-red-700" onClick={loadEvents} data-testid="admin-runtime-quarantine-refresh">
          Refresh
        </Button>
      </header>

      {loading && <p className="text-sm text-slate-400" data-testid="admin-runtime-quarantine-loading">Yükleniyor...</p>}
      {!loading && (snapshot?.items || []).length === 0 && (
        <p className="text-sm text-slate-400" data-testid="admin-runtime-quarantine-empty">Quarantine kuyruğu boş.</p>
      )}

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
              <Button size="sm" className="bg-emerald-500 text-black hover:bg-emerald-600" onClick={() => runAction(rowId, "replay")} data-testid={`runtime-quarantine-replay-${rowId}`}>
                Replay
              </Button>
              <Button size="sm" variant="outline" className="border-slate-500 text-slate-200" onClick={() => runAction(rowId, "dismiss")} data-testid={`runtime-quarantine-dismiss-${rowId}`}>
                Dismiss
              </Button>
              <Button size="sm" variant="outline" className="border-red-500 text-red-300" onClick={() => runAction(rowId, "mark_failed")} data-testid={`runtime-quarantine-mark-failed-${rowId}`}>
                Mark Failed
              </Button>
            </div>
          </div>
        )})}
      </div>
    </section>
  );
};
