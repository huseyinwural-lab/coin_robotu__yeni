import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export const ValidationCenterPanel = ({ approvedUsers, data, loading, error, onRefresh, onRerun }) => {
  const [windowHours, setWindowHours] = useState(24);
  const [userId, setUserId] = useState("");
  const [strategyId, setStrategyId] = useState("");
  const [marketType, setMarketType] = useState("spot");
  const [environment, setEnvironment] = useState("testnet");

  const summary = data?.summary || {};
  const driftAlerts = data?.drift_alerts || [];
  const timeline = data?.timeline || [];
  const diffItems = data?.diff_items || [];
  const checkLevelTrends = data?.check_level_trends || [];
  const topReasons = data?.top_reason_codes || [];

  return (
    <section className="rounded-2xl border border-emerald-500/30 bg-slate-950/80 p-4" data-testid="validation-center-panel">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-base font-semibold text-emerald-200" data-testid="validation-center-title">Validation Center UI (P2-403)</h3>
          <p className="text-xs text-slate-400" data-testid="validation-center-subtitle">validation_report timeline + diff + rerun + drift alerts (24h)</p>
        </div>
        <div className="flex gap-2" data-testid="validation-center-actions-row">
          <Input type="number" value={windowHours} onChange={(event) => setWindowHours(event.target.value)} className="w-24" data-testid="validation-center-window-hours-input" />
          <Button type="button" variant="outline" onClick={() => onRefresh({ window_hours: Number(windowHours), limit: 200 })} data-testid="validation-center-refresh-button">Yenile</Button>
        </div>
      </div>

      <div className="mb-3 grid gap-2 md:grid-cols-5" data-testid="validation-center-rerun-form">
        <select value={userId} onChange={(event) => setUserId(event.target.value)} className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm" data-testid="validation-center-rerun-user-select">
          <option value="">Global rerun</option>
          {(approvedUsers || []).map((user) => (
            <option key={user.id} value={user.id}>{user.email}</option>
          ))}
        </select>
        <Input value={strategyId} onChange={(event) => setStrategyId(event.target.value)} placeholder="strategy_id" data-testid="validation-center-rerun-strategy-input" />
        <select value={marketType} onChange={(event) => setMarketType(event.target.value)} className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm" data-testid="validation-center-rerun-market-type-select">
          <option value="spot">spot</option>
          <option value="futures">futures</option>
        </select>
        <select value={environment} onChange={(event) => setEnvironment(event.target.value)} className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm" data-testid="validation-center-rerun-environment-select">
          <option value="testnet">testnet</option>
          <option value="live">live</option>
        </select>
        <Button
          type="button"
          onClick={() => onRerun({ user_id: userId || null, strategy_id: strategyId || null, market_type: marketType, environment })}
          data-testid="validation-center-rerun-button"
        >
          Rerun
        </Button>
      </div>

      {loading && <p className="text-sm text-slate-400" data-testid="validation-center-loading-state">Yükleniyor...</p>}
      {!loading && error && <p className="text-sm text-red-300" data-testid="validation-center-error-state">{error}</p>}
      {!loading && !error && (
        <>
          <p className="mb-2 text-xs text-slate-200" data-testid="validation-center-summary">events={summary.total_events ?? 0}, pass/warn/block={summary.pass_count ?? 0}/{summary.warn_count ?? 0}/{summary.block_count ?? 0}, drift_alerts={summary.drift_alert_count ?? 0}</p>

          <div className="mb-3" data-testid="validation-center-drift-alerts-list">
            <p className="text-xs font-semibold text-emerald-100" data-testid="validation-center-drift-alerts-title">Validation Drift Alerts</p>
            {driftAlerts.length === 0 && <p className="text-xs text-slate-400" data-testid="validation-center-drift-alerts-empty">Drift alert yok.</p>}
            {driftAlerts.slice(0, 20).map((item, index) => (
              <article key={`${item.strategy_key}-${index}`} className="border-t border-slate-800 py-1 text-xs text-emerald-200" data-testid={`validation-center-drift-alert-${index}`}>
                <p data-testid={`validation-center-drift-alert-summary-${index}`}>{item.strategy_key}: {item.from_status} → {item.to_status} ({item.event_count} event)</p>
                <p className="text-slate-300" data-testid={`validation-center-drift-alert-reasons-${index}`}>reasons: {(item.latest_reason_codes || []).join(", ") || "-"}</p>
                <p className="text-slate-300" data-testid={`validation-center-drift-alert-hints-${index}`}>hints: {(item.root_cause_hints || []).join(" | ") || "-"}</p>
              </article>
            ))}
          </div>

          <div className="mb-3" data-testid="validation-center-check-level-trends-list">
            <p className="text-xs font-semibold text-slate-100" data-testid="validation-center-check-level-trends-title">Check-Level Trend Chart</p>
            {checkLevelTrends.length === 0 && <p className="text-xs text-slate-400" data-testid="validation-center-check-level-trends-empty">Check trend verisi yok.</p>}
            {checkLevelTrends.slice(0, 20).map((item, index) => (
              <p key={`${item.check_name}-${index}`} className="border-t border-slate-800 py-1 text-xs text-slate-300" data-testid={`validation-center-check-level-trend-${index}`}>
                {item.check_name}: pass/warn/block={item.pass_count}/{item.warn_count}/{item.block_count}
              </p>
            ))}
            <p className="mt-1 text-xs text-slate-400" data-testid="validation-center-top-reasons">top reasons: {(topReasons || []).map((item) => `${item[0]}(${item[1]})`).join(", ") || "-"}</p>
          </div>

          <div className="mb-3" data-testid="validation-center-diff-list">
            <p className="text-xs font-semibold text-slate-100" data-testid="validation-center-diff-title">Timeline Diff</p>
            {diffItems.length === 0 && <p className="text-xs text-slate-400" data-testid="validation-center-diff-empty">Status diff yok.</p>}
            {diffItems.slice(0, 20).map((item, index) => (
              <p key={`${item.strategy_key}-${index}`} className="border-t border-slate-800 py-1 text-xs text-slate-300" data-testid={`validation-center-diff-item-${index}`}>
                {item.strategy_key}: {item.from_status} → {item.to_status} ({item.from_at} → {item.to_at})
              </p>
            ))}
          </div>

          <div data-testid="validation-center-timeline-list">
            <p className="text-xs font-semibold text-slate-100" data-testid="validation-center-timeline-title">Validation Timeline</p>
            {timeline.length === 0 && <p className="text-xs text-slate-400" data-testid="validation-center-timeline-empty">Timeline kaydı yok.</p>}
            {timeline.slice(0, 25).map((item, index) => (
              <p key={`${item.id}-${index}`} className="border-t border-slate-800 py-1 text-xs text-slate-300" data-testid={`validation-center-timeline-item-${index}`}>
                {item.created_at} · {item.strategy_key} · {item.net_status} · source={item.source}
              </p>
            ))}
          </div>
        </>
      )}
    </section>
  );
};
