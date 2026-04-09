import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

const formatPct = (value) => `${Number(value || 0).toFixed(2)}%`;

export const AdminStrategyTakipPage = () => {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/admin/canonical-strategies/strategy-takip");
      setRows(Array.isArray(data) ? data : []);
    } catch (error) {
      setRows([]);
      toast.error(error?.response?.data?.detail || "Strategy takip verisi alınamadı");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <section className="space-y-4" data-testid="admin-strategy-takip-page">
      <div className="flex flex-wrap items-center justify-between gap-2" data-testid="admin-strategy-takip-header">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100" data-testid="admin-strategy-takip-title">Strategy Takip</h1>
          <p className="text-sm text-slate-400" data-testid="admin-strategy-takip-subtitle">
            12 strateji için başarı yüzdesi (Win Rate = kârlı kapanan trade / kapanan trade)
          </p>
        </div>
        <Button onClick={load} disabled={loading} data-testid="admin-strategy-takip-refresh-button">
          {loading ? "Yükleniyor..." : "Yenile"}
        </Button>
      </div>

      <div className="overflow-auto rounded border border-slate-800" data-testid="admin-strategy-takip-table-wrapper">
        <table className="min-w-full text-sm" data-testid="admin-strategy-takip-table">
          <thead className="bg-slate-900/80 text-slate-200" data-testid="admin-strategy-takip-table-head">
            <tr>
              <th className="px-3 py-2 text-left" data-testid="admin-strategy-takip-header-strategy-id">strategy_id</th>
              <th className="px-3 py-2 text-left" data-testid="admin-strategy-takip-header-family">family</th>
              <th className="px-3 py-2 text-right" data-testid="admin-strategy-takip-header-1d">1 günlük başarı %</th>
              <th className="px-3 py-2 text-right" data-testid="admin-strategy-takip-header-7d">7 günlük başarı %</th>
              <th className="px-3 py-2 text-right" data-testid="admin-strategy-takip-header-30d">30 günlük başarı %</th>
              <th className="px-3 py-2 text-right" data-testid="admin-strategy-takip-header-90d">90 günlük başarı %</th>
            </tr>
          </thead>
          <tbody data-testid="admin-strategy-takip-table-body">
            {rows.map((row, index) => (
              <tr key={row.strategy_id} className="border-t border-slate-800" data-testid={`admin-strategy-takip-row-${index}`}>
                <td className="px-3 py-2 font-mono text-xs text-slate-100" data-testid={`admin-strategy-takip-row-strategy-id-${index}`}>{row.strategy_id}</td>
                <td className="px-3 py-2 text-slate-200" data-testid={`admin-strategy-takip-row-family-${index}`}>{row.family}</td>
                <td className="px-3 py-2 text-right text-slate-100" data-testid={`admin-strategy-takip-row-1d-${index}`}>{formatPct(row.success_1d_pct)}</td>
                <td className="px-3 py-2 text-right text-slate-100" data-testid={`admin-strategy-takip-row-7d-${index}`}>{formatPct(row.success_7d_pct)}</td>
                <td className="px-3 py-2 text-right text-slate-100" data-testid={`admin-strategy-takip-row-30d-${index}`}>{formatPct(row.success_30d_pct)}</td>
                <td className="px-3 py-2 text-right text-slate-100" data-testid={`admin-strategy-takip-row-90d-${index}`}>{formatPct(row.success_90d_pct)}</td>
              </tr>
            ))}
            {!loading && rows.length === 0 && (
              <tr data-testid="admin-strategy-takip-empty-row">
                <td colSpan={6} className="px-3 py-5 text-center text-slate-400" data-testid="admin-strategy-takip-empty-text">
                  Strategy takip verisi bulunamadı.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
};
