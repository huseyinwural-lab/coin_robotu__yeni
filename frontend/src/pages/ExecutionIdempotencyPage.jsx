import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { toast } from "sonner";

const ACTIONS = ["mark_safe_duplicate", "release_blocked_retry", "suppress_replay", "force_reprocess_new_key"];

export const ExecutionIdempotencyPage = () => {
  const [rows, setRows] = useState([]);
  const [statusFilter, setStatusFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState(null);

  const load = async () => {
    try {
      const params = new URLSearchParams();
      if (statusFilter !== "all") params.set("status_filter", statusFilter);
      if (search.trim()) params.set("search", search.trim());
      params.set("limit", "500");
      const { data } = await apiClient.get(`/admin-phase3/idempotency-collisions?${params.toString()}`);
      setRows(data || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Collision listesi yüklenemedi");
    }
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [statusFilter]);

  const resolveCollision = async (collision, action) => {
    const reason = window.prompt("Resolve reason", `${action}_${collision.collision_id}`);
    if (reason === null) return;
    try {
      await apiClient.post(`/admin-phase3/idempotency-collisions/${collision.collision_id}/resolve`, {
        action,
        reason_note: reason,
        correlation_id: collision.correlation_id || `manual_${collision.collision_id}`,
      });
      toast.success("Collision resolve edildi");
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Resolve başarısız");
    }
  };

  return (
    <section className="space-y-4" data-testid="execution-control-idempotency-page">
      <div className="flex flex-wrap gap-2" data-testid="execution-control-idempotency-filters">
        <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="intent/key/correlation" data-testid="execution-control-idempotency-search-input" />
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger data-testid="execution-control-idempotency-status-select"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">all</SelectItem>
            <SelectItem value="open">open</SelectItem>
            <SelectItem value="resolved">resolved</SelectItem>
          </SelectContent>
        </Select>
        <Button onClick={load} data-testid="execution-control-idempotency-refresh-button">Yenile</Button>
      </div>

      <div className="overflow-x-auto border border-slate-800 bg-slate-900" data-testid="execution-control-idempotency-table-wrapper">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>idempotency_key</TableHead>
              <TableHead>status</TableHead>
              <TableHead>correlation</TableHead>
              <TableHead>actor</TableHead>
              <TableHead>actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.collision_id} data-testid={`execution-control-idempotency-row-${row.collision_id}`}>
                <TableCell onClick={() => setSelected(row)} className="cursor-pointer">{row.idempotency_key.slice(0, 42)}...</TableCell>
                <TableCell>{row.status}</TableCell>
                <TableCell>{row.correlation_id || "-"}</TableCell>
                <TableCell>{row.actor}</TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1">
                    {ACTIONS.map((action) => (
                      <Button key={action} size="sm" variant="outline" onClick={() => resolveCollision(row, action)} data-testid={`execution-control-idempotency-action-${action}-${row.collision_id}`}>
                        {action}
                      </Button>
                    ))}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {selected && (
        <div className="rounded border border-slate-700 bg-slate-950 p-3 text-xs" data-testid="execution-control-idempotency-detail-panel">
          <p>collision_id={selected.collision_id}</p>
          <p>intent_id={selected.intent_id || "-"} · correlation={selected.correlation_id || "-"}</p>
          <pre className="mt-2 overflow-x-auto rounded bg-black/40 p-2">{JSON.stringify(selected.original_request || {}, null, 2)}</pre>
          <pre className="mt-2 overflow-x-auto rounded bg-black/40 p-2">{JSON.stringify(selected.duplicate_request || {}, null, 2)}</pre>
        </div>
      )}
    </section>
  );
};
