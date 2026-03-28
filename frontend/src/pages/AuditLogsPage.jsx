import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, BugPlay, Search } from "lucide-react";
import { toast } from "sonner";
import { Background, Controls, MiniMap, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient, FRONTEND_BACKEND_URL } from "@/lib/api";

const severityClass = {
  info: "bg-cyan-900/40 text-cyan-200",
  warning: "bg-amber-900/40 text-amber-200",
  critical: "bg-rose-900/40 text-rose-200",
};

const LIFECYCLE_ORDER = ["request", "intent", "decision", "risk", "order", "execution", "fill"];

export const AuditLogsPage = () => {
  const [filters, setFilters] = useState({
    q: "",
    payload_query: "",
    severity: "",
    strategy_id: "",
    symbol: "",
    user_id: "",
    event_type: "",
    environment: "prod",
    start_time: "",
    end_time: "",
  });
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState([]);
  const [nextCursor, setNextCursor] = useState(null);
  const [hasMore, setHasMore] = useState(false);
  const [visibleCount, setVisibleCount] = useState(40);
  const [queryLatencyMs, setQueryLatencyMs] = useState(null);

  const [savedQueries, setSavedQueries] = useState([]);
  const [savedQueryName, setSavedQueryName] = useState("");

  const [selectedCorrelation, setSelectedCorrelation] = useState("");
  const [detailLoading, setDetailLoading] = useState(false);
  const [detail, setDetail] = useState(null);
  const [failureExplanation, setFailureExplanation] = useState(null);
  const [rootCauseBreakdown, setRootCauseBreakdown] = useState(null);
  const [replayResult, setReplayResult] = useState(null);
  const [incidents, setIncidents] = useState([]);
  const [viewMode, setViewMode] = useState("graph");
  const [showTestEvents, setShowTestEvents] = useState(false);
  const [archiveMode, setArchiveMode] = useState(false);
  const [crossEnvComparison, setCrossEnvComparison] = useState(null);
  const [integrityResult, setIntegrityResult] = useState(null);
  const [selectedEventId, setSelectedEventId] = useState("");
  const [expandedEventRows, setExpandedEventRows] = useState({});

  const fetchSavedQueries = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/audit-logs/saved-queries", { params: { limit: 50 } });
      setSavedQueries(data?.items || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Saved query listesi alınamadı");
    }
  }, []);

  const fetchSummaries = useCallback(async (cursor = null) => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/audit-logs/trading-lifecycle", {
        params: {
          limit: 150,
          cursor: cursor || undefined,
          q: filters.q || undefined,
          payload_query: filters.payload_query || undefined,
          severity: filters.severity || undefined,
          strategy_id: filters.strategy_id || undefined,
          symbol: filters.symbol || undefined,
          user_id: filters.user_id || undefined,
          event_type: filters.event_type || undefined,
          environment: filters.environment || undefined,
          start_time: filters.start_time || undefined,
          end_time: filters.end_time || undefined,
          include_test_events: showTestEvents,
          archive_mode: archiveMode,
        },
      });
      const incomingItems = data?.items || [];
      if (cursor) {
        setItems((prev) => {
          const map = new Map(prev.map((item) => [item.correlation_id, item]));
          incomingItems.forEach((item) => map.set(item.correlation_id, item));
          return Array.from(map.values());
        });
      } else {
        setItems(incomingItems);
      }
      setNextCursor(data?.next_cursor || null);
      setHasMore(Boolean(data?.has_more));
      setVisibleCount(40);
      setQueryLatencyMs(data?.query_latency_ms || null);
      if (data?.missing_correlation_event_ids?.length) {
        toast.warning(`Correlation eksik event sayısı: ${data.missing_correlation_event_ids.length}`);
      }
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Trading lifecycle listesi alınamadı");
    } finally {
      setLoading(false);
    }
  }, [
    filters.end_time,
    filters.environment,
    filters.event_type,
    filters.payload_query,
    filters.q,
    filters.severity,
    filters.start_time,
    filters.strategy_id,
    filters.symbol,
    filters.user_id,
    archiveMode,
    showTestEvents,
  ]);

  useEffect(() => {
    fetchSummaries(null);
    fetchSavedQueries();
  }, [fetchSavedQueries, fetchSummaries]);

  const fetchIncidents = useCallback(async (correlationId) => {
    if (!correlationId) {
      setIncidents([]);
      return;
    }
    try {
      const { data } = await apiClient.get("/audit-logs/incidents", {
        params: { linked_correlation_id: correlationId, limit: 20 },
      });
      setIncidents(data?.items || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Incident listesi alınamadı");
    }
  }, []);

  const openLifecycle = useCallback(async (correlationId) => {
    setSelectedCorrelation(correlationId);
    setFailureExplanation(null);
    setRootCauseBreakdown(null);
    setReplayResult(null);
    setCrossEnvComparison(null);
    setIntegrityResult(null);
    setSelectedEventId("");
    setExpandedEventRows({});
    setDetailLoading(true);
    try {
      const { data } = await apiClient.get(`/audit-logs/lifecycle/${encodeURIComponent(correlationId)}`);
      setDetail(data);
      setRootCauseBreakdown(data?.root_cause_breakdown || null);
      fetchIncidents(correlationId);
    } catch (error) {
      setDetail(null);
      toast.error(error?.response?.data?.detail || "Lifecycle detayı alınamadı");
    } finally {
      setDetailLoading(false);
    }
  }, [fetchIncidents]);

  const explainFailure = useCallback(async () => {
    if (!selectedCorrelation) return;
    setDetailLoading(true);
    try {
      const { data } = await apiClient.post("/audit-logs/explain", { correlation_id: selectedCorrelation });
      setFailureExplanation(data || null);
      setRootCauseBreakdown(data?.root_cause_breakdown || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Explain failure alınamadı");
    } finally {
      setDetailLoading(false);
    }
  }, [selectedCorrelation]);

  useEffect(() => {
    if (!selectedCorrelation && items.length > 0) {
      openLifecycle(items[0].correlation_id);
    }
  }, [items, openLifecycle, selectedCorrelation]);

  const saveCurrentQuery = useCallback(async () => {
    const trimmedName = savedQueryName.trim();
    if (!trimmedName) {
      toast.error("Saved query adı girin");
      return;
    }
    try {
      await apiClient.post("/audit-logs/saved-queries", { name: trimmedName, params: filters });
      setSavedQueryName("");
      fetchSavedQueries();
      toast.success("Query kaydedildi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Query kaydedilemedi");
    }
  }, [fetchSavedQueries, filters, savedQueryName]);

  const applySavedQuery = useCallback((savedId) => {
    const selected = savedQueries.find((item) => item.id === savedId);
    if (!selected) return;
    const params = selected.params || {};
    setFilters((prev) => ({
      ...prev,
      ...params,
      q: String(params.q || ""),
      payload_query: String(params.payload_query || ""),
      severity: String(params.severity || ""),
      strategy_id: String(params.strategy_id || ""),
      symbol: String(params.symbol || ""),
      user_id: String(params.user_id || ""),
      event_type: String(params.event_type || ""),
      environment: String(params.environment || ""),
      start_time: String(params.start_time || ""),
      end_time: String(params.end_time || ""),
    }));
    toast.success(`Saved query uygulandı: ${selected.name}`);
  }, [savedQueries]);

  const createIncident = useCallback(async () => {
    if (!selectedCorrelation) return;
    try {
      const payload = {
        title: `Lifecycle Incident ${selectedCorrelation.slice(0, 10)}`,
        severity: "CRITICAL",
        tags: ["manual", "debug"],
        linked_correlation_id: selectedCorrelation,
        source_event_id: detail?.chain?.break_step?.event_id || null,
        root_cause: failureExplanation?.root_cause || rootCauseBreakdown?.root_cause || null,
        cluster_id: rootCauseBreakdown?.cluster_id || null,
        details: {
          pattern_tag: rootCauseBreakdown?.pattern_tag || null,
          missing_critical_stages: detail?.chain?.missing_critical_stages || [],
        },
      };
      await apiClient.post("/audit-logs/incidents", payload);
      toast.success("Incident oluşturuldu");
      fetchIncidents(selectedCorrelation);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Incident oluşturulamadı");
    }
  }, [detail?.chain?.break_step?.event_id, detail?.chain?.missing_critical_stages, failureExplanation?.root_cause, fetchIncidents, rootCauseBreakdown?.cluster_id, rootCauseBreakdown?.pattern_tag, rootCauseBreakdown?.root_cause, selectedCorrelation]);

  const closeIncident = useCallback(async (incidentId) => {
    try {
      await apiClient.patch(`/audit-logs/incidents/${encodeURIComponent(incidentId)}/status`, { status: "closed" });
      toast.success("Incident kapatıldı");
      fetchIncidents(selectedCorrelation);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Incident kapatılamadı");
    }
  }, [fetchIncidents, selectedCorrelation]);

  const exportIncidentBundle = useCallback((incidentId) => {
    const url = `${FRONTEND_BACKEND_URL}/api/audit-logs/incidents/${encodeURIComponent(incidentId)}/bundle`;
    window.open(url, "_blank", "noopener,noreferrer");
  }, []);

  const loadMore = useCallback(() => {
    if (!hasMore || !nextCursor || loading) return;
    fetchSummaries(nextCursor);
  }, [fetchSummaries, hasMore, loading, nextCursor]);

  const fetchCrossEnvironmentComparison = useCallback(async () => {
    if (!selectedCorrelation) return;
    try {
      const { data } = await apiClient.get(`/audit-logs/lifecycle/compare/${encodeURIComponent(selectedCorrelation)}`, {
        params: { environments: "prod,staging,test,canary", limit: 1200 },
      });
      setCrossEnvComparison(data || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Cross-environment compare alınamadı");
    }
  }, [selectedCorrelation]);

  const verifyIntegrity = useCallback(async () => {
    if (!selectedCorrelation) return;
    try {
      const { data } = await apiClient.get("/audit/verify-trace", {
        params: {
          correlation_id: selectedCorrelation,
          environment: filters.environment || undefined,
        },
      });
      setIntegrityResult(data || null);
      toast.success("Integrity doğrulaması tamamlandı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Integrity doğrulaması başarısız");
    }
  }, [filters.environment, selectedCorrelation]);

  const copyToClipboard = useCallback(async (value, successMessage) => {
    try {
      await navigator.clipboard.writeText(String(value || ""));
      toast.success(successMessage);
    } catch {
      toast.error("Kopyalama başarısız");
    }
  }, []);

  const onCopyFullTrace = useCallback(() => {
    copyToClipboard(JSON.stringify(detail?.events || detail?.chain?.events || [], null, 2), "Full trace kopyalandı");
  }, [copyToClipboard, detail?.chain?.events, detail?.events]);

  const onCopyCorrelationChain = useCallback(() => {
    const chain = (detail?.events || detail?.chain?.events || []).map((event) => event.event_id).join(" -> ");
    copyToClipboard(chain, "Correlation chain kopyalandı");
  }, [copyToClipboard, detail?.chain?.events, detail?.events]);

  const onCopySelectedEventJson = useCallback(() => {
    const eventsList = detail?.events || detail?.chain?.events || [];
    const selectedEvent = eventsList.find((event) => event.event_id === selectedEventId);
    copyToClipboard(JSON.stringify(selectedEvent || {}, null, 2), "Event JSON kopyalandı");
  }, [copyToClipboard, detail?.chain?.events, detail?.events, selectedEventId]);

  const onCopyReplayInput = useCallback(() => {
    const replayInput = {
      correlation_id: selectedCorrelation,
      replay_mode: "isolated",
      events: detail?.events || detail?.chain?.events || [],
    };
    copyToClipboard(JSON.stringify(replayInput, null, 2), "Replay input kopyalandı");
  }, [copyToClipboard, detail?.chain?.events, detail?.events, selectedCorrelation]);

  const runReplay = useCallback(async () => {
    if (!selectedCorrelation) return;
    setDetailLoading(true);
    try {
      const { data } = await apiClient.post(`/audit-logs/trading-lifecycle/${encodeURIComponent(selectedCorrelation)}/replay`);
      setReplayResult(data);
      toast.success("Replay çalıştırıldı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Replay başarısız");
    } finally {
      setDetailLoading(false);
    }
  }, [selectedCorrelation]);

  const stats = useMemo(
    () => ({
      total: items.length,
      hasError: items.filter((item) => item.has_error).length,
      incomplete: items.filter((item) => item.trace_incomplete).length,
    }),
    [items],
  );

  const hasLifecycle = Boolean(selectedCorrelation && detail);
  const hasRca = Boolean(failureExplanation || rootCauseBreakdown);
  const hasIncident = incidents.length > 0;

  const exportLatestIncident = useCallback(() => {
    if (!incidents.length) {
      toast.error("Önce incident oluşturun");
      return;
    }
    exportIncidentBundle(incidents[0].incident_id);
  }, [exportIncidentBundle, incidents]);

  const events = detail?.events || detail?.chain?.events || [];
  const renderedItems = items.slice(0, visibleCount);
  const graphData = useMemo(() => {
    const sourceEvents = detail?.events || detail?.chain?.events || [];
    const brokenEventId = failureExplanation?.explain_failure?.broken_step?.event_id || null;
    const brokenIndex = sourceEvents.findIndex((event) => event.event_id === brokenEventId);
    const nodes = sourceEvents.map((event, index) => {
      const stageIndex = Math.max(LIFECYCLE_ORDER.indexOf(event.lifecycle_stage), 0);
      const isBroken = brokenEventId && event.event_id === brokenEventId;
      const isUpstream = brokenIndex > 0 && index < brokenIndex;
      const background = isBroken ? "#7f1d1d" : isUpstream ? "#92400e" : "#1f2937";
      return {
        id: event.event_id,
        position: { x: index * 190, y: stageIndex * 130 },
        data: { label: `${event.lifecycle_stage} • ${event.event_type}` },
        style: {
          width: 180,
          borderRadius: 12,
          background,
          color: "#e5e7eb",
          border: "1px solid rgba(148,163,184,0.55)",
          fontSize: 12,
          padding: 8,
        },
      };
    });

    const edges = sourceEvents
      .map((event, index) => {
        const targetId = event.event_id;
        const sourceId = event.parent_event_id || (index > 0 ? sourceEvents[index - 1]?.event_id : null);
        if (!sourceId || !targetId || sourceId === targetId) {
          return null;
        }
        return {
          id: `${sourceId}-${targetId}`,
          source: sourceId,
          target: targetId,
          animated: true,
          style: {
            stroke: brokenEventId && targetId === brokenEventId ? "#ef4444" : "#34d399",
            strokeWidth: 2,
          },
        };
      })
      .filter(Boolean);

    return { nodes, edges };
  }, [detail?.chain?.events, detail?.events, failureExplanation?.explain_failure?.broken_step?.event_id]);

  const rootCauseSummary = useMemo(() => {
    if (failureExplanation?.root_cause) return failureExplanation.root_cause;
    if (rootCauseBreakdown?.root_cause) return rootCauseBreakdown.root_cause;
    if (rootCauseBreakdown?.failure_type) return rootCauseBreakdown.failure_type;
    if (failureExplanation?.broken_step) return `broken_step:${failureExplanation.broken_step}`;
    if (detail?.chain?.break_step?.event_type) return `broken_step:${detail.chain.break_step.event_type}`;
    if (detail?.broken_chain) return "broken_chain_detected";
    if (detail?.trace_incomplete) return "trace_incomplete";
    return "root_cause_unknown";
  }, [
    detail?.broken_chain,
    detail?.chain?.break_step?.event_type,
    detail?.trace_incomplete,
    failureExplanation?.broken_step,
    failureExplanation?.root_cause,
    rootCauseBreakdown?.failure_type,
    rootCauseBreakdown?.root_cause,
  ]);

  const actionSuggestion = useMemo(() => {
    if (!selectedCorrelation) {
      return "Correlation seçin ve Explain Failure çalıştırın.";
    }
    if (detail?.missing_critical_stages?.length) {
      return `Eksik stage'leri tamamla: ${detail.missing_critical_stages.join(", ")}`;
    }
    if (detail?.broken_chain) {
      return "Parent-child zincirini onar ve orphan eventleri bağla.";
    }
    if (failureExplanation?.broken_step) {
      return `Broken step için upstream/downstream kontrolü: ${failureExplanation.broken_step}`;
    }
    if (rootCauseBreakdown?.critical_blockers?.length) {
      return `Kritik blockerları çöz: ${rootCauseBreakdown.critical_blockers.join(", ")}`;
    }
    return "Replay + Verify Integrity ile doğrula.";
  }, [detail?.broken_chain, detail?.missing_critical_stages, failureExplanation?.broken_step, rootCauseBreakdown?.critical_blockers, selectedCorrelation]);

  return (
    <section className="space-y-6" data-testid="audit-logs-page">
      <header className="rounded-2xl border border-cyan-800/50 bg-gradient-to-r from-slate-950 via-slate-900 to-cyan-950 p-6" data-testid="audit-logs-header">
        <h2 className="text-4xl font-black tracking-tight text-cyan-200" data-testid="audit-logs-title">Trading Lifecycle Debugger</h2>
        <p className="mt-2 text-sm text-slate-300" data-testid="audit-logs-subtitle">
          request → intent → decision → risk → order → execution → fill zincirini correlation bazında uçtan uca izle.
        </p>
        <div className="mt-4 flex flex-wrap gap-3 text-xs text-slate-300" data-testid="audit-logs-meta">
          <span data-testid="audit-logs-meta-total">chains: {stats.total}</span>
          <span data-testid="audit-logs-meta-critical">has_error: {stats.hasError}</span>
          <span data-testid="audit-logs-meta-warning">trace_incomplete: {stats.incomplete}</span>
          <span data-testid="audit-logs-meta-query-latency">query_latency_ms: {queryLatencyMs ?? "-"}</span>
        </div>
      </header>

      <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4" data-testid="audit-debug-flow-panel">
        <div className="flex flex-wrap items-start justify-between gap-2" data-testid="audit-debug-flow-header">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400" data-testid="audit-debug-flow-title">Lifecycle → RCA → Incident → Export</p>
            <p className="text-sm text-slate-300" data-testid="audit-debug-flow-subtitle">Tek ekranda debug ve aksiyon akışı.</p>
          </div>
          <p className="text-xs text-slate-400" data-testid="audit-debug-flow-selected">correlation: {selectedCorrelation || "seçilmedi"}</p>
        </div>
        <div className="mt-3 grid gap-3 md:grid-cols-4" data-testid="audit-debug-flow-steps">
          <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-3" data-testid="audit-debug-flow-step-lifecycle">
            <p className="text-xs uppercase text-slate-400" data-testid="audit-debug-flow-lifecycle-label">1) Lifecycle</p>
            <p className="text-sm text-slate-100" data-testid="audit-debug-flow-lifecycle-status">status: {hasLifecycle ? "READY" : "WAITING"}</p>
            <p className="text-xs text-slate-400" data-testid="audit-debug-flow-lifecycle-hint">Correlation seçildiğinde otomatik yüklenir.</p>
          </div>
          <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-3" data-testid="audit-debug-flow-step-rca">
            <p className="text-xs uppercase text-slate-400" data-testid="audit-debug-flow-rca-label">2) RCA</p>
            <p className="text-sm text-slate-100" data-testid="audit-debug-flow-rca-status">status: {hasRca ? "READY" : "WAITING"}</p>
            <Button
              size="sm"
              className="mt-2 w-full"
              onClick={explainFailure}
              disabled={!selectedCorrelation || detailLoading}
              data-testid="audit-debug-flow-rca-button"
            >
              Explain / RCA
            </Button>
          </div>
          <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-3" data-testid="audit-debug-flow-step-incident">
            <p className="text-xs uppercase text-slate-400" data-testid="audit-debug-flow-incident-label">3) Incident</p>
            <p className="text-sm text-slate-100" data-testid="audit-debug-flow-incident-status">status: {hasIncident ? "READY" : "WAITING"}</p>
            <Button
              size="sm"
              className="mt-2 w-full"
              variant="outline"
              onClick={createIncident}
              disabled={!hasRca || detailLoading}
              data-testid="audit-debug-flow-incident-button"
            >
              Incident Oluştur
            </Button>
          </div>
          <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-3" data-testid="audit-debug-flow-step-export">
            <p className="text-xs uppercase text-slate-400" data-testid="audit-debug-flow-export-label">4) Export</p>
            <p className="text-sm text-slate-100" data-testid="audit-debug-flow-export-status">status: {hasIncident ? "READY" : "WAITING"}</p>
            <Button
              size="sm"
              className="mt-2 w-full"
              variant="secondary"
              onClick={exportLatestIncident}
              disabled={!hasIncident}
              data-testid="audit-debug-flow-export-button"
            >
              Export Bundle
            </Button>
          </div>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-5" data-testid="audit-logs-filter-grid">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
          <Input
            value={filters.q}
            onChange={(event) => setFilters((prev) => ({ ...prev, q: event.target.value }))}
            placeholder="correlation / reason ara"
            className="pl-9"
            data-testid="audit-logs-filter-q-input"
          />
        </div>
        <Input
          value={filters.payload_query}
          onChange={(event) => setFilters((prev) => ({ ...prev, payload_query: event.target.value }))}
          placeholder="payload full-text"
          data-testid="audit-logs-filter-payload-query-input"
        />
        <select
          value={filters.severity}
          onChange={(event) => setFilters((prev) => ({ ...prev, severity: event.target.value }))}
          className="h-10 rounded-md border border-slate-700 bg-slate-900 px-3 text-sm text-white"
          data-testid="audit-logs-filter-severity-select"
        >
          <option value="">severity: all</option>
          <option value="INFO">INFO</option>
          <option value="WARNING">WARNING</option>
          <option value="ERROR">ERROR</option>
          <option value="CRITICAL">CRITICAL</option>
        </select>
        <Input
          value={filters.strategy_id}
          onChange={(event) => setFilters((prev) => ({ ...prev, strategy_id: event.target.value }))}
          placeholder="strategy_id"
          data-testid="audit-logs-filter-strategy-id-input"
        />
        <Input
          value={filters.symbol}
          onChange={(event) => setFilters((prev) => ({ ...prev, symbol: event.target.value }))}
          placeholder="symbol"
          data-testid="audit-logs-filter-symbol-input"
        />
      </div>

      <div className="grid gap-3 md:grid-cols-5" data-testid="audit-logs-filter-grid-secondary">
        <Input
          value={filters.user_id}
          onChange={(event) => setFilters((prev) => ({ ...prev, user_id: event.target.value }))}
          placeholder="user_id"
          data-testid="audit-logs-filter-user-id-input"
        />
        <Input
          value={filters.event_type}
          onChange={(event) => setFilters((prev) => ({ ...prev, event_type: event.target.value }))}
          placeholder="event_type"
          data-testid="audit-logs-filter-event-type-input"
        />
        <select
          value={filters.environment}
          onChange={(event) => setFilters((prev) => ({ ...prev, environment: event.target.value }))}
          className="h-10 rounded-md border border-slate-700 bg-slate-900 px-3 text-sm text-white"
          data-testid="audit-logs-filter-environment-select"
        >
          <option value="prod">prod</option>
          <option value="staging">staging</option>
          <option value="test">test</option>
          <option value="canary">canary</option>
        </select>
        <Input
          value={filters.start_time}
          onChange={(event) => setFilters((prev) => ({ ...prev, start_time: event.target.value }))}
          placeholder="start_time (ISO/ms)"
          data-testid="audit-logs-filter-start-time-input"
        />
        <Input
          value={filters.end_time}
          onChange={(event) => setFilters((prev) => ({ ...prev, end_time: event.target.value }))}
          placeholder="end_time (ISO/ms)"
          data-testid="audit-logs-filter-end-time-input"
        />
      </div>

      <div className="grid gap-3 md:grid-cols-5" data-testid="audit-logs-query-actions-grid">
        <Input
          value={savedQueryName}
          onChange={(event) => setSavedQueryName(event.target.value)}
          placeholder="saved query adı"
          data-testid="audit-logs-save-query-name-input"
        />
        <Button onClick={saveCurrentQuery} variant="outline" data-testid="audit-logs-save-query-button">
          Save Query
        </Button>
        <select
          onChange={(event) => applySavedQuery(event.target.value)}
          className="h-10 rounded-md border border-slate-700 bg-slate-900 px-3 text-sm text-white"
          data-testid="audit-logs-saved-query-select"
          value=""
        >
          <option value="">saved query seç</option>
          {savedQueries.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        <Button onClick={() => fetchSummaries(null)} disabled={loading} data-testid="audit-logs-filter-apply-button">
          Yenile
        </Button>
        <Button
          variant="secondary"
          onClick={loadMore}
          disabled={!hasMore || loading}
          data-testid="audit-logs-pagination-load-more-button"
        >
          {hasMore ? "Load more" : "No more"}
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-3" data-testid="audit-logs-view-and-env-controls">
        <Button
          variant={viewMode === "graph" ? "default" : "outline"}
          onClick={() => setViewMode("graph")}
          data-testid="audit-view-mode-graph-button"
        >
          Graph View (Primary)
        </Button>
        <Button
          variant={viewMode === "table" ? "default" : "outline"}
          onClick={() => setViewMode("table")}
          data-testid="audit-view-mode-table-button"
        >
          Event List (Secondary)
        </Button>
        <label className="flex items-center gap-2 text-sm text-slate-300" data-testid="audit-show-test-events-toggle-wrapper">
          <input
            type="checkbox"
            checked={showTestEvents}
            onChange={(event) => setShowTestEvents(event.target.checked)}
            data-testid="audit-show-test-events-toggle"
          />
          test eventleri göster
        </label>
        <label className="flex items-center gap-2 text-sm text-slate-300" data-testid="audit-archive-mode-toggle-wrapper">
          <input
            type="checkbox"
            checked={archiveMode}
            onChange={(event) => setArchiveMode(event.target.checked)}
            data-testid="audit-archive-mode-toggle"
          />
          archive mode (cold)
        </label>
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-3" data-testid="audit-logs-graph-panel">
        <div
          className="sticky top-0 z-10 mb-3 rounded-xl border border-slate-700/60 bg-slate-950/90 p-3 backdrop-blur"
          data-testid="audit-root-cause-sticky-panel"
        >
          <p
            className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400"
            data-testid="audit-root-cause-sticky-label"
          >
            Tek satır kök neden özeti
          </p>
          <p className="mt-1 text-sm text-slate-100" data-testid="audit-root-cause-sticky-summary">
            Kök neden:{" "}
            <span className="text-amber-200" data-testid="audit-root-cause-sticky-cause">
              {rootCauseSummary}
            </span>
            {" "}• Aksiyon:{" "}
            <span className="text-emerald-200" data-testid="audit-root-cause-sticky-action">
              {actionSuggestion}
            </span>
          </p>
        </div>
        <div className="mb-3 flex flex-wrap gap-2" data-testid="audit-logs-copy-tools">
          <Button variant="outline" size="sm" onClick={onCopyFullTrace} data-testid="audit-copy-full-trace-button">Copy full trace</Button>
          <Button variant="outline" size="sm" onClick={onCopyCorrelationChain} data-testid="audit-copy-correlation-chain-button">Copy correlation chain</Button>
          <Button variant="outline" size="sm" onClick={onCopySelectedEventJson} data-testid="audit-copy-event-json-button">Copy event JSON</Button>
          <Button variant="outline" size="sm" onClick={onCopyReplayInput} data-testid="audit-copy-replay-input-button">Copy replay input</Button>
          <Button variant="secondary" size="sm" onClick={fetchCrossEnvironmentComparison} disabled={!selectedCorrelation} data-testid="audit-cross-env-compare-button">Cross-env compare</Button>
          <Button variant="secondary" size="sm" onClick={verifyIntegrity} disabled={!selectedCorrelation} data-testid="audit-verify-integrity-button">Verify integrity</Button>
        </div>
        <p className="mb-2 text-xs text-slate-400" data-testid="audit-selected-event-id">selected_event_id: {selectedEventId || "-"}</p>
        <div className="h-[360px] overflow-hidden rounded-xl border border-slate-700" data-testid="audit-logs-reactflow-wrap">
          {viewMode === "graph" ? (
            <ReactFlow
              nodes={graphData.nodes}
              edges={graphData.edges}
              fitView
              onNodeClick={(_, node) => setSelectedEventId(node.id)}
              data-testid="audit-logs-reactflow"
            >
              <Background />
              <MiniMap pannable zoomable data-testid="audit-logs-reactflow-minimap" />
              <Controls data-testid="audit-logs-reactflow-controls" />
            </ReactFlow>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-slate-400" data-testid="audit-logs-graph-hidden-note">
              Graph görünümü pasif. "Graph View" ile aktif edin.
            </div>
          )}
        </div>
      </div>

      {viewMode === "table" && (
        <div
          className="max-h-[360px] overflow-y-auto rounded-2xl border border-slate-800"
          data-testid="audit-logs-table-wrap"
          onScroll={(event) => {
            const node = event.currentTarget;
            if (node.scrollTop + node.clientHeight >= node.scrollHeight - 24) {
              setVisibleCount((prev) => Math.min(prev + 30, items.length));
            }
          }}
        >
          <Table data-testid="audit-logs-table">
          <TableHeader>
            <TableRow>
              <TableHead>Correlation</TableHead>
              <TableHead>Window</TableHead>
              <TableHead>Chain</TableHead>
              <TableHead>Pattern</TableHead>
              <TableHead>Orphan</TableHead>
              <TableHead>Missing stages</TableHead>
              <TableHead>Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={7} className="py-8 text-center text-slate-300" data-testid="audit-logs-table-loading">yükleniyor...</TableCell>
              </TableRow>
            ) : items.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="py-8 text-center text-slate-400" data-testid="audit-logs-table-empty">kayıt yok</TableCell>
              </TableRow>
            ) : (
              renderedItems.map((item, index) => {
                const sev = item.has_error || item.broken_chain ? "critical" : item.trace_incomplete ? "warning" : "info";
                return (
                  <TableRow key={item.correlation_id} data-testid={`audit-logs-row-${index}`}>
                    <TableCell data-testid={`audit-logs-row-id-${index}`}>{item.correlation_id}</TableCell>
                    <TableCell data-testid={`audit-logs-row-time-${index}`}>{item.started_at} → {item.ended_at}</TableCell>
                    <TableCell data-testid={`audit-logs-row-severity-${index}`}>
                      <span className={`rounded-full px-2 py-1 text-xs font-semibold ${severityClass[sev]}`}>{item.broken_chain ? "BROKEN" : "VALID"}</span>
                    </TableCell>
                    <TableCell data-testid={`audit-logs-row-pattern-${index}`}>{item.pattern_tag || "-"}</TableCell>
                    <TableCell data-testid={`audit-logs-row-action-${index}`}>{item.orphan_count}</TableCell>
                    <TableCell data-testid={`audit-logs-row-entity-${index}`}>{(item.missing_critical_stages || []).join(", ") || "none"}</TableCell>
                    <TableCell data-testid={`audit-logs-row-actor-${index}`}>
                      <Button size="sm" variant="outline" onClick={() => openLifecycle(item.correlation_id)} data-testid={`audit-open-full-lifecycle-button-${index}`}>
                        Open full lifecycle
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
          </Table>
        </div>
      )}

      <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4" data-testid="audit-replay-panel">
        <h3 className="text-lg font-bold text-slate-200" data-testid="audit-replay-title">Open full lifecycle</h3>
        <p className="text-xs text-slate-400" data-testid="audit-replay-subtitle">seçili correlation: {selectedCorrelation || "-"}</p>
        <div className="mt-3 flex flex-wrap gap-2" data-testid="audit-replay-controls">
          <Button onClick={explainFailure} disabled={!selectedCorrelation || detailLoading} data-testid="audit-explain-failure-button">
            <AlertTriangle className="mr-1 h-4 w-4" /> Explain Failure
          </Button>
          <Button onClick={runReplay} disabled={!selectedCorrelation || detailLoading} variant="secondary" data-testid="audit-replay-run-button">
            <BugPlay className="mr-1 h-4 w-4" /> Replay
          </Button>
          <Button
            onClick={createIncident}
            disabled={!selectedCorrelation || detailLoading}
            variant="outline"
            data-testid="audit-create-incident-button"
          >
            Create Incident
          </Button>
        </div>

        {!!detail && (
          <div className="mt-4 overflow-x-auto" data-testid="audit-detail-events-wrap">
            <div className="mb-3 flex flex-wrap gap-3 text-xs text-slate-300" data-testid="audit-detail-chain-indicators">
              <span data-testid="audit-detail-broken-chain-indicator">broken_chain: {String(Boolean(detail?.broken_chain))}</span>
              <span data-testid="audit-detail-trace-incomplete-indicator">trace_incomplete: {String(Boolean(detail?.trace_incomplete))}</span>
              <span data-testid="audit-detail-missing-stages-indicator">
                missing_stages: {(detail?.missing_critical_stages || []).join(", ") || "none"}
              </span>
            </div>
            <Table data-testid="audit-detail-events-table">
              <TableHeader>
                <TableRow>
                  <TableHead>#</TableHead>
                  <TableHead>event_type</TableHead>
                  <TableHead>stage</TableHead>
                  <TableHead>severity</TableHead>
                  <TableHead>parent</TableHead>
                  <TableHead>relation</TableHead>
                  <TableHead>payload</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {events.map((event, index) => (
                  <Fragment key={event.event_id}>
                    <TableRow
                      data-testid={`audit-detail-event-row-${index}`}
                      onClick={() => setSelectedEventId(event.event_id)}
                    >
                      <TableCell data-testid={`audit-detail-event-index-${index}`}>{event.causal_index}</TableCell>
                      <TableCell data-testid={`audit-detail-event-type-${index}`}>{event.event_type}</TableCell>
                      <TableCell data-testid={`audit-detail-event-stage-${index}`}>{event.lifecycle_stage}</TableCell>
                      <TableCell data-testid={`audit-detail-event-severity-${index}`}>{event.severity}</TableCell>
                      <TableCell data-testid={`audit-detail-event-parent-${index}`}>{event.parent_event_id || "-"}</TableCell>
                      <TableCell data-testid={`audit-detail-event-relation-${index}`}>{event.relation_status}</TableCell>
                      <TableCell data-testid={`audit-detail-event-payload-toggle-${index}`}>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={(clickEvent) => {
                            clickEvent.stopPropagation();
                            setExpandedEventRows((prev) => ({ ...prev, [event.event_id]: !prev[event.event_id] }));
                          }}
                          data-testid={`audit-detail-event-expand-button-${index}`}
                        >
                          {expandedEventRows[event.event_id] ? "Collapse" : "Expand JSON"}
                        </Button>
                      </TableCell>
                    </TableRow>
                    {expandedEventRows[event.event_id] && (
                      <TableRow data-testid={`audit-detail-event-json-row-${index}`}>
                        <TableCell colSpan={7}>
                          <pre className="max-h-64 overflow-auto rounded bg-slate-950 p-3 text-xs text-emerald-200" data-testid={`audit-detail-event-json-${index}`}>
                            {JSON.stringify(event.payload || {}, null, 2)}
                          </pre>
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        {!!failureExplanation && (
          <div className="mt-4 rounded-lg border border-amber-800/40 bg-amber-950/20 p-3" data-testid="audit-failure-explanation-panel">
            <p className="text-sm text-amber-100" data-testid="audit-failure-root-cause">root_cause: {failureExplanation.root_cause || "unknown"}</p>
            <p className="text-sm text-amber-100" data-testid="audit-failure-broken-step">broken_step: {failureExplanation.broken_step || "-"}</p>
            <p className="text-sm text-amber-100" data-testid="audit-failure-upstream">upstream: {failureExplanation.upstream_event || "-"}</p>
            <p className="text-sm text-amber-100" data-testid="audit-failure-downstream">downstream: {(failureExplanation.downstream_impact || []).length}</p>
            <p className="text-sm text-amber-100" data-testid="audit-failure-confidence">confidence: {failureExplanation.confidence || "low"}</p>
            <p className="text-sm text-amber-100" data-testid="audit-failure-insufficient-data">insufficient_data: {String(Boolean(failureExplanation.insufficient_data))}</p>
          </div>
        )}

        {!!rootCauseBreakdown && (
          <div className="mt-4 rounded-lg border border-rose-800/40 bg-rose-950/20 p-3" data-testid="audit-root-cause-breakdown-panel">
            <p className="text-sm text-rose-100" data-testid="audit-root-cause-breakdown-type">failure_type: {rootCauseBreakdown.failure_type || "-"}</p>
            <p className="text-sm text-rose-100" data-testid="audit-root-cause-breakdown-pattern">pattern_tag: {rootCauseBreakdown.pattern_tag || "-"}</p>
            <p className="text-sm text-rose-100" data-testid="audit-root-cause-breakdown-cluster">cluster_id: {rootCauseBreakdown.cluster_id || "-"}</p>
            <p className="text-sm text-rose-100" data-testid="audit-root-cause-breakdown-reasons">reason_codes: {(rootCauseBreakdown.reason_codes || []).join(", ") || "none"}</p>
            <p className="text-sm text-rose-100" data-testid="audit-root-cause-breakdown-blockers">critical_blockers: {(rootCauseBreakdown.critical_blockers || []).join(", ") || "none"}</p>
            <p className="text-sm text-rose-100" data-testid="audit-root-cause-breakdown-anomaly">anomaly_detected: {String(Boolean(rootCauseBreakdown.anomaly_detected))}</p>
            <p className="text-sm text-rose-100" data-testid="audit-root-cause-breakdown-anomaly-reasons">anomaly_reasons: {(rootCauseBreakdown.anomaly_reasons || []).join(", ") || "none"}</p>
          </div>
        )}

        {!!replayResult && (
          <div className="mt-4 rounded-lg border border-cyan-800/40 bg-cyan-950/20 p-3" data-testid="audit-replay-result-panel">
            <p className="text-sm text-cyan-100" data-testid="audit-replay-result-status">result: {replayResult.result}</p>
            <p className="text-sm text-cyan-100" data-testid="audit-replay-result-break-step">break_step: {replayResult.break_step?.event_type || "none"}</p>
            <p className="text-sm text-cyan-100" data-testid="audit-replay-result-side-effects">side_effects_blocked: {String(replayResult.side_effects_blocked)}</p>
          </div>
        )}

        {!!crossEnvComparison?.environments && (
          <div className="mt-4 rounded-lg border border-indigo-800/40 bg-indigo-950/20 p-3" data-testid="audit-cross-env-comparison-panel">
            <p className="text-sm font-semibold text-indigo-100" data-testid="audit-cross-env-comparison-title">Cross-environment comparison</p>
            <div className="mt-2 grid gap-2 md:grid-cols-2" data-testid="audit-cross-env-comparison-grid">
              {Object.entries(crossEnvComparison.environments).map(([environment, info]) => (
                <div key={environment} className="rounded border border-indigo-700/40 p-2" data-testid={`audit-cross-env-item-${environment}`}>
                  <p className="text-xs text-indigo-200">{environment}</p>
                  <p className="text-xs text-indigo-100">event_count: {info?.event_count || 0}</p>
                  <p className="text-xs text-indigo-100">broken_chain: {String(Boolean(info?.broken_chain))}</p>
                  <p className="text-xs text-indigo-100">trace_incomplete: {String(Boolean(info?.trace_incomplete))}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {!!integrityResult && (
          <div className="mt-4 rounded-lg border border-emerald-800/40 bg-emerald-950/20 p-3" data-testid="audit-integrity-panel">
            <p className="text-sm text-emerald-100" data-testid="audit-integrity-status">tampered: {String(Boolean(integrityResult.tampered))}</p>
            <p className="text-sm text-emerald-100" data-testid="audit-integrity-events-checked">events_checked: {integrityResult.events_checked || 0}</p>
            <p className="text-sm text-emerald-100" data-testid="audit-integrity-mismatch-count">mismatch_count: {integrityResult.mismatch_count || 0}</p>
          </div>
        )}

        <div className="mt-4 rounded-lg border border-slate-800 bg-slate-900/40 p-3" data-testid="audit-incident-list-panel">
          <p className="text-sm font-semibold text-slate-200" data-testid="audit-incident-list-title">Linked incidents</p>
          {incidents.length === 0 ? (
            <p className="mt-2 text-sm text-slate-400" data-testid="audit-incident-list-empty">incident yok</p>
          ) : (
            <div className="mt-2 space-y-2" data-testid="audit-incident-list-items">
              {incidents.map((incident, idx) => (
                <div key={incident.incident_id} className="flex flex-wrap items-center justify-between gap-3 rounded border border-slate-700 px-3 py-2" data-testid={`audit-incident-item-${idx}`}>
                  <div className="space-y-1">
                    <p className="text-sm text-slate-200" data-testid={`audit-incident-item-id-${idx}`}>{incident.incident_id}</p>
                    <p className="text-xs text-slate-400" data-testid={`audit-incident-item-meta-${idx}`}>
                      {incident.severity} • {incident.status} • auto_created={String(Boolean(incident.auto_created))}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => exportIncidentBundle(incident.incident_id)}
                      data-testid={`audit-incident-export-button-${idx}`}
                    >
                      Export Bundle
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={incident.status === "closed"}
                      onClick={() => closeIncident(incident.incident_id)}
                      data-testid={`audit-incident-close-button-${idx}`}
                    >
                      Close
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
};
