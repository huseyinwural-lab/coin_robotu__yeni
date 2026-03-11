import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

export const StateRebuildLogsPage = () => {
  const [logs, setLogs] = useState([]);

  const loadLogs = async () => {
    try {
      const { data } = await apiClient.get("/admin-phase3/state-rebuild-logs");
      setLogs(data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "State rebuild logları alınamadı");
    }
  };

  useEffect(() => {
    loadLogs();
  }, []);

  const triggerRebuild = async () => {
    try {
      await apiClient.post("/admin-phase3/state-rebuild/run");
      toast.success("State rebuild tetiklendi");
      loadLogs();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "State rebuild tetiklenemedi");
    }
  };

  return (
    <section className="space-y-4" data-testid="state-rebuild-page">
      <header className="border border-blue-900 bg-slate-900 p-4" data-testid="state-rebuild-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-blue-300" data-testid="state-rebuild-title">State Rebuild Logları</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="state-rebuild-description">Restart sonrası state restore kayıtları izlenir.</p>
        <Button className="mt-3 bg-blue-600 text-white hover:bg-blue-700" onClick={triggerRebuild} data-testid="state-rebuild-trigger-button">
          Manual Rebuild Trigger
        </Button>
      </header>

      <div className="border border-slate-800 bg-slate-900" data-testid="state-rebuild-table-wrapper">
        <Table data-testid="state-rebuild-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="rebuild-head-type">Type</TableHead>
              <TableHead data-testid="rebuild-head-status">Status</TableHead>
              <TableHead data-testid="rebuild-head-trigger">Trigger</TableHead>
              <TableHead data-testid="rebuild-head-details">Details</TableHead>
              <TableHead data-testid="rebuild-head-time">Started</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {logs.map((logItem) => (
              <TableRow key={logItem.id} data-testid={`rebuild-row-${logItem.id}`}>
                <TableCell data-testid={`rebuild-type-${logItem.id}`}>{logItem.rebuild_type}</TableCell>
                <TableCell data-testid={`rebuild-status-${logItem.id}`}>{logItem.status}</TableCell>
                <TableCell data-testid={`rebuild-trigger-${logItem.id}`}>{logItem.trigger_source}</TableCell>
                <TableCell className="max-w-sm truncate text-xs" data-testid={`rebuild-details-${logItem.id}`}>{JSON.stringify(logItem.details)}</TableCell>
                <TableCell className="font-mono text-xs" data-testid={`rebuild-time-${logItem.id}`}>{new Date(logItem.started_at).toLocaleString()}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </section>
  );
};
