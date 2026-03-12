import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

export const AdminFuturesStrategyAnalyticsPage = () => {
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [performance, setPerformance] = useState(null);
  const [executionQuality, setExecutionQuality] = useState(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setErrorMessage("");
    try {
      const [performanceResponse, qualityResponse] = await Promise.all([
        apiClient.get("/admin/futures/strategy-performance"),
        apiClient.get("/admin/futures/strategy-execution-quality"),
      ]);
      setPerformance(performanceResponse.data || null);
      setExecutionQuality(qualityResponse.data || null);
    } catch (error) {
      const message = error?.response?.data?.detail || "Strategy analytics verisi alınamadı";
      setErrorMessage(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const pnlRows = useMemo(() => performance?.strategy_pnl_contribution || [], [performance]);
  const signalRows = useMemo(() => performance?.strategy_signal_distribution || [], [performance]);
  const driftRows = useMemo(() => executionQuality?.strategy_drift_alerts || [], [executionQuality]);
  const qualityRows = useMemo(() => executionQuality?.strategy_execution_quality || [], [executionQuality]);
  const slippageRows = useMemo(() => executionQuality?.strategy_slippage || [], [executionQuality]);
  const latencyRows = useMemo(() => executionQuality?.strategy_latency || [], [executionQuality]);
  const rejectRows = useMemo(() => executionQuality?.strategy_reject_rate || [], [executionQuality]);
  const confidenceRows = useMemo(() => executionQuality?.strategy_confidence_vs_result || [], [executionQuality]);
  const falseCompareRows = useMemo(
    () => executionQuality?.false_allow_reject_comparison_by_strategy || [],
    [executionQuality],
  );
  const gateTrend = useMemo(() => executionQuality?.gate_reason_trend_7d || [], [executionQuality]);
  const checklist15 = useMemo(() => executionQuality?.architecture_checklist_15 || [], [executionQuality]);

  return (
    <section className="space-y-4" data-testid="admin-futures-strategy-analytics-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="admin-futures-strategy-analytics-header">
        <h2
          className="text-4xl font-black uppercase tracking-tight text-black"
          data-testid="admin-futures-strategy-analytics-title"
        >
          Futures Strategy Analytics
        </h2>
        <p className="mt-2 text-sm text-black/80" data-testid="admin-futures-strategy-analytics-description">
          Multi-strategy orchestration, performance attribution ve drift alarm görünürlüğü.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3 border border-black/30 bg-orange-100 p-4" data-testid="strategy-analytics-toolbar">
        <Button
          className="border border-black bg-black text-orange-400 hover:bg-zinc-800"
          onClick={loadData}
          data-testid="strategy-analytics-refresh-button"
        >
          Yenile
        </Button>
        <p className="text-sm text-black" data-testid="strategy-analytics-loading-text">
          loading: {String(loading)}
        </p>
        <p className="text-sm text-black" data-testid="strategy-analytics-updated-at-text">
          updated_at: {executionQuality?.generated_at ? new Date(executionQuality.generated_at).toLocaleString() : "-"}
        </p>
      </div>

      {loading && (
        <div className="border border-black/25 bg-orange-50 p-4 text-sm" data-testid="strategy-analytics-loading-state">
          Strategy analytics yükleniyor...
        </div>
      )}
      {!loading && Boolean(errorMessage) && (
        <div className="border border-red-700 bg-red-100 p-4 text-sm text-red-900" data-testid="strategy-analytics-error-state">
          Hata: {errorMessage}
        </div>
      )}

      {!loading && !errorMessage && (
        <>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4" data-testid="strategy-analytics-summary-grid">
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="strategy-analytics-summary-strategy-count-card">
              <p className="text-xs uppercase">Strategy Count</p>
              <p className="text-xl font-bold" data-testid="strategy-analytics-summary-strategy-count-value">
                {(performance?.strategy_registry || []).length}
              </p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="strategy-analytics-summary-drift-alert-card">
              <p className="text-xs uppercase">Drift Alerts</p>
              <p className="text-xl font-bold" data-testid="strategy-analytics-summary-drift-alert-value">
                {driftRows.length}
              </p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="strategy-analytics-summary-rolling-score-card">
              <p className="text-xs uppercase">Rolling 7d Tuning</p>
              <p className="text-xl font-bold" data-testid="strategy-analytics-summary-rolling-score-value">
                {executionQuality?.rolling_7d_tuning_score?.latest_score ?? 0}
              </p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="strategy-analytics-summary-blocked-card">
              <p className="text-xs uppercase">Blocked Decisions</p>
              <p className="text-xl font-bold" data-testid="strategy-analytics-summary-blocked-value">
                {performance?.interaction_guard?.blocked_total ?? 0}
              </p>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2" data-testid="strategy-analytics-primary-grid">
            <div className="border border-black/25 bg-orange-100" data-testid="strategy-analytics-pnl-contribution-table-wrapper">
              <div className="border-b border-black/20 px-4 py-3" data-testid="strategy-analytics-pnl-contribution-header">
                <h3 className="text-lg font-bold" data-testid="strategy-analytics-pnl-contribution-title">Strategy PnL Contribution</h3>
              </div>
              <Table data-testid="strategy-analytics-pnl-contribution-table">
                <TableHeader>
                  <TableRow>
                    <TableHead data-testid="strategy-analytics-pnl-head-strategy">Strategy</TableHead>
                    <TableHead data-testid="strategy-analytics-pnl-head-pnl">PnL</TableHead>
                    <TableHead data-testid="strategy-analytics-pnl-head-ratio">Contribution</TableHead>
                    <TableHead data-testid="strategy-analytics-pnl-head-trades">Trades</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {pnlRows.map((row, index) => (
                    <TableRow key={`${row.strategy}-${index}`} data-testid={`strategy-analytics-pnl-row-${index}`}>
                      <TableCell data-testid={`strategy-analytics-pnl-strategy-${index}`}>{row.strategy}</TableCell>
                      <TableCell data-testid={`strategy-analytics-pnl-value-${index}`}>{row.pnl_attribution}</TableCell>
                      <TableCell data-testid={`strategy-analytics-pnl-ratio-${index}`}>{row.pnl_contribution_ratio}</TableCell>
                      <TableCell data-testid={`strategy-analytics-pnl-trade-count-${index}`}>{row.trade_count}</TableCell>
                    </TableRow>
                  ))}
                  {pnlRows.length === 0 && (
                    <TableRow data-testid="strategy-analytics-pnl-empty-row">
                      <TableCell colSpan={4} className="text-center text-sm" data-testid="strategy-analytics-pnl-empty-text">
                        PnL attribution verisi yok.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>

            <div className="border border-black/25 bg-orange-100" data-testid="strategy-analytics-quality-table-wrapper">
              <div className="border-b border-black/20 px-4 py-3" data-testid="strategy-analytics-quality-header">
                <h3 className="text-lg font-bold" data-testid="strategy-analytics-quality-title">Strategy Execution Quality</h3>
              </div>
              <Table data-testid="strategy-analytics-quality-table">
                <TableHeader>
                  <TableRow>
                    <TableHead data-testid="strategy-analytics-quality-head-strategy">Strategy</TableHead>
                    <TableHead data-testid="strategy-analytics-quality-head-quality">Quality</TableHead>
                    <TableHead data-testid="strategy-analytics-quality-head-slippage">Slippage</TableHead>
                    <TableHead data-testid="strategy-analytics-quality-head-latency">Latency</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {qualityRows.map((row, index) => (
                    <TableRow key={`${row.strategy}-${index}`} data-testid={`strategy-analytics-quality-row-${index}`}>
                      <TableCell data-testid={`strategy-analytics-quality-strategy-${index}`}>{row.strategy}</TableCell>
                      <TableCell data-testid={`strategy-analytics-quality-value-${index}`}>{row.execution_quality}</TableCell>
                      <TableCell data-testid={`strategy-analytics-quality-slippage-${index}`}>{slippageRows[index]?.avg_slippage_bps ?? 0}</TableCell>
                      <TableCell data-testid={`strategy-analytics-quality-latency-${index}`}>{latencyRows[index]?.avg_latency_ms ?? 0}</TableCell>
                    </TableRow>
                  ))}
                  {qualityRows.length === 0 && (
                    <TableRow data-testid="strategy-analytics-quality-empty-row">
                      <TableCell colSpan={4} className="text-center text-sm" data-testid="strategy-analytics-quality-empty-text">
                        Execution quality verisi yok.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2" data-testid="strategy-analytics-secondary-grid">
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="strategy-analytics-signal-distribution-panel">
              <h3 className="text-lg font-bold" data-testid="strategy-analytics-signal-distribution-title">Signal Distribution</h3>
              <div className="mt-2 space-y-1" data-testid="strategy-analytics-signal-distribution-list">
                {signalRows.map((row, index) => (
                  <p key={`${row.strategy}-${index}`} className="text-xs" data-testid={`strategy-analytics-signal-item-${index}`}>
                    {row.strategy}: total={row.signal_total} allow={row.allowed_total} reject={row.rejected_total}
                  </p>
                ))}
                {signalRows.length === 0 && <p className="text-xs" data-testid="strategy-analytics-signal-empty">Signal distribution verisi yok.</p>}
              </div>
            </div>

            <div className="border border-black/25 bg-orange-100 p-4" data-testid="strategy-analytics-drift-alert-panel">
              <h3 className="text-lg font-bold" data-testid="strategy-analytics-drift-alert-title">Strategy Drift Alerts</h3>
              <div className="mt-2 space-y-1" data-testid="strategy-analytics-drift-alert-list">
                {driftRows.map((row, index) => (
                  <p key={`${row.strategy}-${index}`} className="text-xs" data-testid={`strategy-analytics-drift-alert-item-${index}`}>
                    {row.strategy}: {row.event} · {row.severity} · {(row.reasons || []).join(", ")}
                  </p>
                ))}
                {driftRows.length === 0 && <p className="text-xs" data-testid="strategy-analytics-drift-alert-empty">Drift alarmı yok.</p>}
              </div>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2" data-testid="strategy-analytics-diagnostics-grid">
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="strategy-analytics-reject-rate-panel">
              <h3 className="text-lg font-bold" data-testid="strategy-analytics-reject-rate-title">Reject Rate + Confidence vs Result</h3>
              <div className="mt-2 space-y-1" data-testid="strategy-analytics-reject-rate-list">
                {rejectRows.map((row, index) => (
                  <p key={`${row.strategy}-${index}`} className="text-xs" data-testid={`strategy-analytics-reject-rate-item-${index}`}>
                    {row.strategy}: reject_rate={row.reject_rate} · divergence={confidenceRows[index]?.divergence_score ?? 0}
                  </p>
                ))}
                {rejectRows.length === 0 && <p className="text-xs" data-testid="strategy-analytics-reject-rate-empty">Reject rate verisi yok.</p>}
              </div>
            </div>

            <div className="border border-black/25 bg-orange-100 p-4" data-testid="strategy-analytics-false-compare-panel">
              <h3 className="text-lg font-bold" data-testid="strategy-analytics-false-compare-title">False Allow / False Reject</h3>
              <div className="mt-2 space-y-1" data-testid="strategy-analytics-false-compare-list">
                {falseCompareRows.map((row, index) => (
                  <p key={`${row.strategy}-${index}`} className="text-xs" data-testid={`strategy-analytics-false-compare-item-${index}`}>
                    {row.strategy}: false_allow={row.false_allow} · false_reject={row.false_reject}
                  </p>
                ))}
                {falseCompareRows.length === 0 && <p className="text-xs" data-testid="strategy-analytics-false-compare-empty">Karşılaştırma verisi yok.</p>}
              </div>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2" data-testid="strategy-analytics-governance-grid">
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="strategy-analytics-gate-trend-panel">
              <h3 className="text-lg font-bold" data-testid="strategy-analytics-gate-trend-title">Gate Reason Trend (7d)</h3>
              <div className="mt-2 space-y-1" data-testid="strategy-analytics-gate-trend-list">
                {gateTrend.map((row, index) => (
                  <p key={`${row.date}-${index}`} className="text-xs" data-testid={`strategy-analytics-gate-trend-item-${index}`}>
                    {row.date}: {JSON.stringify(row.reasons || {})}
                  </p>
                ))}
                {gateTrend.length === 0 && <p className="text-xs" data-testid="strategy-analytics-gate-trend-empty">Trend verisi yok.</p>}
              </div>
            </div>

            <div className="border border-black/25 bg-orange-100 p-4" data-testid="strategy-analytics-checklist-panel">
              <h3 className="text-lg font-bold" data-testid="strategy-analytics-checklist-title">15-Point Strategy Architecture Checklist</h3>
              <div className="mt-2 space-y-1" data-testid="strategy-analytics-checklist-list">
                {checklist15.map((row, index) => (
                  <p key={`${row.check}-${index}`} className="text-xs" data-testid={`strategy-analytics-checklist-item-${index}`}>
                    {row.id}. {row.check}: {String(row.pass)}
                  </p>
                ))}
                {checklist15.length === 0 && <p className="text-xs" data-testid="strategy-analytics-checklist-empty">Checklist verisi yok.</p>}
              </div>
            </div>
          </div>
        </>
      )}
    </section>
  );
};
