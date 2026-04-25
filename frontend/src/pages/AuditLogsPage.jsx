import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

const ULTRA_DURATION_OPTIONS = ["1h", "3h", "5h", "8h", "12h", "1d", "3d", "5d", "7d"];

export const AuditLogsPage = () => {
  const [logs, setLogs] = useState([]);
  const [ultraEvents, setUltraEvents] = useState([]);
  const [ultraStatus, setUltraStatus] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [ultraDurationOption, setUltraDurationOption] = useState("1h");
  const [maxNormalLogMb, setMaxNormalLogMb] = useState("1024");
  const [maxUltraLogMb, setMaxUltraLogMb] = useState("512");
  const [ultraLogDir, setUltraLogDir] = useState("");
  const [isUltraSubmitting, setIsUltraSubmitting] = useState(false);

  const remainingLabel = useMemo(() => {
    const seconds = Number(ultraStatus?.remaining_seconds || 0);
    if (seconds <= 0) return "-";
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    return `${h}h ${m}m ${s}s`;
  }, [ultraStatus?.remaining_seconds]);

  const refreshUltra = useCallback(async () => {
    const [statusRes, eventsRes] = await Promise.all([
      apiClient.get("/admin/ultra-log/status"),
      apiClient.get("/admin/ultra-log/events?limit=100"),
    ]);
    setUltraStatus(statusRes.data || null);
    setUltraEvents(eventsRes.data || []);
  }, []);

  const fetchLogs = useCallback(async () => {
    setIsLoading(true);
    try {
      const [{ data: auditData }] = await Promise.all([apiClient.get("/audit-logs"), refreshUltra()]);
      setLogs(auditData || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Audit loglar yüklenemedi");
    } finally {
      setIsLoading(false);
    }
  }, [refreshUltra]);

  const activateUltra = async () => {
    setIsUltraSubmitting(true);
    try {
      await apiClient.post("/admin/ultra-log/activate", {
        duration_option: ultraDurationOption,
        max_normal_log_mb: Number(maxNormalLogMb || 1024),
        max_ultra_log_mb: Number(maxUltraLogMb || 512),
        ultra_log_dir: ultraLogDir,
      });
      toast.success("Ultra Log aktif edildi");
      await refreshUltra();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Ultra Log aktif edilemedi");
    } finally {
      setIsUltraSubmitting(false);
    }
  };

  const deactivateUltra = async () => {
    setIsUltraSubmitting(true);
    try {
      await apiClient.post("/admin/ultra-log/deactivate", { reason: "manual_deactivated" });
      toast.success("Ultra Log kapatıldı");
      await refreshUltra();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Ultra Log kapatılamadı");
    } finally {
      setIsUltraSubmitting(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  return (
    <section className="space-y-6" data-testid="audit-logs-page">
      <header className="border border-blue-900 bg-slate-900 p-4" data-testid="audit-logs-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-blue-300" data-testid="audit-logs-title">Audit Log Tablosu</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="audit-logs-description">Admin görünümü için izleme ve kontrol iskeleti.</p>
      </header>

      <div className="grid gap-4 xl:grid-cols-[380px_1fr]" data-testid="ultra-log-grid">
        <div className="space-y-3 border border-emerald-800 bg-emerald-950/20 p-4" data-testid="ultra-log-control-panel">
          <p className="text-xs uppercase tracking-wider text-emerald-300" data-testid="ultra-log-control-title">Ultra Log Yönetimi</p>
          <label className="space-y-1 text-xs text-slate-300" data-testid="ultra-log-duration-wrap">
            <span>Süre</span>
            <select
              value={ultraDurationOption}
              onChange={(event) => setUltraDurationOption(event.target.value)}
              className="w-full border border-slate-700 bg-slate-950 px-2 py-2 text-sm"
              data-testid="ultra-log-duration-select"
            >
              {ULTRA_DURATION_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>

          <label className="space-y-1 text-xs text-slate-300" data-testid="ultra-log-normal-limit-wrap">
            <span>Normal Log Limit (MB)</span>
            <Input
              value={maxNormalLogMb}
              onChange={(event) => setMaxNormalLogMb(event.target.value)}
              data-testid="ultra-log-normal-limit-input"
            />
          </label>

          <label className="space-y-1 text-xs text-slate-300" data-testid="ultra-log-ultra-limit-wrap">
            <span>Ultra Log Limit (MB)</span>
            <Input
              value={maxUltraLogMb}
              onChange={(event) => setMaxUltraLogMb(event.target.value)}
              data-testid="ultra-log-ultra-limit-input"
            />
          </label>

          <label className="space-y-1 text-xs text-slate-300" data-testid="ultra-log-dir-wrap">
            <span>Ultra Log Klasörü (opsiyonel)</span>
            <Input
              value={ultraLogDir}
              onChange={(event) => setUltraLogDir(event.target.value)}
              placeholder="/app/backend/logs/ultra_debug"
              data-testid="ultra-log-dir-input"
            />
          </label>

          <div className="flex flex-wrap gap-2" data-testid="ultra-log-actions-row">
            <Button onClick={activateUltra} disabled={isUltraSubmitting} data-testid="ultra-log-activate-button">
              Ultra Log Aç
            </Button>
            <Button variant="outline" onClick={deactivateUltra} disabled={isUltraSubmitting} data-testid="ultra-log-deactivate-button">
              Ultra Log Kapat
            </Button>
            <Button variant="outline" onClick={refreshUltra} disabled={isUltraSubmitting} data-testid="ultra-log-refresh-button">
              Yenile
            </Button>
          </div>
        </div>

        <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="ultra-log-status-panel">
          <p className="text-xs uppercase tracking-wider text-slate-400" data-testid="ultra-log-status-title">Ultra Log Durumu</p>
          <div className="grid gap-2 md:grid-cols-2 text-sm" data-testid="ultra-log-status-grid">
            <p data-testid="ultra-log-status-enabled">Aktif: <b>{ultraStatus?.enabled ? "Evet" : "Hayır"}</b></p>
            <p data-testid="ultra-log-status-duration">Süre: <b>{ultraStatus?.duration_option || "-"}</b></p>
            <p data-testid="ultra-log-status-remaining">Kalan: <b>{remainingLabel}</b></p>
            <p data-testid="ultra-log-status-reason">Auto close reason: <b>{ultraStatus?.auto_close_reason || "-"}</b></p>
            <p data-testid="ultra-log-status-normal-usage">Normal log kullanım: <b>{ultraStatus?.normal_log_usage_mb ?? 0} MB</b></p>
            <p data-testid="ultra-log-status-ultra-usage">Ultra log kullanım: <b>{ultraStatus?.ultra_log_usage_mb ?? 0} MB</b></p>
            <p className="md:col-span-2" data-testid="ultra-log-status-dir">Log dizini: <b>{ultraStatus?.ultra_log_dir || "-"}</b></p>
            <p data-testid="ultra-log-status-started">Başlangıç: <b>{ultraStatus?.started_at ? new Date(ultraStatus.started_at).toLocaleString() : "-"}</b></p>
            <p data-testid="ultra-log-status-expires">Bitiş: <b>{ultraStatus?.expires_at ? new Date(ultraStatus.expires_at).toLocaleString() : "-"}</b></p>
          </div>
        </div>
      </div>

      <div className="border border-slate-800 bg-slate-900" data-testid="ultra-log-events-wrapper">
        <header className="border-b border-slate-800 px-3 py-2" data-testid="ultra-log-events-header">
          <h3 className="text-sm uppercase tracking-wider text-slate-300" data-testid="ultra-log-events-title">Ultra Log Olayları</h3>
        </header>
        {ultraEvents.length === 0 && <p className="p-3 text-sm text-slate-500" data-testid="ultra-log-events-empty">Ultra log olayı yok.</p>}
        <Table data-testid="ultra-log-events-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="ultra-log-events-head-time">Zaman</TableHead>
              <TableHead data-testid="ultra-log-events-head-category">Kategori</TableHead>
              <TableHead data-testid="ultra-log-events-head-name">Event</TableHead>
              <TableHead data-testid="ultra-log-events-head-severity">Severity</TableHead>
              <TableHead data-testid="ultra-log-events-head-route">Route</TableHead>
              <TableHead data-testid="ultra-log-events-head-status">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ultraEvents.map((event) => (
              <TableRow key={event.id} data-testid={`ultra-log-events-row-${event.id}`}>
                <TableCell className="font-mono text-xs" data-testid={`ultra-log-events-time-${event.id}`}>{new Date(event.created_at).toLocaleString()}</TableCell>
                <TableCell data-testid={`ultra-log-events-category-${event.id}`}>{event.category}</TableCell>
                <TableCell data-testid={`ultra-log-events-name-${event.id}`}>{event.event_name}</TableCell>
                <TableCell data-testid={`ultra-log-events-severity-${event.id}`}>{event.severity}</TableCell>
                <TableCell className="font-mono text-xs" data-testid={`ultra-log-events-route-${event.id}`}>{event.method || "-"} {event.path || "-"}</TableCell>
                <TableCell data-testid={`ultra-log-events-status-${event.id}`}>{event.status_code ?? "-"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="border border-slate-800 bg-slate-900" data-testid="audit-logs-table-wrapper">
        {isLoading && <p className="p-3 text-sm text-slate-400" data-testid="audit-logs-loading-state">Yükleniyor...</p>}
        {!isLoading && logs.length === 0 && <p className="p-3 text-sm text-slate-500" data-testid="audit-logs-empty-state">Henüz audit kaydı yok.</p>}
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
