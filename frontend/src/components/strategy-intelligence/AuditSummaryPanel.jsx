export const AuditSummaryPanel = ({ manualOverrides = [], activeOverrides = [] }) => {
  const latest = manualOverrides[0] || null;

  return (
    <section className="border border-slate-800 bg-slate-900 p-4" data-testid="strategy-intelligence-audit-summary-panel">
      <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="strategy-intelligence-audit-summary-title">Audit Summary</p>
      <div className="mt-2 grid gap-3 md:grid-cols-3" data-testid="strategy-intelligence-audit-summary-grid">
        <article className="border border-slate-800 p-2" data-testid="strategy-intelligence-audit-total-overrides-card">
          <p className="text-xs text-slate-500">total_logs</p>
          <p className="text-xl font-semibold" data-testid="strategy-intelligence-audit-total-overrides-value">{manualOverrides.length}</p>
        </article>
        <article className="border border-slate-800 p-2" data-testid="strategy-intelligence-audit-active-overrides-card">
          <p className="text-xs text-slate-500">active_overrides</p>
          <p className="text-xl font-semibold" data-testid="strategy-intelligence-audit-active-overrides-value">{activeOverrides.length}</p>
        </article>
        <article className="border border-slate-800 p-2" data-testid="strategy-intelligence-audit-latest-action-card">
          <p className="text-xs text-slate-500">latest_action</p>
          <p className="text-sm font-semibold" data-testid="strategy-intelligence-audit-latest-action-value">{latest?.action_type || "-"}</p>
          <p className="text-xs text-slate-400" data-testid="strategy-intelligence-audit-latest-action-reason">{latest?.reason || "-"}</p>
        </article>
      </div>
    </section>
  );
};
