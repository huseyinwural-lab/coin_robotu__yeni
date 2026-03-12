import { useCallback, useEffect, useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

export const AdminFuturesRiskMonitorPage = () => {
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [riskStatus, setRiskStatus] = useState(null);
  const [liquidationStatus, setLiquidationStatus] = useState(null);
  const [adlStatus, setAdlStatus] = useState(null);
  const [strategyStatus, setStrategyStatus] = useState(null);
  const [decisionDiagnostics, setDecisionDiagnostics] = useState(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setErrorMessage("");
    try {
      try {
        await apiClient.post("/admin/futures/strategy/run-paper-cycle");
      } catch {
        // no-op, cached status can still be rendered
      }

      const [riskResponse, liquidationResponse, adlResponse, strategyResponse, diagnosticsResponse] = await Promise.all([
        apiClient.get("/admin/futures/risk/status"),
        apiClient.get("/admin/futures/liquidation-protection/status"),
        apiClient.get("/admin/futures/adl/status"),
        apiClient.get("/admin/futures/strategy/status"),
        apiClient.get("/admin/futures/decision-diagnostics"),
      ]);
      setRiskStatus(riskResponse.data || null);
      setLiquidationStatus(liquidationResponse.data || null);
      setAdlStatus(adlResponse.data || null);
      setStrategyStatus(strategyResponse.data || null);
      setDecisionDiagnostics(diagnosticsResponse.data || null);
    } catch (error) {
      const message = error?.response?.data?.detail || "Futures risk monitor verisi alınamadı";
      setErrorMessage(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const heatmapRows = useMemo(() => liquidationStatus?.symbol_risk_heatmap || [], [liquidationStatus]);
  const criticalPositions = useMemo(() => liquidationStatus?.critical_positions || [], [liquidationStatus]);
  const gateRejections = useMemo(() => liquidationStatus?.gate_rejections || [], [liquidationStatus]);
  const hasData = useMemo(() => Boolean(riskStatus || liquidationStatus || adlStatus || strategyStatus || decisionDiagnostics), [riskStatus, liquidationStatus, adlStatus, strategyStatus, decisionDiagnostics]);
  const adlRiskPercent = useMemo(() => Math.min(100, Math.max(0, Number((adlStatus?.portfolio_adl_risk || 0) * 100))), [adlStatus]);
  const strategySignals = useMemo(() => strategyStatus?.signal_feed || [], [strategyStatus]);
  const strategyDecisions = useMemo(() => strategyStatus?.decision_trace || [], [strategyStatus]);
  const strategyRejects = useMemo(() => strategyStatus?.reject_reason_breakdown || [], [strategyStatus]);
  const confidenceDistribution = useMemo(() => strategyStatus?.confidence_distribution || [], [strategyStatus]);
  const paperPnlSeries = useMemo(() => strategyStatus?.paper_pnl_series || [], [strategyStatus]);
  const gateReasonDistribution = useMemo(() => {
    const map = decisionDiagnostics?.gate_reason_distribution || {};
    return Object.entries(map).map(([reason_code, count]) => ({ reason_code, count }));
  }, [decisionDiagnostics]);
  const confidenceVsOutcome = useMemo(
    () => (decisionDiagnostics?.confidence_vs_result || []).map((item, index) => ({
      idx: index + 1,
      confidence: Number(item.confidence || 0),
      result_pnl: Number(item.result_pnl || 0),
      symbol: item.symbol,
      decision: item.decision,
    })),
    [decisionDiagnostics],
  );
  const decisionLayerDistribution = useMemo(() => {
    const map = decisionDiagnostics?.decision_layer_distribution || {};
    return Object.entries(map).map(([layer, count]) => ({ layer, count }));
  }, [decisionDiagnostics]);

  return (
    <section className="space-y-4" data-testid="admin-futures-risk-monitor-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="admin-futures-risk-monitor-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-black" data-testid="admin-futures-risk-monitor-title">
          Futures Liquidation Protection
        </h2>
        <p className="mt-2 text-sm text-black/80" data-testid="admin-futures-risk-monitor-description">
          Read-only liquidation + ADL risk shield görünürlüğü. Manuel override yoktur.
        </p>
        <p className="mt-1 inline-flex border border-black bg-black px-2 py-1 text-xs font-bold uppercase text-orange-400" data-testid="futures-liquidation-readonly-badge">
          Read-Only
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3 border border-black/30 bg-orange-100 p-4" data-testid="admin-futures-risk-monitor-toolbar">
        <Button className="border border-black bg-black text-orange-400 hover:bg-zinc-800" onClick={loadData} data-testid="admin-futures-risk-monitor-refresh-button">
          Yenile
        </Button>
        <p className="text-sm text-black" data-testid="admin-futures-risk-monitor-loading-text">loading: {String(loading)}</p>
        <p className="text-sm text-black" data-testid="admin-futures-risk-monitor-updated-text">
          updated_at: {riskStatus?.updated_at ? new Date(riskStatus.updated_at).toLocaleString() : "-"}
        </p>
      </div>

      {loading && (
        <div className="border border-black/25 bg-orange-50 p-4 text-sm text-black" data-testid="futures-risk-loading-state">
          Futures liquidation protection verileri yükleniyor...
        </div>
      )}

      {!loading && Boolean(errorMessage) && (
        <div className="border border-red-600 bg-red-100 p-4 text-sm text-red-900" data-testid="futures-risk-error-state">
          Hata: {errorMessage}
        </div>
      )}

      {!loading && !errorMessage && !hasData && (
        <div className="border border-black/25 bg-orange-50 p-4 text-sm text-black" data-testid="futures-risk-empty-state">
          Gösterilecek veri bulunamadı.
        </div>
      )}

      {!loading && !errorMessage && hasData && (
        <>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-5" data-testid="admin-futures-risk-monitor-global-cards-grid">
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="futures-card-portfolio-leverage">
              <p className="text-xs uppercase">Portfolio leverage</p>
              <p className="text-2xl font-bold" data-testid="futures-portfolio-leverage-value">{riskStatus?.portfolio_leverage ?? 0}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="futures-card-margin-usage">
              <p className="text-xs uppercase">Margin usage</p>
              <p className="text-2xl font-bold" data-testid="futures-margin-usage-value">{riskStatus?.margin_usage ?? 0}%</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="futures-card-liquidation-risk">
              <p className="text-xs uppercase">Liquidation risk score</p>
              <p className="text-2xl font-bold" data-testid="futures-liquidation-risk-value">{riskStatus?.liquidation_risk_score ?? 0}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="futures-card-adl-risk">
              <p className="text-xs uppercase">ADL risk score</p>
              <p className="text-2xl font-bold" data-testid="futures-adl-risk-value">{adlStatus?.portfolio_adl_risk ?? riskStatus?.adl_risk_score ?? 0}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="futures-card-policy-state">
              <p className="text-xs uppercase">Policy state</p>
              <p className="text-2xl font-bold" data-testid="futures-policy-state-value">{riskStatus?.policy_state || liquidationStatus?.policy_state || "SAFE"}</p>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2" data-testid="admin-futures-risk-monitor-middle-grid">
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="futures-funding-bias-summary-panel">
              <h3 className="text-lg font-bold" data-testid="futures-funding-bias-title">Funding Bias Summary</h3>
              <p className="mt-2 text-sm" data-testid="futures-funding-bias-score">avg_funding_bias_score: {riskStatus?.funding_bias?.avg_funding_bias_score ?? 0}</p>
              <p className="text-sm" data-testid="futures-funding-bias-direction">dominant_bias: {riskStatus?.funding_bias?.dominant_bias || "NEUTRAL"}</p>
              <p className="text-sm" data-testid="futures-capital-recommendation">capital_recommendation: {JSON.stringify(riskStatus?.capital_recommendation || {})}</p>
            </div>

            <div className="border border-black/25 bg-orange-100 p-4" data-testid="futures-gate-rejection-panel">
              <h3 className="text-lg font-bold" data-testid="futures-gate-rejection-title">Gate Rejection Reasons</h3>
              <p className="mt-2 text-sm" data-testid="futures-gate-rejection-count">count: {riskStatus?.gate_state?.gate_rejection_total ?? 0}</p>
              <div className="mt-2 space-y-1" data-testid="futures-gate-rejection-list">
                {gateRejections.map((item, index) => (
                  <p key={`${item.symbol}-${index}`} className="text-xs" data-testid={`futures-gate-rejection-item-${index}`}>
                    {item.symbol}: {item.reason} ({item.gate_type || "LIQUIDATION"})
                  </p>
                ))}
                {gateRejections.length === 0 && <p className="text-xs" data-testid="futures-gate-rejection-empty">No gate rejection.</p>}
              </div>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-4" data-testid="futures-adl-widget-grid">
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="futures-adl-gauge-widget">
              <h3 className="text-base font-bold" data-testid="futures-adl-gauge-title">ADL Risk Gauge</h3>
              <p className="text-sm" data-testid="futures-adl-gauge-score">score: {adlStatus?.portfolio_adl_risk ?? 0}</p>
              <div className="mt-2 h-3 w-full border border-black/30 bg-white" data-testid="futures-adl-gauge-track">
                <div className="h-full bg-black" style={{ width: `${adlRiskPercent}%` }} data-testid="futures-adl-gauge-fill" />
              </div>
            </div>
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="futures-adl-pressure-widget">
              <h3 className="text-base font-bold" data-testid="futures-adl-pressure-title">Pressure Side</h3>
              <p className="mt-2 text-lg font-bold" data-testid="futures-adl-pressure-value">{adlStatus?.dominant_side || "NONE"}</p>
              <p className="text-xs" data-testid="futures-adl-risk-level-value">risk_level: {adlStatus?.risk_level || "LOW"}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="futures-adl-symbols-widget">
              <h3 className="text-base font-bold" data-testid="futures-adl-symbols-title">ADL Risk Symbols</h3>
              <div className="mt-2 space-y-1" data-testid="futures-adl-symbols-list">
                {(adlStatus?.symbols_at_risk || []).map((symbol, index) => (
                  <p key={`${symbol}-${index}`} className="text-xs" data-testid={`futures-adl-symbol-item-${index}`}>{symbol}</p>
                ))}
                {(adlStatus?.symbols_at_risk || []).length === 0 && <p className="text-xs" data-testid="futures-adl-symbols-empty">No ADL risk symbols.</p>}
              </div>
            </div>
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="futures-adl-policy-widget">
              <h3 className="text-base font-bold" data-testid="futures-adl-policy-title">ADL Policy State</h3>
              <p className="mt-2 text-lg font-bold" data-testid="futures-adl-policy-value">{adlStatus?.adl_policy_state || "ALLOW"}</p>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2" data-testid="admin-futures-risk-monitor-bottom-grid">
            <div className="border border-black/30 bg-orange-100" data-testid="futures-critical-positions-table-wrapper">
              <div className="border-b border-black/20 px-4 py-3" data-testid="futures-critical-positions-header">
                <h3 className="text-lg font-bold" data-testid="futures-critical-positions-title">Critical Positions</h3>
              </div>
              <Table data-testid="futures-critical-positions-table">
                <TableHeader>
                  <TableRow>
                    <TableHead data-testid="futures-critical-head-symbol">Symbol</TableHead>
                    <TableHead data-testid="futures-critical-head-side">Side</TableHead>
                    <TableHead data-testid="futures-critical-head-distance">Distance</TableHead>
                    <TableHead data-testid="futures-critical-head-leverage">Leverage</TableHead>
                    <TableHead data-testid="futures-critical-head-action">Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {criticalPositions.map((item, index) => (
                    <TableRow key={`${item.symbol}-${index}`} data-testid={`futures-critical-row-${index}`}>
                      <TableCell data-testid={`futures-critical-symbol-${index}`}>{item.symbol}</TableCell>
                      <TableCell data-testid={`futures-critical-side-${index}`}>{item.side}</TableCell>
                      <TableCell data-testid={`futures-critical-distance-${index}`}>{item.distance_to_liquidation}</TableCell>
                      <TableCell data-testid={`futures-critical-leverage-${index}`}>{item.leverage}</TableCell>
                      <TableCell data-testid={`futures-critical-action-${index}`}>{item.action}</TableCell>
                    </TableRow>
                  ))}
                  {criticalPositions.length === 0 && (
                    <TableRow data-testid="futures-critical-empty-row">
                      <TableCell colSpan={5} className="text-center text-sm text-black/70" data-testid="futures-critical-empty-text">
                        Kritik pozisyon yok.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>

            <div className="border border-black/30 bg-orange-100" data-testid="futures-heatmap-table-wrapper">
              <div className="border-b border-black/20 px-4 py-3" data-testid="futures-heatmap-header">
                <h3 className="text-lg font-bold" data-testid="futures-heatmap-title">Symbol Risk Heatmap</h3>
              </div>
              <Table data-testid="futures-heatmap-table">
                <TableHeader>
                  <TableRow>
                    <TableHead data-testid="futures-heatmap-head-symbol">Symbol</TableHead>
                    <TableHead data-testid="futures-heatmap-head-score">Risk Score</TableHead>
                    <TableHead data-testid="futures-heatmap-head-level">Risk Level</TableHead>
                    <TableHead data-testid="futures-heatmap-head-distance">Distance</TableHead>
                    <TableHead data-testid="futures-heatmap-head-adl">ADL</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {heatmapRows.map((item, index) => (
                    <TableRow key={`${item.symbol}-${index}`} data-testid={`futures-heatmap-row-${index}`}>
                      <TableCell data-testid={`futures-heatmap-symbol-${index}`}>{item.symbol}</TableCell>
                      <TableCell data-testid={`futures-heatmap-score-${index}`}>{item.risk_score}</TableCell>
                      <TableCell data-testid={`futures-heatmap-level-${index}`}>{item.risk_level}</TableCell>
                      <TableCell data-testid={`futures-heatmap-distance-${index}`}>{item.distance_to_liquidation}</TableCell>
                      <TableCell data-testid={`futures-heatmap-adl-${index}`}>{item.adl_risk_level || "LOW"}</TableCell>
                    </TableRow>
                  ))}
                  {heatmapRows.length === 0 && (
                    <TableRow data-testid="futures-heatmap-empty-row">
                      <TableCell colSpan={5} className="text-center text-sm text-black/70" data-testid="futures-heatmap-empty-text">
                        Heatmap verisi yok.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          </div>

          <div className="border border-black/25 bg-orange-100 p-4" data-testid="futures-policy-timeline-panel">
            <h3 className="text-lg font-bold" data-testid="futures-policy-timeline-title">Policy State Timeline</h3>
            <div className="mt-2 space-y-1" data-testid="futures-policy-timeline-list">
              {(liquidationStatus?.policy_timeline || []).slice(0, 12).map((item, index) => (
                <p key={`${item.ts}-${index}`} className="text-xs" data-testid={`futures-policy-timeline-item-${index}`}>
                  {new Date(item.ts).toLocaleString()} · policy={item.policy_action} · risk={item.risk_level} · cascade={item.cascade}
                </p>
              ))}
              {(!liquidationStatus?.policy_timeline || liquidationStatus.policy_timeline.length === 0) && (
                <p className="text-xs" data-testid="futures-policy-timeline-empty">Timeline verisi yok.</p>
              )}
            </div>
          </div>

          <div className="border border-black/25 bg-orange-100 p-4" data-testid="futures-decision-trace-panel">
            <h3 className="text-lg font-bold" data-testid="futures-decision-trace-title">Decision Trace</h3>
            <pre className="mt-2 overflow-x-auto text-xs text-black" data-testid="futures-decision-trace-json">{JSON.stringify(liquidationStatus?.decision_trace || riskStatus?.decision_trace || {}, null, 2)}</pre>
          </div>

          <div className="border border-black/25 bg-orange-100 p-4" data-testid="futures-strategy-header-panel">
            <h3 className="text-lg font-bold" data-testid="futures-strategy-header-title">Futures Strategy (Paper Mode)</h3>
            <p className="mt-2 text-sm" data-testid="futures-strategy-header-description">
              futures_trend_follow_v1 · signal → gate → decision → synthetic PnL (real order yok)
            </p>
          </div>

          <div className="grid gap-3 md:grid-cols-5" data-testid="futures-strategy-metrics-grid">
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="futures-strategy-signal-total-card">
              <p className="text-xs uppercase">Signal Total</p>
              <p className="text-xl font-bold" data-testid="futures-strategy-signal-total-value">{strategyStatus?.metrics?.futures_strategy_signal_total ?? 0}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="futures-strategy-allowed-total-card">
              <p className="text-xs uppercase">Allowed</p>
              <p className="text-xl font-bold" data-testid="futures-strategy-allowed-total-value">{strategyStatus?.metrics?.futures_strategy_allowed_total ?? 0}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="futures-strategy-rejected-total-card">
              <p className="text-xs uppercase">Rejected</p>
              <p className="text-xl font-bold" data-testid="futures-strategy-rejected-total-value">{strategyStatus?.metrics?.futures_strategy_rejected_total ?? 0}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="futures-strategy-confidence-card">
              <p className="text-xs uppercase">Avg Confidence</p>
              <p className="text-xl font-bold" data-testid="futures-strategy-confidence-value">{strategyStatus?.metrics?.futures_strategy_confidence ?? 0}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="futures-strategy-paper-pnl-card">
              <p className="text-xs uppercase">Paper PnL</p>
              <p className="text-xl font-bold" data-testid="futures-strategy-paper-pnl-value">{strategyStatus?.metrics?.futures_strategy_paper_pnl ?? 0}</p>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2" data-testid="futures-strategy-content-grid">
            <div className="border border-black/25 bg-orange-100" data-testid="futures-strategy-signal-feed-wrapper">
              <div className="border-b border-black/20 px-4 py-3" data-testid="futures-strategy-signal-feed-header">
                <h4 className="text-base font-bold" data-testid="futures-strategy-signal-feed-title">Strategy Signal Feed</h4>
              </div>
              <Table data-testid="futures-strategy-signal-feed-table">
                <TableHeader>
                  <TableRow>
                    <TableHead data-testid="futures-strategy-feed-head-symbol">Symbol</TableHead>
                    <TableHead data-testid="futures-strategy-feed-head-side">Side</TableHead>
                    <TableHead data-testid="futures-strategy-feed-head-confidence">Confidence</TableHead>
                    <TableHead data-testid="futures-strategy-feed-head-reason">Reason</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {strategySignals.slice(0, 12).map((item, index) => (
                    <TableRow key={`${item.symbol}-${index}`} data-testid={`futures-strategy-feed-row-${index}`}>
                      <TableCell data-testid={`futures-strategy-feed-symbol-${index}`}>{item.symbol}</TableCell>
                      <TableCell data-testid={`futures-strategy-feed-side-${index}`}>{item.side}</TableCell>
                      <TableCell data-testid={`futures-strategy-feed-confidence-${index}`}>{item.confidence}</TableCell>
                      <TableCell data-testid={`futures-strategy-feed-reason-${index}`}>{item.reason}</TableCell>
                    </TableRow>
                  ))}
                  {strategySignals.length === 0 && (
                    <TableRow data-testid="futures-strategy-feed-empty-row">
                      <TableCell colSpan={4} className="text-center text-sm text-black/70" data-testid="futures-strategy-feed-empty-text">
                        Strategy sinyali yok.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>

            <div className="border border-black/25 bg-orange-100 p-4" data-testid="futures-strategy-decision-trace-panel">
              <h4 className="text-base font-bold" data-testid="futures-strategy-decision-trace-title">Strategy Decision Trace</h4>
              <div className="mt-2 space-y-1" data-testid="futures-strategy-decision-trace-list">
                {strategyDecisions.slice(0, 12).map((item, index) => (
                  <p key={`${item.symbol}-${index}`} className="text-xs" data-testid={`futures-strategy-decision-item-${index}`}>
                    {item.symbol} · {item.side} · {item.decision} · {item.reason_code}
                  </p>
                ))}
                {strategyDecisions.length === 0 && <p className="text-xs" data-testid="futures-strategy-decision-empty">Karar zinciri henüz oluşmadı.</p>}
              </div>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-3" data-testid="futures-strategy-analytics-grid">
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="futures-strategy-pnl-chart-panel">
              <h4 className="text-base font-bold" data-testid="futures-strategy-pnl-chart-title">Paper PnL Chart</h4>
              <div className="mt-3 h-48" data-testid="futures-strategy-pnl-chart-wrapper">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={paperPnlSeries}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#111" opacity={0.2} />
                    <XAxis dataKey="index" stroke="#111" />
                    <YAxis stroke="#111" />
                    <Tooltip />
                    <Line type="monotone" dataKey="cumulative_pnl" stroke="#111" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              {paperPnlSeries.length === 0 && <p className="mt-2 text-xs" data-testid="futures-strategy-pnl-chart-empty">PnL verisi yok.</p>}
            </div>

            <div className="border border-black/25 bg-orange-100 p-4" data-testid="futures-strategy-reject-reasons-panel">
              <h4 className="text-base font-bold" data-testid="futures-strategy-reject-reasons-title">Strategy Reject Reasons</h4>
              <div className="mt-2 space-y-1" data-testid="futures-strategy-reject-reasons-list">
                {strategyRejects.map((item, index) => (
                  <p key={`${item.reason_code}-${index}`} className="text-xs" data-testid={`futures-strategy-reject-reason-item-${index}`}>
                    {item.reason_code}: {item.count}
                  </p>
                ))}
                {strategyRejects.length === 0 && <p className="text-xs" data-testid="futures-strategy-reject-reasons-empty">Reject nedeni yok.</p>}
              </div>
            </div>

            <div className="border border-black/25 bg-orange-100 p-4" data-testid="futures-strategy-confidence-distribution-panel">
              <h4 className="text-base font-bold" data-testid="futures-strategy-confidence-distribution-title">Confidence Distribution</h4>
              <div className="mt-2 space-y-1" data-testid="futures-strategy-confidence-distribution-list">
                {confidenceDistribution.map((item, index) => (
                  <p key={`${item.bucket}-${index}`} className="text-xs" data-testid={`futures-strategy-confidence-item-${index}`}>
                    {item.bucket}: {item.count}
                  </p>
                ))}
                {confidenceDistribution.length === 0 && <p className="text-xs" data-testid="futures-strategy-confidence-distribution-empty">Confidence dağılımı yok.</p>}
              </div>
            </div>
          </div>

          <div className="border border-black/25 bg-orange-100 p-4" data-testid="futures-decision-diagnostics-header-panel">
            <h3 className="text-lg font-bold" data-testid="futures-decision-diagnostics-header-title">Decision Diagnostics</h3>
            <p className="mt-2 text-sm" data-testid="futures-decision-diagnostics-header-description">
              False allow/reject ve reason/layer attribution tuning görünürlüğü.
            </p>
          </div>

          <div className="grid gap-3 md:grid-cols-5" data-testid="futures-decision-diagnostics-metrics-grid">
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="futures-false-allow-counter-card">
              <p className="text-xs uppercase">False Allow</p>
              <p className="text-xl font-bold" data-testid="futures-false-allow-counter-value">{decisionDiagnostics?.false_allow_count ?? 0}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="futures-false-reject-counter-card">
              <p className="text-xs uppercase">False Reject</p>
              <p className="text-xl font-bold" data-testid="futures-false-reject-counter-value">{decisionDiagnostics?.false_reject_count ?? 0}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3 md:col-span-3" data-testid="futures-gate-reason-distribution-card">
              <p className="text-xs uppercase" data-testid="futures-gate-reason-distribution-title">Gate Reason Distribution</p>
              <div className="mt-1 flex flex-wrap gap-3" data-testid="futures-gate-reason-distribution-items">
                {gateReasonDistribution.map((item, index) => (
                  <p key={`${item.reason_code}-${index}`} className="text-xs" data-testid={`futures-gate-reason-distribution-item-${index}`}>
                    {item.reason_code}: {item.count}
                  </p>
                ))}
                {gateReasonDistribution.length === 0 && <p className="text-xs" data-testid="futures-gate-reason-distribution-empty">Dağılım verisi yok.</p>}
              </div>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2" data-testid="futures-decision-diagnostics-charts-grid">
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="futures-confidence-vs-outcome-scatter-panel">
              <h4 className="text-base font-bold" data-testid="futures-confidence-vs-outcome-scatter-title">Confidence vs Outcome Scatter</h4>
              <div className="mt-3 h-56" data-testid="futures-confidence-vs-outcome-scatter-wrapper">
                <ResponsiveContainer width="100%" height="100%">
                  <ScatterChart>
                    <CartesianGrid strokeDasharray="3 3" stroke="#111" opacity={0.2} />
                    <XAxis type="number" dataKey="confidence" name="confidence" domain={[0, 1]} stroke="#111" />
                    <YAxis type="number" dataKey="result_pnl" name="result_pnl" stroke="#111" />
                    <Tooltip cursor={{ strokeDasharray: "3 3" }} />
                    <Scatter data={confidenceVsOutcome} fill="#111" data-testid="futures-confidence-vs-outcome-scatter-dots" />
                  </ScatterChart>
                </ResponsiveContainer>
              </div>
              {confidenceVsOutcome.length === 0 && <p className="mt-2 text-xs" data-testid="futures-confidence-vs-outcome-scatter-empty">Scatter verisi yok.</p>}
            </div>

            <div className="border border-black/25 bg-orange-100 p-4" data-testid="futures-decision-layer-distribution-panel">
              <h4 className="text-base font-bold" data-testid="futures-decision-layer-distribution-title">Decision Layer Distribution</h4>
              <div className="mt-2 space-y-1" data-testid="futures-decision-layer-distribution-list">
                {decisionLayerDistribution.map((item, index) => (
                  <p key={`${item.layer}-${index}`} className="text-xs" data-testid={`futures-decision-layer-distribution-item-${index}`}>
                    {item.layer}: {item.count}
                  </p>
                ))}
                {decisionLayerDistribution.length === 0 && <p className="text-xs" data-testid="futures-decision-layer-distribution-empty">Layer dağılımı yok.</p>}
              </div>
            </div>
          </div>
        </>
      )}
    </section>
  );
};
