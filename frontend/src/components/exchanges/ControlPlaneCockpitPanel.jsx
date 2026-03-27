import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export const ControlPlaneCockpitPanel = ({ data, loading, error, onRefresh }) => {
  const [windowMinutes, setWindowMinutes] = useState(30);
  const [churnThreshold, setChurnThreshold] = useState(5);

  const refreshWithThreshold = async () => {
    await onRefresh({ window_minutes: Number(windowMinutes), churn_threshold: Number(churnThreshold) });
  };

  const overview = data?.global_overview || {};
  const routeMap = data?.active_route_map || [];
  const churnAlert = data?.route_churn_anomaly_alert || {};
  const latestChanges = data?.last_critical_changes || [];

  return (
    <section className="rounded-2xl border border-orange-500/30 bg-slate-950/80 p-4" data-testid="control-plane-cockpit-panel">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-base font-semibold text-orange-200" data-testid="control-plane-cockpit-title">Control Plane Cockpit (P2-401)</h3>
          <p className="text-xs text-slate-400" data-testid="control-plane-cockpit-subtitle">Global overview, active route map, failover board ve route churn anomaly alert</p>
        </div>
        <div className="flex flex-wrap items-center gap-2" data-testid="control-plane-cockpit-controls">
          <Input type="number" value={windowMinutes} onChange={(event) => setWindowMinutes(event.target.value)} className="w-24" data-testid="control-plane-cockpit-window-minutes-input" />
          <Input type="number" value={churnThreshold} onChange={(event) => setChurnThreshold(event.target.value)} className="w-24" data-testid="control-plane-cockpit-churn-threshold-input" />
          <Button type="button" variant="outline" onClick={refreshWithThreshold} data-testid="control-plane-cockpit-refresh-button">Yenile</Button>
        </div>
      </div>

      {loading && <p className="text-sm text-slate-400" data-testid="control-plane-cockpit-loading-state">Yükleniyor...</p>}
      {!loading && error && <p className="text-sm text-red-300" data-testid="control-plane-cockpit-error-state">{error}</p>}
      {!loading && !error && (
        <>
          <div className="mb-3 grid gap-2 text-xs md:grid-cols-4" data-testid="control-plane-cockpit-overview-grid">
            <p data-testid="control-plane-cockpit-overview-total-venues">venues: {overview.total_venues ?? 0}</p>
            <p data-testid="control-plane-cockpit-overview-health-split">healthy/degraded/down: {overview.healthy_venues ?? 0}/{overview.degraded_venues ?? 0}/{overview.down_venues ?? 0}</p>
            <p data-testid="control-plane-cockpit-overview-routing-rules">routing_rules: {overview.routing_rule_count ?? 0}</p>
            <p data-testid="control-plane-cockpit-overview-failover-rules">failover_rules: {overview.failover_rule_count ?? 0}</p>
          </div>

          <div className="mb-3 rounded-lg border border-slate-800 p-3" data-testid="control-plane-cockpit-churn-alert-box">
            <p className="text-xs font-semibold text-slate-100" data-testid="control-plane-cockpit-churn-alert-status">route_churn_status: {churnAlert.status || "PASS"}</p>
            <p className="text-xs text-slate-300" data-testid="control-plane-cockpit-churn-alert-window">window={churnAlert.window_minutes || 30}m, threshold={churnAlert.threshold || 5}, transitions={churnAlert.total_recent_transitions || 0}</p>
            <p className="text-xs text-slate-400" data-testid="control-plane-cockpit-churn-alert-hot-routes">hot_routes: {(churnAlert.hot_routes || []).map((item) => `${item.key}(${item.transition_count})`).join(", ") || "yok"}</p>
          </div>

          <div className="mb-3" data-testid="control-plane-cockpit-active-route-map">
            <p className="mb-1 text-xs font-semibold text-slate-100" data-testid="control-plane-cockpit-active-route-map-title">Active Route Map</p>
            {routeMap.length === 0 && <p className="text-xs text-slate-400" data-testid="control-plane-cockpit-active-route-map-empty">Aktif route bulunamadı.</p>}
            {routeMap.slice(0, 12).map((row, index) => (
              <p key={`${row.key}-${index}`} className="border-t border-slate-800 py-1 text-xs text-slate-200" data-testid={`control-plane-cockpit-active-route-map-row-${index}`}>
                {row.strategy_id} · {row.market_type}/{row.environment} → {row.active_venue || "-"} · fallback={(row.fallback_chain || []).join(" -> ") || "-"}
              </p>
            ))}
          </div>

          <div data-testid="control-plane-cockpit-last-critical-changes">
            <p className="mb-1 text-xs font-semibold text-slate-100" data-testid="control-plane-cockpit-last-critical-changes-title">Last Critical Changes</p>
            {latestChanges.length === 0 && <p className="text-xs text-slate-400" data-testid="control-plane-cockpit-last-critical-changes-empty">Kritik değişiklik kaydı yok.</p>}
            {latestChanges.slice(0, 10).map((item, index) => (
              <p key={`${item.id}-${index}`} className="border-t border-slate-800 py-1 text-xs text-slate-300" data-testid={`control-plane-cockpit-last-critical-change-${index}`}>
                {item.created_at} · {item.action} · {item.entity_id}
              </p>
            ))}
          </div>
        </>
      )}
    </section>
  );
};
