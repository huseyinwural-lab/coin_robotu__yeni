import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

export const AdminFuturesLiveControlPage = () => {
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [status, setStatus] = useState(null);
  const [gate, setGate] = useState(null);
  const [executionQuality, setExecutionQuality] = useState(null);
  const [rolling7d, setRolling7d] = useState(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setErrorMessage("");
    try {
      const [statusResponse, gateResponse, qualityResponse, rollingResponse] = await Promise.all([
        apiClient.get("/admin/futures/live/status"),
        apiClient.get("/admin/futures/live/release-gate"),
        apiClient.get("/admin/futures/live/execution-quality"),
        apiClient.get("/admin/futures/live/execution-quality/rolling-7d"),
      ]);
      setStatus(statusResponse.data || null);
      setGate(gateResponse.data || null);
      setExecutionQuality(qualityResponse.data || null);
      setRolling7d(rollingResponse.data || null);
    } catch (error) {
      const message = error?.response?.data?.detail || "Live kontrol verisi alınamadı";
      setErrorMessage(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const retryMatrix = useMemo(() => status?.retry_policy || [], [status]);
  const preflightChecks = useMemo(() => status?.preflight_template?.checks || [], [status]);
  const gateReasonTrend = useMemo(() => executionQuality?.gate_reason_trend_7d || [], [executionQuality]);
  const driftAlerts = useMemo(() => executionQuality?.symbol_drift_alerts || [], [executionQuality]);
  const falseCompare = useMemo(() => executionQuality?.false_allow_reject_comparison_by_layer || [], [executionQuality]);
  const checklist15 = useMemo(() => {
    const qualityList = executionQuality?.architecture_checklist_15 || [];
    if (qualityList.length > 0) {
      return qualityList;
    }
    return status?.architecture_checklist_15 || [];
  }, [executionQuality, status]);

  return (
    <section className="space-y-4" data-testid="admin-futures-live-control-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="admin-futures-live-control-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-black" data-testid="admin-futures-live-control-title">
          Futures Live Control
        </h2>
        <p className="mt-2 text-sm text-black/80" data-testid="admin-futures-live-control-description">
          Live release gate ve execution safety görünürlüğü (read-only).
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3 border border-black/30 bg-orange-100 p-4" data-testid="admin-futures-live-control-toolbar">
        <Button className="border border-black bg-black text-orange-400 hover:bg-zinc-800" onClick={loadData} data-testid="admin-futures-live-control-refresh-button">
          Yenile
        </Button>
        <p className="text-sm text-black" data-testid="admin-futures-live-control-loading-text">loading: {String(loading)}</p>
      </div>

      {loading && <div className="border border-black/25 bg-orange-50 p-4 text-sm" data-testid="admin-futures-live-control-loading-state">Live verileri yükleniyor...</div>}
      {!loading && errorMessage && <div className="border border-red-700 bg-red-100 p-4 text-sm text-red-900" data-testid="admin-futures-live-control-error-state">Hata: {errorMessage}</div>}

      {!loading && !errorMessage && (
        <>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4" data-testid="live-control-summary-grid">
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="live-enabled-card">
              <p className="text-xs uppercase">Live Enabled</p>
              <p className="text-xl font-bold" data-testid="live-enabled-value">{String(status?.live_enabled ?? false)}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="live-default-mode-card">
              <p className="text-xs uppercase">Default Mode</p>
              <p className="text-xl font-bold" data-testid="live-default-mode-value">{status?.default_mode || "paper"}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="live-release-gate-status-card">
              <p className="text-xs uppercase">Release Gate</p>
              <p className="text-xl font-bold" data-testid="live-release-gate-status-value">{gate?.status || "BLOCKED"}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="live-order-path-open-card">
              <p className="text-xs uppercase">Order Path Open</p>
              <p className="text-xl font-bold" data-testid="live-order-path-open-value">{String(gate?.order_path_open ?? false)}</p>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2" data-testid="live-control-middle-grid">
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="live-release-gate-reasons-panel">
              <h3 className="text-lg font-bold" data-testid="live-release-gate-reasons-title">Release Gate Reasons</h3>
              <div className="mt-2 space-y-1" data-testid="live-release-gate-reasons-list">
                {(gate?.reasons || []).map((reason, index) => (
                  <p key={`${reason}-${index}`} className="text-xs" data-testid={`live-release-gate-reason-item-${index}`}>{reason}</p>
                ))}
                {(gate?.reasons || []).length === 0 && <p className="text-xs" data-testid="live-release-gate-reasons-empty">Reason yok.</p>}
              </div>
            </div>

            <div className="border border-black/25 bg-orange-100 p-4" data-testid="live-config-isolation-panel">
              <h3 className="text-lg font-bold" data-testid="live-config-isolation-title">Config/Secret Isolation</h3>
              <p className="text-sm" data-testid="live-live-endpoint-access-value">live_endpoint_access: {String(status?.live_endpoint_access ?? false)}</p>
              <p className="text-sm" data-testid="live-secret-isolation-pass-value">isolation_pass: {String(status?.secret_isolation?.live_live_secret_isolation_pass ?? false)}</p>
              <p className="text-sm" data-testid="live-secret-isolation-reason-value">reason: {status?.secret_isolation?.reason_code || "PASS"}</p>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2" data-testid="live-control-bottom-grid">
            <div className="border border-black/25 bg-orange-100" data-testid="live-preflight-checks-table-wrapper">
              <div className="border-b border-black/20 px-4 py-3" data-testid="live-preflight-checks-header">
                <h3 className="text-lg font-bold" data-testid="live-preflight-checks-title">Preflight Checks</h3>
              </div>
              <Table data-testid="live-preflight-checks-table">
                <TableHeader>
                  <TableRow>
                    <TableHead data-testid="live-preflight-head-key">Check</TableHead>
                    <TableHead data-testid="live-preflight-head-pass">Pass</TableHead>
                    <TableHead data-testid="live-preflight-head-reason">Reason</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {preflightChecks.map((item, index) => (
                    <TableRow key={`${item.key}-${index}`} data-testid={`live-preflight-row-${index}`}>
                      <TableCell data-testid={`live-preflight-key-${index}`}>{item.key}</TableCell>
                      <TableCell data-testid={`live-preflight-pass-${index}`}>{String(item.pass)}</TableCell>
                      <TableCell data-testid={`live-preflight-reason-${index}`}>{item.reason}</TableCell>
                    </TableRow>
                  ))}
                  {preflightChecks.length === 0 && (
                    <TableRow data-testid="live-preflight-empty-row">
                      <TableCell colSpan={3} className="text-center text-sm" data-testid="live-preflight-empty-text">Preflight verisi yok.</TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>

            <div className="border border-black/25 bg-orange-100" data-testid="live-retry-policy-table-wrapper">
              <div className="border-b border-black/20 px-4 py-3" data-testid="live-retry-policy-header">
                <h3 className="text-lg font-bold" data-testid="live-retry-policy-title">Retry Policy (Reason-aware)</h3>
              </div>
              <Table data-testid="live-retry-policy-table">
                <TableHeader>
                  <TableRow>
                    <TableHead data-testid="live-retry-head-error">Error</TableHead>
                    <TableHead data-testid="live-retry-head-action">Action</TableHead>
                    <TableHead data-testid="live-retry-head-retry">Retry</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {retryMatrix.map((item, index) => (
                    <TableRow key={`${item.error_code}-${index}`} data-testid={`live-retry-row-${index}`}>
                      <TableCell data-testid={`live-retry-error-${index}`}>{item.error_code}</TableCell>
                      <TableCell data-testid={`live-retry-action-${index}`}>{item.decision?.action}</TableCell>
                      <TableCell data-testid={`live-retry-should-retry-${index}`}>{String(item.decision?.should_retry)}</TableCell>
                    </TableRow>
                  ))}
                  {retryMatrix.length === 0 && (
                    <TableRow data-testid="live-retry-empty-row">
                      <TableCell colSpan={3} className="text-center text-sm" data-testid="live-retry-empty-text">Retry policy verisi yok.</TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-3" data-testid="live-analytics-grid">
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="live-slippage-panel">
              <h3 className="text-lg font-bold" data-testid="live-slippage-title">Realized Slippage</h3>
              <p className="text-sm" data-testid="live-slippage-expected-value">expected: {status?.slippage?.expected_slippage ?? 0}</p>
              <p className="text-sm" data-testid="live-slippage-realized-value">realized: {status?.slippage?.realized_slippage ?? 0}</p>
              <p className="text-sm" data-testid="live-slippage-delta-value">delta: {status?.slippage?.delta ?? 0}</p>
            </div>

            <div className="border border-black/25 bg-orange-100 p-4" data-testid="live-reconciler-panel">
              <h3 className="text-lg font-bold" data-testid="live-reconciler-title">Execution Reconciler</h3>
              <p className="text-sm" data-testid="live-reconciler-state-value">state: {status?.reconciler_state || "unknown_needs_reconcile"}</p>
            </div>

            <div className="border border-black/25 bg-orange-100 p-4" data-testid="live-parity-panel">
              <h3 className="text-lg font-bold" data-testid="live-parity-title">Paper/Live Parity</h3>
              <p className="text-sm" data-testid="live-parity-drift-value">drift_bps: {status?.parity_check?.drift_bps ?? 0}</p>
              <p className="text-sm" data-testid="live-parity-status-value">status: {status?.parity_check?.status || "PASS"}</p>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4" data-testid="live-execution-quality-summary-grid">
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="execution-quality-reject-rate-card">
              <p className="text-xs uppercase">Reject Rate</p>
              <p className="text-xl font-bold" data-testid="execution-quality-reject-rate-value">{executionQuality?.reject_rate ?? 0}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="execution-quality-latency-card">
              <p className="text-xs uppercase">Fill Latency (ms)</p>
              <p className="text-xl font-bold" data-testid="execution-quality-latency-value">{executionQuality?.fill_latency_ms ?? 0}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="execution-quality-partial-fill-card">
              <p className="text-xs uppercase">Partial Fill Rate</p>
              <p className="text-xl font-bold" data-testid="execution-quality-partial-fill-value">{executionQuality?.partial_fill_quality?.partial_fill_rate ?? 0}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="execution-quality-rolling-score-card">
              <p className="text-xs uppercase">Rolling 7d Tuning Score</p>
              <p className="text-xl font-bold" data-testid="execution-quality-rolling-score-value">{executionQuality?.rolling_7d_tuning_score?.score ?? rolling7d?.latest_score ?? 0}</p>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2" data-testid="execution-quality-trend-grid">
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="execution-gate-reason-trend-panel">
              <h3 className="text-lg font-bold" data-testid="execution-gate-reason-trend-title">Gate Reason Trend (7d)</h3>
              <div className="mt-2 space-y-1" data-testid="execution-gate-reason-trend-list">
                {gateReasonTrend.map((item, index) => (
                  <p key={`${item.date}-${index}`} className="text-xs" data-testid={`execution-gate-reason-trend-item-${index}`}>
                    {item.date}: {JSON.stringify(item.reasons || {})}
                  </p>
                ))}
                {gateReasonTrend.length === 0 && <p className="text-xs" data-testid="execution-gate-reason-trend-empty">Trend verisi yok.</p>}
              </div>
            </div>

            <div className="border border-black/25 bg-orange-100 p-4" data-testid="execution-symbol-drift-alert-panel">
              <h3 className="text-lg font-bold" data-testid="execution-symbol-drift-alert-title">Symbol Drift Alarmı</h3>
              <div className="mt-2 space-y-1" data-testid="execution-symbol-drift-alert-list">
                {driftAlerts.map((item, index) => (
                  <p key={`${item.symbol}-${index}`} className="text-xs" data-testid={`execution-symbol-drift-alert-item-${index}`}>
                    {item.symbol}: drift={item.avg_drift_bps}bps ({item.severity})
                  </p>
                ))}
                {driftAlerts.length === 0 && <p className="text-xs" data-testid="execution-symbol-drift-alert-empty">Drift alarmı yok.</p>}
              </div>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2" data-testid="execution-diagnostics-comparison-grid">
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="execution-false-compare-panel">
              <h3 className="text-lg font-bold" data-testid="execution-false-compare-title">False Allow / False Reject Karşılaştırma</h3>
              <div className="mt-2 space-y-1" data-testid="execution-false-compare-list">
                {falseCompare.map((item, index) => (
                  <p key={`${item.layer}-${index}`} className="text-xs" data-testid={`execution-false-compare-item-${index}`}>
                    {item.layer}: {item.count ?? `${item.false_allow}/${item.false_reject}`}
                  </p>
                ))}
                {falseCompare.length === 0 && <p className="text-xs" data-testid="execution-false-compare-empty">Karşılaştırma verisi yok.</p>}
              </div>
            </div>

            <div className="border border-black/25 bg-orange-100 p-4" data-testid="execution-architecture-checklist-panel">
              <h3 className="text-lg font-bold" data-testid="execution-architecture-checklist-title">Futures’ta En Sık 15 Mimari Hata — Checklist</h3>
              <div className="mt-2 space-y-1" data-testid="execution-architecture-checklist-list">
                {checklist15.map((item, index) => (
                  <p key={`${item.check}-${index}`} className="text-xs" data-testid={`execution-architecture-check-item-${index}`}>
                    {item.id}. {item.check}: {String(item.pass)}
                  </p>
                ))}
                {checklist15.length === 0 && <p className="text-xs" data-testid="execution-architecture-checklist-empty">Checklist verisi yok.</p>}
              </div>
            </div>
          </div>
        </>
      )}
    </section>
  );
};
