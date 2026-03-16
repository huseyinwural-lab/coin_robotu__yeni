import { SymbolSelectorPanel } from "@/components/SymbolSelectorPanel";

export const TradeSymbolSelection = ({
  source,
  onSourceChange,
  mode,
  onModeChange,
  selectedSymbols,
  onSelectedSymbolsChange,
  watchlistOnly,
  onWatchlistOnlyChange,
}) => {
  return (
    <section className="space-y-3 rounded border border-slate-800 bg-slate-900 p-4" data-testid="trade-symbol-selection-section">
      <div className="flex flex-wrap items-center justify-between gap-2" data-testid="trade-symbol-selection-header">
        <div data-testid="trade-symbol-selection-title-wrap">
          <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="trade-symbol-selection-kicker">Symbol Selection</p>
          <h3 className="text-base font-semibold text-slate-100" data-testid="trade-symbol-selection-title">Scanner Scope</h3>
          <div className="mt-2 flex flex-wrap items-center gap-2" data-testid="trade-symbol-selection-policy-row">
            <span className="rounded-full border border-emerald-500/50 bg-emerald-500/15 px-2 py-0.5 text-[11px] font-semibold text-emerald-200" data-testid="trade-symbol-selection-policy-badge">
              USDT/USDC-ONLY
            </span>
            <p className="text-xs text-slate-400" data-testid="trade-symbol-selection-policy-text">
              Unsupported quote assets stay visible but disabled.
            </p>
          </div>
        </div>
        <label className="flex items-center gap-2 text-xs text-slate-300" data-testid="trade-symbol-selection-watchlist-mode-toggle-wrap">
          <input
            type="checkbox"
            checked={watchlistOnly}
            onChange={(event) => onWatchlistOnlyChange(Boolean(event.target.checked))}
            data-testid="trade-symbol-selection-watchlist-mode-toggle"
          />
          Watchlist Mode
        </label>
      </div>

      <SymbolSelectorPanel
        testIdPrefix="user-scanner-symbol-selector"
        exchange="binance"
        marketType="spot"
        source={source}
        onSourceChange={onSourceChange}
        mode={mode}
        onModeChange={onModeChange}
        selectedSymbols={selectedSymbols}
        onSelectedSymbolsChange={onSelectedSymbolsChange}
        multi
      />
    </section>
  );
};