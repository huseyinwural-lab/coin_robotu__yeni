import { Fragment, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";

const ALLOWED_QUOTE_ASSETS = new Set(["USDT", "USDC"]);

const detectQuoteAsset = (symbol) => {
  const normalized = String(symbol || "").trim().toUpperCase();
  if (normalized.endsWith("USDT")) return "USDT";
  if (normalized.endsWith("USDC")) return "USDC";
  return "UNKNOWN";
};

const scoreClassName = (score) => {
  const value = Number(score || 0);
  if (value >= 80) {
    return "text-emerald-300";
  }
  if (value >= 60) {
    return "text-amber-300";
  }
  return "text-slate-400";
};

export const ScannerResultsTable = ({
  results,
  compactMode,
  onOpenTrade,
  onViewCard,
  onAddWatchlist,
}) => {
  const [selectedStrategy, setSelectedStrategy] = useState("all");
  const [minConfidence, setMinConfidence] = useState(0);
  const [minScore, setMinScore] = useState(0);
  const [signalType, setSignalType] = useState("all");
  const [expandedRowId, setExpandedRowId] = useState("");

  const strategyOptions = useMemo(() => {
    const unique = Array.from(new Set((results || []).map((item) => String(item.strategy_code || "unknown"))));
    return unique.filter(Boolean).sort();
  }, [results]);

  const filtered = useMemo(() => {
    return (results || []).filter((item) => {
      const strategyPass = selectedStrategy === "all" || String(item.strategy_code || "") === selectedStrategy;
      const confidencePass = Number(item.confidence || 0) >= Number(minConfidence || 0);
      const scorePass = Number(item.signal_score || 0) >= Number(minScore || 0);
      const signal = String(item.signal || "none").toLowerCase();
      const signalPass = signalType === "all" || signal === signalType;
      return strategyPass && confidencePass && scorePass && signalPass;
    });
  }, [results, selectedStrategy, minConfidence, minScore, signalType]);

  const performance = useMemo(() => {
    const candidates = Number(results?.length || 0);
    const qualified = filtered.filter((item) => Number(item.signal_score || 0) >= 60).length;
    const actionable = filtered.filter((item) => {
      const signal = String(item.signal || "none").toLowerCase();
      return (signal === "long" || signal === "short") && Boolean(item.tradeable);
    }).length;
    return {
      symbols_scanned: candidates,
      candidates,
      qualified,
      signals: actionable,
    };
  }, [results, filtered]);

  return (
    <section className="space-y-3 rounded border border-slate-800 bg-slate-900 p-4" data-testid="scanner-results-section">
      <div className="flex flex-wrap items-center justify-between gap-2" data-testid="scanner-results-header">
        <div data-testid="scanner-results-title-wrap">
          <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="scanner-results-kicker">Scanner Results</p>
          <h3 className="text-base font-semibold" data-testid="scanner-results-title">Filtered Signal Grid</h3>
        </div>
      </div>

      <div className="grid gap-2 rounded border border-slate-800 bg-slate-950 p-3 md:grid-cols-4" data-testid="scanner-results-filter-bar">
        <label className="space-y-1" data-testid="scanner-results-filter-strategy-field">
          <span className="text-xs text-slate-400">Strategy</span>
          <select
            value={selectedStrategy}
            onChange={(event) => setSelectedStrategy(event.target.value)}
            className="h-9 w-full rounded border border-slate-700 bg-black px-2 text-xs"
            data-testid="scanner-results-filter-strategy-select"
          >
            <option value="all" data-testid="scanner-results-filter-strategy-option-all">all</option>
            {strategyOptions.map((item) => (
              <option key={item} value={item} data-testid={`scanner-results-filter-strategy-option-${item}`}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1" data-testid="scanner-results-filter-confidence-field">
          <span className="text-xs text-slate-400">Confidence ≥</span>
          <input
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={minConfidence}
            onChange={(event) => setMinConfidence(Number(event.target.value || 0))}
            className="h-9 w-full rounded border border-slate-700 bg-black px-2 text-xs"
            data-testid="scanner-results-filter-confidence-input"
          />
        </label>
        <label className="space-y-1" data-testid="scanner-results-filter-score-field">
          <span className="text-xs text-slate-400">Score ≥</span>
          <input
            type="number"
            min={0}
            max={100}
            step={1}
            value={minScore}
            onChange={(event) => setMinScore(Number(event.target.value || 0))}
            className="h-9 w-full rounded border border-slate-700 bg-black px-2 text-xs"
            data-testid="scanner-results-filter-score-input"
          />
        </label>
        <label className="space-y-1" data-testid="scanner-results-filter-signal-type-field">
          <span className="text-xs text-slate-400">Signal Type</span>
          <select
            value={signalType}
            onChange={(event) => setSignalType(event.target.value)}
            className="h-9 w-full rounded border border-slate-700 bg-black px-2 text-xs"
            data-testid="scanner-results-filter-signal-type-select"
          >
            <option value="all" data-testid="scanner-results-filter-signal-type-option-all">all</option>
            <option value="long" data-testid="scanner-results-filter-signal-type-option-long">long</option>
            <option value="short" data-testid="scanner-results-filter-signal-type-option-short">short</option>
            <option value="none" data-testid="scanner-results-filter-signal-type-option-none">none</option>
          </select>
        </label>
      </div>

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4" data-testid="scanner-results-performance-panel">
        <article className="rounded border border-slate-700 bg-slate-950 p-2" data-testid="scanner-performance-symbols-scanned-card">
          <p className="text-xs text-slate-400" data-testid="scanner-performance-symbols-scanned-label">Symbols Scanned</p>
          <p className="text-lg font-bold" data-testid="scanner-performance-symbols-scanned-value">{performance.symbols_scanned}</p>
        </article>
        <article className="rounded border border-slate-700 bg-slate-950 p-2" data-testid="scanner-performance-candidates-card">
          <p className="text-xs text-slate-400" data-testid="scanner-performance-candidates-label">Candidates</p>
          <p className="text-lg font-bold" data-testid="scanner-performance-candidates-value">{performance.candidates}</p>
        </article>
        <article className="rounded border border-slate-700 bg-slate-950 p-2" data-testid="scanner-performance-qualified-card">
          <p className="text-xs text-slate-400" data-testid="scanner-performance-qualified-label">Qualified</p>
          <p className="text-lg font-bold" data-testid="scanner-performance-qualified-value">{performance.qualified}</p>
        </article>
        <article className="rounded border border-slate-700 bg-slate-950 p-2" data-testid="scanner-performance-signals-card">
          <p className="text-xs text-slate-400" data-testid="scanner-performance-signals-label">Signals</p>
          <p className="text-lg font-bold" data-testid="scanner-performance-signals-value">{performance.signals}</p>
        </article>
      </div>

      <div className="grid gap-3 md:hidden" data-testid="scanner-results-mobile-cards">
        {filtered.map((item) => (
          <article key={item.id} className="rounded border border-slate-800 bg-slate-950 p-3" data-testid={`scanner-results-mobile-card-${item.id}`}>
            {(() => {
              const quoteAsset = String(item?.quote_asset || item?.payload?.quote_asset || detectQuoteAsset(item.symbol)).toUpperCase();
              const unsupported = !ALLOWED_QUOTE_ASSETS.has(quoteAsset);
              return (
                <>
            <p className="text-sm font-semibold" data-testid={`scanner-results-mobile-symbol-${item.id}`}>{item.symbol}</p>
            <p className="text-xs text-cyan-300" data-testid={`scanner-results-mobile-explain-${item.id}`}>
              {(item.explain || []).slice(0, 3).join(" • ") || "Signal explain unavailable"}
            </p>
            <p className="text-xs text-slate-400" data-testid={`scanner-results-mobile-quote-asset-${item.id}`}>Quote Asset: {quoteAsset}</p>
            <p className="text-xs text-slate-400" data-testid={`scanner-results-mobile-signal-${item.id}`}>Signal: {item.signal}</p>
            <p className="text-xs text-slate-400" data-testid={`scanner-results-mobile-confidence-${item.id}`}>Confidence: {item.confidence}</p>
            <p className={`text-xs ${scoreClassName(item.signal_score)}`} data-testid={`scanner-results-mobile-score-${item.id}`}>Score: {item.signal_score}</p>
            <p className="text-xs text-slate-400" data-testid={`scanner-results-mobile-tradeable-${item.id}`}>
              tradeable: <span className={`font-semibold ${item.tradeable ? "text-emerald-300" : "text-rose-300"}`}>{String(Boolean(item.tradeable)).toUpperCase()}</span>
            </p>
            <p className="text-xs text-slate-400" data-testid={`scanner-results-mobile-first-precheck-failure-${item.id}`}>
              first_precheck_failure_code: <span className="font-semibold text-rose-200">{item.first_precheck_failure_code || "-"}</span>
            </p>
            {unsupported && (
              <p className="text-xs text-amber-300" data-testid={`scanner-results-mobile-policy-warning-${item.id}`}>
                Desteklenmeyen parite: yalnızca USDT/USDC sembolleri işleme alınır.
              </p>
            )}
            <div className="mt-2 flex flex-wrap gap-2" data-testid={`scanner-results-mobile-actions-${item.id}`}>
              <Button variant="outline" disabled={unsupported} onClick={() => onOpenTrade(item)} data-testid={`scanner-results-mobile-open-trade-${item.id}`}>Open Trade</Button>
              <Button variant="outline" disabled={unsupported} onClick={() => onViewCard(item)} data-testid={`scanner-results-mobile-view-card-${item.id}`}>View Card</Button>
              <Button variant="outline" disabled={unsupported} onClick={() => onAddWatchlist(item)} data-testid={`scanner-results-mobile-add-watchlist-${item.id}`}>Add Watchlist</Button>
            </div>
                </>
              );
            })()}
          </article>
        ))}
      </div>

      <div className="hidden overflow-x-auto rounded border border-slate-800 md:block" data-testid="scanner-results-table-wrapper">
        <table className="min-w-full text-sm" data-testid="scanner-results-table">
          <thead className="bg-slate-800 text-left" data-testid="scanner-results-table-head">
            <tr>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="scanner-results-head-symbol">Symbol</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="scanner-results-head-quote-asset">Quote Asset</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="scanner-results-head-signal">Signal</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="scanner-results-head-confidence">Confidence</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="scanner-results-head-score">Score</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="scanner-results-head-tradeable">Tradeable</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="scanner-results-head-first-precheck-failure">First Precheck Failure</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="scanner-results-head-strategy">Strategy</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="scanner-results-head-policy">Strategy Policy</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid="scanner-results-head-actions">Actions</th>
            </tr>
          </thead>
          <tbody data-testid="scanner-results-table-body">
            {filtered.map((item) => {
              const expanded = expandedRowId === item.id;
              const snapshot = item.payload || {};
              const quoteAsset = String(item?.quote_asset || snapshot?.quote_asset || detectQuoteAsset(item.symbol)).toUpperCase();
              const unsupported = !ALLOWED_QUOTE_ASSETS.has(quoteAsset);
              return (
                <Fragment key={item.id}>
                  <tr
                    className={`border-t border-slate-800 hover:bg-slate-950/70 ${unsupported ? "opacity-50" : ""}`}
                    data-testid={`scanner-results-row-${item.id}`}
                    onClick={() => setExpandedRowId(expanded ? "" : item.id)}
                  >
                    <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`scanner-results-row-symbol-${item.id}`}>
                      <p data-testid={`scanner-results-row-symbol-label-${item.id}`}>{item.symbol}</p>
                      <p className="text-xs text-cyan-300" data-testid={`scanner-results-row-explain-summary-${item.id}`}>
                        {(item.explain || []).slice(0, 3).join(" • ") || "Signal explain unavailable"}
                      </p>
                    </td>
                    <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`scanner-results-row-quote-asset-${item.id}`}>{quoteAsset}</td>
                    <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`scanner-results-row-signal-${item.id}`}>{item.signal}</td>
                    <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`scanner-results-row-confidence-${item.id}`}>{item.confidence}</td>
                    <td className={`${compactMode ? "px-2 py-1" : "px-3 py-2"} ${scoreClassName(item.signal_score)}`} data-testid={`scanner-results-row-score-${item.id}`}>
                      {item.signal_score}
                    </td>
                    <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`scanner-results-row-tradeable-${item.id}`}>
                      <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${item.tradeable ? "bg-emerald-500/20 text-emerald-300" : "bg-rose-500/20 text-rose-300"}`}>
                        {String(Boolean(item.tradeable)).toUpperCase()}
                      </span>
                    </td>
                    <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`scanner-results-row-first-precheck-failure-${item.id}`}>
                      <span className="text-xs text-rose-200">{item.first_precheck_failure_code || "-"}</span>
                    </td>
                    <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`scanner-results-row-strategy-${item.id}`}>{item.strategy_code}</td>
                    <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`scanner-results-row-policy-${item.id}`}>
                      {unsupported ? "UNSUPPORTED" : "SUPPORTED"}
                    </td>
                    <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`scanner-results-row-actions-${item.id}`}>
                      <div className="flex flex-wrap gap-2" data-testid={`scanner-results-row-actions-wrap-${item.id}`}>
                        <Button variant="outline" disabled={unsupported} onClick={(event) => { event.stopPropagation(); onOpenTrade(item); }} data-testid={`scanner-results-open-trade-${item.id}`}>Open Trade</Button>
                        <Button variant="outline" disabled={unsupported} onClick={(event) => { event.stopPropagation(); onViewCard(item); }} data-testid={`scanner-results-view-card-${item.id}`}>View Card</Button>
                        <Button variant="outline" disabled={unsupported} onClick={(event) => { event.stopPropagation(); onAddWatchlist(item); }} data-testid={`scanner-results-add-watchlist-${item.id}`}>Add Watchlist</Button>
                      </div>
                    </td>
                  </tr>
                  {expanded && (
                    <tr className="border-t border-slate-800 bg-slate-950/60" data-testid={`scanner-results-explainability-row-${item.id}`}>
                      <td colSpan={10} className="px-3 py-2" data-testid={`scanner-results-explainability-cell-${item.id}`}>
                        <div className="grid gap-2 md:grid-cols-4" data-testid={`scanner-results-explainability-grid-${item.id}`}>
                          <p className="text-xs text-slate-300" data-testid={`scanner-results-explainability-volume-spike-${item.id}`}>volume spike: {snapshot?.volume_spike ?? snapshot?.relative_volume ?? "-"}</p>
                          <p className="text-xs text-slate-300" data-testid={`scanner-results-explainability-rsi-${item.id}`}>RSI: {snapshot?.rsi ?? snapshot?.rsi14 ?? snapshot?.indicator_snapshot?.rsi14 ?? "-"}</p>
                          <p className="text-xs text-slate-300" data-testid={`scanner-results-explainability-spread-regime-${item.id}`}>spread regime: {snapshot?.spread_regime ?? snapshot?.spread_state ?? "-"}</p>
                          <p className="text-xs text-slate-300" data-testid={`scanner-results-explainability-market-volatility-${item.id}`}>market volatility: {snapshot?.market_volatility ?? snapshot?.atr_pct ?? "-"}</p>
                          <p className="text-xs text-slate-300" data-testid={`scanner-results-explainability-precheck-tradeable-${item.id}`}>precheck tradeable: {String(Boolean(snapshot?.tradeable)).toUpperCase()}</p>
                          <p className="text-xs text-rose-200" data-testid={`scanner-results-explainability-precheck-first-failure-${item.id}`}>first_precheck_failure_code: {snapshot?.first_precheck_failure_code || "-"}</p>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2" data-testid={`scanner-results-explain-list-${item.id}`}>
                          {(item.explain || []).map((entry, index) => (
                            <span key={`${entry}-${index}`} className="rounded border border-cyan-500/50 bg-cyan-500/10 px-2 py-0.5 text-xs text-cyan-100" data-testid={`scanner-results-explain-item-${item.id}-${index}`}>
                              {entry}
                            </span>
                          ))}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
};