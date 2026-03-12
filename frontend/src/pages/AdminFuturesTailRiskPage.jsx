import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const AdminFuturesTailRiskPage = () => {
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [tailPayload, setTailPayload] = useState(null);
  const [globalPayload, setGlobalPayload] = useState(null);
  const [strategyGovernance, setStrategyGovernance] = useState(null);
  const [clusterRisk, setClusterRisk] = useState(null);
  const [capitalDrift, setCapitalDrift] = useState(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setErrorMessage("");
    try {
      const [tailResponse, globalResponse, strategyResponse, clusterResponse, capitalResponse] = await Promise.all([
        apiClient.get("/admin/futures/tail-risk"),
        apiClient.get("/admin/futures/global-risk"),
        apiClient.get("/admin/futures/strategy-governance"),
        apiClient.get("/admin/futures/cluster-risk"),
        apiClient.get("/admin/futures/capital-drift"),
      ]);
      setTailPayload(tailResponse.data || null);
      setGlobalPayload(globalResponse.data || null);
      setStrategyGovernance(strategyResponse.data || null);
      setClusterRisk(clusterResponse.data || null);
      setCapitalDrift(capitalResponse.data || null);
    } catch (error) {
      const message = error?.response?.data?.detail || "Tail risk verisi alınamadı";
      setErrorMessage(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const tailScore = Number(tailPayload?.tail_risk_score || 0);
  const globalScore = Number(globalPayload?.global_risk_score || 0);
  const tailHistory = useMemo(() => tailPayload?.tail_risk_history || [], [tailPayload]);

  return (
    <section className="space-y-4" data-testid="admin-futures-tail-risk-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="tail-risk-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-black" data-testid="tail-risk-title">
          Futures Tail Risk
        </h2>
        <p className="mt-2 text-sm text-black/80" data-testid="tail-risk-description">
          Tail risk + global risk + cross-layer governance görünürlüğü.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3 border border-black/30 bg-orange-100 p-4" data-testid="tail-risk-toolbar">
        <Button className="border border-black bg-black text-orange-400 hover:bg-zinc-800" onClick={loadData} data-testid="tail-risk-refresh-button">
          Yenile
        </Button>
        <p className="text-sm text-black" data-testid="tail-risk-loading-text">loading: {String(loading)}</p>
        <p className="text-sm text-black" data-testid="tail-risk-updated-at-text">
          updated_at: {globalPayload?.generated_at ? new Date(globalPayload.generated_at).toLocaleString() : "-"}
        </p>
      </div>

      {loading && <div className="border border-black/25 bg-orange-50 p-4 text-sm" data-testid="tail-risk-loading-state">Tail risk yükleniyor...</div>}

      {!loading && Boolean(errorMessage) && (
        <div className="border border-red-700 bg-red-100 p-4 text-sm text-red-900" data-testid="tail-risk-error-state">
          Hata: {errorMessage}
        </div>
      )}

      {!loading && !errorMessage && (
        <>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4" data-testid="tail-risk-summary-grid">
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="tail-risk-score-card">
              <p className="text-xs uppercase">Tail Risk Score</p>
              <p className="text-xl font-bold" data-testid="tail-risk-score-value">{tailScore}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="global-risk-score-card">
              <p className="text-xs uppercase">Global Risk Score</p>
              <p className="text-xl font-bold" data-testid="global-risk-score-value">{globalScore}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="tail-risk-state-card">
              <p className="text-xs uppercase">Tail Risk State</p>
              <p className="text-xl font-bold" data-testid="tail-risk-state-value">{tailPayload?.risk_state || "NORMAL"}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="global-risk-state-card">
              <p className="text-xs uppercase">Global Risk State</p>
              <p className="text-xl font-bold" data-testid="global-risk-state-value">{globalPayload?.risk_state || "NORMAL"}</p>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2" data-testid="tail-risk-main-grid">
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="tail-risk-score-gauge-panel">
              <h3 className="text-lg font-bold" data-testid="tail-risk-score-gauge-title">Tail Risk Score Gauge</h3>
              <div className="mt-3 h-4 w-full border border-black/40 bg-white" data-testid="tail-risk-score-gauge-container">
                <div className="h-full bg-black" style={{ width: `${Math.max(5, Math.min(100, tailScore))}%` }} data-testid="tail-risk-score-gauge-fill" />
              </div>
            </div>

            <div className="border border-black/25 bg-orange-100 p-4" data-testid="tail-risk-liquidation-pressure-panel">
              <h3 className="text-lg font-bold" data-testid="tail-risk-liquidation-pressure-title">Liquidation Pressure Monitor</h3>
              <p className="mt-3 text-xs" data-testid="tail-risk-liquidation-pressure-value">
                liquidation_pressure={tailPayload?.liquidation_pressure ?? 0} · cascade_active={String(tailPayload?.liquidation_cascade?.active || false)}
              </p>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2" data-testid="tail-risk-secondary-grid">
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="tail-risk-volatility-chart-panel">
              <h3 className="text-lg font-bold" data-testid="tail-risk-volatility-chart-title">Volatility Spike Chart</h3>
              <div className="mt-3 space-y-1" data-testid="tail-risk-volatility-chart-list">
                {tailHistory.slice(-10).map((item, index) => (
                  <p className="text-xs" key={`${item?.ts}-${index}`} data-testid={`tail-risk-volatility-point-${index}`}>
                    {item?.ts}: score={item?.tail_risk_score}
                  </p>
                ))}
                {tailHistory.length === 0 && <p className="text-xs" data-testid="tail-risk-volatility-empty">Volatility geçmişi yok.</p>}
              </div>
            </div>

            <div className="border border-black/25 bg-orange-100 p-4" data-testid="tail-risk-exchange-health-panel">
              <h3 className="text-lg font-bold" data-testid="tail-risk-exchange-health-title">Exchange Health Status</h3>
              <p className="mt-3 text-xs" data-testid="tail-risk-exchange-health-value">
                active={String(tailPayload?.exchange_health?.active || false)} · severity={tailPayload?.exchange_health?.severity || "INFO"} · reasons={(tailPayload?.exchange_health?.reason || []).join(",")}
              </p>
            </div>
          </div>

          <div className="border border-black/25 bg-orange-100 p-4" data-testid="tail-risk-integration-panel">
            <h3 className="text-lg font-bold" data-testid="tail-risk-integration-title">Cross-Layer Risk Integration</h3>
            <div className="mt-3 space-y-1" data-testid="tail-risk-integration-list">
              <p className="text-xs" data-testid="tail-risk-integration-strategy-state">
                strategy_global_state={strategyGovernance?.global_risk_state || "NORMAL"} · strategy_tail_score={strategyGovernance?.tail_risk_score ?? 0}
              </p>
              <p className="text-xs" data-testid="tail-risk-integration-cluster-state">
                cluster_risk_state={clusterRisk?.risk_state || "NORMAL"} · cluster_alerts={(clusterRisk?.cluster_risk_alerts || []).length}
              </p>
              <p className="text-xs" data-testid="tail-risk-integration-capital-state">
                capital_drift_state={capitalDrift?.drift_state || "NORMAL"} · capital_drift_events={(capitalDrift?.capital_drift_events || []).length}
              </p>
            </div>
          </div>
        </>
      )}
    </section>
  );
};
