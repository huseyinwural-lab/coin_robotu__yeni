import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

const STATE_COLORS = {
  READY: "bg-emerald-200 text-emerald-950 border-emerald-400",
  PASS: "bg-emerald-200 text-emerald-950 border-emerald-400",
  WARNING: "bg-amber-200 text-amber-950 border-amber-400",
  WARN: "bg-amber-200 text-amber-950 border-amber-400",
  BLOCKED: "bg-rose-200 text-rose-950 border-rose-400",
  FAIL: "bg-rose-200 text-rose-950 border-rose-400",
  UNKNOWN: "bg-slate-200 text-slate-900 border-slate-400",
};

const REASON_HINTS = {
  STRATEGY_ENGINE_UNKNOWN: "Strategy engine heartbeat key'ini Redis'e yazdır ve stale eşiğini doğrula.",
  STRATEGY_ENGINE_HEARTBEAT_STALE: "Engine scheduler/worker çalışmasını kontrol et, heartbeat age düşmeli.",
  STRATEGY_ENGINE_ERROR: "strategy:engine:error_state içeriğini temizlemeden live'a çıkma.",
  FUNDING_DATA_MISSING: "Funding adapter + cache key (futures:funding:<symbol>) akışını doğrula.",
  FUNDING_DATA_STALE: "Funding timestamp freshness süresini aşmış; adapter sync job tetikle.",
  LIQUIDATION_DISTANCE_LOW: "Pozisyon leverage/notional azalt veya hedge uygula.",
  EXECUTION_LIFECYCLE_SYNC_FAIL: "Execution DB transition/event pipeline tutarlılığını onar.",
  REDUCE_ONLY_ACCEPTED: "Venue reduce-only guard başarısız; order policy katmanını sertleştir.",
  RISK_ENGINE_POLICY_APPLY_FAIL: "Risk policy sample decision çağrısı başarısız; risk config + service health kontrol et.",
  EXPOSURE_LIMIT_BREACH: "Global/symbol/strategy exposure limitlerini düşür veya pozisyon azalt.",
};

const badgeClass = (state) => `inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${STATE_COLORS[state] || STATE_COLORS.UNKNOWN}`;

const reasonFixHint = (reasonCode) => REASON_HINTS[reasonCode] || "Operasyon runbook'ta ilgili reason code adımını uygula.";

export const AdminFuturesLiveReadinessPage = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [updatedAt, setUpdatedAt] = useState(null);
  const [readinessPayload, setReadinessPayload] = useState(null);
  const [scorePayload, setScorePayload] = useState(null);
  const [historyPayload, setHistoryPayload] = useState(null);
  const [executionPayload, setExecutionPayload] = useState(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [liveRes, scoreRes, historyRes, executionRes] = await Promise.all([
        apiClient.get("/admin/futures/live-readiness", { params: { refresh: true } }),
        apiClient.get("/admin/futures/readiness-score", { params: { refresh: true } }),
        apiClient.get("/admin/futures/readiness/history", { params: { limit: 30, days: 14 } }),
        apiClient.get("/admin/execution-readiness"),
      ]);
      setReadinessPayload(liveRes.data);
      setScorePayload(scoreRes.data);
      setHistoryPayload(historyRes.data);
      setExecutionPayload(executionRes.data);
      setUpdatedAt(new Date().toISOString());
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || requestError?.message || "Readiness verisi alınamadı");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const blockingSummary = useMemo(() => {
    const summary = readinessPayload?.summary || {};
    const total = Number(summary.blocking_total || 0);
    const passed = Number(summary.blocking_passed || 0);
    const progress = total > 0 ? Math.round((passed / total) * 100) : 0;
    return { total, passed, progress };
  }, [readinessPayload]);

  const blockingFailures = readinessPayload?.blocking_failures || [];
  const warnings = readinessPayload?.warnings || [];
  const unknowns = readinessPayload?.unknowns || [];
  const topBlockers = historyPayload?.top_blockers || [];
  const failureTrend = historyPayload?.failure_trend || [];
  const matrix = readinessPayload?.readiness_matrix || {};

  return (
    <section className="space-y-6 px-1" data-testid="admin-futures-live-readiness-page">
      <header
        className="relative overflow-hidden rounded-2xl border border-cyan-900 bg-gradient-to-r from-cyan-950 via-slate-950 to-zinc-900 p-6 text-cyan-50"
        data-testid="live-readiness-header"
      >
        <div className="absolute -top-20 right-0 h-52 w-52 rounded-full bg-cyan-500/20 blur-3xl" data-testid="live-readiness-header-glow" />
        <p className="text-xs uppercase tracking-[0.2em] text-cyan-300" data-testid="live-readiness-kicker">operator control</p>
        <h2 className="mt-2 text-4xl font-black uppercase tracking-tight" data-testid="live-readiness-title">Futures Live Readiness Matrix</h2>
        <p className="mt-3 max-w-3xl text-sm text-cyan-100/80" data-testid="live-readiness-description">
          Tek kaynak validator çıktısıyla fail nedenlerini, düzeltme adımlarını ve trend analizini operasyona hazır şekilde gösterir.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-cyan-900 bg-slate-950/80 p-4" data-testid="live-readiness-toolbar">
        <Button
          className="border border-cyan-500 bg-cyan-400 text-cyan-950 hover:bg-cyan-300"
          onClick={loadData}
          data-testid="live-readiness-refresh-button"
        >
          Refresh Readiness
        </Button>
        <p className="text-xs text-cyan-200" data-testid="live-readiness-loading-text">loading: {String(loading)}</p>
        <p className="text-xs text-cyan-200" data-testid="live-readiness-updated-at-text">updated: {updatedAt || "-"}</p>
      </div>

      {loading && (
        <div className="rounded-xl border border-cyan-700 bg-cyan-950/30 p-4 text-sm text-cyan-100" data-testid="live-readiness-loading-state">
          Live readiness yükleniyor...
        </div>
      )}

      {!!error && (
        <div className="rounded-xl border border-rose-700 bg-rose-950/40 p-4 text-sm text-rose-200" data-testid="live-readiness-error-state">
          {error}
        </div>
      )}

      {!loading && !error && readinessPayload && (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4" data-testid="live-readiness-summary-grid">
            <article className="rounded-xl border border-cyan-900 bg-slate-950 p-4" data-testid="live-readiness-state-card">
              <p className="text-xs uppercase tracking-widest text-cyan-300" data-testid="live-readiness-state-label">Global State</p>
              <p className={`mt-2 ${badgeClass(readinessPayload.readiness_state)}`} data-testid="live-readiness-state-value">{readinessPayload.readiness_state}</p>
            </article>
            <article className="rounded-xl border border-cyan-900 bg-slate-950 p-4" data-testid="live-readiness-score-card">
              <p className="text-xs uppercase tracking-widest text-cyan-300" data-testid="live-readiness-score-label">Readiness Score</p>
              <p className="mt-2 text-2xl font-bold text-cyan-100" data-testid="live-readiness-score-value">{Number(scorePayload?.readiness_score || readinessPayload?.readiness_score || 0).toFixed(2)}</p>
            </article>
            <article className="rounded-xl border border-cyan-900 bg-slate-950 p-4" data-testid="live-readiness-go-live-card">
              <p className="text-xs uppercase tracking-widest text-cyan-300" data-testid="live-readiness-go-live-label">Go-Live Allowed</p>
              <p className={`mt-2 ${badgeClass(readinessPayload.go_live_allowed ? "READY" : "BLOCKED")}`} data-testid="live-readiness-go-live-value">{String(readinessPayload.go_live_allowed)}</p>
            </article>
            <article className="rounded-xl border border-cyan-900 bg-slate-950 p-4" data-testid="live-readiness-execution-card">
              <p className="text-xs uppercase tracking-widest text-cyan-300" data-testid="live-readiness-execution-label">Execution Allowed</p>
              <p className={`mt-2 ${badgeClass(readinessPayload.execution_allowed ? "READY" : "BLOCKED")}`} data-testid="live-readiness-execution-value">{String(readinessPayload.execution_allowed)}</p>
            </article>
          </div>

          <section className="rounded-xl border border-cyan-900 bg-slate-950 p-4" data-testid="live-readiness-progress-section">
            <div className="flex items-center justify-between" data-testid="live-readiness-progress-header">
              <h3 className="text-sm font-semibold text-cyan-100" data-testid="live-readiness-progress-title">Blocking Coverage Progress</h3>
              <p className="text-xs text-cyan-300" data-testid="live-readiness-progress-meta">{blockingSummary.passed}/{blockingSummary.total} PASS</p>
            </div>
            <div className="mt-3 h-3 w-full overflow-hidden rounded-full bg-cyan-950" data-testid="live-readiness-progress-track">
              <div
                className="h-full rounded-full bg-gradient-to-r from-cyan-400 via-teal-300 to-emerald-300 transition-[width] duration-500"
                style={{ width: `${blockingSummary.progress}%` }}
                data-testid="live-readiness-progress-bar"
              />
            </div>
            <p className="mt-2 text-xs text-cyan-300" data-testid="live-readiness-progress-percent">{blockingSummary.progress}%</p>
          </section>

          <div className="grid gap-4 xl:grid-cols-2" data-testid="live-readiness-main-grid">
            <section className="rounded-xl border border-cyan-900 bg-slate-950 p-4" data-testid="live-readiness-layer-panel">
              <h3 className="text-sm font-semibold text-cyan-100" data-testid="live-readiness-layer-title">Layer Breakdown</h3>
              <div className="mt-3 space-y-2" data-testid="live-readiness-layer-list">
                {Object.entries(readinessPayload.scores || {}).map(([layer, value]) => {
                  const layerSteps = (readinessPayload.by_layer || {})[layer] || [];
                  const layerState = layerSteps.some((step) => step.status === "FAIL")
                    ? "BLOCKED"
                    : layerSteps.some((step) => step.status === "UNKNOWN")
                      ? "UNKNOWN"
                      : layerSteps.some((step) => step.status === "WARN")
                        ? "WARNING"
                        : "READY";
                  return (
                    <article className="flex items-center justify-between rounded-lg border border-cyan-900/60 bg-slate-900 p-2" key={layer} data-testid={`live-readiness-layer-item-${layer}`}>
                      <p className="text-xs uppercase tracking-wide text-cyan-200" data-testid={`live-readiness-layer-name-${layer}`}>{layer}</p>
                      <div className="flex items-center gap-2" data-testid={`live-readiness-layer-metrics-${layer}`}>
                        <span className={badgeClass(layerState)} data-testid={`live-readiness-layer-state-${layer}`}>{layerState}</span>
                        <span className="text-xs font-semibold text-cyan-200" data-testid={`live-readiness-layer-score-${layer}`}>{Number(value || 0).toFixed(1)}</span>
                      </div>
                    </article>
                  );
                })}
              </div>
            </section>

            <section className="rounded-xl border border-cyan-900 bg-slate-950 p-4" data-testid="live-readiness-blocker-panel">
              <h3 className="text-sm font-semibold text-cyan-100" data-testid="live-readiness-blocker-title">Critical Blockers & Fix</h3>
              <div className="mt-3 space-y-2" data-testid="live-readiness-blocker-list">
                {blockingFailures.map((item, index) => (
                  <article className="rounded-lg border border-rose-700/40 bg-rose-950/20 p-3" key={`${item.reason_code}-${index}`} data-testid={`live-readiness-blocker-item-${index}`}>
                    <div className="flex flex-wrap items-center gap-2" data-testid={`live-readiness-blocker-header-${index}`}>
                      <span className={badgeClass(item.status)} data-testid={`live-readiness-blocker-status-${index}`}>{item.status}</span>
                      <span className="text-xs font-semibold text-rose-200" data-testid={`live-readiness-blocker-reason-${index}`}>{item.reason_code}</span>
                    </div>
                    <p className="mt-2 text-xs text-rose-100" data-testid={`live-readiness-blocker-fix-${index}`}>{reasonFixHint(item.reason_code)}</p>
                  </article>
                ))}
                {blockingFailures.length === 0 && <p className="text-xs text-cyan-300" data-testid="live-readiness-blocker-empty">Kritik blocker yok.</p>}
              </div>
            </section>
          </div>

          <div className="grid gap-4 xl:grid-cols-3" data-testid="live-readiness-matrix-grid">
            <section className="rounded-xl border border-cyan-900 bg-slate-950 p-4" data-testid="live-readiness-exchange-matrix-panel">
              <h3 className="text-sm font-semibold text-cyan-100" data-testid="live-readiness-exchange-matrix-title">Exchange Matrix</h3>
              <div className="mt-3 space-y-2" data-testid="live-readiness-exchange-matrix-list">
                {Object.entries(matrix.exchange || {}).map(([exchange, value]) => (
                  <article className="rounded-lg border border-cyan-900/60 bg-slate-900 p-2" key={exchange} data-testid={`live-readiness-exchange-item-${exchange}`}>
                    <div className="flex items-center justify-between" data-testid={`live-readiness-exchange-header-${exchange}`}>
                      <p className="text-xs uppercase tracking-wide text-cyan-200" data-testid={`live-readiness-exchange-name-${exchange}`}>{exchange}</p>
                      <span className={badgeClass(value?.state || "UNKNOWN")} data-testid={`live-readiness-exchange-state-${exchange}`}>{value?.state || "UNKNOWN"}</span>
                    </div>
                    <p className="mt-1 text-xs text-cyan-300" data-testid={`live-readiness-exchange-latency-${exchange}`}>latency_ms: {value?.latency_ms ?? "-"}</p>
                  </article>
                ))}
              </div>
            </section>

            <section className="rounded-xl border border-cyan-900 bg-slate-950 p-4" data-testid="live-readiness-symbol-matrix-panel">
              <h3 className="text-sm font-semibold text-cyan-100" data-testid="live-readiness-symbol-matrix-title">Symbol Matrix</h3>
              <div className="mt-3 space-y-2" data-testid="live-readiness-symbol-matrix-list">
                {Object.entries(matrix.symbol || {}).map(([symbol, state]) => (
                  <article className="flex items-center justify-between rounded-lg border border-cyan-900/60 bg-slate-900 p-2" key={symbol} data-testid={`live-readiness-symbol-item-${symbol}`}>
                    <p className="text-xs font-semibold text-cyan-200" data-testid={`live-readiness-symbol-name-${symbol}`}>{symbol}</p>
                    <span className={badgeClass(state)} data-testid={`live-readiness-symbol-state-${symbol}`}>{state}</span>
                  </article>
                ))}
                {Object.keys(matrix.symbol || {}).length === 0 && <p className="text-xs text-cyan-300" data-testid="live-readiness-symbol-empty">Symbol readiness verisi yok.</p>}
              </div>
            </section>

            <section className="rounded-xl border border-cyan-900 bg-slate-950 p-4" data-testid="live-readiness-strategy-matrix-panel">
              <h3 className="text-sm font-semibold text-cyan-100" data-testid="live-readiness-strategy-matrix-title">Strategy Matrix</h3>
              <div className="mt-3 space-y-2" data-testid="live-readiness-strategy-matrix-list">
                {Object.entries(matrix.strategy || {}).map(([strategy, state]) => (
                  <article className="flex items-center justify-between rounded-lg border border-cyan-900/60 bg-slate-900 p-2" key={strategy} data-testid={`live-readiness-strategy-item-${strategy}`}>
                    <p className="text-xs font-semibold text-cyan-200" data-testid={`live-readiness-strategy-name-${strategy}`}>{strategy}</p>
                    <span className={badgeClass(state)} data-testid={`live-readiness-strategy-state-${strategy}`}>{state}</span>
                  </article>
                ))}
                {Object.keys(matrix.strategy || {}).length === 0 && <p className="text-xs text-cyan-300" data-testid="live-readiness-strategy-empty">Strategy readiness verisi yok.</p>}
              </div>
            </section>
          </div>

          <div className="grid gap-4 xl:grid-cols-2" data-testid="live-readiness-analytics-grid">
            <section className="rounded-xl border border-cyan-900 bg-slate-950 p-4" data-testid="live-readiness-top-blockers-panel">
              <h3 className="text-sm font-semibold text-cyan-100" data-testid="live-readiness-top-blockers-title">Top Blockers</h3>
              <div className="mt-3 space-y-2" data-testid="live-readiness-top-blockers-list">
                {topBlockers.map((item, index) => (
                  <div className="flex items-center justify-between rounded-md border border-cyan-900/60 bg-slate-900 p-2" key={`${item.reason_code}-${index}`} data-testid={`live-readiness-top-blocker-item-${index}`}>
                    <p className="text-xs text-cyan-200" data-testid={`live-readiness-top-blocker-reason-${index}`}>{item.reason_code}</p>
                    <p className="text-xs font-semibold text-cyan-100" data-testid={`live-readiness-top-blocker-count-${index}`}>{item.count}</p>
                  </div>
                ))}
                {topBlockers.length === 0 && <p className="text-xs text-cyan-300" data-testid="live-readiness-top-blockers-empty">Blocker trend verisi yok.</p>}
              </div>
            </section>

            <section className="rounded-xl border border-cyan-900 bg-slate-950 p-4" data-testid="live-readiness-failure-trend-panel">
              <h3 className="text-sm font-semibold text-cyan-100" data-testid="live-readiness-failure-trend-title">Failure Trend (14 gün)</h3>
              <div className="mt-3 space-y-2" data-testid="live-readiness-failure-trend-list">
                {failureTrend.slice(-7).map((row, index) => (
                  <article className="rounded-md border border-cyan-900/60 bg-slate-900 p-2" key={`${row.date}-${index}`} data-testid={`live-readiness-failure-trend-item-${index}`}>
                    <p className="text-xs text-cyan-200" data-testid={`live-readiness-failure-trend-date-${index}`}>{row.date}</p>
                    <div className="mt-1 flex flex-wrap gap-2 text-xs" data-testid={`live-readiness-failure-trend-states-${index}`}>
                      <span className="text-emerald-300" data-testid={`live-readiness-failure-trend-ready-${index}`}>READY: {row.ready}</span>
                      <span className="text-rose-300" data-testid={`live-readiness-failure-trend-blocked-${index}`}>BLOCKED: {row.blocked}</span>
                      <span className="text-amber-300" data-testid={`live-readiness-failure-trend-warning-${index}`}>WARNING: {row.warning}</span>
                      <span className="text-slate-300" data-testid={`live-readiness-failure-trend-unknown-${index}`}>UNKNOWN: {row.unknown}</span>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          </div>

          <section className="rounded-xl border border-cyan-900 bg-slate-950 p-4" data-testid="live-readiness-step-breakdown-panel">
            <h3 className="text-sm font-semibold text-cyan-100" data-testid="live-readiness-step-breakdown-title">Step Breakdown</h3>
            <div className="mt-3 max-h-[420px] overflow-auto" data-testid="live-readiness-step-breakdown-table-wrap">
              <table className="w-full border-collapse text-left text-xs" data-testid="live-readiness-step-breakdown-table">
                <thead data-testid="live-readiness-step-breakdown-head">
                  <tr>
                    <th className="border-b border-cyan-900 p-2 text-cyan-300" data-testid="live-readiness-step-col-layer">layer</th>
                    <th className="border-b border-cyan-900 p-2 text-cyan-300" data-testid="live-readiness-step-col-key">step</th>
                    <th className="border-b border-cyan-900 p-2 text-cyan-300" data-testid="live-readiness-step-col-status">status</th>
                    <th className="border-b border-cyan-900 p-2 text-cyan-300" data-testid="live-readiness-step-col-reason">reason</th>
                    <th className="border-b border-cyan-900 p-2 text-cyan-300" data-testid="live-readiness-step-col-duration">duration</th>
                  </tr>
                </thead>
                <tbody data-testid="live-readiness-step-breakdown-body">
                  {(readinessPayload.steps || []).map((step, index) => (
                    <tr key={`${step.step_key}-${index}`} data-testid={`live-readiness-step-row-${index}`}>
                      <td className="border-b border-cyan-950 p-2 text-cyan-200" data-testid={`live-readiness-step-layer-${index}`}>{step.layer}</td>
                      <td className="border-b border-cyan-950 p-2 text-cyan-100" data-testid={`live-readiness-step-key-${index}`}>{step.step_key}</td>
                      <td className="border-b border-cyan-950 p-2" data-testid={`live-readiness-step-status-${index}`}><span className={badgeClass(step.status)}>{step.status}</span></td>
                      <td className="border-b border-cyan-950 p-2 text-cyan-200" data-testid={`live-readiness-step-reason-${index}`}>{step.reason_code}</td>
                      <td className="border-b border-cyan-950 p-2 text-cyan-300" data-testid={`live-readiness-step-duration-${index}`}>{step.duration_ms}ms</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-xl border border-cyan-900 bg-slate-950 p-4" data-testid="live-readiness-execution-readiness-panel">
            <h3 className="text-sm font-semibold text-cyan-100" data-testid="live-readiness-execution-readiness-title">Execution Readiness Contract</h3>
            <div className="mt-2 flex flex-wrap gap-3 text-xs" data-testid="live-readiness-execution-readiness-content">
              <span data-testid="live-readiness-execution-final-status">final_status: {executionPayload?.final_status || "-"}</span>
              <span data-testid="live-readiness-execution-mode">mode: {executionPayload?.mode || "-"}</span>
              <span data-testid="live-readiness-execution-reason-codes">reason_codes: {(executionPayload?.reason_codes || []).join(", ") || "-"}</span>
            </div>
          </section>

          <section className="rounded-xl border border-cyan-900 bg-slate-950 p-4" data-testid="live-readiness-status-count-panel">
            <h3 className="text-sm font-semibold text-cyan-100" data-testid="live-readiness-status-count-title">Warning / Unknown Counters</h3>
            <div className="mt-2 flex flex-wrap gap-3 text-xs" data-testid="live-readiness-status-count-content">
              <span data-testid="live-readiness-warning-count">warnings: {warnings.length}</span>
              <span data-testid="live-readiness-unknown-count">unknowns: {unknowns.length}</span>
            </div>
          </section>
        </>
      )}
    </section>
  );
};
