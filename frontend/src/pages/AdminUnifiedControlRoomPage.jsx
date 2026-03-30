import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

const monoBox = "overflow-x-auto bg-slate-50 p-2 text-[11px] text-slate-700";
const card = "border border-slate-300 bg-white p-4";

const pretty = (value) => JSON.stringify(value || {}, null, 2);

export default function AdminUnifiedControlRoomPage() {
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [windowRange, setWindowRange] = useState("7d");
  const [selectedIncidentId, setSelectedIncidentId] = useState("");
  const [selectedRecommendationId, setSelectedRecommendationId] = useState("");
  const [incidentReason, setIncidentReason] = useState("control_room_preview");
  const [learningReason, setLearningReason] = useState("control_room_learning_action");
  const [actionLoading, setActionLoading] = useState("");

  const loadOverview = async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/admin/unified-control-room/overview", { params: { window: windowRange } });
      setOverview(data || null);
      setSelectedIncidentId((prev) => prev || data?.live_operations?.incidents?.[0]?.incident_id || "");
      setSelectedRecommendationId((prev) => prev || data?.learning_adaptation?.actionable_recommendations?.[0]?.id || "");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Unified control room yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadOverview();
  }, [windowRange]);

  const selectedIncident = useMemo(
    () => overview?.live_operations?.incidents?.find((item) => item.incident_id === selectedIncidentId) || overview?.live_operations?.incidents?.[0] || null,
    [overview, selectedIncidentId],
  );
  const selectedRecommendation = useMemo(
    () => overview?.learning_adaptation?.actionable_recommendations?.find((item) => item.id === selectedRecommendationId) || overview?.learning_adaptation?.actionable_recommendations?.[0] || null,
    [overview, selectedRecommendationId],
  );

  const previewIncidentAction = async () => {
    if (!selectedIncident?.incident_id) return;
    setActionLoading("incident-preview");
    try {
      await apiClient.post(`/admin/incident-intelligence/incidents/${selectedIncident.incident_id}/actions`, {
        action: "block_trading",
        mode: "dry_run",
        reason: incidentReason,
      });
      toast.success("Incident preview action çalıştırıldı");
      await loadOverview();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Incident preview action başarısız");
    } finally {
      setActionLoading("");
    }
  };

  const runLearningAction = async (action) => {
    if (!selectedRecommendation?.id) return;
    setActionLoading(`learning-${action}`);
    try {
      await apiClient.post(`/admin/learning/recommendations/${selectedRecommendation.id}/${action}`, { reason: learningReason });
      toast.success(`Learning ${action} tamamlandı`);
      await loadOverview();
    } catch (error) {
      toast.error(error?.response?.data?.detail || `Learning ${action} başarısız`);
    } finally {
      setActionLoading("");
    }
  };

  return (
    <section className="space-y-4 bg-[#F9FAFB] text-slate-900" data-testid="unified-control-room-page">
      <header className="border border-slate-300 bg-white p-5" data-testid="unified-control-room-header">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.25em] text-slate-500" data-testid="unified-control-room-kicker">Unified Control Room</p>
            <h1 className="mt-1 text-4xl font-black tracking-tight" data-testid="unified-control-room-title">Tek Karar Merkezi</h1>
            <p className="mt-2 text-sm text-slate-600" data-testid="unified-control-room-description">Incident, Execution, Learning ve Risk/Microstructure sinyalleri tek operatör ekranında.</p>
          </div>
          <div className="flex items-center gap-2">
            <select value={windowRange} onChange={(event) => setWindowRange(event.target.value)} className="border border-slate-300 bg-white px-3 py-2 text-sm" data-testid="unified-control-room-window-select">
              <option value="7d">7d</option>
              <option value="30d">30d</option>
            </select>
            <Button onClick={loadOverview} data-testid="unified-control-room-refresh-button">Yenile</Button>
          </div>
        </div>
      </header>

      {loading ? (
        <div className={card} data-testid="unified-control-room-loading">Yükleniyor...</div>
      ) : (
        <>
          <div className="grid gap-4 xl:grid-cols-12" data-testid="unified-control-room-main-grid">
            <div className="space-y-4 xl:col-span-4" data-testid="unified-control-room-live-operations-column">
              <div className={card} data-testid="unified-control-room-live-operations-panel">
                <h2 className="text-sm font-bold uppercase tracking-[0.2em]" data-testid="unified-control-room-live-operations-title">Live Operations</h2>
                <div className="mt-3 space-y-2" data-testid="unified-control-room-incident-list">
                  {(overview?.live_operations?.incidents || []).map((item, idx) => (
                    <button key={item.incident_id} type="button" onClick={() => setSelectedIncidentId(item.incident_id)} className="block w-full border border-slate-200 p-3 text-left" data-testid={`unified-control-room-incident-item-${idx}`}>
                      <p className="font-semibold" data-testid={`unified-control-room-incident-title-${idx}`}>{item.title}</p>
                      <p className="mt-1 text-xs" data-testid={`unified-control-room-incident-state-${idx}`}>{item.state} · {item.severity}</p>
                    </button>
                  ))}
                </div>
                <div className="mt-4 border-t border-slate-200 pt-3" data-testid="unified-control-room-execution-alerts-panel">
                  <p className="text-[11px] uppercase tracking-[0.2em] text-slate-500">execution alerts</p>
                  <div className="mt-2 space-y-2">
                    {(overview?.live_operations?.execution_alerts || []).slice(0, 5).map((item, idx) => (
                      <div key={`${item.intent_id}-${idx}`} className="border border-slate-200 p-2 text-xs" data-testid={`unified-control-room-execution-alert-${idx}`}>
                        <p className="font-mono">{item.intent_id}</p>
                        <p>{item.type} · {item.severity_level || item.severity}</p>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="mt-4 border-t border-slate-200 pt-3" data-testid="unified-control-room-bots-panel">
                  <p className="text-[11px] uppercase tracking-[0.2em] text-slate-500">bots overview</p>
                  <div className="mt-2 space-y-2">
                    {(overview?.live_operations?.bots_overview || []).slice(0, 6).map((item, idx) => (
                      <div key={`${item.id}-${idx}`} className="border border-slate-200 p-2 text-xs" data-testid={`unified-control-room-bot-item-${idx}`}>
                        <p className="font-semibold" data-testid={`unified-control-room-bot-name-${idx}`}>{item.name}</p>
                        <p data-testid={`unified-control-room-bot-status-${idx}`}>{item.status} · {item.health} · {item.mode}</p>
                        <p data-testid={`unified-control-room-bot-pnl-${idx}`}>pnl={item.today_pnl ?? item.pnl}</p>
                        <p data-testid={`unified-control-room-bot-risk-${idx}`}>risk_exposure={item.risk_exposure ?? 0}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            <div className="space-y-4 xl:col-span-4" data-testid="unified-control-room-learning-column">
              <div className={card} data-testid="unified-control-room-learning-panel">
                <h2 className="text-sm font-bold uppercase tracking-[0.2em]" data-testid="unified-control-room-learning-title">Learning & Adaptation</h2>
                <div className="mt-3 space-y-2" data-testid="unified-control-room-recommendation-list">
                  {(overview?.learning_adaptation?.actionable_recommendations || []).slice(0, 8).map((item, idx) => (
                    <button key={item.id} type="button" onClick={() => setSelectedRecommendationId(item.id)} className="block w-full border border-slate-200 p-3 text-left" data-testid={`unified-control-room-recommendation-item-${idx}`}>
                      <p className="font-semibold" data-testid={`unified-control-room-recommendation-title-${idx}`}>{item.recommendation_type}</p>
                      <p className="mt-1 text-xs">{item.reason}</p>
                      <p className="mt-1 font-mono text-xs" data-testid={`unified-control-room-recommendation-score-${idx}`}>{item.recommendation_score} · {item.actionable_state}</p>
                    </button>
                  ))}
                </div>
              </div>

              <div className={card} data-testid="unified-control-room-explainability-panel">
                <h2 className="text-sm font-bold uppercase tracking-[0.2em]" data-testid="unified-control-room-explainability-title">Explainability</h2>
                <div className="mt-3 space-y-3">
                  {(overview?.explainability || []).slice(0, 3).map((item, idx) => (
                    <div key={`${item.title}-${idx}`} className="border border-slate-200 p-3 text-xs" data-testid={`unified-control-room-explainability-card-${idx}`}>
                      <p className="font-semibold">{item.title}</p>
                      <p className="mt-1">neden: {item.why}</p>
                      <p className="mt-1">öneri: {item.recommended_action}</p>
                      <p className="mt-1">rollback: {item.rollback_ready ? "mümkün" : "yok"}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="space-y-4 xl:col-span-4" data-testid="unified-control-room-right-column">
              <div className={card} data-testid="unified-control-room-risk-panel">
                <h2 className="text-sm font-bold uppercase tracking-[0.2em]" data-testid="unified-control-room-risk-title">Risk & Market Context</h2>
                <div className="mt-3 grid gap-3 text-xs">
                  <pre className={monoBox} data-testid="unified-control-room-risk-capital-pressure">{pretty(overview?.risk_market_context?.capital_pressure)}</pre>
                  <pre className={monoBox} data-testid="unified-control-room-risk-microstructure-stress">{pretty(overview?.risk_market_context?.microstructure_stress)}</pre>
                  <pre className={monoBox} data-testid="unified-control-room-risk-cluster">{pretty(overview?.risk_market_context?.cluster_risk)}</pre>
                  <pre className={monoBox} data-testid="unified-control-room-risk-tail">{pretty(overview?.risk_market_context?.tail_risk)}</pre>
                </div>
              </div>

              <div className={card} data-testid="unified-control-room-action-center-panel">
                <h2 className="text-sm font-bold uppercase tracking-[0.2em]" data-testid="unified-control-room-action-center-title">Action Center</h2>
                <div className="mt-3 grid gap-3">
                  <div className="border border-slate-200 p-3" data-testid="unified-control-room-incident-action-box">
                    <p className="text-[11px] uppercase tracking-[0.2em] text-slate-500">incident preview action</p>
                    <textarea value={incidentReason} onChange={(event) => setIncidentReason(event.target.value)} className="mt-2 min-h-[72px] w-full border border-slate-300 px-3 py-2 text-sm" data-testid="unified-control-room-incident-reason-input" />
                    <Button className="mt-2" variant="outline" onClick={previewIncidentAction} disabled={!!actionLoading} data-testid="unified-control-room-incident-preview-button">Preview Action</Button>
                  </div>
                  <div className="border border-slate-200 p-3" data-testid="unified-control-room-learning-action-box">
                    <p className="text-[11px] uppercase tracking-[0.2em] text-slate-500">learning actions</p>
                    <textarea value={learningReason} onChange={(event) => setLearningReason(event.target.value)} className="mt-2 min-h-[72px] w-full border border-slate-300 px-3 py-2 text-sm" data-testid="unified-control-room-learning-reason-input" />
                    <div className="mt-2 flex flex-wrap gap-2">
                      <Button variant="outline" onClick={() => runLearningAction("approve")} disabled={!!actionLoading} data-testid="unified-control-room-learning-approve-button">Approve</Button>
                      <Button variant="outline" onClick={() => runLearningAction("reject")} disabled={!!actionLoading} data-testid="unified-control-room-learning-reject-button">Reject</Button>
                      <Button onClick={() => runLearningAction("apply")} disabled={!!actionLoading} data-testid="unified-control-room-learning-apply-button">Apply</Button>
                      <Button variant="outline" onClick={() => runLearningAction("rollback")} disabled={!!actionLoading} data-testid="unified-control-room-learning-rollback-button">Rollback</Button>
                    </div>
                  </div>
                </div>
              </div>

              <div className={card} data-testid="unified-control-room-stage-panel">
                <h2 className="text-sm font-bold uppercase tracking-[0.2em]" data-testid="unified-control-room-stage-title">Stage Activation</h2>
                <pre className={`${monoBox} mt-3`} data-testid="unified-control-room-stage-json">{pretty({ checklist: overview?.checklist, stage_activation: overview?.stage_activation })}</pre>
              </div>
            </div>
          </div>
        </>
      )}
    </section>
  );
}