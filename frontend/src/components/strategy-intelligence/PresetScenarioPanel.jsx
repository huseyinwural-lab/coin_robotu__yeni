import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export const PresetScenarioPanel = ({
  canSimulate,
  presets = [],
  selectedPreset,
  onSelectPreset,
  isRunning,
  onRunPreset,
  isCustomizeOpen,
  onToggleCustomize,
  presetOverrides,
  onOverrideChange,
  onCustomizeRun,
}) => {
  return (
    <section className="border border-slate-800 bg-slate-900 p-4" data-testid="strategy-intelligence-preset-scenario-panel">
      <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="strategy-intelligence-preset-scenario-title">
        Preset Scenarios (Quick + Advanced)
      </p>

      <select
        className="mt-2 w-full rounded border border-slate-700 bg-slate-950 px-2 py-2 text-sm"
        value={selectedPreset}
        onChange={(event) => onSelectPreset(event.target.value)}
        disabled={!canSimulate}
        data-testid="strategy-intelligence-preset-scenario-select"
      >
        <option value="">Preset seçin</option>
        {presets.map((item) => (
          <option key={item.preset_key} value={item.preset_key}>
            {item.label}
          </option>
        ))}
      </select>

      {selectedPreset && (
        <p className="mt-2 text-xs text-slate-400" data-testid="strategy-intelligence-preset-scenario-description">
          {(presets.find((item) => item.preset_key === selectedPreset) || {}).description || "-"}
        </p>
      )}

      <div className="mt-2 flex flex-wrap gap-2" data-testid="strategy-intelligence-preset-scenario-actions">
        <Button
          type="button"
          disabled={!canSimulate || isRunning || !selectedPreset}
          onClick={onRunPreset}
          data-testid="strategy-intelligence-preset-run-button"
        >
          {isRunning ? "Running..." : "Run Preset"}
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={!canSimulate || !selectedPreset}
          onClick={onToggleCustomize}
          data-testid="strategy-intelligence-preset-customize-toggle-button"
        >
          {isCustomizeOpen ? "Customize Panel Gizle" : "Customize & Run"}
        </Button>
      </div>

      {isCustomizeOpen && (
        <div className="mt-2 grid gap-2 sm:grid-cols-2" data-testid="strategy-intelligence-preset-customize-panel">
          <Input
            type="number"
            step="0.1"
            value={presetOverrides.volatility_pct ?? ""}
            onChange={(event) => onOverrideChange("volatility_pct", event.target.value)}
            placeholder="volatility_pct"
            data-testid="strategy-intelligence-preset-override-volatility-input"
          />
          <Input
            type="number"
            step="0.01"
            value={presetOverrides.notional_scale ?? ""}
            onChange={(event) => onOverrideChange("notional_scale", event.target.value)}
            placeholder="notional_scale"
            data-testid="strategy-intelligence-preset-override-notional-scale-input"
          />
          <Input
            type="number"
            step="0.01"
            value={presetOverrides.signal_confidence ?? ""}
            onChange={(event) => onOverrideChange("signal_confidence", event.target.value)}
            placeholder="signal_confidence"
            data-testid="strategy-intelligence-preset-override-signal-confidence-input"
          />
          <Input
            type="number"
            step="0.01"
            value={presetOverrides.position_size_scale ?? ""}
            onChange={(event) => onOverrideChange("position_size_scale", event.target.value)}
            placeholder="position_size_scale"
            data-testid="strategy-intelligence-preset-override-position-scale-input"
          />
          <div className="sm:col-span-2">
            <Button
              type="button"
              disabled={!canSimulate || isRunning || !selectedPreset}
              onClick={onCustomizeRun}
              data-testid="strategy-intelligence-preset-customize-run-button"
            >
              {isRunning ? "Running..." : "Customize & Run"}
            </Button>
          </div>
        </div>
      )}
    </section>
  );
};
