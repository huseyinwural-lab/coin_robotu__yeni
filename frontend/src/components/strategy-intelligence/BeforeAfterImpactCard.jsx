export const BeforeAfterImpactCard = ({ simulationResult }) => {
  if (!simulationResult) {
    return (
      <div className="border border-slate-800 bg-slate-900 p-3" data-testid="strategy-intelligence-before-after-empty-card">
        <p className="text-sm text-slate-400">No data yet: simulation çalıştırınca before/after impact burada görünür.</p>
      </div>
    );
  }

  const before = simulationResult.before_state || {};
  const after = simulationResult.after_state || {};

  const renderDelta = (label, value) => {
    const numeric = Number(value || 0);
    const arrow = numeric > 0 ? "↑" : numeric < 0 ? "↓" : "→";
    const color = numeric > 0 ? "text-rose-300" : numeric < 0 ? "text-emerald-300" : "text-slate-300";
    return (
      <p className={`text-sm ${color}`} data-testid={`strategy-intelligence-impact-delta-${label}`}>
        {label}: {arrow} {numeric}
      </p>
    );
  };

  return (
    <div className="border border-slate-800 bg-slate-900 p-4" data-testid="strategy-intelligence-before-after-card">
      <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="strategy-intelligence-before-after-title">Before / After Impact</p>
      <div className="mt-2 grid gap-3 md:grid-cols-2" data-testid="strategy-intelligence-before-after-grid">
        <article className="border border-slate-800 p-2" data-testid="strategy-intelligence-before-state-card">
          <p className="text-xs text-slate-500">Before</p>
          <p className="text-sm" data-testid="strategy-intelligence-before-risk">risk_score: {before.risk_score ?? "-"}</p>
          <p className="text-sm" data-testid="strategy-intelligence-before-gate">gate_decision: {before.gate_decision ?? "-"}</p>
          <p className="text-sm" data-testid="strategy-intelligence-before-exposure">exposure: {before.exposure ?? "-"}</p>
          <p className="text-sm" data-testid="strategy-intelligence-before-pnl">pnl_estimate: {before.pnl_estimate ?? "-"}</p>
        </article>

        <article className="border border-slate-800 p-2" data-testid="strategy-intelligence-after-state-card">
          <p className="text-xs text-slate-500">After</p>
          <p className="text-sm" data-testid="strategy-intelligence-after-risk">risk_score: {after.risk_score ?? "-"}</p>
          <p className="text-sm" data-testid="strategy-intelligence-after-gate">gate_decision: {after.gate_decision ?? "-"}</p>
          <p className="text-sm" data-testid="strategy-intelligence-after-exposure">exposure: {after.exposure ?? "-"}</p>
          <p className="text-sm" data-testid="strategy-intelligence-after-pnl">pnl_estimate: {after.pnl_estimate ?? "-"}</p>
        </article>
      </div>

      <div className="mt-2 rounded border border-slate-800 p-2" data-testid="strategy-intelligence-impact-delta-row">
        <p className="text-sm" data-testid="strategy-intelligence-impact-risk-delta">risk_delta: {simulationResult.risk_delta}</p>
        <p className="text-sm" data-testid="strategy-intelligence-impact-decision-delta">decision_delta: {simulationResult.decision_delta}</p>
        <p className="text-sm" data-testid="strategy-intelligence-impact-projected-pnl">projected_pnl: {simulationResult.projected_pnl}</p>
        <p className="text-sm" data-testid="strategy-intelligence-impact-projected-drawdown">projected_drawdown: {simulationResult.projected_drawdown}</p>
        <p className="text-sm" data-testid="strategy-intelligence-impact-exposure-change">exposure_change: {simulationResult.exposure_change}</p>
        <p className="text-sm" data-testid="strategy-intelligence-impact-var-change">var_change: {simulationResult.var_change}</p>
        <p className="text-sm" data-testid="strategy-intelligence-impact-liquidity-impact">liquidity_impact: {simulationResult.liquidity_impact}</p>
        <p className="text-sm" data-testid="strategy-intelligence-impact-confidence-adjusted-risk">
          confidence_adjusted_risk_score: {simulationResult.confidence_adjusted_risk_score}
        </p>
        <div className="mt-2" data-testid="strategy-intelligence-impact-colored-delta-group">
          {renderDelta("risk", simulationResult.risk_delta)}
          {renderDelta("exposure", simulationResult.exposure_change)}
          {renderDelta("var", simulationResult.var_change)}
        </div>
        <p className="text-xs text-slate-400" data-testid="strategy-intelligence-impact-decision-summary">
          decision_summary={JSON.stringify(simulationResult.decision_summary || {})}
        </p>
      </div>
    </div>
  );
};
