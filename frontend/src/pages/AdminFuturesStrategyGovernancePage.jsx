import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const AdminFuturesStrategyGovernancePage = () => {
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [healthPayload, setHealthPayload] = useState(null);
  const [governancePayload, setGovernancePayload] = useState(null);
  const [compareA, setCompareA] = useState("");
  const [compareB, setCompareB] = useState("");

  const loadData = useCallback(
    async ({ withCompare = false } = {}) => {
      setLoading(true);
      setErrorMessage("");
      try {
        const params = withCompare && compareA && compareB ? { compare_a: compareA, compare_b: compareB } : undefined;
        const [healthResponse, governanceResponse] = await Promise.all([
          apiClient.get("/admin/futures/strategy-health"),
          apiClient.get("/admin/futures/strategy-governance", { params }),
        ]);

        const healthData = healthResponse.data || null;
        const governanceData = governanceResponse.data || null;
        setHealthPayload(healthData);
        setGovernancePayload(governanceData);

        const strategyRows = healthData?.strategy_health_score || [];
        if (strategyRows.length >= 2 && !compareA && !compareB) {
          setCompareA(strategyRows[0]?.strategy || "");
          setCompareB(strategyRows[1]?.strategy || "");
        }
      } catch (error) {
        const message = error?.response?.data?.detail || "Governance verisi alınamadı";
        setErrorMessage(message);
        toast.error(message);
      } finally {
        setLoading(false);
      }
    },
    [compareA, compareB],
  );

  useEffect(() => {
    loadData();
  }, [loadData]);

  const healthRows = useMemo(() => healthPayload?.strategy_health_score || [], [healthPayload]);
  const throttleRows = useMemo(() => governancePayload?.throttle_state || [], [governancePayload]);
  const disableRows = useMemo(() => governancePayload?.disable_state || [], [governancePayload]);
  const decayEvents = useMemo(() => governancePayload?.decay_events || [], [governancePayload]);
  const lifecycleRows = useMemo(() => governancePayload?.lifecycle_state || [], [governancePayload]);
  const compareMetrics = useMemo(() => governancePayload?.strategy_compare_mode?.metrics || [], [governancePayload]);
  const clusterOverlayRows = useMemo(() => governancePayload?.cluster_risk_overlay || [], [governancePayload]);
  const weeklySummary = useMemo(
    () => governancePayload?.strategy_compare_mode?.weekly_auto_summary || { strategy_summaries: [], comparative_deltas: {} },
    [governancePayload],
  );

  const disabledOnly = useMemo(() => disableRows.filter((item) => item?.disable_state === "DISABLED"), [disableRows]);
  const throttledOnly = useMemo(() => throttleRows.filter((item) => item?.throttle_level !== "NONE"), [throttleRows]);

  const avgHealthScore = useMemo(() => {
    if (!healthRows.length) return 0;
    const total = healthRows.reduce((acc, item) => acc + Number(item?.strategy_health_score || 0), 0);
    return (total / healthRows.length).toFixed(2);
  }, [healthRows]);

  return (
    <section className="space-y-4" data-testid="admin-futures-strategy-governance-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="strategy-governance-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-black" data-testid="strategy-governance-title">
          Futures Strategy Governance
        </h2>
        <p className="mt-2 text-sm text-black/80" data-testid="strategy-governance-description">
          Health score, throttle/disable lifecycle ve compare mode tek panelde.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3 border border-black/30 bg-orange-100 p-4" data-testid="strategy-governance-toolbar">
        <Button
          className="border border-black bg-black text-orange-400 hover:bg-zinc-800"
          onClick={() => loadData()}
          data-testid="strategy-governance-refresh-button"
        >
          Yenile
        </Button>
        <p className="text-sm text-black" data-testid="strategy-governance-loading-text">
          loading: {String(loading)}
        </p>
        <p className="text-sm text-black" data-testid="strategy-governance-updated-at-text">
          updated_at: {governancePayload?.generated_at ? new Date(governancePayload.generated_at).toLocaleString() : "-"}
        </p>
      </div>

      {loading && (
        <div className="border border-black/25 bg-orange-50 p-4 text-sm" data-testid="strategy-governance-loading-state">
          Governance verisi yükleniyor...
        </div>
      )}

      {!loading && Boolean(errorMessage) && (
        <div className="border border-red-700 bg-red-100 p-4 text-sm text-red-900" data-testid="strategy-governance-error-state">
          Hata: {errorMessage}
        </div>
      )}

      {!loading && !errorMessage && (
        <>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4" data-testid="strategy-governance-summary-grid">
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="strategy-governance-summary-health-card">
              <p className="text-xs uppercase">Avg Health Score</p>
              <p className="text-xl font-bold" data-testid="strategy-governance-summary-health-value">{avgHealthScore}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="strategy-governance-summary-throttled-card">
              <p className="text-xs uppercase">Throttled</p>
              <p className="text-xl font-bold" data-testid="strategy-governance-summary-throttled-value">{throttledOnly.length}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="strategy-governance-summary-disabled-card">
              <p className="text-xs uppercase">Disabled</p>
              <p className="text-xl font-bold" data-testid="strategy-governance-summary-disabled-value">{disabledOnly.length}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="strategy-governance-summary-decay-card">
              <p className="text-xs uppercase">Decay Events</p>
              <p className="text-xl font-bold" data-testid="strategy-governance-summary-decay-value">{decayEvents.length}</p>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2" data-testid="strategy-governance-health-grid">
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="strategy-governance-health-heatmap-panel">
              <h3 className="text-lg font-bold" data-testid="strategy-governance-health-heatmap-title">Strategy Health Heatmap</h3>
              <div className="mt-3 space-y-2" data-testid="strategy-governance-health-heatmap-list">
                {healthRows.map((row, index) => {
                  const width = Math.max(8, Number(row?.strategy_health_score || 0));
                  return (
                    <div key={`${row?.strategy}-${index}`} className="space-y-1" data-testid={`strategy-governance-health-row-${index}`}>
                      <p className="text-xs" data-testid={`strategy-governance-health-label-${index}`}>
                        {row?.strategy} · score={row?.strategy_health_score} · drawdown={row?.drawdown_state}
                      </p>
                      <div className="h-3 w-full border border-black/40 bg-white" data-testid={`strategy-governance-health-bar-container-${index}`}>
                        <div
                          className="h-full bg-black"
                          style={{ width: `${width}%` }}
                          data-testid={`strategy-governance-health-bar-fill-${index}`}
                        />
                      </div>
                    </div>
                  );
                })}
                {healthRows.length === 0 && <p className="text-xs" data-testid="strategy-governance-health-empty">Health verisi yok.</p>}
              </div>
            </div>

            <div className="border border-black/25 bg-orange-100 p-4" data-testid="strategy-governance-throttle-panel">
              <h3 className="text-lg font-bold" data-testid="strategy-governance-throttle-title">Throttle Status</h3>
              <div className="mt-3 space-y-1" data-testid="strategy-governance-throttle-list">
                {throttleRows.map((row, index) => (
                  <p className="text-xs" key={`${row?.strategy}-${index}`} data-testid={`strategy-governance-throttle-item-${index}`}>
                    {row?.strategy}: level={row?.throttle_level} · conf_cap={row?.confidence_clamp} · max_pos={row?.max_position_ratio} · max_freq={row?.max_signals_per_cycle}
                  </p>
                ))}
                {throttleRows.length === 0 && <p className="text-xs" data-testid="strategy-governance-throttle-empty">Throttle verisi yok.</p>}
              </div>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2" data-testid="strategy-governance-decay-grid">
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="strategy-governance-disable-events-panel">
              <h3 className="text-lg font-bold" data-testid="strategy-governance-disable-events-title">Disable Events</h3>
              <div className="mt-3 space-y-1" data-testid="strategy-governance-disable-events-list">
                {disabledOnly.map((row, index) => (
                  <p className="text-xs" key={`${row?.strategy}-${index}`} data-testid={`strategy-governance-disable-item-${index}`}>
                    {row?.strategy}: disable_state={row?.disable_state} · reasons={(row?.reasons || []).join(",")}
                  </p>
                ))}
                {disabledOnly.length === 0 && <p className="text-xs" data-testid="strategy-governance-disable-empty">Disable event yok.</p>}
              </div>
            </div>

            <div className="border border-black/25 bg-orange-100 p-4" data-testid="strategy-governance-pnl-decay-panel">
              <h3 className="text-lg font-bold" data-testid="strategy-governance-pnl-decay-title">PnL Decay Timeline</h3>
              <div className="mt-3 space-y-1" data-testid="strategy-governance-pnl-decay-list">
                {healthRows.map((row, index) => (
                  <p className="text-xs" key={`${row?.strategy}-${index}`} data-testid={`strategy-governance-pnl-decay-item-${index}`}>
                    {row?.strategy}: pnl_rolling={row?.strategy_pnl_rolling} · health={row?.strategy_health_score}
                  </p>
                ))}
                {healthRows.length === 0 && <p className="text-xs" data-testid="strategy-governance-pnl-decay-empty">Timeline verisi yok.</p>}
              </div>
            </div>
          </div>

          <div className="border border-black/25 bg-orange-100 p-4" data-testid="strategy-governance-confidence-drift-panel">
            <h3 className="text-lg font-bold" data-testid="strategy-governance-confidence-drift-title">Confidence vs Result Drift</h3>
            <div className="mt-3 grid gap-2 md:grid-cols-2" data-testid="strategy-governance-confidence-drift-grid">
              {healthRows.map((row, index) => (
                <p className="text-xs" key={`${row?.strategy}-${index}`} data-testid={`strategy-governance-confidence-drift-item-${index}`}>
                  {row?.strategy}: divergence={row?.strategy_confidence_vs_result} · components={JSON.stringify(row?.health_components || {})}
                </p>
              ))}
              {healthRows.length === 0 && <p className="text-xs" data-testid="strategy-governance-confidence-drift-empty">Drift verisi yok.</p>}
            </div>
          </div>

          <div className="border border-black/25 bg-orange-100 p-4" data-testid="strategy-governance-compare-mode-panel">
            <div className="flex flex-wrap items-center gap-2" data-testid="strategy-governance-compare-controls">
              <h3 className="mr-3 text-lg font-bold" data-testid="strategy-governance-compare-title">Strategy Compare Mode</h3>
              <select
                className="border border-black/40 bg-white px-3 py-2 text-sm"
                value={compareA}
                onChange={(event) => setCompareA(event.target.value)}
                data-testid="strategy-governance-compare-a-select"
              >
                {healthRows.map((row) => (
                  <option value={row?.strategy} key={`compare-a-${row?.strategy}`}>
                    {row?.strategy}
                  </option>
                ))}
              </select>
              <select
                className="border border-black/40 bg-white px-3 py-2 text-sm"
                value={compareB}
                onChange={(event) => setCompareB(event.target.value)}
                data-testid="strategy-governance-compare-b-select"
              >
                {healthRows.map((row) => (
                  <option value={row?.strategy} key={`compare-b-${row?.strategy}`}>
                    {row?.strategy}
                  </option>
                ))}
              </select>
              <Button
                className="border border-black bg-black text-orange-400 hover:bg-zinc-800"
                onClick={() => loadData({ withCompare: true })}
                data-testid="strategy-governance-compare-apply-button"
              >
                Karşılaştır
              </Button>
            </div>

            <div className="mt-3 space-y-2" data-testid="strategy-governance-compare-metrics-list">
              {compareMetrics.map((item, index) => (
                <p className="text-xs" key={`${item?.strategy}-${index}`} data-testid={`strategy-governance-compare-metric-item-${index}`}>
                  {item?.strategy}: pnl={item?.pnl} · exec_q={item?.execution_quality} · freq={item?.signal_frequency} · win={item?.win_rate} · health={item?.health_score}
                </p>
              ))}
              {compareMetrics.length === 0 && <p className="text-xs" data-testid="strategy-governance-compare-metric-empty">Compare metrik verisi yok.</p>}
            </div>

            <div className="mt-3 border border-black/20 bg-orange-50 p-3" data-testid="strategy-governance-weekly-summary-panel">
              <h4 className="text-sm font-bold" data-testid="strategy-governance-weekly-summary-title">Weekly Auto Summary (Structured)</h4>
              <p className="mt-1 text-xs" data-testid="strategy-governance-weekly-summary-window">
                window_days: {weeklySummary?.window_days ?? 7}
              </p>
              <div className="mt-2 space-y-1" data-testid="strategy-governance-weekly-summary-list">
                {(weeklySummary?.strategy_summaries || []).map((item, index) => (
                  <p className="text-xs" key={`${item?.strategy}-${index}`} data-testid={`strategy-governance-weekly-summary-item-${index}`}>
                    {item?.strategy}: avg_pnl={item?.avg_pnl} · avg_exec_q={item?.avg_execution_quality} · avg_freq={item?.avg_signal_frequency} · avg_win={item?.avg_win_rate} · avg_health={item?.avg_health_score}
                  </p>
                ))}
                {(weeklySummary?.strategy_summaries || []).length === 0 && (
                  <p className="text-xs" data-testid="strategy-governance-weekly-summary-empty">Weekly summary verisi yok.</p>
                )}
              </div>
              <p className="mt-2 text-xs" data-testid="strategy-governance-weekly-summary-deltas">
                comparative_deltas: {JSON.stringify(weeklySummary?.comparative_deltas || {})}
              </p>
            </div>
          </div>

          <div className="border border-black/25 bg-orange-100 p-4" data-testid="strategy-governance-lifecycle-panel">
            <h3 className="text-lg font-bold" data-testid="strategy-governance-lifecycle-title">Lifecycle State</h3>
            <div className="mt-3 space-y-1" data-testid="strategy-governance-lifecycle-list">
              {lifecycleRows.map((row, index) => (
                <p className="text-xs" key={`${row?.strategy}-${index}`} data-testid={`strategy-governance-lifecycle-item-${index}`}>
                  {row?.strategy}: state={row?.lifecycle_state} · last_transition_at={row?.last_transition_at} · reason={row?.last_transition_reason}
                </p>
              ))}
              {lifecycleRows.length === 0 && <p className="text-xs" data-testid="strategy-governance-lifecycle-empty">Lifecycle verisi yok.</p>}
            </div>
          </div>

          <div className="border border-black/25 bg-orange-100 p-4" data-testid="strategy-governance-cluster-overlay-panel">
            <h3 className="text-lg font-bold" data-testid="strategy-governance-cluster-overlay-title">Cluster Risk Overlay</h3>
            <div className="mt-3 space-y-1" data-testid="strategy-governance-cluster-overlay-list">
              {clusterOverlayRows.map((row, index) => (
                <p className="text-xs" key={`${row?.cluster_id}-${index}`} data-testid={`strategy-governance-cluster-overlay-item-${index}`}>
                  {row?.cluster_id}: exposure={row?.cluster_exposure} · triggered_strategy={row?.triggered_strategy} · risk_source_symbol={row?.risk_source_symbol}
                </p>
              ))}
              {clusterOverlayRows.length === 0 && <p className="text-xs" data-testid="strategy-governance-cluster-overlay-empty">Cluster overlay verisi yok.</p>}
            </div>
          </div>
        </>
      )}
    </section>
  );
};
