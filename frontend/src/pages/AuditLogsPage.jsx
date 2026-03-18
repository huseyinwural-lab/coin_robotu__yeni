import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";

export const AuditLogsPage = () => {
  const { user } = useAuth();
  const [logs, setLogs] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isPruning, setIsPruning] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [exportWindowDays, setExportWindowDays] = useState("30");
  const [replayFilters, setReplayFilters] = useState({ request_id: "", session_id: "" });
  const [replayData, setReplayData] = useState(null);
  const [isReplayLoading, setIsReplayLoading] = useState(false);
  const [filters, setFilters] = useState({
    q: "",
    action: "",
    severity: "all",
    request_id: "",
    session_id: "",
  });

  const buildFilterParams = useCallback(() => ({
    limit: 300,
    q: filters.q || undefined,
    action: filters.action || undefined,
    severity: filters.severity !== "all" ? filters.severity : undefined,
    request_id: filters.request_id || undefined,
    session_id: filters.session_id || undefined,
  }), [filters]);

  const fetchLogs = useCallback(async () => {
    setIsLoading(true);
    try {
      const { data } = await apiClient.get("/audit-logs/timeline", {
        params: buildFilterParams(),
      });
      setLogs(data?.items || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Audit loglar yüklenemedi");
    } finally {
      setIsLoading(false);
    }
  }, [buildFilterParams]);

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

  const exportIncidentPackage = async () => {
    setIsExporting(true);
    try {
      const response = await apiClient.get("/audit-logs/admin/incident-export", {
        params: {
          ...buildFilterParams(),
          limit: 500,
          window_days: Number(exportWindowDays),
        },
        responseType: "blob",
      });
      const blobUrl = window.URL.createObjectURL(new Blob([response.data]));
      const anchor = document.createElement("a");
      anchor.href = blobUrl;
      anchor.download = `incident_package_${new Date().toISOString().replace(/[:.]/g, "-")}.zip`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(blobUrl);
      toast.success("Incident ZIP indirildi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Incident ZIP indirilemedi");
    } finally {
      setIsExporting(false);
    }
  };

  const loadIncidentReplay = async () => {
    if (!replayFilters.request_id && !replayFilters.session_id) {
      toast.error("Replay için request_id veya session_id girin");
      return;
    }
    setIsReplayLoading(true);
    try {
      const { data } = await apiClient.get("/audit-logs/incident-replay", {
        params: {
          request_id: replayFilters.request_id || undefined,
          session_id: replayFilters.session_id || undefined,
          limit: 1200,
        },
      });
      setReplayData(data || null);
      toast.success("Incident replay yüklendi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Incident replay yüklenemedi");
    } finally {
      setIsReplayLoading(false);
    }
  };

  return (
    <section className="space-y-4" data-testid="audit-logs-page">
      <header className="border border-blue-900 bg-slate-900 p-4" data-testid="audit-logs-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-blue-300" data-testid="audit-logs-title">System Timeline</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="audit-logs-description">Request ID, Session ID ve domain event akışları tek tabloda.</p>
      </header>

      <div className="grid gap-2 border border-slate-800 bg-slate-900 p-3 md:grid-cols-9" data-testid="audit-logs-filters-grid">
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
        {user?.role === "super_admin" && (
          <>
            <select
              className="border border-slate-700 bg-slate-950 px-2 text-sm"
              value={exportWindowDays}
              onChange={(event) => setExportWindowDays(event.target.value)}
              data-testid="audit-logs-incident-window-days-select"
            >
              <option value="1">1 gün</option>
              <option value="7">7 gün</option>
              <option value="30">30 gün</option>
              <option value="90">90 gün</option>
            </select>
            <Button onClick={exportIncidentPackage} disabled={isExporting} variant="outline" data-testid="audit-logs-incident-export-button">
              {isExporting ? "ZIP hazırlanıyor..." : "Incident ZIP İndir"}
            </Button>
          </>
        )}
      </div>

      <div className="space-y-3 border border-slate-800 bg-slate-900 p-3" data-testid="audit-logs-incident-replay-panel">
        <p className="text-sm font-semibold text-white" data-testid="audit-logs-incident-replay-title">Incident Replay</p>
        <div className="grid gap-2 md:grid-cols-4" data-testid="audit-logs-incident-replay-filters-grid">
          <Input
            placeholder="request_id"
            value={replayFilters.request_id}
            onChange={(event) => setReplayFilters((prev) => ({ ...prev, request_id: event.target.value }))}
            data-testid="audit-logs-incident-replay-request-id-input"
          />
          <Input
            placeholder="session_id"
            value={replayFilters.session_id}
            onChange={(event) => setReplayFilters((prev) => ({ ...prev, session_id: event.target.value }))}
            data-testid="audit-logs-incident-replay-session-id-input"
          />
          <Button onClick={loadIncidentReplay} disabled={isReplayLoading} data-testid="audit-logs-incident-replay-load-button">
            {isReplayLoading ? "Yükleniyor..." : "Replay Yükle"}
          </Button>
        </div>
        <div className="grid gap-2 md:grid-cols-4" data-testid="audit-logs-incident-replay-summary-grid">
          <p className="text-xs text-slate-300" data-testid="audit-logs-incident-replay-step-count">step_count={replayData?.summary?.step_count ?? 0}</p>
          <p className="text-xs text-slate-300" data-testid="audit-logs-incident-replay-error-steps">error_steps={replayData?.summary?.error_steps ?? 0}</p>
          <p className="text-xs text-slate-300" data-testid="audit-logs-incident-replay-window-start">window_start={replayData?.summary?.window_start || "-"}</p>
          <p className="text-xs text-slate-300" data-testid="audit-logs-incident-replay-window-end">window_end={replayData?.summary?.window_end || "-"}</p>
          <p className="text-xs text-slate-300 md:col-span-4" data-testid="audit-logs-incident-replay-root-cause-breakdown">
            root_cause_breakdown={JSON.stringify(replayData?.summary?.root_cause_breakdown || {})}
          </p>
        </div>
        <div className="max-h-56 overflow-auto border border-slate-700" data-testid="audit-logs-incident-replay-steps-wrap">
          {(replayData?.steps || []).slice(0, 20).map((step) => (
            <article key={`${step.step_index}-${step.timestamp}`} className="border-b border-slate-800 p-2 text-xs" data-testid={`audit-logs-incident-replay-step-${step.step_index}`}>
              <p data-testid={`audit-logs-incident-replay-step-action-${step.step_index}`}>{step.step_index}. {step.action}</p>
              <p className="text-slate-400" data-testid={`audit-logs-incident-replay-step-meta-${step.step_index}`}>{step.timestamp} · {step.method || "-"} {step.route || "-"} · Δ{step.delta_ms_from_prev ?? 0}ms</p>
              <p className="text-slate-400" data-testid={`audit-logs-incident-replay-step-root-cause-${step.step_index}`}>root={step.root_cause_type} · stage={step.failure_stage} · code={step.primary_error_code}</p>
              <p className="text-slate-400" data-testid={`audit-logs-incident-replay-step-intelligence-${step.step_index}`}>confidence={step.confidence_score ?? 0} · priority={step.priority_level || "LOW"} · secondary={step.secondary_cause?.type || "none"}</p>
            </article>
          ))}
          {(replayData?.steps || []).length === 0 && <p className="p-2 text-xs text-slate-500" data-testid="audit-logs-incident-replay-empty">Replay step bulunamadı.</p>}
        </div>
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
