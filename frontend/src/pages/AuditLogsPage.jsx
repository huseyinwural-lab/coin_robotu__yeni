import { useEffect, useState } from "react";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

export const AuditLogsPage = () => {
  const [logs, setLogs] = useState([]);

  useEffect(() => {
    const fetchLogs = async () => {
      const { data } = await apiClient.get("/audit-logs");
      setLogs(data);
    };
    fetchLogs();
  }, []);

  return (
    <section className="space-y-4" data-testid="audit-logs-page">
      <header className="border border-blue-900 bg-slate-900 p-4" data-testid="audit-logs-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-blue-300" data-testid="audit-logs-title">Audit Log Tablosu</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="audit-logs-description">Admin görünümü için izleme ve kontrol iskeleti.</p>
      </header>

      <div className="border border-slate-800 bg-slate-900" data-testid="audit-logs-table-wrapper">
        <Table data-testid="audit-logs-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="audit-table-head-time">Zaman</TableHead>
              <TableHead data-testid="audit-table-head-action">Action</TableHead>
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
                <TableCell data-testid={`audit-table-entity-${log.id}`}>{log.entity_type}</TableCell>
                <TableCell data-testid={`audit-table-severity-${log.id}`}>{log.severity}</TableCell>
                <TableCell className="max-w-sm truncate font-mono text-xs" data-testid={`audit-table-details-${log.id}`}>{JSON.stringify(log.details)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </section>
  );
};
