import { useEffect, useState } from "react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { apiClient } from "@/lib/api";

export const AdminPositionsMonitorPage = () => {
  const [isLoading, setIsLoading] = useState(true);
  const [data, setData] = useState(null);

  const load = async () => {
    setIsLoading(true);
    try {
      const response = await apiClient.get("/admin/positions-monitor");
      setData(response.data || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Positions monitor yüklenemedi");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  if (isLoading || !data) {
    return <LoadingSkeleton rows={8} testId="admin-positions-monitor-loading-skeleton" />;
  }

  return (
    <section className="grid grid-cols-12 gap-4" data-testid="admin-positions-monitor-page">
      <header className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="admin-positions-monitor-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="admin-positions-monitor-title">Positions Monitor</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="admin-positions-monitor-description">Open positions, cluster exposure, risk level, forced liquidation risk.</p>
      </header>

      <div className="col-span-12 grid gap-3 md:grid-cols-3" data-testid="admin-positions-monitor-summary-grid">
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-positions-monitor-open-count-card">
          <p className="text-xs text-slate-500">Open Positions</p>
          <p className="text-xl font-semibold" data-testid="admin-positions-monitor-open-count-value">{(data.open_positions || []).length}</p>
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
          {Object.entries(data.cluster_exposure || {}).map(([clusterId, exposure]) => (
            <p key={clusterId} className="text-sm" data-testid={`admin-positions-monitor-cluster-exposure-${clusterId}`}>{clusterId}: {exposure}</p>
          ))}
        </div>
      </section>

      <div className="col-span-12 overflow-x-auto border border-slate-800 bg-slate-900" data-testid="admin-positions-monitor-table-wrapper">
        <table className="min-w-full text-sm" data-testid="admin-positions-monitor-table">
          <thead className="bg-slate-800 text-left" data-testid="admin-positions-monitor-table-head">
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
            {(data.open_positions || []).map((row) => (
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
          </tbody>
        </table>
      </div>
    </section>
  );
};
