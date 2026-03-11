import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const AdminRuntimeQuarantinePage = () => {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadEvents = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/strategy-domain/admin/runtime/quarantine");
      setEvents(data || []);
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
      await apiClient.post(`/strategy-domain/admin/runtime/quarantine/${eventId}/${action}`);
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
        <Button className="mt-3 bg-red-600 text-white hover:bg-red-700" onClick={loadEvents} data-testid="admin-runtime-quarantine-refresh">
          Refresh
        </Button>
      </header>

      {loading && <p className="text-sm text-slate-400" data-testid="admin-runtime-quarantine-loading">Yükleniyor...</p>}
      {!loading && events.length === 0 && (
        <p className="text-sm text-slate-400" data-testid="admin-runtime-quarantine-empty">Quarantine kuyruğu boş.</p>
      )}

      <div className="space-y-3" data-testid="admin-runtime-quarantine-list">
        {events.map((eventItem) => (
          <div key={eventItem.id} className="border border-slate-700 bg-slate-900 p-3" data-testid={`runtime-quarantine-row-${eventItem.id}`}>
            <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3" data-testid={`runtime-quarantine-grid-${eventItem.id}`}>
              <p className="text-sm" data-testid={`runtime-quarantine-event-${eventItem.id}`}>event: {eventItem.event_type}</p>
              <p className="text-sm" data-testid={`runtime-quarantine-status-${eventItem.id}`}>status: {eventItem.status}</p>
              <p className="text-sm" data-testid={`runtime-quarantine-reason-${eventItem.id}`}>reason: {eventItem.reason_code || "-"}</p>
              <p className="text-xs text-slate-400" data-testid={`runtime-quarantine-retry-${eventItem.id}`}>retry: {eventItem.retry_count}/{eventItem.max_retry}</p>
              <p className="text-xs text-slate-400" data-testid={`runtime-quarantine-error-${eventItem.id}`}>error: {eventItem.error_message}</p>
            </div>
            <div className="mt-3 flex flex-wrap gap-2" data-testid={`runtime-quarantine-actions-${eventItem.id}`}>
              <Button size="sm" className="bg-emerald-500 text-black hover:bg-emerald-600" onClick={() => runAction(eventItem.event_id, "replay")} data-testid={`runtime-quarantine-replay-${eventItem.id}`}>
                Replay
              </Button>
              <Button size="sm" variant="outline" className="border-slate-500 text-slate-200" onClick={() => runAction(eventItem.event_id, "dismiss")} data-testid={`runtime-quarantine-dismiss-${eventItem.id}`}>
                Dismiss
              </Button>
              <Button size="sm" variant="outline" className="border-red-500 text-red-300" onClick={() => runAction(eventItem.event_id, "mark_failed")} data-testid={`runtime-quarantine-mark-failed-${eventItem.id}`}>
                Mark Failed
              </Button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
};
