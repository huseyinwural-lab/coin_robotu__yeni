import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export const StrategyVenueHeatmapPanel = ({ data, loading, error, onRefresh }) => {
  const [windowHours, setWindowHours] = useState(24);
  const [compareWindowHours, setCompareWindowHours] = useState(720);
  const strategies = data?.strategies || [];
  const topDrifts = data?.top_allocation_drifts || [];
  const strategyDeltas = data?.comparison?.strategy_deltas || [];

  return (
    <section className="rounded-2xl border border-cyan-500/30 bg-slate-950/80 p-4" data-testid="strategy-venue-heatmap-panel">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-base font-semibold text-cyan-200" data-testid="strategy-venue-heatmap-title">Strategy-to-Venue Heatmap (P2-404)</h3>
          <p className="text-xs text-slate-400" data-testid="strategy-venue-heatmap-subtitle">Allocation drift + route churn görünümü</p>
        </div>
        <div className="flex gap-2" data-testid="strategy-venue-heatmap-controls">
          <Input type="number" value={windowHours} onChange={(event) => setWindowHours(event.target.value)} className="w-24" data-testid="strategy-venue-heatmap-window-hours-input" />
          <Input type="number" value={compareWindowHours} onChange={(event) => setCompareWindowHours(event.target.value)} className="w-24" data-testid="strategy-venue-heatmap-compare-window-hours-input" />
          <Button type="button" variant="outline" onClick={() => onRefresh({ window_hours: Number(windowHours), compare_window_hours: Number(compareWindowHours) })} data-testid="strategy-venue-heatmap-refresh-button">Yenile</Button>
        </div>
      </div>

      {loading && <p className="text-sm text-slate-400" data-testid="strategy-venue-heatmap-loading-state">Yükleniyor...</p>}
      {!loading && error && <p className="text-sm text-red-300" data-testid="strategy-venue-heatmap-error-state">{error}</p>}
      {!loading && !error && (
        <>
          <div className="mb-3" data-testid="strategy-venue-heatmap-top-drifts-list">
            <p className="text-xs font-semibold text-cyan-100" data-testid="strategy-venue-heatmap-top-drifts-title">Top Allocation Drifts</p>
            {topDrifts.length === 0 && <p className="text-xs text-slate-400" data-testid="strategy-venue-heatmap-top-drifts-empty">Drift kaydı yok.</p>}
            {topDrifts.slice(0, 20).map((item, index) => (
              <p key={`${item.strategy_key}-${item.venue}-${index}`} className="border-t border-slate-800 py-1 text-xs text-cyan-200" data-testid={`strategy-venue-heatmap-top-drift-${index}`}>
                {item.strategy_key} · {item.venue} · drift={item.allocation_drift}
              </p>
            ))}
          </div>

          <div className="mb-3" data-testid="strategy-venue-heatmap-comparison-list">
            <p className="text-xs font-semibold text-cyan-100" data-testid="strategy-venue-heatmap-comparison-title">24h vs 30d Drift Delta</p>
            {strategyDeltas.length === 0 && <p className="text-xs text-slate-400" data-testid="strategy-venue-heatmap-comparison-empty">Karşılaştırma verisi yok.</p>}
            {strategyDeltas.slice(0, 20).map((item, index) => (
              <p key={`${item.key}-${index}`} className="border-t border-slate-800 py-1 text-xs text-cyan-200" data-testid={`strategy-venue-heatmap-comparison-item-${index}`}>
                {item.key}: drift_delta={item.allocation_drift_delta} · churn_delta={item.route_churn_delta}
              </p>
            ))}
          </div>

          <div data-testid="strategy-venue-heatmap-strategies-list">
            <p className="text-xs font-semibold text-slate-100" data-testid="strategy-venue-heatmap-strategies-title">Strategies</p>
            {strategies.length === 0 && <p className="text-xs text-slate-400" data-testid="strategy-venue-heatmap-strategies-empty">Heatmap verisi yok.</p>}
            {strategies.slice(0, 30).map((row, index) => (
              <article key={`${row.key}-${index}`} className="mb-2 rounded border border-slate-800 p-2 text-xs" data-testid={`strategy-venue-heatmap-strategy-row-${index}`}>
                <p data-testid={`strategy-venue-heatmap-strategy-header-${index}`}>{row.strategy_id} · churn={row.route_churn_count} · routes={row.total_routes}</p>
                {(row.venue_distribution || []).map((venueRow, venueIndex) => (
                  <p key={`${venueRow.venue}-${venueIndex}`} className="text-slate-300" data-testid={`strategy-venue-heatmap-strategy-venue-${index}-${venueIndex}`}>
                    {venueRow.venue}: actual={venueRow.actual_ratio} target={venueRow.target_ratio ?? "-"} drift={venueRow.allocation_drift ?? "-"}
                  </p>
                ))}
              </article>
            ))}
          </div>
        </>
      )}
    </section>
  );
};
