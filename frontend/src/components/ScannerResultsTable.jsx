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

const fallbackDecisionFromStrategyCode = (strategyCode) => {
  const code = String(strategyCode || "").toLowerCase();
  if (code.includes("bollinger")) {
    return "KARAR1(BC01)";
  }
  if (code.includes("breakout") || code.includes("structure") || code.includes("vortex")) {
    return "KARAR2(BC02)";
  }
  if (
    code.includes("momentum") ||
    code.includes("macd") ||
    code.includes("golden") ||
    code.includes("ichimoku") ||
    code.includes("supertrend") ||
    code.includes("fibonacci") ||
    code.includes("moving")
  ) {
    return "KARAR3(BC03)";
  }
  if (code.includes("fisher") || code.includes("divergence") || code.includes("stochastic") || code.includes("reversal")) {
    return "KARAR4(BC04)";
  }
  return "KARAR3(BC03)";
};

export const ScannerResultsTable = ({
  results,
  compactMode,
  onOpenTrade,
  onViewCard,
  onAddWatchlist,
  decisionApprovalMap,
}) => {
  const [expandedRowId, setExpandedRowId] = useState("");

  const resolveDecisionStrategyLabel = (item) => {
    const symbol = String(item?.symbol || "").toUpperCase();
    const decisions = item?.decisions || (decisionApprovalMap || {})[symbol] || null;
    if (!decisions || typeof decisions !== "object") {
      return String(item?.strategy_code || "legacy");
    }

    const signal = String(item?.signal || "").toLowerCase();
    const side = signal === "short" ? "short" : "long";
    const keyMap = [
      ["bc01", "KARAR1(BC01)"],
      ["bc02", "KARAR2(BC02)"],
      ["bc03", "KARAR3(BC03)"],
      ["bc04", "KARAR4(BC04)"],
    ];

    const matched = keyMap
      .filter(([key]) => Boolean(decisions?.[key]?.[side]))
      .map(([, label]) => label);

    if (matched.length > 0) {
      return matched.join(" + ");
    }

    const fallback = keyMap
      .filter(([key]) => Boolean(decisions?.[key]?.long || decisions?.[key]?.short))
      .map(([, label]) => label);
    if (fallback.length > 0) {
      return fallback.join(" + ");
    }

    return fallbackDecisionFromStrategyCode(item?.strategy_code);
  };

  const filtered = useMemo(() => {
    return results || [];
  }, [results]);

  return (
    <section className="space-y-3 rounded border border-slate-800 bg-slate-900 p-4" data-testid="scanner-results-section">
      <div className="flex flex-wrap items-center justify-between gap-2" data-testid="scanner-results-header">
        <div data-testid="scanner-results-title-wrap">
          <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="scanner-results-kicker">Scanner Results</p>
          <h3 className="text-base font-semibold" data-testid="scanner-results-title">Signal Grid</h3>
        </div>
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
                    <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`scanner-results-row-strategy-${item.id}`}>{resolveDecisionStrategyLabel(item)}</td>
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