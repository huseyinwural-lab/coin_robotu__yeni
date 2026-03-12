import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

export const AdminFuturesMicrostructureGuardPage = () => {
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [status, setStatus] = useState(null);

  const loadStatus = useCallback(async () => {
    setLoading(true);
    setErrorMessage("");
    try {
      const response = await apiClient.get("/admin/futures/microstructure/status");
      setStatus(response.data || null);
    } catch (error) {
      const message = error?.response?.data?.detail || "Microstructure verisi alınamadı";
      setErrorMessage(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  const symbols = useMemo(() => status?.symbols || [], [status]);
  const riskSymbols = useMemo(() => status?.symbols_at_risk || [], [status]);
  const gateRejections = useMemo(() => status?.gate_rejections || [], [status]);

  const spreadSummary = useMemo(() => {
    const summary = { NORMAL: 0, ELEVATED: 0, SHOCK: 0 };
    symbols.forEach((item) => {
      const state = item?.spread?.spread_state || "NORMAL";
      summary[state] = (summary[state] || 0) + 1;
    });
    return summary;
  }, [symbols]);

  const slippageSummary = useMemo(() => {
    const summary = { NORMAL: 0, ELEVATED: 0, ANOMALY: 0 };
    symbols.forEach((item) => {
      const state = item?.slippage?.slippage_state || "NORMAL";
      summary[state] = (summary[state] || 0) + 1;
    });
    return summary;
  }, [symbols]);

  const gateReasonDistribution = useMemo(() => {
    const map = {};
    gateRejections.forEach((item) => {
      const key = item.gate_reason || "UNKNOWN";
      map[key] = (map[key] || 0) + 1;
    });
    return Object.entries(map).map(([reason, count]) => ({ reason, count }));
  }, [gateRejections]);

  return (
    <section className="space-y-4" data-testid="admin-futures-microstructure-guard-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="admin-futures-microstructure-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-black" data-testid="admin-futures-microstructure-title">
          Futures Microstructure Guard
        </h2>
        <p className="mt-2 text-sm text-black/80" data-testid="admin-futures-microstructure-description">
          Spread/depth/quote/slippage suitability kontrol katmanı (read-only).
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3 border border-black/30 bg-orange-100 p-4" data-testid="admin-futures-microstructure-toolbar">
        <Button className="border border-black bg-black text-orange-400 hover:bg-zinc-800" onClick={loadStatus} data-testid="admin-futures-microstructure-refresh-button">
          Yenile
        </Button>
        <p className="text-sm text-black" data-testid="admin-futures-microstructure-loading-text">loading: {String(loading)}</p>
        <p className="text-sm text-black" data-testid="admin-futures-microstructure-updated-at">updated_at: {status?.updated_at ? new Date(status.updated_at).toLocaleString() : "-"}</p>
      </div>

      {loading && <div className="border border-black/25 bg-orange-50 p-4 text-sm" data-testid="admin-futures-microstructure-loading-state">Microstructure verileri yükleniyor...</div>}
      {!loading && errorMessage && <div className="border border-red-700 bg-red-100 p-4 text-sm text-red-900" data-testid="admin-futures-microstructure-error-state">Hata: {errorMessage}</div>}

      {!loading && !errorMessage && (
        <>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4" data-testid="admin-futures-microstructure-summary-grid">
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="microstructure-card-portfolio-state">
              <p className="text-xs uppercase">Portfolio State</p>
              <p className="text-2xl font-bold" data-testid="microstructure-portfolio-state-value">{status?.portfolio_microstructure_state || "SAFE"}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="microstructure-card-risk-score">
              <p className="text-xs uppercase">Risk Score</p>
              <p className="text-2xl font-bold" data-testid="microstructure-risk-score-value">{status?.portfolio_microstructure_risk_score ?? 0}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="microstructure-card-gate-rejections">
              <p className="text-xs uppercase">Gate Rejections</p>
              <p className="text-2xl font-bold" data-testid="microstructure-gate-rejections-value">{gateRejections.length}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="microstructure-card-execution-suitability">
              <p className="text-xs uppercase">Execution Suitability</p>
              <p className="text-2xl font-bold" data-testid="microstructure-execution-suitability-value">{status?.execution_suitability?.severity || "LOW"}</p>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-3" data-testid="microstructure-panel-grid-top">
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="microstructure-spread-shock-panel">
              <h3 className="text-lg font-bold" data-testid="microstructure-spread-shock-title">Spread Shock Panel</h3>
              <p className="text-sm" data-testid="microstructure-spread-normal-count">NORMAL: {spreadSummary.NORMAL || 0}</p>
              <p className="text-sm" data-testid="microstructure-spread-elevated-count">ELEVATED: {spreadSummary.ELEVATED || 0}</p>
              <p className="text-sm" data-testid="microstructure-spread-shock-count">SHOCK: {spreadSummary.SHOCK || 0}</p>
            </div>

            <div className="border border-black/25 bg-orange-100 p-4" data-testid="microstructure-quote-stability-panel">
              <h3 className="text-lg font-bold" data-testid="microstructure-quote-stability-title">Quote Stability Stream</h3>
              <div className="mt-2 space-y-1" data-testid="microstructure-quote-stability-list">
                {symbols.slice(0, 8).map((item, index) => (
                  <p key={`${item.symbol}-${index}`} className="text-xs" data-testid={`microstructure-quote-stability-item-${index}`}>
                    {item.symbol}: {item.quote_stability?.quote_stability_state} · rate={item.quote_stability?.quote_update_rate}
                  </p>
                ))}
                {symbols.length === 0 && <p className="text-xs" data-testid="microstructure-quote-stability-empty">Veri yok.</p>}
              </div>
            </div>

            <div className="border border-black/25 bg-orange-100 p-4" data-testid="microstructure-slippage-anomaly-panel">
              <h3 className="text-lg font-bold" data-testid="microstructure-slippage-anomaly-title">Slippage Anomaly Counters</h3>
              <p className="text-sm" data-testid="microstructure-slippage-normal-count">NORMAL: {slippageSummary.NORMAL || 0}</p>
              <p className="text-sm" data-testid="microstructure-slippage-elevated-count">ELEVATED: {slippageSummary.ELEVATED || 0}</p>
              <p className="text-sm" data-testid="microstructure-slippage-anomaly-count">ANOMALY: {slippageSummary.ANOMALY || 0}</p>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2" data-testid="microstructure-panel-grid-bottom">
            <div className="border border-black/25 bg-orange-100" data-testid="microstructure-depth-thinning-heatmap-wrapper">
              <div className="border-b border-black/20 px-4 py-3" data-testid="microstructure-depth-thinning-header">
                <h3 className="text-lg font-bold" data-testid="microstructure-depth-thinning-title">Depth Thinning Heatmap</h3>
              </div>
              <Table data-testid="microstructure-depth-thinning-table">
                <TableHeader>
                  <TableRow>
                    <TableHead data-testid="microstructure-depth-head-symbol">Symbol</TableHead>
                    <TableHead data-testid="microstructure-depth-head-bid">Bid Change</TableHead>
                    <TableHead data-testid="microstructure-depth-head-ask">Ask Change</TableHead>
                    <TableHead data-testid="microstructure-depth-head-state">State</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {symbols.map((item, index) => (
                    <TableRow key={`${item.symbol}-${index}`} data-testid={`microstructure-depth-row-${index}`}>
                      <TableCell data-testid={`microstructure-depth-symbol-${index}`}>{item.symbol}</TableCell>
                      <TableCell data-testid={`microstructure-depth-bid-${index}`}>{item.thinning?.bid_depth_change}</TableCell>
                      <TableCell data-testid={`microstructure-depth-ask-${index}`}>{item.thinning?.ask_depth_change}</TableCell>
                      <TableCell data-testid={`microstructure-depth-state-${index}`}>{item.thinning?.thinning_state}</TableCell>
                    </TableRow>
                  ))}
                  {symbols.length === 0 && (
                    <TableRow data-testid="microstructure-depth-empty-row">
                      <TableCell colSpan={4} className="text-center text-sm" data-testid="microstructure-depth-empty-text">Veri yok.</TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>

            <div className="space-y-3" data-testid="microstructure-right-column-panels">
              <div className="border border-black/25 bg-orange-100 p-4" data-testid="microstructure-risk-symbols-panel">
                <h3 className="text-lg font-bold" data-testid="microstructure-risk-symbols-title">Microstructure Risk Symbols</h3>
                <div className="mt-2 space-y-1" data-testid="microstructure-risk-symbols-list">
                  {riskSymbols.map((item, index) => (
                    <p key={`${item.symbol}-${index}`} className="text-xs" data-testid={`microstructure-risk-symbol-item-${index}`}>
                      {item.symbol} · {item.risk_level} · {item.dominant_factor}
                    </p>
                  ))}
                  {riskSymbols.length === 0 && <p className="text-xs" data-testid="microstructure-risk-symbols-empty">Riskli sembol yok.</p>}
                </div>
              </div>

              <div className="border border-black/25 bg-orange-100 p-4" data-testid="microstructure-execution-suitability-summary-panel">
                <h3 className="text-lg font-bold" data-testid="microstructure-execution-suitability-summary-title">Execution Suitability Summary</h3>
                <p className="text-sm" data-testid="microstructure-execution-suitable-value">execution_suitable: {String(status?.execution_suitability?.execution_suitable)}</p>
                <p className="text-sm" data-testid="microstructure-execution-severity-value">severity: {status?.execution_suitability?.severity || "LOW"}</p>
                <p className="text-sm" data-testid="microstructure-max-size-ratio-value">max_allowed_size_ratio: {status?.execution_suitability?.max_allowed_size_ratio ?? 1}</p>
                <p className="text-sm" data-testid="microstructure-leverage-override-value">leverage_cap_override: {status?.execution_suitability?.leverage_cap_override ?? 5}</p>
              </div>

              <div className="border border-black/25 bg-orange-100 p-4" data-testid="microstructure-gate-rejection-chart-panel">
                <h3 className="text-lg font-bold" data-testid="microstructure-gate-rejection-chart-title">Gate Rejection Chart</h3>
                <div className="mt-2 space-y-1" data-testid="microstructure-gate-rejection-chart-list">
                  {gateReasonDistribution.map((item, index) => (
                    <p key={`${item.reason}-${index}`} className="text-xs" data-testid={`microstructure-gate-rejection-reason-item-${index}`}>
                      {item.reason}: {item.count}
                    </p>
                  ))}
                  {gateReasonDistribution.length === 0 && <p className="text-xs" data-testid="microstructure-gate-rejection-chart-empty">Gate rejection yok.</p>}
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </section>
  );
};
