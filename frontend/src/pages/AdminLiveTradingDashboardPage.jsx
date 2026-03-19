import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

const WINDOW_OPTIONS = ["1h", "6h", "24h"];

const MetricCard = ({ title, value, testId }) => (
  <article className="rounded border border-slate-700 bg-slate-900 p-3" data-testid={`${testId}-card`}>
    <p className="text-xs uppercase tracking-wider text-slate-500" data-testid={`${testId}-label`}>{title}</p>
    <p className="mt-1 text-lg font-bold" data-testid={`${testId}-value`}>{value ?? "-"}</p>
  </article>
);

export const AdminLiveTradingDashboardPage = () => {
  const [windowSize, setWindowSize] = useState("1h");
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState(null);
  const [scannerHealth, setScannerHealth] = useState(null);
  const [executionQuality, setExecutionQuality] = useState(null);
  const [riskSummary, setRiskSummary] = useState(null);
  const [dailyReport, setDailyReport] = useState(null);
  const [learningSummary, setLearningSummary] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const [summaryRes, scannerRes, executionRes, riskRes, dailyRes, learningRes] = await Promise.all([
        apiClient.get("/admin/live-trading/summary", { params: { window: windowSize } }),
        apiClient.get("/admin/live-trading/scanner-health", { params: { window: windowSize } }),
        apiClient.get("/admin/live-trading/execution-quality", { params: { window: windowSize } }),
        apiClient.get("/admin/live-trading/risk-summary", { params: { window: windowSize } }),
        apiClient.get("/admin/live-trading/daily-report"),
        apiClient.get("/admin/live-trading/learning-summary", { params: { window: windowSize } }),
      ]);

      setSummary(summaryRes.data || null);
      setScannerHealth(scannerRes.data || null);
      setExecutionQuality(executionRes.data || null);
      setRiskSummary(riskRes.data || null);
      setDailyReport(dailyRes.data || null);
      setLearningSummary(learningRes.data || null);
    } catch (error) {
      const detail = error?.response?.data?.detail;
      const message = typeof detail === "string" ? detail : "Live Trading Dashboard verisi alınamadı";
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [windowSize]);

  useEffect(() => {
    const timer = setInterval(() => {
      load();
    }, 30000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [windowSize]);

  const alertStatus = (summary?.critical_alerts?.status || "normal").toLowerCase();

  const alertPanelClass =
    alertStatus === "critical"
      ? "border-red-700 bg-red-950/20"
      : alertStatus === "warning"
        ? "border-yellow-700 bg-yellow-950/20"
        : "border-emerald-700 bg-emerald-950/20";

  const oneHourReportText = useMemo(() => {
    const s = summary || {};
    return [
      "CANLI TEST RAPORU — 1 SAAT",
      "",
      `execution_mode: ${s?.system_health?.execution_mode || "-"}`,
      `trades_count: ${dailyReport?.trades_count ?? "-"}`,
      `win_rate: ${dailyReport?.win_rate ?? "-"}`,
      `pnl_usdt: ${dailyReport?.pnl_usdt ?? "-"}`,
      `execution_quality_score: ${s?.system_health?.execution_quality_score ?? "-"}`,
      `fallback_rate: ${scannerHealth?.fallback_rate ?? "-"}`,
      `scan_latency_avg_ms: ${s?.system_health?.scan_latency_avg_ms ?? "-"}`,
      `decision_latency_avg_ms: ${s?.system_health?.decision_latency_avg_ms ?? "-"}`,
      `risk_reject_rate: ${riskSummary?.risk_reject_rate ?? "-"}`,
      `allow/reduce/pass/block: ${riskSummary?.allow_count ?? 0}/${riskSummary?.reduce_size_count ?? 0}/${riskSummary?.pass_count ?? 0}/${riskSummary?.block_count ?? 0}`,
      `critical_errors: ${(dailyReport?.critical_errors || []).join(", ") || "none"}`,
    ].join("\n");
  }, [summary, scannerHealth, riskSummary, dailyReport]);

  const dailyReportText = useMemo(() => {
    const report = dailyReport || {};
    return [
      "CANLI TEST RAPORU — GÜNLÜK",
      "",
      `date: ${report?.date || "-"}`,
      `execution_mode: ${report?.execution_mode || "-"}`,
      `trades_count: ${report?.trades_count ?? "-"}`,
      `win_rate: ${report?.win_rate ?? "-"}`,
      `pnl_usdt: ${report?.pnl_usdt ?? "-"}`,
      `max_drawdown_pct: ${report?.max_drawdown_pct ?? "-"}`,
      `execution_quality_score: ${report?.execution_quality_score ?? "-"}`,
      `fallback_rate: ${report?.fallback_rate ?? "-"}`,
      `scan_latency_avg_ms: ${report?.scan_latency_avg_ms ?? "-"}`,
      `decision_latency_avg_ms: ${report?.decision_latency_avg_ms ?? "-"}`,
      `risk_reject_rate: ${report?.risk_reject_rate ?? "-"}`,
      `allow_count: ${report?.allow_count ?? "-"}`,
      `reduce_size_count: ${report?.reduce_size_count ?? "-"}`,
      `pass_count: ${report?.pass_count ?? "-"}`,
      `block_count: ${report?.block_count ?? "-"}`,
      `top_strategy_stats: ${JSON.stringify(report?.top_3_strategy_stats || [])}`,
      `top_symbol_stats: ${JSON.stringify(report?.top_3_symbol_stats || [])}`,
      `critical_errors: ${(report?.critical_errors || []).join(", ") || "none"}`,
      "yorum/not:",
    ].join("\n");
  }, [dailyReport]);

  const downloadDailyExport = async (format) => {
    try {
      const isCsv = format === "csv";
      const response = await apiClient.get("/admin/live-trading/daily-report/export", {
        params: { format },
        responseType: isCsv ? "blob" : "json",
      });

      if (isCsv) {
        const blobUrl = window.URL.createObjectURL(new Blob([response.data], { type: "text/csv" }));
        const link = document.createElement("a");
        link.href = blobUrl;
        link.download = `live_trading_daily_report_${dailyReport?.date || "latest"}.csv`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(blobUrl);
      } else {
        const blob = new Blob([JSON.stringify(response.data, null, 2)], { type: "application/json" });
        const blobUrl = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = blobUrl;
        link.download = `live_trading_daily_report_${dailyReport?.date || "latest"}.json`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(blobUrl);
      }
      toast.success(`Daily report ${format.toUpperCase()} export hazır`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Daily report export başarısız");
    }
  };

  return (
    <section className="space-y-4" data-testid="admin-live-trading-dashboard-page">
      <header className="border border-emerald-800/60 bg-emerald-950/20 p-4" data-testid="admin-live-trading-dashboard-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-emerald-300" data-testid="admin-live-trading-dashboard-title">Live Trading Dashboard</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="admin-live-trading-dashboard-description">
          Scanner + Risk + Execution + Learning metriklerini tek ekranda operasyonel olarak takip edin.
        </p>
      </header>

      <div className="flex flex-wrap items-end gap-2" data-testid="admin-live-trading-dashboard-toolbar">
        <label className="space-y-1" data-testid="admin-live-trading-dashboard-window-field">
          <span className="text-xs text-slate-400">Summary Window</span>
          <select
            value={windowSize}
            onChange={(event) => setWindowSize(event.target.value)}
            className="h-10 rounded border border-slate-700 bg-black px-2 text-sm"
            data-testid="admin-live-trading-dashboard-window-select"
          >
            {WINDOW_OPTIONS.map((option) => (
              <option key={option} value={option} data-testid={`admin-live-trading-dashboard-window-option-${option}`}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <Button type="button" variant="outline" onClick={load} data-testid="admin-live-trading-dashboard-refresh-button">
          Yenile
        </Button>
        <Button type="button" variant="outline" onClick={() => downloadDailyExport("json")} data-testid="admin-live-trading-dashboard-export-json-button">
          Daily Export JSON
        </Button>
        <Button type="button" variant="outline" onClick={() => downloadDailyExport("csv")} data-testid="admin-live-trading-dashboard-export-csv-button">
          Daily Export CSV
        </Button>
      </div>

      <div className="grid gap-3 md:grid-cols-4" data-testid="admin-live-trading-dashboard-kpi-grid">
        <MetricCard title="execution_mode" value={summary?.system_health?.execution_mode || "-"} testId="live-dashboard-kpi-execution-mode" />
        <MetricCard title="execution_quality_score" value={summary?.system_health?.execution_quality_score ?? "-"} testId="live-dashboard-kpi-execution-quality-score" />
        <MetricCard title="queue_depth" value={summary?.system_health?.queue_depth ?? "-"} testId="live-dashboard-kpi-queue-depth" />
        <MetricCard title="fallback_rate" value={scannerHealth?.fallback_rate ?? "-"} testId="live-dashboard-kpi-fallback-rate" />
      </div>

      <div className={`rounded border p-4 ${alertPanelClass}`} data-testid="live-dashboard-critical-alerts-panel">
        <p className="text-xs uppercase tracking-widest" data-testid="live-dashboard-critical-alerts-title">Critical Alerts</p>
        <p className="mt-1 text-sm" data-testid="live-dashboard-critical-alerts-status">status: {summary?.critical_alerts?.status || "normal"}</p>
        <div className="mt-2 space-y-1 text-sm" data-testid="live-dashboard-critical-alerts-list">
          {(summary?.critical_alerts?.items || []).length === 0 ? (
            <p data-testid="live-dashboard-critical-alerts-empty">normal — aktif kritik uyarı yok</p>
          ) : (
            (summary?.critical_alerts?.items || []).map((item, idx) => (
              <p key={`${item.code}-${idx}`} data-testid={`live-dashboard-critical-alert-item-${idx}`}>
                {item.code} · status={item.status} · value={String(item.value)}
              </p>
            ))
          )}
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-2" data-testid="live-dashboard-sections-grid">
        <article className="rounded border border-slate-700 bg-slate-900 p-4" data-testid="live-dashboard-system-health-section">
          <h3 className="text-base font-semibold" data-testid="live-dashboard-system-health-title">System Health</h3>
          <div className="mt-3 grid gap-2 sm:grid-cols-2" data-testid="live-dashboard-system-health-metrics">
            <MetricCard title="kill_switch_active" value={String(summary?.system_health?.kill_switch_active ?? false)} testId="live-dashboard-system-health-kill-switch" />
            <MetricCard title="fallback_active" value={String(summary?.system_health?.fallback_active ?? false)} testId="live-dashboard-system-health-fallback-active" />
            <MetricCard title="scan_latency_avg_ms" value={summary?.system_health?.scan_latency_avg_ms ?? "-"} testId="live-dashboard-system-health-scan-latency" />
            <MetricCard title="decision_latency_avg_ms" value={summary?.system_health?.decision_latency_avg_ms ?? "-"} testId="live-dashboard-system-health-decision-latency" />
            <MetricCard title="snapshot_age_avg_ms" value={summary?.system_health?.snapshot_age_avg_ms ?? "-"} testId="live-dashboard-system-health-snapshot-age" />
          </div>
        </article>

        <article className="rounded border border-slate-700 bg-slate-900 p-4" data-testid="live-dashboard-trading-performance-section">
          <h3 className="text-base font-semibold" data-testid="live-dashboard-trading-performance-title">Trading Performance</h3>
          <div className="mt-3 grid gap-2 sm:grid-cols-2" data-testid="live-dashboard-trading-performance-metrics">
            <MetricCard title="trades_count_today" value={summary?.trading_performance?.trades_count_today ?? "-"} testId="live-dashboard-trading-trades-count" />
            <MetricCard title="win_rate_today" value={summary?.trading_performance?.win_rate_today ?? "-"} testId="live-dashboard-trading-win-rate" />
            <MetricCard title="pnl_today_usdt" value={summary?.trading_performance?.pnl_today_usdt ?? "-"} testId="live-dashboard-trading-pnl" />
            <MetricCard title="max_drawdown_today_pct" value={summary?.trading_performance?.max_drawdown_today_pct ?? "-"} testId="live-dashboard-trading-max-drawdown" />
            <MetricCard title="avg_hold_time_min" value={summary?.trading_performance?.avg_hold_time_min ?? "-"} testId="live-dashboard-trading-avg-hold-time" />
            <MetricCard title="open_positions_count" value={summary?.trading_performance?.open_positions_count ?? "-"} testId="live-dashboard-trading-open-positions" />
          </div>
        </article>

        <article className="rounded border border-slate-700 bg-slate-900 p-4" data-testid="live-dashboard-risk-engine-section">
          <h3 className="text-base font-semibold" data-testid="live-dashboard-risk-engine-title">Risk Engine</h3>
          <div className="mt-3 grid gap-2 sm:grid-cols-2" data-testid="live-dashboard-risk-engine-metrics">
            <MetricCard title="allow_count" value={riskSummary?.allow_count ?? "-"} testId="live-dashboard-risk-allow-count" />
            <MetricCard title="reduce_size_count" value={riskSummary?.reduce_size_count ?? "-"} testId="live-dashboard-risk-reduce-count" />
            <MetricCard title="pass_count" value={riskSummary?.pass_count ?? "-"} testId="live-dashboard-risk-pass-count" />
            <MetricCard title="block_count" value={riskSummary?.block_count ?? "-"} testId="live-dashboard-risk-block-count" />
            <MetricCard title="risk_reject_rate" value={riskSummary?.risk_reject_rate ?? "-"} testId="live-dashboard-risk-reject-rate" />
            <MetricCard title="daily_loss_pct" value={riskSummary?.daily_loss_pct ?? "-"} testId="live-dashboard-risk-daily-loss-pct" />
            <MetricCard title="portfolio_exposure_pct" value={riskSummary?.portfolio_exposure_pct ?? "-"} testId="live-dashboard-risk-portfolio-exposure-pct" />
          </div>
        </article>

        <article className="rounded border border-slate-700 bg-slate-900 p-4" data-testid="live-dashboard-scanner-health-section">
          <h3 className="text-base font-semibold" data-testid="live-dashboard-scanner-health-title">Scanner Health</h3>
          <div className="mt-3 grid gap-2 sm:grid-cols-2" data-testid="live-dashboard-scanner-health-metrics">
            <MetricCard title="symbols_scanned" value={scannerHealth?.symbols_scanned ?? "-"} testId="live-dashboard-scanner-symbols-scanned" />
            <MetricCard title="discovery_candidates" value={scannerHealth?.discovery_candidates ?? "-"} testId="live-dashboard-scanner-discovery-candidates" />
            <MetricCard title="qualified_candidates" value={scannerHealth?.qualified_candidates ?? "-"} testId="live-dashboard-scanner-qualified-candidates" />
            <MetricCard title="decisions_generated" value={scannerHealth?.decisions_generated ?? "-"} testId="live-dashboard-scanner-decisions-generated" />
            <MetricCard title="fallback_rate" value={scannerHealth?.fallback_rate ?? "-"} testId="live-dashboard-scanner-fallback-rate" />
            <MetricCard title="stale_skip_count" value={scannerHealth?.stale_skip_count ?? "-"} testId="live-dashboard-scanner-stale-skip-count" />
            <MetricCard title="spread_reject_count" value={scannerHealth?.spread_reject_count ?? "-"} testId="live-dashboard-scanner-spread-reject-count" />
          </div>
        </article>

        <article className="rounded border border-slate-700 bg-slate-900 p-4" data-testid="live-dashboard-execution-quality-section">
          <h3 className="text-base font-semibold" data-testid="live-dashboard-execution-quality-title">Execution Quality</h3>
          <div className="mt-3 grid gap-2 sm:grid-cols-2" data-testid="live-dashboard-execution-quality-metrics">
            <MetricCard title="execution_latency_avg_ms" value={executionQuality?.execution_latency_avg_ms ?? "-"} testId="live-dashboard-execution-latency" />
            <MetricCard title="slippage_avg_pct" value={executionQuality?.slippage_avg_pct ?? "-"} testId="live-dashboard-execution-slippage" />
            <MetricCard title="reject_rate" value={executionQuality?.reject_rate ?? "-"} testId="live-dashboard-execution-reject-rate" />
            <MetricCard title="partial_fill_rate" value={executionQuality?.partial_fill_rate ?? "-"} testId="live-dashboard-execution-partial-fill-rate" />
            <MetricCard title="precision_error_count" value={executionQuality?.precision_error_count ?? "-"} testId="live-dashboard-execution-precision-error-count" />
            <MetricCard title="retry_count" value={executionQuality?.retry_count ?? "-"} testId="live-dashboard-execution-retry-count" />
          </div>
        </article>

        <article className="rounded border border-slate-700 bg-slate-900 p-4" data-testid="live-dashboard-learning-section">
          <h3 className="text-base font-semibold" data-testid="live-dashboard-learning-title">Learning Snapshot</h3>
          <div className="mt-3 grid gap-2 sm:grid-cols-2" data-testid="live-dashboard-learning-metrics">
            <MetricCard title="strategy_top_win_rate" value={learningSummary?.strategy_top_win_rate?.hit_rate ?? "-"} testId="live-dashboard-learning-top-win-rate" />
            <MetricCard title="strategy_top_loss_rate" value={learningSummary?.strategy_top_loss_rate?.hit_rate ?? "-"} testId="live-dashboard-learning-top-loss-rate" />
            <MetricCard title="false_allow_rate" value={learningSummary?.false_allow_rate ?? "-"} testId="live-dashboard-learning-false-allow-rate" />
            <MetricCard title="false_reject_rate" value={learningSummary?.false_reject_rate ?? "-"} testId="live-dashboard-learning-false-reject-rate" />
            <MetricCard title="new_recommendations_count" value={learningSummary?.new_recommendations_count ?? "-"} testId="live-dashboard-learning-new-recommendations-count" />
          </div>
          <div className="mt-3 space-y-1 text-xs" data-testid="live-dashboard-learning-quality-by-strategy-list">
            {(learningSummary?.quality_score_by_strategy || []).slice(0, 5).map((item, idx) => (
              <p key={`${item.strategy}-${idx}`} data-testid={`live-dashboard-learning-quality-by-strategy-item-${idx}`}>
                {item.strategy} · quality={item.quality_score} · hit_rate={item.hit_rate}
              </p>
            ))}
          </div>
        </article>
      </div>

      <div className="grid gap-3 lg:grid-cols-2" data-testid="live-dashboard-report-standard-grid">
        <article className="rounded border border-slate-700 bg-slate-900 p-4" data-testid="live-dashboard-report-1h-panel">
          <h3 className="text-base font-semibold" data-testid="live-dashboard-report-1h-title">Rapor Standardı — 1 Saat</h3>
          <pre className="mt-3 overflow-x-auto whitespace-pre-wrap text-xs" data-testid="live-dashboard-report-1h-text">
            {oneHourReportText}
          </pre>
        </article>
        <article className="rounded border border-slate-700 bg-slate-900 p-4" data-testid="live-dashboard-report-daily-panel">
          <h3 className="text-base font-semibold" data-testid="live-dashboard-report-daily-title">Rapor Standardı — Günlük</h3>
          <pre className="mt-3 overflow-x-auto whitespace-pre-wrap text-xs" data-testid="live-dashboard-report-daily-text">
            {dailyReportText}
          </pre>
        </article>
      </div>

      <p className="text-xs text-slate-500" data-testid="live-dashboard-loading-state">loading={String(loading)}</p>
    </section>
  );
};
