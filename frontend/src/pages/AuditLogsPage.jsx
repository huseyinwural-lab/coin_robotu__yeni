import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

export const AuditLogsPage = () => {
  const [logs, setLogs] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isPruning, setIsPruning] = useState(false);
  const [filters, setFilters] = useState({
    q: "",
    action: "",
    severity: "all",
    request_id: "",
    session_id: "",
  });

  const fetchLogs = useCallback(async () => {
    setIsLoading(true);
    try {
      const { data } = await apiClient.get("/audit-logs/timeline", {
        params: {
          limit: 300,
          q: filters.q || undefined,
          action: filters.action || undefined,
          severity: filters.severity !== "all" ? filters.severity : undefined,
          request_id: filters.request_id || undefined,
          session_id: filters.session_id || undefined,
        },
      });
      setLogs(data?.items || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Audit loglar yüklenemedi");
    } finally {
      setIsLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  const runRetentionPrune = async () => {
    setIsPruning(true);
    try {
      const { data } = await apiClient.post("/audit-logs/admin/retention/prune", null, { params: { days: 90 } });
      toast.success(`90 gün retention prune tamamlandı. silinen=${data?.deleted_count ?? 0}`);
      await fetchLogs();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Retention prune başarısız");
    } finally {
      setIsPruning(false);
    }
  };

  return (
    <section className="space-y-4" data-testid="audit-logs-page">
      <header className="border border-blue-900 bg-slate-900 p-4" data-testid="audit-logs-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-blue-300" data-testid="audit-logs-title">System Timeline</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="audit-logs-description">Request ID, Session ID ve domain event akışları tek tabloda.</p>
      </header>

      <div className="grid gap-2 border border-slate-800 bg-slate-900 p-3 md:grid-cols-7" data-testid="audit-logs-filters-grid">
        <Input
          placeholder="search"
          value={filters.q}
          onChange={(event) => setFilters((prev) => ({ ...prev, q: event.target.value }))}
          data-testid="audit-logs-filter-search-input"
        />
        <Input
          placeholder="action"
          value={filters.action}
          onChange={(event) => setFilters((prev) => ({ ...prev, action: event.target.value }))}
          data-testid="audit-logs-filter-action-input"
        />
        <select
          className="border border-slate-700 bg-slate-950 px-2 text-sm"
          value={filters.severity}
          onChange={(event) => setFilters((prev) => ({ ...prev, severity: event.target.value }))}
          data-testid="audit-logs-filter-severity-select"
        >
          <option value="all">all severity</option>
          <option value="info">info</option>
          <option value="warning">warning</option>
          <option value="critical">critical</option>
        </select>
        <Input
          placeholder="request_id"
          value={filters.request_id}
          onChange={(event) => setFilters((prev) => ({ ...prev, request_id: event.target.value }))}
          data-testid="audit-logs-filter-request-id-input"
        />
        <Input
          placeholder="session_id"
          value={filters.session_id}
          onChange={(event) => setFilters((prev) => ({ ...prev, session_id: event.target.value }))}
          data-testid="audit-logs-filter-session-id-input"
        />
        <Button onClick={fetchLogs} data-testid="audit-logs-filter-apply-button">Filtrele</Button>
        <Button onClick={runRetentionPrune} disabled={isPruning} variant="outline" data-testid="audit-logs-retention-prune-button">
          {isPruning ? "Prune..." : "90 Gün Prune"}
        </Button>
      </div>

      <div className="border border-slate-800 bg-slate-900" data-testid="audit-logs-table-wrapper">
        {isLoading && <p className="p-3 text-sm text-slate-400" data-testid="audit-logs-loading-state">Yükleniyor...</p>}
        {!isLoading && logs.length === 0 && <p className="p-3 text-sm text-slate-500" data-testid="audit-logs-empty-state">Henüz audit kaydı yok.</p>}
        <Table data-testid="audit-logs-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="audit-table-head-time">Zaman</TableHead>
              <TableHead data-testid="audit-table-head-action">Action</TableHead>
              <TableHead data-testid="audit-table-head-request-id">Request</TableHead>
              <TableHead data-testid="audit-table-head-session-id">Session</TableHead>
              <TableHead data-testid="audit-table-head-route">Route</TableHead>
              <TableHead data-testid="audit-table-head-entity">Entity</TableHead>
              <TableHead data-testid="audit-table-head-severity">Severity</TableHead>
              <TableHead data-testid="audit-table-head-details">Details</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {logs.map((log) => (
              <TableRow key={log.id} data-testid={`audit-table-row-${log.id}`}>
                <TableCell className="font-mono text-xs" data-testid={`audit-table-time-${log.id}`}>{new Date(log.created_at).toLocaleString()}</TableCell>
                <TableCell data-testid={`audit-table-action-${log.id}`}>{log.action}</TableCell>
                <TableCell className="font-mono text-xs" data-testid={`audit-table-request-id-${log.id}`}>{log.request_id || "-"}</TableCell>
                <TableCell className="font-mono text-xs" data-testid={`audit-table-session-id-${log.id}`}>{log.session_id || "-"}</TableCell>
                <TableCell className="font-mono text-xs" data-testid={`audit-table-route-${log.id}`}>{log.route ? `${log.method || "GET"} ${log.route}` : "-"}</TableCell>
                <TableCell data-testid={`audit-table-entity-${log.id}`}>{log.entity_type}</TableCell>
                <TableCell data-testid={`audit-table-severity-${log.id}`}>{log.severity}</TableCell>
                <TableCell className="max-w-sm truncate font-mono text-xs" data-testid={`audit-table-details-${log.id}`}>{JSON.stringify(log.details || {})}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </section>
  );
};
