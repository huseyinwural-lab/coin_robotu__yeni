import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

const monoBox = "overflow-x-auto bg-slate-50 p-2 text-[11px] text-slate-700";
const safeJson = (value) => JSON.stringify(value || {}, null, 2);

export const AdminLearningImpactSimulatorPage = () => {
  const [overview, setOverview] = useState({ strategy_memory: [], family_memory: [], recommendations: [] });
  const [loading, setLoading] = useState(true);
  const [simulating, setSimulating] = useState(false);
  const [simulationResult, setSimulationResult] = useState(null);
  const [form, setForm] = useState({
    strategy_id: "",
    strategy_ids: "",
    family: "",
    symbol_cluster: "",
    scenario: "base",
    recommendation_type: "decrease_weight_recommendation",
    suggested_weight_multiplier: "0.8",
  });

  const loadOverview = async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/admin/learning/overview");
      setOverview(data || { strategy_memory: [], family_memory: [], recommendations: [] });
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Learning verisi yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadOverview();
  }, []);

  const simulateGlobal = async () => {
    setSimulating(true);
    try {
      const payload = {
        strategy_id: String(form.strategy_id || "").trim() || null,
        strategy_ids: String(form.strategy_ids || "").split(",").map((item) => item.trim()).filter(Boolean),
        family: String(form.family || "").trim() || null,
        symbol_cluster: String(form.symbol_cluster || "").split(",").map((item) => item.trim().toUpperCase()).filter(Boolean),
        scenario: form.scenario,
        recommendation_type: form.recommendation_type,
        suggested_weight_multiplier: form.suggested_weight_multiplier ? Number(form.suggested_weight_multiplier) : null,
      };
      const { data } = await apiClient.post("/admin/learning/simulate-impact", payload);
      setSimulationResult(data || null);
      toast.success("Impact simulation tamamlandı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Simülasyon başarısız");
    } finally {
      setSimulating(false);
    }
  };

  const simulateFromRecommendation = async (recommendationId) => {
    setSimulating(true);
    try {
      const { data } = await apiClient.post(`/admin/learning/recommendations/${recommendationId}/simulate`);
      setSimulationResult(data || null);
      toast.success("Recommendation bazlı simulation tamamlandı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Recommendation simulation başarısız");
    } finally {
      setSimulating(false);
    }
  };

  return (
    <section className="space-y-4" data-testid="admin-learning-impact-simulator-page">
      <header className="border border-slate-700 bg-slate-900 p-4" data-testid="admin-learning-impact-simulator-header">
        <h2 className="text-3xl font-black uppercase tracking-tight" data-testid="admin-learning-impact-simulator-title">Learning Recommendation Impact Simulator</h2>
        <p className="mt-1 text-sm text-slate-400" data-testid="admin-learning-impact-simulator-description">
          Strategy-level + Family-level etki simülasyonu. Read-only çalışır; production apply ayrı adımdır.
        </p>
      </header>

      <div className="grid gap-2 md:grid-cols-7" data-testid="admin-learning-impact-simulator-form-grid">
        <input
          value={form.strategy_id}
          onChange={(event) => setForm((prev) => ({ ...prev, strategy_id: event.target.value }))}
          placeholder="strategy_id"
          className="h-10 rounded border border-slate-700 bg-black px-3 text-xs"
          data-testid="admin-learning-impact-simulator-strategy-id-input"
        />
        <input
          value={form.strategy_ids}
          onChange={(event) => setForm((prev) => ({ ...prev, strategy_ids: event.target.value }))}
          placeholder="strategy_ids (csv)"
          className="h-10 rounded border border-slate-700 bg-black px-3 text-xs"
          data-testid="admin-learning-impact-simulator-strategy-ids-input"
        />
        <input
          value={form.family}
          onChange={(event) => setForm((prev) => ({ ...prev, family: event.target.value }))}
          placeholder="family"
          className="h-10 rounded border border-slate-700 bg-black px-3 text-xs"
          data-testid="admin-learning-impact-simulator-family-input"
        />
        <input
          value={form.symbol_cluster}
          onChange={(event) => setForm((prev) => ({ ...prev, symbol_cluster: event.target.value }))}
          placeholder="symbol_cluster (csv)"
          className="h-10 rounded border border-slate-700 bg-black px-3 text-xs"
          data-testid="admin-learning-impact-simulator-symbol-cluster-input"
        />
        <select
          value={form.scenario}
          onChange={(event) => setForm((prev) => ({ ...prev, scenario: event.target.value }))}
          className="h-10 rounded border border-slate-700 bg-black px-3 text-xs"
          data-testid="admin-learning-impact-simulator-scenario-select"
        >
          <option value="base">base</option>
          <option value="stressed">stressed</option>
          <option value="high_volatility">high_volatility</option>
          <option value="low_liquidity">low_liquidity</option>
        </select>
        <select
          value={form.recommendation_type}
          onChange={(event) => setForm((prev) => ({ ...prev, recommendation_type: event.target.value }))}
          className="h-10 rounded border border-slate-700 bg-black px-3 text-xs"
          data-testid="admin-learning-impact-simulator-recommendation-type-select"
        >
          <option value="disable_recommendation">disable_recommendation</option>
          <option value="decrease_weight_recommendation">decrease_weight_recommendation</option>
          <option value="increase_weight_recommendation">increase_weight_recommendation</option>
          <option value="threshold_tune">threshold_tune</option>
        </select>
        <input
          type="number"
          step="0.05"
          min="0.1"
          max="3"
          value={form.suggested_weight_multiplier}
          onChange={(event) => setForm((prev) => ({ ...prev, suggested_weight_multiplier: event.target.value }))}
          placeholder="weight_multiplier"
          className="h-10 rounded border border-slate-700 bg-black px-3 text-xs"
          data-testid="admin-learning-impact-simulator-weight-multiplier-input"
        />
        <Button type="button" variant="outline" disabled={simulating} onClick={simulateGlobal} data-testid="admin-learning-impact-simulator-run-button">
          {simulating ? "Simulating..." : "Simulate"}
        </Button>
      </div>

      <div className="overflow-x-auto border border-slate-700" data-testid="admin-learning-impact-simulator-recommendations-wrapper">
        <table className="min-w-[1500px] text-xs" data-testid="admin-learning-impact-simulator-recommendations-table">
          <thead>
            <tr>
              <th className="px-2 py-1 text-left">type</th>
              <th className="px-2 py-1 text-left">target</th>
              <th className="px-2 py-1 text-left">reason</th>
              <th className="px-2 py-1 text-left">confidence</th>
              <th className="px-2 py-1 text-left">scope</th>
              <th className="px-2 py-1 text-left">score</th>
              <th className="px-2 py-1 text-left">actionable</th>
              <th className="px-2 py-1 text-left">severity</th>
              <th className="px-2 py-1 text-left">risk</th>
              <th className="px-2 py-1 text-left">action</th>
            </tr>
          </thead>
          <tbody>
            {(overview.recommendations || []).map((item, idx) => (
              <tr key={item.id} className="border-t border-slate-800" data-testid={`admin-learning-impact-simulator-recommendation-row-${idx}`}>
                <td className="px-2 py-1">{item.recommendation_type}</td>
                <td className="px-2 py-1">{item.strategy_id || item.family || "global"}</td>
                <td className="px-2 py-1">{item.reason}</td>
                <td className="px-2 py-1">{item.confidence}</td>
                <td className="px-2 py-1">{item.recommendation_scope}</td>
                <td className="px-2 py-1">{item.recommendation_score}</td>
                <td className="px-2 py-1">{item.actionable_state}</td>
                <td className="px-2 py-1">{item.severity}</td>
                <td className="px-2 py-1"><pre className={monoBox}>{safeJson(item.risk_impact)}</pre></td>
                <td className="px-2 py-1">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={simulating}
                    onClick={() => simulateFromRecommendation(item.id)}
                    data-testid={`admin-learning-impact-simulator-simulate-recommendation-button-${idx}`}
                  >
                    Simulate Impact
                  </Button>
                </td>
              </tr>
            ))}
            {(overview.recommendations || []).length === 0 && <tr><td className="px-2 py-2" colSpan={10} data-testid="admin-learning-impact-simulator-recommendations-empty">Recommendation yok.</td></tr>}
          </tbody>
        </table>
      </div>

      {loading && <div className="border border-slate-700 bg-slate-900 p-3 text-sm" data-testid="admin-learning-impact-simulator-loading">Yükleniyor...</div>}

      {simulationResult && (
        <article className="rounded border border-blue-700/60 bg-blue-950/20 p-4" data-testid="admin-learning-impact-simulator-result-panel">
          <p className="text-sm font-semibold" data-testid="admin-learning-impact-simulator-result-title">Simulation Output</p>
          <div className="mt-2 grid gap-3 md:grid-cols-2" data-testid="admin-learning-impact-simulator-result-grid">
            <pre className={monoBox} data-testid="admin-learning-impact-simulator-result-baseline-metrics">{safeJson(simulationResult.baseline_metrics)}</pre>
            <pre className={monoBox} data-testid="admin-learning-impact-simulator-result-projected-metrics">{safeJson(simulationResult.projected_metrics)}</pre>
            <pre className={monoBox} data-testid="admin-learning-impact-simulator-result-delta-metrics">{safeJson(simulationResult.delta_metrics)}</pre>
            <pre className={monoBox} data-testid="admin-learning-impact-simulator-result-sample-coverage">{safeJson(simulationResult.sample_coverage)}</pre>
            <pre className={monoBox} data-testid="admin-learning-impact-simulator-result-risk-aware-view">{safeJson(simulationResult.risk_aware_view)}</pre>
            <pre className={monoBox} data-testid="admin-learning-impact-simulator-result-portfolio-impact">{safeJson(simulationResult.portfolio_impact)}</pre>
            <pre className={monoBox} data-testid="admin-learning-impact-simulator-result-counterfactual">{safeJson(simulationResult.counterfactual_replay)}</pre>
            <pre className={monoBox} data-testid="admin-learning-impact-simulator-result-interaction-effects">{safeJson(simulationResult.interaction_effects)}</pre>
          </div>
        </article>
      )}
    </section>
  );
};
