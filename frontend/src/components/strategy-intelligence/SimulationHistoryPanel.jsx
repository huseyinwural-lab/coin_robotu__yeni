import { Button } from "@/components/ui/button";

const formatDate = (value) => {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "-" : date.toLocaleString();
};

export const SimulationHistoryPanel = ({ rows = [], comparingRunId, compareResult, onCompare }) => {
  return (
    <section className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="strategy-intelligence-simulation-history-panel">
      <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="strategy-intelligence-simulation-history-title">
        Simulation History + Replay Compare
      </p>

      {compareResult && (
        <div className="mt-2 rounded border border-slate-800 bg-slate-950 p-2" data-testid="strategy-intelligence-simulation-compare-panel">
          <p className="text-sm" data-testid="strategy-intelligence-simulation-compare-run-id">run_id={compareResult.run_id}</p>
          <p className="text-xs text-slate-400" data-testid="strategy-intelligence-simulation-compare-risk-delta">
            risk_delta_vs_history={compareResult.compare_summary?.risk_delta_vs_history ?? "-"}
          </p>
          <p className="text-xs text-slate-400" data-testid="strategy-intelligence-simulation-compare-adj-risk-delta">
            confidence_adjusted_risk_delta_vs_history={compareResult.compare_summary?.confidence_adjusted_risk_delta_vs_history ?? "-"}
          </p>
          <p className="text-xs text-slate-400" data-testid="strategy-intelligence-simulation-compare-decision-delta">
            decision_delta_vs_history={compareResult.compare_summary?.decision_delta_vs_history ?? "-"}
          </p>
        </div>
      )}

      <div className="mt-2 space-y-2" data-testid="strategy-intelligence-simulation-history-list">
        {rows.slice(0, 16).map((item, index) => (
          <article key={item.run_id} className="border border-slate-800 p-2" data-testid={`strategy-intelligence-simulation-history-item-${index}`}>
            <p className="text-sm" data-testid={`strategy-intelligence-simulation-history-main-${index}`}>
              {item.run_id} · mode={item.request_mode} · status={item.status}
            </p>
            <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-simulation-history-symbols-${index}`}>
              symbols={(item.symbols || []).join(", ") || "-"}
            </p>
            <p className="text-xs text-slate-500" data-testid={`strategy-intelligence-simulation-history-created-at-${index}`}>
              created_at={formatDate(item.created_at)}
            </p>
            <Button
              className="mt-2"
              size="sm"
              variant="outline"
              onClick={() => onCompare(item.run_id)}
              disabled={comparingRunId === item.run_id}
              data-testid={`strategy-intelligence-simulation-compare-button-${index}`}
            >
              {comparingRunId === item.run_id ? "Comparing..." : "Compare with Current"}
            </Button>
          </article>
        ))}

        {rows.length === 0 && (
          <p className="text-sm text-slate-400" data-testid="strategy-intelligence-simulation-history-empty">
            No data yet.
          </p>
        )}
      </div>
    </section>
  );
};
