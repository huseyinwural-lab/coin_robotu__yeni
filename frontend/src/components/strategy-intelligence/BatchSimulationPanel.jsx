import { Button } from "@/components/ui/button";

export const BatchSimulationPanel = ({ canSimulate, isRunning, batchResult, onRun }) => {
  return (
    <section className="border border-slate-800 bg-slate-900 p-4" data-testid="strategy-intelligence-batch-simulation-panel">
      <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="strategy-intelligence-batch-simulation-title">
        Batch Simulation (selected symbols)
      </p>
      <Button
        type="button"
        onClick={onRun}
        disabled={!canSimulate || isRunning}
        className="mt-2"
        data-testid="strategy-intelligence-run-batch-simulation-button"
      >
        {isRunning ? "Batch simulation..." : "Run Batch Simulation"}
      </Button>

      {batchResult && (
        <div className="mt-2 space-y-1 text-xs" data-testid="strategy-intelligence-batch-simulation-result">
          <p data-testid="strategy-intelligence-batch-simulation-summary">summary={JSON.stringify(batchResult.summary || {})}</p>
          {(batchResult.items || []).slice(0, 8).map((item, index) => (
            <p key={`${item.simulation_id}-${index}`} data-testid={`strategy-intelligence-batch-simulation-item-${index}`}>
              {item.symbol} · risk={item.projected_risk_score} · adj_risk={item.confidence_adjusted_risk_score} · delta={item.risk_delta}
            </p>
          ))}
        </div>
      )}
    </section>
  );
};
