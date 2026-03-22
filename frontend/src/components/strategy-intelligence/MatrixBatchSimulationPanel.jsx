import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export const MatrixBatchSimulationPanel = ({
  canSimulate,
  config,
  onConfigChange,
  isRunning,
  onRun,
  result,
}) => {
  return (
    <section className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="strategy-intelligence-matrix-batch-panel">
      <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="strategy-intelligence-matrix-batch-title">
        Symbol + Strategy Matrix Batch Simulation
      </p>

      <div className="mt-2 grid gap-2 md:grid-cols-4" data-testid="strategy-intelligence-matrix-batch-form-grid">
        <Input
          value={config.symbols_text}
          onChange={(event) => onConfigChange("symbols_text", event.target.value)}
          placeholder="symbols (BTCUSDT,ETHUSDT)"
          data-testid="strategy-intelligence-matrix-symbols-input"
        />
        <Input
          value={config.strategy_bindings_text}
          onChange={(event) => onConfigChange("strategy_bindings_text", event.target.value)}
          placeholder="strategies (spot_pullback_v1,trend_follow_v1)"
          data-testid="strategy-intelligence-matrix-strategies-input"
        />
        <Input
          value={config.side}
          onChange={(event) => onConfigChange("side", event.target.value)}
          placeholder="side"
          data-testid="strategy-intelligence-matrix-side-input"
        />
        <Input
          type="number"
          value={config.base_notional}
          onChange={(event) => onConfigChange("base_notional", event.target.value)}
          placeholder="base_notional"
          data-testid="strategy-intelligence-matrix-notional-input"
        />
      </div>

      <Button
        className="mt-2"
        type="button"
        disabled={!canSimulate || isRunning}
        onClick={onRun}
        data-testid="strategy-intelligence-matrix-run-button"
      >
        {isRunning ? "Matrix simulation..." : "Run Matrix Batch"}
      </Button>

      {result && (
        <div className="mt-2 space-y-1 text-xs" data-testid="strategy-intelligence-matrix-result">
          <p data-testid="strategy-intelligence-matrix-result-summary">
            total_runs={result.total_runs} · avg_risk={result.summary?.avg_projected_risk_score}
          </p>
          {(result.items || []).slice(0, 16).map((item, index) => (
            <p key={`${item.simulation_id}-${index}`} data-testid={`strategy-intelligence-matrix-result-item-${index}`}>
              {item.symbol} · {item.strategy_binding} · risk={item.projected_risk_score} · severity={item.severity_band}
            </p>
          ))}
        </div>
      )}
    </section>
  );
};
