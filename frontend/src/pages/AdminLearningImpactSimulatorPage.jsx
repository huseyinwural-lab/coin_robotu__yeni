import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const AdminLearningImpactSimulatorPage = () => {
  const [overview, setOverview] = useState({ strategy_memory: [], family_memory: [], recommendations: [] });
  const [loading, setLoading] = useState(true);
  const [simulating, setSimulating] = useState(false);
  const [simulationResult, setSimulationResult] = useState(null);
  const [form, setForm] = useState({
    strategy_id: "",
    family: "",
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
        family: String(form.family || "").trim() || null,
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

      <div className="grid gap-2 md:grid-cols-5" data-testid="admin-learning-impact-simulator-form-grid">
        <input
          value={form.strategy_id}
          onChange={(event) => setForm((prev) => ({ ...prev, strategy_id: event.target.value }))}
          placeholder="strategy_id"
          className="h-10 rounded border border-slate-700 bg-black px-3 text-xs"
          data-testid="admin-learning-impact-simulator-strategy-id-input"
        />
        <input
          value={form.family}
          onChange={(event) => setForm((prev) => ({ ...prev, family: event.target.value }))}
          placeholder="family"
          className="h-10 rounded border border-slate-700 bg-black px-3 text-xs"
          data-testid="admin-learning-impact-simulator-family-input"
        />
        <select
          value={form.recommendation_type}
          onChange={(event) => setForm((prev) => ({ ...prev, recommendation_type: event.target.value }))}
          className="h-10 rounded border border-slate-700 bg-black px-3 text-xs"
          data-testid="admin-learning-impact-simulator-recommendation-type-select"
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
        <table className="min-w-[900px] text-xs" data-testid="admin-learning-impact-simulator-recommendations-table">
          <thead>
            <tr>
              <th className="px-2 py-1 text-left">type</th>
              <th className="px-2 py-1 text-left">target</th>
              <th className="px-2 py-1 text-left">severity</th>
              <th className="px-2 py-1 text-left">note</th>
              <th className="px-2 py-1 text-left">action</th>
            </tr>
          </thead>
          <tbody>
            {(overview.recommendations || []).map((item, idx) => (
              <tr key={item.id} className="border-t border-slate-800" data-testid={`admin-learning-impact-simulator-recommendation-row-${idx}`}>
                <td className="px-2 py-1">{item.recommendation_type}</td>
                <td className="px-2 py-1">{item.strategy_id || item.family || "global"}</td>
                <td className="px-2 py-1">{item.severity}</td>
                <td className="px-2 py-1">{item.note}</td>
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
            {(overview.recommendations || []).length === 0 && <tr><td className="px-2 py-2" colSpan={5} data-testid="admin-learning-impact-simulator-recommendations-empty">Recommendation yok.</td></tr>}
          </tbody>
        </table>
      </div>

      {loading && <div className="border border-slate-700 bg-slate-900 p-3 text-sm" data-testid="admin-learning-impact-simulator-loading">Yükleniyor...</div>}

      {simulationResult && (
        <article className="rounded border border-blue-700/60 bg-blue-950/20 p-4" data-testid="admin-learning-impact-simulator-result-panel">
          <p className="text-sm font-semibold" data-testid="admin-learning-impact-simulator-result-title">Simulation Output</p>
          <div className="mt-2 grid gap-1 md:grid-cols-2" data-testid="admin-learning-impact-simulator-result-grid">
            <p className="text-xs" data-testid="admin-learning-impact-simulator-result-projected-risk">projected_risk_score: {simulationResult.projected_risk_score}</p>
            <p className="text-xs" data-testid="admin-learning-impact-simulator-result-gate">projected_gate_decision: {simulationResult.projected_gate_decision}</p>
            <p className="text-xs" data-testid="admin-learning-impact-simulator-result-hit-delta">expected_hit_rate_delta: {simulationResult.expected_hit_rate_delta}</p>
            <p className="text-xs" data-testid="admin-learning-impact-simulator-result-return-delta">expected_avg_return_delta: {simulationResult.expected_avg_return_delta}</p>
            <p className="text-xs" data-testid="admin-learning-impact-simulator-result-drift-delta">allocation_drift_delta: {simulationResult.allocation_drift_delta}</p>
            <p className="text-xs" data-testid="admin-learning-impact-simulator-result-hedge-score">hedge_effect_score: {simulationResult.hedge_effect_score}</p>
          </div>
        </article>
      )}
    </section>
  );
};
