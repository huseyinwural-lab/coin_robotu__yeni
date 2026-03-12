import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const AdminFuturesCapitalGovernancePage = () => {
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [budgetPayload, setBudgetPayload] = useState(null);
  const [usagePayload, setUsagePayload] = useState(null);
  const [driftPayload, setDriftPayload] = useState(null);
  const [globalRiskPayload, setGlobalRiskPayload] = useState(null);
  const [legacyRows, setLegacyRows] = useState([]);

  const loadData = useCallback(async () => {
    setLoading(true);
    setErrorMessage("");
    try {
      const [budgetResponse, usageResponse, driftResponse, globalRiskResponse, strategyStatusResponse] = await Promise.all([
        apiClient.get("/admin/futures/capital-budget"),
        apiClient.get("/admin/futures/capital-usage"),
        apiClient.get("/admin/futures/capital-drift"),
        apiClient.get("/admin/futures/global-risk"),
        apiClient.get("/admin/futures/strategy/status"),
      ]);
      setBudgetPayload(budgetResponse.data || null);
      setUsagePayload(usageResponse.data || null);
      setDriftPayload(driftResponse.data || null);
      setGlobalRiskPayload(globalRiskResponse.data || null);
      setLegacyRows(strategyStatusResponse.data?.legacy_formula_observability || []);
    } catch (error) {
      const message = error?.response?.data?.detail || "Capital governance verisi alınamadı";
      setErrorMessage(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const budgetRows = useMemo(() => budgetPayload?.strategy_capital_budget || [], [budgetPayload]);
  const usageRows = useMemo(() => usagePayload?.strategy_capital_usage || [], [usagePayload]);
  const driftEvents = useMemo(() => driftPayload?.capital_drift_events || [], [driftPayload]);

  return (
    <section className="space-y-4" data-testid="admin-futures-capital-governance-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="capital-governance-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-black" data-testid="capital-governance-title">
          Futures Capital Governance
        </h2>
        <p className="mt-2 text-sm text-black/80" data-testid="capital-governance-description">
          Strategy budget, usage, drift ve portfolio risk budget görünürlüğü.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3 border border-black/30 bg-orange-100 p-4" data-testid="capital-governance-toolbar">
        <Button className="border border-black bg-black text-orange-400 hover:bg-zinc-800" onClick={loadData} data-testid="capital-governance-refresh-button">
          Yenile
        </Button>
        <p className="text-sm text-black" data-testid="capital-governance-loading-text">loading: {String(loading)}</p>
        <p className="text-sm text-black" data-testid="capital-governance-updated-at-text">
          updated_at: {driftPayload?.generated_at ? new Date(driftPayload.generated_at).toLocaleString() : "-"}
        </p>
      </div>

      {loading && <div className="border border-black/25 bg-orange-50 p-4 text-sm" data-testid="capital-governance-loading-state">Capital governance yükleniyor...</div>}

      {!loading && Boolean(errorMessage) && (
        <div className="border border-red-700 bg-red-100 p-4 text-sm text-red-900" data-testid="capital-governance-error-state">
          Hata: {errorMessage}
        </div>
      )}

      {!loading && !errorMessage && (
        <>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-5" data-testid="capital-governance-summary-grid">
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="capital-governance-summary-equity-card">
              <p className="text-xs uppercase">Portfolio Equity</p>
              <p className="text-xl font-bold" data-testid="capital-governance-summary-equity-value">
                {budgetPayload?.portfolio_capital_registry?.portfolio_equity ?? 0}
              </p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="capital-governance-summary-available-card">
              <p className="text-xs uppercase">Available Capital</p>
              <p className="text-xl font-bold" data-testid="capital-governance-summary-available-value">
                {budgetPayload?.portfolio_capital_registry?.available_capital ?? 0}
              </p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="capital-governance-summary-risk-budget-card">
              <p className="text-xs uppercase">Risk Budget</p>
              <p className="text-xl font-bold" data-testid="capital-governance-summary-risk-budget-value">
                {usagePayload?.portfolio_risk_budget ?? 0}
              </p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="capital-governance-summary-drift-card">
              <p className="text-xs uppercase">Drift Alerts</p>
              <p className="text-xl font-bold" data-testid="capital-governance-summary-drift-value">{driftEvents.length}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="capital-governance-summary-global-risk-card">
              <p className="text-xs uppercase">Global Risk</p>
              <p className="text-xl font-bold" data-testid="capital-governance-summary-global-risk-value">
                {globalRiskPayload?.global_risk_score ?? 0} ({globalRiskPayload?.risk_state || "NORMAL"})
              </p>
            </div>
          </div>

          <div className="border border-black/25 bg-orange-100 p-4" data-testid="capital-governance-allocation-panel">
            <h3 className="text-lg font-bold" data-testid="capital-governance-allocation-title">Strategy Capital Allocation</h3>
            <div className="mt-3 space-y-1" data-testid="capital-governance-allocation-list">
              {budgetRows.map((row, index) => (
                <p className="text-xs" key={`${row?.strategy_id}-${index}`} data-testid={`capital-governance-allocation-item-${index}`}>
                  {row?.strategy_id}: budget={row?.strategy_capital_budget} · used={row?.strategy_capital_used} · available={row?.strategy_capital_available} · state={row?.risk_state}
                </p>
              ))}
              {budgetRows.length === 0 && <p className="text-xs" data-testid="capital-governance-allocation-empty">Allocation verisi yok.</p>}
            </div>
          </div>

          <div className="border border-black/25 bg-orange-100 p-4" data-testid="capital-governance-legacy-shadow-panel">
            <h3 className="text-lg font-bold" data-testid="capital-governance-legacy-shadow-title">Legacy Formula (Capital Governance View)</h3>
            <div className="mt-3 space-y-1" data-testid="capital-governance-legacy-shadow-list">
              {legacyRows.map((row, index) => (
                <p className="text-xs" key={`${row?.strategy}-${index}`} data-testid={`capital-governance-legacy-shadow-item-${index}`}>
                  {row?.strategy}: family={row?.family_code} · source={row?.source_type} · shadow={row?.shadow_status} · signal_frequency={row?.signal_frequency} · shadow_pnl={row?.shadow_pnl} · false_breakout_rate={row?.false_breakout_rate} · confidence_drift={row?.confidence_drift}
                </p>
              ))}
              {legacyRows.length === 0 && <p className="text-xs" data-testid="capital-governance-legacy-shadow-empty">Legacy formula metriği yok.</p>}
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2" data-testid="capital-governance-usage-grid">
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="capital-governance-usage-bars-panel">
              <h3 className="text-lg font-bold" data-testid="capital-governance-usage-bars-title">Capital Usage Bars</h3>
              <div className="mt-3 space-y-2" data-testid="capital-governance-usage-bars-list">
                {usageRows.map((row, index) => {
                  const used = Number(row?.capital_used || 0);
                  const total = used + Number(row?.capital_remaining || 0);
                  const width = total > 0 ? Math.max(6, Math.min(100, (used / total) * 100)) : 6;
                  return (
                    <div className="space-y-1" key={`${row?.strategy_id}-${index}`} data-testid={`capital-governance-usage-row-${index}`}>
                      <p className="text-xs" data-testid={`capital-governance-usage-label-${index}`}>
                        {row?.strategy_id}: used={row?.capital_used} · remaining={row?.capital_remaining} · risk={row?.risk_state}
                      </p>
                      <div className="h-3 w-full border border-black/40 bg-white" data-testid={`capital-governance-usage-bar-container-${index}`}>
                        <div className="h-full bg-black" style={{ width: `${width}%` }} data-testid={`capital-governance-usage-bar-fill-${index}`} />
                      </div>
                    </div>
                  );
                })}
                {usageRows.length === 0 && <p className="text-xs" data-testid="capital-governance-usage-empty">Usage verisi yok.</p>}
              </div>
            </div>

            <div className="border border-black/25 bg-orange-100 p-4" data-testid="capital-governance-drift-alerts-panel">
              <h3 className="text-lg font-bold" data-testid="capital-governance-drift-alerts-title">Capital Drift Alerts</h3>
              <div className="mt-3 space-y-1" data-testid="capital-governance-drift-alerts-list">
                {driftEvents.map((row, index) => (
                  <p className="text-xs" key={`${row?.strategy_id}-${index}`} data-testid={`capital-governance-drift-alert-item-${index}`}>
                    {row?.strategy_id}: severity={row?.drift_severity} · reasons={(row?.reasons || []).join(",")} · used={row?.capital_used} / budget={row?.capital_budget}
                  </p>
                ))}
                {driftEvents.length === 0 && <p className="text-xs" data-testid="capital-governance-drift-alert-empty">Drift alarmı yok.</p>}
              </div>
            </div>
          </div>

          <div className="border border-black/25 bg-orange-100 p-4" data-testid="capital-governance-drift-monitor-panel">
            <h3 className="text-lg font-bold" data-testid="capital-governance-drift-monitor-title">Capital Budget Drift Monitor</h3>
            <div className="mt-3 space-y-1" data-testid="capital-governance-drift-monitor-list">
              {Object.entries(driftPayload?.capital_drift_by_strategy || {}).map(([strategyId, row], index) => (
                <p className="text-xs" key={`${strategyId}-${index}`} data-testid={`capital-governance-drift-monitor-item-${index}`}>
                  {strategyId}: drift_state={row?.drift_state} · growth_ratio={row?.growth_ratio} · reasons={(row?.reasons || []).join(",")}
                </p>
              ))}
              {Object.keys(driftPayload?.capital_drift_by_strategy || {}).length === 0 && (
                <p className="text-xs" data-testid="capital-governance-drift-monitor-empty">Drift monitor verisi yok.</p>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
};
