import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const AdminFuturesScalingValidationPage = () => {
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [validationPayload, setValidationPayload] = useState(null);
  const [reportPayload, setReportPayload] = useState(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setErrorMessage("");
    try {
      const [validationResponse, reportResponse] = await Promise.all([
        apiClient.get("/admin/futures/scaling-validation"),
        apiClient.get("/admin/futures/scaling-report"),
      ]);
      setValidationPayload(validationResponse.data || null);
      setReportPayload(reportResponse.data || null);
    } catch (error) {
      const message = error?.response?.data?.detail || "Scaling validation verisi alınamadı";
      setErrorMessage(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const rows = useMemo(() => validationPayload?.scaling_performance_report || [], [validationPayload]);
  const stressRows = useMemo(() => validationPayload?.stress_replay_dashboard || [], [validationPayload]);

  return (
    <section className="space-y-4" data-testid="admin-futures-scaling-validation-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="scaling-validation-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-black" data-testid="scaling-validation-title">
          Futures Scaling Validation
        </h2>
        <p className="mt-2 text-sm text-black/80" data-testid="scaling-validation-description">
          1M/10M/100M sermaye seviyelerinde performans kırılma analizi.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3 border border-black/30 bg-orange-100 p-4" data-testid="scaling-validation-toolbar">
        <Button className="border border-black bg-black text-orange-400 hover:bg-zinc-800" onClick={loadData} data-testid="scaling-validation-refresh-button">
          Yenile
        </Button>
        <p className="text-sm text-black" data-testid="scaling-validation-loading-text">loading: {String(loading)}</p>
        <p className="text-sm text-black" data-testid="scaling-validation-updated-at-text">
          updated_at: {validationPayload?.generated_at ? new Date(validationPayload.generated_at).toLocaleString() : "-"}
        </p>
      </div>

      {loading && <div className="border border-black/25 bg-orange-50 p-4 text-sm" data-testid="scaling-validation-loading-state">Scaling validation yükleniyor...</div>}
      {!loading && Boolean(errorMessage) && (
        <div className="border border-red-700 bg-red-100 p-4 text-sm text-red-900" data-testid="scaling-validation-error-state">
          Hata: {errorMessage}
        </div>
      )}

      {!loading && !errorMessage && (
        <>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4" data-testid="scaling-validation-summary-grid">
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="scaling-validation-robustness-score-card">
              <p className="text-xs uppercase">Robustness Score</p>
              <p className="text-xl font-bold" data-testid="scaling-validation-robustness-score-value">{validationPayload?.scaling_robustness_score ?? 0}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="scaling-validation-robustness-state-card">
              <p className="text-xs uppercase">Robustness State</p>
              <p className="text-xl font-bold" data-testid="scaling-validation-robustness-state-value">{validationPayload?.robustness_state || "unstable"}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="scaling-validation-capital-cap-card">
              <p className="text-xs uppercase">Capital Cap Recommendation</p>
              <p className="text-xl font-bold" data-testid="scaling-validation-capital-cap-value">
                {validationPayload?.scaling_governance_actions?.capital_cap_recommendation ?? 0}
              </p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="scaling-validation-downshift-card">
              <p className="text-xs uppercase">Risk Downshift</p>
              <p className="text-xl font-bold" data-testid="scaling-validation-downshift-value">
                {String(validationPayload?.scaling_governance_actions?.risk_downshift || false)}
              </p>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2" data-testid="scaling-validation-main-grid">
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="scaling-validation-capital-comparison-panel">
              <h3 className="text-lg font-bold" data-testid="scaling-validation-capital-comparison-title">Capital Scaling Comparison</h3>
              <div className="mt-3 space-y-1" data-testid="scaling-validation-capital-comparison-list">
                {rows.map((row, index) => (
                  <p className="text-xs" key={`${row?.capital_level}-${index}`} data-testid={`scaling-validation-capital-row-${index}`}>
                    capital={row?.capital_level} · pnl={row?.pnl} · slippage={row?.slippage} · execution_quality={row?.execution_quality}
                  </p>
                ))}
                {rows.length === 0 && <p className="text-xs" data-testid="scaling-validation-capital-empty">Scaling karşılaştırma verisi yok.</p>}
              </div>
            </div>

            <div className="border border-black/25 bg-orange-100 p-4" data-testid="scaling-validation-slippage-chart-panel">
              <h3 className="text-lg font-bold" data-testid="scaling-validation-slippage-chart-title">Slippage vs Capital Chart</h3>
              <div className="mt-3 space-y-1" data-testid="scaling-validation-slippage-chart-list">
                {rows.map((row, index) => (
                  <p className="text-xs" key={`${row?.capital_level}-slippage-${index}`} data-testid={`scaling-validation-slippage-item-${index}`}>
                    {row?.capital_level}: slippage={row?.slippage}
                  </p>
                ))}
              </div>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2" data-testid="scaling-validation-secondary-grid">
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="scaling-validation-pnl-stability-panel">
              <h3 className="text-lg font-bold" data-testid="scaling-validation-pnl-stability-title">PnL Stability Chart</h3>
              <div className="mt-3 space-y-1" data-testid="scaling-validation-pnl-stability-list">
                {rows.map((row, index) => (
                  <p className="text-xs" key={`${row?.capital_level}-pnl-${index}`} data-testid={`scaling-validation-pnl-item-${index}`}>
                    {row?.capital_level}: pnl={row?.pnl}
                  </p>
                ))}
              </div>
            </div>

            <div className="border border-black/25 bg-orange-100 p-4" data-testid="scaling-validation-liquidity-impact-panel">
              <h3 className="text-lg font-bold" data-testid="scaling-validation-liquidity-impact-title">Liquidity Impact Chart</h3>
              <div className="mt-3 space-y-1" data-testid="scaling-validation-liquidity-impact-list">
                {rows.map((row, index) => (
                  <p className="text-xs" key={`${row?.capital_level}-liq-${index}`} data-testid={`scaling-validation-liquidity-item-${index}`}>
                    {row?.capital_level}: liquidity_stress={row?.liquidity_stress}
                  </p>
                ))}
              </div>
            </div>
          </div>

          <div className="border border-black/25 bg-orange-100 p-4" data-testid="scaling-validation-stress-replay-dashboard-panel">
            <h3 className="text-lg font-bold" data-testid="scaling-validation-stress-replay-dashboard-title">Stress Replay Dashboard</h3>
            <div className="mt-3 space-y-1" data-testid="scaling-validation-stress-replay-dashboard-list">
              {stressRows.map((row, index) => (
                <p className="text-xs" key={`${row?.scenario}-${index}`} data-testid={`scaling-validation-stress-item-${index}`}>
                  {row?.scenario}: {JSON.stringify(row?.replayed_metrics || {})}
                </p>
              ))}
              {stressRows.length === 0 && <p className="text-xs" data-testid="scaling-validation-stress-empty">Stress replay verisi yok.</p>}
            </div>
          </div>
        </>
      )}
    </section>
  );
};
