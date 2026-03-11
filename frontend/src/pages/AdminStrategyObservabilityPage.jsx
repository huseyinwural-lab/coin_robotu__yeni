import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

const windowOptions = ["24h", "7d", "30d"];

export const AdminStrategyObservabilityPage = () => {
  const [windowRange, setWindowRange] = useState("24h");
  const [topN, setTopN] = useState(10);
  const [loading, setLoading] = useState(false);
  const [topSignals, setTopSignals] = useState([]);
  const [rejection, setRejection] = useState(null);
  const [scoreMetrics, setScoreMetrics] = useState(null);
  const [report, setReport] = useState(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const safeTopN = Math.min(Math.max(Number(topN) || 10, 1), 50);
      const [topRes, rejectionRes, scoreRes, reportRes] = await Promise.all([
        apiClient.get("/admin/strategy/top-signals", { params: { window: windowRange, top_n: safeTopN } }),
        apiClient.get("/admin/strategy/rejection-analytics", { params: { window: windowRange } }),
        apiClient.get("/admin/strategy/score-metrics", { params: { window: windowRange } }),
        apiClient.get("/admin/strategy/report", { params: { window: windowRange } }),
      ]);

      setTopSignals(topRes.data?.items || []);
      setRejection(rejectionRes.data || null);
      setScoreMetrics(scoreRes.data || null);
      setReport(reportRes.data || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Strategy observability verisi alınamadı");
    } finally {
      setLoading(false);
    }
  }, [topN, windowRange]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const regimeRows = useMemo(() => {
    const distribution = scoreMetrics?.market_regime_distribution || {};
    return Object.entries(distribution).sort((a, b) => b[1] - a[1]);
  }, [scoreMetrics]);

  return (
    <section className="space-y-4" data-testid="admin-strategy-observability-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="admin-strategy-observability-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-black" data-testid="admin-strategy-observability-title">
          Strategy Observability Center
        </h2>
        <p className="mt-2 text-sm text-black/80" data-testid="admin-strategy-observability-description">
          Top signals, rejection analytics, score tuning ve strategy report tek ekranda.
        </p>
      </header>

      <div className="grid gap-2 border border-black/30 bg-orange-100 p-4 md:grid-cols-4" data-testid="admin-strategy-observability-controls">
        <select
          className="border border-black/40 bg-white px-3 py-2 text-sm"
          value={windowRange}
          onChange={(event) => setWindowRange(event.target.value)}
          data-testid="strategy-observability-window-select"
        >
          {windowOptions.map((windowValue) => (
            <option key={windowValue} value={windowValue}>
              {windowValue}
            </option>
          ))}
        </select>

        <Input
          type="number"
          min={1}
          max={50}
          value={topN}
          onChange={(event) => setTopN(Math.min(Math.max(Number(event.target.value) || 10, 1), 50))}
          data-testid="strategy-observability-topn-input"
        />

        <Button
          className="border border-black bg-black text-orange-400 hover:bg-zinc-800"
          onClick={loadData}
          data-testid="strategy-observability-refresh-button"
        >
          Yenile
        </Button>

        <p className="self-center text-sm text-black" data-testid="strategy-observability-loading-text">
          loading: {String(loading)}
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4" data-testid="strategy-observability-rejection-cards-grid">
        <div className="border border-black/25 bg-orange-100 p-3" data-testid="rejection-trend-card">
          <p className="text-xs uppercase">Rejected by Trend</p>
          <p className="text-2xl font-bold" data-testid="rejection-trend-value">{rejection?.signals_rejected_trend_strength ?? 0}</p>
        </div>
        <div className="border border-black/25 bg-orange-100 p-3" data-testid="rejection-btc-card">
          <p className="text-xs uppercase">Rejected by BTC</p>
          <p className="text-2xl font-bold" data-testid="rejection-btc-value">{rejection?.signals_rejected_btc_regime ?? 0}</p>
        </div>
        <div className="border border-black/25 bg-orange-100 p-3" data-testid="rejection-freeze-card">
          <p className="text-xs uppercase">Rejected by Freeze</p>
          <p className="text-2xl font-bold" data-testid="rejection-freeze-value">{rejection?.signals_rejected_freeze_guard ?? 0}</p>
        </div>
        <div className="border border-black/25 bg-orange-100 p-3" data-testid="rejection-threshold-card">
          <p className="text-xs uppercase">Rejected by Threshold</p>
          <p className="text-2xl font-bold" data-testid="rejection-threshold-value">{rejection?.signals_rejected_threshold ?? 0}</p>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-2" data-testid="strategy-observability-score-section-grid">
        <div className="border border-black/25 bg-orange-100 p-4" data-testid="score-metrics-panel">
          <h3 className="text-lg font-bold" data-testid="score-metrics-title">Score Tuning Dashboard</h3>
          <div className="mt-3 space-y-2 text-sm" data-testid="score-metrics-values">
            <p data-testid="score-metrics-avg-base">avg_base_score: {scoreMetrics?.avg_base_score ?? 0}</p>
            <p data-testid="score-metrics-avg-adjusted">avg_adjusted_score: {scoreMetrics?.avg_adjusted_score ?? 0}</p>
            <p data-testid="score-metrics-avg-delta">avg_score_delta: {scoreMetrics?.avg_score_delta ?? 0}</p>
            <p data-testid="score-metrics-signals-per-strategy">
              signals_per_strategy: {JSON.stringify(scoreMetrics?.signals_per_strategy || {})}
            </p>
            <p data-testid="score-metrics-selected-per-strategy">
              selected_signals_per_strategy: {JSON.stringify(scoreMetrics?.selected_signals_per_strategy || {})}
            </p>
          </div>
          <div className="mt-4 space-y-2" data-testid="regime-distribution-bars">
            {regimeRows.map(([regime, count]) => {
              const maxCount = Math.max(...regimeRows.map((item) => item[1]), 1);
              const widthPct = Math.max((count / maxCount) * 100, 5);
              return (
                <div key={regime} className="space-y-1" data-testid={`regime-bar-row-${regime}`}>
                  <p className="text-xs font-semibold" data-testid={`regime-bar-label-${regime}`}>{regime}: {count}</p>
                  <div className="h-3 w-full border border-black/40 bg-white" data-testid={`regime-bar-container-${regime}`}>
                    <div className="h-full bg-black" style={{ width: `${widthPct}%` }} data-testid={`regime-bar-fill-${regime}`} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="border border-black/25 bg-orange-100 p-4" data-testid="strategy-report-panel">
          <h3 className="text-lg font-bold" data-testid="strategy-report-title">Strategy Observability Report</h3>
          <div className="mt-3 space-y-2 text-sm" data-testid="strategy-report-values">
            <p data-testid="strategy-report-active-strategies">active_spot_strategies: {(report?.active_spot_strategies || []).join(", ") || "-"}</p>
            <p data-testid="strategy-report-signals-total">signals_total: {report?.signals_total ?? 0}</p>
            <p data-testid="strategy-report-signals-selected">signals_selected: {report?.signals_selected ?? 0}</p>
            <p data-testid="strategy-report-avg-adjusted">avg_adjusted_score: {report?.avg_adjusted_score ?? 0}</p>
            <p data-testid="strategy-report-avg-base">avg_base_score: {report?.avg_base_score ?? 0}</p>
            <p data-testid="strategy-report-score-delta">score_delta_avg: {report?.score_delta_avg ?? 0}</p>
            <p data-testid="strategy-report-signals-per-strategy">
              signals_per_strategy: {JSON.stringify(report?.signals_per_strategy || {})}
            </p>
            <p data-testid="strategy-report-selected-per-strategy">
              selected_signals_per_strategy: {JSON.stringify(report?.selected_signals_per_strategy || {})}
            </p>
          </div>
        </div>
      </div>

      <div className="border border-black/30 bg-orange-100" data-testid="top-signals-table-wrapper">
        <div className="flex items-center justify-between border-b border-black/20 px-4 py-3" data-testid="top-signals-header-row">
          <h3 className="text-lg font-bold" data-testid="top-signals-title">Top N Executable Signals</h3>
          <p className="text-sm" data-testid="top-signals-count-text">count: {topSignals.length}</p>
        </div>

        <Table data-testid="top-signals-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="top-signals-head-rank">Rank</TableHead>
              <TableHead data-testid="top-signals-head-symbol">Symbol</TableHead>
              <TableHead data-testid="top-signals-head-strategy">Strategy</TableHead>
              <TableHead data-testid="top-signals-head-regime">Regime</TableHead>
              <TableHead data-testid="top-signals-head-adjusted">Adjusted Score</TableHead>
              <TableHead data-testid="top-signals-head-base">Base Score</TableHead>
              <TableHead data-testid="top-signals-head-delta">Delta</TableHead>
              <TableHead data-testid="top-signals-head-trend">Trend</TableHead>
              <TableHead data-testid="top-signals-head-rvol">Rel Volume</TableHead>
              <TableHead data-testid="top-signals-head-time">Timestamp</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {topSignals.map((item) => (
              <TableRow key={`${item.symbol}-${item.selection_rank}-${item.timestamp}`} data-testid={`top-signals-row-${item.symbol}`}>
                <TableCell data-testid={`top-signals-rank-${item.symbol}`}>{item.selection_rank ?? "-"}</TableCell>
                <TableCell data-testid={`top-signals-symbol-${item.symbol}`}>{item.symbol}</TableCell>
                <TableCell data-testid={`top-signals-strategy-${item.symbol}`}>{item.strategy_id}</TableCell>
                <TableCell data-testid={`top-signals-regime-${item.symbol}`}>{item.market_regime}</TableCell>
                <TableCell data-testid={`top-signals-adjusted-${item.symbol}`}>{item.adjusted_score}</TableCell>
                <TableCell data-testid={`top-signals-base-${item.symbol}`}>{item.base_score}</TableCell>
                <TableCell data-testid={`top-signals-delta-${item.symbol}`}>{item.score_delta}</TableCell>
                <TableCell data-testid={`top-signals-trend-${item.symbol}`}>{item.trend_strength || "-"}</TableCell>
                <TableCell data-testid={`top-signals-rvol-${item.symbol}`}>{item.relative_volume ?? "-"}</TableCell>
                <TableCell className="text-xs" data-testid={`top-signals-time-${item.symbol}`}>
                  {item.timestamp ? new Date(item.timestamp).toLocaleString() : "-"}
                </TableCell>
              </TableRow>
            ))}

            {!loading && topSignals.length === 0 && (
              <TableRow data-testid="top-signals-empty-row">
                <TableCell colSpan={10} className="text-center text-sm text-black/70" data-testid="top-signals-empty-text">
                  Bu zaman penceresinde executable signal yok.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </section>
  );
};
