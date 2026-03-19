import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const AdminFreshnessHeatmapPage = () => {
  const [windowSize, setWindowSize] = useState("24h");
  const [heatmap, setHeatmap] = useState({ items: [] });
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/admin/universe-monitor/freshness-heatmap", { params: { window: windowSize } });
      setHeatmap(data || { items: [] });
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Freshness heatmap yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, [windowSize]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section className="space-y-4" data-testid="admin-freshness-heatmap-page">
      <header className="border border-rose-800/50 bg-rose-950/20 p-4" data-testid="admin-freshness-heatmap-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-rose-300" data-testid="admin-freshness-heatmap-title">Freshness SLA Breach Heatmap</h2>
        <p className="mt-2 text-sm text-rose-100" data-testid="admin-freshness-heatmap-description">
          Symbol/timeframe bazında stale-rate yoğunluk görünümü.
        </p>
      </header>

      <div className="flex flex-wrap items-end gap-2" data-testid="admin-freshness-heatmap-toolbar">
        <label className="space-y-1" data-testid="admin-freshness-heatmap-window-field">
          <span className="text-xs text-rose-100">Window</span>
          <select
            value={windowSize}
            onChange={(event) => setWindowSize(event.target.value)}
            className="h-10 rounded border border-rose-800 bg-black px-2 text-sm"
            data-testid="admin-freshness-heatmap-window-select"
          >
            <option value="24h" data-testid="admin-freshness-heatmap-window-24h">24s</option>
            <option value="7d" data-testid="admin-freshness-heatmap-window-7d">7g</option>
            <option value="30d" data-testid="admin-freshness-heatmap-window-30d">30g</option>
          </select>
        </label>
        <Button type="button" variant="outline" onClick={load} data-testid="admin-freshness-heatmap-refresh-button">
          Yenile
        </Button>
      </div>

      <div className="max-h-[540px] overflow-auto rounded border border-rose-800/50 bg-rose-950/20 p-3" data-testid="admin-freshness-heatmap-list">
        {(heatmap?.items || []).map((item, idx) => (
          <p key={`heat-${idx}`} className="text-xs" data-testid={`admin-freshness-heatmap-item-${idx}`}>
            {item.symbol}:{item.timeframe} · stale_rate={item.stale_rate} · stale={item.stale}/{item.total} · avg_age={item.avg_snapshot_age}
          </p>
        ))}
        {(heatmap?.items || []).length === 0 && <p className="text-xs text-rose-100" data-testid="admin-freshness-heatmap-empty">Heatmap verisi yok.</p>}
      </div>

      {loading && <p className="text-xs text-rose-100" data-testid="admin-freshness-heatmap-loading">Yükleniyor...</p>}
    </section>
  );
};
