import { SymbolSelectorPanel } from "@/components/SymbolSelectorPanel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export const SimulationGuardPanel = ({
  form,
  setForm,
  canSimulate,
  isRunning,
  onRun,
  symbolSource,
  onSymbolSource,
  symbolMode,
  onSymbolMode,
  selectedSymbols,
  onSelectedSymbols,
}) => {
  const userIdValid = String(form.user_id || "").trim().length > 0;

  return (
    <section className="border border-slate-800 bg-slate-900 p-4" data-testid="strategy-intelligence-simulation-guard-panel">
      <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="strategy-intelligence-simulation-guard-title">Simulation Guard Panel</p>

      <div className="mt-2 grid gap-2 md:grid-cols-3" data-testid="strategy-intelligence-simulation-guard-form-grid">
        <Input
          placeholder="user_id"
          value={form.user_id}
          onChange={(event) => setForm((prev) => ({ ...prev, user_id: event.target.value }))}
          data-testid="strategy-intelligence-simulation-user-id-input"
        />
        <Input
          placeholder="symbol"
          value={form.symbol}
          onChange={(event) => setForm((prev) => ({ ...prev, symbol: event.target.value.toUpperCase() }))}
          data-testid="strategy-intelligence-simulation-symbol-input"
        />
        <Input
          placeholder="side"
          value={form.side}
          onChange={(event) => setForm((prev) => ({ ...prev, side: event.target.value }))}
          data-testid="strategy-intelligence-simulation-side-input"
        />
        <Input
          type="number"
          placeholder="notional"
          value={form.notional}
          onChange={(event) => setForm((prev) => ({ ...prev, notional: event.target.value }))}
          data-testid="strategy-intelligence-simulation-notional-input"
        />
        <Input
          placeholder="strategy_binding"
          value={form.strategy_binding}
          onChange={(event) => setForm((prev) => ({ ...prev, strategy_binding: event.target.value }))}
          data-testid="strategy-intelligence-simulation-strategy-input"
        />
        <Input
          type="number"
          placeholder="volatility_pct"
          value={form.volatility_pct}
          onChange={(event) => setForm((prev) => ({ ...prev, volatility_pct: event.target.value }))}
          data-testid="strategy-intelligence-simulation-volatility-input"
        />
      </div>

      <div className="mt-3" data-testid="strategy-intelligence-symbol-selector-wrapper">
        <SymbolSelectorPanel
          testIdPrefix="strategy-intelligence-symbol-selector"
          exchange="binance"
          marketType="spot"
          source={symbolSource}
          onSourceChange={onSymbolSource}
          mode={symbolMode}
          onModeChange={onSymbolMode}
          selectedSymbols={selectedSymbols}
          onSelectedSymbolsChange={onSelectedSymbols}
          multi={false}
        />
      </div>

      <div className="mt-3" data-testid="strategy-intelligence-simulation-guard-actions">
        <Button
          onClick={onRun}
          disabled={!canSimulate || !userIdValid || isRunning}
          data-testid="strategy-intelligence-run-simulation-button"
        >
          {isRunning ? "Simulation..." : "Run Simulation"}
        </Button>
      </div>
    </section>
  );
};
