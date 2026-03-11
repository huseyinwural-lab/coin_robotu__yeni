import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

export const FailedEventsPage = () => {
  const [events, setEvents] = useState([]);

  const loadEvents = async () => {
    try {
      const { data } = await apiClient.get("/admin-phase3/failed-events");
      setEvents(data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Failed event listesi alınamadı");
    }
  };

  useEffect(() => {
    loadEvents();
  }, []);

  const callAction = async (eventId, action) => {
    try {
      await apiClient.post(`/admin-phase3/failed-events/${eventId}/${action}`);
      toast.success(`Event ${action} işlendi`);
      loadEvents();
    } catch (error) {
      toast.error(error?.response?.data?.detail || `Event ${action} başarısız`);
    }
  };

  const seedEvent = async () => {
    try {
      await apiClient.post("/admin-phase3/failed-events/seed");
      toast.success("Test failed event oluşturuldu");
      loadEvents();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Seed event oluşturulamadı");
    }
  };

  return (
    <section className="space-y-4" data-testid="failed-events-page">
      <header className="border border-red-600/40 bg-slate-900 p-4" data-testid="failed-events-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-red-300" data-testid="failed-events-title">Failed Event Queue</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="failed-events-description">Risk/execution zincirinde düşen eventler bu panelden yönetilir.</p>
        <Button className="mt-3 bg-red-700 text-white hover:bg-red-800" onClick={seedEvent} data-testid="failed-events-seed-button">
          Test Event Oluştur
        </Button>
      </header>

      <div className="border border-slate-800 bg-slate-900" data-testid="failed-events-table-wrapper">
        {events.length === 0 && (
          <p className="p-3 text-sm text-slate-500" data-testid="failed-events-empty-state">
            Event yok. "Test Event Oluştur" ile retry/resolve akışını test edebilirsin.
          </p>
        )}
        <Table data-testid="failed-events-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="failed-head-event-type">Event</TableHead>
              <TableHead data-testid="failed-head-entity">Entity</TableHead>
              <TableHead data-testid="failed-head-status">Status</TableHead>
              <TableHead data-testid="failed-head-retry">Retry</TableHead>
              <TableHead data-testid="failed-head-error">Error</TableHead>
              <TableHead data-testid="failed-head-action">Aksiyon</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {events.map((eventItem) => (
              <TableRow key={eventItem.id} data-testid={`failed-row-${eventItem.id}`}>
                <TableCell data-testid={`failed-event-${eventItem.id}`}>{eventItem.event_type}</TableCell>
                <TableCell data-testid={`failed-entity-${eventItem.id}`}>{eventItem.entity_type}:{eventItem.entity_id}</TableCell>
                <TableCell data-testid={`failed-status-${eventItem.id}`}>{eventItem.status}</TableCell>
                <TableCell className="font-mono" data-testid={`failed-retry-${eventItem.id}`}>{eventItem.retry_count}/{eventItem.max_retry}</TableCell>
                <TableCell className="max-w-sm truncate text-xs" data-testid={`failed-error-${eventItem.id}`}>{eventItem.error_message}</TableCell>
                <TableCell>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" className="border-orange-400 bg-transparent text-orange-300" onClick={() => callAction(eventItem.id, "retry")} data-testid={`failed-retry-btn-${eventItem.id}`}>
                      Retry
                    </Button>
                    <Button size="sm" variant="outline" className="border-green-500 bg-transparent text-green-300" onClick={() => callAction(eventItem.id, "resolve")} data-testid={`failed-resolve-btn-${eventItem.id}`}>
                      Resolve
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </section>
  );
};
