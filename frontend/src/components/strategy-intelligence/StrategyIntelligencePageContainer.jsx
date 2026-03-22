import { Button } from "@/components/ui/button";

export const StrategyIntelligencePageContainer = ({
  role,
  lastUpdatedAt,
  dashboard,
  loadError,
  onRefresh,
  children,
}) => {
  const governance = dashboard?.governance_summary || {};

  return (
    <section className="grid grid-cols-12 gap-4" data-testid="strategy-intelligence-page-container">
      <header className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="strategy-intelligence-header">
        <div className="flex flex-wrap items-start justify-between gap-3" data-testid="strategy-intelligence-header-row">
          <div>
            <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="strategy-intelligence-title">Decision Engine Control Panel</h2>
            <p className="mt-2 text-sm text-slate-400" data-testid="strategy-intelligence-subtitle">
              simulate → impact review → confirm → apply → audit
            </p>
            <p className="mt-1 text-xs text-slate-500" data-testid="strategy-intelligence-last-updated">
              Son güncelleme: {lastUpdatedAt ? new Date(lastUpdatedAt).toLocaleString() : "-"}
            </p>
            <p className="mt-1 text-xs text-slate-500" data-testid="strategy-intelligence-role-badge">role={role || "unknown"}</p>
          </div>
          <Button onClick={onRefresh} data-testid="strategy-intelligence-refresh-button">Yenile</Button>
        </div>
      </header>

      {loadError && (
        <div className="col-span-12 border border-amber-500/40 bg-amber-950/20 p-3 text-sm text-amber-200" data-testid="strategy-intelligence-warning-alert">
          Son yenilemede hata: {loadError}
        </div>
      )}

      <div className="col-span-12 grid gap-3 md:grid-cols-5" data-testid="strategy-intelligence-summary-grid">
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="strategy-intelligence-summary-conflicts-card">
          <p className="text-xs text-slate-500">Strategy Conflicts</p>
          <p className="text-xl font-semibold" data-testid="strategy-intelligence-summary-conflicts-value">{(dashboard?.strategy_conflicts || []).length}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="strategy-intelligence-summary-rebalance-card">
          <p className="text-xs text-slate-500">Rebalance Events</p>
          <p className="text-xl font-semibold" data-testid="strategy-intelligence-summary-rebalance-value">{(dashboard?.capital_rebalance_events || []).length}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="strategy-intelligence-summary-drift-card">
          <p className="text-xs text-slate-500">Allocation Drift</p>
          <p className="text-xl font-semibold" data-testid="strategy-intelligence-summary-drift-value">{dashboard?.allocation_drift ?? 0}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="strategy-intelligence-summary-rar-card">
          <p className="text-xs text-slate-500">Risk Adjusted Return</p>
          <p className="text-xl font-semibold" data-testid="strategy-intelligence-summary-rar-value">{dashboard?.risk_adjusted_return ?? 0}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="strategy-intelligence-summary-cadence-card">
          <p className="text-xs text-slate-500">Cadence Blocked</p>
          <p className="text-xl font-semibold" data-testid="strategy-intelligence-summary-cadence-value">{governance?.cadence_blocked_strategies ?? 0}</p>
        </article>
      </div>

      {children}
    </section>
  );
};
