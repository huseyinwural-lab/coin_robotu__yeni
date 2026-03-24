import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export const StrategyMetricsPanel = ({
  metricsSummary,
  metricsTrend,
  driftSummary,
  falseSignalSummary,
  healthStatusBadge,
}) => {
  const qualityAlerts = metricsSummary?.metrics?.quality_alerts || [];

  return (
    <>
      <div className="grid gap-4 xl:grid-cols-2" data-testid="admin-strategy-observability-grid">
        <div className="space-y-2 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-metrics-summary-panel">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-strategy-metrics-summary-title">Version Metrics Summary</p>
          <div className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${healthStatusBadge === "GOOD" ? "bg-emerald-500/20 text-emerald-300" : healthStatusBadge === "WARNING" ? "bg-amber-500/20 text-amber-300" : "bg-red-500/20 text-red-300"}`} data-testid="admin-strategy-health-status-badge">
            HEALTH: {healthStatusBadge}
          </div>

          {metricsSummary ? (
            <div className="space-y-1 text-xs" data-testid="admin-strategy-metrics-summary-content">
              <p data-testid="admin-strategy-metrics-hit-rate">hit_rate: {metricsSummary?.metrics?.hit_rate ?? "-"}</p>
              <p data-testid="admin-strategy-metrics-block-rate">block_reject_rate: {metricsSummary?.metrics?.block_reject_rate ?? "-"}</p>
              <p data-testid="admin-strategy-metrics-false-allow">false_allow_rate: {metricsSummary?.metrics?.false_allow_rate ?? "-"}</p>
              <p data-testid="admin-strategy-metrics-false-reject">false_reject_rate: {metricsSummary?.metrics?.false_reject_rate ?? "-"}</p>
              <p data-testid="admin-strategy-metrics-pnl">pnl_contribution: {metricsSummary?.metrics?.pnl_contribution ?? "-"}</p>
              <p data-testid="admin-strategy-metrics-execution-quality">execution_quality: {metricsSummary?.metrics?.execution_quality ?? "-"}</p>
              <p data-testid="admin-strategy-metrics-drift-alerts">drift_alerts: {metricsSummary?.metrics?.drift_alerts ?? "-"}</p>
              <p data-testid="admin-strategy-metrics-slippage-p95">slippage_p95_bps: {metricsSummary?.metrics?.slippage_p95_bps ?? "-"}</p>
              <p data-testid="admin-strategy-metrics-latency-p95">latency_p95_ms: {metricsSummary?.metrics?.latency_p95_ms ?? "-"}</p>
              <p data-testid="admin-strategy-metrics-health-score">version_health_score: {metricsSummary?.metrics?.version_health_score ?? "-"}</p>
            </div>
          ) : (
            <p className="text-xs text-slate-400" data-testid="admin-strategy-metrics-summary-empty">Metrics yok.</p>
          )}
        </div>

        <div className="space-y-2 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-observability-secondary-panel">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-strategy-observability-secondary-title">Drift / False Signal Summary</p>
          <p className="text-xs" data-testid="admin-strategy-drift-count">drift_alert_count: {driftSummary?.count ?? 0}</p>
          <p className="text-xs" data-testid="admin-strategy-false-allow-rate">false_allow_rate: {falseSignalSummary?.false_allow_rate ?? "-"}</p>
          <p className="text-xs" data-testid="admin-strategy-false-reject-rate">false_reject_rate: {falseSignalSummary?.false_reject_rate ?? "-"}</p>
          <p className="text-xs" data-testid="admin-strategy-signal-quality">signal_quality_last_50: {falseSignalSummary?.signal_quality_last_50 ?? "-"}</p>
        </div>
      </div>

      <div className="space-y-2 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-quality-alerts-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-strategy-quality-alerts-title">Execution Quality Alerts</p>
        {qualityAlerts.length === 0 ? (
          <p className="text-xs text-slate-400" data-testid="admin-strategy-quality-alerts-empty">Aktif quality anomaly yok.</p>
        ) : (
          <div className="space-y-2" data-testid="admin-strategy-quality-alerts-list">
            {qualityAlerts.map((alert, idx) => (
              <div
                key={`${alert.key}-${idx}`}
                className={`rounded border p-2 text-xs ${alert.severity === "CRITICAL" ? "border-red-600 bg-red-950/30 text-red-200" : "border-amber-600 bg-amber-950/20 text-amber-200"}`}
                data-testid={`admin-strategy-quality-alert-item-${idx}`}
              >
                <p data-testid={`admin-strategy-quality-alert-key-${idx}`}>{alert.key}</p>
                <p data-testid={`admin-strategy-quality-alert-message-${idx}`}>{alert.message}</p>
                <p data-testid={`admin-strategy-quality-alert-threshold-${idx}`}>value={alert.value} / threshold={alert.threshold}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="space-y-2 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-trend-chart-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-strategy-trend-chart-title">Trend + Anomaly Band</p>
        <div className="h-64 w-full" data-testid="admin-strategy-trend-chart-wrapper">
          {(metricsTrend?.trend_series || []).length > 0 ? (
            <ResponsiveContainer width="100%" height="100%" minWidth={320} minHeight={220}>
              <LineChart data={metricsTrend?.trend_series || []} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="timestamp" hide />
                <YAxis stroke="#94a3b8" />
                <Tooltip
                  contentStyle={{ backgroundColor: "#0f172a", borderColor: "#334155", color: "#e2e8f0" }}
                  labelStyle={{ color: "#cbd5e1" }}
                />
                <Line type="monotone" dataKey="score_delta" stroke="#f97316" dot={false} name="score_delta" />
                <Line type="monotone" dataKey="anomaly_upper" stroke="#22c55e" dot={false} name="anomaly_upper" strokeDasharray="5 5" />
                <Line type="monotone" dataKey="anomaly_lower" stroke="#ef4444" dot={false} name="anomaly_lower" strokeDasharray="5 5" />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-xs text-slate-400" data-testid="admin-strategy-trend-chart-empty">Trend verisi bulunamadı.</p>
          )}
        </div>
      </div>
    </>
  );
};
