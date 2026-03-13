import { useEffect, useState } from "react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const AdminPositionsMonitorPage = () => {
  const [isLoading, setIsLoading] = useState(true);
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState("");

  const load = async () => {
    setIsLoading(true);
    setLoadError("");
    try {
      const response = await apiClient.get("/admin/positions-monitor");
      setData(response.data || null);
    } catch (error) {
      const message = error?.response?.data?.detail || "Positions monitor yüklenemedi";
      setLoadError(message);
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  if (isLoading) {
    return <LoadingSkeleton rows={8} testId="admin-positions-monitor-loading-skeleton" />;
  }

  if (!data) {
    return (
      <section className="space-y-4" data-testid="admin-positions-monitor-broken-state">
        <div className="border border-rose-500/40 bg-rose-900/20 p-4" data-testid="admin-positions-monitor-broken-alert">
          <p className="text-sm font-semibold text-rose-200" data-testid="admin-positions-monitor-broken-title">Veri alınamadı</p>
          <p className="mt-1 text-sm text-rose-100" data-testid="admin-positions-monitor-broken-message">{loadError || "Positions monitor servisi şu anda yanıt vermiyor."}</p>
          <Button className="mt-3" onClick={load} data-testid="admin-positions-monitor-broken-retry-button">Tekrar Dene</Button>
        </div>
      </section>
    );
  }

  const openRows = data.open_positions || [];
  const clusterRows = Object.entries(data.cluster_exposure || {});

  return (
    <section className="grid grid-cols-12 gap-4" data-testid="admin-positions-monitor-page">
      <header className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="admin-positions-monitor-header">
        <div className="flex flex-wrap items-start justify-between gap-3" data-testid="admin-positions-monitor-header-row">
          <div data-testid="admin-positions-monitor-header-left">
            <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="admin-positions-monitor-title">Positions Monitor</h2>
            <p className="mt-2 text-sm text-slate-400" data-testid="admin-positions-monitor-description">Open positions, cluster exposure, risk level, forced liquidation risk.</p>
            <p className="mt-1 text-xs text-slate-500" data-testid="admin-positions-monitor-generated-at">Son güncelleme: {new Date(data.generated_at).toLocaleString()}</p>
          </div>
          <Button onClick={load} data-testid="admin-positions-monitor-refresh-button">Yenile</Button>
        </div>
      </header>

      {loadError && (
        <div className="col-span-12 border border-amber-500/40 bg-amber-950/20 p-3 text-sm text-amber-200" data-testid="admin-positions-monitor-warning-alert">
          Son veri yüklendi, ancak son yenilemede hata oluştu: {loadError}
        </div>
      )}

      <div className="col-span-12 grid gap-3 md:grid-cols-3" data-testid="admin-positions-monitor-summary-grid">
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-positions-monitor-open-count-card">
          <p className="text-xs text-slate-500">Open Positions</p>
          <p className="text-xl font-semibold" data-testid="admin-positions-monitor-open-count-value">{openRows.length}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-positions-monitor-risk-level-card">
          <p className="text-xs text-slate-500">Risk Level</p>
          <p className="text-xl font-semibold" data-testid="admin-positions-monitor-risk-level-value">{data.risk_level}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-positions-monitor-forced-risk-card">
          <p className="text-xs text-slate-500">Forced Liquidation Risk</p>
          <p className="text-xl font-semibold" data-testid="admin-positions-monitor-forced-risk-value">{data.forced_liquidation_risk}</p>
        </article>
      </div>

      <section className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="admin-positions-monitor-cluster-exposure-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-positions-monitor-cluster-exposure-title">Cluster Exposure</p>
        <div className="mt-2 grid gap-1" data-testid="admin-positions-monitor-cluster-exposure-list">
          {clusterRows.length === 0 && (
            <p className="text-sm text-slate-400" data-testid="admin-positions-monitor-cluster-exposure-empty">Cluster exposure verisi yok.</p>
          )}
          {clusterRows.map(([clusterId, exposure]) => (
            <p key={clusterId} className="text-sm" data-testid={`admin-positions-monitor-cluster-exposure-${clusterId}`}>{clusterId}: {exposure}</p>
          ))}
        </div>
      </section>

      <div className="col-span-12 overflow-x-auto border border-slate-800 bg-slate-900" data-testid="admin-positions-monitor-table-wrapper">
        <table className="min-w-full text-sm" data-testid="admin-positions-monitor-table">
          <thead className="sticky top-0 z-20 bg-slate-800 text-left" data-testid="admin-positions-monitor-table-head">
            <tr>
              <th className="px-3 py-2">Position</th>
              <th className="px-3 py-2">Symbol</th>
              <th className="px-3 py-2">Size</th>
              <th className="px-3 py-2">Entry</th>
              <th className="px-3 py-2">Current</th>
              <th className="px-3 py-2">PnL</th>
              <th className="px-3 py-2">Leverage</th>
              <th className="px-3 py-2">Strategy</th>
              <th className="px-3 py-2">Cluster</th>
            </tr>
          </thead>
          <tbody data-testid="admin-positions-monitor-table-body">
            {openRows.map((row) => (
              <tr key={row.position_id} className="border-t border-slate-800" data-testid={`admin-positions-monitor-row-${row.position_id}`}>
                <td className="px-3 py-2" data-testid={`admin-positions-monitor-position-id-${row.position_id}`}>{row.position_id}</td>
                <td className="px-3 py-2" data-testid={`admin-positions-monitor-symbol-${row.position_id}`}>{row.symbol}</td>
                <td className="px-3 py-2" data-testid={`admin-positions-monitor-size-${row.position_id}`}>{row.size}</td>
                <td className="px-3 py-2" data-testid={`admin-positions-monitor-entry-${row.position_id}`}>{row.entry_price}</td>
                <td className="px-3 py-2" data-testid={`admin-positions-monitor-current-${row.position_id}`}>{row.current_price}</td>
                <td className="px-3 py-2" data-testid={`admin-positions-monitor-pnl-${row.position_id}`}>{row.unrealized_pnl}</td>
                <td className="px-3 py-2" data-testid={`admin-positions-monitor-leverage-${row.position_id}`}>{row.leverage}</td>
                <td className="px-3 py-2" data-testid={`admin-positions-monitor-strategy-${row.position_id}`}>{row.strategy_id || "-"}</td>
                <td className="px-3 py-2" data-testid={`admin-positions-monitor-cluster-${row.position_id}`}>{row.cluster_id || "UNCLUSTERED"}</td>
              </tr>
            ))}
            {openRows.length === 0 && (
              <tr className="border-t border-slate-800" data-testid="admin-positions-monitor-empty-row">
                <td colSpan={9} className="px-3 py-4 text-center text-sm text-slate-400" data-testid="admin-positions-monitor-empty-text">Şu an açık pozisyon bulunmuyor.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
};
