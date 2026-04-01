import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { apiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { toast } from "sonner";

const STATUS_OPTIONS = ["all", "pending", "retrying", "dead", "resolved", "quarantined"];

export const FailedEventsPage = () => {
  const [searchParams] = useSearchParams();
  const [rows, setRows] = useState([]);
  const [search, setSearch] = useState(searchParams.get("correlation_id") || "");
  const [statusFilter, setStatusFilter] = useState("all");
  const [selected, setSelected] = useState(null);
  const [selectedIds, setSelectedIds] = useState([]);

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      params.set("limit", "400");
      if (statusFilter !== "all") params.set("status_filter", statusFilter);
      if (search.trim()) params.set("search", search.trim());
      const { data } = await apiClient.get(`/admin-phase3/failed-events?${params.toString()}`);
      setRows(data || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Failed events yüklenemedi");
    }
  }, [search, statusFilter]);

  useEffect(() => {
    load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [load]);

  useEffect(() => {
    const correlationId = searchParams.get("correlation_id") || "";
    if (correlationId && correlationId !== search) {
      setSearch(correlationId);
    }
  }, [search, searchParams]);

  const handleAction = async (id, action) => {
    try {
      await apiClient.post(`/admin-phase3/failed-events/${id}/${action}`);
      toast.success(`Event ${action} tamamlandı`);
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || `${action} başarısız`);
    }
  };

  const bulkAction = async (action) => {
    if (!selectedIds.length) {
      toast.error("Önce kayıt seçin");
      return;
    }
    try {
      await apiClient.post(`/admin-phase3/failed-events/bulk-${action}`, selectedIds);
      toast.success(`Bulk ${action} tamamlandı (${selectedIds.length})`);
      setSelectedIds([]);
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || `Bulk ${action} başarısız`);
    }
  };

  const deadLetterCount = useMemo(() => rows.filter((row) => ["dead", "quarantined"].includes(row.status)).length, [rows]);

  return (
    <section className="space-y-4" data-testid="execution-control-failures-page">
      <div className="flex flex-wrap items-end gap-3" data-testid="execution-control-failures-filters">
        <Input placeholder="search event/entity/correlation" value={search} onChange={(e) => setSearch(e.target.value)} data-testid="execution-control-failures-search-input" />
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger data-testid="execution-control-failures-status-select"><SelectValue /></SelectTrigger>
          <SelectContent>{STATUS_OPTIONS.map((status) => <SelectItem key={status} value={status}>{status}</SelectItem>)}</SelectContent>
        </Select>
        <Button onClick={load} data-testid="execution-control-failures-refresh-button">Yenile</Button>
        <Button variant="outline" onClick={() => bulkAction("retry")} data-testid="execution-control-failures-bulk-retry-button">Bulk Retry</Button>
        <Button variant="outline" onClick={() => bulkAction("resolve")} data-testid="execution-control-failures-bulk-resolve-button">Bulk Resolve</Button>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3" data-testid="execution-control-failures-summary-grid">
        <article className="border border-slate-800 bg-slate-900 p-2"><p className="text-xs text-slate-400">Toplam</p><p className="text-lg font-semibold">{rows.length}</p></article>
        <article className="border border-rose-700 bg-rose-950/20 p-2"><p className="text-xs text-rose-300">Dead-letter</p><p className="text-lg font-semibold">{deadLetterCount}</p></article>
        <article className="border border-amber-700 bg-amber-950/20 p-2"><p className="text-xs text-amber-300">Selected</p><p className="text-lg font-semibold">{selectedIds.length}</p></article>
      </div>

      <div className="overflow-x-auto border border-slate-800 bg-slate-900" data-testid="execution-control-failures-table-wrapper">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>pick</TableHead>
              <TableHead>entity</TableHead>
              <TableHead>status</TableHead>
              <TableHead>failure_class</TableHead>
              <TableHead>retry</TableHead>
              <TableHead>actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => {
              const checked = selectedIds.includes(row.id);
              return (
                <TableRow key={row.id} data-testid={`execution-control-failure-row-${row.id}`}>
                  <TableCell>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(e) => setSelectedIds((prev) => (e.target.checked ? [...prev, row.id] : prev.filter((id) => id !== row.id)))}
                      data-testid={`execution-control-failure-checkbox-${row.id}`}
                    />
                  </TableCell>
                  <TableCell onClick={() => setSelected(row)} className="cursor-pointer">{row.entity_type}:{row.entity_id}</TableCell>
                  <TableCell>{row.status}</TableCell>
                  <TableCell>{row.failure_class}</TableCell>
                  <TableCell>{row.retry_count}/{row.max_retry}</TableCell>
                  <TableCell className="space-x-2">
                    <Button size="sm" variant="outline" onClick={() => handleAction(row.id, "retry")} data-testid={`execution-control-failure-retry-${row.id}`}>Retry</Button>
                    <Button size="sm" variant="outline" onClick={() => handleAction(row.id, "reprocess")} data-testid={`execution-control-failure-reprocess-${row.id}`}>Reprocess</Button>
                    <Button size="sm" variant="outline" onClick={() => handleAction(row.id, "resolve")} data-testid={`execution-control-failure-resolve-${row.id}`}>Resolve</Button>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      {selected && (
        <div className="rounded border border-slate-700 bg-slate-950 p-3 text-xs" data-testid="execution-control-failure-detail-panel">
          <p>event_type={selected.event_type} · correlation={selected.correlation_id || "-"}</p>
          <p>error={selected.error_message}</p>
          <p>dead_letter_reason={selected.dead_letter_reason || "-"}</p>
          <pre className="mt-2 overflow-x-auto rounded bg-black/40 p-2">{JSON.stringify(selected.payload || {}, null, 2)}</pre>
          <pre className="mt-2 overflow-x-auto rounded bg-black/40 p-2">{JSON.stringify(selected.error_details || {}, null, 2)}</pre>
        </div>
      )}
    </section>
  );
};
