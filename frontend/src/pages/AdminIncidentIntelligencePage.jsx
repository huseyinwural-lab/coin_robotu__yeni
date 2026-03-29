import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Play, RefreshCw, ShieldAlert, Sparkles, Workflow } from "lucide-react";
import { toast } from "sonner";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Background, Controls, MiniMap, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { apiClient, FRONTEND_BACKEND_URL, getSessionDeviceId } from "@/lib/api";

const severityTone = {
  CRITICAL: "border-l-red-600 bg-red-50 text-red-900",
  ERROR: "border-l-orange-500 bg-orange-50 text-orange-900",
  WARNING: "border-l-amber-500 bg-amber-50 text-amber-900",
  INFO: "border-l-blue-500 bg-blue-50 text-blue-900",
};

const streamUrl = () => {
  const base = FRONTEND_BACKEND_URL.replace(/\/$/, "");
  if (!base) return "";
  if (base.startsWith("https://")) return `${base.replace("https://", "wss://")}/api/incident-intelligence/ws/stream`;
  if (base.startsWith("http://")) return `${base.replace("http://", "ws://")}/api/incident-intelligence/ws/stream`;
  return "";
};

const buildGraphNodes = (nodes = []) =>
  nodes.map((node, index) => ({
    id: node.id,
    position: { x: (index % 4) * 220, y: Math.floor(index / 4) * 120 },
    data: { label: `${node.type || "node"}\n${node.id}` },
    style: { borderRadius: 2, border: "1px solid #111827", background: "#fff", padding: 8, width: 170, fontSize: 11 },
  }));

const buildGraphEdges = (edges = []) =>
  edges.map((edge, index) => ({
    id: `${edge.source}-${edge.target}-${index}`,
    source: edge.source,
    target: edge.target,
    label: edge.relation,
    style: { stroke: "#111827" },
    labelStyle: { fontSize: 10, fill: "#374151" },
  }));

export const AdminIncidentIntelligencePage = () => {
  const navigate = useNavigate();
  const [streamState, setStreamState] = useState("connecting");
  const [anomalies, setAnomalies] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [selectedIncidentId, setSelectedIncidentId] = useState("");
  const [incidentDetail, setIncidentDetail] = useState(null);
  const [kpis, setKpis] = useState(null);
  const [weeklySummary, setWeeklySummary] = useState(null);
  const [graph, setGraph] = useState({ nodes: [], edges: [] });
  const [predictions, setPredictions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState("");
  const [liveActionSymbol, setLiveActionSymbol] = useState("BTCUSDT");
  const [liveTargetLeverage, setLiveTargetLeverage] = useState("1");
  const socketRef = useRef(null);

  const selectedIncident = useMemo(
    () => incidents.find((item) => item.incident_id === selectedIncidentId) || incidents[0] || null,
    [incidents, selectedIncidentId],
  );

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    try {
      const [anomalyRes, incidentRes, kpiRes, weeklyRes, graphRes, predictionRes] = await Promise.all([
        apiClient.get("/admin/incident-intelligence/anomalies"),
        apiClient.get("/admin/incident-intelligence/incidents"),
        apiClient.get("/admin/incident-intelligence/kpis"),
        apiClient.get("/admin/incident-intelligence/weekly-summary"),
        apiClient.get("/admin/incident-intelligence/graph"),
        apiClient.get("/admin/incident-intelligence/predictions"),
      ]);
      const nextIncidents = incidentRes.data?.items || [];
      setAnomalies(anomalyRes.data?.items || []);
      setIncidents(nextIncidents);
      setKpis(kpiRes.data || null);
      setWeeklySummary(weeklyRes.data || null);
      setGraph(graphRes.data || { nodes: [], edges: [] });
      setPredictions(predictionRes.data?.items || []);
      setSelectedIncidentId((prev) => prev || nextIncidents[0]?.incident_id || "");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Incident intelligence verisi alınamadı");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadIncidentDetail = useCallback(async (incidentId) => {
    if (!incidentId) return;
    try {
      const { data } = await apiClient.get(`/admin/incident-intelligence/incidents/${encodeURIComponent(incidentId)}`);
      setIncidentDetail(data || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Incident detayı alınamadı");
    }
  }, []);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  useEffect(() => {
    if (selectedIncidentId) {
      loadIncidentDetail(selectedIncidentId);
    }
  }, [loadIncidentDetail, selectedIncidentId]);

  useEffect(() => {
    const token = window.localStorage.getItem("token");
    const url = streamUrl();
    if (!token || !url) return undefined;
    let reconnectTimer = null;
    let socket = null;

    const connect = () => {
      const deviceId = getSessionDeviceId();
      socket = new WebSocket(`${url}?token=${encodeURIComponent(token)}&device_id=${encodeURIComponent(deviceId)}`);
      socketRef.current = socket;
      socket.onopen = () => setStreamState("connected");
      socket.onclose = () => {
        setStreamState("disconnected");
        reconnectTimer = window.setTimeout(connect, 2000);
      };
      socket.onerror = () => setStreamState("error");
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (["incident_stream_bootstrap", "incident_intelligence_snapshot"].includes(payload.event_type)) {
            loadDashboard();
            if (selectedIncidentId) {
              loadIncidentDetail(selectedIncidentId);
            }
          }
        } catch {
          setStreamState("error");
        }
      };
    };

    connect();
    const heartbeat = window.setInterval(() => {
      if (socket && socket.readyState === WebSocket.OPEN) socket.send("ping");
    }, 15000);
    return () => {
      window.clearInterval(heartbeat);
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
      }
      if (socket) {
        socket.close();
      }
    };
  }, [loadDashboard, loadIncidentDetail, selectedIncidentId]);

  const runEngine = useCallback(async () => {
    setActionLoading("run-engine");
    try {
      await apiClient.post("/admin/incident-intelligence/engine/run?window_minutes=15");
      toast.success("Incident intelligence cycle çalıştırıldı");
      await loadDashboard();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Engine run başarısız");
    } finally {
      setActionLoading("");
    }
  }, [loadDashboard]);

  const triggerAction = useCallback(async (action) => {
    if (!selectedIncident?.incident_id) return;
    setActionLoading(action);
    try {
      await apiClient.post(`/admin/incident-intelligence/incidents/${encodeURIComponent(selectedIncident.incident_id)}/actions`, { action, mode: "manual" });
      toast.success(`${action} aksiyonu tetiklendi`);
      await loadDashboard();
      await loadIncidentDetail(selectedIncident.incident_id);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Aksiyon tetiklenemedi");
    } finally {
      setActionLoading("");
    }
  }, [loadDashboard, loadIncidentDetail, selectedIncident?.incident_id]);

  const updateState = useCallback(async (state) => {
    if (!selectedIncident?.incident_id) return;
    setActionLoading(state);
    try {
      await apiClient.patch(`/admin/incident-intelligence/incidents/${encodeURIComponent(selectedIncident.incident_id)}`, { state, owner: selectedIncident.owner || "ops", note: `ui_${state.toLowerCase()}` });
      toast.success(`Incident state → ${state}`);
      await loadDashboard();
      await loadIncidentDetail(selectedIncident.incident_id);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Incident state güncellenemedi");
    } finally {
      setActionLoading("");
    }
  }, [loadDashboard, loadIncidentDetail, selectedIncident?.incident_id, selectedIncident?.owner]);

  const runControlledLiveAction = useCallback(async (action, mode, parameters = {}) => {
    if (!selectedIncident?.incident_id) return;
    setActionLoading(`${action}-${mode}`);
    try {
      const { data } = await apiClient.post(`/admin/incident-intelligence/incidents/${encodeURIComponent(selectedIncident.incident_id)}/actions`, {
        action,
        mode,
        parameters,
        reason: `operator_${mode}_${action}`,
      });
      const actionResult = data?.action_result || {};
      const preview = actionResult.external_preview;
      const live = actionResult.external_live_result;
      if (preview) {
        toast.success(`Dry-run tamamlandı · open_orders=${preview.open_order_count ?? 0}`);
      } else if (live) {
        toast.success(`${action} live uygulandı`);
      } else {
        toast.success(`${action} tetiklendi`);
      }
      await loadDashboard();
      await loadIncidentDetail(selectedIncident.incident_id);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Controlled action başarısız");
    } finally {
      setActionLoading("");
    }
  }, [loadDashboard, loadIncidentDetail, selectedIncident?.incident_id]);

  const rollbackLastAction = useCallback(async () => {
    if (!selectedIncident?.incident_id) return;
    setActionLoading("rollback");
    try {
      await apiClient.post(`/admin/incident-intelligence/incidents/${encodeURIComponent(selectedIncident.incident_id)}/actions/rollback`);
      toast.success("Son aksiyon rollback edildi");
      await loadDashboard();
      await loadIncidentDetail(selectedIncident.incident_id);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Rollback başarısız");
    } finally {
      setActionLoading("");
    }
  }, [loadDashboard, loadIncidentDetail, selectedIncident?.incident_id]);

  const frequencyChartData = useMemo(
    () => (weeklySummary?.top_root_causes || []).map(([label, value]) => ({ label, value })),
    [weeklySummary],
  );

  return (
    <section className="space-y-4 bg-[#f9fafb] text-slate-900" data-testid="incident-intelligence-page">
      <header className="border border-slate-300 bg-white px-5 py-4" data-testid="incident-intelligence-header">
        <div className="flex flex-wrap items-start justify-between gap-4" data-testid="incident-intelligence-header-row">
          <div data-testid="incident-intelligence-header-copy">
            <p className="text-xs uppercase tracking-[0.25em] text-slate-500" data-testid="incident-intelligence-header-kicker">Incident Intelligence Core</p>
            <h1 className="mt-1 text-3xl font-black tracking-tight" data-testid="incident-intelligence-header-title">Operator Center</h1>
            <p className="mt-1 text-sm text-slate-600" data-testid="incident-intelligence-header-description">Canlı incident stream, root cause, impact, aksiyon ve trendler tek ekranda.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2" data-testid="incident-intelligence-header-actions">
            <span className="border border-slate-300 bg-slate-50 px-3 py-2 font-mono text-xs uppercase tracking-[0.2em]" data-testid="incident-intelligence-stream-state-badge">stream:{streamState}</span>
            <Button variant="outline" onClick={loadDashboard} data-testid="incident-intelligence-refresh-button"><RefreshCw className="mr-2 h-4 w-4" />Yenile</Button>
            <Button onClick={runEngine} disabled={actionLoading === "run-engine"} data-testid="incident-intelligence-run-engine-button"><Play className="mr-2 h-4 w-4" />Cycle Run</Button>
          </div>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-4" data-testid="incident-intelligence-kpi-grid">
          {[
            ["incident_count", kpis?.incident_count ?? 0],
            ["mttd_seconds", Math.round(kpis?.mttd_seconds ?? 0)],
            ["mttr_seconds", Math.round(kpis?.mttr_seconds ?? 0)],
            ["repeat_rate", kpis?.repeat_incident_rate ?? 0],
          ].map(([label, value]) => (
            <div key={label} className="border border-slate-300 bg-slate-50 p-3" data-testid={`incident-intelligence-kpi-card-${label}`}>
              <p className="text-[11px] uppercase tracking-[0.2em] text-slate-500" data-testid={`incident-intelligence-kpi-label-${label}`}>{label}</p>
              <p className="mt-2 font-mono text-2xl font-semibold" data-testid={`incident-intelligence-kpi-value-${label}`}>{value}</p>
            </div>
          ))}
        </div>
      </header>

      <div className="grid gap-4 xl:grid-cols-12" data-testid="incident-intelligence-main-grid">
        <aside className="space-y-3 xl:col-span-3" data-testid="incident-intelligence-stream-column">
          <div className="border border-slate-300 bg-white" data-testid="incident-intelligence-stream-panel">
            <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3" data-testid="incident-intelligence-stream-header">
              <h2 className="text-sm font-bold uppercase tracking-[0.2em]" data-testid="incident-intelligence-stream-title">Incident Stream</h2>
              <span className="font-mono text-xs" data-testid="incident-intelligence-stream-count">{incidents.length}</span>
            </div>
            <div className="max-h-[720px] overflow-y-auto" data-testid="incident-intelligence-stream-list">
              {incidents.map((incident, index) => (
                <button
                  key={incident.incident_id}
                  type="button"
                  onClick={() => setSelectedIncidentId(incident.incident_id)}
                  className={`block w-full border-b border-slate-200 border-l-4 px-4 py-3 text-left transition ${severityTone[incident.severity] || severityTone.INFO} ${selectedIncident?.incident_id === incident.incident_id ? "ring-1 ring-slate-900" : ""}`}
                  data-testid={`incident-intelligence-stream-item-${index}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-semibold" data-testid={`incident-intelligence-stream-item-title-${index}`}>{incident.title}</p>
                    <span className="font-mono text-[11px] uppercase tracking-[0.2em]" data-testid={`incident-intelligence-stream-item-state-${index}`}>{incident.state}</span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-600">
                    <span data-testid={`incident-intelligence-stream-item-severity-${index}`}>{incident.severity}</span>
                    <span data-testid={`incident-intelligence-stream-item-domain-${index}`}>{incident.evidence?.linked_events?.[0]?.split?.(":")?.[0] || incident.root_cause || "incident"}</span>
                    <span data-testid={`incident-intelligence-stream-item-owner-${index}`}>{incident.owner || "unassigned"}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div className="border border-slate-300 bg-white p-4" data-testid="incident-intelligence-trend-panel">
            <div className="flex items-center gap-2" data-testid="incident-intelligence-trend-header"><Sparkles className="h-4 w-4" /><h3 className="text-sm font-bold uppercase tracking-[0.2em]">Incident Trend</h3></div>
            <div className="mt-3 h-56" data-testid="incident-intelligence-trend-chart-wrap">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={frequencyChartData}>
                  <CartesianGrid stroke="#e5e7eb" vertical={false} />
                  <XAxis dataKey="label" tick={{ fontSize: 10 }} hide={frequencyChartData.length > 5} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Bar dataKey="value" fill="#111827" />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-3 space-y-2" data-testid="incident-intelligence-predictions-list">
              {(predictions || []).slice(0, 4).map((item, index) => (
                <div key={`${item.fingerprint}-${index}`} className="border border-slate-200 p-2 text-xs" data-testid={`incident-intelligence-prediction-item-${index}`}>
                  <p className="font-mono" data-testid={`incident-intelligence-prediction-risk-${index}`}>{item.predicted_risk} · {item.risk_trend}</p>
                  <p data-testid={`incident-intelligence-prediction-root-cause-${index}`}>{item.root_cause}</p>
                </div>
              ))}
            </div>
          </div>
        </aside>

        <div className="space-y-4 xl:col-span-5" data-testid="incident-intelligence-center-column">
          <div className="border border-slate-300 bg-white p-4" data-testid="incident-intelligence-root-cause-panel">
            <div className="flex items-center gap-2" data-testid="incident-intelligence-root-cause-header"><Workflow className="h-4 w-4" /><h3 className="text-sm font-bold uppercase tracking-[0.2em]">Root Cause</h3></div>
            <p className="mt-3 text-lg font-bold" data-testid="incident-intelligence-root-cause-value">{selectedIncident?.root_cause || "-"}</p>
            <p className="mt-2 font-mono text-3xl text-emerald-700" data-testid="incident-intelligence-root-cause-confidence">{selectedIncident?.confidence_score ?? 0}</p>
            <p className="mt-2 text-xs uppercase tracking-[0.2em] text-slate-500" data-testid="incident-intelligence-root-cause-correlation">correlation_sources: {(selectedIncident?.evidence?.linked_events || []).length}</p>
          </div>

          <div className="border border-slate-300 bg-white p-4" data-testid="incident-intelligence-impact-panel">
            <div className="flex items-center gap-2"><ShieldAlert className="h-4 w-4" /><h3 className="text-sm font-bold uppercase tracking-[0.2em]" data-testid="incident-intelligence-impact-title">Impact</h3></div>
            <div className="mt-3 grid gap-3 sm:grid-cols-3">
              {[["pnl", selectedIncident?.impact?.pnl], ["exposure", selectedIncident?.impact?.exposure], ["availability", selectedIncident?.impact?.availability]].map(([label, value]) => (
                <div key={label} className="border border-slate-200 p-3" data-testid={`incident-intelligence-impact-card-${label}`}>
                  <p className="text-[11px] uppercase tracking-[0.2em] text-slate-500">{label}</p>
                  <p className="mt-2 font-mono text-2xl" data-testid={`incident-intelligence-impact-value-${label}`}>{value ?? 0}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="border border-slate-300 bg-white p-4" data-testid="incident-intelligence-timeline-panel">
            <div className="flex items-center justify-between gap-2"><h3 className="text-sm font-bold uppercase tracking-[0.2em]" data-testid="incident-intelligence-timeline-title">Timeline View</h3>{selectedIncident?.incident_id && <Button variant="outline" onClick={() => navigate(`/admin/incident-intelligence/${selectedIncident.incident_id}`)} data-testid="incident-intelligence-open-detail-button">Detay Sayfası <ArrowRight className="ml-2 h-4 w-4" /></Button>}</div>
            <div className="mt-4 space-y-3" data-testid="incident-intelligence-timeline-list">
              {((incidentDetail?.timeline?.chain) || []).map((item, index) => (
                <div key={`${item.kind}-${item.id}-${index}`} className="grid grid-cols-[18px_1fr] gap-3" data-testid={`incident-intelligence-timeline-item-${index}`}>
                  <div className="flex flex-col items-center"><span className="h-3 w-3 rounded-full bg-slate-900" /><span className="min-h-[44px] w-px bg-slate-200" /></div>
                  <div className="border border-slate-200 p-3">
                    <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-slate-500" data-testid={`incident-intelligence-timeline-kind-${index}`}>{item.kind}</p>
                    <p className="mt-1 text-sm font-semibold" data-testid={`incident-intelligence-timeline-id-${index}`}>{item.id}</p>
                    <p className="mt-1 font-mono text-xs text-slate-500" data-testid={`incident-intelligence-timeline-timestamp-${index}`}>{item.timestamp || "-"}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <aside className="space-y-4 xl:col-span-4" data-testid="incident-intelligence-action-column">
          <div className="border border-slate-300 bg-white p-4" data-testid="incident-intelligence-action-panel">
            <h3 className="text-sm font-bold uppercase tracking-[0.2em]" data-testid="incident-intelligence-action-title">Action Panel</h3>
            <div className="mt-3 flex flex-wrap gap-2" data-testid="incident-intelligence-action-buttons">
              {(selectedIncident?.suggested_actions || []).map((action, index) => (
                <Button key={`${action}-${index}`} variant={action === "block_trading" ? "destructive" : "outline"} onClick={() => triggerAction(action === "inspect_reconcile" ? "reconcile_trigger" : action)} disabled={!!actionLoading} data-testid={`incident-intelligence-trigger-action-${action}`}>{action}</Button>
              ))}
              <Button variant="outline" onClick={() => updateState("INVESTIGATING")} disabled={!!actionLoading} data-testid="incident-intelligence-set-investigating-button">Investigating</Button>
              <Button variant="outline" onClick={() => updateState("RESOLVED")} disabled={!!actionLoading} data-testid="incident-intelligence-set-resolved-button">Resolved</Button>
              <Button variant="outline" onClick={() => updateState("FALSE_POSITIVE")} disabled={!!actionLoading} data-testid="incident-intelligence-set-false-positive-button">False Positive</Button>
            </div>
            <div className="mt-4 grid gap-2 border border-slate-200 p-3" data-testid="incident-intelligence-live-action-controls">
              <p className="text-[11px] uppercase tracking-[0.2em] text-slate-500" data-testid="incident-intelligence-live-action-kicker">Controlled External Action</p>
              <div className="grid gap-2 sm:grid-cols-2">
                <input value={liveActionSymbol} onChange={(event) => setLiveActionSymbol(event.target.value.toUpperCase())} className="border border-slate-300 px-3 py-2 text-sm" data-testid="incident-intelligence-live-symbol-input" />
                <input value={liveTargetLeverage} onChange={(event) => setLiveTargetLeverage(event.target.value)} className="border border-slate-300 px-3 py-2 text-sm" data-testid="incident-intelligence-live-leverage-input" />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" disabled={!!actionLoading} onClick={() => runControlledLiveAction("block_trading", "dry_run")} data-testid="incident-intelligence-live-block-preview-button">Preview Block</Button>
                <Button disabled={!!actionLoading} onClick={() => runControlledLiveAction("block_trading", "manual_live")} data-testid="incident-intelligence-live-block-apply-button">Apply Live Block</Button>
                <Button variant="outline" disabled={!!actionLoading} onClick={() => runControlledLiveAction("reduce_leverage", "dry_run", { symbol: liveActionSymbol, target_leverage: Number(liveTargetLeverage || 1) })} data-testid="incident-intelligence-live-leverage-preview-button">Preview Leverage</Button>
                <Button variant="outline" disabled={!!actionLoading} onClick={rollbackLastAction} data-testid="incident-intelligence-live-rollback-button">Rollback Last Action</Button>
              </div>
            </div>
            <div className="mt-4 space-y-2" data-testid="incident-intelligence-action-history-list">
              {(selectedIncident?.remediation_history || []).map((entry, index) => (
                <div key={`${entry.action}-${index}`} className="border border-slate-200 p-2 text-xs" data-testid={`incident-intelligence-action-history-item-${index}`}>
                  <p className="font-mono" data-testid={`incident-intelligence-action-history-action-${index}`}>{entry.action}</p>
                  <p data-testid={`incident-intelligence-action-history-status-${index}`}>{entry.status}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="border border-slate-300 bg-white p-4" data-testid="incident-intelligence-graph-panel">
            <h3 className="text-sm font-bold uppercase tracking-[0.2em]" data-testid="incident-intelligence-graph-title">Correlation Graph</h3>
            <div className="mt-3 h-[320px] border border-slate-200" data-testid="incident-intelligence-graph-canvas">
              <ReactFlow nodes={buildGraphNodes(graph.nodes)} edges={buildGraphEdges(graph.edges)} fitView>
                <MiniMap />
                <Controls />
                <Background color="#e5e7eb" gap={18} />
              </ReactFlow>
            </div>
          </div>
        </aside>
      </div>

      {loading && <p className="font-mono text-xs text-slate-500" data-testid="incident-intelligence-loading-state">loading...</p>}
    </section>
  );
};

export default AdminIncidentIntelligencePage;