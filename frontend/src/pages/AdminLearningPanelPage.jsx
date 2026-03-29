import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

const metricCard = "border border-slate-300 bg-white p-4";
const monoBox = "overflow-x-auto bg-slate-50 p-2 text-[11px] text-slate-700";

const safeJson = (value) => JSON.stringify(value || {}, null, 2);

const scopeLabel = (row) => row.strategy_id || row.family || row.recommendation_scope || "global";

export const AdminLearningPanelPage = () => {
  const [overview, setOverview] = useState({ strategy_memory: [], family_memory: [], recommendations: [], events: [], guardrails: {}, adaptive_summary: {} });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [actionLoading, setActionLoading] = useState("");
  const [reasonById, setReasonById] = useState({});
  const [simulationHistory, setSimulationHistory] = useState([]);

  const loadOverview = async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/admin/learning/overview");
      setOverview(data || { strategy_memory: [], family_memory: [], recommendations: [], events: [], guardrails: {}, adaptive_summary: {} });
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Learning overview yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadOverview();
  }, []);

  const refreshLearning = async () => {
    setRefreshing(true);
    try {
      await apiClient.post("/admin/learning/refresh", null, { params: { days: 30 } });
      await loadOverview();
      toast.success("Learning memory refresh tamamlandı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Learning refresh başarısız");
    } finally {
      setRefreshing(false);
    }
  };

  const requireReason = (recommendationId) => {
    const reason = String(reasonById[recommendationId] || "").trim();
    if (!reason) {
      toast.error("Aksiyon için reason zorunlu");
      return null;
    }
    return reason;
  };

  const actOnRecommendation = async (recommendationId, action) => {
    const reason = requireReason(recommendationId);
    if (!reason) return;
    setActionLoading(`${action}-${recommendationId}`);
    try {
      let response;
      if (action === "simulate") {
        response = await apiClient.post(`/admin/learning/recommendations/${recommendationId}/simulate`);
        setSimulationHistory((prev) => [response.data, ...prev].slice(0, 20));
      } else {
        response = await apiClient.post(`/admin/learning/recommendations/${recommendationId}/${action}`, { reason });
      }
      await loadOverview();
      toast.success(`Recommendation ${action} tamamlandı`);
      return response?.data;
    } catch (error) {
      toast.error(error?.response?.data?.detail || `Recommendation ${action} başarısız`);
      return null;
    } finally {
      setActionLoading("");
    }
  };

  const summary = useMemo(
    () => ({
      strategies: overview.strategy_memory?.length || 0,
      families: overview.family_memory?.length || 0,
      recommendations: overview.recommendations?.length || 0,
      affectedStrategies: overview.adaptive_summary?.affected_strategies?.length || 0,
    }),
    [overview],
  );

  return (
    <section className="space-y-5 bg-[#F9FAFB] text-slate-900" data-testid="admin-learning-panel-page">
      <header className="border border-slate-300 bg-white p-5" data-testid="admin-learning-panel-header">
        <p className="text-xs uppercase tracking-[0.25em] text-slate-500" data-testid="admin-learning-panel-kicker">Learning Control</p>
        <h2 className="mt-1 text-3xl font-black tracking-tight text-slate-900" data-testid="admin-learning-panel-title">Learning Memory</h2>
        <p className="mt-2 text-sm text-slate-600" data-testid="admin-learning-panel-description">
          Kanonik learning event kayıtları, adaptive performans sinyalleri, recommendation lifecycle ve replay tabanlı simülasyonlar.
        </p>
        <div className="mt-4 flex flex-wrap gap-2" data-testid="admin-learning-panel-toolbar">
          <Button type="button" onClick={loadOverview} data-testid="admin-learning-panel-reload-button">Yenile</Button>
          <Button type="button" variant="outline" onClick={refreshLearning} disabled={refreshing} data-testid="admin-learning-panel-refresh-button">
            {refreshing ? "Çalışıyor..." : "Learning Refresh (30g)"}
          </Button>
          <Link to="/admin/learning-impact-simulator" className="inline-flex" data-testid="admin-learning-panel-open-impact-simulator-link">
            <Button type="button" variant="outline" data-testid="admin-learning-panel-open-impact-simulator-button">Recommendation Simulator</Button>
          </Link>
        </div>
      </header>

      <div className="grid gap-3 md:grid-cols-4" data-testid="admin-learning-summary-grid">
        {[["strategies", summary.strategies], ["families", summary.families], ["recommendations", summary.recommendations], ["affected-strategies", summary.affectedStrategies]].map(([label, value]) => (
          <div key={label} className={metricCard} data-testid={`admin-learning-summary-card-${label}`}>
            <p className="text-[11px] uppercase tracking-[0.22em] text-slate-500" data-testid={`admin-learning-summary-label-${label}`}>{label}</p>
            <p className="mt-2 font-mono text-3xl" data-testid={`admin-learning-summary-value-${label}`}>{value}</p>
          </div>
        ))}
      </div>

      {loading ? (
        <div className="border border-slate-300 bg-white p-4 text-sm" data-testid="admin-learning-panel-loading">Yükleniyor...</div>
      ) : (
        <>
          <div className="grid gap-4 xl:grid-cols-12" data-testid="admin-learning-main-grid">
            <div className="space-y-4 xl:col-span-7" data-testid="admin-learning-left-column">
              <div className="overflow-x-auto border border-slate-300 bg-white" data-testid="admin-learning-strategy-memory-wrapper">
                <div className="border-b border-slate-200 px-4 py-3">
                  <h3 className="text-sm font-bold uppercase tracking-[0.2em]" data-testid="admin-learning-strategy-memory-title">Strategy Performance</h3>
                </div>
                <table className="min-w-[2200px] text-xs" data-testid="admin-learning-strategy-memory-table">
                  <thead className="bg-slate-50">
                    <tr>
                      {[
                        "strategy", "direction", "regime", "sample", "hit_rate", "avg_return", "drawdown", "false_allow", "false_reject", "pnl_by_regime", "decision_quality", "rolling_windows", "window_comparison", "stability", "decay_score", "drift_flag", "drift_confidence", "confidence_degradation", "actionability", "recommendation",
                      ].map((label) => (
                        <th key={label} className="px-2 py-2 text-left uppercase tracking-[0.16em] text-slate-500">{label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(overview.strategy_memory || []).map((row, idx) => (
                      <tr key={`${row.strategy_id}-${idx}`} className="border-t border-slate-200 align-top" data-testid={`admin-learning-strategy-memory-row-${idx}`}>
                        <td className="px-2 py-2 font-mono" data-testid={`admin-learning-strategy-memory-strategy-${idx}`}>{row.strategy_id}</td>
                        <td className="px-2 py-2">{row.direction}</td>
                        <td className="px-2 py-2">{row.regime}</td>
                        <td className="px-2 py-2">{row.sample_count}</td>
                        <td className="px-2 py-2">{row.hit_rate}</td>
                        <td className="px-2 py-2">{row.avg_return}</td>
                        <td className="px-2 py-2">{row.drawdown}</td>
                        <td className="px-2 py-2">{row.false_allow_rate}</td>
                        <td className="px-2 py-2">{row.false_reject_rate}</td>
                        <td className="px-2 py-2"><pre className={monoBox}>{safeJson(row.pnl_by_regime)}</pre></td>
                        <td className="px-2 py-2"><pre className={monoBox}>{safeJson(row.decision_quality_breakdown)}</pre></td>
                        <td className="px-2 py-2"><pre className={monoBox}>{safeJson(row.rolling_windows)}</pre></td>
                        <td className="px-2 py-2"><pre className={monoBox}>{safeJson(row.window_comparison)}</pre></td>
                        <td className="px-2 py-2">{row.stability_score}</td>
                        <td className="px-2 py-2">{row.decay_score}</td>
                        <td className="px-2 py-2">{row.regime_drift_flag ? "yes" : "no"}</td>
                        <td className="px-2 py-2">{row.drift_confidence}</td>
                        <td className="px-2 py-2">{row.confidence_degradation}</td>
                        <td className="px-2 py-2">{row.actionability_flag ? "actionable" : "monitor"}</td>
                        <td className="px-2 py-2">{row?.recommendation?.recommendation_type || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="overflow-x-auto border border-slate-300 bg-white" data-testid="admin-learning-events-wrapper">
                <div className="border-b border-slate-200 px-4 py-3">
                  <h3 className="text-sm font-bold uppercase tracking-[0.2em]" data-testid="admin-learning-events-title">Learning Events</h3>
                </div>
                <table className="min-w-[2000px] text-xs" data-testid="admin-learning-events-table">
                  <thead className="bg-slate-50">
                    <tr>
                      {[
                        "event_id", "signal", "decision", "outcome", "pnl_norm", "mfe", "mae", "false_allow", "false_reject", "regime", "strategy_id", "symbol", "created_at",
                      ].map((label) => (
                        <th key={label} className="px-2 py-2 text-left uppercase tracking-[0.16em] text-slate-500">{label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(overview.events || []).slice(0, 120).map((item, idx) => (
                      <tr key={item.event_id} className="border-t border-slate-200 align-top" data-testid={`admin-learning-events-row-${idx}`}>
                        <td className="px-2 py-2 font-mono" data-testid={`admin-learning-events-id-${idx}`}>{item.event_id}</td>
                        <td className="px-2 py-2"><pre className={monoBox}>{safeJson(item.signal)}</pre></td>
                        <td className="px-2 py-2">{item.decision}</td>
                        <td className="px-2 py-2">{item.outcome}</td>
                        <td className="px-2 py-2">{item.pnl_norm}</td>
                        <td className="px-2 py-2">{item.mfe}</td>
                        <td className="px-2 py-2">{item.mae}</td>
                        <td className="px-2 py-2">{item.false_allow ? "true" : "false"}</td>
                        <td className="px-2 py-2">{item.false_reject ? "true" : "false"}</td>
                        <td className="px-2 py-2">{item.regime}</td>
                        <td className="px-2 py-2 font-mono">{item.strategy_id}</td>
                        <td className="px-2 py-2">{item.symbol}</td>
                        <td className="px-2 py-2 font-mono">{String(item.created_at || "")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <aside className="space-y-4 xl:col-span-5" data-testid="admin-learning-right-column">
              <div className="border border-slate-300 bg-white p-4" data-testid="admin-learning-guardrail-panel">
                <h3 className="text-sm font-bold uppercase tracking-[0.2em]">Guardrails</h3>
                <div className="mt-3 space-y-1 text-xs">
                  <p data-testid="admin-learning-guardrail-auto-change">Auto Change Forbidden: {overview?.guardrails?.auto_change_forbidden ? "true" : "false"}</p>
                  <p data-testid="admin-learning-guardrail-admin-approval">Admin Approval Required: {overview?.guardrails?.admin_approval_required ? "true" : "false"}</p>
                  <p data-testid="admin-learning-guardrail-audit">Audit Log Enabled: {overview?.guardrails?.audit_log_enabled ? "true" : "false"}</p>
                </div>
              </div>

              <div className="space-y-3" data-testid="admin-learning-recommendation-list">
                {(overview.recommendations || []).map((item, idx) => (
                  <article key={item.id} className="border border-slate-300 bg-white p-4" data-testid={`admin-learning-recommendation-item-${idx}`}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <p className="text-[11px] uppercase tracking-[0.2em] text-slate-500">{item.recommendation_type}</p>
                        <h4 className="mt-1 text-base font-bold" data-testid={`admin-learning-recommendation-scope-${idx}`}>{scopeLabel(item)}</h4>
                      </div>
                      <p className="font-mono text-sm" data-testid={`admin-learning-recommendation-actionable-state-${idx}`}>{item.actionable_state}</p>
                    </div>
                    <div className="mt-3 grid gap-2 sm:grid-cols-2 text-xs">
                      <p data-testid={`admin-learning-recommendation-reason-${idx}`}>reason: {item.reason}</p>
                      <p data-testid={`admin-learning-recommendation-confidence-${idx}`}>confidence: {item.confidence}</p>
                      <p data-testid={`admin-learning-recommendation-score-${idx}`}>recommendation_score: {item.recommendation_score}</p>
                      <p data-testid={`admin-learning-recommendation-scope-label-${idx}`}>scope: {item.recommendation_scope}</p>
                      <p data-testid={`admin-learning-recommendation-decision-candidate-${idx}`}>decision_candidate: {String(item.decision_candidate)}</p>
                      <p data-testid={`admin-learning-recommendation-auto-apply-${idx}`}>auto_apply_eligible: {String(item.auto_apply_eligible)}</p>
                    </div>
                    <div className="mt-3 grid gap-3 md:grid-cols-2">
                      <div>
                        <p className="mb-1 text-[11px] uppercase tracking-[0.2em] text-slate-500">evidence_summary</p>
                        <pre className={monoBox} data-testid={`admin-learning-recommendation-evidence-${idx}`}>{safeJson(item.evidence_summary)}</pre>
                      </div>
                      <div>
                        <p className="mb-1 text-[11px] uppercase tracking-[0.2em] text-slate-500">risk_impact</p>
                        <pre className={monoBox} data-testid={`admin-learning-recommendation-risk-impact-${idx}`}>{safeJson(item.risk_impact)}</pre>
                      </div>
                      <div>
                        <p className="mb-1 text-[11px] uppercase tracking-[0.2em] text-slate-500">status / version history</p>
                        <pre className={monoBox} data-testid={`admin-learning-recommendation-version-${idx}`}>{safeJson({ lifecycle: item.lifecycle, status_history: item.status_history, version: item.version, version_history: item.version_history })}</pre>
                      </div>
                      <div>
                        <p className="mb-1 text-[11px] uppercase tracking-[0.2em] text-slate-500">monitoring / simulation</p>
                        <pre className={monoBox} data-testid={`admin-learning-recommendation-monitoring-${idx}`}>{safeJson({ post_change_monitoring: item.post_change_monitoring, last_simulation: item.recommendation_value?.last_simulation })}</pre>
                      </div>
                    </div>

                    <div className="mt-3 grid gap-2" data-testid={`admin-learning-recommendation-action-form-${idx}`}>
                      <textarea
                        value={reasonById[item.id] || ""}
                        onChange={(event) => setReasonById((prev) => ({ ...prev, [item.id]: event.target.value }))}
                        placeholder="reason zorunlu"
                        className="min-h-[72px] border border-slate-300 px-3 py-2 text-sm"
                        data-testid={`admin-learning-recommendation-reason-input-${idx}`}
                      />
                      <div className="flex flex-wrap gap-2">
                        <Button type="button" variant="outline" onClick={() => actOnRecommendation(item.id, "simulate")} disabled={!!actionLoading} data-testid={`admin-learning-recommendation-simulate-button-${idx}`}>Simulate</Button>
                        <Button type="button" variant="outline" onClick={() => actOnRecommendation(item.id, "approve")} disabled={!!actionLoading} data-testid={`admin-learning-recommendation-approve-button-${idx}`}>Approve</Button>
                        <Button type="button" variant="outline" onClick={() => actOnRecommendation(item.id, "reject")} disabled={!!actionLoading} data-testid={`admin-learning-recommendation-reject-button-${idx}`}>Reject</Button>
                        <Button type="button" onClick={() => actOnRecommendation(item.id, "apply")} disabled={!!actionLoading} data-testid={`admin-learning-recommendation-apply-button-${idx}`}>Apply</Button>
                        <Button type="button" variant="outline" onClick={() => actOnRecommendation(item.id, "rollback")} disabled={!!actionLoading} data-testid={`admin-learning-recommendation-rollback-button-${idx}`}>Rollback</Button>
                      </div>
                    </div>
                  </article>
                ))}
                {(overview.recommendations || []).length === 0 && <div className="border border-slate-300 bg-white p-4 text-sm" data-testid="admin-learning-recommendation-empty">Öneri yok.</div>}
              </div>
            </aside>
          </div>

          <div className="border border-slate-300 bg-white p-4" data-testid="admin-learning-simulation-history-panel">
            <h3 className="text-sm font-bold uppercase tracking-[0.2em]" data-testid="admin-learning-simulation-history-title">Recommendation Simulator Output</h3>
            <div className="mt-3 grid gap-3 lg:grid-cols-2" data-testid="admin-learning-simulation-history-grid">
              {simulationHistory.map((item, idx) => (
                <article key={`sim-${idx}`} className="border border-slate-200 p-3" data-testid={`admin-learning-simulation-history-card-${idx}`}>
                  <p className="text-[11px] uppercase tracking-[0.2em] text-slate-500">{item.scope} · {item.recommendation_type}</p>
                  <div className="mt-2 grid gap-2 md:grid-cols-2 text-xs">
                    <pre className={monoBox} data-testid={`admin-learning-simulation-baseline-${idx}`}>{safeJson(item.baseline_metrics)}</pre>
                    <pre className={monoBox} data-testid={`admin-learning-simulation-projected-${idx}`}>{safeJson(item.projected_metrics)}</pre>
                    <pre className={monoBox} data-testid={`admin-learning-simulation-delta-${idx}`}>{safeJson(item.delta_metrics)}</pre>
                    <pre className={monoBox} data-testid={`admin-learning-simulation-coverage-${idx}`}>{safeJson(item.sample_coverage)}</pre>
                    <pre className={monoBox} data-testid={`admin-learning-simulation-risk-aware-${idx}`}>{safeJson(item.risk_aware_view)}</pre>
                    <pre className={monoBox} data-testid={`admin-learning-simulation-portfolio-impact-${idx}`}>{safeJson(item.portfolio_impact)}</pre>
                    <pre className={monoBox} data-testid={`admin-learning-simulation-counterfactual-${idx}`}>{safeJson(item.counterfactual_replay)}</pre>
                    <pre className={monoBox} data-testid={`admin-learning-simulation-interaction-${idx}`}>{safeJson(item.interaction_effects)}</pre>
                  </div>
                </article>
              ))}
              {simulationHistory.length === 0 && <p className="text-sm text-slate-500" data-testid="admin-learning-simulation-history-empty">Henüz simülasyon çalıştırılmadı.</p>}
            </div>
          </div>
        </>
      )}
    </section>
  );
};
