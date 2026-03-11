import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { MetricCard } from "@/components/MetricCard";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

export const HardeningChecklistPage = () => {
  const [checklist, setChecklist] = useState(null);

  const loadLatest = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/admin-phase3/hardening-checklist/latest");
      setChecklist(data);
    } catch (error) {
      if (error?.response?.status !== 404) {
        toast.error(error?.response?.data?.detail || "Checklist verisi alınamadı");
      }
    }
  }, []);

  useEffect(() => {
    loadLatest();
  }, [loadLatest]);

  const runChecklist = async () => {
    try {
      const { data } = await apiClient.post("/admin-phase3/hardening-checklist/run");
      setChecklist(data);
      toast.success("Hardening checklist çalıştırıldı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Checklist çalıştırılamadı");
    }
  };

  return (
    <section className="space-y-4" data-testid="hardening-checklist-page">
      <header className="border border-blue-900 bg-slate-900 p-4" data-testid="hardening-checklist-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-blue-300" data-testid="hardening-checklist-title">Hardening Checklist</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="hardening-checklist-description">
          Kritik kapı mantığı aktif: kritik kontrollerden biri fail ise skor 60 altına kilitlenir.
        </p>
        <Button className="mt-3 bg-blue-600 text-white hover:bg-blue-700" onClick={runChecklist} data-testid="hardening-checklist-run-button">
          Checklist Çalıştır
        </Button>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" data-testid="hardening-checklist-metrics-grid">
        <MetricCard label="Score" value={checklist?.score ?? "-"} tone="blue" testId="hardening-metric-score" />
        <MetricCard label="Readiness" value={checklist?.readiness_status ?? "-"} tone={checklist?.readiness_status === "ready" ? "blue" : "red"} testId="hardening-metric-readiness" />
        <MetricCard label="Critical Blocked" value={String(checklist?.critical_blocked ?? "-")} tone="red" testId="hardening-metric-critical-blocked" />
        <MetricCard label="Last Run" value={checklist?.created_at ? new Date(checklist.created_at).toLocaleString() : "-"} tone="orange" testId="hardening-metric-last-run" />
      </div>

      <div className="border border-slate-800 bg-slate-900" data-testid="hardening-checklist-table-wrapper">
        <Table data-testid="hardening-checklist-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="hardening-head-label">Kontrol</TableHead>
              <TableHead data-testid="hardening-head-critical">Critical</TableHead>
              <TableHead data-testid="hardening-head-status">Status</TableHead>
              <TableHead data-testid="hardening-head-value">Value</TableHead>
              <TableHead data-testid="hardening-head-threshold">Threshold</TableHead>
              <TableHead data-testid="hardening-head-note">Note</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(checklist?.checklist_items || []).map((item) => (
              <TableRow key={item.key} data-testid={`hardening-row-${item.key}`}>
                <TableCell data-testid={`hardening-label-${item.key}`}>{item.label}</TableCell>
                <TableCell data-testid={`hardening-critical-${item.key}`}>{String(item.critical)}</TableCell>
                <TableCell data-testid={`hardening-status-${item.key}`}>{item.status}</TableCell>
                <TableCell className="max-w-xs truncate font-mono text-xs" data-testid={`hardening-value-${item.key}`}>{JSON.stringify(item.value)}</TableCell>
                <TableCell data-testid={`hardening-threshold-${item.key}`}>{item.threshold}</TableCell>
                <TableCell className="max-w-xs truncate text-xs" data-testid={`hardening-note-${item.key}`}>{item.note}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </section>
  );
};
