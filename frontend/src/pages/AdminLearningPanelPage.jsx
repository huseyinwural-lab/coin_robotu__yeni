import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const AdminLearningPanelPage = () => {
  const [overview, setOverview] = useState({ strategy_memory: [], family_memory: [], recommendations: [] });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const loadOverview = async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/admin/learning/overview");
      setOverview(data || { strategy_memory: [], family_memory: [], recommendations: [] });
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
      </div>

      {loading ? (
        <div className="border border-slate-700 bg-slate-900 p-4 text-sm" data-testid="admin-learning-panel-loading">Yükleniyor...</div>
      ) : (
        <>
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
                    <td className="px-2 py-1">{row.recent_rolling_score}</td>
                    <td className="px-2 py-1">{row.decay_adjusted_quality_score}</td>
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
                </div>
              ))}
              {(overview.recommendations || []).length === 0 && <p className="text-xs" data-testid="admin-learning-recommendation-empty">Öneri yok.</p>}
            </div>
          </div>
        </>
      )}
    </section>
  );
};
