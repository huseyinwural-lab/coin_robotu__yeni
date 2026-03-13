import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const AdminLearningPanelPage = () => {
  const [overview, setOverview] = useState({ strategy_memory: [], family_memory: [], recommendations: [], events: [], guardrails: {} });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [isSimulating, setIsSimulating] = useState(false);
  const [simulationHistory, setSimulationHistory] = useState([]);
  const [simForm, setSimForm] = useState({
    strategy_id: "",
    family: "",
    recommendation_type: "decrease_weight_recommendation",
    suggested_weight_multiplier: "0.8",
  });

  const loadOverview = async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/admin/learning/overview");
      setOverview(data || { strategy_memory: [], family_memory: [], recommendations: [], events: [], guardrails: {} });
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

  const applyRecommendation = async (recommendationId) => {
    try {
      await apiClient.post(`/admin/learning/recommendations/${recommendationId}/apply`);
      await loadOverview();
      toast.success("Öneri uygulandı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Öneri uygulanamadı");
    }
  };

  const pushSimulationResult = (payload) => {
    setSimulationHistory((prev) => [payload, ...prev].slice(0, 20));
  };

  const simulateRecommendation = async (recommendationId) => {
    setIsSimulating(true);
    try {
      const { data } = await apiClient.post(`/admin/learning/recommendations/${recommendationId}/simulate`);
      pushSimulationResult(data);
      toast.success("Recommendation impact simülasyonu üretildi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Recommendation simulation başarısız");
    } finally {
      setIsSimulating(false);
    }
  };

  const simulateGlobalImpact = async () => {
    setIsSimulating(true);
    try {
      const payload = {
        strategy_id: String(simForm.strategy_id || "").trim() || null,
        family: String(simForm.family || "").trim() || null,
        recommendation_type: simForm.recommendation_type,
        suggested_weight_multiplier: simForm.suggested_weight_multiplier ? Number(simForm.suggested_weight_multiplier) : null,
      };
      const { data } = await apiClient.post("/admin/learning/simulate-impact", payload);
      pushSimulationResult(data);
      toast.success("Global impact simülasyonu üretildi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Global simulation başarısız");
    } finally {
      setIsSimulating(false);
    }
  };

  return (
    <section className="space-y-4" data-testid="admin-learning-panel-page">
      <header className="border border-black/40 bg-lime-300 p-4" data-testid="admin-learning-panel-header">
        <h2 className="text-3xl font-black uppercase tracking-tight text-black" data-testid="admin-learning-panel-title">Learning Memory Panel</h2>
        <p className="mt-2 text-sm text-black/80" data-testid="admin-learning-panel-description">
          Bu panel öneri üretir; production kural setini otomatik değiştirmez (admin onayı gerekir).
        </p>
      </header>

      <div className="flex flex-wrap gap-2" data-testid="admin-learning-panel-toolbar">
        <Button type="button" onClick={loadOverview} data-testid="admin-learning-panel-reload-button">Yenile</Button>
        <Button type="button" variant="outline" onClick={refreshLearning} disabled={refreshing} data-testid="admin-learning-panel-refresh-button">
          {refreshing ? "Çalışıyor..." : "Learning Refresh (30g)"}
        </Button>
        <Link to="/admin/learning-impact-simulator" className="inline-flex" data-testid="admin-learning-panel-open-impact-simulator-link">
          <Button type="button" variant="outline" data-testid="admin-learning-panel-open-impact-simulator-button">Impact Simulator (Detay)</Button>
        </Link>
      </div>

      {loading ? (
        <div className="border border-slate-700 bg-slate-900 p-4 text-sm" data-testid="admin-learning-panel-loading">Yükleniyor...</div>
      ) : (
        <>
          <div className="rounded border border-blue-800/50 bg-blue-950/20 p-3" data-testid="admin-learning-impact-global-form-panel">
            <p className="text-sm font-semibold" data-testid="admin-learning-impact-global-form-title">Learning Recommendation Impact Simulator (Global)</p>
            <div className="mt-2 grid gap-2 md:grid-cols-4" data-testid="admin-learning-impact-global-form-grid">
              <input
                value={simForm.strategy_id}
                onChange={(event) => setSimForm((prev) => ({ ...prev, strategy_id: event.target.value }))}
                placeholder="strategy_id (opsiyonel)"
                className="h-10 rounded border border-blue-700 bg-black px-3 text-xs"
                data-testid="admin-learning-impact-global-strategy-id-input"
              />
              <input
                value={simForm.family}
                onChange={(event) => setSimForm((prev) => ({ ...prev, family: event.target.value }))}
                placeholder="family (trend/breakout/...)"
                className="h-10 rounded border border-blue-700 bg-black px-3 text-xs"
                data-testid="admin-learning-impact-global-family-input"
              />
              <select
                value={simForm.recommendation_type}
                onChange={(event) => setSimForm((prev) => ({ ...prev, recommendation_type: event.target.value }))}
                className="h-10 rounded border border-blue-700 bg-black px-3 text-xs"
                data-testid="admin-learning-impact-global-recommendation-type-select"
              >
                <option value="disable_recommendation">disable_recommendation</option>
                <option value="decrease_weight_recommendation">decrease_weight_recommendation</option>
                <option value="increase_weight_recommendation">increase_weight_recommendation</option>
              </select>
              <input
                type="number"
                step="0.05"
                min="0.1"
                max="3"
                value={simForm.suggested_weight_multiplier}
                onChange={(event) => setSimForm((prev) => ({ ...prev, suggested_weight_multiplier: event.target.value }))}
                placeholder="weight multiplier"
                className="h-10 rounded border border-blue-700 bg-black px-3 text-xs"
                data-testid="admin-learning-impact-global-weight-multiplier-input"
              />
            </div>
            <div className="mt-2 flex items-center gap-2" data-testid="admin-learning-impact-global-form-actions">
              <Button type="button" variant="outline" disabled={isSimulating} onClick={simulateGlobalImpact} data-testid="admin-learning-impact-global-simulate-button">
                {isSimulating ? "Simulating..." : "Simulate Impact"}
              </Button>
              <p className="text-xs text-blue-100" data-testid="admin-learning-impact-global-form-note">Read-only simülasyon; Apply ayrı butondur.</p>
            </div>
          </div>

          <div className="overflow-x-auto border border-slate-700" data-testid="admin-learning-strategy-memory-wrapper">
            <table className="min-w-[1400px] text-xs" data-testid="admin-learning-strategy-memory-table">
              <thead>
                <tr>
                  <th className="px-2 py-1 text-left">strategy</th>
                  <th className="px-2 py-1 text-left">direction</th>
                  <th className="px-2 py-1 text-left">regime</th>
                  <th className="px-2 py-1 text-left">sample</th>
                  <th className="px-2 py-1 text-left">hit_rate</th>
                  <th className="px-2 py-1 text-left">avg_return</th>
                  <th className="px-2 py-1 text-left">false_allow</th>
                  <th className="px-2 py-1 text-left">false_reject</th>
                  <th className="px-2 py-1 text-left">rolling</th>
                  <th className="px-2 py-1 text-left">decay_quality</th>
                  <th className="px-2 py-1 text-left">quality_degradation</th>
                  <th className="px-2 py-1 text-left">recommendation</th>
                </tr>
              </thead>
              <tbody>
                {(overview.strategy_memory || []).map((row, idx) => (
                  <tr key={`${row.strategy_id}-${idx}`} className="border-t border-slate-800" data-testid={`admin-learning-strategy-memory-row-${idx}`}>
                    <td className="px-2 py-1" data-testid={`admin-learning-strategy-memory-strategy-${idx}`}>{row.strategy_id}</td>
                    <td className="px-2 py-1">{row.direction}</td>
                    <td className="px-2 py-1">{row.regime}</td>
                    <td className="px-2 py-1">{row.sample_count}</td>
                    <td className="px-2 py-1">{row.hit_rate}</td>
                    <td className="px-2 py-1">{row.avg_return}</td>
                    <td className="px-2 py-1">{row.false_allow_rate}</td>
                    <td className="px-2 py-1">{row.false_reject_rate}</td>
                    <td className="px-2 py-1">{row.rolling_quality_score ?? row.recent_rolling_score}</td>
                    <td className="px-2 py-1">{row.decay_adjusted_score ?? row.decay_adjusted_quality_score}</td>
                    <td className="px-2 py-1">{row.quality_degradation_flag ? "yes" : "no"}</td>
                    <td className="px-2 py-1">{row?.recommendation?.recommendation_type || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="overflow-x-auto border border-slate-700" data-testid="admin-learning-family-memory-wrapper">
            <table className="min-w-[1000px] text-xs" data-testid="admin-learning-family-memory-table">
              <thead>
                <tr>
                  <th className="px-2 py-1 text-left">family</th>
                  <th className="px-2 py-1 text-left">regime</th>
                  <th className="px-2 py-1 text-left">sample</th>
                  <th className="px-2 py-1 text-left">hit_rate</th>
                  <th className="px-2 py-1 text-left">avg_return</th>
                  <th className="px-2 py-1 text-left">volatility_success</th>
                  <th className="px-2 py-1 text-left">conflict_success</th>
                </tr>
              </thead>
              <tbody>
                {(overview.family_memory || []).map((row, idx) => (
                  <tr key={`${row.family}-${idx}`} className="border-t border-slate-800" data-testid={`admin-learning-family-memory-row-${idx}`}>
                    <td className="px-2 py-1">{row.family}</td>
                    <td className="px-2 py-1">{row.regime}</td>
                    <td className="px-2 py-1">{row.sample_count}</td>
                    <td className="px-2 py-1">{row.hit_rate}</td>
                    <td className="px-2 py-1">{row.avg_return}</td>
                    <td className="px-2 py-1">{row.volatility_success}</td>
                    <td className="px-2 py-1">{row.conflict_success}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="border border-slate-700 p-3" data-testid="admin-learning-recommendation-panel">
            <p className="text-sm font-semibold" data-testid="admin-learning-recommendation-title">Learning Recommendations</p>
            <div className="mt-2 rounded border border-lime-900/60 bg-lime-950/20 p-2" data-testid="admin-learning-guardrail-panel">
              <p className="text-xs" data-testid="admin-learning-guardrail-auto-change">Auto Change Forbidden: {overview?.guardrails?.auto_change_forbidden ? "true" : "false"}</p>
              <p className="text-xs" data-testid="admin-learning-guardrail-admin-approval">Admin Approval Required: {overview?.guardrails?.admin_approval_required ? "true" : "false"}</p>
              <p className="text-xs" data-testid="admin-learning-guardrail-audit">Audit Log Enabled: {overview?.guardrails?.audit_log_enabled ? "true" : "false"}</p>
            </div>
            <div className="mt-2 space-y-2" data-testid="admin-learning-recommendation-list">
              {(overview.recommendations || []).map((item) => (
                <div key={item.id} className="flex flex-wrap items-center gap-2 rounded border border-slate-700 p-2" data-testid={`admin-learning-recommendation-item-${item.id}`}>
                  <p className="text-xs">{item.recommendation_type}</p>
                  <p className="text-xs">{item.strategy_id || item.family || "global"}</p>
                  <p className="text-xs">severity={item.severity}</p>
                  <p className="text-xs">{item.note}</p>
                  <Button type="button" size="sm" variant="outline" disabled={Boolean(item.is_applied)} onClick={() => applyRecommendation(item.id)} data-testid={`admin-learning-recommendation-apply-button-${item.id}`}>
                    {item.is_applied ? "Applied" : "Apply"}
                  </Button>
                  <Button type="button" size="sm" variant="outline" disabled={isSimulating} onClick={() => simulateRecommendation(item.id)} data-testid={`admin-learning-recommendation-simulate-button-${item.id}`}>
                    Simulate Impact
                  </Button>
                </div>
              ))}
              {(overview.recommendations || []).length === 0 && <p className="text-xs" data-testid="admin-learning-recommendation-empty">Öneri yok.</p>}
            </div>
          </div>

          <div className="grid gap-2 md:grid-cols-2" data-testid="admin-learning-impact-simulation-results-grid">
            {simulationHistory.map((item, idx) => (
              <article key={`sim-${idx}`} className="rounded border border-blue-700/60 bg-black/30 p-3" data-testid={`admin-learning-impact-simulation-result-card-${idx}`}>
                <p className="text-xs" data-testid={`admin-learning-impact-simulation-scope-${idx}`}>scope={item.scope} · rec={item.recommendation_type}</p>
                <p className="text-xs" data-testid={`admin-learning-impact-simulation-project-risk-${idx}`}>projected_risk_score={item.projected_risk_score}</p>
                <p className="text-xs" data-testid={`admin-learning-impact-simulation-project-gate-${idx}`}>projected_gate_decision={item.projected_gate_decision}</p>
                <p className="text-xs" data-testid={`admin-learning-impact-simulation-hit-delta-${idx}`}>expected_hit_rate_delta={item.expected_hit_rate_delta}</p>
                <p className="text-xs" data-testid={`admin-learning-impact-simulation-return-delta-${idx}`}>expected_avg_return_delta={item.expected_avg_return_delta}</p>
                <p className="text-xs" data-testid={`admin-learning-impact-simulation-drift-delta-${idx}`}>allocation_drift_delta={item.allocation_drift_delta}</p>
                <p className="text-xs" data-testid={`admin-learning-impact-simulation-hedge-score-${idx}`}>hedge_effect_score={item.hedge_effect_score}</p>
              </article>
            ))}
            {simulationHistory.length === 0 && <p className="text-xs text-slate-300" data-testid="admin-learning-impact-simulation-empty">Henüz simülasyon çalıştırılmadı.</p>}
          </div>

          <div className="overflow-x-auto border border-slate-700" data-testid="admin-learning-events-wrapper">
            <table className="min-w-[1400px] text-xs" data-testid="admin-learning-events-table">
              <thead>
                <tr>
                  <th className="px-2 py-1 text-left">event_id</th>
                  <th className="px-2 py-1 text-left">symbol</th>
                  <th className="px-2 py-1 text-left">decision</th>
                  <th className="px-2 py-1 text-left">outcome</th>
                  <th className="px-2 py-1 text-left">pnl_norm</th>
                  <th className="px-2 py-1 text-left">mfe</th>
                  <th className="px-2 py-1 text-left">mae</th>
                  <th className="px-2 py-1 text-left">hold_duration</th>
                  <th className="px-2 py-1 text-left">created_at</th>
                </tr>
              </thead>
              <tbody>
                {(overview.events || []).slice(0, 120).map((item, idx) => (
                  <tr key={item.event_id} className="border-t border-slate-800" data-testid={`admin-learning-events-row-${idx}`}>
                    <td className="px-2 py-1" data-testid={`admin-learning-events-id-${idx}`}>{item.event_id}</td>
                    <td className="px-2 py-1">{item.symbol}</td>
                    <td className="px-2 py-1">{item.decision}</td>
                    <td className="px-2 py-1">{item.outcome_label}</td>
                    <td className="px-2 py-1">{item.pnl_normalized}</td>
                    <td className="px-2 py-1">{item.max_favorable_excursion}</td>
                    <td className="px-2 py-1">{item.max_adverse_excursion}</td>
                    <td className="px-2 py-1">{item.hold_duration}</td>
                    <td className="px-2 py-1">{String(item.created_at || "")}</td>
                  </tr>
                ))}
                {(overview.events || []).length === 0 && <tr><td className="px-2 py-2 text-xs" colSpan={9} data-testid="admin-learning-events-empty">Event yok.</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
};
