import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const AdminUniverseMonitorPage = () => {
  const [mode, setMode] = useState("ALL_MARKET_SYMBOLS");
  const [windowSize, setWindowSize] = useState("24h");
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState(null);
  const [debugPayload, setDebugPayload] = useState(null);
  const [trend, setTrend] = useState({ points: [] });
  const [breakdown, setBreakdown] = useState({ user_breakdown: [], regime_breakdown: [] });
  const [heatmap, setHeatmap] = useState({ items: [] });
  const [rollout, setRollout] = useState(null);
  const [fallbackEvents, setFallbackEvents] = useState([]);
  const [runtimeSummary, setRuntimeSummary] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const [summaryRes, debugRes, trendRes, breakdownRes, heatmapRes, rolloutRes, fallbackEventsRes, runtimeSummaryRes] = await Promise.all([
        apiClient.get("/admin/universe-monitor", { params: { market_type: "spot", scanner_mode: mode, top_n: 200 } }),
        apiClient.get("/debug/effective-universe", { params: { market_type: "spot", scanner_mode: mode, top_n: 200 } }),
        apiClient.get("/admin/universe-monitor/trends", { params: { window: windowSize } }),
        apiClient.get("/admin/universe-monitor/breakdown", { params: { window: windowSize } }),
        apiClient.get("/admin/universe-monitor/freshness-heatmap", { params: { window: windowSize } }),
        apiClient.get("/admin/universe-monitor/rollout/status"),
        apiClient.get("/admin/universe-monitor/fallback-events", { params: { limit: 80 } }),
        apiClient.get("/admin/universe/runtime-summary", { params: { scanner_mode: mode, top_n: 200 } }),
      ]);
      setSummary(summaryRes.data || null);
      setDebugPayload(debugRes.data || null);
      setTrend(trendRes.data || { points: [] });
      setBreakdown(breakdownRes.data || { user_breakdown: [], regime_breakdown: [] });
      setHeatmap(heatmapRes.data || { items: [] });
      setRollout(rolloutRes.data || null);
      setFallbackEvents(fallbackEventsRes?.data?.items || []);
      setRuntimeSummary(runtimeSummaryRes?.data || null);
    } catch (error) {
      const detail = error?.response?.data?.detail;
      const errorMessage = typeof detail === "string" ? detail : (Array.isArray(detail) ? detail.map(d => d?.msg || JSON.stringify(d)).join(", ") : "Universe monitor verisi alınamadı");
      toast.error(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, windowSize]);

  useEffect(() => {
    const timer = setInterval(() => {
      load();
    }, 10000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, windowSize]);

  const latestTrendPoint = useMemo(() => trend?.latest || trend?.points?.[trend.points.length - 1] || null, [trend]);

  const requestRolloutRecommendation = async () => {
    try {
      await apiClient.post("/admin/universe-monitor/rollout/recommend");
      toast.success("Rollout recommendation üretildi");
      load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Recommendation üretilemedi");
    }
  };

  const approveRolloutRecommendation = async () => {
    try {
      await apiClient.post("/admin/universe-monitor/rollout/approve");
      toast.success("Rollout stage admin onayı ile güncellendi");
      load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Rollout approve başarısız");
    }
  };

  const downloadCsv = async () => {
    try {
      const { data } = await apiClient.get("/admin/universe-monitor/export.csv", {
        params: { window: windowSize },
        responseType: "blob",
      });
      const blobUrl = window.URL.createObjectURL(new Blob([data], { type: "text/csv" }));
      const link = document.createElement("a");
      link.href = blobUrl;
      link.download = `universe_monitor_${windowSize}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(blobUrl);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "CSV export başarısız");
    }
  };

  return (
    <section className="space-y-4" data-testid="admin-universe-monitor-page">
      <header className="border border-blue-900 bg-slate-900 p-4" data-testid="admin-universe-monitor-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-blue-300" data-testid="admin-universe-monitor-title">Universe Monitor</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="admin-universe-monitor-description">
          Throughput / latency / freshness / rollout durumunu tek panelde izleyin.
        </p>
      </header>

      <div className="flex flex-wrap items-end gap-2" data-testid="admin-universe-monitor-toolbar">
        <label className="space-y-1" data-testid="admin-universe-monitor-mode-field">
          <span className="text-xs text-slate-400">Scanner Mode</span>
          <select
            value={mode}
            onChange={(event) => setMode(event.target.value)}
            className="h-10 rounded border border-slate-700 bg-black px-2 text-sm"
            data-testid="admin-universe-monitor-mode-select"
          >
            <option value="ALL_MARKET_SYMBOLS" data-testid="admin-universe-monitor-mode-option-all">ALL_MARKET_SYMBOLS</option>
            <option value="TOP_VOLUME" data-testid="admin-universe-monitor-mode-option-top">TOP_VOLUME</option>
            <option value="MANUAL_SELECTION" data-testid="admin-universe-monitor-mode-option-manual">MANUAL_SELECTION</option>
          </select>
        </label>

        <label className="space-y-1" data-testid="admin-universe-monitor-window-field">
          <span className="text-xs text-slate-400">Trend Window</span>
          <select
            value={windowSize}
            onChange={(event) => setWindowSize(event.target.value)}
            className="h-10 rounded border border-slate-700 bg-black px-2 text-sm"
            data-testid="admin-universe-monitor-window-select"
          >
            <option value="24h" data-testid="admin-universe-monitor-window-24h">24s</option>
            <option value="7d" data-testid="admin-universe-monitor-window-7d">7g</option>
            <option value="30d" data-testid="admin-universe-monitor-window-30d">30g</option>
          </select>
        </label>

        <Button type="button" variant="outline" onClick={load} data-testid="admin-universe-monitor-refresh-button">
          Yenile
        </Button>
        <Button type="button" variant="outline" onClick={downloadCsv} data-testid="admin-universe-monitor-export-csv-button">
          Export CSV
        </Button>
        <Link to="/admin/freshness-heatmap" data-testid="admin-universe-monitor-open-heatmap-link">
          <Button type="button" variant="outline" data-testid="admin-universe-monitor-open-heatmap-button">Freshness Heatmap Sayfası</Button>
        </Link>
      </div>

      <div className="grid gap-3 md:grid-cols-5 xl:grid-cols-10" data-testid="admin-universe-monitor-metrics-grid">
        {[
          ["total exchange symbols", summary?.total_exchange_symbols, "admin-universe-monitor-total-exchange"],
          ["active scan symbols", summary?.active_scan_symbols, "admin-universe-monitor-active-scan"],
          ["symbols evaluated this cycle", summary?.symbols_evaluated_this_cycle, "admin-universe-monitor-evaluated-this-cycle"],
          ["average cycle latency (ms)", summary?.average_cycle_latency_ms, "admin-universe-monitor-cycle-latency"],
          ["queue depth", summary?.queue_depth, "admin-universe-monitor-queue-depth"],
          ["blocked by permission", summary?.blocked_by_permission, "admin-universe-monitor-blocked-permission"],
          ["blocked by risk", summary?.blocked_by_risk, "admin-universe-monitor-blocked-risk"],
          ["blocked by liquidity", summary?.blocked_by_liquidity, "admin-universe-monitor-blocked-liquidity"],
          ["stale blocks", summary?.stale_blocks, "admin-universe-monitor-stale-blocks"],
          ["worker utilization", summary?.worker_utilization, "admin-universe-monitor-worker-utilization"],
          ["fallback active", String(summary?.fallback_active ?? false), "admin-universe-monitor-fallback-active"],
          ["fallback healthy streak", summary?.fallback_healthy_streak, "admin-universe-monitor-fallback-healthy-streak"],
        ].map(([label, value, key]) => (
          <article key={key} className="rounded border border-slate-700 bg-slate-900 p-3" data-testid={`${key}-card`}>
            <p className="text-xs text-slate-400">{label}</p>
            <p className="text-xl font-bold" data-testid={`${key}-value`}>{value ?? "-"}</p>
          </article>
        ))}
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4" data-testid="admin-runtime-risk-overview-grid">
        {[
          ["portfolio_exposure", runtimeSummary?.risk_overview?.portfolio_exposure, "admin-runtime-risk-portfolio-exposure"],
          ["symbol_exposure_count", (runtimeSummary?.risk_overview?.symbol_exposure || []).length, "admin-runtime-risk-symbol-exposure-count"],
          ["cluster_exposure_count", (runtimeSummary?.risk_overview?.cluster_exposure || []).length, "admin-runtime-risk-cluster-exposure-count"],
          ["daily_loss_pct", runtimeSummary?.risk_overview?.daily_loss?.daily_loss_pct, "admin-runtime-risk-daily-loss-pct"],
          ["execution_quality_score", runtimeSummary?.risk_overview?.execution_quality_score, "admin-runtime-risk-execution-quality-score"],
          ["fallback_state", String(runtimeSummary?.risk_overview?.fallback_state?.active ?? false), "admin-runtime-risk-fallback-state"],
          ["queue_depth", runtimeSummary?.risk_overview?.queue_depth, "admin-runtime-risk-queue-depth"],
          ["stale_reject_count", runtimeSummary?.risk_overview?.stale_reject_count, "admin-runtime-risk-stale-reject-count"],
          ["spread_reject_count", runtimeSummary?.risk_overview?.spread_reject_count, "admin-runtime-risk-spread-reject-count"],
          ["cooldown_state", Object.keys(runtimeSummary?.risk_overview?.cooldown_state || {}).length, "admin-runtime-risk-cooldown-state"],
          ["kill_switch_state", String(runtimeSummary?.risk_overview?.kill_switch_state?.pipeline_kill_switch_active ?? false), "admin-runtime-risk-kill-switch-state"],
        ].map(([label, value, key]) => (
          <article key={key} className="rounded border border-emerald-800/40 bg-emerald-950/20 p-3" data-testid={`${key}-card`}>
            <p className="text-xs uppercase tracking-widest text-emerald-200">{label}</p>
            <p className="mt-1 text-lg font-semibold" data-testid={`${key}-value`}>{value ?? "-"}</p>
          </article>
        ))}
      </div>

      <div className="grid gap-3 md:grid-cols-2" data-testid="admin-runtime-observability-trend-grid">
        <article className="rounded border border-slate-700 bg-slate-900 p-3" data-testid="admin-runtime-observability-latency-trend-card">
          <p className="text-xs uppercase tracking-widest text-slate-300">execution latency trend</p>
          <div className="mt-2 space-y-1 text-xs" data-testid="admin-runtime-observability-latency-trend-list">
            {(runtimeSummary?.observability_trends?.execution_latency_trend || []).slice(-8).map((item, idx) => (
              <p key={`latency-${idx}`} data-testid={`admin-runtime-observability-latency-trend-item-${idx}`}>{item.ts} · {item.value}</p>
            ))}
          </div>
        </article>
        <article className="rounded border border-slate-700 bg-slate-900 p-3" data-testid="admin-runtime-observability-veto-trend-card">
          <p className="text-xs uppercase tracking-widest text-slate-300">risk veto rate trend</p>
          <div className="mt-2 space-y-1 text-xs" data-testid="admin-runtime-observability-veto-trend-list">
            {(runtimeSummary?.observability_trends?.risk_veto_rate_trend || []).slice(-8).map((item, idx) => (
              <p key={`veto-${idx}`} data-testid={`admin-runtime-observability-veto-trend-item-${idx}`}>{item.ts} · {item.value}</p>
            ))}
          </div>
        </article>
        <article className="rounded border border-slate-700 bg-slate-900 p-3" data-testid="admin-runtime-observability-scanner-latency-trend-card">
          <p className="text-xs uppercase tracking-widest text-slate-300">scanner cycle latency trend</p>
          <div className="mt-2 space-y-1 text-xs" data-testid="admin-runtime-observability-scanner-latency-trend-list">
            {(runtimeSummary?.observability_trends?.scanner_cycle_latency_trend || []).slice(-8).map((item, idx) => (
              <p key={`scanner-latency-${idx}`} data-testid={`admin-runtime-observability-scanner-latency-trend-item-${idx}`}>{item.ts} · {item.value}</p>
            ))}
          </div>
        </article>
        <article className="rounded border border-slate-700 bg-slate-900 p-3" data-testid="admin-runtime-observability-fallback-trend-card">
          <p className="text-xs uppercase tracking-widest text-slate-300">fallback activation trend</p>
          <div className="mt-2 space-y-1 text-xs" data-testid="admin-runtime-observability-fallback-trend-list">
            {(runtimeSummary?.observability_trends?.fallback_activation_rate_trend || []).slice(-8).map((item, idx) => (
              <p key={`fallback-${idx}`} data-testid={`admin-runtime-observability-fallback-trend-item-${idx}`}>{item.ts} · {item.value}</p>
            ))}
          </div>
        </article>
        <article className="rounded border border-slate-700 bg-slate-900 p-3 md:col-span-2" data-testid="admin-runtime-observability-pnl-trend-card">
          <p className="text-xs uppercase tracking-widest text-slate-300">PnL trend</p>
          <div className="mt-2 grid gap-1 text-xs md:grid-cols-2" data-testid="admin-runtime-observability-pnl-trend-list">
            {(runtimeSummary?.risk_overview?.pnl_trend || []).slice(-12).map((item, idx) => (
              <p key={`pnl-${idx}`} data-testid={`admin-runtime-observability-pnl-trend-item-${idx}`}>
                {item.closed_at} · {item.symbol} · pnl={item.realized_pnl}
              </p>
            ))}
          </div>
        </article>
      </div>

      <div className="grid gap-3 md:grid-cols-2" data-testid="admin-universe-monitor-rollout-panels">
        <article className="rounded border border-emerald-800/50 bg-emerald-950/20 p-3" data-testid="admin-universe-monitor-rollout-status-panel">
          <p className="text-xs uppercase tracking-widest text-emerald-300" data-testid="admin-universe-monitor-rollout-status-title">Rollout Orchestrator</p>
          <p className="mt-2 text-xs" data-testid="admin-universe-monitor-rollout-current-stage">Current Stage: {rollout?.current_stage || "-"}</p>
          <p className="text-xs" data-testid="admin-universe-monitor-rollout-recommended-stage">Recommended Stage: {rollout?.recommended_stage || "-"}</p>
          <p className="text-xs" data-testid="admin-universe-monitor-rollout-approval-required">Admin Approval Required: {String(rollout?.requires_admin_approval ?? true)}</p>
          <div className="mt-3 flex flex-wrap gap-2" data-testid="admin-universe-monitor-rollout-actions">
            <Button type="button" variant="outline" onClick={requestRolloutRecommendation} data-testid="admin-universe-monitor-rollout-recommend-button">
              KPI Recommendation Üret
            </Button>
            <Button type="button" variant="outline" onClick={approveRolloutRecommendation} data-testid="admin-universe-monitor-rollout-approve-button">
              Recommend Stage'i Onayla
            </Button>
          </div>
        </article>

        <article className="rounded border border-cyan-800/50 bg-cyan-950/20 p-3" data-testid="admin-universe-monitor-trend-summary-panel">
          <p className="text-xs uppercase tracking-widest text-cyan-300" data-testid="admin-universe-monitor-trend-summary-title">Trend Summary ({windowSize})</p>
          <p className="mt-2 text-xs" data-testid="admin-universe-monitor-trend-summary-latency">Latest Latency: {latestTrendPoint?.average_cycle_latency_ms ?? "-"}</p>
          <p className="text-xs" data-testid="admin-universe-monitor-trend-summary-stale">Latest Stale Blocks: {latestTrendPoint?.stale_blocks ?? "-"}</p>
          <p className="text-xs" data-testid="admin-universe-monitor-trend-summary-dropped">Latest Dropped: {latestTrendPoint?.dropped_evaluations ?? "-"}</p>
          <p className="text-xs" data-testid="admin-universe-monitor-trend-summary-points">Points: {(trend?.points || []).length}</p>
        </article>
      </div>

      <div className="grid gap-3 md:grid-cols-2" data-testid="admin-universe-monitor-slow-panels">
        <article className="rounded border border-slate-800 bg-slate-900 p-3" data-testid="admin-universe-monitor-top-slow-strategies-panel">
          <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="admin-universe-monitor-top-slow-strategies-title">Top Slow Strategies</p>
          <div className="mt-2 space-y-1" data-testid="admin-universe-monitor-top-slow-strategies-list">
            {(summary?.top_slow_strategies || []).slice(0, 10).map((item, idx) => (
              <p key={`slow-strategy-${idx}`} className="text-xs" data-testid={`admin-universe-monitor-top-slow-strategy-${idx}`}>
                {item.strategy_id} · avg={item.avg_ms}ms · calls={item.calls}
              </p>
            ))}
            {(summary?.top_slow_strategies || []).length === 0 && <p className="text-xs text-slate-500" data-testid="admin-universe-monitor-top-slow-strategies-empty">Veri yok.</p>}
          </div>
        </article>

        <article className="rounded border border-slate-800 bg-slate-900 p-3" data-testid="admin-universe-monitor-top-slow-symbols-panel">
          <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="admin-universe-monitor-top-slow-symbols-title">Top Slow Symbols</p>
          <div className="mt-2 space-y-1" data-testid="admin-universe-monitor-top-slow-symbols-list">
            {(summary?.top_slow_symbols || []).slice(0, 10).map((item, idx) => (
              <p key={`slow-symbol-${idx}`} className="text-xs" data-testid={`admin-universe-monitor-top-slow-symbol-${idx}`}>
                {item.symbol} · {item.elapsed_ms}ms
              </p>
            ))}
            {(summary?.top_slow_symbols || []).length === 0 && <p className="text-xs text-slate-500" data-testid="admin-universe-monitor-top-slow-symbols-empty">Veri yok.</p>}
          </div>
        </article>
      </div>

      <div className="grid gap-3 md:grid-cols-2" data-testid="admin-universe-monitor-breakdown-panels">
        <article className="rounded border border-fuchsia-800/50 bg-fuchsia-950/20 p-3" data-testid="admin-universe-monitor-user-breakdown-panel">
          <p className="text-xs uppercase tracking-widest text-fuchsia-300" data-testid="admin-universe-monitor-user-breakdown-title">User/Profile Breakdown</p>
          <div className="mt-2 max-h-52 space-y-1 overflow-auto" data-testid="admin-universe-monitor-user-breakdown-list">
            {(breakdown?.user_breakdown || []).slice(0, 20).map((item, idx) => (
              <p key={`user-breakdown-${idx}`} className="text-xs" data-testid={`admin-universe-monitor-user-breakdown-item-${idx}`}>
                {item.user_id} · runs={item.runs} · eval={item.symbols_evaluated} · false_block={item.false_block_rate} · missed={item.missed_update_rate}
              </p>
            ))}
          </div>
        </article>

        <article className="rounded border border-indigo-800/50 bg-indigo-950/20 p-3" data-testid="admin-universe-monitor-regime-breakdown-panel">
          <p className="text-xs uppercase tracking-widest text-indigo-300" data-testid="admin-universe-monitor-regime-breakdown-title">Regime Breakdown</p>
          <div className="mt-2 max-h-52 space-y-1 overflow-auto" data-testid="admin-universe-monitor-regime-breakdown-list">
            {(breakdown?.regime_breakdown || []).slice(0, 20).map((item, idx) => (
              <p key={`regime-breakdown-${idx}`} className="text-xs" data-testid={`admin-universe-monitor-regime-breakdown-item-${idx}`}>
                {item.regime} · count={item.count}
              </p>
            ))}
          </div>
        </article>
      </div>

      <article className="rounded border border-rose-800/50 bg-rose-950/20 p-3" data-testid="admin-universe-monitor-freshness-heatmap-widget">
        <p className="text-xs uppercase tracking-widest text-rose-300" data-testid="admin-universe-monitor-freshness-heatmap-title">Freshness SLA Breach Heatmap (Embedded)</p>
        <div className="mt-2 max-h-56 space-y-1 overflow-auto" data-testid="admin-universe-monitor-freshness-heatmap-list">
          {(heatmap?.items || []).slice(0, 40).map((item, idx) => (
            <p key={`heatmap-${idx}`} className="text-xs" data-testid={`admin-universe-monitor-freshness-heatmap-item-${idx}`}>
              {item.symbol}:{item.timeframe} · stale_rate={item.stale_rate} · stale={item.stale} / total={item.total} · avg_age={item.avg_snapshot_age}
            </p>
          ))}
          {(heatmap?.items || []).length === 0 && <p className="text-xs text-rose-200" data-testid="admin-universe-monitor-freshness-heatmap-empty">Heatmap verisi yok.</p>}
        </div>
      </article>

      <article className="rounded border border-amber-800/50 bg-amber-950/20 p-3" data-testid="admin-universe-monitor-fallback-events-panel">
        <p className="text-xs uppercase tracking-widest text-amber-300" data-testid="admin-universe-monitor-fallback-events-title">Fallback Timeline</p>
        <div className="mt-2 max-h-64 space-y-1 overflow-auto" data-testid="admin-universe-monitor-fallback-events-list">
          {fallbackEvents.map((item, idx) => (
            <div key={item.id || idx} className="rounded border border-amber-700/50 p-2" data-testid={`admin-universe-monitor-fallback-event-${idx}`}>
              <p className="text-xs" data-testid={`admin-universe-monitor-fallback-event-timestamp-${idx}`}>timestamp: {String(item.timestamp || "-")}</p>
              <p className="text-xs" data-testid={`admin-universe-monitor-fallback-event-trigger-metric-${idx}`}>trigger_metric: {item.trigger_metric || "-"}</p>
              <p className="text-xs" data-testid={`admin-universe-monitor-fallback-event-threshold-breach-${idx}`}>threshold_breach: {JSON.stringify(item.threshold_breach || {})}</p>
              <p className="text-xs" data-testid={`admin-universe-monitor-fallback-event-exit-reason-${idx}`}>exit_reason: {item.exit_reason || "-"}</p>
              <p className="text-xs" data-testid={`admin-universe-monitor-fallback-event-cycle-snapshot-${idx}`}>cycle_snapshot: {JSON.stringify(item.cycle_snapshot || {})}</p>
            </div>
          ))}
          {fallbackEvents.length === 0 && <p className="text-xs text-amber-200" data-testid="admin-universe-monitor-fallback-events-empty">Fallback event kaydı yok.</p>}
        </div>
      </article>

      <div className="grid gap-3 border border-slate-800 bg-slate-900 p-4" data-testid="admin-universe-monitor-debug-panel">
        <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="admin-universe-monitor-debug-title">Debug Effective Universe</p>
        <p className="text-xs" data-testid="admin-universe-monitor-debug-market-count">market_symbols_count: {debugPayload?.market_symbols_count ?? "-"}</p>
        <p className="text-xs" data-testid="admin-universe-monitor-debug-after-blacklist">after_blacklist: {debugPayload?.after_blacklist ?? "-"}</p>
        <p className="text-xs" data-testid="admin-universe-monitor-debug-after-scanner">after_scanner_mode: {debugPayload?.after_scanner_mode ?? "-"}</p>
        <p className="text-xs" data-testid="admin-universe-monitor-debug-after-liquidity">after_liquidity_filter: {debugPayload?.after_liquidity_filter ?? "-"}</p>
        <div className="max-h-52 overflow-auto rounded border border-slate-700 p-2" data-testid="admin-universe-monitor-debug-final-symbols-wrapper">
          <p className="text-xs text-slate-400" data-testid="admin-universe-monitor-debug-final-symbols-label">final_symbols</p>
          <p className="text-xs font-mono" data-testid="admin-universe-monitor-debug-final-symbols-value">{(debugPayload?.final_symbols || []).join(", ") || "-"}</p>
        </div>
      </div>

      {loading && <p className="text-xs text-slate-400" data-testid="admin-universe-monitor-loading">Yükleniyor...</p>}
    </section>
  );
};
