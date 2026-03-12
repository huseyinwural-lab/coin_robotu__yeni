import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const AdminFuturesClusterRiskPage = () => {
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [matrixPayload, setMatrixPayload] = useState(null);
  const [clustersPayload, setClustersPayload] = useState(null);
  const [riskPayload, setRiskPayload] = useState(null);
  const [globalRisk, setGlobalRisk] = useState(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setErrorMessage("");
    try {
      const [matrixResponse, clustersResponse, riskResponse, globalRiskResponse] = await Promise.all([
        apiClient.get("/admin/futures/correlation-matrix"),
        apiClient.get("/admin/futures/correlation-clusters"),
        apiClient.get("/admin/futures/cluster-risk"),
        apiClient.get("/admin/futures/global-risk"),
      ]);
      setMatrixPayload(matrixResponse.data || null);
      setClustersPayload(clustersResponse.data || null);
      setRiskPayload(riskResponse.data || null);
      setGlobalRisk(globalRiskResponse.data || null);
    } catch (error) {
      const message = error?.response?.data?.detail || "Cluster risk verisi alınamadı";
      setErrorMessage(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const symbols = useMemo(() => matrixPayload?.symbols || [], [matrixPayload]);
  const clusters = useMemo(() => clustersPayload?.correlation_clusters || [], [clustersPayload]);
  const exposures = useMemo(() => riskPayload?.cluster_exposures || [], [riskPayload]);
  const alerts = useMemo(() => riskPayload?.cluster_risk_alerts || [], [riskPayload]);

  return (
    <section className="space-y-4" data-testid="admin-futures-cluster-risk-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="cluster-risk-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-black" data-testid="cluster-risk-title">
          Futures Cluster Risk
        </h2>
        <p className="mt-2 text-sm text-black/80" data-testid="cluster-risk-description">
          Correlation matrix, cluster exposure ve risk governance görünürlüğü.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3 border border-black/30 bg-orange-100 p-4" data-testid="cluster-risk-toolbar">
        <Button className="border border-black bg-black text-orange-400 hover:bg-zinc-800" onClick={loadData} data-testid="cluster-risk-refresh-button">
          Yenile
        </Button>
        <p className="text-sm text-black" data-testid="cluster-risk-loading-text">loading: {String(loading)}</p>
        <p className="text-sm text-black" data-testid="cluster-risk-updated-at-text">
          updated_at: {riskPayload?.generated_at ? new Date(riskPayload.generated_at).toLocaleString() : "-"}
        </p>
      </div>

      {loading && <div className="border border-black/25 bg-orange-50 p-4 text-sm" data-testid="cluster-risk-loading-state">Cluster risk yükleniyor...</div>}
      {!loading && Boolean(errorMessage) && (
        <div className="border border-red-700 bg-red-100 p-4 text-sm text-red-900" data-testid="cluster-risk-error-state">
          Hata: {errorMessage}
        </div>
      )}

      {!loading && !errorMessage && (
        <>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-5" data-testid="cluster-risk-summary-grid">
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="cluster-risk-summary-symbol-card">
              <p className="text-xs uppercase">Symbols</p>
              <p className="text-xl font-bold" data-testid="cluster-risk-summary-symbol-value">{symbols.length}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="cluster-risk-summary-cluster-card">
              <p className="text-xs uppercase">Clusters</p>
              <p className="text-xl font-bold" data-testid="cluster-risk-summary-cluster-value">{clusters.length}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="cluster-risk-summary-alert-card">
              <p className="text-xs uppercase">Risk Alerts</p>
              <p className="text-xl font-bold" data-testid="cluster-risk-summary-alert-value">{alerts.length}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="cluster-risk-summary-state-card">
              <p className="text-xs uppercase">Risk State</p>
              <p className="text-xl font-bold" data-testid="cluster-risk-summary-state-value">{riskPayload?.risk_state || "NORMAL"}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="cluster-risk-summary-global-card">
              <p className="text-xs uppercase">Global Risk</p>
              <p className="text-xl font-bold" data-testid="cluster-risk-summary-global-value">
                {globalRisk?.global_risk_score ?? 0} ({globalRisk?.risk_state || "NORMAL"})
              </p>
            </div>
          </div>

          <div className="overflow-auto border border-black/25 bg-orange-100 p-4" data-testid="cluster-risk-heatmap-panel">
            <h3 className="mb-3 text-lg font-bold" data-testid="cluster-risk-heatmap-title">Correlation Heatmap</h3>
            <table className="min-w-full border-collapse text-xs" data-testid="cluster-risk-heatmap-table">
              <thead>
                <tr>
                  <th className="border border-black/30 px-2 py-1" data-testid="cluster-risk-heatmap-head-symbol">Symbol</th>
                  {symbols.map((symbol, index) => (
                    <th className="border border-black/30 px-2 py-1" key={symbol} data-testid={`cluster-risk-heatmap-head-${index}`}>
                      {symbol}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {symbols.map((base, baseIndex) => (
                  <tr key={base} data-testid={`cluster-risk-heatmap-row-${baseIndex}`}>
                    <td className="border border-black/30 px-2 py-1 font-semibold" data-testid={`cluster-risk-heatmap-label-${baseIndex}`}>{base}</td>
                    {symbols.map((compare, compareIndex) => {
                      const value = matrixPayload?.correlation_matrix?.[base]?.[compare] ?? 0;
                      const highlight = Math.abs(value) >= 0.75 ? "bg-orange-300" : "bg-white";
                      return (
                        <td
                          className={`border border-black/30 px-2 py-1 font-mono ${highlight}`}
                          key={`${base}-${compare}`}
                          data-testid={`cluster-risk-heatmap-cell-${baseIndex}-${compareIndex}`}
                        >
                          {value}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="grid gap-3 lg:grid-cols-2" data-testid="cluster-risk-exposure-grid">
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="cluster-risk-exposure-bars-panel">
              <h3 className="text-lg font-bold" data-testid="cluster-risk-exposure-bars-title">Cluster Exposure Bars</h3>
              <div className="mt-3 space-y-2" data-testid="cluster-risk-exposure-bars-list">
                {exposures.map((row, index) => {
                  const width = Math.max(6, Math.min(100, Number(row?.cluster_exposure || 0) * 100));
                  return (
                    <div className="space-y-1" key={`${row?.cluster_id}-${index}`} data-testid={`cluster-risk-exposure-row-${index}`}>
                      <p className="text-xs" data-testid={`cluster-risk-exposure-label-${index}`}>
                        {row?.cluster_id}: exposure={row?.cluster_exposure} · direction={row?.cluster_direction} · positions={row?.cluster_position_count}
                      </p>
                      <div className="h-3 w-full border border-black/40 bg-white" data-testid={`cluster-risk-exposure-bar-container-${index}`}>
                        <div className="h-full bg-black" style={{ width: `${width}%` }} data-testid={`cluster-risk-exposure-bar-fill-${index}`} />
                      </div>
                    </div>
                  );
                })}
                {exposures.length === 0 && <p className="text-xs" data-testid="cluster-risk-exposure-empty">Exposure verisi yok.</p>}
              </div>
            </div>

            <div className="border border-black/25 bg-orange-100 p-4" data-testid="cluster-risk-alerts-panel">
              <h3 className="text-lg font-bold" data-testid="cluster-risk-alerts-title">Cluster Risk Alerts</h3>
              <div className="mt-3 space-y-1" data-testid="cluster-risk-alerts-list">
                {alerts.map((row, index) => (
                  <p className="text-xs" key={`${row?.cluster_id}-${index}`} data-testid={`cluster-risk-alert-item-${index}`}>
                    {row?.cluster_id}: {row?.event} · exposure={row?.cluster_exposure} · reason={(row?.reason || []).join(",")}
                  </p>
                ))}
                {alerts.length === 0 && <p className="text-xs" data-testid="cluster-risk-alert-empty">Aktif cluster risk alert yok.</p>}
              </div>
            </div>
          </div>

          <div className="border border-black/25 bg-orange-100 p-4" data-testid="cluster-risk-position-map-panel">
            <h3 className="text-lg font-bold" data-testid="cluster-risk-position-map-title">Cluster Position Map</h3>
            <div className="mt-3 space-y-2" data-testid="cluster-risk-position-map-list">
              {exposures.map((row, index) => (
                <p className="text-xs" key={`${row?.cluster_id}-map-${index}`} data-testid={`cluster-risk-position-map-item-${index}`}>
                  {row?.cluster_id}: symbols={(row?.symbols || []).join(",")} · positions={(row?.positions || []).map((item) => `${item.symbol}:${item.side}`).join(" | ") || "-"}
                </p>
              ))}
              {exposures.length === 0 && <p className="text-xs" data-testid="cluster-risk-position-map-empty">Position map verisi yok.</p>}
            </div>
          </div>
        </>
      )}
    </section>
  );
};
